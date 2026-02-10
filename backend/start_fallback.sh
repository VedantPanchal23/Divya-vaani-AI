#!/bin/sh
set -e

echo "[FALLBACK] start.sh failed or did not run."
echo "[FALLBACK] Listing /app and /app/backend:"
ls -la /app
ls -la /app/backend

echo "[FALLBACK] Sleeping forever so logs stay open."
while true; do sleep 3600; done
