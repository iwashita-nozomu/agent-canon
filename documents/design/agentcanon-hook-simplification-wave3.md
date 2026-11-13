<!--
@dependency-start
contract design
responsibility Defines the implementation-ready AgentCanon Wave 3 hook simplification target after the completed caller audit and reviewer-finding correction.
upstream design ../../.codex/README.md owns the project-scoped hook design and reader route.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs owns the active lifecycle dispatch contract.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_event_log.rs owns no-replace per-event spool transport for canonical hook telemetry.
upstream implementation ../../tools/runtime/archive/log_surface_inventory.py emits telemetry field inventory on demand.
upstream design ../../tools/catalog.yaml owns canonical tool registration.
upstream design ../../responsibility-scope.toml owns top-level responsibility coverage.
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs implements the selected active contract.
downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates active event and current-event readback.
@dependency-end
-->

# AgentCanon Hook Simplification Wave 3 Design

この文書は、2026-07-30 時点の親 `main` が pin する AgentCanon `0e3fe239` を基準に、完了済み hook caller audit と reviewer findings を反映した実装用 target state を固定する。これは設計文書だけの変更であり、production code、test code、catalog、inventory の実装変更、削除、commit はこの wave に含めない。

現在の実装は `tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs` が所有し、
`tools/bin/agent-canon codex-hook --contract` で読み戻します。以下は移行前の設計記録です。
完了済み移行の台帳・固定件数・digest・専用checkerは廃止しました。
現行の検証はイベント設定と動作・安全境界を対象にします。

## Authority と設計境界

- canonical design owner: [.codex/README.md](../../.codex/README.md) の Hook Context と `.codex/hooks/hook_dispatcher.py` の lifecycle contract
- canonical non-hook owners: `tools/agent/` と `tools/runtime/` の typed tool/checker modules
- decision: 3 active dispatcher events、inactive `Stop`、retired executable file なし
- no compatibility surface: 旧 executable、re-export、wrapper、shim、fallback CLI は作らない
- source checkout: fresh design clone from current `main`; implementation wave は同じ source snapshot を再読込して開始する
- source identity / spool boundary: dispatcher は repository-owned source-root resolver と明示 override から active source root を決め、`HookLogContext` はその repository identity と runtime spool root から event path を解決します。
- invocation ownership: 下表は `active handler -> record assembly -> one append` の順序と単一 owner を示します。behavior record がある場合は同じ base event に merge します。

| artifact owner | caller path | write/projection policy |
| --- | --- | --- |
| `.codex/hooks/hook_dispatcher.py` | finalized `UserPromptSubmit`/`PreToolUse`/`PostToolUse` path | one `record_hook_invocation` call; one `HookLogContext.append` for every active invocation; merge an eligible behavior record into that base event |
| `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` | direct import from dispatcher | returns `BehaviorEventRecord | None`; no I/O |
| `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs` | direct import from dispatcher | no-replace per-event spool append (`<spool>/<namespace>/<hook_name>/<hook_run_id>.json`) with `spooled|duplicate|failed` result |

### Repository identity and append-only spool

`hook_dispatcher.rs` は repository-owned source-root resolver と `AGENT_CANON_HOOK_SOURCE_ROOT` / target-root override を使います。Active root は repository-scoped event identity と behavior assembly の source context に使います。`HookLogContext` は明示 spool/result override または `AGENT_CANON_RUNTIME_ROOT` 配下の repository-keyed spool を使います。Runtime root がない場合や publication authority が失敗した場合は spool append が失敗し、finalized hook output は変わりません。

Active invocation は一つの finalized base event を作り、behavior record がある場合は同じ event に merge してから一度 append します。Canonical checkpoint JSONL は後続の `runtime-log-archive-git` owner が明示 checkpoint 時に生成し、hook hot path は archive sync、Git、network を呼びません。Hook events are written only to the append-only runtime spool; reports and Eval artifacts remain with their own owners.


Invalid interpretations:

- no transport relocation（hook transport は `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs` に留める）
- no compatibility wrapper / shim / fallback re-export

## Reviewer-corrected caller and readback audit

### 再現可能な監査コマンド

実装前に次の `git grep` と readback を同じ AgentCanon source root で実行し、出力を source packet に保存する。検索は `rg` を使わず、Git 管理対象と明示した runtime surface を対象にする。

```bash
git grep -l -E 'hook_dispatcher|hook_safety|execution_resource_plan_projection_guard|prompt_secret_guard|branch_worktree_guard|skill_usage_logger|hook_event_log|RETIRED_HOOK_ROUTES|retired_hook_routes|skill_lane|generate_agent_runtime_dashboard|check_convention_compliance|convention_compliance_contracts|run_python_quality_checks|report_artifact_checks|worktree-health|gpu-admission-r5-source-packet' -- . | sort -u
git grep -n -E 'hook_dispatcher|hook_safety|execution_resource_plan_projection_guard|prompt_secret_guard|branch_worktree_guard|skill_usage_logger|hook_event_log|RETIRED_HOOK_ROUTES|retired_hook_routes' -- .codex tools agents documents tests templates responsibility-scope.toml
git grep -n -E 'check_convention_compliance|convention_compliance_contracts|generate_agent_runtime_dashboard|skill_lane_detector|run_python_quality_checks|report_artifact_checks|worktree-health|gpu-admission-r5-source-packet' -- .codex tools agents documents tests templates responsibility-scope.toml
python3 .codex/hooks/hook_dispatcher.py --contract
python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py
```

`git read-tree` は checkout を作り直すための操作ではなく、実装 clone の index/readback が source snapshot と一致することを確認する読み取り前提の手順である。共有 checkout では実行せず、fresh implementation clone でだけ実行する。

### exact caller/readback path set

cutover 前に選択した source root と revision から caller/retired-path readback を再生成し、実装の evidence に残します。実行登録、import、CLI、checker、dashboard、skill lane、inventory、docs、catalog、responsibility、test と requested reviewer paths の必要な範囲を閉じます。後続の path 一覧は、この設計時点の readback 範囲の記録です。

**dispatcher、hook、registration**

`.codex/hooks.json`, `.codex/config.toml`, [.codex/README.md](../../.codex/README.md), `.codex/hooks/hook_dispatcher.py`, `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs`, `.codex/hooks/hook_safety.py`, `.codex/hooks/execution_resource_plan_projection_guard.py`, `.codex/hooks/prompt_secret_guard.py`, `.codex/hooks/branch_worktree_guard.py`, `.codex/hooks/skill_usage_logger.py`, `.codex/hooks/cause_investigation_guard.py`, `.codex/hooks/module_boundary_guard.py`, `.codex/hooks/library_implementation_guard.py`, `.codex/hooks/style_checker_guard.py`, `.codex/hooks/completion_review_guard.py`, `.codex/hooks/log_archive_mount_warning.py`, `.codex/hooks/reference_capture_guard.py`, `.codex/hooks/direct_rg_context_guard.py`, `.codex/hooks/task_authority_schema_guard.py`, `.codex/hooks/role_write_policy_guard.py`, `.codex/hooks/oop_readability_guard.py`, `.codex/hooks/first_party_library_guard.py`, `.codex/hooks/helper_inventory_guard.py`, `.codex/hooks/helper_first_guard.py`, `.codex/hooks/log_surface_inventory_guard.py`, `.codex/hooks/notebook_quality_guard.py`, `.codex/hooks/goal_completion_guard.py`, `.codex/hooks/codex_runtime_summary_logger.py`, `.codex/hooks/runtime_log_auto_sync.py`。

**canonical callers and reviewers**

`tools/runtime/dispatch/agent-canon/src/workflow_selection_eval.rs`, `eval/producers/evaluate_skill_workflow_prompts.py`, `tools/runtime/dispatch/agent-canon/src/prompt_capture.rs`（new）、`tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs`（new）、`tools/runtime/dispatch/agent-canon/src/tool_selection.rs`（new）、`tools/agent/orchestration/subagent_selection.py`（new）、`tools/runtime/dispatch/agent-canon/src/workflow_context.rs`（new）、`tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs`（new）、`tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs`（new）、`tools/runtime/dispatch/agent-canon/src/execution_resource_projection.rs`（new）、`tools/runtime/dispatch/agent-canon/src/hook_safety.rs`（new）、`tools/validation/semantic/tools/tool_rejection_preflight.py`, `tools/analysis/code/import_responsibility.py`, `tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs`  , `tools/runtime/dispatch/agent-canon/src/skill_lane_detector.rs`, `tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs`, `tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs`, `tools/runtime/archive/log_surface_inventory.py`, `tools/runtime/dispatch/agent-canon/src/eval_archive_paths.rs`, `tools/runtime/dispatch/agent-canon/src/runtime_log_archive.rs`, `tools/runtime/dispatch/agent-canon/src/codex_runtime_summary.rs`, `tools/validation/semantic/runtime/check_agent_runtime_alignment.py`, `tools/runtime/dispatch/agent-canon/src/convention_compliance.rs`, `tools/validation/semantic/convention/convention_compliance_contracts.toml`, `tools/validation/ci/checks/run_python_quality_checks.sh`, `.github/workflows/agent-improvement-guide.yml`, `tools/catalog.yaml`, `responsibility-scope.toml`, [documents/runtime/runtime-log-archive.md](../runtime/runtime-log-archive.md), [documents/runtime/runtime-log-archive-migration.md](../runtime/runtime-log-archive-migration.md), [documents/experiments/gpu-admission-r5-source-packet.md](../experiments/gpu-admission-r5-source-packet.md), [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md), [agents/skills/worktree-health.md](../../agents/skills/worktree-health.md), [AGENTS.md](../../AGENTS.md), [ROOT_AGENTS.md](../../ROOT_AGENTS.md), `README.md`。

**tests、fixtures、generated readback**

`tests/agent_tools/test_codex_hooks.py`, `tests/agent_tools/test_hook_event_log.rs`, `tests/tools/test_execution_resource_plan.py`, `tests/agent_tools/test_evaluate_workflow_selection.py`, `tests/agent_tools/test_evaluate_skill_workflow_prompts.py`, `tests/agent_tools/test_tool_rejection_preflight.py`, `tests/agent_tools/test_import_responsibility.py` , `tests/agent_tools/test_check_agent_runtime_alignment.py`, `tests/agent_tools/test_check-convention-compliance`, `tests/agent_tools/test_generate_agent_runtime_dashboard.py`, `tests/agent_tools/test_generate_agent_improvement_guide.py` , `tests/agent_tools/test_log_surface_inventory.py`, `tools/runtime/dispatch/agent-canon/tests/execution_resource_projection_native.rs`（new）、`tools/runtime/dispatch/agent-canon/tests/prompt_capture_native.rs`（new）、`tools/runtime/dispatch/agent-canon/tests/prompt_classifier_native.rs`（new）、`tools/runtime/dispatch/agent-canon/tests/tool_selection_native.rs`（new）、`tests/agent_tools/test_subagent_selection.py`（new）、`tests/agent_tools/test_workflow_context.rs`（new）、`tests/agent_tools/test_behavior_event_assembly.rs`（new）、`tests/agent_tools/test_historical_skill_usage_reader.py`（new）、`tools/runtime/dispatch/agent-canon/tests/hook_safety_native.rs`（new）、`tests/fixtures/behavior_events/`（new corpus）。

Audit conclusions:

1. current dispatcher has 23 former child names in `FORMER_ACTIVE_HOOK_CHILDREN` and a duplicated `RETIRED_HOOK_ROUTES` table;
2. the recorded baseline used a Python evaluator that dynamically loaded `.codex/hooks/skill_usage_logger.py`;
3. current dashboard next-action/readback text contain `.codex/hooks/skill_usage_logger.py` records;
4. current `.codex/hooks/hook_dispatcher.py` imports `.codex/hooks/hook_safety.py`, so moving that file requires a direct dispatcher import change and an absent old path proof;
5. convention, quality, report, worktree-health, GPU admission, catalog, responsibility, and generated-inventory surfaces are callers/readbacks, even when they do not invoke the hook process directly.

For completeness, the baseline legacy-name `git grep -l` readback also returned
non-runtime and historical surfaces across the source, evidence, tests, and
GitHub Issue records. The implementation packet reads those bounded surfaces;
GitHub Issue URLs/numbers remain the only durable Issue references and no local
Issue history is recreated as a compatibility surface.

## Responsibility partition: 9 blocking groups and 14 direct retirements

| group | current child/caller | reusable responsibility | one target owner |
| --- | --- | --- | --- |
| B1 | `execution_resource_plan_projection_guard.py` → dispatcher and projection tests | exact normalized input and projection byte validation | new `tools/runtime/dispatch/agent-canon/src/execution_resource_projection.rs`; managed producer authority is `tools/runtime/dispatch/agent-canon/src/execution_resource_plan.rs` |
| B2 | `skill_usage_logger.py` → evaluator and prompt-eval tests | pure prompt-to-workflow/skill classification | new `tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs`; evaluator imports it directly |
| B3 | `prompt_secret_guard.py` → prompt safety and dispatcher | secret classification and redacted block payload | `tools/runtime/dispatch/agent-canon/src/hook_safety.rs` |
| B4 | `branch_worktree_guard.py` and workflow docs → dispatcher | destructive Git intent, same-segment authority, redacted payload | the same `tools/runtime/dispatch/agent-canon/src/hook_safety.rs`; policy wording remains [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md) |
| B5 | `cause_investigation_guard.py` → preflight gate | cause evidence preflight | native `tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs` |
| B6 | `module_boundary_guard.py` → preflight gate | import boundary finding | existing `tools/analysis/code/import_responsibility.py` |
| B8 | `style_checker_guard.py` and quality script | Markdown/style validation | `tools/bin/agent-canon docs check` and `$md-style-check` |

The 14 direct-retirement positions are: `log_archive_mount_warning.py`, `reference_capture_guard.py`, `direct_rg_context_guard.py`, `task_authority_schema_guard.py`, `role_write_policy_guard.py`, `oop_readability_guard.py`, `first_party_library_guard.py`, `helper_inventory_guard.py`, `helper_first_guard.py`, `log_surface_inventory_guard.py`, `notebook_quality_guard.py`, `goal_completion_guard.py`, `codex_runtime_summary_logger.py`, `runtime_log_auto_sync.py`. The 9 blocking positions are `execution_resource_plan_projection_guard.py`, `skill_usage_logger.py`, `prompt_secret_guard.py`, `branch_worktree_guard.py`, `cause_investigation_guard.py`, `module_boundary_guard.py`, `library_implementation_guard.py`, `style_checker_guard.py`, and `completion_review_guard.py`. `first_party_library_guard.py` is the shared B7/direct cleanup position and is stored once in this historical migration plan.

### Single decision-owner routes for B7 and B9

| group | final decision owner | read-only consumers/callers | one execution route |
| --- | --- | --- | --- |

The read-only consumers may not emit an independent B7/B9 decision, approval, or alternate execution route. Their fields are projections of the decision owner result: B7 exposes authority `allowed/reason`; B9 exposes the current candidate, decision, dispatch blocker, and `publication_unlocked`. A missing or malformed owner result is a blocking finding, not a consumer-local fallback.

## Positive target state

### Three active dispatcher events and inactive Stop

`.codex/hooks.json` registers only these three event groups, each invoking `.codex/hooks/hook_dispatcher.py` once. `Stop` is a contract row with `active=false`, is not registered, reads no stdin, emits no output and no telemetry, and remains an inactive no-op forever.

| event | matcher | active owner call | post-result caller action | success output | failure semantics |
| --- | --- | --- | --- | --- | --- |
| `UserPromptSubmit` | none | `hook_safety.secret_kind` then `secret_block_payload` | after the safety result is final, call `behavior_event_assembly.record_hook_invocation(parts)` exactly once | no output on pass; official redacted block on match | secret match block; malformed input and spool failure fail-open |
| `PreToolUse` | `Bash\|apply_patch\|python\|python3` | `hook_safety.first_block` then `branch_block_payload` | after the safety result is final, call `behavior_event_assembly.record_hook_invocation(parts)` exactly once | no output on pass; operation/hash-only block | unauthorized destructive Git block; malformed input and spool failure fail-open |
| `PostToolUse` | current ten-tool matcher set | normalize six fields, then `execution_resource_projection.validate_projection_bytes` | after the projection result is final, call `behavior_event_assembly.record_hook_invocation(parts)` exactly once | validated successful Bash projection as official `additionalContext` | malformed input, non-Bash, unsuccessful response, invalid projection, spool failure fail-open |

The active handler set is exactly `UserPromptSubmit.secret_safety`, `PreToolUse.destructive_git_safety`, `PostToolUse.execution_resource_projection`. The dispatcher is the sole caller of `record_hook_invocation`; `behavior_event_assembly.rs` is the sole pure owner for eligibility, event-id, and snapshot assembly. The dispatcher imports the owner directly and calls it after, never before, the existing handler result is finalized. The call is exactly once per active handler invocation, including a finalized block/fail-open result; `Stop` is inactive and calls it zero times. The official output schema remains `agent-canon.posttooluse-stop.v1`; contract readback schema remains `agent-canon.hook-contract.v1` with `active_events` length 3 and `inactive_events=["Stop"]`.

### Dispatcher caller contract for `record_hook_invocation`

The dispatcher imports `record_hook_invocation` directly from `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` using the same source-root import bootstrap as the other non-hook owners. Each active handler constructs one immutable `HookInvocationParts` value only after its existing handler result is final:

```text
HookInvocationParts = frozen {
  hook_event_name: "UserPromptSubmit" | "PreToolUse" | "PostToolUse",
  hook_invocation_id: non-empty str,                 # current hook_run_id
  hook_payload: Mapping[str, JSONValue] | None,       # parsed hook payload; raw text is never copied
  payload_status: "parsed" | "malformed_payload",
  handler_result: FinalHandlerResult,                # finalized safety/projection result
  classifier_rules: FrozenClassifierRules,           # immutable repo_root/catalog/routing rules
  tool_selection: ToolSelection | None,
  subagent_selection: SubagentSelection | None,
  workflow_context: WorkflowContext,                 # empty typed context when absent
}
```

`handler_result` includes the finalized dispatcher status, output/block decision, and safe result fields; it never contains raw prompt, command, secret, stdout, or stderr material. `classifier_rules` is the already-frozen input described in the pure classifier contract. `tool_selection`, `subagent_selection`, and `workflow_context` are typed values or explicit empty values; the dispatcher does not recompute any of them. The caller contract is therefore one direct import of `behavior_event_assembly`, one parts construction in parts-preparation, one call, and no caller-side artifact serialization/write during parts-preparation.

The owner boundaries for admission are fixed:

| decision | owner | true condition | false result |
| --- | --- | --- | --- |
| `should_log(parts, signals)` | `behavior_event_assembly.rs` | `parts` contains a configured prompt/classifier signal or workflow/workflow-context/subagent/tool selection signal | `False`; no classifier-owned side effects; dispatcher handler result is unchanged |
| `eligible_hook_invocation(parts, signals)` | `behavior_event_assembly.rs` | active event name; finalized handler result; `payload_status="parsed"`; status is not `blocked_secret`, `blocked_destructive_git`, `blocked_parent_mutation`, `malformed_payload`; and `should_log(parts, signals)` | `skipped`, with no behavior record candidate |

`Stop` never constructs parts. A finalized safety block is still passed once to the assembly caller, but is ineligible and cannot cause prompt/command material to be captured. A parsed `PostToolUse` with an unsuccessful response or invalid resource projection remains eligible when it contains a safe behavior signal. Preserve the original handler status in the same event; do not relabel a projection failure as `pass`. The assembly owner, not the dispatcher, owns `should_log` and `eligible` and is the only place that may turn an eligible invocation into a behavior snapshot.

Resource projection validity controls forwarding of `additionalContext`, not whether
an independently safe observation exists. In particular, ordinary command output,
non-Bash tool results, and additional metadata can fail the projection-specific
shape without invalidating bounded tool-name and fingerprint evidence. Keep raw
command arguments, stdout, stderr, and extra metadata out of that evidence. The
projection validator, payload parser, safety exclusions, and single spool writer
retain their own contracts. Recording the failure
allows diagnosis without guessing a producer or weakening projection validation.

Dispatcher must build a typed workflow context before assembly and pass it into parts:

1. `hook_dispatcher.py` executes `workflow_context.load_workflow_context(...)` before constructing parts; load failure is fail-open to a typed empty context.
2. `hook_dispatcher.py` completes the event-specific safety or projection handler and stores its `FinalHandlerResult`.
3. The dispatcher executes `subagent_selection.select_subagents(...)` and `tool_selection.select_tools(...)` in parts-preparation.
4. If parts-preparation fails, typed input is normalized to explicit empties and the assembly call still happens exactly once.
5. The dispatcher builds one immutable `HookInvocationParts` and calls `record_hook_invocation(parts)` exactly once.
6. `behavior_event_assembly.rs` validates parts, runs pure prompt capture + `prompt_classifier.prompt_intake_signals`, consumes precomputed typed tool/subagent/workflow-context values from `parts`, applies eligibility and `should_log`, assembles the one canonical snapshot, and derives `event_id`, returning `BehaviorEventRecord | None`.
7. The dispatcher loads the base spool entry, merges behavior fields into that base when a record exists, and calls `HookLogContext.append(...)` exactly once for every active invocation after the handler result is finalized.
8. The dispatcher returns the finalized handler output unchanged after the one base append attempt. Spool status never creates a second file or changes the safety/projection result.

`record_hook_invocation` is fail-open at the telemetry boundary: `skipped` and malformed inputs cannot change the finalized hook decision or create a new block. The assembly API returns a typed `BehaviorEventRecord | None` and does not raise into the dispatcher.

Dispatcher parts-preparation remains I/O-free for artifact writes. Caller-side transport is exactly one `HookLogContext.append(...)` call for every active invocation (including blocked/malformed/ineligible). An eligible behavior record is merged into that same append.

### Transport hook name, semantic event kind, cardinality, and identity

`hook_event_name` is transport metadata and is never used as the semantic event kind. It is exactly one of `UserPromptSubmit`, `PreToolUse`, or `PostToolUse` on an active invocation. `event_kind` is the behavior meaning and is independent of the transport name: `behavior_snapshot`, `prompt_intake`, `tool_selection`, `subagent_selection`, `workflow_attribution`, or `skill_lane`. The canonical replacement record uses `event_kind="behavior_snapshot"` and carries the other semantic dimensions as fields; the dimension names are not aliases for `hook_event_name`. The old ambiguous `event` field is removed from the target behavior schema and has no compatibility alias.

Transport status is emitted only by `HookLogContext.append`, and telemetry cardinality is:

| source | cardinality for one invocation | canonical identity |
| --- | --- | --- |
| ineligible invocation | 0 behavior record candidate → 1 base append attempt (`HookLogContext.append`) with no behavior fields | `hook_invocation_id`/current `hook_run_id` plus `hook_event_name` |
| eligible behavior invocation | exactly 1 behavior record candidate merged into the one base append | one `event_id` for the snapshot; no per-field or per-dimension duplicate rows |
| blocked_secret | 0 behavior record candidate → 1 base append; telemetry fields include `safety_decision` only | same as invocation id + event name, with safety telemetry context |
| blocked_destructive_git | 0 behavior record candidate → 1 base append; telemetry fields include `safety_decision`, `operation` | same as invocation id + event name, with safety telemetry context |
| malformed_payload | 0 behavior record candidate → 1 base append; telemetry fields include base status/fingerprint only | same as invocation id + event name, with safety telemetry context |
| append result (spooled/duplicate/failed) | status is owned by `HookLogContext.append`; it never creates another event or changes the finalized handler result | the base event retains one `hook_run_id` and at most one merged `event_id` |

`hook_invocation_id` is the current `hook_run_id` supplied by the dispatcher context and is reused when the same invocation is retried. `event_id` is the lowercase SHA-256 of this exact UTF-8 preimage, with no newline:

```text
event_id_preimage = json.dumps(
  {
    "schema": "agent-canon.behavior-event.v1",
    "record_kind": "behavior_event",
    "hook_invocation_id": hook_invocation_id,
    "hook_event_name": hook_event_name,
    "event_kind": event_kind,
    "payload_fingerprint": payload_fingerprint,
    "behavior_fields": behavior_fields_without_event_id_or_timestamp,
  },
  sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
).encode("utf-8")
event_id = hashlib.sha256(event_id_preimage).hexdigest()
```

`timestamp` is not in the preimage; it is the invocation observation timestamp and must be UTC. `behavior_fields_without_event_id_or_timestamp` contains every schema field in canonical key order, including explicit empty sentinels. A retry with identical invocation id, payload fingerprint, hook name, kind, and fields therefore has identical bytes and is a duplicate. The parser accepts the first canonical instance, increments `duplicate_count` for later identical instances, and rejects a conflicting same-`event_id` byte sequence as `conflicting_event_id`. A second snapshot for the same `hook_invocation_id` is malformed even if its hash differs. A snapshot with a mismatched `hook_event_name` or `event_kind` is malformed; `Stop` cannot produce a record. These rules are separate from hook spool statuses (`spooled|duplicate|failed`) and do not change fail-open hook safety behavior.

### Native dispatcher owner calls

The active dispatcher calls the native safety, projection, selection, behavior,
and spool owners directly. These library calls preserve the existing handler
result and enrich its single spool event with eligible behavior evidence:

```rust
use crate::tool_selection::{select_tools, ToolSelection};
use crate::subagent_selection::{select_subagents, SubagentSelection};
use crate::workflow_context::WorkflowContext;
use crate::hook_event_log::{utc_now, HookLogContext};
use crate::behavior_event_assembly::{record_hook_invocation, HookInvocationParts};
```

These modules live under `tools/runtime/dispatch/agent-canon/src/`.
`hook_safety.rs` owns secret and destructive-Git checks;
`execution_resource_projection.rs` owns projection validation.
The dispatcher calls behavior assembly once per active invocation and appends
through `hook_event_log.rs`. Task progress projections are retired.

Raw-to-spool mapping: for every active invocation, the handler result defines one base spool record; behavior-only fields are an optional enrichment layer merged into that base before append.

## Current hook contract

The completed migration keeps no runtime retirement ledger, fixed retired-file
counts, digest, or dedicated caller-audit checker. Migration history remains in
Git. The native dispatcher contract reports current events and active handlers;
existing hook configuration, safety, and event tests validate that behavior.

## Exact raw event, input, output, block, spool, and telemetry mapping

The following is copied from the current implementation and is the parity oracle. `None` means JSON null or Python nullable return; an omitted field is not equivalent to null.

| layer | field(s) | current domain/nullability | limit/status | target mapping |
| --- | --- | --- | --- | --- |
| raw stdin | `raw_payload` | bytes; UTF-8 decoded; parsed value must be an object, else nullable parse result `None` | `MAX_HOOK_PAYLOAD_BYTES=262144`; empty/whitespace becomes `{}`; duplicate keys, non-finite constants, invalid UTF-8/JSON, recursion, over-limit become `malformed_payload` | dispatcher parses once; no owner changes semantics |
| prompt input | `prompt` | optional raw key; non-string becomes `""`; `secret_kind` returns `str | None` | four regex classes; first match wins; raw prompt never enters block payload or spool | `hook_safety.payload_prompt` and `secret_kind` |
| pre-tool input | `tool_name`, `tool_input.command/cmd`, top-level `command/cmd` | strings when present, otherwise `""`; shell names exactly `Bash`/`bash` | command is parsed in memory; raw command is never output/telemetry | `hook_safety` payload extractors and Git classifier |
| normalized PostToolUse | `hook_event_name`, `schema_version`, `tool_input_fingerprint`, `tool_name`, `tool_input`, `tool_response` | exact six-key object; fingerprint is 64 lowercase hex; `tool_input` object; response exact `{exit_code:int, stderr:str, stdout:str}`; `exit_code` rejects bool | schema `agent-canon-post-tool-use-input/v1`; extra/missing/wrong-type fields → `invalid_projection` | `execution_resource_projection.validate_normalized_input` |
| projection | `admission`, `completion_coverage_path`, `error`, `exit_code`, `plan_fingerprint`, `plan_path`, `projection`, `run_id`, `schema_version` | exact nine keys; `admission` and `error` are nullable; hashes 64 lowercase hex; paths are derived from safe `run_id` | stdout max `MAX_PROJECTION_BYTES=65536`; exactly one LF, no CR, canonical sorted JSON, schema `execution-resource-plan/v1`, kind `post_tool_use` | same nine-key validator in new non-hook owner |
| admission | `admission_fingerprint`, `guarantee`, `namespace_id`, `provision_receipt_fingerprint`, `selected_uuids` | nullable object or exact five-key object; namespace regex bounded 1–64; UUIDs match `GPU|MIG` opaque form | guarantee `run-level-opaque-uuid-admission`; wrong/null shape → invalid projection | unchanged |
| projection error | `kind` | nullable object or exact one-key object | one of `managed_gpu_failure`, `managed_gpu_execution`, `see_execution_resource_plan` | unchanged |
| safety block | `decision`, `reason`, `next_action`, `remediation`; Git adds `operation`, `command_sha256` | decision fixed `block`; reason/next_action strings; remediation list of strings; Git operation string and command hash 64 lowercase hex; prompt/command material absent | official wrapper adds `schema`, `hookSpecificOutput.{hookEventName,additionalContext}`; block status is `blocked_secret` or `blocked_destructive_git` | new `hook_safety`, same payload bytes/fields |
| projection output | `schema`, `hookSpecificOutput.{hookEventName,additionalContext}` | strings; context is the already validated canonical projection stdout | official schema `agent-canon.posttooluse-stop.v1`; context max is bounded by 65536-byte projection | new projection owner, same wrapper |
| spool base | `hook_run_id`, `timestamp`, `payload_fingerprint`, `status`, `hook_event_name` | all non-empty strings; payload hash 64 lowercase hex; timestamp UTC ISO string | no explicit spool event byte limit in current code; only bounded hashes/status/short telemetry are written | preserve no new input/raw text |
| spool context | `source_repo_key`, `hook_log_namespace` | non-empty strings added by `HookLogContext`; optional `codex_trace_key`, `codex_thread_id` are non-empty strings when environment provides them | namespace slug max 80; no-replace per-event path; mode 0600 temp file | `hook_event_log.rs` remains sole transport owner |
| spool identity | `hook_run_id` | `hook-<compact timestamp>-<10 hex digest>-<10 hex nonce>`; path basename-safe; `fingerprint_json` helper returns 12 lowercase hex, while namespace disambiguation uses 8 lowercase hex | append-only no-replace; duplicate identical bytes is `duplicate`; conflict/I/O is failure | dispatcher catches all append failures and stays fail-open |
| append result | `status`, `hook_run_id`, `spool_path`, `event_sha256`, `error_code` | status is `spooled|duplicate|failed`; path is `Path`; event hash is 64 lowercase hex on success; error code is empty or `event_identity_missing|event_schema_invalid|spool_unavailable|spool_io_failure|spool_conflict` | returned by `HookLogContext.append`; not copied into dispatcher safety status | transport owner preserves result domain |
| telemetry | `safety_decision`, `operation` | optional non-empty strings; only block events emit them | UserPrompt block emits `safety_decision=block`; PreTool block additionally emits `operation`; no prompt, command, secret, stdout, stderr | field names and omission rules unchanged |
| behavior JSONL | `event_id`, `hook_invocation_id`, `hook_event_name`, `event_kind`, timestamp, and the complete logger parity field union | required fields use the domains above; empty strings/lists/bools/counts are explicit; no JSON null for an absent parity field | current `skill_usage.jsonl` has no independent event-byte limit; target `behavior_events.jsonl` retains that absence, while prompt excerpt remains 600 characters and all canonical JSON is UTF-8/one-line | no file write owner in this table; readback is owned by dashboard/parser layer |

Dispatcher status domain is exactly `malformed_payload`, `pass`, `blocked_secret`, `blocked_destructive_git`, `projection_forwarded`, `unsuccessful_tool_response`, and `invalid_projection`; `Stop` emits none. `spooled`, `duplicate`, `failed`, and error codes belong to `HookAppendResult`, not dispatcher safety status. Spool failure never changes a safety decision.

## Skill logger replacement: classifier, lane emitter, dashboard, inventory

### Complete `skill_usage_logger` responsibility map

The old hook module is not replaced by one broad helper. Its complete responsibility set is split into single owners with one API and one write set per row. A caller may consume a result from an owner, but may not reimplement that responsibility or write the owner's artifact.

| responsibility | single owner | API contract | write set / side effect | callers |
| --- | --- | --- | --- | --- |
| prompt capture and redaction | `tools/runtime/dispatch/agent-canon/src/prompt_capture.rs` | `capture_prompt(payload) -> PromptCapture` | none; immutable return containing status, redacted excerpt, original char count, fingerprint | `prompt_classifier.py`, behavior assembly |
| prompt classification | `tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs` | `prompt_intake_signals(inputs: PromptClassifierInputs) -> PromptIntakeSignals` | none; no subprocess, Git, network, environment mutation, or file I/O | workflow evaluator and behavior assembly |
| feedback, candidate-reason, and related-skill normalization | `tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs` | `feedback_targets(signals) -> tuple[str, ...]` | none; preserves current feedback labels/action/target and candidate-reason ordering | evaluator and behavior assembly consume the classifier result |
| tool selection | `tools/runtime/dispatch/agent-canon/src/tool_selection.rs` | `select_tools(payload) -> ToolSelection` | none; tuple/list ordering is part of return contract | `hook_dispatcher.py` parts-preparation caller |
| subagent selection and attribution | `tools/agent/orchestration/subagent_selection.py` | `select_subagents(payload, workflow_context) -> SubagentSelection` | none; selection/workflow attribution is returned, not emitted directly | `hook_dispatcher.py` parts-preparation caller |
| workflow context store/load | `tools/runtime/dispatch/agent-canon/src/workflow_context.rs` | `load_workflow_context(path) -> WorkflowContext`; `store_workflow_context(path, context) -> StoreResult` | only the existing paired `skill_usage_context.json` path (resolved under the selected log/report directory); atomic write; load/store failure is fail-open to an empty context, never a second event | `hook_dispatcher.py` loads for parts; evaluator/workflow lifecycle owner stores |
| behavior record assembly | `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` | `record_hook_invocation(parts) -> BehaviorEventRecord | None` | one record candidate per eligible invocation; returns `BehaviorEventRecord` only, no append/monitor/IO | dispatcher is the sole caller |
| historical skill-usage readback | `tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs` | `agent-canon historical-skill-usage-read --path PATH` emits records, counts, reasons, and status | opens `skill_usage.jsonl` read-only; no archive writes | improvement guide and fixture tests |

The ownership boundary is intentional: `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs` owns canonical per-event spool transport and `tools/runtime/dispatch/agent-canon/src/runtime_log_archive.rs` owns explicit checkpointing into `behavior_events.jsonl`. Dashboard, Eval, and historical readers remain read-only consumers of their owner-defined inputs.

### Pure classifier owner

`tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs` owns the current `PromptIntakeSignals` fields exactly: `skills`, `selected_workflows`, `candidate_skills`, `candidate_skill_reasons`, `candidate_workflows`, `candidate_tools`, `feedback_labels`, `feedback_action`, all as tuples of strings except `feedback_action: str`. `feedback_targets()` remains pure. `prompt_intake_signals(inputs)` preserves current keyword, catalog, structural-lane, validation-repair, feedback, and related-skill ordering. `behavior_event_assembly.rs` consumes the returned signals and owns `should_log`.

The classifier receives all repository-dependent knowledge as immutable input to return dimensions consumed by assembly; it does not discover it. The exact input contract is:

```text
PromptClassifierInputs = frozen {
  prompt: str,
  repo_root: Path,                         # resolved once by evaluator; never read by classifier
  catalog: FrozenMapping[str, FrozenValue],
  routing_rules: FrozenMapping[str, FrozenValue],
  structural_lane_evidence: tuple[SkillLaneEvidence, ...],
  validation_repair_evidence: tuple[str, ...],
}
```

`catalog` and `routing_rules` are recursively frozen mappings/tuples before injection; `repo_root` is an immutable value used only as provenance and is not opened. The evaluator loads the current catalog and routing rules once, freezes them, and passes them to the pure function. The classifier performs no subprocess, `importlib` loading, Git, network, environment mutation, file read/write, or hook-log append. A missing injected rule is classified as missing evidence with the current fail-open result; the classifier does not shell out to recover it.

`workflow_selection_eval.rs` calls `prompt_classifier::prompt_intake_signals`
directly with immutable inputs. It retains the existing case/result fields and
expected/forbidden workflow oracle. The manifest bridge exposes the same
loader to the remaining producer caller.

### Skill-lane detector and behavior emitter

The existing pure `tools/runtime/dispatch/agent-canon/src/skill_lane_detector.rs` remains the structural concept detector. Its implementation-ready output contract is:

```text
SkillLaneEvidence {
  schema: "agent-canon.skill-lane.v1",
  lane: str,
  route_skills: tuple[str, ...],
  evidence_categories: tuple[str, ...],
  status: "observed" | "candidate",
  source: "prompt_classifier",
}
```

The detector returns no record for an unmatched lane; it never writes logs. `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` is the sole pure assembler (`record_hook_invocation(parts) -> BehaviorEventRecord | None`) and does not perform transport I/O. Canonical durable behavior events are serialized by `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs` into per-event no-replace spool files with result `spooled|duplicate|failed`. Task progress projections are retired. The event envelope is the fixed `agent-canon.behavior-event.v1` schema:

```text
{
  "schema": "agent-canon.behavior-event.v1",
  "event_id": str,
  "hook_invocation_id": str,
  "hook_event_name": "UserPromptSubmit" | "PreToolUse" | "PostToolUse",
  "event_kind": "behavior_snapshot",
  "timestamp": RFC3339 UTC str ending in Z,
  "source": "behavior_event_assembly",
  "status": "pass",
  "prompt_capture_status": "present" | "missing",
  "prompt_excerpt_redacted": str,
  "prompt_char_count": int >= 0,
  "tool_name": str,
  "tool_command_verb": str,
  "selected_tools": list[str],
  "feedback_labels": list[str],
  "candidate_skill_reasons": list[str],
  "subagent_invoked": bool,
  "subagent_event_kind": str,
  "subagent_tool_name": str,
  "subagent_agent_type": str,
  "subagent_target": str,
  "subagent_targets": list[str],
  "subagent_target_count": int >= 0,
  "subagent_model": str,
  "subagent_reasoning_effort": str,
  "subagent_fork_context": bool,
  "subagent_prompt_fingerprint": str,
  "subagent_prompt_char_count": int >= 0,
  "subagent_item_count": int >= 0,
  "selected_workflows": list[str],
  "workflow_selection_kind": "" | "declared_workflow" | "inherited_workflow" | "context_workflow",
  "workflow_attribution_kind": "owner" | "context" | "missing",
  "workflow_owner": str,
  "workflow_owner_workflows": list[str],
  "workflow_context_kind": str,
  "workflow_context_source": str,
  "workflow_context_workflows": list[str],
  "workflow_context_timestamp": str,
  "workflow_context_source_event": str,
  "skill_lane": list[SkillLaneEvidence],
  "candidate_skills": list[str],
  "candidate_workflows": list[str],
  "candidate_tools": list[str],
  "feedback_action": str,
}
```

The fields above preserve the current logger's types and empty-value nullability: strings use `""` rather than JSON null; lists use `[]`; booleans are always present; counts are nonnegative integers. `prompt_excerpt_redacted` is bounded to 600 characters, `prompt_char_count` is the original prompt length, and `subagent_prompt_fingerprint` is `""` or 16 lowercase hex characters. `tool_name` and `tool_command_verb` are `""` when no tool/command is present. `workflow_context_timestamp` is `""` when no context exists. `skill_lane` is `[]` when no structural lane matches. `status` is `pass` for an emitted event; parser status is separate and never replaces this field. `hook_event_name` and `event_kind` are required non-null strings from the fixed domains above; they are never inferred from each other.

The exact behavior-event field set is the union of the envelope fields and the parity fields in the table below; no implementation may silently drop a current logger field because a dashboard row does not display it.

The classifier returns the existing behavior dimensions consumed by assembly: selected/candidate skills and workflows, `candidate_skill_reasons`, feedback labels/action/targets, prompt capture, tool selection, subagent selection, workflow attribution/context, and structural lane evidence. This keeps one execution route and one event identity for dashboard aggregation. `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs` performs per-event no-replace spool append; `tools/runtime/dispatch/agent-canon/src/runtime_log_archive.rs` emits checkpoint `behavior_events` lines after explicit checkpointing from per-event spools, and task progress projections are retired. `hook_event_log` never writes shared `behavior_events.jsonl`; it only spools per-event bytes. `runtime-log-archive-git` writes checkpoint JSONL only after invocation and outside the hot-path.

The remaining current logger fields are carried without semantic loss as follows; these are part of the behavior-event schema even when a dashboard view does not display them:

| current field family | exact type/nullability and domain |
| --- | --- |
| `hook_run_id` → `hook_invocation_id`, `hook_log_namespace`, `timestamp`, `root` | non-empty `str`; timestamp is UTC ISO text; `hook_invocation_id` is the current hook-run identity and is distinct from the derived behavior `event_id` |
| `event` (legacy logger field) → `event_kind` plus `hook_event_name` | legacy `event` is not copied as an alias; target kind is `behavior_snapshot`, transport name is required from dispatcher context |
| `event_declared`, `subagent_invoked`, `subagent_fork_context`, `prompt_feedback_detected` | `bool`, always present |
| `prompt_fingerprint`, `tool_input_fingerprint`, `payload_fingerprint`, `subagent_prompt_fingerprint` | `str`; empty sentinel or lowercase hex; prompt/subagent fingerprints are 16 hex characters, JSON fingerprints are 12 hex characters |
| `prompt_excerpt_truncated`, `skill_selection_kind`, `workflow_selection_kind`, `workflow_attribution_kind`, `workflow_context_kind`, `workflow_context_source`, `workflow_context_source_event`, `tool_selection_kind` | `str` or `bool` exactly as current emitter; empty string means not applicable; `workflow_attribution_kind` is `owner|context|missing`, `workflow_selection_kind` is empty or `declared_workflow|inherited_workflow|context_workflow`, and `tool_selection_kind` is empty or `executed_tool` |
| `skills`, `selected_skills`, `selected_workflows`, `workflow`, `workflow_owner_workflows`, `workflow_context_workflows`, `candidate_skills`, `candidate_skill_reasons`, `candidate_workflows`, `candidate_tools`, `selected_tools`, `subagent_targets`, `skill_source_fields`, `feedback_labels`, `feedback_targets`, `tool_input_keys` | `list[str]`, empty list means no value; preserve current sorted/tuple order after parser normalization |
| `selected_workflow`, `workflow_family`, `workflow_owner`, `tool_name`, `tool_command_verb`, `subagent_event_kind`, `subagent_tool_name`, `subagent_agent_type`, `subagent_target`, `subagent_model`, `subagent_reasoning_effort`, `feedback_action`, `workflow_context_timestamp`, `workflow_monitor_report_dir` | `str`, empty sentinel when absent; `subagent_event_kind` is empty or `spawn|send_input|wait|close|resume`; `feedback_action` is empty or `prompt_repair|knowledge_record`; workflow owner/family are first selected workflow only under current attribution rule |
| `skill_count`, `selected_workflow_count`, `candidate_skill_count`, `candidate_workflow_count`, `candidate_tool_count`, `selected_tool_count`, `subagent_target_count`, `subagent_prompt_char_count`, `subagent_item_count`, `observed_text_field_count`, `observed_text_value_count`, `payload_key_count`, `workflow_monitor_event_count`, `workflow_monitor_feedback_count`, `workflow_monitor_subagent_event_count`, `prompt_char_count`, `tool_input_key_count` | `int >= 0`; zero is the absent/empty sentinel |

The `workflow_monitor_*` names remain schema-compatibility fields: the native dispatcher passes no report directory, so `workflow_monitor_report_dir` is empty and the related counters are zero. No hook-side report output is produced. The schema retains the other prompt, tool, feedback, selection, text-source, payload, and root fields for Eval/archive readers.

### Dashboard readback contract

`generate_agent_runtime_dashboard.py` reads canonical `behavior_events.jsonl` and archived workflow-monitor behavior-event rows. `generate_agent_improvement_guide.py` uses `agent-canon historical-skill-usage-read --path PATH` for archived `skill_usage.jsonl` through the native reader. This route opens the history read-only and preserves its records and diagnostics. Historical files are never imported or executed as Python, appended to, rewritten, or regenerated into the target inventory.

The parser boundary is fixed:

| input artifact | parser owner | accepted purpose | forbidden behavior |
| --- | --- | --- | --- |
| `behavior_events.jsonl` and `behavior_event_json=` monitor lines | `generate_agent_runtime_dashboard.py` parser for behavior readback | active target behavior readback and dashboard oracle | no legacy-field guessing; no fallback to `skill_usage.jsonl` |
| historical `skill_usage.jsonl` | `tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs` | read-only migration/improvement-guide evidence, preserving old field names and nullability | no old Python reader import or execution; no append, rewrite, or conversion into an active event |

Fixtures are exact: `tests/fixtures/behavior_events/accepted.jsonl`, `duplicate.jsonl`, `malformed.jsonl`, `out_of_order.jsonl`, `escaping.jsonl`, and `oracle.json`. The historical parser's valid and malformed readback cases remain covered inline, while the behavior fixtures prove that the active parser never accepts legacy records as target records.

The dashboard parser accepts canonical compact JSON lines from `behavior_events.jsonl`. It may additionally read `behavior_event_json=` projection lines in the Behavior Events section as a transport readback, but it never treats a projection line as a second canonical record. It normalizes each accepted canonical record into the existing function set. Its typed readback is:

```text
{
  "schema": "agent-canon.behavior-readback.v1",
  "accepted_count": int >= 0,
  "duplicate_count": int >= 0,
  "malformed_count": int >= 0,
  "ignored_count": int >= 0,
  "malformed_by_reason": {str: int >= 1},
  "prompt_entries": int >= 0,
  "prompt_excerpt_entries": int >= 0,
  "prompt_missing_excerpt_entries": int >= 0,
  "prompt_total_chars": int >= 0,
  "tool_selection_entries": int >= 0,
  "tools": {str: int >= 1},
  "command_verbs": {str: int >= 1},
  "selected_tools": {str: int >= 1},
  "selected_skills": {str: int >= 1},
  "candidate_skills": {str: int >= 1},
  "candidate_skill_reasons": {str: int >= 1},
  "selected_workflows": {str: int >= 1},
  "candidate_workflows": {str: int >= 1},
  "feedback_labels": {str: int >= 1},
  "feedback_actions": {str: int >= 1},
  "subagent_events": {str: int >= 1},
  "subagent_tools": {str: int >= 1},
  "subagent_agent_types": {str: int >= 1},
  "subagent_targets": {str: int >= 1},
  "workflow_attribution": {"owner": int, "context": int, "missing": int},
  "workflow_context_attributed_entries": int >= 0,
  "lanes": {str: int >= 1},
  "status": "present" | "missing" | "malformed",
}
```

Dashboard oracle is fixed: `prompt_entries` counts accepted events with `prompt_capture_status=present`; `prompt_excerpt_entries` counts those with non-empty `prompt_excerpt_redacted`; `prompt_missing_excerpt_entries` counts present prompts with an empty excerpt; `prompt_total_chars` sums `prompt_char_count`. `tool_selection_entries` counts accepted events with non-empty `tool_name`; `tools`, `command_verbs`, and `selected_tools` count their corresponding non-empty values. Selection metrics use the current canonical selected/candidate normalization, with candidate skills excluded only when every supplied reason is `related_to=...`; later selected evidence confirms a candidate within the same namespace, and workflow candidates may be confirmed cross-namespace exactly as today. Workflow attribution uses current direct attribution first, then inherited context; `workflow_attribution` counts the resulting `owner/context/missing` classification. Subagent counters include only `subagent_invoked=true`. Lane counters count `skill_lane[].lane`; feedback counters count list members and non-empty actions. Malformed and duplicate records never contribute to any functional metric.

The parser is deterministic. It requires one-line compact JSON with `sort_keys=true`, `separators=(',', ':')`, `ensure_ascii=true`, `allow_nan=false`, and no trailing newline inside the JSON value. Duplicate JSON keys reject the record. Duplicate `event_id` records are `duplicate_count += 1` and are ignored only when their canonical bytes are identical; conflicting bytes for the same `event_id` increment `malformed_count` with reason `conflicting_event_id` and contribute no event. Accepted records are ordered by parsed UTC timestamp ascending, then source line sequence; equal timestamps preserve source order. Timestamp must be RFC3339 UTC ending in `Z`; missing, non-UTC, invalid, or non-string timestamps are `malformed_by_reason[timestamp]`. JSON escaping is canonical and round-trippable; raw newline, carriage return, non-finite value, invalid UTF-8, or noncanonical serialization is malformed. Non-event Markdown lines are `ignored_count`, not malformed.

The parser aggregates malformed records without aborting the batch: `malformed_by_reason` uses stable reasons `json`, `duplicate_key`, `noncanonical_json`, `timestamp`, `schema`, `field_type`, `field_domain`, `conflicting_event_id`, and `line_encoding`. Dashboard and Eval readers may consume archived workflow reports as historical input; the active hook path writes only the per-event spool and never emits a monitor report.

### Inventory emitter and generated readback

`tools/runtime/archive/log_surface_inventory.py --root . --format json` emits the current inventory on demand. Its JSON retains `schema_version: 1`, sorted `scanned_files`, and records `{path,surface,emitter,field,line,certainty}`. There is no tracked inventory or regeneration gate. After migration:

- `.codex/hooks/skill_usage_logger.py` is absent from both `scanned_files` and `records`;
- `tools/runtime/dispatch/agent-canon/src/prompt_capture.rs`, `tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs`, `tools/runtime/dispatch/agent-canon/src/tool_selection.rs`, `tools/agent/orchestration/subagent_selection.py`, `tools/runtime/dispatch/agent-canon/src/workflow_context.rs`, `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs`, `tools/runtime/dispatch/agent-canon/src/skill_lane_detector.rs`, `tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs`, and `tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs` are present with their new static/dynamic fields or read-only consumer surfaces;
- `behavior_events.jsonl` is the checkpoint/readback corpus for `runtime-log-archive-git` (`<hook-name>-<agent-canon-commit>.jsonl` emitted; readback and verification consume `behavior_events.jsonl`); `skill_usage.jsonl` is classified as historical read-only evidence and is not an active emitter path;
- `behavior_event_json`, `agent-canon.behavior-event.v1`, `prompt_capture_status`, `prompt_excerpt_redacted`, `prompt_char_count`, `tool_name`, `tool_command_verb`, `selected_tools`, `feedback_labels`, `candidate_skill_reasons`, every `subagent_*` and `workflow_*` attribution field, and `skill_lane` are read back from the new emitter where statically discoverable;
- old hook child names are absent from executable inventory paths, while their names may occur only in the manifest/design metadata allowlist;
- The dashboard parser verifies the behavior-event schema and oracle.

## Import, CLI, and owner contract matrix

| target | import/CLI contract | caller migration |
| --- | --- | --- |
| `tools/runtime/dispatch/agent-canon/src/prompt_capture.rs` | import-only: `PromptCapture`, `capture_prompt`; no CLI | `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` direct import; no write |
| `tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs` | import-only: `PromptClassifierInputs`, `PromptIntakeSignals`, `prompt_intake_signals`; no hook CLI | evaluator and `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` direct import; no write |
| `tools/runtime/dispatch/agent-canon/src/tool_selection.rs` | import-only: `ToolSelection`, `select_tools`; no CLI | `hook_dispatcher.py` parts-preparation direct import; `behavior_event_assembly.rs` consumes precomputed typed value only |
| `tools/agent/orchestration/subagent_selection.py` | import-only: `SubagentSelection`, `select_subagents`; no CLI | `hook_dispatcher.py` parts-preparation direct import; `behavior_event_assembly.rs` consumes precomputed typed value only |
| `tools/runtime/dispatch/agent-canon/src/workflow_context.rs` | import-only: `WorkflowContext`, `load_workflow_context`, `store_workflow_context`; no hook CLI | `hook_dispatcher.py` parts-preparation direct load import; `behavior_event_assembly.rs` consumes precomputed typed value only; evaluator/context lifecycle owner for store |
| `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` | import-only: `HookInvocationParts`, `BehaviorEventRecord`, `record_hook_invocation`; no `append_behavior_event`, `parse_behavior_events` | dispatcher is the sole caller; sole pure owner for `should_log` / eligibility / `event_id` / record assembly; returns `BehaviorEventRecord | None`; no file I/O |
| `tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs` | native CLI: `agent-canon historical-skill-usage-read --path PATH` | read-only `skill_usage.jsonl` input; never imports the retired logger |
| `tools/runtime/dispatch/agent-canon/src/execution_resource_projection.rs` | import-only: `validate_normalized_input`, `validate_projection_bytes`, `projection_context_payload`; no guard CLI | dispatcher and pure projection tests direct import |
| `tools/runtime/dispatch/agent-canon/src/hook_safety.rs` | import-only pure API listed above; no standalone safety CLI | dispatcher direct import; old hook safety path deleted |
| `tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs` | native CLI and typed gate output | four old gate templates become direct owner commands |
| `tools/analysis/code/import_responsibility.py` | existing checker CLI/JSON | module-boundary owner |
| `tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs` | existing validation readback API; no B9 decision | consumes typed B9 state read-only |
| `tools/validation/ci/checks/run_python_quality_checks.sh` | existing shell quality route; no B9 decision | invokes validation consumers only |
| `.codex/hooks/hook_dispatcher.py` | direct import-only caller: `record_hook_invocation(parts)`; exactly once after each of the three finalized handler results; one `HookLogContext.append` for every active invocation | sole active-hook caller; returns the finalized handler output unchanged; an eligible behavior record is merged into that one event |
| `generate_agent_runtime_dashboard.py` | existing read-only dashboard CLI; `agent-canon.behavior-readback.v1` oracle and parser aggregation | reads canonical behavior events and owner-defined historical inputs; retains prompt/tool/feedback/subagent/workflow/lane metrics |
| `generate_agent_improvement_guide.py` | existing read-only guide CLI | consumes the native historical reader for archived `skill_usage.jsonl` and active dashboard evidence; no active emission |

## Exact implementation write set and fixture corpus

This is the exact future implementation write set `W`; this design wave does not touch these implementation paths.

**new files:**

`tools/runtime/dispatch/agent-canon/src/prompt_capture.rs`, `tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs`, `tools/runtime/dispatch/agent-canon/src/tool_selection.rs`, `tools/agent/orchestration/subagent_selection.py`, `tools/runtime/dispatch/agent-canon/src/workflow_context.rs`, `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs`, `tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs`, `tools/runtime/dispatch/agent-canon/src/execution_resource_projection.rs`, `tools/runtime/dispatch/agent-canon/src/hook_safety.rs`, `tools/runtime/dispatch/agent-canon/tests/prompt_capture_native.rs`, `tools/runtime/dispatch/agent-canon/tests/prompt_classifier_native.rs`, `tools/runtime/dispatch/agent-canon/tests/tool_selection_native.rs`, `tests/agent_tools/test_subagent_selection.py`, `tests/agent_tools/test_workflow_context.rs`, `tests/agent_tools/test_behavior_event_assembly.rs`, `tests/agent_tools/test_historical_skill_usage_reader.py`, `tools/runtime/dispatch/agent-canon/tests/execution_resource_projection_native.rs`, `tools/runtime/dispatch/agent-canon/tests/hook_safety_native.rs`, `tests/agent_tools/test_behavior_event_parser.py`, `tests/fixtures/behavior_events/accepted.jsonl`, `tests/fixtures/behavior_events/duplicate.jsonl`, `tests/fixtures/behavior_events/malformed.jsonl`, `tests/fixtures/behavior_events/out_of_order.jsonl`, `tests/fixtures/behavior_events/escaping.jsonl`, `tests/fixtures/behavior_events/oracle.json`, `tests/fixtures/behavior_events/hook_invocation_parts_user_prompt.json`, `tests/fixtures/behavior_events/hook_invocation_parts_pre_tool.json`, `tests/fixtures/behavior_events/hook_invocation_parts_post_tool.json`, `tests/fixtures/behavior_events/ineligible_blocked.json`, `tests/fixtures/behavior_events/record_hook_invocation_oracle.json`。

**modified/migrated files:**

`.codex/hooks/hook_dispatcher.py`, `.codex/hooks.json`, `.codex/README.md`, `README.md`, `agents/canonical/CODEX_SUBAGENTS.md`, `documents/conventions/coding-conventions-python.md`, `documents/design/codex-spark-implementation-routing.md`, `documents/design/responsibility-scope-management.md`, `documents/runtime/runtime-log-archive.md`, `documents/runtime/runtime-log-archive-migration.md`, `documents/tools/README.md`, `eval/definitions/issue_eval_manifest.toml`, `eval/definitions/workflow_selection_eval.toml`, `.codex/personal/skills/worktree-health/SKILL.md`, `tools/README.md`, `tools/experiments/execution/execution_resource_plan.py`, `tools/validation/notebooks/notebook_quality.py`, `tools/runtime/dispatch/agent-canon/src/workflow_selection_eval.rs`, `eval/producers/evaluate_skill_workflow_prompts.py`, `tools/validation/semantic/tools/tool_rejection_preflight.py`, `tools/analysis/code/import_responsibility.py`, `tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs`  , `tools/runtime/dispatch/agent-canon/src/skill_lane_detector.rs`, `tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs`, `tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs`, `.github/workflows/agent-improvement-guide.yml`, `tools/runtime/archive/log_surface_inventory.py`, `tools/runtime/dispatch/agent-canon/src/eval_archive_paths.rs`, `tools/runtime/dispatch/agent-canon/src/runtime_log_archive.rs`, `tools/runtime/dispatch/agent-canon/src/codex_runtime_summary.rs`, `tools/validation/semantic/runtime/check_agent_runtime_alignment.py`, `tools/runtime/dispatch/agent-canon/src/convention_compliance.rs`, `tools/validation/semantic/convention/convention_compliance_contracts.toml`, `tools/validation/ci/checks/run_python_quality_checks.sh`, `tools/catalog.yaml`, `responsibility-scope.toml`, `documents/experiments/gpu-admission-r5-source-packet.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/skills/worktree-health.md`, `AGENTS.md`, `ROOT_AGENTS.md`, `tests/agent_tools/test_codex_hooks.py`, `tests/agent_tools/test_hook_event_log.rs`, `tests/tools/test_execution_resource_plan.py`, `tests/agent_tools/test_evaluate_workflow_selection.py`, `tests/agent_tools/test_evaluate_skill_workflow_prompts.py`, `tests/agent_tools/test_tool_rejection_preflight.py`, `tests/agent_tools/test_import_responsibility.py` , `tests/agent_tools/test_check_agent_runtime_alignment.py`, `tests/agent_tools/test_check-convention-compliance`, `tests/agent_tools/test_generate_agent_runtime_dashboard.py`, `tests/agent_tools/test_generate_agent_improvement_guide.py` , `tests/agent_tools/test_log_surface_inventory.py`, `tests/agent_tools/test_responsibility_scope.py`, 。

**runtime artifact write set:**

`behavior_events` checkpoint lines (`<hook-name>-<agent-canon-commit>.jsonl`) are written only by `tools/runtime/dispatch/agent-canon/src/runtime_log_archive.rs`; per-invocation transport spooling is performed only by `tools/runtime/dispatch/agent-canon/src/hook_event_log.rs` into no-replace `<spool>/<namespace>/<hook_name>/<hook_run_id>.json` with `spooled|duplicate|failed` result. The dispatcher performs exactly one base append per active invocation and merges behavior fields into that same entry when a behavior record exists; no second append is allowed. Task progress projections are retired; archived monitoring files remain historical Eval inputs. `.codex/hooks/hook_dispatcher.py` and `tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs` write no files. `skill_usage.jsonl` has no active writer. A runtime append or monitor failure is telemetry-only and leaves the finalized handler output unchanged.

**deleted files, only after caller migration:**

`.codex/hooks/hook_safety.py`, `.codex/hooks/execution_resource_plan_projection_guard.py`, `.codex/hooks/skill_usage_logger.py`, `.codex/hooks/prompt_secret_guard.py`, `.codex/hooks/branch_worktree_guard.py`, `.codex/hooks/cause_investigation_guard.py`, `.codex/hooks/module_boundary_guard.py`, `.codex/hooks/library_implementation_guard.py`, `.codex/hooks/style_checker_guard.py`, `.codex/hooks/completion_review_guard.py`, `.codex/hooks/log_archive_mount_warning.py`, `.codex/hooks/reference_capture_guard.py`, `.codex/hooks/direct_rg_context_guard.py`, `.codex/hooks/task_authority_schema_guard.py`, `.codex/hooks/role_write_policy_guard.py`, `.codex/hooks/oop_readability_guard.py`, `.codex/hooks/first_party_library_guard.py`, `.codex/hooks/helper_inventory_guard.py`, `.codex/hooks/helper_first_guard.py`, `.codex/hooks/log_surface_inventory_guard.py`, `.codex/hooks/notebook_quality_guard.py`, `.codex/hooks/goal_completion_guard.py`, `.codex/hooks/codex_runtime_summary_logger.py`, `.codex/hooks/runtime_log_auto_sync.py`。


## Retirement order and reverse trace

1. Establish the pure owners, historical read-only parser, behavior assembly owner, and their pure-owner tests; update dispatcher import bootstrap to the non-hook owner. Keep current child files only as migration evidence.
2. Move the complete safety implementation to `tools/runtime/dispatch/agent-canon/src/hook_safety.rs`; pass pure safety tests; delete `.codex/hooks/hook_safety.py`; prove the old path is absent before B3/B4 retirement.
3. Migrate dashboard, skill lane, workflow monitor, inventory, evaluator, convention/readback, report, worktree, and GPU source-packet callers; generate the new inventory in memory and compare it before writing the generated file.
4. Retire the 14 direct files in this order: `log_archive_mount_warning.py`, `reference_capture_guard.py`, `direct_rg_context_guard.py`, `task_authority_schema_guard.py`, `role_write_policy_guard.py`, `oop_readability_guard.py`, `first_party_library_guard.py`, `helper_inventory_guard.py`, `helper_first_guard.py`, `log_surface_inventory_guard.py`, `notebook_quality_guard.py`, `goal_completion_guard.py`, `codex_runtime_summary_logger.py`, `runtime_log_auto_sync.py`.
5. Retire the 9 blocking files in dependency order: `execution_resource_plan_projection_guard.py`, `skill_usage_logger.py`, `prompt_secret_guard.py`, `branch_worktree_guard.py`, `cause_investigation_guard.py`, `module_boundary_guard.py`, `library_implementation_guard.py`, `style_checker_guard.py`, `completion_review_guard.py`.
6. Run dispatcher contract readback, dashboard/skill-lane readback, generated inventory readback, catalog, responsibility, convention, dependency, and pure-owner tests from one source snapshot; assert each active dispatcher handler calls `record_hook_invocation` exactly once after its finalized result and `Stop` calls it zero times.

Forward trace: hooks dispatch through the native `hook_dispatcher.rs`, which finalizes the selected handler and appends one event through `hook_event_log.rs`. `behavior_event_assembly.rs` supplies eligible behavior fields; the archive owner checkpoints immutable spool files.

Reverse trace: the native dispatcher and event-log tests check handler output, one append attempt, privacy and no-replace publication. Archive and Eval readers retain their own fixture checks. Retired task-monitor projections have no writer.

## Fail-open/fail-closed parity

| boundary | fail-open | fail-closed |
| --- | --- | --- |
| UserPromptSubmit | malformed/empty payload, spool failure | high-confidence secret |
| PreToolUse | malformed/empty payload, spool failure | unauthorized protected Git; normal creation requires creation authority, while force-create/ref overwrite requires creation and destructive authority |
| PostToolUse | malformed input, non-Bash, nonzero response, invalid projection, spool failure | no hook transport block; producer owns execution failure |
| Stop | inactive no-op | none |
| behavior-event dashboard | no event rows report `missing`; malformed JSON/field/timestamp rows aggregate as `malformed` without aborting valid rows | never convert missing/malformed into `present` |
| preflight/closeout | no implicit approval | unknown owner/gate, stale command, missing evidence, non-`APPROVE` review |

## Validation corpus

Exact fixture and test corpus:

- active contract: 3 registrations, inactive Stop, aliases, official schema, no subprocess/Git/network; each `UserPromptSubmit`/`PreToolUse`/`PostToolUse` handler calls `record_hook_invocation(parts)` exactly once after the finalized result, and `Stop` calls it zero times;
- safety: four secret classes, benign/malformed prompt, protected/read-only/authorized Git, operation-risk authority matrix (normal creation versus force-create/ref overwrite), shell wrapper/backtick/opaque cases, exact redaction and hash;
- projection: raw six-key normalization, exact nine-key projection, nested nullable admission/error, duplicate/extra/nonfinite/schema/path/byte/LF/unsuccessful matrices;
- skill replacement: frozen workflow manifest, immutable injected `repo_root`/catalog/routing-rules classifier inputs, all eight `PromptIntakeSignals` fields, prompt capture/tool/feedback/candidate-reason/subagent/workflow-attribution fields with current empty-string/list/bool/int domains, structural lane observed/candidate/unmatched, one-snapshot-per-invocation cardinality, exact event-id preimage, canonical behavior-event JSON parse, duplicate/order/timestamp/escaping/malformed aggregation, historical `skill_usage.jsonl` read-only parsing, and missing/malformed dashboard readback against `oracle.json`;
- dispatcher-to-assembly: three event-specific parts fixtures, finalized pass/block/projection/unsuccessful results, explicit cardinality oracle (`blocked_secret=1 append/0 projection`, `blocked_destructive_git=1 append/0 projection`, `malformed_payload=1 append/0 projection`, `eligible behavior=1 merged append/spooled=>1 projection`, `ineligible normal=1 append/0 projection`, `duplicate/failed=1 append attempt/0 projection`), eligible and `should_log` truth table, exactly-once post-result call assertions, merged-append policy with one transport write, and `record_hook_invocation_oracle.json`;
- conventions/readback: `check-convention-compliance`, `convention_compliance_contracts.toml`, `check_agent_runtime_alignment.py`, `run_python_quality_checks.sh`, `report_artifact_checks.rs`, [agents/skills/worktree-health.md](../../agents/skills/worktree-health.md), and [documents/experiments/gpu-admission-r5-source-packet.md](../experiments/gpu-admission-r5-source-packet.md) contain canonical owner paths only;
- transport/readback separation: no direct shared `behavior_events.jsonl` append path is asserted in hot-path; `HookLogContext.append` to no-replace per-event spool and `runtime-log-archive-git` checkpointing to `behavior_events` JSONL are tested separately in the same run;
- pure-owner tests: `prompt_capture_native.rs`, `prompt_classifier_native.rs`, `tool_selection_native.rs`, `test_subagent_selection.py`, `test_workflow_context.rs`, `test_behavior_event_assembly.rs`, `test_historical_skill_usage_reader.py`, `hook_safety_native.rs`, `execution_resource_projection_native.rs`, and prove import side-effect absence, immutable-input/no-subprocess behavior, domain/nullability, parity, event identity/cardinality, historical parser separation; `test_codex_hooks.py` proves the dispatcher caller contract and ordering.

Current validation uses the existing runtime-alignment and convention checkers,
targeted Markdown checks, and the focused event and safety tests. Completed
migration baselines, fixed retired-file counts, and retirement audits are not
ongoing validation requirements.

No code implementation, compatibility wrapper, parent pin update, root-view sync, branch publication, or commit is authorized by this design wave.

## Historical migration evidence

| id | observation | source/readback | target proof |
| --- | --- | --- | --- |
| E1 | current registration has UserPromptSubmit, PreToolUse, PostToolUse; Stop is inactive | `.codex/hooks.json`, dispatcher contract | active contract test and readback |
| E2 | current dispatcher duplicates 23 child names into `FORMER_ACTIVE_HOOK_CHILDREN` and `RETIRED_HOOK_ROUTES` while moved `hook_safety.py` is a separate source absence | dispatcher lines 94–163 and safety import readback | current-event contract and dispatcher tests |
| E3 | current hook safety owner is `.codex/hooks/hook_safety.py` and dispatcher imports it | dispatcher/safety readback | new owner import and old path absence |
| E4 | evaluator dynamically imports old skill logger | evaluator `load_skill_usage_logger` | direct classifier import test |
| E5 | dashboard and generated inventory read old logger fields/path | dashboard grep/readback | new workflow-monitor lane schema and inventory diff |
| E6 | projection limit is 64 KiB and hook stdin limit is 256 KiB | current dispatcher/projection constants | byte-limit corpus |
| E7 | spool is bounded fingerprint/status telemetry with no explicit event-byte limit and no-replace identity | hook event log readback | field/domain/nullability parity test |
| E8 | requested convention, quality, report, worktree, GPU, catalog, responsibility, test, and fixture paths are caller/readback surfaces | exact path set above | current source diff and references |
| E9 | current skill logger emits prompt capture, tool selection, feedback, candidate reasons, subagent, and workflow-context fields consumed by dashboard readers | `skill_usage_logger.py` dataclasses/emitter and dashboard accumulators | canonical behavior-event schema and fixed dashboard oracle |
| E11 | active dispatcher handlers have one finalized result before telemetry append can occur | dispatcher event handlers and behavior assembly caller contract | exactly-once `record_hook_invocation` call, one base append per active invocation, merged-write policy, and fail-open caller tests |
