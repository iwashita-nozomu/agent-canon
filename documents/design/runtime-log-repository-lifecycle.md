<!--
@dependency-start
contract design
responsibility Defines the stable runtime-log repository lifecycle and the owner split between AgentCanon and agent-canon-log.
upstream design ../rule/README.md document naming and Japanese-content rule
upstream design ../runtime/runtime-log-archive.md AgentCanon consumer, mount, publication, and command contract
upstream design ../runtime/runtime-log-archive-migration.md legacy in-tree migration boundary
upstream design ../../agents/internal-routines/design-implementation-correspondence.md universal design-to-implementation correspondence
upstream design ../../tools/agent_tools/log_repository_identity.py stable source identity implementation contract
downstream implementation ../../tools/agent_tools/agent_canon_source_root.py source/canon root resolution
downstream implementation ../../tools/agent_tools/runtime_log_paths.py logical runtime path resolution
downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py archive lifecycle, locking, snapshots, push, and readback
downstream implementation ../../tests/agent_tools/test_log_repository_lifecycle.py lifecycle evidence
@dependency-end
-->

# Runtime Log Repository Lifecycle

## Reader Map

この文書は、AgentCanon の runtime log を外部 `agent-canon-log` repository に保存する lifecycle の設計正本です。最初に、既に merged された [agent-canon-log PR #4](https://github.com/iwashita-nozomu/agent-canon-log/pull/4) と AgentCanon [commit #461](https://github.com/iwashita-nozomu/agent-canon/commit/3c9b851838dc16d1d76963fe0bd153a316345854) の owner split を読みます。次に stable identity、root、branch、snapshot、concurrency、legacy、retention の state model と invariant を確認し、最後に exact implementation links、validation/readback、Design-To-Implementation Trace を使います。

## Responsibility / Owner Boundaries

| 責務 | owner | canonical evidence | 境界 (`documents/runtime/runtime-log-archive.md`) |
| --- | --- | --- | --- |
| stable source identity、per-source branch、legacy inventory、retention policy | `agent-canon-log` policy repository | PR #4 とその policy branch | AgentCanon は policy schema を複製・変更しない |
| source root / canon root の解決 | AgentCanon source | `tools/agent_tools/agent_canon_source_root.py` | standalone/vendored/override の layout を確定する |
| logical runtime paths、chat metadata、commit-keyed filenames | AgentCanon source | `tools/agent_tools/runtime_log_paths.py` | filesystem path は実行時 projection、branch identity は chat/path から作らない |
| archive clone、branch、lock、snapshot、commit/push、remote readback | AgentCanon source | `tools/agent_tools/runtime_log_archive_git.py` | policy-selected branch を使い、fail-closed publication を行う |
| archive schema / merge attributes / retention classes | `agent-canon-log` | PR #4 | AgentCanon docs は consumer contract と link だけを持つ |
| old in-tree files の one-time migration | migration owner | `documents/runtime/runtime-log-archive-migration.md` と policy repo | 通常 runtime write と同じ route に混ぜない |

Evidence: `documents/runtime/runtime-log-archive.md`, `documents/runtime/runtime-log-archive-migration.md`, `tools/agent_tools/log_repository_identity.py`, `tools/agent_tools/runtime_log_archive_git.py`。

これは #4 の policy owner と #461 の AgentCanon consumer owner を分ける設計です。#461 の変更で AgentCanon 側には `log_repository_identity.py`、stable branch adapter、immutable report snapshot、explicit source-root resolution、fail-closed status、bounded optimistic publication が入り、policy repository の schema/retention authority は維持されました。

## Exact Data / State Model

### Identity and roots

```text
SourceIdentity {
  normalized_remote: host/path-without-git
  stable_source_repository_id: readable-prefix + '-' + sha256-prefix
}
RootResolution {
  current_repository_root: AbsolutePath (runtime only)
  source_root: AbsolutePath (runtime only)
  canon_root: AbsolutePath (runtime only)
  layout: standalone|vendored|override
}
```

`normalized_remote` は network remote の host/path を case-fold し、末尾 `.git` を除去して作ります。local/file remote、空 path、invalid host、missing repository は reject します。stable ID は remote identity から決まり、filesystem root、chat/session ID、branch 名の推測からは決まりません。durable artifact には repository-relative locator または stable ID を保存し、absolute root は execution context だけに置きます。

### Branch and archive context

```text
ArchiveContext {
  source_root: runtime absolute path
  canon_root: runtime absolute path
  archive_root: runtime absolute path
  stable_source_id: stable ID
  env_key: metadata-only local key
  branch: logs/<stable-source-repository-id>
  remote: policy-selected network remote
}
```

`main` は archive policy/merge attributes/legacy-import の branch、通常 write は exactly one `logs/<stable-source-repository-id>` branch です。chat/session key、environment key、AgentCanon commit key は metadata/path grouping 用であり、stable branch identity ではありません。Evidence: `tools/agent_tools/runtime_log_archive_git.py:build_context`, `tools/agent_tools/runtime_log_paths.py:log_branch_key`。

### Snapshot and publication state

```text
ReportSnapshot {
  repo_id: stable source ID
  run_id: safe path segment
  snapshot_id: content digest
  file_manifest: ordered relative paths + byte sizes + sha256
  source_head: source HEAD OID when available
  agent_canon_commit: short HEAD or no-git-head
}
Publication {
  lock: source-local nonblocking transaction lock
  branch_head_before: OID
  staged_tree: OID
  commit: OID
  remote_head_after: OID
  readback: commit/tree/index/cursor/projection identities
  state: prepared|committed|pushed|read_back|retained|failed
}
```

Agent report snapshot は immutable content-addressed directoryと append-only `index.jsonl` で保存します。同じ bytes は idempotent に再利用し、同じ run で changed bytes が出た場合は別 snapshot とします。既存 artifact、observation、receipt、index line は上書きしません。

### Legacy and retention

```text
LegacyInventory { source_path, source_sha256, mapped_stable_id, destination, disposition }
RetentionClass { family, owner, duration/policy-ref, deletion-authority }
```

旧 in-tree logs は `legacy-import/hook-runs/` と `legacy-import/eval-results/` に read-only inventory と mapping を残します。一般 report/experiment retention は `documents/experiments/result-log-retention-and-visualization.md`、archive branch の schema/retention は PR #4 が owner です。AgentCanon source branch に runtime logs を戻す retention route は存在しません。

## Invariants

- `RL-001` stable source identity は normalized network remote からのみ決まり、filesystem path、chat/session、environment、current branch からは決まらない。
- `RL-002` source root と canon root は explicit marker/layout resolution で決まり、standalone/vendored/override の ambiguity は fail-closed にする。
- `RL-003` durable path は source-relative/logical locator と stable ID を使い、absolute runtime path は execution state に限定する。
- `RL-004` 通常 archive write は `logs/<stable-source-repository-id>` の一 branch だけを使用し、`main` への runtime write、source AgentCanon branch、parent submodule pin を変更しない。
- `RL-005` report snapshot は content-addressed かつ immutable で、同一 bytes は idempotent、異なる bytes は collision-safe な新 snapshot になる。
- `RL-006` concurrent writer は source-local nonblocking lock と bounded fetch/rebase/push を使い、force push、branch deletion、unbounded retry を使わない。
- `RL-007` publication は source snapshot、staged tree、commit、remote ref、readback identities を保存し、readback 不一致時は source event/report を retained にする。
- `RL-008` branch mismatch、foreign dirty/tree、invalid root、invalid identity、lock busy、remote conflict、readback gap は typed nonzero failure とし、silently switch/overwrite しない。
- `RL-009` legacy import は one-time, explicit, policy-owned inventory であり、通常 `sync`/`archive-agent-report` と同じ cleanup semantics にしない。
- `RL-010` retention class と deletion authority は policy repo #4 または general result-retention owner に属し、AgentCanon consumer は保持期間を推測しない。
- `RL-011` #461 command order は immutable: `ensure → status → stage/snapshot → commit → compare/rebase → push → remote readback → check-clean`。どの shortcut もこの順序を隠してはならない。
- `RL-012` `check-clean` は branch match、dirty、foreign dirty、foreign tree を別々に報告し、source/AgentCanon associated keys と unrelated key を区別する。

## Side Effects

`status`、`repo-key`、root/path resolution は read-only です。`ensure` は ignored archive clone の作成・fetch・stable branch switch を行い、branch switch 前には managed dirty path を commit して preserve します。`archive-agent-report`/`sync` は source-local lock、immutable snapshot、index/cursor/projection、local commit を作ります。`push` は policy-selected remote ref を bounded optimistic update し、成功後に exact remote readback を行います。hook hot path は archive、Git、network、SSH、auto-sync を呼ばず、local spool にだけ fingerprint event を書きます。

## Failure Semantics

| failure code / condition | state | side-effect rule | recovery |
| --- | --- | --- | --- |
| `source_repository_identity_unavailable` / invalid remote | `failed` | archive mutation を始めない | explicit network remote を owner route で解決 |
| `agent_canon_source_root_missing` / ambiguous | `failed` | guessed root を使わない | marker/layout/override を readback |
| `archive_branch_mismatch` | `blocked` | status/write は archive を mutate しない | explicit `ensure` 後に再確認 |
| `archive_transaction_busy` | `blocked` | second writer は即時 fail、既存 transaction は保持 | owner が次 checkpoint で再試行 |
| `foreign_dirty` / `foreign_tree` | `blocked` | unrelated key を current branch に混ぜない | correct stable branch へ移動して readback |
| content collision / malformed snapshot | `failed` or `retained` | existing bytes/index を上書きしない | new snapshot ID または owner repair |
| non-fast-forward remote | `retryable` | force push しない | fetch/rebase bounded append-only data、同じ order で再試行 |
| commit/tree/index/cursor/projection readback mismatch | `retained` | source spool/report を削除しない | exact identities を調べて repair |
| legacy source not mapped | `blocked` | source file を delete しない | policy-owned inventory/mapping を補完 |
| retention authority missing | `blocked` | deletion を実行しない | PR #4/general retention owner を参照 |

## Validation / Readback

source identity/root/branch の targeted readback:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py repo-key
python3 tools/agent_tools/runtime_log_archive_git.py status
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

immutable report route の readback (`tools/agent_tools/runtime_log_archive_git.py:command_archive_agent_report`):

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>
python3 tools/agent_tools/runtime_log_archive_git.py push
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

readback は `RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH=logs/<stable-id>`、branch match、commit/tree/index/cursor/projection digest、remote ref、foreign dirty/tree、retained source files を確認します。`status` が archive branch mismatch を返した場合、成功に読み替えず `ensure` の explicit operation と再 readback を行います。#461 の current evidence は `tools/agent_tools/runtime_log_archive_git.py` と `tests/agent_tools/test_log_repository_lifecycle.py` の commit/tree/remote/readback tests にあります。

## Clause IDs

この文書の design clauses は `RL-001` から `RL-012` です。各 clause は stable identity/root/branch/snapshot/concurrency/legacy/retention/command-order/readback の一つの owner と reverse mapping rule を持ちます。

## Exact Implementation Links

| design surface | current implementation | current evidence |
| --- | --- | --- |
| stable remote normalization / stable ID / branch | [`tools/agent_tools/log_repository_identity.py`](../../tools/agent_tools/log_repository_identity.py) `normalize_remote`, `stable_source_repository_id`, `stable_source_id`, `stable_log_branch` | commit #461 lines 33-140; lifecycle tests identity/branch cases |
| root layout resolution | [`tools/agent_tools/agent_canon_source_root.py`](../../tools/agent_tools/agent_canon_source_root.py) `resolve_agent_canon_source_root` | standalone/vendored/override tests in `test_log_repository_lifecycle.py` |
| logical spool/archive paths and metadata | [`tools/agent_tools/runtime_log_paths.py`](../../tools/agent_tools/runtime_log_paths.py) `repo_log_key`, `hook_event_spool_root`, `log_branch_key`, `agent_canon_git_commit_key`, `mounted_log_archive_root` | runtime path tests and hook hot-path contract |
| archive context and branch status | [`tools/agent_tools/runtime_log_archive_git.py`](../../tools/agent_tools/runtime_log_archive_git.py) `ArchiveContext`, `archive_status_summary`, `ensure_archive`, `prepare_archive_transaction` | branch mismatch, foreign tree, and status tests |
| immutable report snapshots | same file `report_snapshot_digest`, `_archive_agent_report_prepared`, `command_archive_agent_report` | `test_snapshots_are_content_addressed_idempotent_and_collision_safe` |
| concurrency | same file `PreparedArchiveTransaction`, `acquire_publication_attempt_lock`, `_rebase_to_remote`, `_compare_and_push` | `test_two_writers_retry_without_force_and_read_back_remote_ref` |
| legacy migration | [`documents/runtime/runtime-log-archive-migration.md`](../runtime/runtime-log-archive-migration.md) and `command_import_legacy` / `command_import_eval_results` | policy-owned inventory and migration docs |
| publication/readback | same file `publish_prepared_archive`, `command_push`, `command_sync`, `finalize_hook_spool_readback` | commit/tree/index/cursor/projection readback evidence |

## Exact #4 / #461 Owner Split

`agent-canon-log` PR #4 owns stable branch naming, archive repository policy, merge attributes, legacy retention inventory, and retention/deletion authority. AgentCanon #461 owns the consumer adapter: it resolves source identity and root, chooses the policy branch, maintains ignored local archive state, creates immutable snapshots, performs bounded optimistic publication, and fails closed on branch/dirty/readback errors. `documents/runtime/runtime-log-archive.md` remains the reader-facing consumer contract; this design records the split without copying PR #4 schema or retention prose.

## Design-To-Implementation Trace

| clause | current/planned implementation owner | exact file / symbol | reverse mapping rule |
| --- | --- | --- | --- |
| `RL-001` | current identity owner; policy authority external | `tools/agent_tools/log_repository_identity.py:normalize_remote`, `:stable_source_repository_id`, `:stable_source_id` | remote normalization or identity field changes require RL-001 and PR #4 review |
| `RL-002..RL-003` | current root/path owners | `tools/agent_tools/agent_canon_source_root.py`, `tools/agent_tools/runtime_log_paths.py` | any root marker, locator, or absolute-path persistence change maps to these clauses |
| `RL-004` | current archive branch owner | `tools/agent_tools/runtime_log_archive_git.py:build_context`, `:ensure_archive`, `:switch_to_archive_branch` | branch/ref/checkout changes map to RL-004 and E60 in the skill graph |
| `RL-005` | current snapshot owner | `tools/agent_tools/runtime_log_archive_git.py:report_snapshot_digest`, `:_archive_agent_report_prepared`, `:write_jsonl_once` | snapshot/index bytes or collision behavior must cite RL-005 |
| `RL-006..RL-008` | current lifecycle/publication owner | `tools/agent_tools/runtime_log_archive_git.py:prepare_archive_transaction`, `:acquire_publication_attempt_lock`, `:_compare_and_push`, `:publish_prepared_archive` | lock, retry, force, failure, or readback changes require clauses and lifecycle evidence |
| `RL-009..RL-010` | external policy + migration owner | `documents/runtime/runtime-log-archive-migration.md`, PR #4 | import/retention/deletion changes require external policy owner; AgentCanon cannot infer authority |
| `RL-011..RL-012` | current command/readback owner | `tools/agent_tools/runtime_log_archive_git.py:command_sync`, `:command_push`, `:command_check_clean`, `documents/runtime/runtime-log-archive.md:Push` | command order or dirty/foreign classification changes are design drift until reviewed |

Reverse mapping rule: every changed implementation path, public command, archive state, branch/ref operation, snapshot field, lock/retry behavior, legacy disposition, retention reference, or readback field must cite one or more `RL-*` clause IDs. A current implementation link without a clause is incomplete evidence; a planned implementation link is not a claim that code or tests have changed.

## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| request contract | #4/#461 owner split、stable identity/root/branch/snapshot/concurrency/legacy/retention、exact implementation links、immutable command order | user request; `RL-001..RL-012` | fixed |
| current state | AgentCanon #461 consumer adapter exists for identity, root, paths, snapshots, locks, bounded push, and readback | `tools/agent_tools/log_repository_identity.py`, `tools/agent_tools/agent_canon_source_root.py`, `tools/agent_tools/runtime_log_paths.py`, `tools/agent_tools/runtime_log_archive_git.py` | checked |
| target state | policy owner remains `agent-canon-log` PR #4 while AgentCanon owns consumer lifecycle and exact readback | `documents/runtime/runtime-log-archive.md`, PR #4, commit #461 | fixed |
| assumption | PR #4 is the authoritative external policy source for retention/schema and is not copied into AgentCanon | `documents/runtime/runtime-log-archive.md`, `RL-010` | explicit |
| assumption | current lifecycle tests are evidence only; this workstream changes no production implementation or tests | `tests/agent_tools/test_log_repository_lifecycle.py`; git diff scope | explicit |
| assumption | normalization means the canonical network host/path transformation before stable ID hashing | `tools/agent_tools/log_repository_identity.py:normalize_remote` | explicit |

## Clause ID Maintenance

この文書の design clauses は `RL-001` から `RL-012` です。#4 policy owner と #461 AgentCanon consumer owner を混ぜる変更、stable identity を path/chat に戻す変更、immutable snapshot を mutable mirror に戻す変更、または exact command order を省略する変更は、implementation ではなく design drift として扱います。
