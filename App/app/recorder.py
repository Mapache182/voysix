import sounddevice as sd
import numpy as np
import threading
import queue

class AudioRecorder:
    def __init__(self, samplerate=16000, channels=1, on_level_callback=None):
        self.samplerate = samplerate
        self.channels = channels
        self.audio_data = []
        self.recording = False
        self.stream = None
        self.on_level_callback = on_level_callback
        
        # 🔹 Pre-recording (pre-buffer)
        self.pre_buffer = [] 
        self.pre_buffer_max_frames = 0 # 0 means disabled by default
        self._lock = threading.Lock()

    def set_pre_buffer(self, seconds):
        """Configure how many seconds of 'past' audio to keep."""
        with self._lock:
            self.pre_buffer_max_frames = int(seconds * self.samplerate)
            if self.pre_buffer_max_frames <= 0:
                self.pre_buffer = []

    def start(self, device=None):
        """Start the active recording phase."""
        if not self.recording:
            # When starting, we potentially ALREADY have some audio in pre_buffer
            with self._lock:
                # Initialize audio_data with whatever is in the pre_buffer
                # (We concatenate later to avoid keeping large objects in list)
                self.audio_data = list(self.pre_buffer)
                self.recording = True
            
            # If stream is already running (pre-recording), we just continue.
            # If not, we must start it.
            if self.stream is None:
                self._start_stream(device)
            
            print(f"Recorder ACTIVE (pre-buffer contains {len(self.audio_data)} chunks).")

    def _start_stream(self, device=None):
        """Low-level stream initialization with fallbacks."""
        try:
            # Refresh device list
            sd.query_devices()
            
            if device is not None:
                try:
                    info = sd.query_devices(device)
                    if info.get('max_input_channels', 0) == 0:
                        print(f"Device {device} is an OUTPUT device, not a mic. Using default.")
                        device = None
                except:
                    print(f"Device {device} unavailable, using default.")
                    device = None

            # 🔹 Try combinations of Samplerate and Channels
            # Some modern Intel Smart Sound arrays require EXACTLY 4 channels and 48kHz.
            for rate in [16000, 48000, 44100]:
                for ch in [1, 2, 4]:
                    try:
                        if rate != 16000 or ch != 1:
                            print(f"Attempting audio fallback: {rate}Hz, {ch}ch...")
                        
                        self.stream = sd.InputStream(
                            samplerate=rate,
                            channels=ch,
                            dtype=np.float32,
                            device=device,
                            callback=self._callback
                        )
                        self.stream.start()
                        self.samplerate = rate
                        self.channels = ch
                        print(f"Stream started successfully at {rate}Hz, {ch}ch.")
                        return # Success
                    except Exception as e:
                        # Only print if it's not the initial 16k mono attempt or if we are already failing
                        if rate != 16000 or ch != 1:
                            print(f"Fallback ({rate}Hz, {ch}ch) failed: {e}")
        except Exception as e:
            print(f"Critical stream start error: {e}")
            self.recording = False
            self.stream = None

    def _callback(self, indata, frames, time, status):
        try:
            if status:
                print(f"Recorder Status: {status}")
            
            data_copy = indata.copy()
            # Downmix to mono if stereo
            if data_copy.ndim > 1 and data_copy.shape[1] > 1:
                data_copy = np.mean(data_copy, axis=1, keepdims=True)
            
            with self._lock:
                if self.recording:
                    # Active recording: append to main data
                    self.audio_data.append(data_copy)
                
                # In ANY case (if pre-recording enabled), manage the pre-buffer
                if self.pre_buffer_max_frames > 0:
                    self.pre_buffer.append(data_copy)
                    # Simple frame counting instead of total length calculation for speed
                    current_frames = sum([len(c) for c in self.pre_buffer])
                    while len(self.pre_buffer) > 1 and current_frames > self.pre_buffer_max_frames:
                        popped = self.pre_buffer.pop(0)
                        current_frames -= len(popped)

            # Signal level for UI
            if self.on_level_callback:
                rms = np.sqrt(np.mean(data_copy**2))
                self.on_level_callback(rms)
                
        except Exception as e:
            pass

    def stop(self):
        """Stop the active recording and return the data."""
        if self.recording:
            with self._lock:
                self.recording = False
                result_list = list(self.audio_data)
                self.audio_data = []

            print("Recorder STOPPED (active phase).")
            
            # 🔹 If we don't need pre-recording, we should close the stream to release the mic
            if self.pre_buffer_max_frames <= 0:
                self.close()

            # Signal zero level to reset UI
            if self.on_level_callback:
                self.on_level_callback(0.0)

            if result_list:
                audio = np.concatenate(result_list, axis=0).flatten()
                
                # Resample to 16000 if needed (Whisper expects 16k)
                if self.samplerate != 16000:
                    try:
                        print(f"Resampling from {self.samplerate} to 16000Hz...")
                        duration = len(audio) / self.samplerate
                        new_len = int(duration * 16000)
                        audio = np.interp(
                            np.linspace(0, len(audio) - 1, new_len),
                            np.arange(len(audio)),
                            audio
                        ).astype(np.float32)
                    except Exception as e:
                        print(f"Resampling error: {e}")
                
                return audio
        return None

    def close(self):
        """Completely shut down the stream."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            self.recording = False
            self.pre_buffer = []
