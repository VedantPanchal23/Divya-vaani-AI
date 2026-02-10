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

# Install system dependencies (ffmpeg for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (CPU-only torch to reduce image size)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt \
    && pip check

# Copy backend code
COPY backend/ ./

# Copy built frontend into static/ directory
COPY --from=frontend-builder /app/frontend/dist ./static

# Create necessary data directories
RUN mkdir -p data/uploads data/transcripts data/audio data/index data/thumbnails

# NOTE: Do NOT use VOLUME here — Railway bans it.
# Instead, attach a Railway Volume via Dashboard -> Service -> Settings -> Volumes
# Mount path: /app/data

# NOTE: No HEALTHCHECK here — Railway uses its own (configured in railway.toml)

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

# Set production defaults
ENV DEBUG=false
ENV TTS_MODE=fast
ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1

# Railway dynamically assigns PORT via env var
EXPOSE 8000

# Use shell form so $PORT is expanded at runtime
CMD uvicorn run:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log
