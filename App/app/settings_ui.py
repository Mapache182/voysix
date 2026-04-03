from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QPushButton, QDoubleSpinBox, QFormLayout, QSlider, QSpinBox, QLineEdit, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QKeyEvent, QMouseEvent, QIcon
import os
import time
import threading
import sounddevice as sd

from app.settings import load_config, save_config
from app.utils import get_resource_path
from app.volume import get_mic_volume, set_mic_volume
from app.i18n import tr, hlp, set_ui_lang
from app.autostart import set_autostart, is_autostart_enabled
from app.gpu_manager import check_gpu_available, GPUDownloadDialog, check_hardware_for_nvidia

class ConnectionTester(QThread):
    ts_signal = Signal(bool, str) # connected, state_text
    worker_signal = Signal(bool, str, str) # online, message, color

    def __init__(self, node, api_key, manual_url, ts_key):
        super().__init__()
        self.node = node
        self.api_key = api_key
        self.manual_url = manual_url
        self.ts_key = ts_key

    def run(self):
        import sys
        print(f"\nDEBUG: ConnectionTester.run() - sys.path[0]={sys.path[0]}")
        try:
            import app.worker_client
            print(f"DEBUG: app.worker_client found at: {app.worker_client.__file__}")
        except Exception as e:
            print(f"DEBUG: Pre-import of worker_client failed: {e}")

        from app.worker_client import WorkerClient
        client = WorkerClient(self.node, api_key=self.api_key, manual_url=self.manual_url)
        
        # 1. Check Tailscale (and optionally try to 'up')
        ts = client.get_tailscale_status(auth_key=self.ts_key)
        self.ts_signal.emit(ts["connected"], ts["state"])

        # 2. Check Worker
        url = client.discover()
        if url:
            if client.check_health():
                info = client.get_info()
                model = "???"
                if info:
                    model = info.get("config", {}).get("model", "???")
                self.worker_signal.emit(True, f"{tr('status_online')} [Model: {model}]", "green")
            else:
                self.worker_signal.emit(False, f"{tr('status_error')} (Check API Key)", "red")
        else:
            self.worker_signal.emit(False, tr("status_offline"), "red")

class HotkeyLineEdit(QLineEdit):
    def __init__(self, current_hotkey, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setText(current_hotkey)
        self.setPlaceholderText(tr("press_any_key"))
        # Using a slightly darker background with black text for maximum contrast
        self.setStyleSheet("""
            QLineEdit {
                background-color: #e0e0e0;
                color: black;
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 2px;
            }
            QLineEdit::placeholder {
                color: #555555;
            }
        """)
        self.recording = False

    def mousePressEvent(self, event: QMouseEvent):
        if not self.recording:
            self.recording = True
            self.setText(f"<{tr('press_any_key')}>")
            self.setFocus()
        else:
            if event.button() == Qt.MiddleButton:
                self.set_hotkey("middle_click")
            elif event.button() == Qt.RightButton:
                self.set_hotkey("right_click")
            elif event.button() == Qt.LeftButton:
                self.set_hotkey("left_click")

    def keyPressEvent(self, event: QKeyEvent):
        if self.recording:
            key = event.key()
            if key == Qt.Key_Escape:
                self.recording = False
                self.setText(self.text()) # Restore or leave as is
                return
            
            # Simple mapping for pynput compatibility
            text = event.text().lower()
            if not text or key >= Qt.Key_F1 and key <= Qt.Key_F12:
                # Meta keys
                meta_map = {
                    Qt.Key_F1: "f1", Qt.Key_F2: "f2", Qt.Key_F3: "f3", Qt.Key_F4: "f4",
                    Qt.Key_F5: "f5", Qt.Key_F6: "f6", Qt.Key_F7: "f7", Qt.Key_F8: "f8",
                    Qt.Key_F9: "f9", Qt.Key_F10: "f10", Qt.Key_F11: "f11", Qt.Key_F12: "f12",
                    Qt.Key_Alt: "alt", Qt.Key_Control: "ctrl", Qt.Key_Shift: "shift",
                    Qt.Key_CapsLock: "caps_lock", Qt.Key_Space: "space", Qt.Key_Tab: "tab"
                }
                k_str = meta_map.get(key, text)
            else:
                k_str = text
            
            if k_str:
                self.set_hotkey(k_str)

    def set_hotkey(self, hotkey_str):
        self.setText(hotkey_str)
        self.recording = False
        self.clearFocus()

class SettingsDialog(QDialog):
    opacity_preview = Signal(float)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_config()
        self.original_opacity = self.config.get("opacity", 0.9)
        set_ui_lang(self.config.get("ui_language", "en"))
        
        self.setWindowTitle(tr("settings"))
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(350, 450)
        
        self.help_text = {
            "model": "<b>Whisper Model:</b><br>'tiny' is fastest, 'large' is most accurate. 'base' is recommended for most users.",
            "mic": "<b>Microphone:</b><br>Select the audio device to record from. 'Default' follows your Windows settings.",
            "lang": "<b>Language:</b><br>Forcing a language (e.g., Russian) improves accuracy and reduces translation errors.",
            "mode": "<b>Output Mode:</b><br>'type' pastes text automatically. 'clipboard' just copies it. 'console' only shows logs.",
            "delay": "<b>Paste Delay:</b><br>Wait time (seconds) before pasting. Increase if text pastes into the wrong window.",
            "autostart": "<b>Autostart:</b><br>Automatically launch voysix when you log into Windows.",
            "opacity": "<b>UI Opacity:</b><br>Changes how transparent the floating 'Ready' window is.",
            "mic_vol": "<b>Mic Volume:</b><br>Synchronized with Windows System Microphone volume. Use this if your voice is too quiet.",
            "beam": "<b>Beam Size:</b><br>Higher values (e.g., 5-10) explore more phrase variants. Improving grammar but slowing down processing.",
            "temp": "<b>Temperature:</b><br>0.0 is strict and stable. Higher values add 'creativity' but might cause hallucinations.",
            "prompt": "<b>Initial Prompt:</b><br>Provide context or common words (like names or tech terms) to guide the AI's vocabulary.",
            "ts_authkey": "<b>Tailscale Auth Key:</b><br>Use this to automatically join the Tailscale network. Create it in the Tailscale admin console."
        }
        
        layout = QVBoxLayout(self)
        self.form = QFormLayout()
        
        # Helper to add row with info button
        def add_info_row(label_key, widget, help_key):
            row_layout = QHBoxLayout()
            row_layout.addWidget(widget)
            
            info_btn = QPushButton("ⓘ")
            info_btn.setFixedSize(20, 20)
            info_btn.setStyleSheet("""
                QPushButton { 
                    border: none; color: #0078d4; font-weight: bold; background: transparent; font-size: 14px;
                }
                QPushButton:hover { color: #005a9e; }
            """)
            info_btn.clicked.connect(lambda: QMessageBox.information(self, tr("info_title"), hlp(help_key)))
            row_layout.addWidget(info_btn)
            
            self.form.addRow(tr(label_key), row_layout)

        self.model_cb = QComboBox()
        self.model_cb.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_cb.setCurrentText(self.config["model_name"])
        add_info_row("model", self.model_cb, "model")

        # Engine selection
        self.engine_cb = QComboBox()
        self.engine_cb.addItem("OpenAI Whisper", "openai-whisper")
        self.engine_cb.addItem("Faster Whisper", "faster-whisper")
        idx = self.engine_cb.findData(self.config.get("engine", "openai-whisper"))
        self.engine_cb.setCurrentIndex(idx if idx >= 0 else 0)
        add_info_row("engine", self.engine_cb, "engine")
        
        # GPU Checkbox
        self.use_gpu_chk = QCheckBox(tr("enabled"))
        self.use_gpu_chk.setChecked(self.config.get("use_gpu", False))
        self.use_gpu_chk.stateChanged.connect(self._on_use_gpu_toggled)
        self.form.addRow("Use GPU (NVIDIA)", self.use_gpu_chk)
        
        # Mic Selection
        self.mic_cb = QComboBox()
        self.mic_cb.addItem(tr("default_mic"), None)
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                self.mic_cb.addItem(f"{i}: {dev['name']}", i)
        
        if self.config["selected_mic"] is None:
            self.mic_cb.setCurrentIndex(0)
        else:
            idx = self.mic_cb.findData(self.config["selected_mic"])
            self.mic_cb.setCurrentIndex(idx if idx >= 0 else 0)
        add_info_row("microphone", self.mic_cb, "mic")
        
        # Transcription Language Selection
        self.lang_cb = QComboBox()
        langs = {"auto": "Auto Detect", "en": "English", "ru": "Russian", "de": "German", "fr": "French", "es": "Spanish"}
        for code, name in langs.items():
            self.lang_cb.addItem(name, code)
        self.lang_cb.setCurrentIndex(max(0, self.lang_cb.findData(self.config.get("language", "auto"))))
        add_info_row("language", self.lang_cb, "lang")

        # Interface Language Selection
        self.ui_lang_cb = QComboBox()
        ui_langs = {"en": "English", "ru": "Русский", "es": "Español"}
        for code, name in ui_langs.items():
            self.ui_lang_cb.addItem(name, code)
        self.ui_lang_cb.setCurrentIndex(max(0, self.ui_lang_cb.findData(self.config.get("ui_language", "en"))))
        add_info_row("ui_lang", self.ui_lang_cb, "ui_lang")
        
        # Output Mode
        self.output_cb = QComboBox()
        self.output_cb.addItems(["type", "clipboard", "console"])
        self.output_cb.setCurrentText(self.config["output_mode"])
        add_info_row("output_mode", self.output_cb, "mode")
        
        # Paste Delay
        self.delay_sb = QDoubleSpinBox()
        self.delay_sb.setRange(0.1, 5.0)
        self.delay_sb.setValue(self.config["paste_delay"])
        add_info_row("paste_delay", self.delay_sb, "delay")
        
        # Always on top
        self.always_on_top_chk = QCheckBox(tr("enabled"))
        self.always_on_top_chk.setChecked(self.config.get("always_on_top", True))
        add_info_row("always_on_top", self.always_on_top_chk, "always_on_top")
        
        # UI Design
        self.design_cb = QComboBox()
        self.design_cb.addItem(tr("design_classic"), "classic")
        self.design_cb.addItem(tr("design_waveform"), "waveform")
        self.design_cb.setCurrentIndex(max(0, self.design_cb.findData(self.config.get("ui_design", "classic"))))
        add_info_row("ui_design", self.design_cb, "ui_design")

        # Autostart
        self.autostart_chk = QCheckBox(tr("enabled"))
        actual_autostart = is_autostart_enabled()
        self.autostart_chk.setChecked(actual_autostart)
        # Ensure config is in sync with reality
        self.config["autostart"] = actual_autostart
        add_info_row("autostart", self.autostart_chk, "autostart")
        
        # Opacity
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.original_opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        add_info_row("ui_opacity", self.opacity_slider, "opacity")
        

        
        # Mic Volume
        self.mic_vol_slider = QSlider(Qt.Horizontal)
        self.mic_vol_slider.setRange(0, 100)
        self.mic_vol_slider.setValue(get_mic_volume())
        self.mic_vol_slider.valueChanged.connect(self._on_mic_vol_changed)
        add_info_row("mic_volume", self.mic_vol_slider, "mic_vol")

        # Add Space
        self.add_space_chk = QCheckBox(tr("enabled"))
        self.add_space_chk.setChecked(self.config.get("add_space", False))
        add_info_row("add_space", self.add_space_chk, "add_space")

        # Add Newline
        self.add_newline_chk = QCheckBox(tr("enabled"))
        self.add_newline_chk.setChecked(self.config.get("add_newline", False))
        add_info_row("add_newline", self.add_newline_chk, "add_newline")
        
        # Pause Media
        self.pause_media_chk = QCheckBox(tr("enabled"))
        self.pause_media_chk.setChecked(self.config.get("pause_media_on_record", False))
        add_info_row("pause_media", self.pause_media_chk, "pause_media")

        # Start timer to sync system volume to slider (polling)
        self.vol_timer = QTimer(self)
        self.vol_timer.timeout.connect(self._sync_volume_from_system)
        self.vol_timer.start(500) # Check every 0.5s

        # Hotkey
        self.hotkey_le = HotkeyLineEdit(self.config.get("hotkey", "middle_click"))
        add_info_row("hotkey", self.hotkey_le, "hotkey")
        
        self.form.addRow(QLabel(f"<br><b>{tr('advanced_tuning')}</b>"), QLabel(""))
        
        # Beam Size
        self.beam_size_sb = QSpinBox()
        self.beam_size_sb.setRange(1, 10)
        self.beam_size_sb.setValue(self.config.get("beam_size", 5))
        add_info_row("beam_size", self.beam_size_sb, "beam")
        
        # Temperature
        self.temp_sb = QDoubleSpinBox()
        self.temp_sb.setRange(0.0, 1.0)
        self.temp_sb.setSingleStep(0.1)
        self.temp_sb.setValue(self.config.get("temperature", 0.0))
        add_info_row("temperature", self.temp_sb, "temp")
        
        # Backspace Cleanup
        self.cleanup_sb = QSpinBox()
        self.cleanup_sb.setRange(0, 10)
        self.cleanup_sb.setValue(self.config.get("backspace_cleanup", 0))
        add_info_row("backspace_cleanup", self.cleanup_sb, "backspace_cleanup")

        # Unload model when idle
        self.unload_idle_chk = QCheckBox(tr("enabled"))
        self.unload_idle_chk.setChecked(self.config.get("unload_idle", True))
        add_info_row("unload_idle", self.unload_idle_chk, "unload_idle")

        # Idle time
        self.idle_time_sb = QSpinBox()
        self.idle_time_sb.setRange(1, 60)
        self.idle_time_sb.setValue(self.config.get("idle_time_minutes", 5))
        add_info_row("idle_time", self.idle_time_sb, "idle_time")

        # Pre-recording
        self.pre_record_sb = QDoubleSpinBox()
        self.pre_record_sb.setRange(0.0, 5.0)
        self.pre_record_sb.setSingleStep(0.5)
        self.pre_record_sb.setValue(self.config.get("pre_record_seconds", 0.0))
        add_info_row("pre_record", self.pre_record_sb, "pre_record")
        
        # Initial Prompt
        self.prompt_le = QLineEdit()
        self.prompt_le.setText(self.config.get("initial_prompt", ""))
        self.prompt_le.setPlaceholderText("Enter context/vocabulary...")
        add_info_row("initial_prompt", self.prompt_le, "prompt")
        
        # --- Remote Worker Section ---
        self.form.addRow(QLabel(f"<br><b>{tr('remote_worker')}</b>"), QLabel(""))
        
        self.remote_mode_chk = QCheckBox(tr("enabled"))
        self.remote_mode_chk.setChecked(self.config.get("remote_mode", False))
        add_info_row("remote_worker", self.remote_mode_chk, "remote_worker")
        
        self.remote_node_le = QLineEdit()
        self.remote_node_le.setText(self.config.get("remote_worker_name", ""))
        self.remote_node_le.setPlaceholderText("tailscale-node-name")
        add_info_row("remote_node", self.remote_node_le, "remote_node")

        self.remote_key_le = QLineEdit()
        self.remote_key_le.setEchoMode(QLineEdit.Password)
        self.remote_key_le.setText(self.config.get("remote_api_key", ""))
        add_info_row("worker_api_key", self.remote_key_le, "remote_api_key")

        self.manual_url_le = QLineEdit()
        self.manual_url_le.setText(self.config.get("remote_worker_url", ""))
        self.manual_url_le.setPlaceholderText("http://100.x.y.z:8000")
        add_info_row("manual_url", self.manual_url_le, "manual_url_help")

        self.ts_key_le = QLineEdit()
        self.ts_key_le.setEchoMode(QLineEdit.Password)
        self.ts_key_le.setText(self.config.get("tailscale_auth_key", ""))
        self.ts_key_le.setPlaceholderText("tskey-auth-...")
        add_info_row("ts_authkey", self.ts_key_le, "ts_authkey")
        
        self.test_worker_btn = QPushButton(tr("test_connection"))
        self.test_worker_btn.clicked.connect(self._test_worker)
        self.worker_status_lbl = QLabel(tr("status_offline"))
        self.worker_status_lbl.setStyleSheet("color: gray;")
        
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.test_worker_btn)
        status_layout.addWidget(self.worker_status_lbl)
        self.form.addRow(tr("worker_status"), status_layout)

        # 🔹 Tailscale Status Label & Fix Button
        self.ts_status_lbl = QLabel("---")
        self.ts_status_lbl.setStyleSheet("color: gray;")
        
        self.ts_fix_btn = QPushButton(tr("ts_fix_btn"))
        self.ts_fix_btn.setToolTip(tr("ts_fix_msg"))
        self.ts_fix_btn.setFixedWidth(80)
        self.ts_fix_btn.setVisible(False)
        self.ts_fix_btn.clicked.connect(self._fix_tailscale)
        
        ts_status_layout = QHBoxLayout()
        ts_status_layout.addWidget(self.ts_status_lbl)
        ts_status_layout.addWidget(self.ts_fix_btn)
        ts_status_layout.addStretch()
        
        self.form.addRow(tr("ts_status"), ts_status_layout)
        
        layout.addLayout(self.form)
        
        self.tester = None

        buttons = QHBoxLayout()
        save_btn = QPushButton(tr("save"))
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(self.cancel)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _on_opacity_slider_changed(self, value):
        self.opacity_preview.emit(value / 100.0)

    def _on_mic_vol_changed(self, value):
        set_mic_volume(value)

    def _sync_volume_from_system(self):
        # Update slider if system volume changed externally
        if not self.mic_vol_slider.isSliderDown():
            sys_vol = get_mic_volume()
            if abs(self.mic_vol_slider.value() - sys_vol) > 1:
                self.mic_vol_slider.blockSignals(True)
                self.mic_vol_slider.setValue(sys_vol)
                self.mic_vol_slider.blockSignals(False)

    def _test_worker(self):
        if self.tester and self.tester.isRunning():
            return

        print(f"\n--- Connection Test Started [{time.strftime('%H:%M:%S')}] ---")
        node = self.remote_node_le.text().strip()
        manual_url = self.manual_url_le.text().strip()
        api_key = self.remote_key_le.text().strip()
        ts_key = self.ts_key_le.text().strip()

        if not node and not manual_url:
            self.worker_status_lbl.setText("Enter Node or URL")
            return

        self.worker_status_lbl.setText("Connecting...")
        self.worker_status_lbl.setStyleSheet("color: orange;")
        self.ts_status_lbl.setText("Checking...")
        self.ts_status_lbl.setStyleSheet("color: orange;")
        self.test_worker_btn.setEnabled(False)
        
        self.tester = ConnectionTester(node, api_key, manual_url, ts_key)
        self.tester.ts_signal.connect(self._on_ts_result)
        self.tester.worker_signal.connect(self._on_worker_result)
        self.tester.finished.connect(lambda: self.test_worker_btn.setEnabled(True))
        self.tester.start()

    def _on_ts_result(self, connected, state):
        if connected:
            self.ts_status_lbl.setText(f"{tr('status_connected')} ({state})")
            self.ts_status_lbl.setStyleSheet("color: green;")
            self.ts_fix_btn.setVisible(False)
        else:
            self.ts_status_lbl.setText(f"{tr('status_offline')} ({state})")
            self.ts_status_lbl.setStyleSheet("color: red;")
            
            # Show fix button if it looks like the service is stuck
            if "starting" in state.lower() or "nostate" in state.lower():
                self.ts_fix_btn.setVisible(True)
            else:
                self.ts_fix_btn.setVisible(False)

            # 🔹 Offer to download Tailscale if not found
            if "not found" in state.lower():
                from app.tailscale_manager import TailscaleDownloadDialog
                reply = QMessageBox.question(
                    self,
                    "Tailscale Required",
                    "Tailscale is not installed on this system. It is required for discovering remote workers in your private network.\n\nDo you want to download and install it now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    dlg = TailscaleDownloadDialog(self)
                    dlg.start_download()
                    dlg.exec()
                    # After install, we could re-test, but the worker client might need 
                    # to re-scan paths or wait for the service to start.


    def _on_worker_result(self, online, message, color):
        self.worker_status_lbl.setText(message)
        self.worker_status_lbl.setStyleSheet(f"color: {color};")

    def _fix_tailscale(self):
        from app.worker_client import WorkerClient
        ts_key = self.ts_key_le.text().strip()
        client = WorkerClient()
        ok, msg = client.restart_tailscale_service(auth_key=ts_key)
        if ok:
            QMessageBox.information(self, tr("info_title"), msg)
            # Re-test after a short delay
            QTimer.singleShot(5000, self._test_worker)
        else:
            QMessageBox.warning(self, tr("status_error"), f"Failed to restart service:\n{msg}")

    def _on_use_gpu_toggled(self, state):
        from PySide6.QtCore import Qt
        if state == Qt.Checked or state == 2:
            # 1. Hardware Check
            if not check_hardware_for_nvidia():
                QMessageBox.warning(
                    self,
                    "Hardware Not Supported",
                    "An NVIDIA GPU was not detected on your system.\nCurrently, only NVIDIA graphics cards (CUDA) are supported for local hardware acceleration.\nFalling back to CPU."
                )
                self.use_gpu_chk.blockSignals(True)
                self.use_gpu_chk.setChecked(False)
                self.use_gpu_chk.blockSignals(False)
                return

            # 2. Software Check
            if not check_gpu_available():
                reply = QMessageBox.question(
                    self, 
                    "GPU Libraries Required", 
                    "To use your NVIDIA GPU, the app needs to download ~100MB of CUDA libraries.\nDo you want to download them now?", 
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    dialog = GPUDownloadDialog(self)
                    dialog.start_download()
                    res = dialog.exec()
                    # If it failed or rejected, rollback check
                    if res != QDialog.Accepted:
                        self.use_gpu_chk.blockSignals(True)
                        self.use_gpu_chk.setChecked(False)
                        self.use_gpu_chk.blockSignals(False)
                else:
                    self.use_gpu_chk.blockSignals(True)
                    self.use_gpu_chk.setChecked(False)
                    self.use_gpu_chk.blockSignals(False)

    def save(self):
        self.vol_timer.stop()
        self.config["model_name"] = self.model_cb.currentText()
        self.config["selected_mic"] = self.mic_cb.currentData()
        self.config["engine"] = self.engine_cb.currentData()
        self.config["language"] = self.lang_cb.currentData()
        self.config["ui_language"] = self.ui_lang_cb.currentData()
        self.config["output_mode"] = self.output_cb.currentText()
        self.config["paste_delay"] = self.delay_sb.value()
        self.config["autostart"] = self.autostart_chk.isChecked()
        self.config["always_on_top"] = self.always_on_top_chk.isChecked()
        self.config["ui_design"] = self.design_cb.currentData()
        self.config["use_gpu"] = self.use_gpu_chk.isChecked()
        
        # Apply autostart setting
        set_autostart(self.config["autostart"])

        self.config["add_space"] = self.add_space_chk.isChecked()
        self.config["add_newline"] = self.add_newline_chk.isChecked()
        self.config["pause_media_on_record"] = self.pause_media_chk.isChecked()
        
        self.config["opacity"] = self.opacity_slider.value() / 100.0
        self.config["hotkey"] = self.hotkey_le.text().strip().lower()
        self.config["beam_size"] = self.beam_size_sb.value()
        self.config["temperature"] = self.temp_sb.value()
        self.config["backspace_cleanup"] = self.cleanup_sb.value()
        self.config["unload_idle"] = self.unload_idle_chk.isChecked()
        self.config["idle_time_minutes"] = self.idle_time_sb.value()
        self.config["pre_record_seconds"] = self.pre_record_sb.value()
        self.config["initial_prompt"] = self.prompt_le.text()
        self.config["remote_mode"] = self.remote_mode_chk.isChecked()
        self.config["remote_worker_name"] = self.remote_node_le.text().strip()
        self.config["remote_api_key"] = self.remote_key_le.text().strip()
        self.config["remote_worker_url"] = self.manual_url_le.text().strip()
        self.config["tailscale_auth_key"] = self.ts_key_le.text().strip()
        
        save_config(self.config)
        set_ui_lang(self.config["ui_language"])
        self.accept()

    def cancel(self):
        self.vol_timer.stop()
        self.opacity_preview.emit(self.original_opacity)
        self.reject()
