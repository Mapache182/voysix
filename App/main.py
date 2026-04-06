import sys
import os
# Prioritize local project directory to avoid importing from "Program Files"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ctypes
import threading
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtGui import QIcon

import time
from app.ui import FloatingStatus, AppTrayIcon, LogWindow, LogHandler
from app.settings_ui import SettingsDialog
from app.recorder import AudioRecorder
from app.transcriber import WhisperTranscriber
from app.hotkeys import GlobalListener
from app.settings import load_config, save_config
from app.utils import output_transcription, get_resource_path, toggle_media_playback
import queue
from app.i18n import set_ui_lang, tr
from app.volume import get_mic_volume, set_mic_volume

class AppController(QObject):
    status_changed = Signal(str)
    log_signal = Signal(str)
    level_changed = Signal(float)
    
    def __init__(self):
        super().__init__()
        
        # Log Window setup (start redirecting immediately to catch all init logs)
        self.log_window = LogWindow()
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            self.log_window.setWindowIcon(QIcon(icon_path))
        self.log_signal.connect(self.log_window.append_log)
        sys.stdout = LogHandler(self.log_signal)
        sys.stderr = LogHandler(self.log_signal)
        
        self.config = load_config()
        set_ui_lang(self.config.get("ui_language", "en"))
        
        # Load version
        self.version = "4.4.65"
        version_file = get_resource_path("version.txt")
        if os.path.exists(version_file):
            try:
                with open(version_file, "r") as f:
                    self.version = f.read().strip()
            except: pass
        
        # Poke the mic volume to ensure it's "awake" and unmuted
        try:
            current_vol = get_mic_volume()
            set_mic_volume(current_vol)
            print(f"Self-check: Microphone volume is at {current_vol}% and unmuted.")
        except Exception as e:
            print(f"Mic poke failed: {e}")

        self.recorder = AudioRecorder(on_level_callback=lambda level: self.level_changed.emit(level))
        self.recorder.set_pre_buffer(self.config.get("pre_record_seconds", 0.0))
        # If pre-recording is ON, we must start the stream immediately
        if self.config.get("pre_record_seconds", 0.0) > 0:
            self.recorder._start_stream(device=self.config["selected_mic"])
            
        self.transcriber = WhisperTranscriber(
            self.config["model_name"], 
            self.config.get("engine", "openai-whisper"),
            use_gpu=self.config.get("use_gpu", False)
        )
        self.last_toggle_time = 0
        self.min_recording_duration = 0.5 # 500ms
        self.debounce_time = 0.3 # 300ms
        
        # --- Transcription Queue Setup ---
        self.audio_queue = queue.Queue()
        self.processing_thread = threading.Thread(target=self._queue_worker, daemon=True)
        self.processing_thread.start()
        self.is_processing = False
        
        # Background model loading (if not in RAM saving mode)
        self.last_action_time = time.time()
        if not self.config.get("unload_idle", False):
            self.load_model_async()
        
        # Idle timer to unload model
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.check_idle)
        self.idle_timer.start(30000) # Check every 30 seconds
        
        self.listener = GlobalListener(self.on_press, self.on_release, self.on_abort)
        self.listener.start(self.config["hotkey"])
        
        self.floating_ui = FloatingStatus()
        pos = self.config.get("window_pos", [20, 20])
        self.floating_ui.move(pos[0], pos[1])
        size = self.config.get("window_size", [160, 40])
        self.floating_ui.resize(size[0], size[1])
        self.floating_ui.setWindowOpacity(self.config.get("opacity", 0.9))
        self.floating_ui.set_always_on_top(self.config.get("always_on_top", True))
        self.floating_ui.ui_design = self.config.get("ui_design", "classic")
        self.floating_ui.show()
        

        
        self.tray = AppTrayIcon()
        self.tray.exit_action.triggered.connect(self.quit)
        self.tray.settings_action.triggered.connect(self.show_settings)
        self.tray.log_action.triggered.connect(self.show_logs)
        self.tray.restart_action.triggered.connect(self.restart_services)
        self.tray.about_action.triggered.connect(self.show_about)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        # Timer to detect sleep/wake
        self.last_check_time = time.time()
        self.sleep_check_timer = QTimer(self)
        self.sleep_check_timer.timeout.connect(self.check_system_sleep)
        self.sleep_check_timer.start(10000) # Check every 10 seconds
        

        
        print("Application started.")
        
        self.floating_ui.show_context_menu = self.show_floating_context_menu
        self.floating_ui.show_settings_callback = self.show_settings
        self.floating_ui.geometry_changed.connect(self.on_window_geometry_change)
        self.status_changed.connect(self.update_status) # Changed from set_status
        self.level_changed.connect(self.floating_ui.set_level)
        
        self.abort_transcription = False
        self.settings_dialog = None
        self.worker_url = None
        self.worker_info = None
        
        # Periodic discovery for remote worker
        self.discovery_timer = QTimer(self)
        self.discovery_timer.timeout.connect(self._background_discovery)
        self.discovery_timer.start(60000) # Check every 60 seconds
        
        # Initial check
        QTimer.singleShot(2000, self._background_discovery)

        self.ui_update_timer = QTimer(self)
        self.ui_update_timer.timeout.connect(self._on_ui_update_timer)
        self.recording_start_time = 0
        self.transcription_start_time = 0

    def _on_ui_update_timer(self):
        if self.recorder.recording and self.recording_start_time > 0:
            elapsed = time.time() - self.recording_start_time
            self.floating_ui.set_durations(recording=elapsed)
        
        if self.is_processing and self.transcription_start_time > 0:
            elapsed = time.time() - self.transcription_start_time
            self.floating_ui.set_durations(transcription=elapsed)

    @Slot(str)
    def update_status(self, status):
        self.floating_ui.set_status(status)
        if status in ["recording", "processing"]:
            if not self.ui_update_timer.isActive():
                self.ui_update_timer.start(100)
        elif status == "idle":
             self.ui_update_timer.stop()
        # "done" status doesn't stop the timer immediately to let final values settle or show for a bit
        # But wait, "done" status lasts 2 seconds, then goes to "idle".
        # So it's fine.

    def on_press(self):
        try:
            current_time = time.time()
            if (current_time - self.last_toggle_time) < self.debounce_time:
                return
                
            if getattr(self.transcriber, 'loading', False):
                print("Action blocked: Model is still loading.")
                return
                
            if not self.recorder.recording:
                # Start recording
                print("Starting recording...")
                self.last_toggle_time = current_time
                self.last_action_time = current_time
                
                # Start loading model if needed
                if self.transcriber.model is None and not self.config.get("remote_mode", False):
                    print("Loading model on demand...")
                    self.load_model_async()
                
                self.status_changed.emit("recording")
                if self.config.get("pause_media_on_record", False):
                    toggle_media_playback()
                self.recorder.start(device=self.config["selected_mic"])
                
                self.recording_start_time = time.time()
                self.transcription_start_time = 0
                self.floating_ui.set_durations(recording=0.0, transcription=0.0) # Clear previous
            else:
                # Check duration
                duration = current_time - self.last_toggle_time
                if duration < self.min_recording_duration:
                    print(f"Recording too short ({duration:.2f}s), ignoring stop.")
                    return

                # Stop recording and put into queue
                print("Stopping recording... Adding to queue.")
                self.last_toggle_time = current_time
                if self.config.get("pause_media_on_record", False):
                    toggle_media_playback()
                audio = self.recorder.stop()
                # final duration will be set by the timer or final check
                final_dur = time.time() - self.recording_start_time
                self.floating_ui.set_durations(recording=final_dur)
                
                if audio is not None and len(audio) > 0:
                    self.audio_queue.put(audio)
                    # Status logic is now handled in _queue_worker and on_press
                else:
                    print("No audio data recorded.")
                
                # Update status based on whether queue is working
                if self.is_processing or not self.audio_queue.empty():
                    self.status_changed.emit("processing")
                else:
                    self.status_changed.emit("idle")
        except Exception as e:
            print(f"Error in on_press: {e}")
            self.status_changed.emit("idle")

    def on_release(self):
        # We now use toggle logic (click to start / click to stop)
        pass

    def on_abort(self):
        try:
            if self.recorder.recording:
                print("Recording ABORTED by user (Escape).")
                if self.config.get("pause_media_on_record", False):
                    toggle_media_playback()
                self.recorder.stop()
                self.floating_ui.set_durations(recording=0.0, transcription=0.0)
                self.status_changed.emit("idle")
            
            if self.is_processing:
                print("Transcription CANCEL requested by user (Escape).")
                self.abort_transcription = True
                self.status_changed.emit("idle")
        except Exception as e:
            print(f"Error in on_abort: {e}")

    def load_model_async(self, model_name=None, engine=None, use_gpu=None):
        if getattr(self.transcriber, 'loading', False):
             print("Reload already in progress, ignoring.")
             return
             
        self.status_changed.emit("loading")
        def target():
            try:
                # 🔹 GIVE OS A MOMENT to settle after dialog close and before new thread starts heavy work
                # This helps preventing 0xc0000005 when COM objects are being GC'd
                time.sleep(0.5)
                self.transcriber.load_model(model_name, engine, use_gpu)
            except Exception as e:
                print(f"Async Model Load Error: {e}")
            finally:
                self.status_changed.emit("idle")
        threading.Thread(target=target, daemon=True).start()


    def _queue_worker(self):
        """Dedicated thread to handle the audio queue sequentially."""
        while True:
            try:
                audio = self.audio_queue.get(block=True)
                self.is_processing = True
                
                # If we are NOT recording right now, show processing status
                if not self.recorder.recording:
                    self.status_changed.emit("processing")
                
                self.process_audio(audio)
                
                self.is_processing = False
                
                # After finishing one, if we are NOT recording and queue is empty, set idle
                if not self.recorder.recording:
                    if self.audio_queue.empty():
                        self.status_changed.emit("done")
                    else:
                        self.status_changed.emit("processing")
                        
            except Exception as e:
                print(f"Error in queue worker: {e}")
                self.is_processing = False

    def process_audio(self, audio):
        self.transcription_start_time = time.time()
        try:
            print(f"Transcription started for {len(audio)/16000:.2f}s of audio...")
            self.abort_transcription = False # Reset flag at start
            
            # --- Remote Mode Logic with Fallback ---
            transcriber = self.transcriber
            if self.config.get("remote_mode", False):
                from app.transcriber import RemoteWhisperTranscriber
                
                # Check for discoverable worker
                remote = RemoteWhisperTranscriber(
                    self.config.get("remote_worker_name", "voysix-worker"),
                    api_key=self.config.get("remote_api_key", ""),
                    manual_url=self.config.get("remote_worker_url", "")
                )
                
                # Use cached URL from background discovery if available for faster check
                if self.worker_url:
                    remote.client.base_url = self.worker_url
                
                # Crucial Check: Verify if remote worker is actually ONLINE and HEALTHY
                # This prevents sending large audio blobs to a dead endpoint
                is_available = False
                if remote.client.base_url:
                    print(f"Verifying remote worker health at {remote.client.base_url}...")
                    if remote.client.check_health():
                        is_available = True
                
                # If cached URL is invalid, try new discovery
                if not is_available:
                    print("Remote worker status uncertain. Attempting discovery...")
                    if remote.load_model(): # load_model calls discover()
                        if remote.client.check_health():
                            is_available = True
                            self.worker_url = remote.client.base_url
                
                if is_available:
                    transcriber = remote
                    print(f"✅ Using REMOTE transcriber (worker at {remote.client.base_url})")
                else:
                    print("⚠️ Remote worker NOT REACHABLE. Falling back to LOCAL.")
                    # 🔹 Ensure local model is loaded if we fall back
                    if transcriber.model is None:
                        print("Local model not loaded, loading now...")
                        self.status_changed.emit("loading")
                        transcriber.load_model(self.config["model_name"], self.config.get("engine", "openai-whisper"))
                        self.status_changed.emit("processing")

            # 🔹 Select appropriate parameters for local or remote mode
            if self.config.get("remote_mode", False) and is_available:
                lang = self.config.get("remote_language", "auto")
                model = self.config.get("remote_model_name", "base")
                engine = self.config.get("remote_engine", "openai-whisper")
                beam = self.config.get("remote_beam_size", 5)
                temp = self.config.get("remote_temperature", 0.0)
                prompt = self.config.get("remote_initial_prompt", "")
                no_speech = self.config.get("remote_no_speech_threshold", 0.6)
                logprob = self.config.get("remote_logprob_threshold", -1.0)
                compression = self.config.get("remote_compression_ratio_threshold", 2.4)
                condition = self.config.get("remote_condition_on_previous_text", True)
                silence_thr = self.config.get("remote_hallucination_silence_threshold", 2.0)
                rep_pen = self.config.get("remote_repetition_penalty", 1.0)
                no_repeat_ngram = self.config.get("remote_no_repeat_ngram_size", 0)
                
                # Selection of replacements and normalization
                repl_str = self.config.get("remote_word_replacements", "")
                smart_norm = self.config.get("remote_smart_normalization", False)
            else:
                lang = self.config.get("language", "auto")
                model = self.config.get("model_name", "base")
                engine = self.config.get("engine", "openai-whisper")
                beam = self.config.get("beam_size", 5)
                temp = self.config.get("temperature", 0.0)
                prompt = self.config.get("initial_prompt", "")
                no_speech = self.config.get("no_speech_threshold", 0.6)
                logprob = self.config.get("logprob_threshold", -1.0)
                compression = self.config.get("compression_ratio_threshold", 2.4)
                condition = self.config.get("condition_on_previous_text", True)
                silence_thr = self.config.get("hallucination_silence_threshold", 2.0)
                rep_pen = self.config.get("repetition_penalty", 1.0)
                no_repeat_ngram = self.config.get("no_repeat_ngram_size", 0)
                
                repl_str = self.config.get("word_replacements", "")
                smart_norm = self.config.get("smart_normalization", False)

            text = transcriber.transcribe(
                audio, 
                model_name=model,
                engine=engine,
                language=lang,
                beam_size=beam,
                temperature=temp,
                initial_prompt=prompt,
                no_speech_threshold=no_speech,
                logprob_threshold=logprob,
                compression_ratio_threshold=compression,
                condition_on_previous_text=condition,
                hallucination_silence_threshold=silence_thr,
                repetition_penalty=rep_pen,
                no_repeat_ngram_size=no_repeat_ngram,
                smart_normalization=smart_norm,
                word_replacements=repl_str,
                cancellation_callback=lambda: self.abort_transcription
            )
            
            if text is None:
                print("Transcription cancelled, skipping output.")
                self.status_changed.emit("idle")
                return
            
            # 🔹 Post-processing (still applied here for safety or for local mode)
            # If it was remote, the worker already did it, but doing it again with same rules is idempotent.
            from app.utils import apply_replacements, apply_smart_normalization
            
            text = apply_replacements(text, repl_str)
            if smart_norm:
                text = apply_smart_normalization(text)
                
            print(f"Transcription finished: '{text}'")
            trans_dur = time.time() - self.transcription_start_time
            self.floating_ui.set_durations(transcription=trans_dur)
            self.transcription_start_time = 0
            self.status_changed.emit("done")
            output_transcription(
                text, 
                mode=self.config["output_mode"], 
                delay=self.config["paste_delay"],
                cleanup=self.config["backspace_cleanup"],
                add_space=self.config.get("add_space", False),
                add_newline=self.config.get("add_newline", False)
            )
        except Exception as e:
            print(f"Process Audio Error: {e}")
            self.status_changed.emit("idle")
        finally:
            self.last_action_time = time.time()

    def check_idle(self):
        if not self.config.get("unload_idle", False):
            return
            
        if self.recorder.recording or self.is_processing or not self.audio_queue.empty():
            return
            
        idle_time = self.config.get("idle_time_minutes", 5) * 60
        if (time.time() - self.last_action_time) > idle_time:
            if self.transcriber.model is not None:
                print(f"Application idle for >{self.config.get('idle_time_minutes', 5)} min. Unloading model to save RAM.")
                self.transcriber.unload_model()

    def show_settings(self):
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.activateWindow()
            self.settings_dialog.raise_()
            return

        self.settings_dialog = SettingsDialog()
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            self.settings_dialog.setWindowIcon(QIcon(icon_path))
        self.settings_dialog.opacity_preview.connect(self.floating_ui.setWindowOpacity)
        self.settings_dialog.accepted.connect(self.apply_settings)
        self.settings_dialog.show()
        self.settings_dialog.activateWindow()

    def apply_settings(self):
        # Reload config
        self.config = load_config()
        set_ui_lang(self.config["ui_language"])
        
        # Refresh UI text
        self.floating_ui.status_labels = {
            "idle": tr("ready"),
            "loading": tr("loading"),
            "recording": tr("recording"),
            "processing": tr("processing"),
            "done": tr("done")
        }
        self.floating_ui.set_status(self.floating_ui.status) # Forces text update
        
        # Refresh Tray Menu
        self.tray.settings_action.setText(tr("settings"))
        self.tray.log_action.setText(tr("show_logs"))
        self.tray.restart_action.setText(tr("restart"))
        self.tray.about_action.setText(tr("about"))
        self.tray.exit_action.setText(tr("exit"))

        self.floating_ui.setWindowOpacity(self.config.get("opacity", 0.9))
        self.floating_ui.set_always_on_top(self.config.get("always_on_top", True))
        self.floating_ui.ui_design = self.config.get("ui_design", "classic")
        
        # If pre-recording was ON, we might need to restart/update the stream
        self.recorder.set_pre_buffer(self.config.get("pre_record_seconds", 0.0))
        if self.config.get("pre_record_seconds", 0.0) > 0:
             if self.recorder.stream is None:
                 self.recorder._start_stream(device=self.config["selected_mic"])
        else:
             if not self.recorder.recording:
                 self.recorder.close()
        
        self.listener.stop()
        self.listener.start(self.config["hotkey"])

        # If model, engine, or gpu changed, reload the model instead of restarting the app
        if self.transcriber.model_name != self.config["model_name"] or \
           self.transcriber.engine != self.config["engine"] or \
           getattr(self.transcriber, 'use_gpu', False) != self.config.get("use_gpu", False):
            print("Model/Engine/GPU changed. Reloading model dynamically...")
            self.load_model_async(
                self.config["model_name"], 
                self.config.get("engine", "openai-whisper"),
                self.config.get("use_gpu", False)
            )

    def show_floating_context_menu(self, pos):
        self.tray.menu.exec(self.floating_ui.mapToGlobal(pos))

    def on_tray_activated(self, reason):
        if reason == AppTrayIcon.Trigger:
            self.floating_ui.bring_to_front()


    def on_window_geometry_change(self):
        pos = self.floating_ui.pos()
        size = self.floating_ui.size()
        self.config["window_pos"] = [pos.x(), pos.y()]
        self.config["window_size"] = [size.width(), size.height()]
        save_config(self.config)



    def show_logs(self):
        self.log_window.show()
        self.log_window.activateWindow()

    def show_about(self):
        title = tr("about_title")
        content = tr("about_text").format(version=self.version)
        msg = QMessageBox(None)
        msg.setWindowTitle(title)
        msg.setText(content)
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            msg.setWindowIcon(QIcon(icon_path))
            # Set a nice large icon in the dialog body too
            msg.setIconPixmap(QIcon(icon_path).pixmap(64, 64))
        msg.exec()

    def check_system_sleep(self):
        current_time = time.time()
        # If the gap is significantly larger than the timer interval (e.g., > 30s for a 10s timer)
        if (current_time - self.last_check_time) > 40:
            print("System resume detected! Restarting app for fresh state...")
            self.restart_app()
        self.last_check_time = current_time

    def restart_services(self):
        # We now simply restart the whole process for maximum reliability
        self.restart_app()

    def restart_app(self):
        """Full process restart."""
        print("Restarting Voysix process...")
        try:
            if self.recorder.recording:
                self.recorder.stop()
        except: pass
        try:
            self.listener.stop()
        except: pass
        try:
            self.tray.hide()
        except: pass
        
        # Determine arguments
        # If we are running from .exe, sys.executable is the exe.
        # If we are running from python main.py, it's python.exe.
        args = sys.argv[1:]
        print(f"Executing: {sys.executable} {args}")
        os.execl(sys.executable, sys.executable, *sys.argv)

    def _background_discovery(self):
        if not self.config.get("remote_mode", False):
            return
            
        def target():
            try:
                from app.worker_client import WorkerClient
                node = self.config.get("remote_worker_name")
                manual = self.config.get("remote_worker_url")
                key = self.config.get("remote_api_key")
                ts_key = self.config.get("tailscale_auth_key")
                
                if not node and not manual:
                    return

                client = WorkerClient(node, api_key=key, manual_url=manual)
                
                # 1. Brief Tailscale check (non-blocking)
                ts = client.get_tailscale_status(auth_key=ts_key)
                if ts["connected"]:
                    print(f"Background Check: Tailscale is ONLINE ({ts['state']})")
                else:
                    # Don't spam restart, just log status
                    print(f"Background Check: Tailscale is OFFLINE ({ts['state']})")
                
                # 2. Worker Discovery
                url = client.discover()
                if url:
                    if client.check_health():
                        if not self.worker_url:
                            print(f"✨ Remote worker DISCOVERED at {url}")
                        self.worker_url = url
                        self.worker_info = client.get_info()
                    else:
                        if self.worker_url:
                             print(f"⚠️ Remote worker at {url} became UNHEALTHY.")
                        self.worker_url = None
                else:
                    if self.worker_url:
                        print("⚠️ Remote worker LOST in network.")
                    self.worker_url = None
                    
            except Exception as e:
                print(f"Background discovery error: {e}")
                
        threading.Thread(target=target, daemon=True).start()

    def quit(self):
        print("Exiting application...")
        if self.recorder.recording:
            self.recorder.stop()
        self.recorder.close()
        self.listener.stop()
        self.tray.hide()
        # Force terminate all threads and process
        os._exit(0)

def main():
    # --- Single Instance Check (Windows) ---
    if os.name == 'nt':
        mutex_name = "VoysixAppInstanceMutex_Unique_2025"
        # We store the handle in a global to prevent it from being garbage collected
        global _app_mutex
        _app_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
            # Another instance is already running
            # We try to show a simple message box to the user
            try:
                # 0x40 is MB_ICONINFORMATION, 0 is MB_OK
                ctypes.windll.user32.MessageBoxW(0, 
                    "Another instance of Voysix is already running.\nCheck your system tray icon.\n\n"
                    "Приложение Voysix уже запущено.\nПроверьте иконку в системном трее.", 
                    "Voysix", 
                    0x40 | 0x0)
            except:
                pass
            sys.exit(0)
    # ---------------------------------------

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Initialize COM for the main thread once
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception as e:
        print(f"COM Init Warning: {e}")
    
    icon_path = get_resource_path(os.path.join("assets", "icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    controller = AppController()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
