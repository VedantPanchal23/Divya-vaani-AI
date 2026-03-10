"""
Divya Vaani AI - Main Application
FastAPI server for spiritual AI assistant.
Production-ready with security, rate limiting, and cleanup.
"""
# ── Very early diagnostics (before any app imports) ──
import sys
import os
print(f"[BOOT] Python {sys.version}", flush=True)
print(f"[BOOT] PORT={os.environ.get('PORT', 'NOT SET')}", flush=True)
print(f"[BOOT] DATABASE_URL={'SET' if os.environ.get('DATABASE_URL') else 'NOT SET'}", flush=True)
print(f"[BOOT] Working dir: {os.getcwd()}", flush=True)

import logging
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager

print("[BOOT] Core stdlib imports OK", flush=True)

from config import settings

print(f"[BOOT] Settings loaded — PORT={settings.PORT}, HOST={settings.HOST}", flush=True)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Rate limiting
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from rate_limiter import limiter

print("[BOOT] Rate limiter OK", flush=True)


async def _cleanup_old_audio():
    """Periodically delete audio files older than AUDIO_CLEANUP_HOURS."""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            audio_dir = settings.AUDIO_DIR
            if not audio_dir.exists():
                continue
            cutoff = time.time() - (settings.AUDIO_CLEANUP_HOURS * 3600)
            deleted = 0
            for f in audio_dir.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
                    deleted += 1
            if deleted:
                logger.info(f"Cleanup: deleted {deleted} old audio files")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Audio cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    cleanup_task = None
    try:
        logger.info("=" * 60)
        logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
        logger.info("=" * 60)
        
        # Check API keys
        if settings.GROQ_API_KEY.get_secret_value():
            logger.info("Groq API configured")
        else:
            logger.warning("GROQ_API_KEY not set! Transcription and Q&A will not work.")
        
        if settings.GEMINI_API_KEY.get_secret_value():
            logger.info("Gemini API configured")
        else:
            logger.info("GEMINI_API_KEY not set (summaries will use Groq fallback)")
        
        # Security warnings
        if not settings.ADMIN_API_KEY:
            logger.warning("ADMIN_API_KEY not set! Upload/admin endpoints are unprotected.")
        else:
            logger.info("Admin API key configured")
        
        if settings.CORS_ORIGINS == "*":
            logger.warning("CORS_ORIGINS='*' - restrict this in production")
        
        # Initialize database (create tables)
        try:
            from db.database import init_db
            await asyncio.wait_for(init_db(), timeout=20)
            logger.info("Database initialized")
        except asyncio.TimeoutError:
            logger.warning("Database init timed out after 20s — continuing without DB")
        except Exception as e:
            logger.warning(f"Database init failed: {e}")

        # Auto-migrate videos from JSON → DB if DB is empty
        try:
            from db.database import _get_session_factory
            from db import crud
            import json
            factory = _get_session_factory()
            async with factory() as db:
                existing = await asyncio.wait_for(crud.get_all_videos_db(db), timeout=15)
                if not existing:
                    json_path = Path(__file__).parent / "data" / "videos_content.json"
                    if json_path.exists():
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        videos = list(data.values()) if isinstance(data, dict) else data
                        migrated = 0
                        for v in videos:
                            if v.get("id"):
                                try:
                                    await crud.upsert_video(db, v)
                                    migrated += 1
                                except Exception as e:
                                    logger.warning(f"Migration skip {v.get('id')}: {e}")
                        logger.info(f"Auto-migrated {migrated} videos from JSON → DB")
                    else:
                        logger.info("No videos_content.json found — starting fresh")
                else:
                    logger.info(f"Database has {len(existing)} videos")
        except asyncio.TimeoutError:
            logger.warning("Video migration timed out — continuing")
        except Exception as e:
            logger.warning(f"Video migration failed: {e}")

        # Copy initial data files from package to storage (first run only)
        try:
            import shutil
            from config import PACKAGE_DATA_DIR
            storage_index = settings.INDEX_DIR
            package_index = PACKAGE_DATA_DIR / "index"
            if package_index.exists():
                for f in package_index.iterdir():
                    dest = storage_index / f.name
                    if f.is_file() and not dest.exists():
                        shutil.copy2(f, dest)
                        logger.info(f"Copied {f.name} to storage index")
        except Exception as e:
            logger.warning(f"Index copy failed: {e}")

        # Initialize video content for RAG indexing (still needed for FAISS)
        try:
            from data.videos_content import init_videos_content
            init_videos_content()
        except Exception as e:
            logger.warning(f"Video content init failed: {e}")
        
        logger.info(f"TTS Mode: {settings.TTS_MODE} (gTTS + Edge TTS)")
        logger.info(f"Server: http://0.0.0.0:{os.environ.get('PORT', settings.PORT)}")

        # Start background cleanup task
        cleanup_task = asyncio.create_task(_cleanup_old_audio())
        
    except Exception as e:
        logger.error(f"Startup error (app will still serve /health): {e}", exc_info=True)
    
    # ALWAYS yield — even if startup failed, uvicorn must accept connections
    print("[BOOT] Lifespan startup complete — yielding to uvicorn", flush=True)
    yield
    
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    # Close database connections
    try:
        from db.database import close_db
        await close_db()
    except Exception as e:
        logger.warning(f"Database close failed: {e}")

    logger.info("Shutting down gracefully...")


# Create app
app = FastAPI(
    title=settings.APP_NAME,
    description="Spiritual AI Assistant - Answers from Pravachan & Bhagavad Gita",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - use configured origins
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True if "*" not in cors_origins else False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key", "Authorization"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Global exception handler - prevent stack trace leaks
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )


# Routes
print("[BOOT] Importing API routes...", flush=True)
from api import router
from api.admin_routes import router as admin_router

app.include_router(admin_router, prefix="/admin")
app.include_router(router, prefix="/api")
print("[BOOT] API routes loaded OK", flush=True)

# ── Static file serving (production / Railway) ──
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def root():
    """Health check / serve frontend index."""
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check for Railway."""
    return {
        "status": "healthy",
        "groq": bool(settings.GROQ_API_KEY.get_secret_value())
    }


# ── Serve frontend static files in production (Railway) ──
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA - catch-all for client-side routing."""
        # Path traversal protection (case-insensitive safe)
        file_path = (STATIC_DIR / full_path).resolve()
        static_resolved = STATIC_DIR.resolve()
        if not file_path.is_relative_to(static_resolved):
            return FileResponse(STATIC_DIR / "index.html")
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", settings.PORT))
    print(f"[BOOT] Starting uvicorn on {settings.HOST}:{port}", flush=True)
    uvicorn.run(
        "run:app",
        host=settings.HOST,
        port=port,
        reload=settings.DEBUG,
        reload_excludes=["data/*", "*.mp3", "*.mp4", "*.wav", "*.json"] if settings.DEBUG else None
    )

