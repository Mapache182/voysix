#!/bin/sh

# Выходим при любой ошибке
set -e

echo "--- [1/3] Starting Tailscale Daemon ---"

# Запускаем демон в режиме userspace-networking.
# Это позволяет Tailscale работать без флага --privileged и NET_ADMIN, 
# что делает соединение намного стабильнее в Docker.
# --socket=/tmp/tailscaled.sock явно задает путь к сокету для команд cli.
tailscaled --tun=userspace-networking --socket=/tmp/tailscaled.sock &

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
# Это важно для корректной обработки сигналов остановки контейнера.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000