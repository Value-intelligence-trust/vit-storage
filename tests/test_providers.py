import pytest
import os
import shutil
from tachyon.providers.disk import DiskProvider
from tachyon.providers.s3 import S3Provider

@pytest.fixture
def disk_provider():
    path = "/tmp/test_tachyon_disk"
    if os.path.exists(path):
        shutil.rmtree(path)
    prov = DiskProvider("test_disk_acc", storage_path=path)
    yield prov
    if os.path.exists(path):
        shutil.rmtree(path)

@pytest.fixture
def s3_mock_provider():
    os.environ["S3_ACCESS_KEY_ID"] = "" # Force mock
    os.environ["S3_SECRET_ACCESS_KEY"] = ""
    prov = S3Provider("test_s3_acc")
    yield prov
    if os.path.exists(prov.mock_dir):
        shutil.rmtree(prov.mock_dir)

@pytest.mark.anyio
async def test_disk_provider_crud(disk_provider):
    data = b"Tachyon integration verification data"
    name = "test_shard.bin"

    # Upload
    uploaded = await disk_provider.upload(data, name)
    assert uploaded is True

    # Exists
    exists = await disk_provider.exists(name)
    assert exists is True

    # Download
    downloaded = await disk_provider.download(name)
    assert downloaded == data

    # Checksum
    chk = await disk_provider.checksum(name)
    assert len(chk) == 64 # SHA256 length

    # Metadata
    meta = await disk_provider.metadata(name)
    assert meta["name"] == name
    assert meta["size"] == len(data)

    # Rename
    renamed = await disk_provider.rename(name, "renamed_shard.bin")
    assert renamed is True
    assert await disk_provider.exists("renamed_shard.bin") is True
    assert await disk_provider.exists(name) is False

    # Delete
    deleted = await disk_provider.delete("renamed_shard.bin")
    assert deleted is True
    assert await disk_provider.exists("renamed_shard.bin") is False

@pytest.mark.anyio
async def test_s3_provider_mock_crud(s3_mock_provider):
    data = b"S3 mock transaction payload data"
    name = "test_s3_shard.bin"

    # Upload
    uploaded = await s3_mock_provider.upload(data, name)
    assert uploaded is True

    # Exists
    exists = await s3_mock_provider.exists(name)
    assert exists is True

    # Download
    downloaded = await s3_mock_provider.download(name)
    assert downloaded == data

    # Delete
    deleted = await s3_mock_provider.delete(name)
    assert deleted is True
    assert await s3_mock_provider.exists(name) is False
