import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.core.errors import AppError, error_payload
from tachyon.api.models import FileMetadata, UploadResponse, FragmentMetadata
from tachyon.core.orchestrator import TachyonOrchestrator
from tachyon.core.models import TachyonManifest
from tachyon.core.s3_compat import router as s3_router

logger = logging.getLogger(__name__)

router = APIRouter()
orchestrator = TachyonOrchestrator()

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
        "version": "1.1.0",
        "active_nodes": len(orchestrator.pool.providers),
        "manifest_count": manifest_count,
        "total_bytes": total_bytes,
        "providers": provider_health
    }

@router.post("/upload",
             response_model=UploadResponse,
             summary="Upload a file",
             description="Splits the file into fragments and distributes them across available cloud providers.")
async def upload_file(
    file: UploadFile = File(..., description="The file to upload"),
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"Uploading file: {file.filename}")
    try:
        content = await file.read()
        file_id = str(uuid.uuid4())

        manifest = await orchestrator.upload(
            db=db,
            file_id=file_id,
            filename=file.filename,
            data=content
        )

        shards_count = len(manifest.provider_mapping.get("shards", []))
        return UploadResponse(
            file_id=manifest.file_id,
            status="uploaded",
            fragments_count=shards_count if shards_count else 9
        )
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.exception("File upload failed")
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {e}")

@router.get("/download/{file_id}",
            summary="Download a file",
            description="Reassembles erasure-coded fragments in parallel and streams the reconstructed file back to the client.")
async def download_file(file_id: str, db: AsyncSession = Depends(get_db)):
    try:
        # Fetch filename for content-disposition
        manifest_result = await db.execute(
            select(TachyonManifest).where(TachyonManifest.file_id == file_id)
        )
        manifest = manifest_result.scalar_one_or_none()
        filename = manifest.filename if manifest else "download"

        data = await orchestrator.retrieve(db, file_id)
        return Response(
            content=data,
            media_type="application/octet-stream",
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
            description="Returns a list of all files managed by the swarm coordination plane.")
async def list_files(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(TachyonManifest).order_by(TachyonManifest.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        manifests = result.scalars().all()

        response_data = []
        for m in manifests:
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

            response_data.append(
                FileMetadata(
                    file_id=m.file_id,
                    filename=m.filename,
                    total_size=m.size_bytes,
                    fragments=frags,
                    redundancy_ratio=1.5,
                    created_at=m.created_at.isoformat() if m.created_at else None,
                )
            )
        return response_data
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

    frags = [
        FragmentMetadata(
            name=f["file_id"],
            provider=f["provider_id"],
            size=f["size_bytes"],
            checksum=f.get("shard_hash")
        )
        for f in manifest.provider_mapping.get("shards", [])
    ]
    return FileMetadata(
        file_id=manifest.file_id,
        filename=manifest.filename,
        total_size=manifest.size_bytes,
        fragments=frags,
        created_at=manifest.created_at.isoformat() if manifest.created_at else None,
    )

@router.delete("/files/{file_id}",
               summary="Delete a file",
               description="Removes all fragments of the file from cloud providers and deletes metadata.")
async def delete_file(file_id: str, db: AsyncSession = Depends(get_db)):
    try:
        success = await orchestrator.delete(db, file_id)
        if not success:
            raise HTTPException(status_code=404, detail="File manifest not found")
        return {"status": "deleted", "file_id": file_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("File deletion failed")
        raise HTTPException(status_code=500, detail=f"Delete action failed: {e}")

# Wire S3 Compatible APIRouter
router.include_router(s3_router, prefix="/s3", tags=["S3 Compatible API"])
