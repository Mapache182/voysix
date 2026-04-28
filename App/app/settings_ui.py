from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QPushButton, QDoubleSpinBox, QFormLayout, QSlider, QSpinBox, QLineEdit, QMessageBox,
    QTabWidget, QWidget, QScrollArea, QMenu
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
from app.presets import PROMPT_PRESETS, get_preset_text

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
        self.setMinimumSize(420, 550)
        
        main_layout = QVBoxLayout(self)
        
        # --- TAB WIDGET ---
        self.tabs = QTabWidget()
        
        self.init_general_tab()
        self.init_local_tab()
        self.init_remote_tab()
        
        main_layout.addWidget(self.tabs)

        # --- BOTTOM BUTTONS ---
        buttons = QHBoxLayout()
        save_btn = QPushButton(tr("save"))
        save_btn.setStyleSheet("font-weight: bold; padding: 6px 12px;")
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.setStyleSheet("padding: 6px 12px;")
        cancel_btn.clicked.connect(self.cancel)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        main_layout.addLayout(buttons)

        # Timers & Tester
        self.vol_timer = QTimer(self)
        self.vol_timer.timeout.connect(self._sync_volume_from_system)
        self.vol_timer.start(500)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._test_worker)
        
        self.tester = None

        if self.remote_mode_chk.isChecked():
            self._toggle_status_timer(Qt.Checked)
            QTimer.singleShot(1000, self._test_worker)

    def add_info_row(self, form, label_key, widget, help_key):
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
        
        form.addRow(tr(label_key), row_layout)

    def init_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        # Interface Language
        self.ui_lang_cb = QComboBox()
        ui_langs = {"en": "English", "ru": "Русский", "es": "Español"}
        for code, name in ui_langs.items():
            self.ui_lang_cb.addItem(name, code)
        self.ui_lang_cb.setCurrentIndex(max(0, self.ui_lang_cb.findData(self.config.get("ui_language", "en"))))
        self.add_info_row(form, "ui_lang", self.ui_lang_cb, "ui_lang")

        # Design
        self.design_cb = QComboBox()
        self.design_cb.addItem(tr("design_classic"), "classic")
        self.design_cb.addItem(tr("design_waveform"), "waveform")
        self.design_cb.setCurrentIndex(max(0, self.design_cb.findData(self.config.get("ui_design", "classic"))))
        self.add_info_row(form, "ui_design", self.design_cb, "ui_design")

        # Logging level
        self.log_level_cb = QComboBox()
        self.log_level_cb.addItem(tr("log_none"), "none")
        self.log_level_cb.addItem(tr("log_info"), "info")
        self.log_level_cb.addItem(tr("log_debug"), "debug")
        self.log_level_cb.setCurrentIndex(max(0, self.log_level_cb.findData(self.config.get("log_level", "info"))))
        self.add_info_row(form, "log_level", self.log_level_cb, "log_level_help")

        # Mic
        self.mic_cb = QComboBox()
        self.mic_cb.addItem(tr("default_mic"), None)
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                self.mic_cb.addItem(f"{i}: {dev['name']}", i)
        idx = self.mic_cb.findData(self.config["selected_mic"])
        self.mic_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.add_info_row(form, "microphone", self.mic_cb, "mic")

        # Mic Volume
        self.mic_vol_slider = QSlider(Qt.Horizontal)
        self.mic_vol_slider.setRange(0, 100)
        self.mic_vol_slider.setValue(get_mic_volume())
        self.mic_vol_slider.valueChanged.connect(self._on_mic_vol_changed)
        self.add_info_row(form, "mic_volume", self.mic_vol_slider, "mic_vol")

        # Hotkey
        self.hotkey_le = HotkeyLineEdit(self.config.get("hotkey", "middle_click"))
        self.add_info_row(form, "hotkey", self.hotkey_le, "hotkey")

        # Behavior
        self.autostart_chk = QCheckBox(tr("enabled"))
        self.autostart_chk.setChecked(is_autostart_enabled())
        self.add_info_row(form, "autostart", self.autostart_chk, "autostart")

        self.always_on_top_chk = QCheckBox(tr("enabled"))
        self.always_on_top_chk.setChecked(self.config.get("always_on_top", True))
        self.add_info_row(form, "always_on_top", self.always_on_top_chk, "always_on_top")

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.original_opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        self.add_info_row(form, "ui_opacity", self.opacity_slider, "opacity")

        self.pause_media_chk = QCheckBox(tr("enabled"))
        self.pause_media_chk.setChecked(self.config.get("pause_media_on_record", False))
        self.add_info_row(form, "pause_media", self.pause_media_chk, "pause_media")

        self.pre_record_sb = QDoubleSpinBox()
        self.pre_record_sb.setRange(0.0, 5.0)
        self.pre_record_sb.setSingleStep(0.5)
        self.pre_record_sb.setValue(self.config.get("pre_record_seconds", 0.0))
        self.add_info_row(form, "pre_record", self.pre_record_sb, "pre_record")

        # Output group
        form.addRow(QLabel(f"<br><b>{tr('output_mode')}</b>"), QLabel(""))
        self.output_cb = QComboBox()
        self.output_cb.addItems(["type", "clipboard", "console"])
        self.output_cb.setCurrentText(self.config["output_mode"])
        self.add_info_row(form, "output_mode", self.output_cb, "mode")

        self.delay_sb = QDoubleSpinBox()
        self.delay_sb.setRange(0.1, 5.0)
        self.delay_sb.setValue(self.config["paste_delay"])
        self.add_info_row(form, "paste_delay", self.delay_sb, "delay")

        self.add_space_chk = QCheckBox(tr("enabled"))
        self.add_space_chk.setChecked(self.config.get("add_space", False))
        self.add_info_row(form, "add_space", self.add_space_chk, "add_space")

        self.add_newline_chk = QCheckBox(tr("enabled"))
        self.add_newline_chk.setChecked(self.config.get("add_newline", False))
        self.add_info_row(form, "add_newline", self.add_newline_chk, "add_newline")

        self.cleanup_sb = QSpinBox()
        self.cleanup_sb.setRange(0, 10)
        self.cleanup_sb.setValue(self.config.get("backspace_cleanup", 0))
        self.add_info_row(form, "backspace_cleanup", self.cleanup_sb, "backspace_cleanup")

        # --- Processing context (Moved to General) ---
        form.addRow(QLabel(f"<br><b>{tr('processing_settings')}</b>"), QLabel(""))
        
        self.prompt_le = QLineEdit()
        self.prompt_le.setText(self.config.get("initial_prompt", ""))
        self.prompt_le.setPlaceholderText("Context words...")
        
        # Preset button
        preset_btn = QPushButton(tr("presets"))
        preset_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        preset_btn.clicked.connect(self._show_preset_menu)
        
        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(self.prompt_le)
        prompt_layout.addWidget(preset_btn)
        
        info_btn = QPushButton("ⓘ")
        info_btn.setFixedSize(20, 20)
        info_btn.setStyleSheet("""
            QPushButton { 
                border: none; color: #0078d4; font-weight: bold; background: transparent; font-size: 14px;
            }
            QPushButton:hover { color: #005a9e; }
        """)
        info_btn.clicked.connect(lambda: QMessageBox.information(self, tr("info_title"), hlp("prompt")))
        prompt_layout.addWidget(info_btn)

        form.addRow(tr("initial_prompt"), prompt_layout)

        from PySide6.QtWidgets import QPlainTextEdit
        self.replacements_te = QPlainTextEdit()
        self.replacements_te.setPlaceholderText("word:replacement\nмерч:merch")
        self.replacements_te.setPlainText(self.config.get("word_replacements", ""))
        self.replacements_te.setMaximumHeight(80)
        self.add_info_row(form, "word_replacements", self.replacements_te, "word_replacements")

        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(tab, tr("tab_general"))

    def init_local_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        # Enabled
        self.local_enabled_chk = QCheckBox(tr("enabled"))
        self.local_enabled_chk.setChecked(self.config.get("local_whisper_enabled", True))
        self.add_info_row(form, "local_whisper", self.local_enabled_chk, "local_whisper")

        # Engine
        self.engine_cb = QComboBox()
        self.engine_cb.addItem("OpenAI Whisper", "openai-whisper")
        self.engine_cb.addItem("Faster Whisper", "faster-whisper")
        idx = self.engine_cb.findData(self.config.get("engine", "openai-whisper"))
        self.engine_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.add_info_row(form, "engine", self.engine_cb, "engine")

        # Model
        self.model_cb = QComboBox()
        self.model_cb.addItems(["tiny", "base", "small", "medium", "large", "distil-large-v3"])
        self.model_cb.setCurrentText(self.config["model_name"])
        self.add_info_row(form, "model", self.model_cb, "model")

        # Transcribe Language
        self.lang_cb = QComboBox()
        langs = {"auto": "Auto Detect", "en": "English", "ru": "Russian", "de": "German", "fr": "French", "es": "Spanish"}
        for code, name in langs.items():
            self.lang_cb.addItem(name, code)
        self.lang_cb.setCurrentIndex(max(0, self.lang_cb.findData(self.config.get("language", "auto"))))
        self.add_info_row(form, "language", self.lang_cb, "lang")

        # GPU
        self.use_gpu_chk = QCheckBox(tr("enabled"))
        self.use_gpu_chk.setChecked(self.config.get("use_gpu", False))
        self.use_gpu_chk.stateChanged.connect(self._on_use_gpu_toggled)
        form.addRow("Use GPU (NVIDIA):", self.use_gpu_chk)

        # Advanced
        form.addRow(QLabel(f"<br><b>{tr('processing_settings')}</b>"), QLabel(""))
        
        self.beam_size_sb = QSpinBox()
        self.beam_size_sb.setRange(1, 10)
        self.beam_size_sb.setValue(self.config.get("beam_size", 5))
        self.add_info_row(form, "beam_size", self.beam_size_sb, "beam")

        self.temp_sb = QDoubleSpinBox()
        self.temp_sb.setRange(0.0, 1.0)
        self.temp_sb.setSingleStep(0.1)
        self.temp_sb.setValue(self.config.get("temperature", 0.0))
        self.add_info_row(form, "temperature", self.temp_sb, "temp")

        self.unload_idle_chk = QCheckBox(tr("enabled"))
        self.unload_idle_chk.setChecked(self.config.get("unload_idle", True))
        self.add_info_row(form, "unload_idle", self.unload_idle_chk, "unload_idle")

        self.idle_time_sb = QSpinBox()
        self.idle_time_sb.setRange(1, 60)
        self.idle_time_sb.setValue(self.config.get("idle_time_minutes", 5))
        self.add_info_row(form, "idle_time", self.idle_time_sb, "idle_time")

        self.no_speech_sb = QDoubleSpinBox()
        self.no_speech_sb.setRange(0.0, 1.0)
        self.no_speech_sb.setSingleStep(0.05)
        self.no_speech_sb.setValue(self.config.get("no_speech_threshold", 0.6))
        self.add_info_row(form, "no_speech_threshold", self.no_speech_sb, "no_speech")

        self.logprob_sb = QDoubleSpinBox()
        self.logprob_sb.setRange(-10.0, 1.0)
        self.logprob_sb.setSingleStep(0.1)
        self.logprob_sb.setValue(self.config.get("logprob_threshold", -1.0))
        self.add_info_row(form, "logprob_threshold", self.logprob_sb, "logprob")

        self.compression_sb = QDoubleSpinBox()
        self.compression_sb.setRange(0.0, 10.0)
        self.compression_sb.setSingleStep(0.1)
        self.compression_sb.setValue(self.config.get("compression_ratio_threshold", 2.4))
        self.add_info_row(form, "compression_ratio_threshold", self.compression_sb, "compression")

        self.condition_chk = QCheckBox(tr("enabled"))
        self.condition_chk.setChecked(self.config.get("condition_on_previous_text", True))
        self.add_info_row(form, "condition_on_previous_text", self.condition_chk, "always_on_top")

        self.hallucination_sb = QDoubleSpinBox()
        self.hallucination_sb.setRange(0.0, 10.0)
        self.hallucination_sb.setSingleStep(0.1)
        self.hallucination_sb.setValue(self.config.get("hallucination_silence_threshold", 2.0))
        self.add_info_row(form, "hallucination_silence_threshold", self.hallucination_sb, "hallucination")

        self.repetition_sb = QDoubleSpinBox()
        self.repetition_sb.setRange(1.0, 10.0)
        self.repetition_sb.setSingleStep(0.1)
        self.repetition_sb.setValue(self.config.get("repetition_penalty", 1.0))
        self.add_info_row(form, "repetition_penalty", self.repetition_sb, "repetition")

        self.no_repeat_sb = QSpinBox()
        self.no_repeat_sb.setRange(0, 10)
        self.no_repeat_sb.setValue(self.config.get("no_repeat_ngram_size", 0))
        self.add_info_row(form, "no_repeat_ngram_size", self.no_repeat_sb, "no_repeat")

        self.smart_normalization_chk = QCheckBox(tr("enabled"))
        self.smart_normalization_chk.setChecked(self.config.get("smart_normalization", False))
        self.add_info_row(form, "smart_normalization", self.smart_normalization_chk, "smart_normalization")

        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(tab, tr("tab_local"))

    def init_remote_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        self.remote_mode_chk = QCheckBox(tr("enabled"))
        self.remote_mode_chk.setChecked(self.config.get("remote_mode", False))
        self.remote_mode_chk.stateChanged.connect(self._toggle_status_timer)
        self.add_info_row(form, "remote_worker", self.remote_mode_chk, "remote_worker")

        self.remote_node_le = QLineEdit()
        self.remote_node_le.setText(self.config.get("remote_worker_name", ""))
        self.remote_node_le.setPlaceholderText("voysix-worker")
        self.add_info_row(form, "remote_node", self.remote_node_le, "remote_node")

        self.remote_key_le = QLineEdit()
        self.remote_key_le.setEchoMode(QLineEdit.Password)
        self.remote_key_le.setText(self.config.get("remote_api_key", ""))
        self.add_info_row(form, "worker_api_key", self.remote_key_le, "remote_api_key")

        self.manual_url_le = QLineEdit()
        self.manual_url_le.setText(self.config.get("remote_worker_url", ""))
        self.manual_url_le.setPlaceholderText("http://100.x.y.z:8000")
        self.add_info_row(form, "manual_url", self.manual_url_le, "manual_url_help")

        self.ts_key_le = QLineEdit()
        self.ts_key_le.setEchoMode(QLineEdit.Password)
        self.ts_key_le.setText(self.config.get("tailscale_auth_key", ""))
        self.ts_key_le.setPlaceholderText("tskey-auth-...")
        self.add_info_row(form, "ts_authkey", self.ts_key_le, "ts_authkey")

        # Status labels
        form.addRow(QLabel(f"<br><b>{tr('worker_status')}</b>"), QLabel(""))
        
        self.worker_status_lbl = QLabel(tr("status_offline"))
        self.worker_status_lbl.setStyleSheet("color: gray;")
        form.addRow(tr("worker_status"), self.worker_status_lbl)

        self.ts_status_lbl = QLabel("---")
        self.ts_status_lbl.setStyleSheet("color: gray;")
        
        self.ts_fix_btn = QPushButton(tr("ts_fix_btn"))
        self.ts_fix_btn.setVisible(False)
        self.ts_fix_btn.clicked.connect(self._fix_tailscale)
        
        ts_layout = QHBoxLayout()
        ts_layout.addWidget(self.ts_status_lbl)
        ts_layout.addWidget(self.ts_fix_btn)
        ts_layout.addStretch()
        form.addRow(tr("ts_status"), ts_layout)

        # 🔹 Remote-specific transcription settings
        form.addRow(QLabel(f"<br><b>{tr('processing_settings')}</b>"), QLabel(""))

        # Remote Engine
        self.remote_engine_cb = QComboBox()
        self.remote_engine_cb.addItem("OpenAI Whisper", "openai-whisper")
        self.remote_engine_cb.addItem("Faster Whisper", "faster-whisper")
        idx = self.remote_engine_cb.findData(self.config.get("remote_engine", "openai-whisper"))
        self.remote_engine_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.add_info_row(form, "engine", self.remote_engine_cb, "engine")

        # Remote Audio Format
        self.remote_audio_format_cb = QComboBox()
        self.remote_audio_format_cb.addItem("FLAC (Lossless, Rec.)", "flac")
        self.remote_audio_format_cb.addItem("OGG Vorbis (High Compress)", "ogg")
        self.remote_audio_format_cb.addItem("WAV (Uncompressed)", "wav")
        idx = self.remote_audio_format_cb.findData(self.config.get("remote_audio_format", "flac"))
        self.remote_audio_format_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.add_info_row(form, "Audio Format", self.remote_audio_format_cb, "audio_format")

        # Remote Model
        self.remote_model_cb = QComboBox()
        self.remote_model_cb.addItems(["tiny", "base", "small", "medium", "large", "distil-large-v3"])
        self.remote_model_cb.setCurrentText(self.config.get("remote_model_name", "base"))
        self.add_info_row(form, "model", self.remote_model_cb, "model")

        # Remote Language
        self.remote_lang_cb = QComboBox()
        langs = {"auto": "Auto Detect", "en": "English", "ru": "Russian", "de": "German", "fr": "French", "es": "Spanish"}
        for code, name in langs.items():
            self.remote_lang_cb.addItem(name, code)
        self.remote_lang_cb.setCurrentIndex(max(0, self.remote_lang_cb.findData(self.config.get("remote_language", "auto"))))
        self.add_info_row(form, "language", self.remote_lang_cb, "lang")

        # Remote Beam Size
        self.remote_beam_size_sb = QSpinBox()
        self.remote_beam_size_sb.setRange(1, 10)
        self.remote_beam_size_sb.setValue(self.config.get("remote_beam_size", 5))
        self.add_info_row(form, "beam_size", self.remote_beam_size_sb, "beam")

        # Remote Temperature
        self.remote_temp_sb = QDoubleSpinBox()
        self.remote_temp_sb.setRange(0.0, 1.0)
        self.remote_temp_sb.setSingleStep(0.1)
        self.remote_temp_sb.setValue(self.config.get("remote_temperature", 0.0))
        self.add_info_row(form, "temperature", self.remote_temp_sb, "temp")

        # 🔹 Remote advanced
        self.remote_no_speech_sb = QDoubleSpinBox()
        self.remote_no_speech_sb.setRange(0.0, 1.0)
        self.remote_no_speech_sb.setSingleStep(0.05)
        self.remote_no_speech_sb.setValue(self.config.get("remote_no_speech_threshold", 0.6))
        self.add_info_row(form, "no_speech_threshold", self.remote_no_speech_sb, "no_speech")

        self.remote_logprob_sb = QDoubleSpinBox()
        self.remote_logprob_sb.setRange(-10.0, 1.0)
        self.remote_logprob_sb.setSingleStep(0.1)
        self.remote_logprob_sb.setValue(self.config.get("remote_logprob_threshold", -1.0))
        self.add_info_row(form, "logprob_threshold", self.remote_logprob_sb, "logprob")

        self.remote_compression_sb = QDoubleSpinBox()
        self.remote_compression_sb.setRange(0.0, 10.0)
        self.remote_compression_sb.setSingleStep(0.1)
        self.remote_compression_sb.setValue(self.config.get("remote_compression_ratio_threshold", 2.4))
        self.add_info_row(form, "compression_ratio_threshold", self.remote_compression_sb, "compression")

        self.remote_condition_chk = QCheckBox(tr("enabled"))
        self.remote_condition_chk.setChecked(self.config.get("remote_condition_on_previous_text", True))
        self.add_info_row(form, "condition_on_previous_text", self.remote_condition_chk, "always_on_top")

        self.remote_hallucination_sb = QDoubleSpinBox()
        self.remote_hallucination_sb.setRange(0.0, 10.0)
        self.remote_hallucination_sb.setSingleStep(0.1)
        self.remote_hallucination_sb.setValue(self.config.get("remote_hallucination_silence_threshold", 2.0))
        self.add_info_row(form, "hallucination_silence_threshold", self.remote_hallucination_sb, "hallucination")

        self.remote_repetition_sb = QDoubleSpinBox()
        self.remote_repetition_sb.setRange(1.0, 10.0)
        self.remote_repetition_sb.setSingleStep(0.1)
        self.remote_repetition_sb.setValue(self.config.get("remote_repetition_penalty", 1.0))
        self.add_info_row(form, "repetition_penalty", self.remote_repetition_sb, "repetition")

        self.remote_no_repeat_sb = QSpinBox()
        self.remote_no_repeat_sb.setRange(0, 10)
        self.remote_no_repeat_sb.setValue(self.config.get("remote_no_repeat_ngram_size", 0))
        self.add_info_row(form, "no_repeat_ngram_size", self.remote_no_repeat_sb, "no_repeat")

        self.remote_smart_normalization_chk = QCheckBox(tr("enabled"))
        self.remote_smart_normalization_chk.setChecked(self.config.get("remote_smart_normalization", False))
        self.add_info_row(form, "smart_normalization", self.remote_smart_normalization_chk, "smart_normalization")

        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(tab, tr("tab_remote"))

    def _toggle_status_timer(self, state):
        if state == Qt.Checked or state == 2:
            self.status_timer.start(15000) # 15 seconds
        else:
            self.status_timer.stop()
            self.ts_status_lbl.setText("---")
            self.worker_status_lbl.setText(tr("status_offline"))

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
        
        # Only test if remote mode is actually enabled
        if not self.remote_mode_chk.isChecked():
            return

        print(f"\n--- Periodic Connection Check [{time.strftime('%H:%M:%S')}] ---")
        node = self.remote_node_le.text().strip()
        manual_url = self.manual_url_le.text().strip()
        api_key = self.remote_key_le.text().strip()
        ts_key = self.ts_key_le.text().strip()

        if not node and not manual_url:
            self.worker_status_lbl.setText("Enter Node or URL")
            return

        # Don't change text/color to orange here to avoid flickering every 15s
        # unless it was previously failed/unknown
        if "online" not in self.worker_status_lbl.text().lower():
             self.worker_status_lbl.setText("Connecting...")
             self.worker_status_lbl.setStyleSheet("color: orange;")
             self.ts_status_lbl.setText("Checking...")
             self.ts_status_lbl.setStyleSheet("color: orange;")
        
        self.tester = ConnectionTester(node, api_key, manual_url, ts_key)
        self.tester.ts_signal.connect(self._on_ts_result)
        self.tester.worker_signal.connect(self._on_worker_result)
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
                    tr("ts_not_found_title"),
                    tr("ts_not_found_msg"),
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
        self.status_timer.stop()
        self.config["model_name"] = self.model_cb.currentText()
        self.config["local_whisper_enabled"] = self.local_enabled_chk.isChecked()
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
        self.config["log_level"] = self.log_level_cb.currentData()
        
        # Apply autostart setting
        set_autostart(self.config["autostart"])

        self.config["add_space"] = self.add_space_chk.isChecked()
        self.config["add_newline"] = self.add_newline_chk.isChecked()
        self.config["pause_media_on_record"] = self.pause_media_chk.isChecked()
        self.config["smart_normalization"] = self.smart_normalization_chk.isChecked()
        self.config["opacity"] = self.opacity_slider.value() / 100.0
        self.config["hotkey"] = self.hotkey_le.text().strip().lower()
        self.config["beam_size"] = self.beam_size_sb.value()
        self.config["temperature"] = self.temp_sb.value()
        self.config["no_speech_threshold"] = self.no_speech_sb.value()
        self.config["logprob_threshold"] = self.logprob_sb.value()
        self.config["compression_ratio_threshold"] = self.compression_sb.value()
        self.config["condition_on_previous_text"] = self.condition_chk.isChecked()
        self.config["hallucination_silence_threshold"] = self.hallucination_sb.value()
        self.config["repetition_penalty"] = self.repetition_sb.value()
        self.config["no_repeat_ngram_size"] = self.no_repeat_sb.value()
        self.config["word_replacements"] = self.replacements_te.toPlainText()

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
        
        # New remote-specific transcription settings
        self.config["remote_model_name"] = self.remote_model_cb.currentText()
        self.config["remote_engine"] = self.remote_engine_cb.currentData()
        self.config["remote_audio_format"] = self.remote_audio_format_cb.currentData()
        self.config["remote_language"] = self.remote_lang_cb.currentData()
        self.config["remote_beam_size"] = self.remote_beam_size_sb.value()
        self.config["remote_temperature"] = self.remote_temp_sb.value()
        self.config["remote_no_speech_threshold"] = self.remote_no_speech_sb.value()
        self.config["remote_logprob_threshold"] = self.remote_logprob_sb.value()
        self.config["remote_compression_ratio_threshold"] = self.remote_compression_sb.value()
        self.config["remote_condition_on_previous_text"] = self.remote_condition_chk.isChecked()
        self.config["remote_hallucination_silence_threshold"] = self.remote_hallucination_sb.value()
        self.config["remote_repetition_penalty"] = self.remote_repetition_sb.value()
        self.config["remote_no_repeat_ngram_size"] = self.remote_no_repeat_sb.value()
        self.config["remote_smart_normalization"] = self.remote_smart_normalization_chk.isChecked()

        save_config(self.config)
        set_ui_lang(self.config["ui_language"])
        self.accept()

    def _show_preset_menu(self):
        menu = QMenu(self)
        for key, data in PROMPT_PRESETS.items():
            action = menu.addAction(data["name"])
            action.triggered.connect(lambda checked=False, k=key: self._apply_preset(k))
        
        # Position menu above/below button
        btn = self.sender()
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _apply_preset(self, key):
        text = get_preset_text(key)
        if not text: return
        
        if self.prompt_le.text().strip():
            msg = QMessageBox(self)
            msg.setWindowTitle(tr("presets"))
            msg.setText("Replace existing prompt or append?\n\nЗаменить текущую подсказку или добавить в конец?")
            
            replace_btn = msg.addButton(tr("replace"), QMessageBox.ActionRole)
            append_btn = msg.addButton(tr("append"), QMessageBox.ActionRole)
            msg.addButton(tr("cancel"), QMessageBox.RejectRole)
            
            msg.exec()
            
            if msg.clickedButton() == replace_btn:
                self.prompt_le.setText(text)
            elif msg.clickedButton() == append_btn:
                current = self.prompt_le.text().strip()
                if not current.endswith(","): current += ","
                self.prompt_le.setText(f"{current} {text}")
        else:
            self.prompt_le.setText(text)

    def cancel(self):
        self.vol_timer.stop()
        self.status_timer.stop()
        self.opacity_preview.emit(self.original_opacity)
        self.reject()
