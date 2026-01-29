"""
Divya Vaani AI - Main Application
FastAPI server for spiritual AI assistant.
OPTIMIZED: Fast startup, no blocking pre-loads.
"""
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fast startup - no blocking operations."""
    print()
    print("=" * 60)
    print(f"  🙏 {settings.APP_NAME} v{settings.APP_VERSION}")
    print("=" * 60)
    print()
    
    # Check Groq API (instant)
    if settings.GROQ_API_KEY:
        print("✅ Groq API configured")
    else:
        print("❌ GROQ_API_KEY not set! Check .env file")
    
    print()
    print(f"🚀 Server: http://localhost:{settings.PORT}")
    print(f"📚 Docs: http://localhost:{settings.PORT}/docs")
    print()
    print("💡 Embedding model will load on first search (lazy load)")
    print()
    
    yield
    
    print()
    print("🙏 Shutting down gracefully...")


# Create app
app = FastAPI(
    title=settings.APP_NAME,
    description="Spiritual AI Assistant - Answers from Pravachan & Bhagavad Gita",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
from api import router
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Health check."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "groq": bool(settings.GROQ_API_KEY)
    }


if __name__ == "__main__":
    uvicorn.run(
        "run:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        reload_excludes=["data/*", "*.mp3", "*.mp4", "*.wav", "*.json"] if settings.DEBUG else None
    )

