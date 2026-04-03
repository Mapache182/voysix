import threading

_lock = threading.Lock()

_config = {
    "model": "base",
    "language": "auto",
    "engine": "whisper",
    "temperature": 0.0,
    "beam_size": 1,
    "initial_prompt": ""
}

_capabilities = {
    "models": ["base", "small", "medium"],
    "languages": ["auto", "en", "ru"],
    "engines": ["whisper"]
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