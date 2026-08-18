<!--
@dependency-start
contract data
responsibility Records how to include repository symlink targets outside the workspace in container mount inventory.
upstream design ../README.md memory record contract
upstream implementation ../../rust/agent-canon/src/memory.rs schema, validation, and search owner
upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md linked-data-roots mount contract
upstream design ../../documents/parent-repository/CONTAINER_OPERATIONS.md container mount inventory operations
@dependency-end
-->

# External symlink target mount

record_id: `container--external-symlink-target-mount`
record_schema: `agent-canon.memory-record.v1`

## Problem/Symptom

repository 内の symlink を workspace とともに container へ渡しても、link が workspace
外の host path を指す場合、container 内では解決先が存在せず、linked data を読めない。
workspace mount が成功しているため、mount inventory の欠落を見落としやすい。

## Context/Trigger

devcontainer または直接 container runtime が repository の symlink を利用し、その
`realpath` が既存 workspace mount の外へ出るときに使う。特に `/mnt/<drive>/...` の
ような host data root を repository-relative link から参照する場合が該当する。

## Root Cause

mount inventory が repository root と symlink entry だけを列挙し、canonical target を
独立した runtime dependency として扱っていない。symlink metadata は container に見えても、
解決先の host directory は自動的には bind mount されない。

## Effective Resolution

選択した runtime profile で利用する repository symlink と期待 target を明示し、生成前に
`realpath -e` した既存 directory が declared target と完全一致することを確認する。一致した
target だけを同一 absolute path へ structured read-write bind として追加し、生成 Compose と
直接 runner の双方で source、target、bind type、write mode を read back する。

## Failed Approaches

- workspace root の bind だけで、その内部 symlink の外部 target も見えると仮定する。
- repository や host filesystem を探索して、見つけた外部 path を暗黙にすべて mount する。
- untyped な raw mount string を受け入れ、target identity や衝突を検証しない。
- host 側で link が解決できることだけを確認し、生成 Compose または container route を読まない。

## Applicability/Limits

明示された repository symlink が workspace 外の既存 directory を指し、その data を
container から利用する場合に適用する。任意の host path、credential、shell startup file、
Docker socket を自動 mount する規則ではない。read-only が必要な対象や symlink 以外の
runtime dependency は、それぞれの canonical profile contract で別に扱う。

## Evidence/Source

PR #536 の branch `codex/devcontainer-host-shell-mounts` で、`link/msm_data_root` が
workspace 外の `/mnt/l/msm_data_root` へ解決する一方、生成 Compose の mount inventory に
target がなかった incident を確認した。commit
`51f3c5eb82f0529be90efa960a3324a5d0713176` が typed `linked-data-roots` contract、generator、
direct runner、targeted tests、および canonical owner 文書を追加した。

## Promoted Owner Refs

- `documents/design/devcontainer/parent-devcontainer-policy.md`
- `documents/parent-repository/CONTAINER_OPERATIONS.md`

## Related Records

- なし
