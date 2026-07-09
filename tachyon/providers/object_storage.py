import logging
from typing import Optional
from tachyon.providers.s3 import S3Provider

logger = logging.getLogger(__name__)

class ObjectStorageProvider(S3Provider):
    """
    General Object Storage Provider for Tachyon Fabric.
    Maps directly to S3-compatible interfaces (such as Cloudflare R2, MinIO,
    Backblaze B2) to prevent any code duplication while keeping configuration distinct.
    """

    def __init__(self, account_id: str, credentials: Optional[dict] = None):
        logger.info(f"Initializing general ObjectStorageProvider for account: {account_id}")
        super().__init__(account_id, credentials)
