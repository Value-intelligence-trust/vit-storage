import uuid
import mimetypes
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.db.database import get_db
from app.core.errors import AppError, error_payload
from tachyon.api.models import (
    FileMetadata, UploadResponse, FragmentMetadata,
    BatchDeleteRequest, BatchDeleteResponse, BatchDeleteResult,
    UploadFromUrlRequest, VerifyResponse
)
from tachyon.core.orchestrator import TachyonOrchestrator
from tachyon.core.models import TachyonManifest
from tachyon.core.s3_compat import router as s3_router

logger = logging.getLogger(__name__)

router = APIRouter()
orchestrator = TachyonOrchestrator()

VERSION = "2.0.0"


def _detect_content_type(filename: str, content_type: str = None) -> str:
    """Detect MIME type from filename or use provided content_type."""
    if content_type and content_type != "application/octet-stream":
        return content_type
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or "application/octet-stream"


def _manifest_to_metadata(m: TachyonManifest) -> FileMetadata:
    frags = []
    shards = m.provider_mapping.get("shards", [])
    for sh in shards:
        frags.append(
            FragmentMetadata(
                name=sh.get("file_id", f"{m.file_id}_{sh.get('shard_index')}") or "",
                provider=sh.get("provider_id", "local_disk"),
                size=sh.get("size_bytes", 0),
                checksum=sh.get("shard_hash")
            )
        )
    health_score = m.provider_mapping.get("_metadata", {}).get("health_score")
    return FileMetadata(
        file_id=m.file_id,
        filename=m.filename,
        total_size=m.size_bytes,
        fragments=frags,
        redundancy_ratio=1.5,
        created_at=m.created_at.isoformat() if m.created_at else None,
        content_type=m.content_type,
        tags=m.tags if m.tags else None,
        health_score=health_score,
    )


@router.get("/status",
            summary="Get API status",
            description="Returns the current operational status of the Tachyon API module.")
async def get_status(db: AsyncSession = Depends(get_db)):
    try:
        count_stmt = select(func.count(TachyonManifest.file_id))
        result = await db.execute(count_stmt)
        manifest_count = result.scalar() or 0

        sum_stmt = select(func.sum(TachyonManifest.size_bytes))
        sum_result = await db.execute(sum_stmt)
        total_bytes = sum_result.scalar() or 0

        provider_health = await orchestrator.pool.health_check()
    except Exception as e:
        logger.warning(f"Database/Pool read on status failed: {e}")
        manifest_count = 0
        total_bytes = 0
        provider_health = {}

    return {
        "status": "operational",
        "module": "tachyon.api",
        "version": VERSION,
        "active_nodes": len(orchestrator.pool.providers),
        "manifest_count": manifest_count,
        "total_bytes": total_bytes,
        "providers": provider_health
    }


@router.post("/upload",
             response_model=UploadResponse,
             summary="Upload a file",
             description="Splits the file into erasure-coded fragments and distributes them across available cloud providers.")
async def upload_file(
    file: UploadFile = File(..., description="The file to upload"),
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"Uploading file: {file.filename}")
    try:
        content = await file.read()
        file_id = str(uuid.uuid4())
        ct = _detect_content_type(file.filename, file.content_type)

        manifest = await orchestrator.upload(
            db=db,
            file_id=file_id,
            filename=file.filename,
            data=content,
            content_type=ct,
        )
        await db.commit()

        shards_count = len(manifest.provider_mapping.get("shards", []))
        return UploadResponse(
            file_id=manifest.file_id,
            status="uploaded",
            fragments_count=shards_count if shards_count else 9,
            filename=manifest.filename,
            content_type=manifest.content_type,
            size_bytes=manifest.size_bytes,
        )
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.exception("File upload failed")
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {e}")


@router.post("/upload/url",
             response_model=UploadResponse,
             summary="Upload a file from URL",
             description="Downloads content from a remote URL and stores it in the swarm.")
async def upload_from_url(
    payload: UploadFromUrlRequest,
    db: AsyncSession = Depends(get_db)
):
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            resp = await client.get(payload.url)
            resp.raise_for_status()
            content = resp.content
            remote_ct = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()

        filename = payload.filename
        if not filename:
            path_part = payload.url.split("?")[0].rstrip("/").split("/")[-1]
            filename = path_part or "remote_file"

        file_id = str(uuid.uuid4())
        ct = _detect_content_type(filename, remote_ct)

        manifest = await orchestrator.upload(
            db=db,
            file_id=file_id,
            filename=filename,
            data=content,
            content_type=ct,
        )
        await db.commit()

        shards_count = len(manifest.provider_mapping.get("shards", []))
        return UploadResponse(
            file_id=manifest.file_id,
            status="uploaded",
            fragments_count=shards_count if shards_count else 9,
            filename=manifest.filename,
            content_type=manifest.content_type,
            size_bytes=manifest.size_bytes,
        )
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Remote URL fetch failed: {e.response.status_code}")
    except Exception as e:
        logger.exception("Upload from URL failed")
        raise HTTPException(status_code=500, detail=f"Upload from URL failed: {e}")


@router.get("/download/{file_id}",
            summary="Download a file",
            description="Reassembles erasure-coded fragments in parallel and streams the reconstructed file.")
async def download_file(file_id: str, db: AsyncSession = Depends(get_db)):
    try:
        manifest_result = await db.execute(
            select(TachyonManifest).where(TachyonManifest.file_id == file_id)
        )
        manifest = manifest_result.scalar_one_or_none()
        filename = manifest.filename if manifest else "download"
        ct = (manifest.content_type if manifest and manifest.content_type else None) or "application/octet-stream"

        data = await orchestrator.retrieve(db, file_id)
        return Response(
            content=data,
            media_type=ct,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except AppError as ae:
        raise HTTPException(status_code=ae.status_code, detail=ae.message)
    except Exception as e:
        logger.exception(f"File retrieval failed for: {file_id}")
        raise HTTPException(status_code=404, detail="File could not be recovered")


@router.get("/files",
            response_model=List[FileMetadata],
            summary="List files",
            description="Returns a paginated list of files. Supports search by filename and filter by content type.")
async def list_files(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search by filename (case-insensitive substring)"),
    content_type: Optional[str] = Query(None, description="Filter by content type prefix (e.g. image/)"),
    db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(TachyonManifest)

        if search:
            stmt = stmt.where(TachyonManifest.filename.ilike(f"%{search}%"))

        if content_type:
            stmt = stmt.where(TachyonManifest.content_type.ilike(f"{content_type}%"))

        stmt = stmt.order_by(TachyonManifest.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        manifests = result.scalars().all()

        return [_manifest_to_metadata(m) for m in manifests]
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        return []


@router.get("/files/{file_id}",
            response_model=FileMetadata,
            summary="Get file metadata",
            description="Retrieves detailed metadata and fragment locations for a specific file.")
async def get_file_metadata(file_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(TachyonManifest).where(TachyonManifest.file_id == file_id)
    result = await db.execute(stmt)
    manifest = result.scalar_one_or_none()
    if not manifest:
        raise HTTPException(status_code=404, detail="File manifest not found")
    return _manifest_to_metadata(manifest)


@router.delete("/files/{file_id}",
               summary="Delete a file",
               description="Removes all fragments of the file from cloud providers and deletes metadata.")
async def delete_file(file_id: str, db: AsyncSession = Depends(get_db)):
    try:
        success = await orchestrator.delete(db, file_id)
        if not success:
            raise HTTPException(status_code=404, detail="File manifest not found")
        await db.commit()
        return {"status": "deleted", "file_id": file_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("File deletion failed")
        raise HTTPException(status_code=500, detail=f"Delete action failed: {e}")


@router.post("/files/batch-delete",
             response_model=BatchDeleteResponse,
             summary="Batch delete files",
             description="Deletes multiple files in a single request. Returns per-file success/failure results.")
async def batch_delete_files(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db)
):
    results = []
    deleted = 0
    failed = 0

    for file_id in payload.file_ids:
        try:
            success = await orchestrator.delete(db, file_id)
            if success:
                deleted += 1
                results.append(BatchDeleteResult(file_id=file_id, success=True))
            else:
                failed += 1
                results.append(BatchDeleteResult(file_id=file_id, success=False, error="File not found"))
        except Exception as e:
            failed += 1
            results.append(BatchDeleteResult(file_id=file_id, success=False, error=str(e)))

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Batch delete commit failed: {e}")

    return BatchDeleteResponse(results=results, deleted=deleted, failed=failed)


@router.post("/files/{file_id}/verify",
             response_model=VerifyResponse,
             summary="Verify file integrity",
             description="Performs a challenge-response check against a random sample of shards to confirm data integrity.")
async def verify_file(file_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await orchestrator.verify(db, file_id)
        await db.commit()
        return VerifyResponse(
            file_id=file_id,
            verified=result["verified"],
            shards_checked=result["shards_checked"],
            shards_healthy=result["shards_healthy"],
            health_score=result.get("health_score", 1.0),
            degraded=result["degraded"],
        )
    except AppError as ae:
        raise HTTPException(status_code=ae.status_code, detail=ae.message)
    except Exception as e:
        logger.exception(f"Verify failed for {file_id}")
        raise HTTPException(status_code=500, detail=f"Verify failed: {e}")


# Wire S3 Compatible APIRouter
router.include_router(s3_router, prefix="/s3", tags=["S3 Compatible API"])
