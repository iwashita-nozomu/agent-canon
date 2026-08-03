# Dependency Integrity Audit Unit
<!--
@dependency-start
contract design
responsibility Audits dependency headers, graph direction, manifests, and full-tree dependency evidence.
upstream design ../README.md owns unit closure and evidence separation
upstream design ../../../agents/internal-routines/README.md owns internal dependency route
upstream implementation ../../../tools/agent_tools/check_dependency_headers.py owns header validation
downstream implementation ../../../agents/skills/dependency-analysis.md repairs dependency evidence
@dependency-end
-->

## Reader Map

human-authored file の dependency header、upstream/downstream graph、manifest、全 repo
review の順に読みます。差分だけでなく tracked tree 全体を対象にし、report は evidence
として source header と分離します。

## Owner Responsibility

`dependency-analysis` が dependency manifest、header、import/code dependency、graph
review の owner です。

## Invariant

各 human-authored text file の header が責務、upstream、downstream を正しく示し、
self-reference、cycle、孤立 manifest、古い header 形式がない。dependency edge は
実装、design、skill、tool の読解順と変更影響を表す。

## Evidence Sources

- `@dependency-start` / `@dependency-end` headers
- `tools/agent_tools/check_dependency_headers.py`
- `tools/agent_tools/check_dependency_graph.sh`
- `tools/agent_tools/run_repo_dependency_review.sh`
- `documents/design/parent-repository-audit.md` の dependency edge

## Repair Route

owner skill は `dependency-analysis`、主 tool は `check_dependency_headers.py`、
`check_dependency_graph.sh`、`run_repo_dependency_review.sh`。既存 helper と graph
owner を再利用し、別の checker を増やさずに header/edge の正本を修正します。

## Validation

header format、全 tree dependency review、graph self/cycle/orphan の static result を
必要十分な証拠とします。実行時 import は static graph で判定不能なときだけ対象 package
の owner-native command を使います。

## Close Condition

全対象 file の header と graph が pass し、変更した header/edge を readback して、
design、skill、tool、runtime の関係が同じ責務境界を指している。

## Related Change Surfaces

`surface:dependency.headers`、`surface:dependency.graph`、`surface:dependency.manifests`。
header、dependency map、graph、import boundary を変更した同じ PR で本 unit を更新します。

## Scope Patterns

- `pattern:documents/**`
- `pattern:agents/**`
- `pattern:tools/**`
- `pattern:tests/**`
- `pattern:README.md`
- `pattern:AGENTS.md`

## Legacy Migration IDs

PRA-C025 PRA-C026 PRA-C027 PRA-C028 PRA-C029 PRA-C030 PRA-C031 PRA-C032 PRA-X018 PRA-X019 PRA-X020 PRA-X021
