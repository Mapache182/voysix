import threading
import os

_lock = threading.Lock()

_config = {
    "model": "base",
    "language": "auto",
    "engine": "openai-whisper",
    "device": os.getenv("DEFAULT_DEVICE", "cpu"), # 'cpu' or 'cuda'
    "temperature": 0.0,
    "beam_size": 1,
    "initial_prompt": "",
    "no_speech_threshold": 0.6,
    "logprob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "condition_on_previous_text": True,
    "hallucination_silence_threshold": 2.0, # Faster-Whisper specific
    "repetition_penalty": 1.0, # Faster-Whisper specific
    "no_repeat_ngram_size": 0, # Faster-Whisper specific
    "smart_normalization": False,
    "word_replacements": "",
}

_capabilities = {
    "models": ["base", "small", "medium", "large", "distil-large-v3"],
    "languages": ["auto", "en", "ru"],
    "engines": ["openai-whisper", "faster-whisper"],
    "devices": ["cpu", "cuda"]
}


def get_config():
    with _lock:
        return dict(_config)


def update_config(new_config: dict):
    with _lock:
        for key in new_config:
            if key in _config:
                _config[key] = new_config[key]


def get_capabilities():
    return _capabilities