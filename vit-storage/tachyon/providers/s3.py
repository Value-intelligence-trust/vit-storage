import os
import io
import shutil
import hashlib
import logging
import asyncio
from typing import Optional, List, AsyncIterator, Dict, Any
from tachyon.providers.base import CloudProvider
from tachyon.providers.exceptions import FileNotFoundError, StorageError

logger = logging.getLogger(__name__)

class S3Provider(CloudProvider):
    """
    S3-Compatible Object Storage Provider for Tachyon Fabric.
    Utilizes boto3 for high-performance connections. Supports fallbacks
    to local mock storage for flawless offline test execution.
    """

    def __init__(self, account_id: str, credentials: Optional[dict] = None):
        self.account_id = account_id
        self.name = account_id
        self._credentials = credentials or {}

        # Load configs
        self.endpoint_url = self._credentials.get("endpoint_url") or os.getenv("S3_ENDPOINT_URL")
        self.access_key = self._credentials.get("access_key") or os.getenv("S3_ACCESS_KEY_ID")
        self.secret_key = self._credentials.get("secret_key") or os.getenv("S3_SECRET_ACCESS_KEY")
        self.bucket_name = self._credentials.get("bucket_name") or os.getenv("S3_BUCKET_NAME", f"tachyon-{account_id}")
        self.region = self._credentials.get("region") or os.getenv("S3_REGION", "us-east-1")

        self._s3_client = None
        self._use_mock = not all([self.access_key, self.secret_key])

        if self._use_mock:
            logger.info(f"S3 credentials not complete. Using mock storage for account: {self.account_id}")
            self.mock_dir = os.path.abspath(f"/tmp/tachyon_s3_mock/{account_id}/{self.bucket_name}")
            os.makedirs(self.mock_dir, exist_ok=True)

    def _get_client(self):
        if self._use_mock:
            return None
        if self._s3_client:
            return self._s3_client

        import boto3
        from botocore.config import Config

        session = boto3.session.Session()
        self._s3_client = session.client(
            service_name="s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            config=Config(signature_version="s3v4")
        )
        return self._s3_client

    def _clean_path(self, name: str) -> str:
        if ".." in name or name.startswith("/"):
            raise StorageError(f"Security Warning: Path traversal blocked: {name}", code="path_traversal", status_code=400)
        return name

    async def upload(self, data: bytes, name: str) -> bool:
        key = self._clean_path(name)
        if self._use_mock:
            try:
                file_path = os.path.join(self.mock_dir, key)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(data)
                return True
            except Exception as e:
                logger.error(f"S3 Mock upload failed: {e}")
                return False

        try:
            client = self._get_client()
            def _put():
                client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=data,
                    ContentType="application/octet-stream"
                )
            await asyncio.to_thread(_put)
            return True
        except Exception as e:
            logger.error(f"S3 upload failed [{self.account_id}]: {e}")
            return False

    async def download(self, name: str) -> Optional[bytes]:
        key = self._clean_path(name)
        if self._use_mock:
            file_path = os.path.join(self.mock_dir, key)
            if not os.path.exists(file_path) or os.path.isdir(file_path):
                return None
            with open(file_path, "rb") as f:
                return f.read()

        try:
            client = self._get_client()
            def _get():
                res = client.get_object(Bucket=self.bucket_name, Key=key)
                return res["Body"].read()
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f"S3 download failed [{self.account_id}]: {e}")
            return None

    async def stream(self, name: str) -> AsyncIterator[bytes]:
        key = self._clean_path(name)
        if self._use_mock:
            file_path = os.path.join(self.mock_dir, key)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File {name} not found")
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            return

        client = self._get_client()
        # Stream from real S3
        def _get_stream():
            response = client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"]

        body = await asyncio.to_thread(_get_stream)
        chunk_size = 1024 * 1024
        while True:
            def _read_chunk():
                return body.read(chunk_size)
            chunk = await asyncio.to_thread(_read_chunk)
            if not chunk:
                break
            yield chunk

    async def delete(self, name: str) -> bool:
        key = self._clean_path(name)
        if self._use_mock:
            file_path = os.path.join(self.mock_dir, key)
            try:
                if os.path.exists(file_path):
                    if os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                    else:
                        os.remove(file_path)
                return True
            except Exception as e:
                logger.error(f"S3 Mock delete failed: {e}")
                return False

        try:
            client = self._get_client()
            await asyncio.to_thread(client.delete_object, Bucket=self.bucket_name, Key=key)
            return True
        except Exception as e:
            logger.warning(f"S3 delete failed [{self.account_id}]: {e}")
            return False

    async def rename(self, old_name: str, new_name: str) -> bool:
        src = self._clean_path(old_name)
        dest = self._clean_path(new_name)

        if self._use_mock:
            src_path = os.path.join(self.mock_dir, src)
            dest_path = os.path.join(self.mock_dir, dest)
            try:
                if not os.path.exists(src_path):
                    raise FileNotFoundError(f"Source file {old_name} not found")
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                os.rename(src_path, dest_path)
                return True
            except Exception as e:
                logger.error(f"S3 Mock rename failed: {e}")
                return False

        try:
            if await self.copy(old_name, dest):
                await self.delete(old_name)
                return True
            return False
        except Exception as e:
            logger.error(f"S3 rename failed: {e}")
            return False

    async def copy(self, src_name: str, dest_name: str) -> bool:
        src = self._clean_path(src_name)
        dest = self._clean_path(dest_name)

        if self._use_mock:
            src_path = os.path.join(self.mock_dir, src)
            dest_path = os.path.join(self.mock_dir, dest)
            try:
                if not os.path.exists(src_path):
                    raise FileNotFoundError(f"Source file {src_name} not found")
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dest_path)
                return True
            except Exception as e:
                logger.error(f"S3 Mock copy failed: {e}")
                return False

        try:
            client = self._get_client()
            copy_source = {'Bucket': self.bucket_name, 'Key': src}
            await asyncio.to_thread(client.copy_object, CopySource=copy_source, Bucket=self.bucket_name, Key=dest)
            return True
        except Exception as e:
            logger.error(f"S3 copy failed: {e}")
            return False

    async def exists(self, name: str) -> bool:
        key = self._clean_path(name)
        if self._use_mock:
            return os.path.exists(os.path.join(self.mock_dir, key))

        try:
            client = self._get_client()
            await asyncio.to_thread(client.head_object, Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    async def metadata(self, name: str) -> Dict[str, Any]:
        if not name:
            if self._use_mock:
                total, used, free = shutil.disk_usage(self.mock_dir)
                return {
                    "total_bytes": total,
                    "used_bytes": used,
                    "free_bytes": free,
                    "type": "directory"
                }
            return {
                "total_bytes": 1024 * 1024**3, # 1TB simulation
                "used_bytes": 0,
                "free_bytes": 1024 * 1024**3,
                "type": "directory"
            }

        key = self._clean_path(name)
        if self._use_mock:
            file_path = os.path.join(self.mock_dir, key)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"S3 file {name} not found")
            stat = os.stat(file_path)
            return {
                "name": name,
                "size": stat.st_size,
                "created_at": stat.st_ctime,
                "modified_at": stat.st_mtime,
                "type": "directory" if os.path.isdir(file_path) else "file"
            }

        client = self._get_client()
        try:
            res = await asyncio.to_thread(lambda: client.head_object(Bucket=self.bucket_name, Key=key))
            return {
                "name": name,
                "size": res.get("ContentLength", 0),
                "created_at": res.get("LastModified"),
                "modified_at": res.get("LastModified"),
                "type": "file"
            }
        except Exception as e:
            raise FileNotFoundError(f"S3 file {name} not found: {e}")

    async def checksum(self, name: str) -> str:
        key = self._clean_path(name)
        if self._use_mock:
            file_path = os.path.join(self.mock_dir, key)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"S3 file {name} not found")
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()

        client = self._get_client()
        res = await asyncio.to_thread(lambda: client.head_object(Bucket=self.bucket_name, Key=key))
        etag = res.get("ETag", "").replace('"', '')
        return etag

    async def create_directory(self, path: str) -> bool:
        key = self._clean_path(path)
        if not key.endswith("/"):
            key += "/"
        return await self.upload(b"", key)

    async def delete_directory(self, path: str) -> bool:
        prefix = self._clean_path(path)
        if self._use_mock:
            dir_path = os.path.join(self.mock_dir, prefix)
            try:
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)
                return True
            except Exception:
                return False

        try:
            client = self._get_client()
            def _list():
                return client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            res = await asyncio.to_thread(_list)
            objects = res.get("Contents", [])
            if not objects:
                return True

            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            def _del_batch():
                client.delete_objects(Bucket=self.bucket_name, Delete={"Objects": delete_keys})
            await asyncio.to_thread(_del_batch)
            return True
        except Exception:
            return False

    async def list_directory(self, path: str) -> List[str]:
        prefix = self._clean_path(path) if path else ""
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        if self._use_mock:
            dir_path = os.path.join(self.mock_dir, prefix)
            try:
                if not os.path.exists(dir_path):
                    return []
                if not os.path.isdir(dir_path):
                    return [os.path.basename(dir_path)]
                return os.listdir(dir_path)
            except Exception:
                return []

        try:
            client = self._get_client()
            def _list():
                return client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            res = await asyncio.to_thread(_list)
            contents = res.get("Contents", [])
            results = []
            for item in contents:
                key = item["Key"]
                if key.startswith(prefix):
                    rel = key[len(prefix):]
                    if rel:
                        results.append(rel.split("/")[0])
            return list(set(results))
        except Exception:
            return []

    async def generate_signed_url(self, name: str, expiration: int = 3600) -> str:
        key = self._clean_path(name)
        if self._use_mock:
            file_path = os.path.join(self.mock_dir, key)
            return f"file://{file_path}"

        try:
            client = self._get_client()
            def _url():
                return client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket_name, "Key": key},
                    ExpiresIn=expiration
                )
            return await asyncio.to_thread(_url)
        except Exception:
            return f"https://{self.bucket_name}.s3.amazonaws.com/{key}"

    async def health_check(self) -> bool:
        if self._use_mock:
            return os.path.exists(self.mock_dir)

        try:
            client = self._get_client()
            def _ping():
                return client.head_bucket(Bucket=self.bucket_name)
            await asyncio.to_thread(_ping)
            return True
        except Exception:
            return False
