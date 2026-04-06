#!/bin/sh

# Выходим при любой ошибке
set -e

if [ "$GPU_ENABLED" = "1" ] || command -v nvidia-smi > /dev/null 2>&1; then
    echo "--- [GPU] GPU detected or GPU_ENABLED is set. ---"
    # Проверяем, установлена ли уже версия с CUDA (не +cpu)
    if python3 -c "import torch; exit(0 if torch.cuda.is_available() else 1)"; then
        echo "--- [GPU] CUDA is already available in Torch. Skipping installation. ---"
    else
        echo "--- [GPU] CUDA not found or CPU-only version detected. ---"
        echo "--- [GPU] Installing CUDA-enabled PyTorch... (approx. 3GB) ---"
        pip install --no-cache-dir torch torchaudio --force-reinstall
        echo "--- [GPU] Installation complete. ---"
    fi
    # Указываем приложению использовать куду по умолчанию
    export DEFAULT_DEVICE="cuda"
else
    echo "--- [GPU] GPU not detected and GPU_ENABLED is not set. Using CPU. ---"
fi

echo "--- [0/3] Preparing Persistent Directories ---"
mkdir -p /data/tailscale
mkdir -p /data/models

echo "--- [1/3] Starting Tailscale Daemon ---"

# Запускаем демон в режиме userspace-networking.
# Мы явно указываем путь к файлу состояния на нашем волюме /data.
tailscaled --tun=userspace-networking --socket=/tmp/tailscaled.sock --state=/data/tailscale/tailscaled.state &

# Даем демону время инициализироваться
sleep 3

echo "--- [2/3] Authenticating with Tailscale ---"

# Подключаемся к сети. 
# Используем переменные TS_AUTHKEY и TS_HOSTNAME.
# Если TS_HOSTNAME не задан, используем имя контейнера.
tailscale --socket=/tmp/tailscaled.sock up \
    --authkey="${TS_AUTHKEY}" \
    --hostname="${TS_HOSTNAME:-voysix-worker}" \
    --accept-dns=false \
    --accept-routes=false

echo "--- [3/3] Tailscale is UP, starting FastAPI ---"

# Используем exec, чтобы uvicorn стал основным процессом (PID 1).
# --no-access-log убирает спам от проверок /health.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log --log-level info