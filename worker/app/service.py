import whisper
import tempfile
import threading

from .config_store import get_config

_models = {}
_lock = threading.Lock()
_busy = False


def is_busy():
    return _busy


def get_model(name: str):
    if name not in _models:
        _models[name] = whisper.load_model(name)
    return _models[name]


def transcribe_audio(audio_bytes: bytes) -> str:
    global _busy

    with _lock:
        _busy = True
        try:
            cfg = get_config()

            model = get_model(cfg["model"])

            with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as tmp:
                tmp.write(audio_bytes)
                tmp.flush()

                result = model.transcribe(
                    tmp.name,
                    language=None if cfg["language"] == "auto" else cfg["language"],
                    temperature=cfg.get("temperature", 0.0),
                    beam_size=cfg.get("beam_size", 1),
                    initial_prompt=cfg.get("initial_prompt", "")
                )

                return result["text"]

        finally:
            _busy = False