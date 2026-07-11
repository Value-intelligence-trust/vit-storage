from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class FileEntry(Base):
    """Normalization track file model for standalone tracking."""
    __tablename__ = "files"
    id = Column(String(36), primary_key=True)
    filename = Column(String(512), nullable=False)
    total_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    fragments = relationship("FragmentEntry", back_populates="file", cascade="all, delete-orphan")

class FragmentEntry(Base):
    """Normalization track fragment model for standalone tracking."""
    __tablename__ = "fragments"
    id = Column(String(36), primary_key=True)
    file_id = Column(String(36), ForeignKey("files.id", ondelete="CASCADE"))
    provider = Column(String(128), nullable=False)
    name = Column(String(512), nullable=False)
    size = Column(Integer, nullable=False)
    checksum = Column(String(128))
    file = relationship("FileEntry", back_populates="fragments")

class TachyonManifest(Base):
    """
    Backwards-compatible manifest schema identical to legacy app database model.
    Enables dual-parsing and direct deployment synchronisation.
    """
    __tablename__ = "tachyon_manifests"

    file_id = Column(String(36), primary_key=True)
    filename = Column(String(512), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    fragment_names = Column(JSON, nullable=False)
    provider_mapping = Column(JSON, nullable=False)
    owner_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SharedLink(Base):
    """Shared file link records for the Shared Links tab."""
    __tablename__ = "shared_links"

    id = Column(String(36), primary_key=True)
    file_id = Column(String(36), nullable=False)
    filename = Column(String(512), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    link_type = Column(String(16), default="public")      # public | password
    password_hash = Column(String(128), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    download_count = Column(Integer, default=0)
    download_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
