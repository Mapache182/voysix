import os
import sys
import tempfile
import zipfile
import requests
import time
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox
from PySide6.QtCore import QThread, Signal
from app.i18n import tr

# URL for downloading CUDA DLLs. For demonstration purposes, we're using a 100MB mock file.
# In a real scenario, this would point to a ZIP containing cublas64_*.dll and cudnn*.dll
GPU_DLLS_URL = "https://speed.hetzner.de/100MB.bin" 

def check_hardware_for_nvidia():
    """Returns True if the system has an NVIDIA GPU."""
    if sys.platform == 'win32':
        try:
            import subprocess
            # CREATE_NO_WINDOW = 0x08000000 to avoid popping a terminal
            CREATE_NO_WINDOW = 0x08000000
            output = subprocess.check_output(
                "wmic path win32_VideoController get name", 
                text=True, 
                creationflags=CREATE_NO_WINDOW
            )
            return "nvidia" in output.lower()
        except Exception as e:
            print(f"Warning: Could not check for NVIDIA GPU: {e}")
            return False
    elif sys.platform == 'darwin':
        # On macOS, we generally look for Apple Silicon (M1/M2/M3) which has integrated GPU
        # or discrete AMD/NVIDIA on older Intel Macs. 
        # But for Whisper, we mostly care about MPS support.
        return False # This function is specifically for NVIDIA/CUDA discovery
    return False

def check_gpu_available():
    """Check if we have GPU capabilities dynamically (CUDA or MPS)"""
    try:
        import torch
        if torch.cuda.is_available():
            return True
        if sys.platform == "darwin":
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return True
    except:
        pass
        
    # If in frozen exe on Windows, check if DLLs exist
    if sys.platform == "win32" and getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        lib_dir = os.path.join(base_dir, 'lib')
        dl_target_11 = os.path.join(lib_dir, 'cublas64_11.dll')
        dl_target_12 = os.path.join(lib_dir, 'cublas64_12.dll')
        # Also check for mock completion file
        mock_done = os.path.join(lib_dir, 'gpu_downloaded.marker')
        if os.path.exists(dl_target_11) or os.path.exists(dl_target_12) or os.path.exists(mock_done):
            return True
            
    return False

class DownloadWorker(QThread):
    progress = Signal(int, int) # downloaded, total
    finished = Signal(bool, str) # success, msg

    def run(self):
        try:
            url = GPU_DLLS_URL
            # Setting stream=True to get content chunks
            response = requests.get(url, stream=True, timeout=10)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 104857600)) # Default 100MB fallback
            
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.tmp')
            os.close(tmp_fd)
            
            downloaded = 0
            last_emit_time = 0
            
            with open(tmp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192*4):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Throttle UI updates to 10 FPS
                        current_time = time.time()
                        if current_time - last_emit_time > 0.1:
                            self.progress.emit(downloaded, total_size)
                            last_emit_time = current_time
                            
            self.progress.emit(total_size, total_size) # 100%
            
            # --- Emulate extraction phase ---
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(__file__))
            lib_dir = os.path.join(base_dir, 'lib')
            os.makedirs(lib_dir, exist_ok=True)
            
            # If it's a real zip, extract it:
            if url.endswith('.zip'):
                with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                    zip_ref.extractall(lib_dir)
            else:
                # Mock extraction for our dummy .bin file
                time.sleep(1) # Pretend extracting
                with open(os.path.join(lib_dir, 'gpu_downloaded.marker'), 'w') as mf:
                    mf.write("done")
                
            os.remove(tmp_path)
            self.finished.emit(True, "GPU Libraries successfully installed! Please restart the application.")
        except Exception as e:
            self.finished.emit(False, str(e))

class GPUDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading GPU Libraries")
        self.setFixedSize(400, 120)
        
        layout = QVBoxLayout(self)
        self.label = QLabel("Downloading NVIDIA CUDA Libraries...\nPlease wait, it may take a few minutes depending on your speed.", self)
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.worker = DownloadWorker()
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_finished)
        
        # Prevent closing by user easily
        self.setWindowFlags(self.windowFlags() & ~str(self.windowFlags().__class__.WindowCloseButtonHint)) 
        
    def start_download(self):
        self.worker.start()
        
    def update_progress(self, downloaded, total):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.label.setText(f"Downloading NVIDIA CUDA Libraries...\n{mb_downloaded:.1f} MB / {mb_total:.1f} MB ({pct}%)")
        else:
            self.progress_bar.setMaximum(0) # Indeterminate mode
            mb_downloaded = downloaded / (1024 * 1024)
            self.label.setText(f"Downloading NVIDIA CUDA Libraries...\n{mb_downloaded:.1f} MB downloaded...")
            
    def on_finished(self, success, msg):
        if success:
            QMessageBox.information(self, "Success", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Download Error", f"Failed to download GPU libraries:\n{msg}")
            self.reject()
