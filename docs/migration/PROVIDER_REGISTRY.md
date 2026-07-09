# Provider Registry & Failover Architecture

This document describes the design, configuration, and failover capabilities of the centralized `ProviderRegistry` (and its backwards-compatible alias `ProviderPool`) inside `vit-storage`.

---

## 🛠️ Design Specification

The `ProviderRegistry` is located at `tachyon/providers/registry.py`. It is responsible for bootup, capabilities discovery, high-availability routing, and resource protection for all cloud providers.

```
                              [File/Shard Operation Request]
                                            │
                                            ▼
                               [Filter Quarantined Nodes]
                                            │
                                            ▼
                              [Filter Quota-Full (>90%) Nodes]
                                            │
                                            ▼
                                [Round-Robin Sequence]
                                      /        \
                            (Success)/          \(Failure)
                                    ▼            ▼
                                [Done]     [Quarantine 600s]
                                                 │
                                                 ▼
                                           [Try Next Node]
```

---

## 🚀 Key Features

### 1. Automatic Registration & Configuration Bootstrapping
On initialization, the registry automatically parses environment variables and instantiates valid provider adapters:
- **Local Disk Backend:** Registers `local_disk` using the standard `TACHYON_STORAGE_PATH` fallback directory.
- **Google Drive SA Array:** Parses `GDRIVE_SERVICE_ACCOUNT_KEYS` (JSON array of service account structures) and boots multiple Google Drive clients.
- **Microsoft OneDrive Accounts:** Parses `ONEDRIVE_ACCOUNTS` (JSON array of Microsoft client credential maps) to initialize Microsoft Graph endpoints.
- **Dropbox Tokens:** Parses `DROPBOX_TOKENS` (JSON array of static tokens) or discrete App credentials.
- **S3 / Object Storage:** Detects and registers S3 endpoint keys dynamically.

### 2. Capability Discovery
The registry exposes a `discover_capabilities()` query mapping provider instances to verified traits (e.g. streaming, signed URL generator, directories) enabling the scheduler to filter targets dynamically.

### 3. High-Availability Failover & 10-Minute Quarantine
When a provider raises an uncaught network exception or standard timeout during shard upload/download, the registry:
1. Logs the failure and quarantines the specific provider for **600 seconds (10 minutes)**.
2. Selects the next available provider in the round-robin sequence to handle the chunk.
3. Automatically restores the node's status to "active" once the quarantine timestamp expires.

### 4. Quota Guard Protection
The registry implements a **90% used-bytes threshold cutoff** (`QUOTA_GUARD_PCT = 0.90`). Prior to uploading a shard, the registry queries and caches node space allocations:
- If a provider exceeds **90% usage**, it is excluded from round-robin selection to prevent file truncation or un-shreddable file blocks.
- Cache duration is set to **5 minutes (300s)** to minimize API latency overhead.

---

## 🔄 Backwards Compatibility Alias

To prevent import errors across legacy modules inside the VIT ecosystem, the class implements:
- An alias `ProviderPool = ProviderRegistry`.
- Legacies import pathway forwarding `tachyon/core/providers/pool.py` directly to the centralized registry.
