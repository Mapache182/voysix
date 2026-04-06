import whisper
import torch
import tempfile
import threading
import os
import io
from faster_whisper import WhisperModel

from .config_store import get_config

_models = {}
_lock = threading.Lock()
_busy = False
_initializing = False


def is_busy():
    return _busy


def is_initializing():
    return _initializing


def get_device():
    cfg = get_config()
    requested_device = cfg.get("device", "cpu")
    if requested_device == "cuda" and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def warm_up():
    """Immediately downloads the default model in background if not present."""
    global _initializing
    cfg = get_config()
    model_name = cfg["model"]
    engine = cfg.get("engine", "openai-whisper")
    device = get_device()
    
    with _lock:
         key = (model_name, engine, device)
         if key not in _models:
            _initializing = True
            try:
                get_model(model_name, engine, device)
            finally:
                _initializing = False


MODELS_DIR = os.getenv("MODELS_DIR", "/data/models")

def get_model(name: str, engine: str, device: str):
    key = (name, engine, device)
    if key not in _models:
        print(f"--- [Worker] Loading model '{name}' ({engine}) on {device} ---")
        if engine == "faster-whisper":
            # For Faster-Whisper we use int8 on CPU and float16 on GPU for maximum speed
            compute_type = "float16" if device == "cuda" else "int8"
            _models[key] = WhisperModel(name, device=device, compute_type=compute_type, download_root=MODELS_DIR)
        else:
            _models[key] = whisper.load_model(name, device=device, download_root=MODELS_DIR)
    return _models[key]


import re

def _apply_replacements(text, replacements_str):
    if not text or not replacements_str:
        return text
    
    lines = replacements_str.split('\n')
    for line in lines:
        if ':' in line:
            try:
                find, replace = line.split(':', 1)
                find = find.strip()
                replace = replace.strip()
                if find:
                    pattern = re.compile(rf'\b{re.escape(find)}\b', re.IGNORECASE)
                    text = pattern.sub(replace, text)
            except:
                continue
    return text

def _apply_smart_normalization(text):
    if not text:
        return text
    
    # 1. Fix spacing around punctuation
    text = re.sub(r'\s+([,.!?])', r'\1', text)
    
    # 2. Capitalize sentences
    def capitalize(match):
        return match.group(1) + match.group(2).upper()
    text = re.sub(r'(^|[.!?]\s+)([a-zа-я])', capitalize, text)

    return text


def transcribe_audio(audio_bytes: bytes) -> str:
    global _busy

    with _lock:
        _busy = True
        try:
            cfg = get_config()
            device = get_device()
            engine = cfg.get("engine", "openai-whisper")

            model = get_model(cfg["model"], engine, device)

            with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as tmp:
                tmp.write(audio_bytes)
                tmp.flush()

                if engine == "faster-whisper":
                    # Faster Whisper API
                    segments, info = model.transcribe(
                        tmp.name,
                        language=None if cfg["language"] == "auto" else cfg["language"],
                        temperature=cfg.get("temperature", 0.0),
                        beam_size=cfg.get("beam_size", 1),
                        initial_prompt=cfg.get("initial_prompt", ""),
                        no_speech_threshold=cfg.get("no_speech_threshold", 0.6),
                        log_prob_threshold=cfg.get("logprob_threshold", -1.0),
                        compression_ratio_threshold=cfg.get("compression_ratio_threshold", 2.4),
                        condition_on_previous_text=cfg.get("condition_on_previous_text", True),
                        hallucination_silence_threshold=cfg.get("hallucination_silence_threshold", 2.0),
                        repetition_penalty=cfg.get("repetition_penalty", 1.0),
                        no_repeat_ngram_size=cfg.get("no_repeat_ngram_size", 0),
                        vad_filter=True
                    )
                    text = " ".join([seg.text for seg in segments]).strip()
                else:
                    # Original Whisper API
                    result = model.transcribe(
                        tmp.name,
                        language=None if cfg["language"] == "auto" else cfg["language"],
                        temperature=cfg.get("temperature", 0.0),
                        beam_size=cfg.get("beam_size", 1),
                        best_of=cfg.get("beam_size", 1) if cfg.get("temperature", 0.0) > 0 else 1,
                        initial_prompt=cfg.get("initial_prompt", ""),
                        no_speech_threshold=cfg.get("no_speech_threshold", 0.6),
                        logprob_threshold=cfg.get("logprob_threshold", -1.0),
                        compression_ratio_threshold=cfg.get("compression_ratio_threshold", 2.4),
                        condition_on_previous_text=cfg.get("condition_on_previous_text", True),
                        fp16=(device == "cuda")
                    )
                    text = result["text"].strip()

                # 🔹 Post-processing on worker side
                text = _apply_replacements(text, cfg.get("word_replacements", ""))
                if cfg.get("smart_normalization", False):
                    text = _apply_smart_normalization(text)
                
                return text

        finally:
            _busy = False