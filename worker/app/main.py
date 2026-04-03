import os
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
from fastapi.responses import JSONResponse

from .service import transcribe_audio, is_busy
from .config_store import get_config, update_config, get_capabilities

app = FastAPI()

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
        "busy": is_busy()
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
async def transcribe(file: UploadFile = File(...)):
    try:
        content = await file.read()
        text = transcribe_audio(content)

        return {
            "status": "ok",
            "text": text
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )