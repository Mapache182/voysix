import os
import sys
try:
    import winreg
except ImportError:
    winreg = None

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
    # --- macOS Implementation ---
    if sys.platform == "darwin":
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.voysix.app.plist")
        if enabled:
            # Determine the executable path for macOS
            if getattr(sys, 'frozen', False):
                # In .app bundle, sys.executable points to the binary inside MacOS/
                app_path = sys.executable
            else:
                app_path = sys.executable # python interpreter
                # We'd need more logic for script mode, but usually it's for frozen apps

            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voysix.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>{app_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>"""
            try:
                os.makedirs(os.path.dirname(plist_path), exist_ok=True)
                with open(plist_path, "w") as f:
                    f.write(plist_content)
                print(f"Created macOS LaunchAgent at: {plist_path}")
            except Exception as e:
                print(f"Failed to create macOS LaunchAgent: {e}")
        else:
            if os.path.exists(plist_path):
                try:
                    os.remove(plist_path)
                    print(f"Removed macOS LaunchAgent at: {plist_path}")
                except Exception as e:
                    print(f"Failed to remove macOS LaunchAgent: {e}")
        return

    # --- Windows Implementation ---
    if winreg is None:
        return

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
        except (FileNotFoundError, Exception):
            pass

        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, app_path)
            print(f"Set autostart registry key for: {APP_NAME} -> {app_path}")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                print(f"Removed autostart registry key for: {APP_NAME}")
            except (FileNotFoundError, Exception):
                pass # Already gone
        
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Failed to update autostart registry: {e}")

def is_autostart_enabled() -> bool:
    """Check if the autostart value exists in the Registry."""
    if sys.platform == "darwin":
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.voysix.app.plist")
        return os.path.exists(plist_path)

    if winreg is None:
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        try:
            # Check for current name
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, Exception):
            try:
                # Check for legacy name
                winreg.QueryValueEx(key, LEGACY_APP_NAME)
                winreg.CloseKey(key)
                return True
            except (FileNotFoundError, Exception):
                winreg.CloseKey(key)
                return False
    except Exception:
        return False
