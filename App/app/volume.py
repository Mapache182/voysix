try:
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    WINDOWS_AUDIO = True
except (ImportError, Exception):
    WINDOWS_AUDIO = False

import sys
import subprocess
import os

MACOS_AUDIO = sys.platform == "darwin"

import threading

class VolumeManager:
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._volume_ptr = None
        self._interface = None
        self._com_initialized = False

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    def _init_com(self):
        """Internal: ensure COM and interface are ready (Windows) or check macOS."""
        if MACOS_AUDIO:
            return True # No special init needed for osascript
            
        if not WINDOWS_AUDIO:
            return False
            
        if self._volume_ptr and self._interface:
            return True
            
        try:
            if not self._com_initialized:
                try:
                    comtypes.CoInitialize()
                    self._com_initialized = True
                except:
                    pass
            
            devices = AudioUtilities.GetMicrophone()
            if not devices:
                return False
            
            self._interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._volume_ptr = comtypes.cast(self._interface, comtypes.POINTER(IAudioEndpointVolume))
            return True
        except Exception as e:
            if sys.platform == "win32":
                print(f"VolumeManager Init Error: {e}")
            self._cleanup()
            return False

    def _cleanup(self):
        # We don't call CoUninitialize to stay safe on main thread,
        # but we clear the pointers. comtypes handles .Release()
        self._volume_ptr = None
        self._interface = None

    def get_volume(self):
        with self._lock:
            if MACOS_AUDIO:
                try:
                    result = subprocess.check_output(["osascript", "-e", "input volume of (get volume settings)"]).decode().strip()
                    return int(result)
                except Exception as e:
                    print(f"macOS Volume Get Error: {e}")
                    return 50

            if not self._init_com():
                return 50
            try:
                val = self._volume_ptr.GetMasterVolumeLevelScalar()
                return int(val * 100)
            except Exception as e:
                print(f"Volume Get Error (retrying): {e}")
                self._cleanup()
                if self._init_com():
                    try:
                        return int(self._volume_ptr.GetMasterVolumeLevelScalar() * 100)
                    except: pass
                return 50

    def set_volume(self, level):
        with self._lock:
            if MACOS_AUDIO:
                try:
                    subprocess.run(["osascript", "-e", f"set volume input volume {level}"], check=True)
                except Exception as e:
                    print(f"macOS Volume Set Error: {e}")
                return

            if not self._init_com():
                return
            try:
                self._volume_ptr.SetMute(0, None)
                self._volume_ptr.SetMasterVolumeLevelScalar(level / 100.0, None)
            except Exception as e:
                print(f"Volume Set Error (retrying): {e}")
                self._cleanup()
                if self._init_com():
                    try:
                        self._volume_ptr.SetMute(0, None)
                        self._volume_ptr.SetMasterVolumeLevelScalar(level / 100.0, None)
                    except: pass

def get_mic_volume():
    return VolumeManager.get_instance().get_volume()

def set_mic_volume(level):
    VolumeManager.get_instance().set_volume(level)
