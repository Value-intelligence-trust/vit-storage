"""
VIT Connect Credential Vault
Fernet symmetric encryption for provider tokens / keys.
Key is loaded from the CONNECT_VAULT_KEY environment variable.
"""
import os
import json
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.getenv("CONNECT_VAULT_KEY", "").strip()
    if not key:
        key = Fernet.generate_key().decode()
        os.environ["CONNECT_VAULT_KEY"] = key
        logger.warning(
            "CONNECT_VAULT_KEY not set — using a one-time ephemeral key. "
            "All stored credentials will be unreadable after process restart. "
            "Set CONNECT_VAULT_KEY to a 32-byte URL-safe base64 key for production."
        )

    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt(data: dict) -> str:
    """Encrypt a dict to a URL-safe base64 Fernet token string."""
    return _get_fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt(token: str) -> dict:
    """Decrypt a Fernet token back to a dict. Raises InvalidToken on tampering."""
    try:
        return json.loads(_get_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise ValueError("Credential vault: decryption failed — token may be corrupt or from a different key.") from exc
