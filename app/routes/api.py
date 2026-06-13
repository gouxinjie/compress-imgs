from __future__ import annotations

import logging
from time import perf_counter
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.models.schemas import CreateTaskResponseSchema, TaskResponseSchema
from app.services.cleanup import cleanup_expired_files
from app.services.compressor import CompressionError
from app.services.file_store import UploadLimitError


router = APIRouter(prefix="/api", tags=["api"])
logger = logging.getLogger("uvicorn.error")
LOG_PREFIX = "[compress-task]"


async def _cleanup_partial_uploads(files: list[UploadFile], saved_paths: list[Path], upload_dir: Path, compressed_dir: Path) -> None:
    for upload in files:
        await upload.close()
    for saved_path in saved_paths:
        saved_path.unlink(missing_ok=True)
    try:
        upload_dir.rmdir()
    except OSError:
        pass
    try:
        compressed_dir.rmdir()
    except OSError:
        pass


@router.post("/compress", response_model=CreateTaskResponseSchema)
async def create_compress_task(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    request_started_at = perf_counter()
    settings = request.app.state.settings
    file_store = request.app.state.file_store
    task_store = request.app.state.task_store
    limiter = request.app.state.limiter

    client_ip = request.client.host if request.client else "unknown"
    if not limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "请求过于频繁，请稍后再试。"},
        )

    cleanup_expired_files(settings)

    if not files:
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_files", "message": "请至少选择 1 张图片。"},
        )
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "too_many_files",
                "message": f"单次最多上传 {settings.max_files_per_upload} 张图片。",
            },
        )

    task_id = file_store.generate_task_id()
    upload_dir, compressed_dir = file_store.prepare_task_dirs(task_id)
    existing_names: set[str] = set()
    items: list[dict[str, object]] = []
    saved_paths: list[Path] = []
    total_size = 0

    try:
        for upload in files:
            upload_started_at = perf_counter()
            extension = Path(upload.filename or "").suffix.lower().lstrip(".")
            if extension not in settings.allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "invalid_file_type",
                        "message": "仅支持 PNG、JPG、JPEG、WEBP。",
                    },
                )

            request_remaining_bytes = settings.max_request_size_bytes - total_size
            if request_remaining_bytes <= 0:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "request_too_large",
                        "message": f"本次上传总大小不能超过 {settings.max_request_size_mb} MB。",
                    },
                )

            saved = await file_store.save_upload(
                upload,
                upload_dir,
                existing_names,
                max_file_size_bytes=settings.max_file_size_bytes,
                max_request_remaining_bytes=request_remaining_bytes,
            )
            saved_paths.append(saved["path"])
            file_size = int(saved["size"])
            total_size += file_size
            upload_elapsed_ms = int((perf_counter() - upload_started_at) * 1000)

            items.append(
                {
                    "filename": saved["filename"],
                    "stored_filename": saved["stored_filename"],
                    "status": "queued",
                    "original_size": file_size,
                    "compressed_size": None,
                    "ratio": None,
                    "download_path": None,
                    "preview_path": None,
                    "error_code": None,
                    "error_message": None,
                }
            )
            logger.info(
                "%s event=upload_saved task_id=%s file=%s bytes=%s elapsed_ms=%s client_ip=%s",
                LOG_PREFIX,
                task_id,
                saved["stored_filename"],
                file_size,
                upload_elapsed_ms,
                client_ip,
            )
    except UploadLimitError as exc:
        await _cleanup_partial_uploads(files, saved_paths, upload_dir, compressed_dir)
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception:
        await _cleanup_partial_uploads(files, saved_paths, upload_dir, compressed_dir)
        raise

    task_store.create_task(task_id, items)
    background_tasks.add_task(process_task, request.app, task_id, upload_dir, compressed_dir)
    logger.info(
        "%s event=task_created task_id=%s files=%s total_bytes=%s upload_elapsed_ms=%s client_ip=%s",
        LOG_PREFIX,
        task_id,
        len(items),
        total_size,
        int((perf_counter() - request_started_at) * 1000),
        client_ip,
    )
    return {"task_id": task_id, "status": "queued", "poll_url": f"/api/tasks/{task_id}"}


@router.get("/tasks/{task_id}", response_model=TaskResponseSchema)
async def get_task_status(task_id: str, request: Request):
    try:
        return request.app.state.task_store.load(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。") from exc


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    return {"status": "ok", "app": settings.app_name}


@router.get("/errors/{code}")
async def error_dictionary(code: str):
    return JSONResponse({"code": code})


def process_task(app, task_id: str, upload_dir: Path, compressed_dir: Path) -> None:
    task_started_at = perf_counter()
    task_store = app.state.task_store
    file_store = app.state.file_store
    compressor = app.state.compressor
    zip_service = app.state.zip_service

    task_store.mark_processing(task_id)
    successful_files: list[Path] = []

    task = task_store.load(task_id)
    logger.info(
        "%s event=task_processing_started task_id=%s files=%s backend=%s",
        LOG_PREFIX,
        task_id,
        len(task["items"]),
        compressor.backend_name,
    )
    for item in task["items"]:
        stored_filename = item["stored_filename"]
        file_started_at = perf_counter()
        task_store.update_current_item(task_id, item["filename"])
        task_store.update_item(task_id, stored_filename, {"status": "processing"})

        source_path = upload_dir / stored_filename
        target_path = compressed_dir / stored_filename
        try:
            compressor.compress(source_path, target_path)
            compressed_size = target_path.stat().st_size
            original_size = source_path.stat().st_size
            ratio = round(max((1 - (compressed_size / original_size)) * 100, 0), 2) if original_size else 0
            successful_files.append(target_path)
            task_store.update_item(
                task_id,
                stored_filename,
                {
                    "status": "success",
                    "compressed_size": compressed_size,
                    "ratio": ratio,
                    "download_path": file_store.build_download_path(task_id, stored_filename),
                    "preview_path": file_store.build_download_path(task_id, stored_filename),
                    "error_code": None,
                    "error_message": None,
                },
            )
            logger.info(
                "%s event=file_compressed task_id=%s file=%s backend=%s original_bytes=%s compressed_bytes=%s ratio=%s elapsed_ms=%s",
                LOG_PREFIX,
                task_id,
                stored_filename,
                compressor.backend_name,
                original_size,
                compressed_size,
                ratio,
                int((perf_counter() - file_started_at) * 1000),
            )
        except CompressionError as exc:
            task_store.update_item(
                task_id,
                stored_filename,
                {
                    "status": "failed",
                    "compressed_size": None,
                    "ratio": None,
                    "download_path": None,
                    "preview_path": None,
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
            logger.warning(
                "%s event=file_compress_failed task_id=%s file=%s backend=%s error_code=%s elapsed_ms=%s",
                LOG_PREFIX,
                task_id,
                stored_filename,
                compressor.backend_name,
                exc.code,
                int((perf_counter() - file_started_at) * 1000),
            )
        except Exception:
            task_store.update_item(
                task_id,
                stored_filename,
                {
                    "status": "failed",
                    "compressed_size": None,
                    "ratio": None,
                    "download_path": None,
                    "preview_path": None,
                    "error_code": "server_error",
                    "error_message": "压缩服务暂时不可用，请稍后再试。",
                },
            )
            logger.exception(
                "%s event=file_compress_failed task_id=%s file=%s backend=%s error_code=server_error elapsed_ms=%s",
                LOG_PREFIX,
                task_id,
                stored_filename,
                compressor.backend_name,
                int((perf_counter() - file_started_at) * 1000),
            )

    zip_download_path = None
    if len(successful_files) >= 2:
        zip_started_at = perf_counter()
        zip_service.create_zip(task_id, successful_files)
        zip_download_path = file_store.build_zip_download_path(task_id)
        logger.info(
            "%s event=task_zip_created task_id=%s files=%s elapsed_ms=%s",
            LOG_PREFIX,
            task_id,
            len(successful_files),
            int((perf_counter() - zip_started_at) * 1000),
        )

    finalized_task = task_store.finalize(task_id, zip_download_path)
    logger.info(
        "%s event=task_processing_completed task_id=%s status=%s success=%s failed=%s total_elapsed_ms=%s",
        LOG_PREFIX,
        task_id,
        finalized_task["status"],
        finalized_task["summary"]["success"],
        finalized_task["summary"]["failed"],
        int((perf_counter() - task_started_at) * 1000),
    )


download_router = APIRouter(tags=["download"])


@download_router.get("/download/{task_id}/all.zip")
async def download_zip(task_id: str, request: Request):
    zip_path = request.app.state.settings.zips_dir / f"{task_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="压缩包不存在或已过期。")
    return FileResponse(zip_path, filename=f"{task_id}.zip")


@download_router.get("/download/{task_id}/{filename}")
async def download_single(task_id: str, filename: str, request: Request):
    path = request.app.state.settings.compressed_dir / task_id / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期。")
    return FileResponse(path, filename=Path(filename).name)
