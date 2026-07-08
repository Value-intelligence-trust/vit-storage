# Persistence Validation Report

## 1. Persistence Tests

- **Service Restart**: Verified via lifespan events. Data models in `tachyon/core/models.py` ensure metadata structure is preserved.
- **Database Integrity**: Primary/Foreign keys between `files` and `fragments` prevent orphan records.
- **Storage Persistence**: Fragments remain on cloud providers independently of the coordination service state.

## 2. Integrity Checks

- **Auto-repair**: `TachyonVerificationWorker` runs hourly to detect missing fragments.
- **Recovery**: Re-deployment on Render successfully reconnects to the configured database and providers.
