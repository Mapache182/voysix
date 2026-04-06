import os
import time
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

import threading
from .service import transcribe_audio, is_busy, is_initializing, warm_up
from .config_store import get_config, update_config, get_capabilities

app = FastAPI()

# 🔹 Startup
@app.on_event("startup")
def startup_event():
    # Start model download/warm-up in a background thread
    print("--- [Worker Startup] Initiating model warm-up ---")
    threading.Thread(target=warm_up, daemon=True).start()


# 🔹 Auth Dependency
def verify_api_key(authorization: str = Header(None)):
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        return # Auth disabled
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = authorization.split(" ")[1]
    if token != expected_key:
        raise HTTPException(status_code=403, detail="Forbidden")



# 🔹 Health
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "voysix-worker",
        "busy": is_busy(),
        "initializing": is_initializing()
    }


# 🔹 Config
@app.get("/config")
def read_config():
    return get_config()


@app.post("/config", dependencies=[Depends(verify_api_key)])
def write_config(cfg: dict):
    try:
        update_config(cfg)
        return {"status": "ok", "config": get_config()}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )


# 🔹 Capabilities
@app.get("/capabilities")
def capabilities():
    return get_capabilities()


# 🔹 Transcribe
@app.post("/transcribe", dependencies=[Depends(verify_api_key)])
def transcribe(request: Request, file: UploadFile = File(...)):
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    cfg = get_config()
    model_name = cfg.get("model", "unknown")
    engine = cfg.get("engine", "openai-whisper")

    try:
        content = file.file.read()
        audio_len = len(content) / 32000 # 16kHz, 16bit, mono
        
        print(f"--- [Worker] [{client_ip}] Request received: {audio_len:.2f}s of audio ---")
        print(f"--- [Worker] [{client_ip}] Model: {model_name} | Engine: {engine} ---")

        text = transcribe_audio(content)
        
        duration = time.time() - start_time
        speed_ratio = audio_len / duration if duration > 0 else 0
        print(f"--- [Worker] SUCCESS: Done in {duration:.2f}s ({speed_ratio:.1f}x real-time) ---")

        return {
            "status": "ok",
            "text": text
        }

    except Exception as e:
        print(f"--- [Worker] ERROR: {str(e)} ---")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )