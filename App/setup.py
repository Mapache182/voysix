import sys
import os
from cx_Freeze import setup, Executable

sys.setrecursionlimit(5000)

# --- Dependencies ---
build_exe_options = {
    "packages": ["os", "sys", "whisper", "faster_whisper", "huggingface_hub", "tokenizers", "sounddevice", "numpy", "pynput", "pyautogui", "pyperclip", "threading", "PySide6", "torch", "json", "ctypes", "pycaw", "comtypes", "psutil", "requests"],
    "include_files": [
        ("app", "app"),
        ("assets", "assets"),
        ("version.txt", "version.txt"),
    ],
    "excludes": [
        "tkinter",
        "pydoc",
        "torch.include"
    ],
    "optimize": 2,
    "zip_include_packages": [],
    "zip_exclude_packages": ["*"],
}

# --- Try to find sounddevice data folder dynamically ---
try:
    import sounddevice
    sounddevice_data = os.path.join(os.path.dirname(sounddevice.__file__), "_sounddevice_data")
    if os.path.exists(sounddevice_data):
        build_exe_options["include_files"].append((sounddevice_data, "lib/_sounddevice_data"))
except ImportError:
    pass

# --- Executable ---
base = None
if sys.platform == "win32":
    base = "Win32GUI" # Hides the console window

setup(
    name="Voysix",
    version="4.4.69",
    description="Voysix Application (Speech-to-Text)",
    options={
        "build_exe": build_exe_options
    },
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="Voysix.exe",
            icon="assets/icon.ico",
            shortcut_name="Voysix",
            shortcut_dir="ProgramMenuFolder",
        )
    ],
)
