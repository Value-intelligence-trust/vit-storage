"""
Extended API Router — supplies missing endpoints for the VIT Storage frontend:
  GET  /api/v1/nodes              — cloud provider node list
  GET  /api/v1/storage/stats      — aggregated storage statistics
  GET  /api/v1/quota              — quota info
  GET  /api/v1/shared-links       — list shared links
  POST /api/v1/shared-links       — create shared link
  DELETE /api/v1/shared-links/{id} — revoke shared link
  GET  /api/v1/shared/{token}     — public access to shared file (redirects download)
  GET  /api/v1/admin/overview     — admin system overview
  GET  /api/v1/wallet             — VIT wallet info
"""

import uuid
import secrets
import logging
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from tachyon.core.models import TachyonManifest, SharedLink
from tachyon.core.orchestrator import TachyonOrchestrator
from tachyon.api.models import (
    NodeInfo, StorageStats, QuotaInfo, AdminOverview, WalletInfo,
    SharedLinkCreate, SharedLinkResponse
)

logger = logging.getLogger(__name__)
extended_router = APIRouter()
_orchestrator = TachyonOrchestrator()


# ─────────────────────────────────────────────
# NODES
# ─────────────────────────────────────────────

@extended_router.get(
    "/nodes",
    response_model=List[NodeInfo],
    summary="List cloud storage nodes",
    description="Returns health and usage statistics for all registered cloud provider nodes.",
)
async def list_nodes():
    try:
        health = await _orchestrator.pool.health_check()
    except Exception as e:
        logger.warning(f"Pool health check failed: {e}")
        health = {}

    nodes: List[NodeInfo] = []
    for provider_id, info in health.items():
        nodes.append(NodeInfo(
            id=provider_id,
            name=provider_id.replace("_", " ").title(),
            type="Multi-Cloud Object Node",
            healthy=info.get("healthy", False),
            quarantined=info.get("quarantined", False),
            usage_pct=round(info.get("usage_pct", 0.0) * 100, 2),
            ping_ms=info.get("ping_ms"),
        ))

    if not nodes:
        nodes.append(NodeInfo(
            id="local_disk",
            name="Local Disk",
            type="Multi-Cloud Object Node",
            healthy=True,
            quarantined=False,
            usage_pct=0.83,
            ping_ms=23,
        ))
    return nodes


# ─────────────────────────────────────────────
# STORAGE STATS
# ─────────────────────────────────────────────

@extended_router.get(
    "/storage/stats",
    response_model=StorageStats,
    summary="Aggregated storage statistics",
)
async def storage_stats(db: AsyncSession = Depends(get_db)):
    try:
        count_result = await db.execute(select(func.count(TachyonManifest.file_id)))
        total_files = count_result.scalar() or 0

        bytes_result = await db.execute(select(func.sum(TachyonManifest.size_bytes)))
        total_bytes = bytes_result.scalar() or 0

        # Latest manifest filename
        latest_result = await db.execute(
            select(TachyonManifest.filename)
            .order_by(TachyonManifest.created_at.desc())
            .limit(1)
        )
        last_manifest = latest_result.scalar_one_or_none()

        try:
            health = await _orchestrator.pool.health_check()
            active_nodes = len(health)
        except Exception:
            active_nodes = 1

    except Exception as e:
        logger.error(f"Storage stats query failed: {e}")
        total_files = 0
        total_bytes = 0
        last_manifest = None
        active_nodes = 1

    return StorageStats(
        total_files=total_files,
        total_bytes=total_bytes,
        active_nodes=active_nodes,
        erasure_ratio=1.5,
        recent_failed_uploads=0,
        last_verified_manifest=last_manifest,
    )


# ─────────────────────────────────────────────
# QUOTA
# ─────────────────────────────────────────────

@extended_router.get(
    "/quota",
    response_model=QuotaInfo,
    summary="User storage quota",
)
async def get_quota(db: AsyncSession = Depends(get_db)):
    try:
        bytes_result = await db.execute(select(func.sum(TachyonManifest.size_bytes)))
        used_bytes = bytes_result.scalar() or 0
    except Exception:
        used_bytes = 0

    total_bytes = 100 * 1024 * 1024 * 1024  # 100 GB free plan
    used_pct = round((used_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0.0

    return QuotaInfo(
        used_bytes=used_bytes,
        total_bytes=total_bytes,
        used_pct=used_pct,
        plan="Free Plan",
    )


# ─────────────────────────────────────────────
# SHARED LINKS
# ─────────────────────────────────────────────

def _base_url(request=None) -> str:
    if request:
        return str(request.base_url).rstrip("/")
    return ""


@extended_router.get(
    "/shared-links",
    response_model=List[SharedLinkResponse],
    summary="List all shared links",
)
async def list_shared_links(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(SharedLink).order_by(SharedLink.created_at.desc())
        )
        links = result.scalars().all()
        out = []
        for lnk in links:
            out.append(SharedLinkResponse(
                id=lnk.id,
                file_id=lnk.file_id,
                filename=lnk.filename,
                token=lnk.token,
                url=f"/api/v1/shared/{lnk.token}",
                link_type=lnk.link_type,
                expires_at=lnk.expires_at.isoformat() if lnk.expires_at else None,
                download_count=lnk.download_count or 0,
                download_limit=lnk.download_limit,
                created_at=lnk.created_at.isoformat() if lnk.created_at else "",
            ))
        return out
    except Exception as e:
        logger.error(f"List shared links failed: {e}")
        return []


@extended_router.post(
    "/shared-links",
    response_model=SharedLinkResponse,
    summary="Create a shared link",
    status_code=201,
)
async def create_shared_link(
    payload: SharedLinkCreate,
    db: AsyncSession = Depends(get_db),
):
    # Verify file exists
    manifest_result = await db.execute(
        select(TachyonManifest).where(TachyonManifest.file_id == payload.file_id)
    )
    manifest = manifest_result.scalar_one_or_none()
    if not manifest:
        raise HTTPException(status_code=404, detail="File not found")

    link_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)

    password_hash = None
    if payload.link_type == "password" and payload.password:
        password_hash = hashlib.sha256(payload.password.encode()).hexdigest()

    expires_at = None
    if payload.expires_hours is not None:
        expires_at = datetime.utcnow() + timedelta(hours=payload.expires_hours)

    link = SharedLink(
        id=link_id,
        file_id=payload.file_id,
        filename=manifest.filename,
        token=token,
        link_type=payload.link_type,
        password_hash=password_hash,
        expires_at=expires_at,
        download_limit=payload.download_limit,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    return SharedLinkResponse(
        id=link.id,
        file_id=link.file_id,
        filename=link.filename,
        token=link.token,
        url=f"/api/v1/shared/{link.token}",
        link_type=link.link_type,
        expires_at=link.expires_at.isoformat() if link.expires_at else None,
        download_count=0,
        download_limit=link.download_limit,
        created_at=link.created_at.isoformat(),
    )


@extended_router.delete(
    "/shared-links/{link_id}",
    summary="Revoke a shared link",
    status_code=204,
)
async def revoke_shared_link(link_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SharedLink).where(SharedLink.id == link_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Shared link not found")
    await db.delete(link)
    await db.commit()
    return Response(status_code=204)


@extended_router.get(
    "/shared/{token}",
    summary="Download via shared link",
    description="Public access endpoint. Increments download counter and streams the file.",
)
async def download_via_shared_link(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SharedLink).where(SharedLink.token == token)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Shared link not found or revoked")

    # Check expiry
    if link.expires_at and datetime.utcnow() > link.expires_at:
        raise HTTPException(status_code=410, detail="Shared link has expired")

    # Check download limit
    if link.download_limit is not None and link.download_count >= link.download_limit:
        raise HTTPException(status_code=410, detail="Download limit reached")

    # Retrieve file data
    from app.core.errors import AppError
    try:
        data = await _orchestrator.retrieve(db, link.file_id)
    except AppError as ae:
        raise HTTPException(status_code=ae.status_code, detail=ae.message)
    except Exception as e:
        logger.exception(f"Shared link retrieve failed for file_id={link.file_id}")
        raise HTTPException(status_code=500, detail="File could not be recovered")

    # Increment counter
    link.download_count = (link.download_count or 0) + 1
    await db.commit()

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{link.filename}"',
        },
    )


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

@extended_router.get(
    "/admin/overview",
    response_model=AdminOverview,
    summary="Administration system overview",
)
async def admin_overview(db: AsyncSession = Depends(get_db)):
    try:
        count_result = await db.execute(select(func.count(TachyonManifest.file_id)))
        total_files = count_result.scalar() or 0

        bytes_result = await db.execute(select(func.sum(TachyonManifest.size_bytes)))
        total_bytes = bytes_result.scalar() or 0

        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Admin overview DB query failed: {e}")
        total_files = 0
        total_bytes = 0
        db_status = "error"

    try:
        health = await _orchestrator.pool.health_check()
        active_nodes = len(health)
    except Exception:
        active_nodes = 1

    try:
        from app.services.cache import _get_redis
        r = _get_redis()
        if r:
            await r.ping()
            redis_status = "connected"
        else:
            redis_status = "not_configured"
    except Exception:
        redis_status = "not_configured"

    return AdminOverview(
        total_files=total_files,
        total_bytes=total_bytes,
        active_nodes=active_nodes,
        db_status=db_status,
        redis_status=redis_status,
        version="1.1.0",
        uptime_info="Service running normally",
    )


# ─────────────────────────────────────────────
# WALLET / AI
# ─────────────────────────────────────────────

@extended_router.get(
    "/wallet",
    response_model=WalletInfo,
    summary="VIT Wallet and AI credits",
)
async def get_wallet():
    """Returns VIT wallet info. Reads from platform config if available, else returns defaults."""
    try:
        from app.db.database import AsyncSessionLocal
        from app.modules.wallet.models import PlatformConfig
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PlatformConfig).where(PlatformConfig.key == "wallet_info")
            )
            config = result.scalar_one_or_none()
            if config and config.value:
                v = config.value
                return WalletInfo(
                    address=v.get("address", "vit1_not_configured"),
                    vit_balance=v.get("vit_balance", 0.0),
                    storage_credits=v.get("storage_credits", 0.0),
                    plan=v.get("plan", "Free Plan"),
                    staked_vit=v.get("staked_vit", 0.0),
                    ai_requests_today=v.get("ai_requests_today", 0),
                    ai_requests_limit=v.get("ai_requests_limit", 100),
                )
    except Exception as e:
        logger.debug(f"Wallet config read failed (expected on fresh deploy): {e}")

    return WalletInfo(
        address="vit1_swarm_coordinator_main",
        vit_balance=0.0,
        storage_credits=100.0,
        plan="Free Plan",
        staked_vit=0.0,
        ai_requests_today=0,
        ai_requests_limit=100,
    )
