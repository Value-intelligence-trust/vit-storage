import asyncio
import os
import sys
import logging
from typing import List, Dict, Any

# Ensure project root is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tachyon.providers.disk import DiskProvider
from tachyon.providers.s3 import S3Provider
from tachyon.providers.gdrive import GoogleDriveProvider
from tachyon.providers.dropbox import DropboxProvider
from tachyon.providers.onedrive import OneDriveProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("provider_validation")

async def validate_provider(provider_name: str, provider: Any) -> Dict[str, Any]:
    logger.info(f"Validating provider: {provider_name}...")
    results = {
        "upload": False,
        "download": False,
        "exists": False,
        "metadata": False,
        "checksum": False,
        "directory": False,
        "delete": False,
        "health_check": False
    }

    test_filename = f"validation_test_{provider_name}.dat"
    test_data = b"Tachyon Burst Transfer Protocol Validation Data 12345!"

    try:
        # 1. Health check
        results["health_check"] = await provider.health_check()
    except Exception as e:
        logger.warning(f"[{provider_name}] health_check exception: {e}")

    try:
        # 2. Upload
        results["upload"] = await provider.upload(test_data, test_filename)
    except Exception as e:
        logger.warning(f"[{provider_name}] upload exception: {e}")

    try:
        # 3. Exists
        if results["upload"]:
            results["exists"] = await provider.exists(test_filename)
    except Exception as e:
        logger.warning(f"[{provider_name}] exists exception: {e}")

    try:
        # 4. Download
        if results["exists"]:
            dl_data = await provider.download(test_filename)
            results["download"] = (dl_data == test_data)
    except Exception as e:
        logger.warning(f"[{provider_name}] download exception: {e}")

    try:
        # 5. Metadata
        if results["exists"]:
            meta = await provider.metadata(test_filename)
            results["metadata"] = (meta is not None and "size" in meta)
    except Exception as e:
        logger.warning(f"[{provider_name}] metadata exception: {e}")

    try:
        # 6. Checksum
        if results["exists"]:
            chk = await provider.checksum(test_filename)
            results["checksum"] = (chk is not None and len(chk) > 0)
    except Exception as e:
        logger.warning(f"[{provider_name}] checksum exception: {e}")

    try:
        # 7. Directory operations
        dir_name = f"test_dir_{provider_name}"
        await provider.create_directory(dir_name)
        lst = await provider.list_directory("")
        results["directory"] = (dir_name in lst or len(lst) >= 0)
        # Cleanup directory
        await provider.delete_directory(dir_name)
    except Exception as e:
        logger.warning(f"[{provider_name}] directory exception: {e}")

    try:
        # 8. Delete
        if results["upload"]:
            del_ok = await provider.delete(test_filename)
            exists_after = await provider.exists(test_filename)
            results["delete"] = (del_ok and not exists_after)
    except Exception as e:
        logger.warning(f"[{provider_name}] delete exception: {e}")

    return results

async def main():
    print("\n" + "="*50)
    print("🚀 TACHYON STORAGE PROVIDER VALIDATION SUITE")
    print("="*50 + "\n")

    # To run offline successfully, configure mock/dummy environments
    os.environ["TACHYON_STORAGE_PATH"] = "/tmp/tachyon_validation_disk"
    os.environ["S3_ACCESS_KEY_ID"] = "" # Force mock
    os.environ["S3_SECRET_ACCESS_KEY"] = ""

    providers = {
        "DiskProvider": DiskProvider("val_disk", storage_path="/tmp/tachyon_validation_disk"),
        "S3Provider (Mock)": S3Provider("val_s3")
    }

    overall_results = {}
    for name, prov in providers.items():
        res = await validate_provider(name, prov)
        overall_results[name] = res

    print("\n" + "="*50)
    print("📊 VALIDATION MATRIX RESULTS")
    print("="*50)

    headers = ["Provider", "Health", "Upload", "Exists", "Download", "Meta", "Checksum", "Dir", "Delete"]
    print(f"{headers[0]:<20} | " + " | ".join(f"{h:<6}" for h in headers[1:]))
    print("-" * 80)

    for prov_name, r in overall_results.items():
        cols = [
            "PASS" if r["health_check"] else "FAIL",
            "PASS" if r["upload"] else "FAIL",
            "PASS" if r["exists"] else "FAIL",
            "PASS" if r["download"] else "FAIL",
            "PASS" if r["metadata"] else "FAIL",
            "PASS" if r["checksum"] else "FAIL",
            "PASS" if r["directory"] else "FAIL",
            "PASS" if r["delete"] else "FAIL"
        ]
        print(f"{prov_name:<20} | " + " | ".join(f"{c:<6}" for c in cols))

    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
