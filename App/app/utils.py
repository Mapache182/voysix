import ctypes
import time
import pyperclip
import pyautogui
import os
import sys

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for cx_Freeze """
    if getattr(sys, 'frozen', False):
        if sys.platform == "darwin":
            # On macOS, if frozen, resources are usually in ../Resources or same dir as binary
            # depending on how cx_Freeze was configured. 
            # In bdist_mac, it's often in Contents/Resources
            base_dir = os.path.dirname(sys.executable)
            # If we are inside MacOS/ subdirectory of the bundle
            if "Contents/MacOS" in base_dir:
                base_dir = os.path.abspath(os.path.join(base_dir, "..", "Resources"))
        else:
            base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_dir, relative_path)


try:
    user32 = ctypes.windll.user32
    VK_CONTROL = 0x11
    VK_V = 0x56
    VK_MEDIA_PLAY_PAUSE = 0xB3
    KEYEVENTF_KEYUP = 0x0002
    HAS_WIN32 = True
except AttributeError:
    HAS_WIN32 = False

def toggle_media_playback():
    """Toggle system media playback (Pause/Play)."""
    if HAS_WIN32:
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 103'], capture_output=True) # Usually Play/Pause
    else:
        pass

def native_paste():
    """Platform-specific keyboard paste."""
    if HAS_WIN32:
        # Lowest-level Windows API keyboard simulation
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    elif sys.platform == "darwin":
        pyautogui.hotkey('command', 'v')
    else:
        # Linux fallback
        pyautogui.hotkey('ctrl', 'v')

def output_transcription(text, mode="type", delay=0.7, cleanup=0, add_space=False, add_newline=False):
    if not text:
        return

    # Prepend space or newline if requested
    prefix = ""
    if add_newline:
        prefix += "\n"
    if add_space:
        prefix += " "
    
    text = prefix + text

    if mode == "console":
        print(f"Transcription: {text}")
    
    elif mode == "clipboard":
        pyperclip.copy(text)
        print("Copied to clipboard.")

    elif mode == "type":
        pyperclip.copy(text)
        # Give OS time to settle and focus app
        if delay > 0:
            print(f"DEBUG: Waiting {delay}s for system focus before pasting...")
            time.sleep(delay)
        
        # Cleanup potential junk (like a middle-click menu if any)
        if cleanup > 0:
            print(f"DEBUG: Cleaning up {cleanup} backspaces...")
            pyautogui.press('backspace', presses=cleanup)
            time.sleep(0.1)
            
        t_paste_start = time.time()
        native_paste()
        t_paste_dur = time.time() - t_paste_start
        print(f"Text pasted in {t_paste_dur:.3f}s: {text[:20]}...")

def apply_replacements(text, replacements_str):
    if not text or not replacements_str:
        return text
    
    import re
    lines = replacements_str.split('\n')
    for line in lines:
        if ':' in line:
            try:
                find, replace = line.split(':', 1)
                find = find.strip()
                replace = replace.strip()
                if find:
                    # Use regex with word boundaries for better accuracy
                    pattern = re.compile(rf'\b{re.escape(find)}\b', re.IGNORECASE)
                    text = pattern.sub(replace, text)
            except:
                continue
    return text

def apply_smart_normalization(text):
    if not text:
        return text
    
    import re
    # 1. Fix spacing around punctuation if model messed up
    text = re.sub(r'\s+([,.!?])', r'\1', text)
    
    # 2. Capitalize sentences
    def capitalize(match):
        return match.group(1) + match.group(2).upper()
    text = re.sub(r'(^|[.!?]\s+)([a-zа-я])', capitalize, text)

    return text
