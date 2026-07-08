import httpx
import asyncio
import os
import sys

RENDER_URL = os.getenv("RENDER_URL", "https://vit-storage-svc.onrender.com")

async def validate_storage_pipeline():
    print(f"Starting functional validation against {RENDER_URL}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Health check
        res = await client.get(f"{RENDER_URL}/health")
        print(f"[HEALTH] {res.status_code} - {res.json()}")

        # 2. Upload
        files = {"file": ("test_file.txt", b"Hello VIT Storage", "text/plain")}
        res = await client.post(f"{RENDER_URL}/api/v1/upload", files=files)
        print(f"[UPLOAD] {res.status_code} - {res.json()}")
        file_id = res.json().get("file_id")

        if not file_id:
            print("Upload failed, skipping remaining tests.")
            return

        # 3. Metadata
        res = await client.get(f"{RENDER_URL}/api/v1/files/{file_id}")
        print(f"[METADATA] {res.status_code} - {res.json()}")

        # 4. Download
        res = await client.get(f"{RENDER_URL}/api/v1/download/{file_id}")
        print(f"[DOWNLOAD] {res.status_code} - Content Length: {len(res.content)}")

        # 5. List
        res = await client.get(f"{RENDER_URL}/api/v1/files")
        print(f"[LIST] {res.status_code} - Count: {len(res.json())}")

        # 6. Delete
        res = await client.delete(f"{RENDER_URL}/api/v1/files/{file_id}")
        print(f"[DELETE] {res.status_code} - {res.json()}")

if __name__ == "__main__":
    asyncio.run(validate_storage_pipeline())
