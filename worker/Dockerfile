FROM python:3.12-slim

# Install dependencies (ffmpeg + tailscale)
RUN apt-get update && apt-get install -y ffmpeg curl gnupg && \
    curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null && \
    curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list && \
    apt-get update && apt-get install -y tailscale && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Optimization: Create a folder for models to cache them
RUN mkdir -p /root/.cache/whisper

COPY requirements.txt .

# Install CPU-only PyTorch (MUCH smaller than default CUDA version)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

# Entrypoint will start Tailscale and then FastAPI
ENTRYPOINT ["/bin/sh", "entrypoint.sh"]