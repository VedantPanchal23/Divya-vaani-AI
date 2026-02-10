#!/bin/sh
set -e

echo "=== CONTAINER STARTING ==="
echo "PORT=$PORT"
echo "DATABASE_URL=${DATABASE_URL:+SET}"
echo "STORAGE_DIR=$STORAGE_DIR"
echo "PWD=$(pwd)"
echo "Python: $(python --version 2>&1)"
echo "Uvicorn: $(which uvicorn 2>&1 || echo 'NOT FOUND')"

# ── Fix Railway volume permissions ──
# Railway mounts volumes as root; appuser needs write access
if [ -d "/app/storage" ]; then
    echo "=== Fixing /app/storage permissions ==="
    chown -R appuser:appuser /app/storage 2>/dev/null || true
    chmod -R 755 /app/storage 2>/dev/null || true
    echo "Storage permissions fixed"
fi

echo "=== FILES IN /app ==="
ls -la /app/ 2>&1 | head -20
echo "=== DATA DIR ==="
ls -la /app/data/ 2>&1 | head -10
echo "=== Testing Python import ==="
python -c "
import sys
print('Python import test...')
try:
    from config import settings
    print(f'Config OK - PORT={settings.PORT}')
except Exception as e:
    print(f'Config FAILED: {e}')
try:
    from data.schema import TranscriptChunk
    print('data.schema OK')
except Exception as e:
    print(f'data.schema FAILED: {e}')
try:
    from api import router
    print('API router OK')
except Exception as e:
    print(f'API router FAILED: {e}')
print('All imports passed!')
" 2>&1

echo "=== Starting uvicorn as appuser on port ${PORT:-8000} ==="
exec su -s /bin/sh appuser -c "exec uvicorn run:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"
