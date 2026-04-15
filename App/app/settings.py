import json
import os

# Use %APPDATA%/voysix/config.json for persistence across updates
if os.name == "nt":
    APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", ""), "voysix")
    if not os.path.exists(APP_DATA_DIR):
        os.makedirs(APP_DATA_DIR, exist_ok=True)
    CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
else:
    CONFIG_FILE = "config.json"


DEFAULT_CONFIG = {
    "model_name": "base",
    "local_whisper_enabled": True,
    "hotkey": "middle_click",
    "backspace_cleanup": 0,
    "paste_delay": 0.7,

    "output_mode": "type",  # "type", "clipboard", "console"
    "autostart": False,
    "selected_mic": None,
    "language": "auto",
    "engine": "openai-whisper", # or "faster-whisper"
    "window_pos": [20, 20],
    "window_size": [160, 40],
    "opacity": 0.9,
    "beam_size": 5,
    "temperature": 0.0,
    "initial_prompt": "Это запись русской речи. Пожалуйста, соблюдайте пунктуацию и правильные окончания слов.",
    "ui_language": "en",
    "ui_design": "waveform", # "classic" or "waveform"
    "remote_mode": False,
    "remote_worker_name": "voysix-worker",
    "remote_worker_url": "",
    "remote_api_key": "",
    "tailscale_auth_key": "",
    "always_on_top": True,
    "add_space": False,
    "add_newline": False,
    "unload_idle": True,
    "idle_time_minutes": 5,
    "pre_record_seconds": 0.0,
    "pause_media_on_record": False,
    "remote_model_name": "base",
    "remote_engine": "openai-whisper",
    "remote_beam_size": 5,
    "remote_temperature": 0.0,
    "remote_language": "auto",
    "remote_initial_prompt": "Это запись русской речи. Пожалуйста, соблюдайте пунктуацию и правильные окончания слов.",
    "no_speech_threshold": 0.6,
    "logprob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "condition_on_previous_text": True,
    "hallucination_silence_threshold": 2.0,
    "repetition_penalty": 1.0,
    "no_repeat_ngram_size": 0,
    "smart_normalization": False,
    "word_replacements": "мерч:merch\nвоисикс:Voysix",
    
    "remote_no_speech_threshold": 0.6,
    "remote_logprob_threshold": -1.0,
    "remote_compression_ratio_threshold": 2.4,
    "remote_condition_on_previous_text": True,
    "remote_hallucination_silence_threshold": 2.0,
    "remote_repetition_penalty": 1.0,
    "remote_no_repeat_ngram_size": 0,
    "remote_smart_normalization": False,
    "remote_word_replacements": "",
    "remote_audio_format": "flac"
}

def load_config():
    # Legacy config location (local directory)
    OLD_CONFIG = "config.json"
    
    # 1. Migration: if old config exists but new one doesn't, move it
    if os.path.exists(OLD_CONFIG) and not os.path.exists(CONFIG_FILE):
        try:
            import shutil
            shutil.copy2(OLD_CONFIG, CONFIG_FILE)
            print(f"Migrated configuration from {OLD_CONFIG} to {CONFIG_FILE}")
            # We keep the old one as backup for now, or we could rename/remove it
        except Exception as e:
            print(f"Migration failed: {e}")

    # 2. Normal load
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")
