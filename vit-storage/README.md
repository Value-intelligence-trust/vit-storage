# VIT Tachyon Fabric

**Decentralised swarm storage coordination service** for the VIT Network.

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-latest-009688?style=flat-square)](https://fastapi.tiangolo.com)

## Overview

Tachyon Fabric provides parallel burst data transfers across aggregated cloud storage providers with EEC-based erasure coding for high-speed, quantum-safe fragmentation.

## Architecture

- **Swarm Coordinator** — distributes fragments across providers
- **EEC Engine** — erasure coding for redundancy and speed
- **Provider Adapters** — Google Drive, S3, IPFS, and more
- **Reconstruction Service** — parallel fragment retrieval and reassembly

## Run

```bash
pip install -r requirements.txt
uvicorn tachyon.main:app --reload --port 8080
```

Health: `GET /health` → `{"status": "quantum_stable"}`
