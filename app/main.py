from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.routes.api import download_router, router as api_router
from app.routes.pages import router as page_router
from app.services.cleanup import cleanup_expired_files, ensure_directories
from app.services.compressor import Compressor
from app.services.file_store import FileStore
from app.services.limiter import SimpleRateLimiter
from app.services.task_store import TaskStore
from app.services.zip_service import ZipService


def format_bytes(value: int | None) -> str:
    if value is None:
        return "-"
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.2f} KB"
    return f"{value / 1024 / 1024:.2f} MB"


def build_app() -> FastAPI:
    settings = get_settings()
    ensure_directories(settings)
    cleanup_expired_files(settings)

    app = FastAPI(title=settings.app_name)
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    templates.env.filters["filesize"] = format_bytes

    app.state.settings = settings
    app.state.templates = templates
    app.state.file_store = FileStore(settings)
    app.state.task_store = TaskStore(settings)
    app.state.compressor = Compressor(settings)
    app.state.zip_service = ZipService(settings)
    app.state.limiter = SimpleRateLimiter(settings.rate_limit_per_minute)

    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
    app.mount("/assets", StaticFiles(directory=str(settings.assets_dir)), name="assets")

    app.include_router(page_router)
    app.include_router(api_router)
    app.include_router(download_router)
    return app


app = build_app()
