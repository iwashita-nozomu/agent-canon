<!--
@dependency-start
contract reference
responsibility Documents Server Host Inventory Template for this repository.
upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# Server Host Inventory Template

この template は、main server host の inventory と readiness gap を記録するためのものです。
実値は host 固有なので、そのまま `documents/` に置かず、必要なら `documents/notes/` か infra 管理 repo に複製して使います。

## Reader Map

この inventory は host identity → runtime/storage/mount → Git/mirror → validation → gap/owner/cleanup
の順で読みます。ここには reader が再構築に必要な実値と evidence の所在を記録し、host
固有値を AgentCanon の policy source に戻しません。

- purpose:
- intended reader and decision:
- what this document contains:
- canonical owner / responsibility boundary:
- source, generated, and local inventory surfaces:
- validation/readback command:
- retention and lifecycle cleanup owner:

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

## Contract and readback

- owner / responsibility unit:
- dependency and side-effect map:
- failure-cause classification:
- conflict intent / preserved host contract:
- formatter/readback: `tools/bin/agent-canon docs check <path>`（Markdown）
- cleanup command and reconstructibility evidence:
