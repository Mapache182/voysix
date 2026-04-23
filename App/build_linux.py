import os
import shutil
import subprocess
import sys

# --- CONFIGURATION ---
APP_NAME = "voysix"
VERSION = "1.0.0"
MAINTAINER = "Your Name <you@example.com>"
DESCRIPTION = "Powerful Speech-to-Text for your Desktop"
HOMEPAGE = "https://github.com/your-username/voysix"

def clean():
    print("Cleaning up...")
    for folder in ["build", "dist", f"{APP_NAME}-deb"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

def build_pyinstaller():
    print("Building binary with PyInstaller...")
    # Add hidden imports if necessary
    # sounddevice and others might need some care
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", APP_NAME,
        "--icon", "assets/icon.png",
        "--add-data", "assets:assets",
        "--add-data", "app/i18n/*.json:app/i18n",
        "--exclude-module", "coverage",
        "main.py"
    ]
    subprocess.run(cmd, check=True)

def create_deb_structure():
    print("Creating .deb structure...")
    deb_dir = f"{APP_NAME}-deb"
    os.makedirs(f"{deb_dir}/DEBIAN", exist_ok=True)
    os.makedirs(f"{deb_dir}/usr/bin", exist_ok=True)
    os.makedirs(f"{deb_dir}/usr/share/applications", exist_ok=True)
    os.makedirs(f"{deb_dir}/usr/share/icons/hicolor/256x256/apps", exist_ok=True)
    
    # Copy binary
    shutil.copy(f"dist/{APP_NAME}", f"{deb_dir}/usr/bin/{APP_NAME}")
    
    # Desktop file
    shutil.copy("assets/voysix.desktop", f"{deb_dir}/usr/share/applications/voysix.desktop")
    
    # Icon
    if os.path.exists("assets/icon.png"):
        shutil.copy("assets/icon.png", f"{deb_dir}/usr/share/icons/hicolor/256x256/apps/voysix.png")

    # Create control file
    control_content = f"""Package: {APP_NAME}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: {MAINTAINER}
Description: {DESCRIPTION}
 Depends: libportaudio2, libsndfile1, ffmpeg
Homepage: {HOMEPAGE}
"""
    with open(f"{deb_dir}/DEBIAN/control", "w") as f:
        f.write(control_content)

def build_deb():
    print("Building .deb package...")
    deb_dir = f"{APP_NAME}-deb"
    output_deb = f"{APP_NAME}_{VERSION}_amd64.deb"
    
    try:
        subprocess.run(["dpkg-deb", "--build", deb_dir, output_deb], check=True)
        print(f"Successfully built: {output_deb}")
    except FileNotFoundError:
        print("Error: 'dpkg-deb' not found. This part of the script MUST run on Linux.")
        print(f"The binary was still built and is available in dist/{APP_NAME}")

if __name__ == "__main__":
    if sys.platform != "linux":
        print("Warning: This script is designed to run on Linux to create a .deb package.")
        print("Running PyInstaller only...")
    
    clean()
    try:
        build_pyinstaller()
        if sys.platform == "linux":
            create_deb_structure()
            build_deb()
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)
