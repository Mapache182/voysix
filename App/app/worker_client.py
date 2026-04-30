import os
import subprocess
import json
import requests
import numpy as np
import io
import wave
import time

class WorkerClient:
    def __init__(self, node_name=None, api_key=None, manual_url=None):
        self.node_name = node_name
        self.api_key = api_key
        self.base_url = manual_url
        self.worker_info = None

    def _get_headers(self):
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_tailscale_cmd(self):
        """Returns the full path to tailscale executable or just 'tailscale' if it's in PATH."""
        if sys.platform == "win32":
            # Check relative to script/exe first (if bundled or downloaded to app folder)
            import sys as sys_win
            base_dir = os.path.dirname(sys_win.executable) if getattr(sys_win, 'frozen', False) else os.path.dirname(os.path.dirname(__file__))
            
            # Common installation paths on Windows
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")
                local_app_data = os.path.join(user_profile, "AppData", "Local")

            common_paths = [
                os.path.join(base_dir, "tailscale", "tailscale.exe"), # Local bundle
                os.path.join(base_dir, "tailscale.exe"),               # Local root
                os.path.join(program_files, "Tailscale", "tailscale.exe"),
                os.path.join(program_files_x86, "Tailscale", "tailscale.exe"),
                os.path.join(local_app_data, "Programs", "Tailscale", "tailscale.exe"), # User-only installs
            ]
            for p in common_paths:
                if os.path.exists(p):
                    return p
        elif sys.platform == "darwin":
            common_paths = [
                "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
                "/usr/local/bin/tailscale",
                "/opt/homebrew/bin/tailscale"
            ]
            for p in common_paths:
                if os.path.exists(p):
                    return p
        
        return "tailscale"
    
    def _run_tailscale_cmd(self, args):
        """Runs a tailscale command with proper quoting on Windows."""
        cmd = self._get_tailscale_cmd()
        
        # If we have a full path, use it directly. 
        # If it's just "tailscale", it relies on PATH.
        try:
            # shell=True is required on Windows to find 'tailscale' in PATH if not absolute.
            # On macOS/Linux, it's generally better to use shell=False with a list.
            use_shell = (sys.platform == "win32")
            
            return subprocess.run(
                [cmd] + args,
                capture_output=True,
                text=True,
                check=False,
                shell=use_shell
            )
        except Exception as e:
            # Fallback for unexpected subprocess errors
            from dataclasses import dataclass
            @dataclass
            class MockResult:
                stdout: str
                stderr: str
                returncode: int
            return MockResult("", str(e), 1)

    def restart_tailscale_service(self, auth_key=None):
        """Attempts to restart the Tailscale service or run 'up' with elevation."""
        if sys.platform == "win32":
            import ctypes
            try:
                cmd_path = self._get_tailscale_cmd()
                commands = ["net stop tailscale", "net start tailscale"]
                if auth_key:
                    quoted_exe = f'"{cmd_path}"' if ' ' in cmd_path else cmd_path
                    commands.append(f'{quoted_exe} up --authkey {auth_key} --reset')
                
                params = f'/c "{" & ".join(commands)}"'
                res = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", params, None, 1)
                if res > 32:
                    return True, "Restart command sent."
                else:
                    return False, f"Elevation failed ({res})"
            except Exception as e:
                return False, str(e)
        
        elif sys.platform == "darwin":
            try:
                cmd_path = self._get_tailscale_cmd()
                # On macOS, we use osascript to run commands as root
                # We'll try to run 'up' with the key
                if auth_key:
                    script = f'do shell script "{cmd_path} up --authkey {auth_key} --reset" with administrator privileges'
                    subprocess.run(["osascript", "-e", script], check=True)
                    return True, "Tailscale 'up' command executed."
                else:
                    # Just a restart of the app/CLI isn't easily unified on Mac without knowing if it's App Store or CLI
                    return False, "Auth key required for elevated macOS operations."
            except Exception as e:
                return False, str(e)

        return False, "Not supported on this OS"
    
    def get_tailscale_status(self, auth_key=None):
        try:
            # 1. Check current status
            print(f"DEBUG [Tailscale]: Running status check...")
            result = self._run_tailscale_cmd(["status", "--json"])

            if not result.stdout:
                print(f"DEBUG [Tailscale]: Empty stdout! Stderr: {result.stderr or 'None'}")
                if "not recognized" in result.stderr or "not found" in result.stderr:
                    print("Hint: Tailscale might not be installed or not added to PATH.")
                return {
                    "connected": False,
                    "state": "Not Found / Not Running",
                    "error": result.stderr
                }
            
            # log a snippet for debugging if it's very short or looks broken
            if len(result.stdout) < 50:
                 print(f"DEBUG [Tailscale]: Short JSON output: {result.stdout}")

            try:
                data = json.loads(result.stdout)
            except Exception as je:
                print(f"DEBUG: Failed to parse Tailscale JSON. Output start: {result.stdout[:100]}")
                return {
                    "connected": False,
                    "state": "Parse Error",
                    "error": str(je)
                }

            self_node = data.get("Self", {})
            state = data.get("BackendState", "Unknown")
            node_name = self_node.get("HostName", "Unknown")
            dns_name = self_node.get("DNSName", "")
            ips = self_node.get("TailscaleIPs", [])
            
            print(f"DEBUG: Tailscale Status Check: state='{state}', hostname='{node_name}', IPs='{ips}'")

            # 2. Fallback: if auth_key is None but api_key looks like a TS Key
            if not auth_key and self.api_key and self.api_key.startswith("tskey-"):
                print("DEBUG: Hint: Using 'Remote API Key' as Tailscale Auth Key (fallback).")
                auth_key = self.api_key

            # 3. If not running and we have an auth key, try to 'up' it
            # CRITICAL: If state is 'NoState' and Health says "Starting", we usually wait.
            # HOWEVER, if Health specifically says "You are logged out", we must try 'up' anyway.
            health_list = data.get("Health") or []
            health_msg = ", ".join(health_list).lower()
            is_starting = (state == "NoState" and health_list) or "starting" in state.lower()
            needs_login = state == "NeedsLogin" or "logged out" in health_msg or "login" in health_msg

            if state != "Running" and auth_key and (not is_starting or needs_login):
                print(f"Tailscale state is '{state}'. Attempting 'tailscale up' with provided Auth Key...")
                try:
                    # 🔹 Using --reset helps when the internal state is corrupted or "stuck"
                    print(f"DEBUG [Tailscale]: Executing up --reset ...")
                    up_result = self._run_tailscale_cmd(["up", "--authkey", auth_key, "--reset"])
                    print(f"DEBUG [Tailscale]: up --reset finished with code {up_result.returncode}")
                    
                    if up_result.returncode == 0:
                        print("Tailscale 'up' command sent successfully. Waiting for state transition...")
                        # On Windows, transitions can take 10+ seconds. We wait a bit and re-check once.
                        time.sleep(6) 
                        return self.get_tailscale_status(auth_key=None) 

                    else:
                        print(f"Tailscale 'up' failed (exit code {up_result.returncode}). Stderr: {up_result.stderr}")
                        if "not permitted" in up_result.stderr.lower() or "admin" in up_result.stderr.lower():
                            print("CRITICAL: Tailscale requires Administrator privileges to log in on Windows.")
                            state = "Needs Elevation"
                except Exception as e:
                    print(f"Error during 'tailscale up': {e}")

            if state != "Running":
                print(f"Tailscale is NOT running (current state: {state}).")
                if state == "NeedsLogin":
                    print("Hint: You need to log in to Tailscale by running 'tailscale up' in your command line or providing an Auth Key.")
                elif state == "Stopped":
                    print("Hint: Tailscale service is stopped. Try starting it from the system tray or command line.")
                elif is_starting:
                    health_msg = ", ".join(data.get("Health") or ["Starting..."])
                    print(f"Tailscale is currently starting: {health_msg}")
                    state = f"Starting... ({health_msg})"
                elif state == "NoState":
                    print("Tailscale is in NoState. This often means the service is still initializing.")

            return {
                "connected": state == "Running",
                "state": state,
                "node_name": node_name,
                "dns_name": dns_name
            }
        except Exception as e:
            print(f"Tailscale Check CRITICAL Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "connected": False,
                "state": "Tailscale Error",
                "error": str(e)
            }


    def discover(self, node_name=None):
        if self.base_url:
            print(f"DEBUG: Discovery using manual_url='{self.base_url}'")
            return self.base_url

        if node_name:
            self.node_name = node_name

        if not self.node_name:
            print("Discovery: No worker node name provided.")
            return None

        print(f"DEBUG: Discovery: Searching for worker node '{self.node_name}' in Tailscale network...")

        try:
            # Discover via Tailscale
            print(f"DEBUG: Running discovery via Tailscale...")
            result = self._run_tailscale_cmd(["status", "--json"])

            if not result.stdout:
                print(f"Discovery Error: No output from '{cmd} status'. Stderr: {result.stderr}")
                return None

            data = json.loads(result.stdout)

            # --- Check State ---
            state = data.get("BackendState", "Unknown")
            if state != "Running":
                health = data.get("Health") or []
                is_starting = state == "NoState" and health
                if is_starting:
                    print(f"Discovery: Tailscale is still starting ({', '.join(health)}). Waiting...")
                    return None
            
            # --- Check Self ---
            self_node = data.get("Self") or {}

            host_name_self = self_node.get("HostName", "").lower()
            dns_name_self = self_node.get("DNSName", "").lower()
            print(f"DEBUG: Checking self: HostName='{host_name_self}', DNSName='{dns_name_self}'")

            if (self.node_name.lower() in host_name_self) or (self.node_name.lower() in dns_name_self):
                ips = self_node.get("TailscaleIPs", [])
                if ips:
                    self.base_url = f"http://{ips[0]}:8000"
                    print(f"Worker Found (SELF): Found '{host_name_self}' at {self.base_url}")
                    return self.base_url

            # --- Check Peers ---
            peers = data.get("Peer") or {}

            available_peers = []
            for peer_id, peer_info in peers.items():
                host_name = peer_info.get("HostName", "").lower()
                dns_name = peer_info.get("DNSName", "").lower()
                available_peers.append(f"{host_name} ({peer_info.get('Online', False)})")

                if (self.node_name.lower() in host_name) or (self.node_name.lower() in dns_name):
                    ips = peer_info.get("TailscaleIPs", [])
                    if ips:
                        self.base_url = f"http://{ips[0]}:8000"
                        print(f"Worker Found: Node '{host_name}' at {self.base_url}")
                        return self.base_url

            print(f"Worker Node '{self.node_name}' NOT FOUND in Tailscale peers.")
            if available_peers:
                print(f"Available network peers: {', '.join(available_peers)}")
            else:
                if state == "Running":
                    print("Tailscale list of peers is empty. Are you connected to the right tailnet?")
                else:
                    print(f"Tailscale is not ready (State: {state}). Discovery aborted.")

        except Exception as e:
            if not getattr(self, "_tailscale_error_shown", False):
                print(f"Tailscale discovery error: {e}")
                import traceback
                traceback.print_exc()
                self._tailscale_error_shown = True

        return None

    def check_health(self):
        if not self.base_url:
            print("DEBUG: check_health called but base_url is None")
            return False
        try:
            print(f"DEBUG: Health check request to {self.base_url}/health")
            resp = requests.get(f"{self.base_url}/health", headers=self._get_headers(), timeout=5)
            print(f"DEBUG: Health check status_code={resp.status_code}")
            if resp.status_code == 200:
                is_ok = resp.json().get("status") == "ok"
                print(f"DEBUG: Health check status field='{resp.json().get('status')}' -> is_ok={is_ok}")
                return is_ok
            else:
                print(f"DEBUG: Health check failed with status {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"DEBUG: Health check Exception: {e}")
            pass
        return False

    def get_info(self):
        if not self.base_url:
            return None
        try:
            headers = self._get_headers()
            health = requests.get(f"{self.base_url}/health", headers=headers, timeout=2).json()
            config = requests.get(f"{self.base_url}/config", headers=headers, timeout=2).json()
            caps = requests.get(f"{self.base_url}/capabilities", headers=headers, timeout=2).json()
            return {
                "health": health,
                "config": config,
                "capabilities": caps,
                "url": self.base_url
            }
        except:
            return None

    def transcribe(self, audio_np, model_name="base", engine="openai-whisper", language="auto", beam_size=5, temperature=0.0, initial_prompt=None,
                  no_speech_threshold=0.6, logprob_threshold=-1.0, compression_ratio_threshold=2.4, condition_on_previous_text=True,
                  hallucination_silence_threshold=2.0, repetition_penalty=1.0, no_repeat_ngram_size=0,
                  smart_normalization=False, word_replacements=""):
        if not self.base_url:
            return "Worker not connected."

        try:
            # 🔹 Prepare data for worker config
            worker_cfg = {
                "model": model_name,
                "engine": engine,
                "language": language,
                "beam_size": beam_size,
                "temperature": temperature,
                "initial_prompt": initial_prompt,
                "no_speech_threshold": no_speech_threshold,
                "logprob_threshold": logprob_threshold,
                "compression_ratio_threshold": compression_ratio_threshold,
                "condition_on_previous_text": condition_on_previous_text,
                "hallucination_silence_threshold": hallucination_silence_threshold,
                "repetition_penalty": repetition_penalty,
                "no_repeat_ngram_size": no_repeat_ngram_size,
                "smart_normalization": smart_normalization,
                "word_replacements": word_replacements
            }
            headers = self._get_headers()
            requests.post(f"{self.base_url}/config", json=worker_cfg, headers=headers, timeout=2)

            # 🔹 Convert numpy to bytes (Packaging)
            from app.settings import load_config
            cfg = load_config()
            audio_format = cfg.get("remote_audio_format", "flac")

            t_pkg_start = time.time()
            wav_buf = io.BytesIO()
            
            # Try compression if selected
            success = False
            if audio_format in ["flac", "ogg"]:
                import tempfile
                # On Windows, libsndfile 1.2.0+ can crash with Stack Overflow (0xc00000fd)
                # when writing FLAC to a virtual file/buffer (io.BytesIO).
                # Using a physical temporary file bypasses the problematic virtual I/O stack.
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{audio_format}")
                try:
                    os.close(tmp_fd)
                    import soundfile as sf
                    # Ensure data is in a format soundfile likes (int16 avoids some internal libsndfile stack usage)
                    data_int16 = np.clip(audio_np * 32767, -32768, 32767).astype(np.int16)
                    
                    # Use a context manager and chunked write to minimize stack depth during any single call
                    # On Windows, libsndfile 1.2.x can crash with Stack Overflow (0xc00000fd)
                    # especially when handling float32 or large continuous blocks.
                    with sf.SoundFile(tmp_path, mode='w', samplerate=16000, channels=1, format=audio_format.upper()) as f:
                        chunk_size = 16000 # 1 second chunks
                        for i in range(0, len(data_int16), chunk_size):
                            f.write(data_int16[i:i+chunk_size])
                    
                    with open(tmp_path, "rb") as f:
                        wav_buf.write(f.read())
                    success = True
                except Exception as e:
                    print(f"DEBUG: Failed to encode {audio_format}, falling back to wav: {e}")
                finally:
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except:
                        pass
                    
            if not success:
                audio_format = "wav" # Fallback
                wav_buf = io.BytesIO() # Reset buffer
                with wave.open(wav_buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2) # 16-bit
                    wf.setframerate(16000)
                    audio_int16 = np.clip(audio_np * 32767, -32768, 32767).astype(np.int16)
                    wf.writeframes(audio_int16.tobytes())

            wav_buf.seek(0)
            t_pkg_dur = time.time() - t_pkg_start
            print(f"DEBUG: Audio packaging ({audio_format}) took {t_pkg_dur:.3f}s. Size: {len(wav_buf.getvalue())/1024:.1f} KB")

            # 🔹 Sending to /transcribe (Network + Backend Processing)
            t_net_start = time.time()
            # We always send the file named "audio.wav" to safely bypass backend extension checks, 
            # ffmpeg under the hood will read the magic header bytes and decode it correctly regardless!
            files = {"file": ("audio.wav", wav_buf, f"audio/{audio_format}")}
            # (connect_timeout, read_timeout)
            resp = requests.post(f"{self.base_url}/transcribe", files=files, headers=headers, timeout=(3, 60))
            t_net_dur = time.time() - t_net_start
            
            if resp.status_code == 200:
                text = resp.json().get("text", "").strip()
                print(f"DEBUG: Remote request took {t_net_dur:.3f}s (Response length: {len(text)})")
                return text
            else:
                print(f"DEBUG: Remote request failed after {t_net_dur:.3f}s with status {resp.status_code}")
                return f"Worker error: {resp.status_code}"
        except requests.exceptions.Timeout:
             return "Remote transcription error: Connection timed out. Falling back."
        except requests.exceptions.ConnectionError:
             return "Remote transcription error: Connection failed. Falling back."
        except Exception as e:
            return f"Remote transcription error: {e}"
