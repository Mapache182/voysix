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
        check_cmd = "where" if sys.platform == "win32" else "which"
        subprocess.run([check_cmd, "tailscale"], capture_output=True, check=True, shell=(sys.platform == "win32"))
        return True
    except:
        return False

class TailscaleDownloadWorker(QThread):
    progress = Signal(int, int) # downloaded, total
    finished = Signal(bool, str) # success, msg

    def run(self):
        if sys.platform == "darwin":
            # On macOS, we don't download MSI. We point to the App Store or official DMG.
            import webbrowser
            webbrowser.open("https://tailscale.com/download/mac")
            self.finished.emit(True, "Opened Tailscale download page. Please install Tailscale and sign in.")
            return

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
            
            # --- Installation (Windows) ---
            import ctypes
            res = ctypes.windll.shell32.ShellExecuteW(None, "runas", "msiexec.exe", f'/i "{tmp_path}"', None, 1)
            
            if res <= 32:
                subprocess.run(["msiexec.exe", "/i", tmp_path], check=True)

            time.sleep(5) 
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
            if sys.platform == "win32":
                reply = QMessageBox.warning(
                    self, 
                    tr("ts_reboot_required"), 
                    tr("ts_reboot_msg") + "\n\n" + tr("ts_restart_now"),
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    os.system("shutdown /r /t 0")
            else:
                QMessageBox.information(self, "Tailscale", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Download Error", f"Failed to download Tailscale:\n{msg}")
            self.reject()
