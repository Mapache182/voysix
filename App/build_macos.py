import os
import subprocess
import sys
import re

# Config
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(PROJECT_DIR, "version.txt")
SETUP_FILE = os.path.join(PROJECT_DIR, "setup.py")

# Use current python executable
VENV_PYTHON = sys.executable
MAIN_FILE = os.path.join(PROJECT_DIR, "main.py")

def get_current_version():
    with open(VERSION_FILE, "r") as f:
        return f.read().strip()

def save_version(version):
    with open(VERSION_FILE, "w") as f:
        f.write(version)

def increment_patch(version):
    parts = version.split('.')
    if len(parts) >= 3:
        parts[-1] = str(int(parts[-1]) + 1)
    else:
        parts.append("1")
    return '.'.join(parts)

def update_setup_py(version):
    with open(SETUP_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(r'version="[^"]+"', f'version="{version}"', content)
    with open(SETUP_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

def update_main_py(version):
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(r'self\.version = "[^"]+"', f'self.version = "{version}"', content)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

def run_build():
    print("--- 1. Building with cx_Freeze (bdist_mac) ---")
    # Using python directly
    subprocess.run([VENV_PYTHON, SETUP_FILE, "bdist_mac"], check=True, cwd=PROJECT_DIR)
    
    print("--- 2. Creating DMG (optional) ---")
    # Note: On macOS, one would usually use dmgbuild or hdiutil here.
    # For now, we just inform that .app is ready in dist/
    dist_dir = os.path.join(PROJECT_DIR, "dist")
    print(f"Build finished. Check {dist_dir} for Voysix.app")

if __name__ == "__main__":
    if sys.platform != "darwin":
        print("Error: This script must be run on macOS.")
        sys.exit(1)

    try:
        if len(sys.argv) > 1:
            new_version = sys.argv[1]
            print(f"Building version from argument: {new_version}")
        else:
            current = get_current_version()
            new_version = increment_patch(current)
            print(f"Updating version: {current} -> {new_version}")
        
        save_version(new_version)
        update_setup_py(new_version)
        update_main_py(new_version)
        
        run_build()
        
        print("\n\n" + "="*40)
        print(f"SUCCESS! macOS Version {new_version} built.")
        print("="*40)
        
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)
