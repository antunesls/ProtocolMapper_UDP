from fastapi import APIRouter

from app.api.routes import mappings, settings, logs

router = APIRouter()
router.include_router(mappings.router)
router.include_router(settings.router)
router.include_router(logs.router)
