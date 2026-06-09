from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class TaskStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_task(self, task_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        task = {
            "task_id": task_id,
            "status": "queued",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "error_code": None,
            "error_message": None,
            "current_filename": None,
            "summary": {
                "total": len(items),
                "processed": 0,
                "success": 0,
                "failed": 0,
                "original_bytes": sum(item["original_size"] for item in items),
                "compressed_bytes": 0,
                "saved_bytes": 0,
            },
            "items": items,
            "zip_download_path": None,
        }
        self.save(task)
        return task

    def load(self, task_id: str) -> dict[str, Any]:
        path = self._task_path(task_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, task: dict[str, Any]) -> None:
        task["updated_at"] = _now_iso()
        path = self._task_path(task["task_id"])
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def mark_failed(self, task_id: str, code: str, message: str) -> dict[str, Any]:
        task = self.load(task_id)
        task["status"] = "failed"
        task["error_code"] = code
        task["error_message"] = message
        self.save(task)
        return task

    def mark_processing(self, task_id: str) -> dict[str, Any]:
        task = self.load(task_id)
        task["status"] = "processing"
        self.save(task)
        return task

    def update_current_item(self, task_id: str, filename: str | None) -> dict[str, Any]:
        task = self.load(task_id)
        task["current_filename"] = filename
        self.save(task)
        return task

    def update_item(self, task_id: str, stored_filename: str, updates: dict[str, Any]) -> dict[str, Any]:
        task = self.load(task_id)
        for item in task["items"]:
            if item["stored_filename"] != stored_filename:
                continue
            item.update(deepcopy(updates))
            break

        self._recompute_summary(task)
        self.save(task)
        return task

    def finalize(self, task_id: str, zip_download_path: str | None) -> dict[str, Any]:
        task = self.load(task_id)
        task["zip_download_path"] = zip_download_path
        task["current_filename"] = None

        success = task["summary"]["success"]
        failed = task["summary"]["failed"]
        if success and failed:
            task["status"] = "partial_success"
        elif success:
            task["status"] = "completed"
        else:
            task["status"] = "failed"
            if not task["error_message"]:
                task["error_code"] = "compress_failed"
                task["error_message"] = "全部图片处理失败，请稍后重试。"

        self.save(task)
        return task

    def _recompute_summary(self, task: dict[str, Any]) -> None:
        processed = 0
        success = 0
        failed = 0
        compressed_bytes = 0
        saved_bytes = 0

        for item in task["items"]:
            if item["status"] in {"success", "failed"}:
                processed += 1
            if item["status"] == "success":
                success += 1
                original_size = item["original_size"] or 0
                compressed_size = item["compressed_size"] or 0
                compressed_bytes += compressed_size
                saved_bytes += max(original_size - compressed_size, 0)
            if item["status"] == "failed":
                failed += 1

        original_bytes = sum(item["original_size"] for item in task["items"])
        task["summary"].update(
            {
                "processed": processed,
                "success": success,
                "failed": failed,
                "original_bytes": original_bytes,
                "compressed_bytes": compressed_bytes,
                "saved_bytes": saved_bytes,
            }
        )

    def _task_path(self, task_id: str) -> Path:
        return self.settings.tasks_dir / f"{task_id}.json"
