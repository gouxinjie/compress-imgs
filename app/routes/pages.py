from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse


router = APIRouter()


def _demo_items() -> list[dict[str, object]]:
    return [
        {
            "filename": "hero-banner.png",
            "display_thumb": "/assets/thumb_lake.png",
            "status": "success",
            "original_size": 2569011,
            "compressed_size": 881879,
            "ratio": 65.67,
        },
        {
            "filename": "product-show.jpg",
            "display_thumb": "/assets/thumb_desert.png",
            "status": "success",
            "original_size": 1342177,
            "compressed_size": 524738,
            "ratio": 60.91,
        },
        {
            "filename": "logo.webp",
            "display_thumb": "/assets/thumb_abstract.png",
            "status": "success",
            "original_size": 123321,
            "compressed_size": 45211,
            "ratio": 63.34,
        },
        {
            "filename": "large-photo.jpeg",
            "display_thumb": "/assets/thumb_city.png",
            "status": "processing",
            "original_size": 12939428,
            "compressed_size": None,
            "ratio": None,
        },
    ]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    summary = {
        "success": 2,
        "failed": 0,
        "total": 4,
        "processed": 2,
        "original_bytes": 4016048,
        "compressed_bytes": 584224,
        "saved_bytes": 3431824,
    }
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": settings,
            "demo_items": _demo_items(),
            "demo_summary": summary,
        },
    )


@router.get("/result/{task_id}", response_class=HTMLResponse)
async def result_page(task_id: str, request: Request) -> HTMLResponse:
    try:
        task = request.app.state.task_store.load(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。") from exc

    return request.app.state.templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "settings": request.app.state.settings,
            "task": task,
        },
    )
