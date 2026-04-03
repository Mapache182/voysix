import os
import sys
import winreg

# App name used for the registry key. 
# We'll use 'voysix' as it's the current project name, 
# but also handle 'WhisperSTT' if it was set by an older installer.
APP_NAME = "Voysix"
LEGACY_APP_NAME = "WhisperSTT"

def set_autostart(enabled: bool):
    """
    Enable or disable autostart by updating the Registry.
    Location: HKCU\Software\Microsoft\Windows\CurrentVersion\Run
    """
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    # Determine the executable path
    if getattr(sys, 'frozen', False):
        # Running as a compiled .exe
        app_path = f'"{sys.executable}"'
    else:
        # Running from Python scripts
        # We use pythonw.exe to avoid console window
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        # App/app/autostart.py -> App/main.py
        current_dir = os.path.dirname(os.path.abspath(__file__))
        main_py = os.path.abspath(os.path.join(current_dir, "..", "main.py"))
        app_path = f'"{python_exe}" "{main_py}"'

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        
        # Always try to remove legacy key to avoid duplicates
        try:
            winreg.DeleteValue(key, LEGACY_APP_NAME)
        except FileNotFoundError:
            pass

        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, app_path)
            print(f"Set autostart registry key for: {APP_NAME} -> {app_path}")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                print(f"Removed autostart registry key for: {APP_NAME}")
            except FileNotFoundError:
                pass # Already gone
        
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Failed to update autostart registry: {e}")

def is_autostart_enabled() -> bool:
    """Check if the autostart value exists in the Registry."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        try:
            # Check for current name
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            try:
                # Check for legacy name
                winreg.QueryValueEx(key, LEGACY_APP_NAME)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
    except Exception:
        return False
