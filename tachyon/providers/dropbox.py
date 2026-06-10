import os
import asyncio
import logging
from typing import Optional
from tachyon.providers.base import CloudProvider

logger = logging.getLogger(__name__)

class DropboxProvider(CloudProvider):
    """Dropbox provider using access token."""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self._token = os.getenv("DROPBOX_ACCESS_TOKEN")
        self._dbx = None

    def _get_client(self):
        if self._dbx:
            return self._dbx
        if not self._token:
            raise RuntimeError("DROPBOX_ACCESS_TOKEN env var not set")
        import dropbox
        self._dbx = dropbox.Dropbox(self._token)
        return self._dbx

    async def upload_fragment(self, data: bytes, name: str) -> bool:
        try:
            dbx = self._get_client()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: dbx.files_upload(data, f"/tachyon/{name}", mute=True))
            return True
        except Exception as e:
            logger.error(f"Dropbox upload failed [{self.account_id}]: {e}")
            return False

    async def download_fragment(self, name: str) -> Optional[bytes]:
        try:
            dbx = self._get_client()
            loop = asyncio.get_event_loop()
            _, res = await loop.run_in_executor(None, lambda: dbx.files_download(f"/tachyon/{name}"))
            return res.content
        except Exception as e:
            logger.error(f"Dropbox download failed [{self.account_id}]: {e}")
            return None

    async def get_quota(self) -> dict:
        try:
            dbx = self._get_client()
            loop = asyncio.get_event_loop()
            usage = await loop.run_in_executor(None, dbx.users_get_space_usage)
            alloc = usage.allocation.get_individual()
            return {"total": alloc.allocated, "used": usage.used}
        except Exception:
            return {"total": 0, "used": 0}

    async def get_latency(self) -> float:
        import time
        t = time.monotonic()
        try:
            dbx = self._get_client()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, dbx.users_get_current_account)
        except Exception:
            pass
        return (time.monotonic() - t) * 1000
