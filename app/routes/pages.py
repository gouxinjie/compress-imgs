from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": settings,
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
