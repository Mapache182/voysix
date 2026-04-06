import os
import subprocess
import sys
import re

# Config
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(PROJECT_DIR, "version.txt")
SETUP_FILE = os.path.join(PROJECT_DIR, "setup.py")
ISS_FILE = os.path.join(PROJECT_DIR, "installer", "installer.iss")

# Use current python executable
VENV_PYTHON = sys.executable
MAIN_FILE = os.path.join(PROJECT_DIR, "main.py")
ISCC_PATH = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

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

def update_iss_file(version):
    with open(ISS_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = re.sub(r'AppVersion=[^\n]+', f'AppVersion={version}', content)
    # Also update OutputBaseFilename to include version? Optionally
    # new_content = re.sub(r'OutputBaseFilename=[^\n]+', f'OutputBaseFilename=voysix_Setup_{version.replace(".", "_")}', new_content)
    with open(ISS_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

def run_build():
    print("--- 1. Building with cx_Freeze ---")
    # Using python directly to avoid shell issues
    subprocess.run([VENV_PYTHON, SETUP_FILE, "build"], check=True, cwd=PROJECT_DIR)
    
    print("--- 2. Compiling Inno Setup Installer ---")
    subprocess.run([ISCC_PATH, "installer/installer.iss"], check=True, cwd=PROJECT_DIR)

if __name__ == "__main__":
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
        update_iss_file(new_version)
        update_main_py(new_version)
        
        run_build()
        
        print("\n\n" + "="*40)
        print(f"SUCCESS! Version {new_version} built.")
        print(f"Installer is available at: {os.path.join(PROJECT_DIR, 'dist', 'Voysix_Setup.exe')}")
        print("="*40)
        
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)
