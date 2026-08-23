# Ownership And Root Views Audit Unit
<!--
@dependency-start
contract design
responsibility Audits ownership maps, standalone AgentCanon source boundaries, and shared runtime ownership.
upstream design ../README.md owns canonical audit boundaries
upstream design ../../runtime/bootstrap-runtime.md owns shared tool-runtime policy
upstream implementation ../../../bootstrap.sh owns host lifecycle and source/runtime separation
downstream implementation ../../../agents/skills/agent-canon-update.md owns source PR/readback
@dependency-end
-->

## Reader Map

親固有の tracked tree と standalone AgentCanon source clone の境界、shared tool runtime、
MCP/Codex runtime surface を確認します。shared canon の変更は source 側、template 固有の
変更は親側という ownership を先に固定します。

## Owner Responsibility

`agent-canon-update` が AgentCanon source clone、source PR、merged-main readback の
所有境界を管理します。親監査はその boundary evidence と runtime/source unchanged
readback を監査します。

## Invariant

親 tracked tree に AgentCanon source、vendor path、submodule gitlink、root projection
が存在しない。AgentCanon source は qualified ignored clone にあり、tool runtime state
は親 workspace の明示 runtime root にあり、MCP、個人 Codex state、template 固有説明は
別責務として保持する。

## Evidence Sources

- qualified source clone の Git status、branch、remote/main、PR merge readback
- `bootstrap.sh status` と runtime-root ownership/readback
- source-unchanged and exact cleanup evidence
- parent `AGENTS.md` と source clone `AGENTS.md`

## Repair Route

owner skill は `agent-canon-update`、主 tool は standalone source clone の
`bootstrap.sh` と source PR workflow。source/runtime drift は source owner に routing
し、親側で AgentCanon 正本を直接上書きしません。

## Validation

source clone identity、PR/main readback、runtime status、source-unchanged check、対象
path diff で十分性を判定します。remote auth/network は静的に確定できない項目だけ owner
command を条件付きで使います。

## Close Condition

source clone、runtime root、ownership map が一致し、drift 修正後の対象 readback が clean
になる。個人 runtime state や generated inventory を canonical source に追加しない。

## Related Change Surfaces

`surface:agentcanon.source-clone`、`surface:agentcanon.shared-runtime`、
`surface:parent.source-free`。source clone、bootstrap runtime、parent boundary の変更時
だけ本 unit を更新します。

## Legacy Migration IDs

PRA-C001 PRA-C002 PRA-C003 PRA-C004 PRA-C005 PRA-C006 PRA-C007 PRA-C008 PRA-C009 PRA-C010 PRA-C011 PRA-C012 PRA-C013 PRA-C014 PRA-C015 PRA-C016 PRA-C017 PRA-C018 PRA-C019 PRA-C020 PRA-C021 PRA-C022 PRA-C023 PRA-C024 PRA-C087 PRA-C088 PRA-C089 PRA-C090 PRA-C091 PRA-C097 PRA-C098 PRA-C099 PRA-C100 PRA-C102 PRA-C103 PRA-C104 PRA-C105 PRA-X001 PRA-X002 PRA-X003 PRA-X004 PRA-X005 PRA-X006 PRA-X007 PRA-X008 PRA-X009 PRA-X010 PRA-X011 PRA-X012 PRA-X013 PRA-X014 PRA-X015 PRA-X016 PRA-X017 PRA-X047 PRA-X048 PRA-X050 PRA-X051 PRA-X052 PRA-X053
