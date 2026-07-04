# vit-storage Roadmap

## Phase 0 — Rename & Standards (complete)
- [x] Renamed `vit-tachyon` → `vit-storage`
- [x] Apache-2.0 LICENSE, SECURITY.md, CONTRIBUTING.md, CODEOWNERS, CI templates
- [x] Documented planned package layout (see ARCHITECTURE.md)

## Phase 1 — Test & CI Hardening
- [ ] Add unit test suite under `tests/`
- [ ] Add branch protection on `main` (currently missing)
- [ ] Add CI workflow: lint (ruff/flake8) + pytest + coverage

## Phase 2 — Package Reorganization
- [ ] Incrementally move `tachyon/core` → `core/`
- [ ] Extract `sdk/` and `cli/` as installable sub-packages
- [ ] Introduce `gateway/` as the single public entrypoint

## Phase 3 — Reliability
- [ ] `integrity/` — background fragment health checks + auto-repair
- [ ] `replication/` — configurable replication factor per provider
- [ ] `monitoring/` — Prometheus metrics + health dashboards

## Phase 4 — Distribution
- [ ] Publish `sdk/` as a standalone Python package
- [ ] Docker image published to GHCR
- [ ] Helm chart / docker-compose for self-hosting
