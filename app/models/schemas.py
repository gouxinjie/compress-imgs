from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


TaskStatus = Literal["queued", "processing", "partial_success", "completed", "failed"]
ItemStatus = Literal["queued", "processing", "success", "failed"]


class TaskItemSchema(BaseModel):
    filename: str
    stored_filename: str
    status: ItemStatus
    original_size: int
    compressed_size: int | None = None
    ratio: float | None = None
    download_path: str | None = None
    preview_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class TaskSummarySchema(BaseModel):
    total: int
    processed: int
    success: int
    failed: int
    original_bytes: int
    compressed_bytes: int
    saved_bytes: int


class TaskResponseSchema(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: str
    updated_at: str
    error_code: str | None = None
    error_message: str | None = None
    current_filename: str | None = None
    summary: TaskSummarySchema
    items: list[TaskItemSchema]
    zip_download_path: str | None = None


class CreateTaskResponseSchema(BaseModel):
    task_id: str
    status: TaskStatus
    poll_url: str
