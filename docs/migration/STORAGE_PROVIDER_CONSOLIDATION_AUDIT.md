# Storage Provider Consolidation Audit

This document identifies all findings during the audit of the existing `vit-storage` codebase in comparison to the authoritative `vit` migration package and production features.

---

## 🔎 Audit Findings

### 1. File: `tachyon/providers/base.py`
- **Severity**: Medium
- **Migration Status**: Needs Merge
- **Production Impact**: Discrepancies between legacy interface names (`upload_fragment`, `download_fragment`) and the target standard interface. Client requests and scheduling flows will raise `AttributeError` if unified naming is not used.
- **Recommended Action**: Standardize the interface to use 14 core operations (`upload`, `download`, `stream`, etc.) and add backward compatibility shims for all legacy method names.

### 2. File: `tachyon/providers/disk.py`
- **Severity**: Critical
- **Migration Status**: Missing
- **Production Impact**: Missing local file system provider. Essential for offline dev environments, test suite isolation, and running mock-based integration tests. Without this, standard uploads with no credentials fail entirely.
- **Recommended Action**: Migrate and consolidate `DiskProvider` from `vit` and implement all 14 standard operations with path traversal checks.

### 3. File: `tachyon/providers/gdrive.py`
- **Severity**: High
- **Migration Status**: Needs Merge
- **Production Impact**: Heavy API discovery overhead (>150ms per warm start) and repetitive folder parent lookup. Resumable large-file uploads are missing, causing instability for files > 5MB.
- **Recommended Action**: Merge legacy and core Google Drive classes. Implement discovery suppression (`cache_discovery=False`), folder ID memoization, local `name_to_file_id` caching, and chunked resumable upload logic.

### 4. File: `tachyon/providers/dropbox.py`
- **Severity**: High
- **Migration Status**: Needs Merge
- **Production Impact**: Static short-lived Dropbox tokens will expire within 4 hours, causing silent operational failure in production.
- **Recommended Action**: Consolidate short-lived token implementation with OAuth2 refresh token flows (`app_key`, `app_secret`, `oauth2_refresh_token`) from legacy `vit` providers.

### 5. File: `tachyon/providers/onedrive.py`
- **Severity**: High
- **Migration Status**: Needs Merge
- **Production Impact**: Rapid concurrent downloads will trigger Azure endpoint rate-limiting and slow down reassembly times due to missing MSAL silent AD caching.
- **Recommended Action**: Unify modern async `httpx` PUT/GET Graph API requests with MSAL Confidential Client token caching.

### 6. File: `tachyon/core/providers/pool.py` (Registry/Factory)
- **Severity**: Critical
- **Migration Status**: Missing
- **Production Impact**: Lacks a centralized registry/factory inside `vit-storage` to coordinate multiple loaded cloud endpoints, leading to unhandled timeout spikes and no fallback options if a provider is down.
- **Recommended Action**: Port `pool.py` as a centralized `ProviderRegistry` inside `tachyon/providers/registry.py` with automatic configuration loading, status logging, capacity controls, and 10-minute timeout quarantine.

### 7. File: `tachyon/core/scheduler.py`
- **Severity**: Critical
- **Migration Status**: Placeholder Stub
- **Production Impact**: Files are not chunked, erasure-coded, or distributed parallelly across cloud providers.
- **Recommended Action**: Migrate and complete `TachyonScheduler` to route fragments parallelly to healthy nodes in `ProviderRegistry`.

### 8. File: `tachyon/core/worker.py`
- **Severity**: High
- **Migration Status**: Placeholder Stub
- **Production Impact**: Background worker has empty sleep loops. Fails to perform fragment-level verification or self-healing.
- **Recommended Action**: Rewrite background loop to audit manifest health and trigger `SelfHealingManager` for degraded chunks.
