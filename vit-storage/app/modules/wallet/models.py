from sqlalchemy import Column, String, JSON
from tachyon.core.models import Base

class PlatformConfig(Base):
    """Configuration mapping matching legacy wallet platform variables."""
    __tablename__ = "platform_configs"

    key = Column(String(255), primary_key=True)
    value = Column(JSON, nullable=False)
