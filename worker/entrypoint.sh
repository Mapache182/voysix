#!/bin/sh

set -e

echo "Starting Tailscale..."

# Запуск tailscaled
tailscaled &

sleep 2

# Подключение к сети
tailscale up --authkey=${TS_AUTHKEY} --hostname=${TS_HOSTNAME}

echo "Tailscale connected"

# Запуск API
echo "Starting FastAPI..."

uvicorn app.main:app --host 0.0.0.0 --port 8000