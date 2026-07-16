"""
S3-compatible connection wizard for VIT Connect.
Supports: Amazon S3, Cloudflare R2, Backblaze B2, generic S3-compatible endpoints.
Uses httpx — no boto3 required.
"""
import hmac
import hashlib
import datetime
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

PROVIDER_DEFAULTS = {
    "s3":        {"endpoint": None,          "region": "us-east-1"},
    "r2":        {"endpoint": "https://{account_id}.r2.cloudflarestorage.com", "region": "auto"},
    "backblaze": {"endpoint": "https://s3.{region}.backblazeb2.com",           "region": "us-west-004"},
}


def _build_endpoint(provider_subtype: str, region: str, account_id: str = "") -> str:
    defaults = PROVIDER_DEFAULTS.get(provider_subtype, {})
    tpl = defaults.get("endpoint") or ""
    if not tpl:
        return f"https://s3.{region}.amazonaws.com"
    return tpl.format(account_id=account_id, region=region)


def _sign_headers(
    method: str,
    bucket: str,
    access_key: str,
    secret_key: str,
    region: str,
    endpoint_host: str,
) -> dict:
    """
    Minimal SigV4 signing for a HEAD /{bucket} request.
    Returns headers dict including Authorization.
    """
    now = datetime.datetime.utcnow()
    datestamp  = now.strftime("%Y%m%d")
    amzdate    = now.strftime("%Y%m%dT%H%M%SZ")
    service    = "s3"
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"

    headers_to_sign = {
        "host":                 endpoint_host,
        "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "x-amz-date":           amzdate,
    }
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted(headers_to_sign.items()))
    signed_headers    = ";".join(sorted(headers_to_sign.keys()))

    canonical_request = "\n".join([
        method.upper(),
        f"/{bucket}",
        "",
        canonical_headers,
        signed_headers,
        headers_to_sign["x-amz-content-sha256"],
    ])

    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amzdate,
        credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _hmac(
        _hmac(
            _hmac(
                _hmac(f"AWS4{secret_key}".encode(), datestamp),
                region,
            ),
            service,
        ),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        **{k: v for k, v in headers_to_sign.items() if k != "host"},
        "Authorization": authorization,
    }


async def test_connection(
    provider_subtype: str,
    bucket_name: str,
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
    account_id: str = "",
    endpoint_url: str = "",
) -> dict:
    """
    Attempt a HEAD request to the bucket using SigV4.
    Returns {"success": True, ...} or {"success": False, "error": "..."}.
    """
    try:
        endpoint = endpoint_url.rstrip("/") if endpoint_url else _build_endpoint(provider_subtype, region, account_id)
        from urllib.parse import urlparse
        host = urlparse(endpoint).netloc or endpoint
        url  = f"{endpoint}/{bucket_name}"

        headers = _sign_headers("HEAD", bucket_name, access_key, secret_key, region, host)

        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            r = await c.head(url, headers=headers)

        if r.status_code in (200, 204, 301, 307):
            return {"success": True, "bucket": bucket_name, "region": region, "endpoint": endpoint}
        elif r.status_code == 403:
            return {"success": False, "error": "Access denied — check your Access Key and Secret Key."}
        elif r.status_code == 404:
            return {"success": False, "error": f"Bucket '{bucket_name}' not found."}
        else:
            return {"success": False, "error": f"Unexpected response: HTTP {r.status_code}"}

    except httpx.ConnectError as e:
        return {"success": False, "error": f"Could not connect to endpoint: {e}"}
    except httpx.TimeoutException:
        return {"success": False, "error": "Connection timed out — check endpoint URL."}
    except Exception as e:
        return {"success": False, "error": str(e)}
