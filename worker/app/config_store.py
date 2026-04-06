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
    "logprob_threshold": -1.0
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