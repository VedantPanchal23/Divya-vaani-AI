# ============================================================
# Divya Vaani AI - Railway Deployment
# Multi-stage build: Frontend (Node.js) + Backend (Python)
# ============================================================

# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend
FROM python:3.11-slim

WORKDIR /app

# Ensure Python can import /app as a package root
ENV PYTHONPATH=/app

# Install system dependencies (ffmpeg for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (CPU-only torch to reduce image size)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt \
    && pip check

# Copy backend code and scripts as root
COPY backend/ ./
RUN chmod +x start.sh
COPY backend/start_fallback.sh ./
RUN chmod +x start_fallback.sh

# Copy built frontend into static/ directory
COPY --from=frontend-builder /app/frontend/dist ./static

# Create necessary storage directories (separate from Python data/ package)
RUN mkdir -p /app/storage/uploads /app/storage/transcripts /app/storage/audio /app/storage/index /app/storage/thumbnails

# NOTE: Do NOT use VOLUME here — Railway bans it.
# Attach a Railway Volume via Dashboard -> Service -> Settings -> Volumes
# Mount path: /app/storage   (NOT /app/data — that's a Python package!)

# NOTE: No HEALTHCHECK here — Railway uses its own (configured in railway.toml)

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app /app/storage

# Set production defaults
ENV DEBUG=false
ENV TTS_MODE=fast
ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1
ENV STORAGE_DIR=/app/storage

# Railway dynamically assigns PORT via env var
EXPOSE 8000

# Run entrypoint as root so it can fix volume permissions,
# then start.sh drops to appuser via su-exec / gosu
CMD ["/bin/sh", "/app/start.sh"]
