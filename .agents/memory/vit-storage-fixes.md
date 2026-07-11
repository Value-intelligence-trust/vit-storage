---
name: vit-storage fixes
description: What was fixed in vitnetwork/vit-storage and how the architecture works
---

## Repository
`vitnetwork/vit-storage` — deployed at https://vit-storage-4trt.onrender.com

## What was fixed (pushed to main branch)

### Backend fixes
1. **SPA routing** — `main.py` now has explicit GET routes for every tab path (`/my-files`, `/shared-links`, `/api-playground`, `/administration`, `/wallet`, `/documentation`) that all serve `frontend/static/index.html`.
2. **New `tachyon/api/extended_router.py`** with 9 endpoints:
   - `GET /api/v1/nodes` — cloud provider health
   - `GET /api/v1/storage/stats` — aggregated stats
   - `GET /api/v1/quota` — user quota (100 GB free plan)
   - `GET /api/v1/shared-links` — list shared links
   - `POST /api/v1/shared-links` — create shared link (DB-backed, `SharedLink` model)
   - `DELETE /api/v1/shared-links/{id}` — revoke link
   - `GET /api/v1/shared/{token}` — download via token (increments counter, checks expiry)
   - `GET /api/v1/admin/overview` — DB/Redis/node status
   - `GET /api/v1/wallet` — VIT balance + AI quota
3. **`tachyon/core/models.py`** — Added `SharedLink` SQLAlchemy model (table: `shared_links`). `init_db()` auto-creates it via `create_all`.
4. **`tachyon/api/models.py`** — `FileMetadata` now includes `file_id` and `created_at` fields.
5. **`tachyon/api/router.py`** — `list_files`, `get_file_metadata`, `upload_file` all return `file_id` now. Download adds `Content-Disposition` header with filename.

### Frontend rebuild
- `frontend/static/index.html` completely rebuilt (91KB)
- All 7 tabs fully wired: Dashboard, My Files, Shared Links, API Playground, Administration, VIT Wallet/AI, Documentation
- All tabs call real API endpoints; toast notifications throughout
- File manager: select-all/bulk-delete, drag-drop, correct download by file_id
- Shared links: create/list/copy/revoke via REST API with expiry and download limits
- API Playground: preset buttons + full endpoint reference grid
- Admin: live DB/Redis/node status
- Wallet: gradient card + AI quota progress bar
- Docs: Swagger link, cURL quickstart, architecture overview cards

**Why:** The original frontend had tabs that returned 404 for direct URL navigation, missing endpoints for nodes/shared-links/admin/wallet, and a broken download that tried to extract file_id from fragment names.

**How to apply:** On future changes to vit-storage, push to `vitnetwork/vit-storage` main branch. Render auto-deploys. The `SharedLink` model is in `tachyon/core/models.py` and `init_db()` creates it automatically on startup.
