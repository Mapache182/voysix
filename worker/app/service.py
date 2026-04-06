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


def get_model(name: str, engine: str, device: str):
    key = (name, engine, device)
    if key not in _models:
        print(f"--- [Worker] Loading model '{name}' ({engine}) on {device} ---")
        if engine == "faster-whisper":
            # For Faster-Whisper we use int8 on CPU and float16 on GPU for maximum speed
            compute_type = "float16" if device == "cuda" else "int8"
            _models[key] = WhisperModel(name, device=device, compute_type=compute_type)
        else:
            _models[key] = whisper.load_model(name, device=device)
    return _models[key]


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
                    )
                    text = " ".join([seg.text for seg in segments]).strip()
                    return text
                else:
                    # Original Whisper API
                    result = model.transcribe(
                        tmp.name,
                        language=None if cfg["language"] == "auto" else cfg["language"],
                        temperature=cfg.get("temperature", 0.0),
                        beam_size=cfg.get("beam_size", 1),
                        initial_prompt=cfg.get("initial_prompt", ""),
                        no_speech_threshold=cfg.get("no_speech_threshold", 0.6),
                        logprob_threshold=cfg.get("logprob_threshold", -1.0),
                        fp16=(device == "cuda")
                    )
                    return result["text"].strip()

        finally:
            _busy = False