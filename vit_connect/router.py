"""
VIT Connect — FastAPI router.

Endpoints
─────────
GET  /api/v1/connect/providers              list all provider types + configured status
GET  /api/v1/connect/connections            list all stored connections
GET  /api/v1/connect/connections/{id}       get one connection detail
DELETE /api/v1/connect/connections/{id}     disconnect / remove
POST /api/v1/connect/connections/{id}/reconnect  re-start OAuth for an expired connection

POST /api/v1/connect/oauth/start/{provider} begin OAuth flow → returns {redirect_url}
GET  /api/v1/connect/oauth/callback/{provider}  OAuth callback (handles code exchange)

POST /api/v1/connect/wizard/s3             test + save an S3-compatible connection
POST /api/v1/connect/connections/{id}/refresh-health  force a health check
"""
import os
import secrets
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from tachyon.core.database import get_db
from vit_connect.models import ProviderConnection
from vit_connect import vault
from vit_connect.oauth import google, dropbox, microsoft

logger = logging.getLogger(__name__)

router = APIRouter(tags=["VIT Connect"])

# ── In-process OAuth state store (nonce → provider) ──────────────────
# For production scale, replace with Redis.
_oauth_states: dict[str, dict] = {}   # state_token → {provider, redirect_uri, ts}
_STATE_TTL = 600   # seconds


def _make_state(provider: str, redirect_uri: str) -> str:
    token = secrets.token_urlsafe(32)
    _oauth_states[token] = {"provider": provider, "redirect_uri": redirect_uri, "ts": time.time()}
    return token


def _consume_state(state: str) -> dict | None:
    entry = _oauth_states.pop(state, None)
    if not entry:
        return None
    if time.time() - entry["ts"] > _STATE_TTL:
        return None
    return entry


def _redirect_uri_for(request: Request, provider: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/connect/oauth/callback/{provider}"


# ─────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────

class ProviderTypeInfo(BaseModel):
    id:          str
    name:        str
    icon:        str
    auth_method: str   # oauth | key
    configured:  bool  # env vars present
    description: str


class ConnectionOut(BaseModel):
    id:                  str
    provider_type:       str
    account_label:       Optional[str]
    account_email:       Optional[str]
    status:              str
    health_score:        Optional[int]
    storage_quota_bytes: Optional[int]
    storage_used_bytes:  Optional[int]
    latency_ms:          Optional[int]
    last_sync_at:        Optional[str]
    expires_at:          Optional[str]
    created_at:          str
    extra_config:        Optional[dict]


class S3WizardRequest(BaseModel):
    provider_subtype: str = "s3"   # s3 | r2 | backblaze
    bucket_name:  str
    access_key:   str
    secret_key:   str
    region:       str = "us-east-1"
    account_id:   str = ""         # required for R2
    endpoint_url: str = ""
    label:        str = ""


def _conn_to_out(c: ProviderConnection) -> dict:
    return {
        "id":                  c.id,
        "provider_type":       c.provider_type,
        "account_label":       c.account_label,
        "account_email":       c.account_email,
        "status":              c.status,
        "health_score":        c.health_score,
        "storage_quota_bytes": c.storage_quota_bytes,
        "storage_used_bytes":  c.storage_used_bytes,
        "latency_ms":          c.latency_ms,
        "last_sync_at":        c.last_sync_at.isoformat() if c.last_sync_at else None,
        "expires_at":          c.expires_at.isoformat() if c.expires_at else None,
        "created_at":          c.created_at.isoformat() if c.created_at else "",
        "extra_config":        {k: v for k, v in (c.extra_config or {}).items()
                                if k not in ("access_key", "secret_key")},
    }


# ─────────────────────────────────────────────────────────────────────
# Provider catalogue
# ─────────────────────────────────────────────────────────────────────

def _get_provider_catalogue() -> list[dict]:
    return [
        {
            "id": "google_drive", "name": "Google Drive", "icon": "📁",
            "auth_method": "oauth", "configured": google.is_configured(),
            "description": "Connect with your Google account. No credentials to copy.",
        },
        {
            "id": "dropbox", "name": "Dropbox", "icon": "📦",
            "auth_method": "oauth", "configured": dropbox.is_configured(),
            "description": "One-click Dropbox authorisation.",
        },
        {
            "id": "onedrive", "name": "OneDrive", "icon": "☁️",
            "auth_method": "oauth", "configured": microsoft.is_configured(),
            "description": "Microsoft account sign-in for OneDrive.",
        },
        {
            "id": "r2", "name": "Cloudflare R2", "icon": "🔶",
            "auth_method": "key",
            "configured": True,   # wizard-only, no pre-config required
            "description": "Bucket name, Access Key, Secret Key — four fields.",
        },
        {
            "id": "backblaze", "name": "Backblaze B2", "icon": "🔥",
            "auth_method": "key", "configured": True,
            "description": "S3-compatible Backblaze B2 bucket.",
        },
        {
            "id": "s3", "name": "Amazon S3", "icon": "🪣",
            "auth_method": "key", "configured": True,
            "description": "Any S3-compatible endpoint including Amazon S3.",
        },
    ]


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────

@router.get("/providers", summary="List available provider types")
async def list_providers():
    return _get_provider_catalogue()


@router.get("/connections", summary="List all stored connections")
async def list_connections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProviderConnection).where(ProviderConnection.is_active == True).order_by(ProviderConnection.created_at.desc())
    )
    return [_conn_to_out(c) for c in result.scalars()]


@router.get("/connections/{conn_id}", summary="Get one connection")
async def get_connection(conn_id: str, db: AsyncSession = Depends(get_db)):
    c = await db.get(ProviderConnection, conn_id)
    if not c or not c.is_active:
        raise HTTPException(404, "Connection not found")
    return _conn_to_out(c)


@router.delete("/connections/{conn_id}", summary="Disconnect a provider")
async def disconnect_provider(conn_id: str, db: AsyncSession = Depends(get_db)):
    c = await db.get(ProviderConnection, conn_id)
    if not c:
        raise HTTPException(404, "Connection not found")
    c.is_active = False
    c.status    = "disconnected"
    await db.commit()
    return {"ok": True, "id": conn_id}


# ─── OAuth start ──────────────────────────────────────────────────────

@router.post("/oauth/start/{provider}", summary="Begin OAuth flow")
async def oauth_start(provider: str, request: Request):
    redirect_uri = _redirect_uri_for(request, provider)
    state        = _make_state(provider, redirect_uri)

    if provider == "google_drive":
        url = google.get_authorize_url(redirect_uri, state)
    elif provider == "dropbox":
        url = dropbox.get_authorize_url(redirect_uri, state)
    elif provider == "onedrive":
        url = microsoft.get_authorize_url(redirect_uri, state)
    else:
        raise HTTPException(400, f"Unknown OAuth provider: {provider}")

    if not url:
        raise HTTPException(503, f"{provider} OAuth is not configured on this server. "
                                 f"Set the required client ID and secret environment variables.")

    return {"redirect_url": url, "provider": provider}


# ─── OAuth callback ────────────────────────────────────────────────────

@router.get("/oauth/callback/{provider}", summary="OAuth callback handler")
async def oauth_callback(provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    params = dict(request.query_params)
    code   = params.get("code")
    state  = params.get("state")
    error  = params.get("error")

    frontend_base = str(request.base_url).rstrip("/")

    if error:
        logger.warning(f"OAuth error for {provider}: {error}")
        return RedirectResponse(f"{frontend_base}/connect?error={error}&provider={provider}")

    if not code or not state:
        return RedirectResponse(f"{frontend_base}/connect?error=missing_params&provider={provider}")

    state_data = _consume_state(state)
    if not state_data:
        return RedirectResponse(f"{frontend_base}/connect?error=invalid_state&provider={provider}")

    redirect_uri = state_data["redirect_uri"]

    try:
        if provider == "google_drive":
            tokens   = await google.exchange_code(code, redirect_uri)
            userinfo = await google.get_userinfo(tokens["access_token"])
            quota    = await google.get_drive_quota(tokens["access_token"])

            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))) if "expires_in" in tokens else None

            enc = vault.encrypt({
                "access_token":  tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
                "token_type":    tokens.get("token_type", "Bearer"),
            })

            conn = ProviderConnection(
                provider_type       = "google_drive",
                auth_method         = "oauth",
                account_label       = userinfo.get("name") or userinfo.get("email", "Google Drive"),
                account_email       = userinfo.get("email"),
                encrypted_data      = enc,
                scopes              = google.SCOPES,
                expires_at          = expires_at,
                status              = "connected",
                storage_quota_bytes = int(quota.get("limit", 0)) if quota.get("limit") else None,
                storage_used_bytes  = int(quota.get("usageInDrive", 0)) if quota.get("usageInDrive") else None,
                last_sync_at        = datetime.utcnow(),
            )

        elif provider == "dropbox":
            tokens  = await dropbox.exchange_code(code, redirect_uri)
            account = await dropbox.get_account_info(tokens["access_token"])
            space   = await dropbox.get_space_usage(tokens["access_token"])

            expires_at = None
            if "expires_in" in tokens:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

            enc = vault.encrypt({
                "access_token":  tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
            })

            email = account.get("email") or account.get("name", {}).get("display_name", "Dropbox")
            used  = space.get("used") if space else None
            alloc = space.get("allocation", {}).get("allocated") if space else None

            conn = ProviderConnection(
                provider_type       = "dropbox",
                auth_method         = "oauth",
                account_label       = account.get("name", {}).get("display_name", "Dropbox"),
                account_email       = email,
                encrypted_data      = enc,
                expires_at          = expires_at,
                status              = "connected",
                storage_quota_bytes = int(alloc) if alloc else None,
                storage_used_bytes  = int(used)  if used  else None,
                last_sync_at        = datetime.utcnow(),
            )

        elif provider == "onedrive":
            tokens   = await microsoft.exchange_code(code, redirect_uri)
            userinfo = await microsoft.get_user_info(tokens["access_token"])
            drive    = await microsoft.get_drive_info(tokens["access_token"])

            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])) if "expires_in" in tokens else None

            enc = vault.encrypt({
                "access_token":  tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
                "token_type":    tokens.get("token_type", "Bearer"),
            })

            quota_info = drive.get("quota", {})
            conn = ProviderConnection(
                provider_type       = "onedrive",
                auth_method         = "oauth",
                account_label       = userinfo.get("displayName") or userinfo.get("userPrincipalName", "OneDrive"),
                account_email       = userinfo.get("mail") or userinfo.get("userPrincipalName"),
                encrypted_data      = enc,
                scopes              = microsoft.SCOPES,
                expires_at          = expires_at,
                status              = "connected",
                storage_quota_bytes = quota_info.get("total"),
                storage_used_bytes  = quota_info.get("used"),
                last_sync_at        = datetime.utcnow(),
            )

        else:
            return RedirectResponse(f"{frontend_base}/connect?error=unknown_provider&provider={provider}")

        db.add(conn)
        await db.commit()
        logger.info(f"VIT Connect: {provider} connected — {conn.account_email}")
        return RedirectResponse(f"{frontend_base}/connect?success={provider}&label={conn.account_label or ''}")

    except Exception as exc:
        logger.error(f"OAuth callback error for {provider}: {exc}", exc_info=True)
        return RedirectResponse(f"{frontend_base}/connect?error=callback_failed&provider={provider}")


# ─── OAuth reconnect ──────────────────────────────────────────────────

@router.post("/connections/{conn_id}/reconnect", summary="Reconnect an expired connection")
async def reconnect(conn_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    c = await db.get(ProviderConnection, conn_id)
    if not c:
        raise HTTPException(404, "Connection not found")
    return await oauth_start(c.provider_type, request)


# ─── S3 Wizard ────────────────────────────────────────────────────────

@router.post("/wizard/s3", summary="Test and save an S3-compatible connection")
async def s3_wizard(req: S3WizardRequest, db: AsyncSession = Depends(get_db)):
    from vit_connect.wizard.s3 import test_connection

    result = await test_connection(
        provider_subtype = req.provider_subtype,
        bucket_name      = req.bucket_name,
        access_key       = req.access_key,
        secret_key       = req.secret_key,
        region           = req.region,
        account_id       = req.account_id,
        endpoint_url     = req.endpoint_url,
    )

    if not result["success"]:
        raise HTTPException(400, result["error"])

    enc = vault.encrypt({
        "access_key":    req.access_key,
        "secret_key":    req.secret_key,
        "region":        req.region,
        "endpoint_url":  result.get("endpoint", req.endpoint_url),
    })

    label = req.label or f"{req.provider_subtype.upper()} / {req.bucket_name}"

    conn = ProviderConnection(
        provider_type  = req.provider_subtype,
        auth_method    = "key",
        account_label  = label,
        encrypted_data = enc,
        status         = "connected",
        last_sync_at   = datetime.utcnow(),
        extra_config   = {
            "bucket_name":   req.bucket_name,
            "region":        req.region,
            "endpoint_url":  result.get("endpoint", ""),
            "account_id":    req.account_id,
        },
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    logger.info(f"VIT Connect: {req.provider_subtype} wizard connected — {label}")
    return _conn_to_out(conn)


# ─── Health refresh ────────────────────────────────────────────────────

@router.post("/connections/{conn_id}/refresh-health", summary="Force a health check on a connection")
async def refresh_health(conn_id: str, db: AsyncSession = Depends(get_db)):
    import time
    c = await db.get(ProviderConnection, conn_id)
    if not c or not c.is_active:
        raise HTTPException(404, "Connection not found")

    t0 = time.monotonic()
    try:
        tokens = vault.decrypt(c.encrypted_data)

        if c.provider_type == "google_drive" and tokens.get("access_token"):
            import httpx
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    "https://www.googleapis.com/drive/v3/about?fields=storageQuota",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"}
                )
            latency = int((time.monotonic() - t0) * 1000)
            if r.is_success:
                q = r.json().get("storageQuota", {})
                c.health_score        = 98
                c.storage_quota_bytes = int(q.get("limit", 0))  or c.storage_quota_bytes
                c.storage_used_bytes  = int(q.get("usageInDrive", 0)) or c.storage_used_bytes
                c.status              = "connected"
            else:
                c.health_score = 0
                c.status = "expired" if r.status_code == 401 else "error"
            c.latency_ms   = latency
            c.last_sync_at = datetime.utcnow()

        elif c.provider_type == "dropbox" and tokens.get("access_token"):
            import httpx
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.post(
                    "https://api.dropboxapi.com/2/users/get_space_usage",
                    headers={"Authorization": f"Bearer {tokens['access_token']}", "Content-Type": "application/json"},
                    content=b"null"
                )
            latency = int((time.monotonic() - t0) * 1000)
            c.latency_ms   = latency
            c.last_sync_at = datetime.utcnow()
            if r.is_success:
                sp = r.json()
                c.health_score     = 98
                c.status           = "connected"
                c.storage_used_bytes = sp.get("used")
                c.storage_quota_bytes = sp.get("allocation", {}).get("allocated")
            else:
                c.health_score = 0
                c.status = "expired" if r.status_code == 401 else "error"

        else:
            # Generic ping: just mark a successful vault decrypt
            c.health_score = 90
            c.latency_ms   = int((time.monotonic() - t0) * 1000)
            c.last_sync_at = datetime.utcnow()

    except Exception as exc:
        logger.warning(f"Health check for {conn_id} failed: {exc}")
        c.health_score = 0
        c.status       = "error"
        c.latency_ms   = int((time.monotonic() - t0) * 1000)

    await db.commit()
    return _conn_to_out(c)
