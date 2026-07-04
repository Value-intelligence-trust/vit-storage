# ADR 0001: Rename vit-tachyon to vit-storage

## Status
Accepted — 2026-07-04

## Context
The VIT ecosystem's target repository architecture defines a `vit-storage` repository as the
canonical decentralized storage fabric. An existing, actively-developed repository
(`vit-tachyon`) already implements this exact responsibility (swarm storage, erasure coding,
provider adapters).

## Decision
Rename `vit-tachyon` to `vit-storage` in place (preserving full git history, issues, and stars)
rather than creating a new, empty `vit-storage` repository. This avoids duplicate storage
implementations and keeps a single source of truth.

## Consequences
- GitHub automatically redirects the old `vit-tachyon` URL to `vit-storage`.
- Internal module name `tachyon/` is retained for now; will be reorganized per `ROADMAP.md`.
- Any external references to `vit-tachyon` (docs, CI, deploy configs) should be updated over time.
