import os
import sys
import tempfile
import zipfile
import subprocess
import requests
import time
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox
from PySide6.QtCore import QThread, Signal
from app.i18n import tr

# Latest stable windows MSI (AMD64)
TAILSCALE_MSI_URL = "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi"


def is_tailscale_present():
    """Checks if tailscale.exe is found by the worker client."""
    from app.worker_client import WorkerClient
    client = WorkerClient()
    cmd = client._get_tailscale_cmd()
    
    # If _get_tailscale_cmd returned a full path that exists, it's present.
    # If it returned just "tailscale", check if it's actually in PATH.
    if os.path.isabs(cmd):
        return os.path.exists(cmd)
    
    # Check PATH
    import subprocess
    try:
        subprocess.run(["where", "tailscale"], capture_output=True, check=True, shell=True)
        return True
    except:
        return False

class TailscaleDownloadWorker(QThread):
    progress = Signal(int, int) # downloaded, total
    finished = Signal(bool, str) # success, msg

    def run(self):
        try:
            url = TAILSCALE_MSI_URL
            response = requests.get(url, stream=True, timeout=15)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 25000000)) # Approx 25MB
            
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.msi')
            os.close(tmp_fd)
            
            downloaded = 0
            last_emit_time = 0
            
            with open(tmp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        current_time = time.time()
                        if current_time - last_emit_time > 0.1:
                            self.progress.emit(downloaded, total_size)
                            last_emit_time = current_time
                            
            self.progress.emit(total_size, total_size)
            
            # --- Installation ---
            # Removing /qn (silent) so the user can see the progress bar and success message.
            # /passive shows progress but doesn't require user input for most parts.
            # Or just remove flags for full interactive installer.
            import ctypes
            # 32 = SUCCESS (anything > 32 is success for ShellExecute)
            # Using "open" verb for standard installer UI.
            res = ctypes.windll.shell32.ShellExecuteW(None, "runas", "msiexec.exe", f'/i "{tmp_path}"', None, 1)
            
            if res <= 32:
                # Fallback to subprocess if shell32 failed or was cancelled
                subprocess.run(["msiexec.exe", "/i", tmp_path], check=True)

            
            # We don't really know when msiexec finishes since it runs in background by default.
            # But we can wait a few seconds or check if the service appears.
            time.sleep(5) 
            
            # Cleanup temp file is tricky because msiexec might still be reading it.
            # We'll try to delete it after a delay in a separate thread or just leave it to OS temp cleanup.
            # os.remove(tmp_path) 
            
            self.finished.emit(True, "Tailscale installation started! It will finish in the background. Please wait a minute before testing connection again.")
        except Exception as e:
            self.finished.emit(False, str(e))


class TailscaleDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Tailscale")
        self.setFixedSize(400, 120)
        
        layout = QVBoxLayout(self)
        self.label = QLabel("Downloading Tailscale components for remote worker discovery...", self)
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.worker = TailscaleDownloadWorker()
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_finished)
        
    def start_download(self):
        self.worker.start()
        
    def update_progress(self, downloaded, total):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.label.setText(f"Downloading Tailscale... {mb_downloaded:.1f} MB / {mb_total:.1f} MB ({pct}%)")
        else:
            self.progress_bar.setMaximum(0)
            mb_downloaded = downloaded / (1024 * 1024)
            self.label.setText(f"Downloading Tailscale... {mb_downloaded:.1f} MB downloaded...")
            
    def on_finished(self, success, msg):
        if success:
            reply = QMessageBox.warning(
                self, 
                tr("ts_reboot_required"), 
                tr("ts_reboot_msg") + "\n\n" + tr("ts_restart_now"),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                import os
                os.system("shutdown /r /t 0")
            self.accept()
        else:
            QMessageBox.critical(self, "Download Error", f"Failed to download Tailscale:\n{msg}")
            self.reject()
