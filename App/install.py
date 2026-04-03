import os
import winshell
from win32com.client import Dispatch

# --- Constants ---
PROJECT_DIR = r"d:\Project\voysix\App"
ROOT_DIR = r"d:\Project\voysix"
VENV_PYTHONW = os.path.join(ROOT_DIR, r"venv\Scripts\pythonw.exe")
SCRIPT_PATH = os.path.join(PROJECT_DIR, "whisper_transcription.py")
VBS_PATH = os.path.join(PROJECT_DIR, "record_whisper.vbs")

def create_vbs_launcher():
    vbs_content = f'''Set WinScriptHost = CreateObject("WScript.Shell")
WinScriptHost.Run "{VENV_PYTHONW} {SCRIPT_PATH}", 0
Set WinScriptHost = Nothing
'''
    with open(VBS_PATH, "w") as f:
        f.write(vbs_content)
    print(f"VBS Launcher created at: {VBS_PATH}")

def create_startup_shortcut():
    startup_path = winshell.startup()
    shortcut_path = os.path.join(startup_path, "voysix.lnk")
    
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = VBS_PATH
    shortcut.WorkingDirectory = PROJECT_DIR
    shortcut.Description = "voysix Real-time Voice Transcription"
    shortcut.IconLocation = "pythonw.exe"
    shortcut.save()
    
    print(f"Startup shortcut created at: {shortcut_path}")

if __name__ == "__main__":
    print("--- voysix Installer ---")
    create_vbs_launcher()
    create_startup_shortcut()
    print("\nInstallation COMPLETE!")
    print("The program will now start automatically when Windows boots.")
    print("You can find the blue tray icon in the taskbar.")
