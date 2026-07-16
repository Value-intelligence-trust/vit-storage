"""
Dropbox OAuth2 web flow for VIT Connect.
Requires env vars: DROPBOX_APP_KEY, DROPBOX_APP_SECRET
"""
import os
import logging
import httpx
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_AUTH_URL    = "https://www.dropbox.com/oauth2/authorize"
_TOKEN_URL   = "https://api.dropbox.com/oauth2/token"
_ACCOUNT_URL = "https://api.dropboxapi.com/2/users/get_current_account"
_SPACE_URL   = "https://api.dropboxapi.com/2/users/get_space_usage"


def is_configured() -> bool:
    return bool(os.getenv("DROPBOX_APP_KEY")) and bool(os.getenv("DROPBOX_APP_SECRET"))


def get_authorize_url(redirect_uri: str, state: str) -> str | None:
    app_key = os.getenv("DROPBOX_APP_KEY")
    if not app_key:
        return None
    params = {
        "client_id":         app_key,
        "response_type":     "code",
        "redirect_uri":      redirect_uri,
        "state":             state,
        "token_access_type": "offline",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> dict:
    app_key    = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(_TOKEN_URL, data={
            "code":         code,
            "grant_type":   "authorization_code",
            "redirect_uri": redirect_uri,
        }, auth=(app_key, app_secret))
        r.raise_for_status()
        return r.json()


async def get_account_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        # Dropbox uses POST with empty JSON body for this endpoint
        r = await c.post(_ACCOUNT_URL,
                         headers={"Authorization": f"Bearer {access_token}",
                                  "Content-Type":  "application/json"},
                         content=b"null")
        if r.is_success:
            return r.json()
        return {}


async def get_space_usage(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(_SPACE_URL,
                         headers={"Authorization": f"Bearer {access_token}",
                                  "Content-Type":  "application/json"},
                         content=b"null")
        if r.is_success:
            return r.json()
        return {}
