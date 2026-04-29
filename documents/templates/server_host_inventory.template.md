<!--
@dependency-start
responsibility Documents Server Host Inventory Template for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Server Host Inventory Template

この template は、main server host の inventory と readiness gap を記録するためのものです。
実値は host 固有なので、そのまま `documents/` に置かず、必要なら `notes/` か infra 管理 repo に複製して使います。

## Host Summary

- Host id:
- Label:
- Role:
- Host kind:
- OS / kernel:
- Primary user:
- Active groups:

## Container Runtime

- Builder:
- `docker` CLI version:
- `podman` version:
- Docker socket path:
- Docker socket access status:
- `codex` CLI version:
- `python3` version:

## Storage Layout

- Bare repo root:
- Shared workspace root:
- Local state root:
- Docker state root:
- Artifact root:

## Mount Inventory

- Path:
  - Filesystem type:
  - Source:
  - Intended use:
  - Risk:

## Git / Mirror

- `origin` target:
- Mirror remote:
- Bare repo hook path:
- SSH / credential note:

## Validation Log

- `uname -a`:
- `id`:
- `df -h`:
- `mount`:
- `docker version`:
- `python3 tools/ci/check_server_readiness.py`:

## Gaps

- `Gap:`
- `Decision:`
- `Owner:`
- `Next check:`
