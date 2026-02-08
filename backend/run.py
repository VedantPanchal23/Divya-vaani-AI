"""
Divya Vaani AI - Main Application
FastAPI server for spiritual AI assistant.
Production-ready with security, rate limiting, and cleanup.
"""
import logging
import asyncio
import time
import uvicorn
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager

from config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)


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
    logger.info("=" * 60)
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)
    
    # Check API keys
    if settings.GROQ_API_KEY:
        logger.info("Groq API configured")
    else:
        logger.warning("GROQ_API_KEY not set! Transcription and Q&A will not work.")
    
    if settings.GEMINI_API_KEY:
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
    
    # Initialize video content store
    try:
        from data.videos_content import init_videos_content
        init_videos_content()
        logger.info("Video content store initialized")
    except Exception as e:
        logger.warning(f"Video content init failed: {e}")
    
    logger.info(f"TTS Mode: {settings.TTS_MODE} (gTTS + Edge TTS)")
    logger.info(f"Server: http://localhost:{settings.PORT}")
    logger.info(f"Docs: http://localhost:{settings.PORT}/docs")

    # Start background cleanup task
    cleanup_task = asyncio.create_task(_cleanup_old_audio())
    
    yield
    
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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
from api import router
app.include_router(router, prefix="/api")

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
        "groq": bool(settings.GROQ_API_KEY)
    }


# ── Serve frontend static files in production (Railway) ──
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA - catch-all for client-side routing."""
        # Path traversal protection
        file_path = (STATIC_DIR / full_path).resolve()
        static_resolved = STATIC_DIR.resolve()
        if not str(file_path).startswith(str(static_resolved)):
            return FileResponse(STATIC_DIR / "index.html")
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    uvicorn.run(
        "run:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        reload_excludes=["data/*", "*.mp3", "*.mp4", "*.wav", "*.json"] if settings.DEBUG else None
    )

