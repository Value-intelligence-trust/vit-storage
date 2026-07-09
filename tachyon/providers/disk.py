import os
import shutil
import hashlib
import aiofiles
import logging
from typing import Optional, List, AsyncIterator, Dict, Any
from tachyon.providers.base import CloudProvider
from tachyon.providers.exceptions import FileNotFoundError, StorageError

logger = logging.getLogger(__name__)

class DiskProvider(CloudProvider):
    """
    Persistent Local Disk Provider for Tachyon Fabric.
    Stores files in a local folder with path traversal protection.
    """

    def __init__(self, account_id: str, storage_path: str = "/tmp/tachyon_storage"):
        self.account_id = account_id
        self.name = account_id
        self.storage_root = os.path.abspath(storage_path)
        self.storage_path = os.path.abspath(os.path.join(self.storage_root, account_id))
        os.makedirs(self.storage_path, exist_ok=True)

    def _safe_path(self, name: str) -> str:
        """Resolve path and assert it stays within the designated storage_path directory."""
        if ".." in name or name.startswith("/"):
            raise StorageError(f"Security Warning: Path traversal blocked for: {name}", code="path_traversal", status_code=400)
        # Avoid removing double slashes to resolve to absolute
        resolved = os.path.abspath(os.path.join(self.storage_path, name))
        if not resolved.startswith(self.storage_path):
            raise StorageError(f"Security Warning: Sandbox escape blocked for: {name}", code="sandbox_escape", status_code=400)
        return resolved

    async def upload(self, data: bytes, name: str) -> bool:
        try:
            file_path = self._safe_path(name)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data)
            return True
        except Exception as e:
            logger.error(f"Disk upload failed [{self.account_id}]: {e}")
            return False

    async def download(self, name: str) -> Optional[bytes]:
        try:
            file_path = self._safe_path(name)
            if not os.path.exists(file_path) or os.path.isdir(file_path):
                return None
            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Disk download failed [{self.account_id}]: {e}")
            return None

    async def stream(self, name: str) -> AsyncIterator[bytes]:
        file_path = self._safe_path(name)
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            raise FileNotFoundError(f"File {name} not found")

        async with aiofiles.open(file_path, "rb") as f:
            chunk_size = 1024 * 1024 # 1MB
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def delete(self, name: str) -> bool:
        try:
            file_path = self._safe_path(name)
            if os.path.exists(file_path):
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                else:
                    os.remove(file_path)
            return True
        except Exception as e:
            logger.error(f"Disk delete failed [{self.account_id}]: {e}")
            return False

    async def rename(self, old_name: str, new_name: str) -> bool:
        try:
            old_path = self._safe_path(old_name)
            new_path = self._safe_path(new_name)
            if not os.path.exists(old_path):
                raise FileNotFoundError(f"Source file {old_name} not found")
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            os.rename(old_path, new_path)
            return True
        except Exception as e:
            logger.error(f"Disk rename failed [{self.account_id}]: {e}")
            return False

    async def copy(self, src_name: str, dest_name: str) -> bool:
        try:
            src_path = self._safe_path(src_name)
            dest_path = self._safe_path(dest_name)
            if not os.path.exists(src_path):
                raise FileNotFoundError(f"Source file {src_name} not found")
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dest_path)
            return True
        except Exception as e:
            logger.error(f"Disk copy failed [{self.account_id}]: {e}")
            return False

    async def exists(self, name: str) -> bool:
        try:
            file_path = self._safe_path(name)
            return os.path.exists(file_path)
        except Exception:
            return False

    async def metadata(self, name: str) -> Dict[str, Any]:
        if not name:
            # Return storage space details
            total, used, free = shutil.disk_usage(self.storage_path)
            return {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "type": "directory"
            }

        file_path = self._safe_path(name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {name} not found")

        stat = os.stat(file_path)
        return {
            "name": name,
            "size": stat.st_size,
            "created_at": stat.st_ctime,
            "modified_at": stat.st_mtime,
            "type": "directory" if os.path.isdir(file_path) else "file"
        }

    async def checksum(self, name: str) -> str:
        file_path = self._safe_path(name)
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            raise FileNotFoundError(f"File {name} not found")

        h = hashlib.sha256()
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    async def create_directory(self, path: str) -> bool:
        try:
            dir_path = self._safe_path(path)
            os.makedirs(dir_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Disk create_directory failed [{self.account_id}]: {e}")
            return False

    async def delete_directory(self, path: str) -> bool:
        try:
            dir_path = self._safe_path(path)
            if os.path.exists(dir_path):
                if os.path.isdir(dir_path):
                    shutil.rmtree(dir_path)
                else:
                    os.remove(dir_path)
            return True
        except Exception as e:
            logger.error(f"Disk delete_directory failed [{self.account_id}]: {e}")
            return False

    async def list_directory(self, path: str) -> List[str]:
        try:
            dir_path = self._safe_path(path) if path else self.storage_path
            if not os.path.exists(dir_path):
                return []
            if not os.path.isdir(dir_path):
                return [os.path.basename(dir_path)]
            return os.listdir(dir_path)
        except Exception as e:
            logger.error(f"Disk list_directory failed [{self.account_id}]: {e}")
            return []

    async def generate_signed_url(self, name: str, expiration: int = 3600) -> str:
        file_path = self._safe_path(name)
        return f"file://{file_path}"

    async def health_check(self) -> bool:
        try:
            test_file = f".health_check_test"
            file_path = os.path.join(self.storage_path, test_file)
            with open(file_path, "w") as f:
                f.write("ok")
            os.remove(file_path)
            return True
        except Exception:
            return False
