# Dependency Manifest Design

<!--
@dependency-start
upstream design ../agents/canonical/CODEX_WORKFLOW.md dependency header workflow requirement
upstream design ../agents/templates/closeout_gate.md closeout dependency evidence requirement
downstream implementation ../tools/agent_tools/check_dependency_headers.py validates changed-file manifests
downstream implementation ../tools/agent_tools/scan_dependency_headers.sh scans manifest marker coverage
downstream implementation ../tools/agent_tools/check_dependency_header_format.sh validates manifest syntax
downstream implementation ../tools/agent_tools/check_dependency_graph.sh validates manifest graph semantics
downstream implementation ../tests/agent_tools/test_check_dependency_headers.py verifies manifest checker
downstream implementation ../tests/agent_tools/test_dependency_manifest_tools.py verifies manifest shell tools
@dependency-end
-->

このメモは、file 先頭に置く依存 manifest block の次期設計を固定します。
目的は、agent と tool の両方が、ある file を編集する前後に読むべき関係 file を機械的に取得できるようにすることです。
旧 `Dependency Files:` block は廃止方向です。
この設計では `@dependency-start` / `@dependency-end` marker による line-oriented DSL を正とします。

## Goals

- 変更前に読むべき upstream context を、file から相対 path で取得できる
- 変更後に確認すべき downstream context を、file から相対 path で取得できる
- human reviewer、agent、CI tool が同じ manifest を読む
- Bash / awk で高速に scan と format check ができる
- graph-level の双方向整合、自己参照、循環、closure を tool で検証できる
- code、docs、workflow、test、environment file を同じ内部 DSL で扱う

## Non-Goals

- YAML / JSON の完全 parser を作らない
- 推移依存を各 file に手書きしない
- すべての generated / binary artifact を同じ manifest で管理しない
- write-capable subagent の並列数を増やすための設計ではない

## Manifest Block

各 file の先頭付近に、共通 marker を含む dependency manifest block を置きます。
外側は file type ごとの comment syntax を使います。
内部 DSL はすべての file type で同じです。

```text
@dependency-start
upstream design ../agents/canonical/CODEX_WORKFLOW.md workflow contract
upstream implementation ../tools/agent_tools/bootstrap_agent_run.py consumes workflow metadata
downstream implementation ../tests/agent_tools/test_task_start_and_close.py verifies emitted output
@dependency-end
```

1 dependency は 1 line で表します。
文法は次です。

```text
<direction> <kind> <relative-path> <reason...>
```

- `direction` は `upstream` または `downstream`
- `kind` は `design`、`implementation`、`environment`
- `relative-path` は manifest を持つ file から見た相対 path
- `reason` は 4 field 目以降の短い説明

複数 file に依存する場合は、依存ごとに行を増やします。
依存がない direction は行を置きません。
空の placeholder 行や `none` 行は不要です。

## Dependency Kinds

`design` は仕様、設計、workflow、規約、schema、ADR 的な上位判断を表します。

`implementation` は code、script、test、runtime consumer、生成元、生成先を表します。

`environment` は Docker、CI、requirements、lock、tool config、runtime assumption を表します。

最初はこの 3 種に限定します。
新しい kind を増やす場合は、tool、docs、review gate、migration plan を同じ変更で更新します。

## Comment Wrapping

内部 marker と DSL は全 file type 共通です。
外側 comment syntax だけを file type に合わせます。

Markdown:

```markdown
<!--
@dependency-start
upstream design ../agents/canonical/CODEX_WORKFLOW.md workflow contract
downstream implementation ../tools/agent_tools/bootstrap_agent_run.py consumes workflow contract
@dependency-end
-->
```

Python / shell / TOML:

```python
# @dependency-start
# upstream implementation ../tools/agent_tools/agent_team.py imports helper contract
# downstream implementation ../tests/agent_tools/test_task_start_and_close.py verifies CLI behavior
# @dependency-end
```

C-like languages:

```c
/*
@dependency-start
upstream design ../include/public_api.h public API contract
downstream implementation ../tests/test_public_api.cpp validates API behavior
@dependency-end
*/
```

Line comments are allowed because TOML, shell, Python, and many config formats do not have a native multiline comment.
The canonical parser must ignore common comment prefixes before reading each manifest line.
Commentless formats such as strict JSON are classified separately by the scan tool; they do not define the common path.

## Upstream And Downstream Graphs

`upstream` and `downstream` are separate graphs.
They are not mixed into one dependency graph.

The upstream graph answers: before editing this file, what context must be read?

The downstream graph answers: after editing this file, what affected files must be checked?

This separation exists for human and agent context management.
An agent can load upstream closure before editing, then load downstream closure after the diff exists.

## Bidirectional Consistency

Bidirectional consistency is a graph-level validation, not a hand-maintained prose rule.

If file A declares:

```text
downstream implementation ../b.py B consumes A
```

then file B must declare the matching reverse edge:

```text
upstream implementation ../a.py A is consumed by B
```

The same rule applies in the other direction.
Kind must match unless a later design explicitly allows cross-kind reverse edges.

The graph checker compares the downstream edge set with the inverse upstream edge set.
It should report missing reverse edges and kind mismatches with file-relative diagnostics.

## Self Reference And Cycles

Self reference is a graph-level error.
It belongs in `check_dependency_graph.sh`, not in the format checker, because the graph checker resolves paths and normalizes edges across the repository.

Cycle detection is also graph-level.
The checker should analyze upstream and downstream separately.

- upstream cycles are fail by default because upstream represents prerequisite context
- downstream cycles are fail by default during initial rollout unless a documented allowlist is introduced
- bidirectional consistency itself is not treated as a cycle because upstream and downstream are separate graphs

Example: A `downstream` B plus B `upstream` A is expected and valid.
Example: A `upstream` B plus B `upstream` A is an upstream cycle and should fail.

## Tool Split

Tools are Bash-first.
Python is not required for the first implementation because the DSL is line-oriented.

### `scan_dependency_headers.sh`

Responsibilities:

- enumerate tracked files with `git ls-files`
- classify binary, generated, vendored external, commentless, unsupported, and checkable files
- report files missing `@dependency-start` / `@dependency-end`
- run in report-only mode during migration
- later become a CI fail gate

### `check_dependency_header_format.sh`

Responsibilities:

- validate marker count and marker order
- validate placement near the top of the file
- strip common comment prefixes
- validate each dependency line has direction, kind, relative path, and reason
- validate direction and kind enum values
- validate path is relative
- validate target path exists

This tool does not check bidirectional consistency, self reference, closure, or cycles.

### `check_dependency_graph.sh`

Responsibilities:

- extract normalized edges from all manifest blocks
- build separate upstream and downstream edge sets
- validate self reference
- validate bidirectional consistency
- validate kind match on reverse edges
- detect cycles separately in upstream and downstream graphs
- print upstream closure for changed files
- print downstream closure for changed files
- emit machine-readable TSV for future visualization

The graph checker can be implemented with Bash, `awk`, `sort`, `comm`, and a small DFS in `awk`.
If later graph requirements outgrow shell tooling, a Python implementation can replace only this layer while preserving the DSL and CLI contract.

## Migration Plan

Phase 1: add this design and make changed-file validation require `@dependency-start` / `@dependency-end`.

Phase 2: implement Bash tools first:

- `scan_dependency_headers.sh`
- `check_dependency_header_format.sh`
- `check_dependency_graph.sh`

`scan_dependency_headers.sh` starts as full-repo report-only so it can list missing manifests without blocking unrelated work.
`check_dependency_headers.py --changed` and `check_dependency_header_format.sh --changed` reject changed files that do not have valid `@dependency-start` blocks.

Phase 3: migrate files one by one from checker findings.
Each touched file must be converted from `Dependency Files:` to `@dependency-start` in the same change that touches it.

Phase 4: enable CI fail gate for changed files.
Full-repo missing-header scan remains report-only until the repository is migrated.

Phase 5: remove legacy `Dependency Files:` wording from remaining docs after all checkable files use dependency manifest blocks.

## Open Design Questions

- Whether strict JSON files should require a sidecar manifest or remain classified as commentless unsupported files
- Whether downstream cycles should eventually support an explicit allowlist
- Whether generated files should point to generators via sidecar metadata or stay outside the checkable set
- Whether closure output should be ordered by graph distance, kind, or stable path sort
