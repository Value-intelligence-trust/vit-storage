# Provider Configuration Specification

This guide describes how to configure cloud and local storage backend providers inside the canonical `vit-storage` service.

---

## ⚙️ Centralized Configuration Structure

We use **Pydantic Settings** (under `tachyon/core/config.py`) to parse, validate, and load environment variables. This prevents environment leakages and structures authentication keys cleanly.

---

## 🔑 Reference Environment Variable Matrix

| Backend Provider | Environment Variable Name | Format / Schema Requirement | Description |
| :--- | :--- | :--- | :--- |
| **Global Plane** | `PORT` | `int` (default `8080`) | Listening port of the FastAPI coordination app. |
| | `ENVIRONMENT` | `string` (`"development"`, `"production"`) | Application deployment state. |
| | `DATABASE_URL` | `string` (e.g. `postgresql+asyncpg://...` or `sqlite+aiosqlite://...`) | Connection URL for tracking files and fragment schemas. |
| | `REDIS_URL` | `string` (e.g. `redis://...`) | Optional URL to dispatch manifest degradation pubsub events. |
| **Google Drive** | `GDRIVE_SERVICE_ACCOUNT_JSON` | Raw SA JSON string or Base64-encoded string | Singleton Service Account key used for primary actions. |
| | `GDRIVE_SERVICE_ACCOUNT_KEYS` | JSON-encoded array of SA structures | Used by ProviderRegistry to load multiple Google Drive nodes. |
| **Dropbox** | `DROPBOX_ACCESS_TOKEN` | Static string token | Fast static access authorization. |
| | `DROPBOX_APP_KEY` | OAuth client ID key | Used to acquire refreshed access tokens. |
| | `DROPBOX_APP_SECRET` | OAuth client secret | Used alongside `DROPBOX_APP_KEY`. |
| | `DROPBOX_REFRESH_TOKEN` | Continuous offline refresh token | High-availability long-term authentication flow. |
| **OneDrive** | `ONEDRIVE_CLIENT_ID` | Azure Active Directory App Client ID | Client ID identifier under Azure Portal. |
| | `ONEDRIVE_CLIENT_SECRET` | Azure Confidential Client Secret | Password credential associated with Azure AD app. |
| | `ONEDRIVE_TENANT_ID` | Directory Tenant ID or `"common"` | Specifies Microsoft AD authorization endpoint context. |
| **S3 Storage** | `S3_ENDPOINT_URL` | Fully-qualified URL (e.g. `https://s3.us-east-1.amazonaws.com`) | Destination endpoint. Required for custom S3 providers (MinIO/R2). |
| | `S3_ACCESS_KEY_ID` | String identifier | AWS or S3 endpoint access credential. |
| | `S3_SECRET_ACCESS_KEY` | String secret | Cryptographic password key matching Access ID. |
| | `S3_BUCKET_NAME` | S3 standard bucket name | Destination Bucket where shards will reside. |
| | `S3_REGION` | AWS region string (e.g. `"us-east-1"`) | Targeted geographical region. |

---

## 📦 Service Account Base64 Parsing

To prevent issues with multi-line JSON strings inside `.env` or deployment consoles (like Render / Heroku):
1. Convert your Service Account JSON file to a Base64 string:
   ```bash
   cat credentials.json | base64 -w 0
   ```
2. Assign the resulting single-line string to `GDRIVE_SERVICE_ACCOUNT_JSON`.
3. The consolidated provider automatically detects and decodes Base64 inputs into a Python dictionary.

---

## 🚀 Resilience, Retries, and Circuit-Breaking

- **Timeout Policies:** Put/Get queries towards cloud providers default to a **30.0s hard timeout limit** inside async HTTPX clients.
- **Failover / Circuit-Breaker:** If an upload fails, the provider is placed under a **600s (10 minutes) quarantine** by `ProviderRegistry`.
- **Capacity Limits:** Any provider reporting a space utilization fraction > **90%** is skipped for uploads to prevent disk-full exceptions.
