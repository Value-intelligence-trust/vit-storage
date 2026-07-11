from abc import ABC, abstractmethod
from typing import Optional, List, AsyncIterator, Dict, Any

class CloudProvider(ABC):
    account_id: str
    name: str

    @abstractmethod
    async def upload(self, data: bytes, name: str) -> bool:
        """Upload a file/shard to the provider."""
        ...

    @abstractmethod
    async def download(self, name: str) -> Optional[bytes]:
        """Download a file/shard from the provider."""
        ...

    @abstractmethod
    async def stream(self, name: str) -> AsyncIterator[bytes]:
        """Stream a file/shard from the provider."""
        ...

    @abstractmethod
    async def delete(self, name: str) -> bool:
        """Delete a file/shard from the provider."""
        ...

    @abstractmethod
    async def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a file/shard in the provider."""
        ...

    @abstractmethod
    async def copy(self, src_name: str, dest_name: str) -> bool:
        """Copy a file/shard in the provider."""
        ...

    @abstractmethod
    async def exists(self, name: str) -> bool:
        """Check if a file/shard exists in the provider."""
        ...

    @abstractmethod
    async def metadata(self, name: str) -> Dict[str, Any]:
        """Get metadata for a file/shard, or quota for empty name."""
        ...

    @abstractmethod
    async def checksum(self, name: str) -> str:
        """Get the hash/checksum of a file/shard."""
        ...

    @abstractmethod
    async def create_directory(self, path: str) -> bool:
        """Create a directory in the provider."""
        ...

    @abstractmethod
    async def delete_directory(self, path: str) -> bool:
        """Delete a directory and all of its contents."""
        ...

    @abstractmethod
    async def list_directory(self, path: str) -> List[str]:
        """List the contents of a directory."""
        ...

    @abstractmethod
    async def generate_signed_url(self, name: str, expiration: int = 3600) -> str:
        """Generate a temporary signed URL for a file."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Perform a quick health/ping check on the provider."""
        ...

    # --- Backwards Compatibility Shims (Legacy Interface) ---

    async def upload_fragment(self, data: bytes, name: str) -> bool:
        return await self.upload(data, name)

    async def download_fragment(self, name: str) -> Optional[bytes]:
        return await self.download(name)

    async def delete_fragment(self, name: str) -> bool:
        return await self.delete(name)

    async def list_fragments(self) -> List[str]:
        return await self.list_directory("")

    async def get_quota(self) -> dict:
        meta = await self.metadata("")
        return {
            "total": meta.get("total_bytes", 10 * 1024**3),
            "used": meta.get("used_bytes", 0)
        }

    async def get_latency(self) -> float:
        import time
        t0 = time.monotonic()
        try:
            await self.health_check()
            return (time.monotonic() - t0) * 1000
        except Exception:
            return 9999.0

    # --- Backwards Compatibility Shims (Core Shard Interface) ---

    async def upload_shard(self, shard_id: str, data: bytes) -> str:
        success = await self.upload(data, shard_id)
        if not success:
            raise RuntimeError(f"Shard upload failed for {shard_id}")
        return shard_id

    async def download_shard(self, file_id: str) -> bytes:
        res = await self.download(file_id)
        if res is None:
            raise RuntimeError(f"Shard download failed for {file_id}")
        return res

    async def delete_shard(self, file_id: str) -> bool:
        return await self.delete(file_id)

    async def get_usage(self) -> dict:
        meta = await self.metadata("")
        limit = meta.get("total_bytes", 10 * 1024**3)
        used = meta.get("used_bytes", 0)
        return {
            "used_bytes": used,
            "quota_bytes": limit,
            "available_bytes": max(0, limit - used)
        }
