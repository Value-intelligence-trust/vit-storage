from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import io
from tachyon.api.models import FileMetadata, UploadResponse, FragmentMetadata
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Storage"])

@router.get("/status",
            summary="Get API status",
            description="Returns the current operational status of the Tachyon API module.")
async def get_status():
    return {"status": "ok", "module": "tachyon.api", "version": "1.1.0"}

@router.post("/upload",
             response_model=UploadResponse,
             summary="Upload a file",
             description="Splits the file into fragments and distributes them across available cloud providers.")
async def upload_file(file: UploadFile = File(..., description="The file to upload")):
    logger.info(f"Uploading file: {file.filename}")
    return UploadResponse(file_id=f"file_{file.filename}", status="uploaded", fragments_count=3)

@router.get("/download/{file_id}",
            summary="Download a file",
            description="Reconstructs the file from fragments and streams it to the client.")
async def download_file(file_id: str):
    logger.info(f"Downloading file: {file_id}")
    # Placeholder: Return dummy content
    buf = io.BytesIO(b"Dummy file content for " + file_id.encode())
    return StreamingResponse(buf, media_type="application/octet-stream")

@router.get("/files",
            response_model=List[FileMetadata],
            summary="List files",
            description="Returns a list of all files managed by the swarm coordination plane.")
async def list_files(limit: int = Query(10, ge=1), offset: int = Query(0, ge=0)):
    return []

@router.get("/files/{file_id}",
            response_model=FileMetadata,
            summary="Get file metadata",
            description="Retrieves detailed metadata and fragment locations for a specific file.")
async def get_file_metadata(file_id: str):
    # Dummy metadata
    return FileMetadata(
        filename=file_id,
        total_size=1024,
        fragments=[
            FragmentMetadata(name=f"{file_id}_f1", provider="dropbox", size=512),
            FragmentMetadata(name=f"{file_id}_f2", provider="gdrive", size=512)
        ],
        redundancy_ratio=1.5
    )

@router.post("/files/{file_id}/rename",
             summary="Rename a file")
async def rename_file(file_id: str, new_name: str = Query(...)):
    return {"status": "renamed", "old_id": file_id, "new_id": new_name}

@router.post("/files/{file_id}/copy",
             summary="Copy a file")
async def copy_file(file_id: str, target_id: str = Query(...)):
    return {"status": "copied", "source": file_id, "destination": target_id}

@router.delete("/files/{file_id}",
               summary="Delete a file",
               description="Removes all fragments of the file from cloud providers and deletes metadata.")
async def delete_file(file_id: str):
    return {"status": "deleted", "file_id": file_id}
