import os
import sys

# 🔹 Workaround for AttributeError: module 'coverage' has no attribute 'types'
# which happens in environments where 'coverage' 7.x is installed 
# and 'numba' (via whisper) tries to access 'coverage.types'.
try:
    if 'coverage' in sys.modules:
        import coverage
        if not hasattr(coverage, 'types'):
            coverage.types = type("MockTypes", (), {})
except:
    pass

import whisper
import sounddevice as sd
import numpy as np
from pynput import mouse, keyboard
import pyautogui
import pyperclip
import threading
import queue
import time
import sys
import ctypes
import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

# --- Windows API for low-level paste ---
user32 = ctypes.windll.user32
VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002

def win32_paste():
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

# --- Configuration Management ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "model_name": "base",
    "hotkey": "middle_click",
    "backspace_cleanup": 2,
    "paste_delay": 0.7
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# --- Global State ---
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.float32
kb_controller = keyboard.Controller()

class WhisperApp:
    def __init__(self):
        self.config = load_config()
        self.recording = False
        self.processing = False
        self.audio_data = []
        self.model = None
        self.tray_icon = None
        self.stop_requested = False
        
        # Initial model load
        self.load_whisper_model()

    def load_whisper_model(self):
        m_name = self.config.get("model_name", "base")
        print(f"Loading Whisper model '{m_name}'...")
        # Note: model load is heavy, we print status to console if open
        self.model = whisper.load_model(m_name)
        print("Model loaded.")

    def start_recording(self):
        if not self.recording and not self.processing:
            try: pyperclip.copy("") 
            except: pass
            
            print("\n[REC] Started...")
            self.recording = True
            self.audio_data = []
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._audio_callback
            )
            self.stream.start()

    def _audio_callback(self, indata, frames, time, status):
        if self.recording:
            self.audio_data.append(indata.copy())

    def stop_recording(self):
        if self.recording:
            print("[REC] Stopped. Transcribing...")
            self.recording = False
            self.processing = True
            self.stream.stop()
            self.stream.close()
            
            if self.audio_data:
                full_audio = np.concatenate(self.audio_data, axis=0).flatten()
                threading.Thread(target=self.transcribe_and_type, args=(full_audio,)).start()
            else:
                self.processing = False

    def transcribe_and_type(self, audio_np):
        try:
            result = self.model.transcribe(audio_np, fp16=False)
            text = result.get("text", "").strip()
            
            if text:
                print(f"Recognized: [{text}]")
                pyperclip.copy(text)
                
                # Wait for system back-focus
                time.sleep(self.config.get("paste_delay", 0.7)) 
                
                # ESC and Cleanup
                pyautogui.press('esc')
                time.sleep(0.05)
                pyautogui.press('backspace', presses=self.config.get("backspace_cleanup", 2))
                time.sleep(0.05)
                
                # Win32 Paste
                win32_paste()
                print("Done.")
            else:
                print("Empty result.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.processing = False

    # --- UI Logic ---
    def show_settings(self):
        root = tk.Tk()
        root.title("voysix Settings")
        root.geometry("300x250")
        root.attributes("-topmost", True)

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Whisper Model:").pack(pady=5)
        model_var = tk.StringVar(value=self.config["model_name"])
        model_cb = ttk.Combobox(main_frame, textvariable=model_var)
        model_cb['values'] = ('tiny', 'base', 'small', 'medium')
        model_cb.pack(pady=5)

        ttk.Label(main_frame, text="Paste Delay (sec):").pack(pady=5)
        delay_var = tk.DoubleVar(value=self.config["paste_delay"])
        ttk.Entry(main_frame, textvariable=delay_var).pack(pady=5)

        def save():
            self.config["model_name"] = model_var.get()
            self.config["paste_delay"] = delay_var.get()
            save_config(self.config)
            messagebox.showinfo("Success", "Settings saved. Please restart the app for model changes to take effect.")
            root.destroy()

        ttk.Button(main_frame, text="Save Settings", command=save).pack(pady=20)
        root.mainloop()

    def create_tray_icon(self):
        # Create a simple icon image
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), 'blue')
        dc = ImageDraw.Draw(image)
        dc.ellipse([width//4, height//4, width*3//4, height*3//4], fill='white')

        menu = (
            item('Settings', self.show_settings),
            item('Exit', self.exit_app),
        )
        self.tray_icon = pystray.Icon("voysix", image, "voysix (Active)", menu)
        self.tray_icon.run()

    def exit_app(self):
        self.stop_requested = True
        if self.tray_icon:
            self.tray_icon.stop()
        os._exit(0)

# --- Mouse Listener ---
def on_click(x, y, button, pressed):
    if button == mouse.Button.middle:
        if not pressed: # On Release
            if app.processing: return
            if not app.recording:
                app.start_recording()
            else:
                app.stop_recording()

if __name__ == "__main__":
    app = WhisperApp()

    # Start mouse listener in thread
    mouse_thread = threading.Thread(target=lambda: mouse.Listener(on_click=on_click).start())
    mouse_thread.daemon = True
    mouse_thread.start()

    print("Running in background with Tray Icon...")
    # Run tray icon in main thread
    app.create_tray_icon()
