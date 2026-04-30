import sys
import os
import subprocess
from cx_Freeze import setup, Executable

# --- Auto-fix environment ---
try:
    import chardet
except ImportError:
    print("Installing missing dependency: chardet...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "chardet"])
    import chardet

try:
    import soundfile
except ImportError:
    print("Installing missing dependency: soundfile...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "soundfile"])
    import soundfile

sys.setrecursionlimit(5000)

# --- Dependencies ---
# Attempt to find PySide6 plugins directory
import PySide6.QtCore
pyside6_dir = os.path.dirname(PySide6.QtCore.__file__)
plugins_dir = os.path.join(pyside6_dir, "plugins")

import shiboken6
shiboken_dir = os.path.dirname(shiboken6.__file__)

build_exe_options = {
    "packages": [
        "os", "sys", "whisper", "faster_whisper", "huggingface_hub", "tokenizers", 
        "sounddevice", "numpy", "pynput", "pyautogui", "pyperclip", "threading", 
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "torch", "json", "ctypes", "pycaw", "comtypes", "psutil", 
        "requests", "chardet", "idna", "certifi", "soundfile"
    ],
    "include_files": [
        ("app", "app"),
        ("assets", "assets"),
        ("version.txt", "version.txt"),
        (shiboken_dir, "lib/shiboken6"), # Manually include shiboken files
    ],
    "include_msvcr": True,
    "excludes": [
        "tkinter",
        "pydoc",
        "torch.include",
        "coverage"
    ],
    "optimize": 2,
    "zip_include_packages": [],
    "zip_exclude_packages": ["*"],
}

# --- macOS specific options ---
bdist_mac_options = {
    "bundle_name": "Voysix",
    "iconfile": "assets/icon.icns", # Will need to create this
    "plist_items": [
        ("CFBundleIdentifier", "com.voysix.app"),
        ("NSMicrophoneUsageDescription", "Voysix needs microphone access for speech-to-text."),
        ("LSUIElement", "1") # Hides from dock if it's a tray app
    ],
}

if os.path.exists(plugins_dir):
    build_exe_options["include_files"].append((plugins_dir, "lib/PySide6/plugins"))

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
    version="4.4.93",
    description="Voysix Application (Speech-to-Text)",
    options={
        "build_exe": build_exe_options,
        "bdist_mac": bdist_mac_options
    },
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="Voysix.exe" if sys.platform == "win32" else "Voysix",
            icon="assets/icon.ico" if sys.platform == "win32" else "assets/icon.icns",
            shortcut_name="Voysix",
            shortcut_dir="ProgramMenuFolder",
        )
    ],
)
