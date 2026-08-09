# Ownership And Root Views Audit Unit
<!--
@dependency-start
contract design
responsibility Audits ownership maps, AgentCanon source boundaries, submodule pins, and root runtime views.
upstream design ../README.md owns canonical audit boundaries
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md owns shared root surface policy
upstream implementation ../../../tools/agent_tools/agent_canon_source_root.py resolves source roots
downstream implementation ../../../agents/skills/agent-canon-update.md owns pin and root-view repair
@dependency-end
-->

## Reader Map

親固有の root view と AgentCanon source の境界、submodule pin、MCP/Codex runtime surface
を確認します。shared canon の変更は source 側、template 固有の変更は親側という ownership
を先に固定します。

## Owner Responsibility

`agent-canon-update` が AgentCanon source、submodule pin、root view、sync control の
所有境界を管理します。親監査はその boundary evidence と root/view readback を監査します。

## Invariant

`vendor/agent-canon`、root `AGENTS.md`、`.codex/config.toml`、
`tools/agent-canon/` の active views は canonical source と整合し、pin は意図した
remote/main を指す。`agents/`、`.agents/`、`.devcontainer/`、`.vscode/`、GitHub
paths は親-owned regular content として保持する。MCP、個人 Codex state、template
固有説明を別責務として保持する。

## Evidence Sources

- `.gitmodules` と `git submodule status`
- `agent_canon_source_root.py` の typed resolution
- `tools/sync_agent_canon.sh check` と root-view diff
- `documents/runtime/SHARED_RUNTIME_SURFACES.md`
- root `AGENTS.md` と `vendor/agent-canon/ROOT_AGENTS.md`

## Repair Route

owner skill は `agent-canon-update`、主 tool は `agent_canon_source_root.py` と
`tools/sync_agent_canon.sh`。source/root-view drift は source owner に routing し、
親側で正本を直接上書きしません。

## Validation

source-root typed result、submodule/pin readback、root-view sync check、対象 path diff
で十分性を判定します。remote auth/network は静的に確定できない項目だけ owner command
を条件付きで使います。

## Close Condition

source root、pin、root views、ownership map が一致し、drift 修正後の対象 readback が
clean になる。個人 runtime state や generated inventory を canonical source に追加しない。

## Related Change Surfaces

`surface:agentcanon.root-views`、`surface:agentcanon.source-root`、`surface:submodule.pin`。
shared surface、source-root resolver、pin、root AGENTS の変更時だけ本 unit を更新します。

## Scope Patterns

- `pattern:vendor/agent-canon/**`
- `pattern:.codex/config.toml`
- `pattern:tools/agent-canon/**`
- `pattern:AGENTS.md`
- `pattern:ROOT_AGENTS.md`
- `pattern:.gitmodules`

## Legacy Migration IDs

PRA-C001 PRA-C002 PRA-C003 PRA-C004 PRA-C005 PRA-C006 PRA-C007 PRA-C008 PRA-C009 PRA-C010 PRA-C011 PRA-C012 PRA-C013 PRA-C014 PRA-C015 PRA-C016 PRA-C017 PRA-C018 PRA-C019 PRA-C020 PRA-C021 PRA-C022 PRA-C023 PRA-C024 PRA-C087 PRA-C088 PRA-C089 PRA-C090 PRA-C091 PRA-C097 PRA-C098 PRA-C099 PRA-C100 PRA-C102 PRA-C103 PRA-C104 PRA-C105 PRA-X001 PRA-X002 PRA-X003 PRA-X004 PRA-X005 PRA-X006 PRA-X007 PRA-X008 PRA-X009 PRA-X010 PRA-X011 PRA-X012 PRA-X013 PRA-X014 PRA-X015 PRA-X016 PRA-X017 PRA-X047 PRA-X048 PRA-X050 PRA-X051 PRA-X052 PRA-X053
