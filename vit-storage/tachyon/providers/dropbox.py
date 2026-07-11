import os
import io
import logging
import asyncio
from typing import Optional, List, AsyncIterator, Dict, Any
from tachyon.providers.base import CloudProvider
from tachyon.providers.exceptions import FileNotFoundError, StorageError

logger = logging.getLogger(__name__)

class DropboxProvider(CloudProvider):
    """
    Consolidated Production-Grade Dropbox Provider for Tachyon Fabric.
    Integrates support for continuous offline OAuth2 refresh token flow
    with threadpool isolation, path-traversal checks, and standard folder mappings.
    """

    def __init__(self, account_id: str, credentials: Optional[dict] = None):
        self.account_id = account_id
        self.name = account_id
        self._credentials = credentials or {}
        self._dbx = None

    def _get_client(self):
        if self._dbx:
            return self._dbx

        import dropbox

        # 1. Check passed credentials dict
        access_token = self._credentials.get("access_token") or os.getenv("DROPBOX_ACCESS_TOKEN")
        app_key = self._credentials.get("app_key") or os.getenv("DROPBOX_APP_KEY")
        app_secret = self._credentials.get("app_secret") or os.getenv("DROPBOX_APP_SECRET")
        refresh_token = self._credentials.get("refresh_token") or os.getenv("DROPBOX_REFRESH_TOKEN")

        # 2. Prefer continuous offline refresh token authorization
        if refresh_token and app_key and app_secret:
            logger.info(f"Initializing Dropbox with OAuth2 refresh token for account: {self.account_id}")
            self._dbx = dropbox.Dropbox(
                oauth2_refresh_token=refresh_token,
                app_key=app_key,
                app_secret=app_secret
            )
        elif access_token:
            logger.info(f"Initializing Dropbox with static access token for account: {self.account_id}")
            self._dbx = dropbox.Dropbox(access_token)
        else:
            raise RuntimeError(f"Dropbox credentials not configured for account {self.account_id}")

        return self._dbx

    def _clean_path(self, name: str) -> str:
        if ".." in name or name.startswith("/"):
            raise StorageError(f"Security Warning: Path traversal blocked: {name}", code="path_traversal", status_code=400)
        # Dropbox expects root directory paths to start with / but relative files like /tachyon/name are absolute from root
        return f"/tachyon/{name}" if name else "/tachyon"

    async def upload(self, data: bytes, name: str) -> bool:
        path = self._clean_path(name)
        try:
            dbx = self._get_client()
            import dropbox
            def _upload():
                # WriteMode.overwrite replaces existing file completely
                dbx.files_upload(
                    data,
                    path,
                    mode=dropbox.files.WriteMode.overwrite,
                    mute=True
                )
            await asyncio.to_thread(_upload)
            return True
        except Exception as e:
            logger.error(f"Dropbox upload failed [{self.account_id}]: {e}")
            return False

    async def download(self, name: str) -> Optional[bytes]:
        path = self._clean_path(name)
        try:
            dbx = self._get_client()
            def _download():
                _, res = dbx.files_download(path)
                return res.content
            return await asyncio.to_thread(_download)
        except Exception as e:
            logger.error(f"Dropbox download failed [{self.account_id}]: {e}")
            return None

    async def stream(self, name: str) -> AsyncIterator[bytes]:
        path = self._clean_path(name)
        dbx = self._get_client()

        def _download():
            _, res = dbx.files_download(path)
            return res.content

        # Dropbox API download is standard blocking. We fetch fully and stream in chunks.
        content = await asyncio.to_thread(_download)
        chunk_size = 1024 * 1024
        for i in range(0, len(content), chunk_size):
            yield content[i:i+chunk_size]

    async def delete(self, name: str) -> bool:
        path = self._clean_path(name)
        try:
            dbx = self._get_client()
            def _del():
                dbx.files_delete_v2(path)
            await asyncio.to_thread(_del)
            return True
        except Exception as e:
            logger.warning(f"Dropbox delete failed [{self.account_id}] for {name}: {e}")
            return False

    async def rename(self, old_name: str, new_name: str) -> bool:
        old_path = self._clean_path(old_name)
        new_path = self._clean_path(new_name)
        try:
            dbx = self._get_client()
            def _ren():
                dbx.files_move_v2(old_path, new_path)
            await asyncio.to_thread(_ren)
            return True
        except Exception as e:
            logger.error(f"Dropbox rename failed [{self.account_id}]: {e}")
            return False

    async def copy(self, src_name: str, dest_name: str) -> bool:
        src_path = self._clean_path(src_name)
        dest_path = self._clean_path(dest_name)
        try:
            dbx = self._get_client()
            def _cp():
                dbx.files_copy_v2(src_path, dest_path)
            await asyncio.to_thread(_cp)
            return True
        except Exception as e:
            logger.error(f"Dropbox copy failed [{self.account_id}]: {e}")
            return False

    async def exists(self, name: str) -> bool:
        path = self._clean_path(name)
        try:
            dbx = self._get_client()
            def _meta():
                return dbx.files_get_metadata(path)
            await asyncio.to_thread(_meta)
            return True
        except Exception:
            return False

    async def metadata(self, name: str) -> Dict[str, Any]:
        dbx = self._get_client()
        if not name:
            # Get space usage for capacity mapping
            def _space():
                return dbx.users_get_space_usage()
            usage = await asyncio.to_thread(_space)
            alloc = usage.allocation.get_individual()
            total = alloc.allocated
            used = usage.used
            return {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": max(0, total - used),
                "type": "directory"
            }

        path = self._clean_path(name)
        import dropbox
        try:
            def _meta():
                return dbx.files_get_metadata(path)
            res = await asyncio.to_thread(_meta)
            is_folder = isinstance(res, dropbox.files.FolderMetadata)
            return {
                "name": res.name,
                "size": res.size if not is_folder else 0,
                "created_at": getattr(res, "client_modified", None),
                "modified_at": getattr(res, "server_modified", None),
                "type": "directory" if is_folder else "file"
            }
        except Exception as e:
            raise FileNotFoundError(f"File {name} metadata not found: {e}")

    async def checksum(self, name: str) -> str:
        path = self._clean_path(name)
        dbx = self._get_client()
        try:
            def _meta():
                return dbx.files_get_metadata(path)
            res = await asyncio.to_thread(_meta)
            return getattr(res, "content_hash", "")
        except Exception as e:
            raise FileNotFoundError(f"File {name} not found: {e}")

    async def create_directory(self, path: str) -> bool:
        dir_path = self._clean_path(path)
        try:
            dbx = self._get_client()
            def _create():
                dbx.files_create_folder_v2(dir_path)
            await asyncio.to_thread(_create)
            return True
        except Exception as e:
            logger.warning(f"Dropbox create_directory failed [{self.account_id}]: {e}")
            return True # Usually already exists

    async def delete_directory(self, path: str) -> bool:
        return await self.delete(path)

    async def list_directory(self, path: str) -> List[str]:
        dir_path = self._clean_path(path)
        try:
            dbx = self._get_client()
            def _list():
                res = dbx.files_list_folder(dir_path)
                return [entry.name for entry in res.entries]
            return await asyncio.to_thread(_list)
        except Exception as e:
            logger.error(f"Dropbox list_directory failed [{self.account_id}]: {e}")
            return []

    async def generate_signed_url(self, name: str, expiration: int = 3600) -> str:
        path = self._clean_path(name)
        dbx = self._get_client()
        try:
            # Attempt to create shared link
            def _link():
                try:
                    return dbx.sharing_create_shared_link_with_settings(path).url
                except Exception:
                    # If already exists, list links and return the first
                    links = dbx.sharing_list_shared_links(path=path, direct_only=True).links
                    if links:
                        return links[0].url
                    raise
            return await asyncio.to_thread(_link)
        except Exception as e:
            logger.error(f"Dropbox generate_signed_url failed: {e}")
            # Fallback to direct download temporary link
            def _temp():
                return dbx.files_get_temporary_link(path).link
            try:
                return await asyncio.to_thread(_temp)
            except Exception:
                return f"https://www.dropbox.com/home/tachyon/{name}"

    async def health_check(self) -> bool:
        try:
            dbx = self._get_client()
            def _ping():
                return dbx.users_get_current_account()
            await asyncio.to_thread(_ping)
            return True
        except Exception:
            return False
