"""
Google Drive OAuth2 web flow for VIT Connect.
Requires env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
"""
import os
import logging
import httpx
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL    = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_DRIVE_URL    = "https://www.googleapis.com/drive/v3/about?fields=storageQuota"

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def is_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID")) and bool(os.getenv("GOOGLE_CLIENT_SECRET"))


def get_authorize_url(redirect_uri: str, state: str) -> str | None:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        return None
    params = {
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> dict:
    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(_TOKEN_URL, data={
            "code":          code,
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        r.raise_for_status()
        return r.json()


async def get_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        return r.json()


async def get_drive_quota(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(_DRIVE_URL, headers={"Authorization": f"Bearer {access_token}"})
        if r.is_success:
            return r.json().get("storageQuota", {})
        return {}


async def refresh_access_token(refresh_token: str) -> dict:
    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id":     client_id,
            "client_secret": client_secret,
            "grant_type":    "refresh_token",
        })
        r.raise_for_status()
        return r.json()
