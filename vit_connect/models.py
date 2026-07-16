"""
VIT Connect — provider connection persistence model.
All credentials are stored encrypted; raw tokens never touch the frontend.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, JSON

# Share the same declarative Base so init_db() picks this table up automatically.
from tachyon.core.models import Base


class ProviderConnection(Base):
    __tablename__ = "provider_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Which provider / auth style
    provider_type  = Column(String(32),  nullable=False)   # google_drive | dropbox | onedrive | s3 | r2 | backblaze | local
    auth_method    = Column(String(16),  nullable=False)   # oauth | key
    account_label  = Column(String(128), nullable=True)    # display name, e.g. "Personal Gmail"
    account_email  = Column(String(255), nullable=True)    # populated from OAuth userinfo

    # Credential store (Fernet-encrypted JSON blob)
    encrypted_data = Column(Text, nullable=False)

    # OAuth metadata
    scopes     = Column(JSON,   nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Runtime health
    status            = Column(String(16),  default="connected")   # connected | expired | error | disconnected
    health_score      = Column(Integer,     nullable=True)          # 0-100
    storage_quota_bytes = Column(Integer,   nullable=True)
    storage_used_bytes  = Column(Integer,   nullable=True)
    latency_ms        = Column(Integer,     nullable=True)
    last_sync_at      = Column(DateTime,    nullable=True)

    # S3-compatible wizard extras (bucket, region, endpoint_url, …)
    extra_config = Column(JSON, nullable=True)

    is_active  = Column(Boolean,  default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
