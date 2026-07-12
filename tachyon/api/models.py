from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class FragmentMetadata(BaseModel):
    name: str
    provider: str
    size: int
    checksum: Optional[str] = None

class FileMetadata(BaseModel):
    file_id: str
    filename: str
    total_size: int
    fragments: List[FragmentMetadata]
    redundancy_ratio: float = 1.5
    created_at: Optional[str] = None
    content_type: Optional[str] = None
    tags: Optional[List[str]] = None
    health_score: Optional[float] = None

class UploadResponse(BaseModel):
    file_id: str
    status: str
    fragments_count: int
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

class DownloadResponse(BaseModel):
    data: str  # Base64 encoded or URL

class SharedLinkCreate(BaseModel):
    file_id: str
    link_type: str = "public"          # public | password
    password: Optional[str] = None
    expires_hours: Optional[int] = 24  # None = no expiry
    download_limit: Optional[int] = None

class SharedLinkResponse(BaseModel):
    id: str
    file_id: str
    filename: str
    token: str
    url: str
    link_type: str
    expires_at: Optional[str] = None
    download_count: int = 0
    download_limit: Optional[int] = None
    created_at: str

class NodeInfo(BaseModel):
    id: str
    name: str
    type: str
    healthy: bool
    quarantined: bool
    usage_pct: float
    ping_ms: Optional[int] = None
    capabilities: Optional[List[str]] = None

class StorageStats(BaseModel):
    total_files: int
    total_bytes: int
    active_nodes: int
    erasure_ratio: float
    recent_failed_uploads: int
    last_verified_manifest: Optional[str] = None

class QuotaInfo(BaseModel):
    used_bytes: int
    total_bytes: int
    used_pct: float
    plan: str

class AdminOverview(BaseModel):
    total_files: int
    total_bytes: int
    active_nodes: int
    db_status: str
    redis_status: str
    version: str
    uptime_info: str

class WalletInfo(BaseModel):
    address: str
    vit_balance: float
    storage_credits: float
    plan: str
    staked_vit: float
    ai_requests_today: int
    ai_requests_limit: int

class BatchDeleteRequest(BaseModel):
    file_ids: List[str] = Field(..., min_length=1, max_length=100)

class BatchDeleteResult(BaseModel):
    file_id: str
    success: bool
    error: Optional[str] = None

class BatchDeleteResponse(BaseModel):
    results: List[BatchDeleteResult]
    deleted: int
    failed: int

class UploadFromUrlRequest(BaseModel):
    url: str
    filename: Optional[str] = None
    tags: Optional[List[str]] = None

class VerifyResponse(BaseModel):
    file_id: str
    verified: bool
    shards_checked: int
    shards_healthy: int
    health_score: float
    degraded: bool

class ProviderCapabilities(BaseModel):
    provider_id: str
    name: str
    provider_type: str
    capabilities: List[str]
    healthy: bool
    quarantined: bool
    usage_pct: float

class RegisterProviderRequest(BaseModel):
    provider_type: str = Field(..., description="s3 | dropbox | gdrive | onedrive | disk")
    provider_id: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)

class RegisterProviderResponse(BaseModel):
    provider_id: str
    provider_type: str
    registered: bool
    healthy: bool
    message: str
