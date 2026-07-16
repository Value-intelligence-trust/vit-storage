"""
Microsoft OneDrive OAuth2 web flow for VIT Connect.
Requires env vars: ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET
"""
import os
import logging
import httpx
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_AUTH_URL  = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_ME_URL    = "https://graph.microsoft.com/v1.0/me"
_DRIVE_URL = "https://graph.microsoft.com/v1.0/me/drive"

SCOPES = ["Files.ReadWrite", "User.Read", "offline_access"]


def is_configured() -> bool:
    return bool(os.getenv("ONEDRIVE_CLIENT_ID")) and bool(os.getenv("ONEDRIVE_CLIENT_SECRET"))


def get_authorize_url(redirect_uri: str, state: str) -> str | None:
    client_id = os.getenv("ONEDRIVE_CLIENT_ID")
    if not client_id:
        return None
    params = {
        "client_id":     client_id,
        "response_type": "code",
        "redirect_uri":  redirect_uri,
        "scope":         " ".join(SCOPES),
        "state":         state,
        "response_mode": "query",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> dict:
    client_id     = os.getenv("ONEDRIVE_CLIENT_ID")
    client_secret = os.getenv("ONEDRIVE_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(_TOKEN_URL, data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "code":          code,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        r.raise_for_status()
        return r.json()


async def get_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(_ME_URL, headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        return r.json()


async def get_drive_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(_DRIVE_URL, headers={"Authorization": f"Bearer {access_token}"})
        if r.is_success:
            return r.json()
        return {}


async def refresh_token(refresh_tok: str) -> dict:
    client_id     = os.getenv("ONEDRIVE_CLIENT_ID")
    client_secret = os.getenv("ONEDRIVE_CLIENT_SECRET")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(_TOKEN_URL, data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_tok,
            "grant_type":    "refresh_token",
        })
        r.raise_for_status()
        return r.json()
