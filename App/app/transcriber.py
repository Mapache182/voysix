import os
import torch
import numpy as np
import gc
import threading

class WhisperTranscriber:
    def __init__(self, model_name="base", engine="openai-whisper", use_gpu=False):
        self.model_name = model_name
        self.engine = engine
        self.use_gpu = use_gpu
        self.download_root = os.path.join(os.environ.get("APPDATA", "."), "voysix", "models")
        os.makedirs(self.download_root, exist_ok=True)
        
        self.model = None
        self.device = "cpu"
        if self.use_gpu:
            try:
                from app.gpu_manager import check_gpu_available
                if check_gpu_available():
                    self.device = "cuda"
            except:
                pass
        
        self.loading = False
        self._lock = threading.Lock()

    def load_model(self, model_name=None, engine=None, use_gpu=None):
        with self._lock:
            if use_gpu is not None:
                self.use_gpu = use_gpu
                if self.use_gpu:
                    try:
                        from app.gpu_manager import check_gpu_available
                        if check_gpu_available():
                            self.device = "cuda"
                        else:
                            self.device = "cpu"
                    except:
                        self.device = "cpu"
                else:
                    self.device = "cpu"

            if model_name:
                # If everything is same, skip
                if self.model is not None and self.model_name == model_name and (engine is None or self.engine == engine):
                    print(f"Model {model_name} already loaded, skipping.")
                    return
                self.model_name = model_name
            if engine:
                self.engine = engine
            
            print(f"--- Model Change Requested: {self.model_name} ({self.engine}) on {self.device} ---")
            self.loading = True
            
            # 🔹 1. Explicitly clear previous model to free memory/VRAM
            if self.model is not None:
                print("Releasing previous model...")
                try:
                    del self.model
                    self.model = None
                except Exception as e:
                    print(f"Error releasing model: {e}")
                
                # Force garbage collection
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print("Previous model released.")

            try:
                print(f"Loading '{self.model_name}' on {self.device}...")
                if self.engine == "faster-whisper":
                    print("Importing faster_whisper...")
                    from faster_whisper import WhisperModel
                    
                    compute_type = "float16" if self.device == "cuda" else "float32"
                    print(f"Initializing Faster-Whisper ({self.model_name}, {compute_type})...")
                    
                    self.model = WhisperModel(
                        self.model_name, 
                        device=self.device, 
                        compute_type=compute_type, 
                        download_root=self.download_root
                    )
                else:
                    print("Importing openai-whisper...")
                    import whisper
                    print(f"Calling whisper.load_model ({self.model_name})...")
                    self.model = whisper.load_model(
                        self.model_name, 
                        device=self.device, 
                        download_root=self.download_root
                    )
                print("Model loaded successfully.")
            except Exception as e:
                print(f"CRITICAL Error loading model: {e}")
                self.model = None
                raise e
            finally:
                self.loading = False

    def unload_model(self):
        with self._lock:
            if self.model is not None:
                print("Unloading model to free RAM...")
                try:
                    del self.model
                    self.model = None
                except Exception as e:
                    print(f"Error unloading model: {e}")
                
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print("Model unloaded successfully.")
            else:
                print("Model was not loaded, nothing to unload.")

    def transcribe(self, audio_np, model_name="base", engine="openai-whisper", language="auto", beam_size=5, temperature=0.0, initial_prompt=None, 
                  no_speech_threshold=0.6, logprob_threshold=-1.0, 
                  compression_ratio_threshold=2.4, condition_on_previous_text=True,
                  hallucination_silence_threshold=2.0, repetition_penalty=1.0, no_repeat_ngram_size=0,
                  cancellation_callback=None):
        # Use lock to ensure we don't transcribe while loading
        with self._lock:
            if self.model is None:
                return "Model not loaded."
            
            try:
                lang_code = None if language == "auto" else language
                
                if self.engine == "faster-whisper":
                    segments, info = self.model.transcribe(
                        audio_np,
                        language=lang_code,
                        beam_size=beam_size,
                        temperature=temperature,
                        initial_prompt=initial_prompt,
                        no_speech_threshold=no_speech_threshold,
                        log_prob_threshold=logprob_threshold,
                        compression_ratio_threshold=compression_ratio_threshold,
                        condition_on_previous_text=condition_on_previous_text,
                        hallucination_silence_threshold=hallucination_silence_threshold,
                        repetition_penalty=repetition_penalty,
                        no_repeat_ngram_size=no_repeat_ngram_size,
                        vad_filter=True
                    )
                    full_text = ""
                    for segment in segments:
                        if cancellation_callback and cancellation_callback():
                            print("Transcription ABORTED during generation.")
                            return None
                        full_text += segment.text
                    return full_text.strip()
                else:
                    # OpenAI Whisper is harder to interrupt mid-call,
                    # but we will check after if we should discard results.
                    result = self.model.transcribe(
                        audio_np, 
                        fp16=(self.device == "cuda"),
                        language=lang_code,
                        beam_size=beam_size,
                        best_of=beam_size if temperature > 0 else 1,
                        temperature=temperature,
                        initial_prompt=initial_prompt,
                        no_speech_threshold=no_speech_threshold,
                        logprob_threshold=logprob_threshold,
                        compression_ratio_threshold=compression_ratio_threshold,
                        condition_on_previous_text=condition_on_previous_text
                    )
                    if cancellation_callback and cancellation_callback():
                        return None
                    return result.get("text", "").strip()
            except Exception as e:
                print(f"Transcription error: {e}")
                return f"Error: {e}"


class RemoteWhisperTranscriber:
    def __init__(self, node_name, api_key=None, manual_url=None):
        from app.worker_client import WorkerClient
        self.client = WorkerClient(node_name, api_key=api_key, manual_url=manual_url)
        self.loading = False
        self.model_name = "remote"
        self.engine = "remote"

    def load_model(self, *args, **kwargs):
        # Discovery is fast, but let's do it
        print(f"Discovering remote worker: {self.client.node_name}...")
        url = self.client.discover()
        if url:
            print(f"Remote worker found at {url}")
            return True
        else:
            print("Remote worker not found.")
            return False

    def transcribe(self, audio_np, model_name="base", engine="openai-whisper", language="auto", beam_size=5, temperature=0.0, initial_prompt=None, 
                  no_speech_threshold=0.6, logprob_threshold=-1.0, 
                  compression_ratio_threshold=2.4, condition_on_previous_text=True,
                  hallucination_silence_threshold=2.0, repetition_penalty=1.0, no_repeat_ngram_size=0,
                  cancellation_callback=None):
        # The remote client might not support interruption easily, but we'll check after
        result = self.client.transcribe(
            audio_np, model_name, engine, language, beam_size, temperature, initial_prompt,
            no_speech_threshold=no_speech_threshold, logprob_threshold=logprob_threshold,
            compression_ratio_threshold=compression_ratio_threshold, 
            condition_on_previous_text=condition_on_previous_text,
            hallucination_silence_threshold=hallucination_silence_threshold,
            repetition_penalty=repetition_penalty,
            no_repeat_ngram_size=no_repeat_ngram_size
        )
        if cancellation_callback and cancellation_callback():
            return None
        return result
