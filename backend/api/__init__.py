"""API module — combines all sub-routers into a single router."""
from fastapi import APIRouter

from .upload_routes import router as upload_router
from .video_routes import router as video_router
from .chat_routes import router as chat_router
from .tts_routes import router as tts_router
from .auth_routes import router as auth_router
from .user_routes import router as user_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(upload_router)
router.include_router(video_router)
router.include_router(chat_router)
router.include_router(tts_router)
