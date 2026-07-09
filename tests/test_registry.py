import pytest
import os
from tachyon.providers.registry import ProviderRegistry
from tachyon.providers.disk import DiskProvider

def test_registry_bootstrapping():
    # Clear settings to test standard loading
    os.environ["DROPBOX_TOKENS"] = "[\"tok1\", \"tok2\"]"

    registry = ProviderRegistry()
    assert len(registry.providers) >= 1

    # Check manual register
    test_prov = DiskProvider("test_manual_register", storage_path="/tmp/test_manual")
    registry.register("test_manual", test_prov)
    assert registry.get_provider("test_manual") == test_prov

def test_capability_discovery():
    registry = ProviderRegistry()
    caps = registry.discover_capabilities()
    assert "local_disk" in caps
    assert "upload" in caps["local_disk"]
    assert "download" in caps["local_disk"]
