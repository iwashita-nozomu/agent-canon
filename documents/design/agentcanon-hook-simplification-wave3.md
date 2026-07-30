<!--
@dependency-start
contract design
responsibility Defines the implementation-ready AgentCanon Wave 3 hook simplification target after the completed caller audit and reviewer-finding correction.
upstream design ../../.codex/README.md owns the project-scoped hook design and reader route.
upstream implementation ../../.codex/hooks/hook_dispatcher.py owns the active lifecycle dispatch contract.
upstream implementation ../../.codex/hooks/hook_event_log.py owns append-only hook telemetry transport.
upstream design ../runtime/log-surface-inventory.json owns generated telemetry field inventory.
upstream design ../../tools/catalog.yaml owns canonical tool registration.
upstream design ../../responsibility-scope.toml owns top-level responsibility coverage.
downstream implementation ../../.codex/hooks/hook_dispatcher.py implements the selected active contract.
downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates active event and retired-name readback.
@dependency-end
-->

# AgentCanon Hook Simplification Wave 3 Design

この文書は、2026-07-30 時点の親 `main` が pin する AgentCanon `0e3fe239` を基準に、完了済み hook caller audit と reviewer findings を反映した実装用 target state を固定する。これは設計文書だけの変更であり、production code、test code、catalog、inventory の実装変更、削除、commit はこの wave に含めない。

## Authority と設計境界

- canonical design owner: `.codex/README.md` の Hook Context と `.codex/hooks/hook_dispatcher.py` の lifecycle contract
- canonical non-hook owners: `tools/agent_tools/` の typed tool/checker modules、`tools/agent_tools/workflow_monitor.py` の behavior-event emitter
- decision: 3 active dispatcher events、inactive `Stop`、permanent tombstones、retired executable file なし
- no compatibility surface: 旧 executable、re-export、wrapper、shim、fallback CLI は作らない
- source checkout: fresh design clone from current `main`; implementation wave は同じ source snapshot を再読込して開始する

## Reviewer-corrected caller and readback audit

### 再現可能な監査コマンド

実装前に次の `git grep` と readback を同じ AgentCanon source root で実行し、出力を source packet に保存する。検索は `rg` を使わず、Git 管理対象と明示した runtime surface を対象にする。

```bash
git grep -l -E 'hook_dispatcher|hook_safety|execution_resource_plan_projection_guard|prompt_secret_guard|branch_worktree_guard|skill_usage_logger|hook_event_log|RETIRED_HOOK_ROUTES|retired_hook_routes|skill_lane|generate_agent_runtime_dashboard|check_convention_compliance|convention_compliance_contracts|run_python_quality_checks|report_artifact_checks|worktree-health|gpu-admission-r5-source-packet' -- . | sort -u
git grep -n -E 'hook_dispatcher|hook_safety|execution_resource_plan_projection_guard|prompt_secret_guard|branch_worktree_guard|skill_usage_logger|hook_event_log|RETIRED_HOOK_ROUTES|retired_hook_routes' -- .codex tools agents documents tests templates responsibility-scope.toml
git grep -n -E 'check_convention_compliance|convention_compliance_contracts|generate_agent_runtime_dashboard|skill_lane_detector|run_python_quality_checks|report_artifact_checks|worktree-health|gpu-admission-r5-source-packet' -- .codex tools agents documents tests templates responsibility-scope.toml
python3 .codex/hooks/hook_dispatcher.py --contract
python3 tools/agent_tools/log_surface_inventory.py --root . --check --baseline documents/runtime/log-surface-inventory.json
git rev-parse main
git show main:documents/runtime/log-surface-inventory.json
python3 tools/agent_tools/check_agent_runtime_alignment.py
```

`git read-tree` は checkout を作り直すための操作ではなく、実装 clone の index/readback が source snapshot と一致することを確認する読み取り前提の手順である。共有 checkout では実行せず、fresh implementation clone でだけ実行する。

### exact caller/readback path set

次の集合を `CALLER_READBACK_PATHS` として source packet に固定する。これは incidental な履歴 report ではなく、実行登録、import、CLI、checker、dashboard、skill lane、inventory、docs、catalog、responsibility、test の直接 caller/readback surface である。requested reviewer paths を含め、実装時にこの集合から漏れを出さない。

Caller audit also has a typed artifact/read-only-consumer sidecar. It is part of the same `--contract` readback, but it does not expand the manifest's 24-basename generation rule:

```text
CALLER_AUDIT_ARTIFACTS = (
  "skill_usage.jsonl",          # historical read-only input
  "behavior_events.jsonl",      # active target input
  "workflow_monitoring.md",     # monitor projection
)
CALLER_AUDIT_CONSUMERS = (
  "tools/agent_tools/historical_skill_usage_reader.py",
  "tools/agent_tools/generate_agent_improvement_guide.py",
  "tools/agent_tools/workflow_monitor.py",
  "tools/agent_tools/generate_agent_runtime_dashboard.py",
  "tools/agent_tools/skill_lane_detector.py",
  "tools/agent_tools/log_surface_inventory.py",
)
```

The artifact sidecar records each artifact's `mode` (`historical_read_only`, `active_canonical`, or `projection`), producer owner, parser owner, and all read-only consumers. `skill_usage.jsonl` must have no active producer after migration; its only permitted edges are to `historical_skill_usage_reader.py` and the improvement-guide/dashboard historical readback. A sidecar mismatch is a caller-audit failure, not a compatibility route.

**dispatcher、hook、registration**

`.codex/hooks.json`, `.codex/config.toml`, `.codex/README.md`, `.codex/hooks/hook_dispatcher.py`, `.codex/hooks/hook_event_log.py`, `.codex/hooks/hook_safety.py`, `.codex/hooks/execution_resource_plan_projection_guard.py`, `.codex/hooks/prompt_secret_guard.py`, `.codex/hooks/branch_worktree_guard.py`, `.codex/hooks/skill_usage_logger.py`, `.codex/hooks/cause_investigation_guard.py`, `.codex/hooks/module_boundary_guard.py`, `.codex/hooks/library_implementation_guard.py`, `.codex/hooks/style_checker_guard.py`, `.codex/hooks/completion_review_guard.py`, `.codex/hooks/log_archive_mount_warning.py`, `.codex/hooks/reference_capture_guard.py`, `.codex/hooks/direct_rg_context_guard.py`, `.codex/hooks/task_authority_schema_guard.py`, `.codex/hooks/role_write_policy_guard.py`, `.codex/hooks/oop_readability_guard.py`, `.codex/hooks/first_party_library_guard.py`, `.codex/hooks/helper_inventory_guard.py`, `.codex/hooks/helper_first_guard.py`, `.codex/hooks/log_surface_inventory_guard.py`, `.codex/hooks/notebook_quality_guard.py`, `.codex/hooks/goal_completion_guard.py`, `.codex/hooks/codex_runtime_summary_logger.py`, `.codex/hooks/runtime_log_auto_sync.py`。

**canonical callers and reviewers**

`tools/agent_tools/evaluate_workflow_selection.py`, `tools/agent_tools/evaluate_skill_workflow_prompts.py`, `tools/agent_tools/prompt_capture.py`（new）、`tools/agent_tools/prompt_classifier.py`（new）、`tools/agent_tools/tool_selection.py`（new）、`tools/agent_tools/subagent_selection.py`（new）、`tools/agent_tools/workflow_context.py`（new）、`tools/agent_tools/behavior_event_assembly.py`（new）、`tools/agent_tools/historical_skill_usage_reader.py`（new）、`tools/agent_tools/execution_resource_projection.py`（new）、`tools/agent_tools/hook_safety.py`（new）、`tools/agent_tools/hook_retirement.py`（new）、`tools/agent_tools/check_hook_retirement.py`（new）、`tools/agent_tools/tool_rejection_preflight.py`, `tools/agent_tools/import_responsibility.py`, `tools/agent_tools/task_authority.py`, `tools/agent_tools/review_dispatch.py`, `tools/agent_tools/report_artifact_checks.py`, `tools/agent_tools/task_close.py`, `tools/agent_tools/workflow_monitor.py`, `tools/agent_tools/skill_lane_detector.py`, `tools/agent_tools/generate_agent_runtime_dashboard.py`, `tools/agent_tools/generate_agent_improvement_guide.py`, `tools/agent_tools/log_surface_inventory.py`, `tools/agent_tools/runtime_log_paths.py`, `tools/agent_tools/runtime_log_archive_git.py`, `tools/agent_tools/export_codex_runtime_summary.py`, `tools/agent_tools/check_agent_runtime_alignment.py`, `tools/agent_tools/check_convention_compliance.py`, `tools/agent_tools/convention_compliance_contracts.toml`, `tools/ci/run_python_quality_checks.sh`, `.github/workflows/agent-improvement-guide.yml`, `tools/catalog.yaml`, `responsibility-scope.toml`, `documents/runtime/log-surface-inventory.json`, `documents/runtime/runtime-log-archive.md`, `documents/runtime/runtime-log-archive-migration.md`, `documents/experiments/gpu-admission-r5-source-packet.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/skills/worktree-health.md`, `AGENTS.md`, `ROOT_AGENTS.md`, `README.md`。

**tests、fixtures、generated readback**

`tests/agent_tools/test_codex_hooks.py`, `tests/agent_tools/test_hook_event_log.py`, `tests/tools/test_execution_resource_plan.py`, `tests/agent_tools/test_evaluate_workflow_selection.py`, `tests/agent_tools/test_evaluate_skill_workflow_prompts.py`, `tests/agent_tools/test_tool_rejection_preflight.py`, `tests/agent_tools/test_import_responsibility.py`, `tests/agent_tools/test_review_dispatch.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_check_agent_runtime_alignment.py`, `tests/agent_tools/test_check_convention_compliance.py`, `tests/agent_tools/test_generate_agent_runtime_dashboard.py`, `tests/agent_tools/test_generate_agent_improvement_guide.py`, `tests/agent_tools/test_workflow_monitor.py`, `tests/agent_tools/test_log_surface_inventory.py`, `tests/agent_tools/test_hook_retirement.py`（new）、`tests/agent_tools/test_execution_resource_projection.py`（new）、`tests/agent_tools/test_prompt_capture.py`（new）、`tests/agent_tools/test_prompt_classifier.py`（new）、`tests/agent_tools/test_tool_selection.py`（new）、`tests/agent_tools/test_subagent_selection.py`（new）、`tests/agent_tools/test_workflow_context.py`（new）、`tests/agent_tools/test_behavior_event_assembly.py`（new）、`tests/agent_tools/test_historical_skill_usage_reader.py`（new）、`tests/agent_tools/test_hook_safety.py`（new）、`tests/fixtures/hook_retirement/`（new corpus）、`tests/fixtures/behavior_events/`（new corpus）、`tests/fixtures/skill_usage_history/`（new corpus）。

Audit conclusions:

1. current dispatcher has 23 former child names in `FORMER_ACTIVE_HOOK_CHILDREN` and a duplicated `RETIRED_HOOK_ROUTES` table;
2. current `tools/agent_tools/evaluate_workflow_selection.py` dynamically loads `.codex/hooks/skill_usage_logger.py`;
3. current dashboard next-action/readback text and `documents/runtime/log-surface-inventory.json` contain `.codex/hooks/skill_usage_logger.py` records;
4. current `.codex/hooks/hook_dispatcher.py` imports `.codex/hooks/hook_safety.py`, so moving that file requires a direct dispatcher import change and an absent old path proof;
5. convention, quality, report, worktree-health, GPU admission, catalog, responsibility, and generated-inventory surfaces are callers/readbacks, even when they do not invoke the hook process directly.

For completeness, the baseline legacy-name `git grep -l` readback also returned these non-runtime or historical surfaces: `.agents/skills/worktree-health/SKILL.md`, `README.md`, `agents/canonical/CODEX_SUBAGENTS.md`, `documents/conventions/coding-conventions-python.md`, `documents/design/codex-spark-implementation-routing.md`, `documents/design/responsibility-scope-management.md`, `documents/runtime/runtime-log-archive.md`, `documents/tools/README.md`, `evidence/agent-evals/issue_eval_manifest.toml`, `evidence/agent-evals/workflow_selection_eval.toml`, `issues/closed/AC-20260513-hook-result-accumulation.md`, `issues/closed/AC-20260514-oop-hook-side-effect-and-skill-split.md`, `issues/closed/AC-20260514-skill-usage-noop-hook-churn.md`, `issues/closed/AC-20260517-responsibility-scope-management.md`, `issues/closed/AC-20260519-oop-hook-warning-mode.md`, `issues/open/AC-20260517-eval-accumulation-gaps.md`, `rust/agent-canon/src/rust_migration_plan.rs`, `tests/agent_tools/test_responsibility_scope.py`, `tests/agent_tools/test_task_authority.py`, `tools/README.md`, `tools/experiments/execution_resource_plan.py`, and `tools/validation/notebook_quality.py`. The implementation packet reads all of these; closed issues and historical evidence remain read-only and are not rewritten as compatibility references.

## Responsibility partition: 9 blocking groups and 14 direct retirements

| group | current child/caller | reusable responsibility | one target owner |
| --- | --- | --- | --- |
| B1 | `execution_resource_plan_projection_guard.py` → dispatcher and projection tests | exact normalized input and projection byte validation | new `tools/agent_tools/execution_resource_projection.py`; producer authority remains `tools/experiments/execution_resource_plan.py` |
| B2 | `skill_usage_logger.py` → evaluator and prompt-eval tests | pure prompt-to-workflow/skill classification | new `tools/agent_tools/prompt_classifier.py`; evaluator imports it directly |
| B3 | `prompt_secret_guard.py` → prompt safety and dispatcher | secret classification and redacted block payload | `tools/agent_tools/hook_safety.py` |
| B4 | `branch_worktree_guard.py` and workflow docs → dispatcher | destructive Git intent, same-segment authority, redacted payload | the same `tools/agent_tools/hook_safety.py`; policy wording remains `agents/canonical/CODEX_WORKFLOW.md` |
| B5 | `cause_investigation_guard.py` → preflight gate | cause evidence preflight | existing `tools/agent_tools/tool_rejection_preflight.py` |
| B6 | `module_boundary_guard.py` → preflight gate | import boundary finding | existing `tools/agent_tools/import_responsibility.py` |
| B7 | `library_implementation_guard.py`, `first_party_library_guard.py` | dependency/public-surface authority | final decision owner: `tools/agent_tools/task_authority.py`; `responsibility_scope.py` and `$dependency-module-change` are read-only consumers/callers |
| B8 | `style_checker_guard.py` and quality script | Markdown/style validation | `tools/bin/agent-canon docs check` and `$md-style-check` |
| B9 | `completion_review_guard.py` → review/report/quality callers | review/completion acceptance | final decision owner: `tools/agent_tools/review_dispatch.py`; `report_artifact_checks.py`, `task_close.py`, and `run_python_quality_checks.sh` are read-only consumers/callers |

The 14 direct-retirement positions are: `log_archive_mount_warning.py`, `reference_capture_guard.py`, `direct_rg_context_guard.py`, `task_authority_schema_guard.py`, `role_write_policy_guard.py`, `oop_readability_guard.py`, `first_party_library_guard.py`, `helper_inventory_guard.py`, `helper_first_guard.py`, `log_surface_inventory_guard.py`, `notebook_quality_guard.py`, `goal_completion_guard.py`, `codex_runtime_summary_logger.py`, `runtime_log_auto_sync.py`. The 9 blocking positions are `execution_resource_plan_projection_guard.py`, `skill_usage_logger.py`, `prompt_secret_guard.py`, `branch_worktree_guard.py`, `cause_investigation_guard.py`, `module_boundary_guard.py`, `library_implementation_guard.py`, `style_checker_guard.py`, and `completion_review_guard.py`. `first_party_library_guard.py` is the shared B7/direct cleanup position and is stored once, so the typed child manifest remains 23 unique rows while the retirement ledger remains 14+9 positions.

### Single decision-owner routes for B7 and B9

| group | final decision owner | read-only consumers/callers | one execution route |
| --- | --- | --- | --- |
| B7 | `tools/agent_tools/task_authority.py:first_party_library_authorized` | `responsibility_scope.py` projects scope evidence; `$dependency-module-change` supplies dependency-source context; `tool_rejection_preflight.py` reports the finding | `import-only:tools.agent_tools.task_authority:first_party_library_authorized` |
| B9 | `tools/agent_tools/review_dispatch.py:resolve_current_review_state` | `report_artifact_checks.py` consumes the typed review state; `task_close.py` consumes readiness; `tools/ci/run_python_quality_checks.sh` invokes the existing validation set | `import-only:tools.agent_tools.review_dispatch:resolve_current_review_state` |

The read-only consumers may not emit an independent B7/B9 decision, approval, or alternate execution route. Their fields are projections of the decision owner result: B7 exposes authority `allowed/reason`; B9 exposes the current candidate, decision, dispatch blocker, and `publication_unlocked`. A missing or malformed owner result is a blocking finding, not a consumer-local fallback.

## Positive target state

### Three active dispatcher events and inactive Stop

`.codex/hooks.json` registers only these three event groups, each invoking `.codex/hooks/hook_dispatcher.py` once. `Stop` is a contract row with `active=false`, is not registered, reads no stdin, emits no output and no telemetry, and remains an inactive no-op forever.

| event | matcher | active owner call | post-result caller action | success output | failure semantics |
| --- | --- | --- | --- | --- | --- |
| `UserPromptSubmit` | none | `hook_safety.secret_kind` then `secret_block_payload` | after the safety result is final, call `behavior_event_assembly.record_hook_invocation(parts)` exactly once | no output on pass; official redacted block on match | secret match block; malformed input and spool failure fail-open |
| `PreToolUse` | `Bash\|apply_patch\|python\|python3` | `hook_safety.first_block` then `branch_block_payload` | after the safety result is final, call `behavior_event_assembly.record_hook_invocation(parts)` exactly once | no output on pass; operation/hash-only block | unauthorized destructive Git block; malformed input and spool failure fail-open |
| `PostToolUse` | current ten-tool matcher set | normalize six fields, then `execution_resource_projection.validate_projection_bytes` | after the projection result is final, call `behavior_event_assembly.record_hook_invocation(parts)` exactly once | validated successful Bash projection as official `additionalContext` | malformed input, non-Bash, unsuccessful response, invalid projection, spool failure fail-open |

The active handler set is exactly `UserPromptSubmit.secret_safety`, `PreToolUse.destructive_git_safety`, `PostToolUse.execution_resource_projection`. The dispatcher is the sole caller of `record_hook_invocation`; `behavior_event_assembly.py` is the sole writer and orchestration owner for behavior-event persistence. The dispatcher imports the owner directly and calls it after, never before, the existing handler result is finalized. The call is exactly once per active handler invocation, including a finalized block/fail-open result; `Stop` is inactive and calls it zero times. The official output schema remains `agent-canon.posttooluse-stop.v1`; contract readback schema remains `agent-canon.hook-contract.v1` with `active_events` length 3 and `inactive_events=["Stop"]`.

### Dispatcher caller contract for `record_hook_invocation`

The dispatcher imports `record_hook_invocation` directly from `tools/agent_tools/behavior_event_assembly.py` using the same source-root import bootstrap as the other non-hook owners. It does not dynamically load the retired logger, call a CLI, write JSONL, or invoke `workflow_monitor.py` itself. Each active handler constructs one immutable `HookInvocationParts` value only after its existing handler result is final:

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

`handler_result` includes the finalized dispatcher status, output/block decision, and safe result fields; it never contains raw prompt, command, secret, stdout, or stderr material. `classifier_rules` is the already-frozen input described in the pure classifier contract. `tool_selection`, `subagent_selection`, and `workflow_context` are typed values or explicit empty values; the dispatcher does not recompute any of them. The caller contract is therefore one import, one parts value, one call, and no caller-side artifact write.

The owner boundaries for admission are fixed:

| decision | owner | true condition | false result |
| --- | --- | --- | --- |
| `eligible_hook_invocation(parts)` | `behavior_event_assembly.py` | active event name; finalized handler result; `payload_status="parsed"`; status is not `malformed_payload`, `blocked_secret`, `blocked_destructive_git`, or `invalid_projection`; and at least one safe behavior signal exists | `skipped`, with no JSONL write and no monitor projection |
| `should_log(classifier_inputs)` | `prompt_classifier.py` | current pure classifier rule: prompt classification has a selected/candidate/feedback signal according to the injected immutable catalog and routing rules | `False`; no classifier-owned side effect |
| final snapshot admission | `behavior_event_assembly.py` | `eligible_hook_invocation(parts)` and (`should_log(...)` or a nonempty tool-selection, subagent-selection, or workflow-context signal) | `skipped`; dispatcher handler result is unchanged |

`Stop` never constructs parts. A finalized safety block is still passed once to the assembly caller, but is ineligible and cannot cause prompt/command material to be captured. A valid `PostToolUse` with an unsuccessful producer response may remain eligible for safe tool-selection evidence; an invalid projection is ineligible. The assembly owner, not the dispatcher, owns all three decisions and is the only place that may turn them into a behavior snapshot.

The call and write order is strict:

1. `hook_dispatcher.py` completes the existing event-specific safety or projection handler and stores its `FinalHandlerResult`.
2. The dispatcher calls `record_hook_invocation(parts)` exactly once.
3. `behavior_event_assembly.py` validates parts, invokes the pure classifier/selection/context owners, applies eligibility and `should_log`, assembles the one canonical snapshot, derives `event_id`, and writes `behavior_events.jsonl` through the canonical append transport.
4. Only after a new JSONL record is successfully written does the assembly owner call `workflow_monitor.emit_behavior_projection(...)` with the same snapshot. A duplicate append does not emit a second monitor projection; a failed append never invokes the monitor.
5. The dispatcher returns the already-finalized handler output. It ignores assembly status for safety/output purposes; assembly status is telemetry-only.

`record_hook_invocation` is fail-open at the telemetry boundary: `skipped`, `duplicate`, JSONL append failure, monitor failure, malformed classifier inputs, and context load failure cannot change the finalized hook decision or create a new block. A successful JSONL write remains durable even if monitor projection fails. The assembly API returns a typed `RecordHookInvocationResult` and does not raise into the dispatcher. Exactly one eligible invocation produces exactly one `behavior-event.v1` snapshot; retries are deduplicated by the previously fixed `event_id` rule.

### Transport hook name, semantic event kind, cardinality, and identity

`hook_event_name` is transport metadata and is never used as the semantic event kind. It is exactly one of `UserPromptSubmit`, `PreToolUse`, or `PostToolUse` on an active invocation. `event_kind` is the behavior meaning and is independent of the transport name: `behavior_snapshot`, `prompt_intake`, `tool_selection`, `subagent_selection`, `workflow_attribution`, or `skill_lane`. The canonical replacement record uses `event_kind="behavior_snapshot"` and carries the other semantic dimensions as fields; the dimension names are not aliases for `hook_event_name`. The old ambiguous `event` field is removed from the target behavior schema and has no compatibility alias.

Cardinality is fixed at both layers:

| source | cardinality for one invocation | canonical identity |
| --- | --- | --- |
| active dispatcher spool | exactly one `hook_event_log` record for each active hook invocation; `Stop` produces zero | `hook_invocation_id`/current `hook_run_id` plus `hook_event_name` |
| behavior-event artifact | zero when the invocation has no behavior signal; otherwise exactly one `behavior-event.v1` snapshot with `event_kind="behavior_snapshot"` | one `event_id` for the snapshot; no per-field or per-dimension duplicate rows |
| monitor projection | zero or more human-readable monitoring lines derived from the one snapshot; these are projections, not canonical event records | projection lines never create a new `event_id` |

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

### One `hook_safety` owner, direct import, old path deleted

The single safety owner is `tools/agent_tools/hook_safety.py`. It receives all pure reusable safety logic from the current `.codex/hooks/hook_safety.py`: `SECRET_PATTERNS`, `SHELL_TOOL_NAMES`, payload extractors, `secret_kind`, `secret_block_payload`, `GitCommand`, `GitIntent`, shell/backtick parsing, protected update/branch/worktree/Git intent classification, authority predicates, `first_block`, `command_sha256`, and `branch_block_payload`. No second `prompt_safety.py`, `destructive_git_safety.py`, or hook-local safety owner exists.

The implementation dispatcher import contract is exact: resolve `Path(__file__).resolve().parents[2]` as source root, prepend `<source-root>/tools/agent_tools` once to `sys.path` if absent, then use this direct-import list exactly once:

```text
tools.agent_tools.hook_safety
tools.agent_tools.execution_resource_projection
tools.agent_tools.hook_event_log
tools.agent_tools.hook_retirement
tools.agent_tools.behavior_event_assembly:record_hook_invocation
```

After the source-root path insertion, the last entry is the ordinary direct Python import `from behavior_event_assembly import record_hook_invocation`; its canonical module identity is `tools.agent_tools.behavior_event_assembly` and its only imported symbol is `record_hook_invocation`. No `importlib`, dynamic path loading, CLI subprocess, or second assembly import is permitted. The dispatcher must not inspect cwd or Git, spawn a process, or access a network. It calls the new owner directly; `.codex/hooks/hook_safety.py` is deleted after the new owner and pure-owner tests pass. The old file is not a wrapper and is not importable in target state.

## Canonical tombstone manifest and guard

`tools/agent_tools/hook_retirement.py` is the one source of retirement metadata. It is a pure import-only data module; dispatcher and guard import it, and neither reproduces the list.

```text
TOMBSTONE_SCHEMA = "agent-canon.hook-retirement-tombstones.v2"
RetiredChildTombstone = frozen dataclass {
  filename: str,
  owner: str,
  command_or_skill: str,
  profile_trigger: str,
  decision_semantics: str,
  artifact: str,
}
MovedSourceAbsence = frozen dataclass {
  filename: str,
  moved_to: str,
  import_contract: str,
  reason: str,
  artifact: str,
}
RETIRED_CHILD_TOMBSTONES: tuple[RetiredChildTombstone, ...]  # exactly 23
MOVED_SOURCE_ABSENCES: tuple[MovedSourceAbsence, ...]       # exactly 1
```

The two tuples are type-separated. `RETIRED_CHILD_TOMBSTONES` contains exactly the 23 former child names (14 direct plus 9 blocking). `MOVED_SOURCE_ABSENCES` contains exactly `.codex/hooks/hook_safety.py`, whose implementation moves to `tools/agent_tools/hook_safety.py`; it is an absent source path, not a retired child responsibility. The union has exactly 24 basenames. The 14+9 retirement ledger remains the child retirement order; the safety leaf relocation is a prerequisite move.

`command_or_skill` has one fixed metadata grammar and no old executable path:

- pure owner: `import-only:tools.agent_tools.<module>:<symbol>`;
- canonical command: `command-only:python3 tools/agent_tools/<owner>.py <subcommand>`;
- canonical skill: `skill-only:$<skill-id>`;
- canonical docs command: `docs-only:tools/bin/agent-canon docs check`.

The field is non-null, non-empty, one line, and must not contain `.codex/hooks/`, a retired filename, `compat`, `wrapper`, `shim`, or `fallback`. These are import/command/skill representations for tombstone readback only; `check_hook_retirement.py` never executes the value. `owner` is the responsibility owner, not a deleted filename.

The canonical tuple rows are fixed as follows; no row may be inferred from a nearby file:

| filename | owner | command_or_skill |
| --- | --- | --- |
| `log_archive_mount_warning.py` | `tools/agent_tools/runtime_log_archive_git.py` | `command-only:python3 tools/agent_tools/runtime_log_archive_git.py ensure` |
| `reference_capture_guard.py` | `tools/agent_tools/reference_materializer.py` | `command-only:python3 tools/agent_tools/reference_materializer.py` |
| `direct_rg_context_guard.py` | `$task-routing` | `skill-only:$task-routing` |
| `task_authority_schema_guard.py` | `tools/agent_tools/task_authority.py` | `command-only:python3 tools/agent_tools/task_authority.py` |
| `role_write_policy_guard.py` | `tools/agent_tools/agent_team.py` | `command-only:python3 tools/agent_tools/agent_team.py` |
| `oop_readability_guard.py` | `$oop-readability-check` | `skill-only:$oop-readability-check` |
| `first_party_library_guard.py` | `tools/agent_tools/task_authority.py` | `import-only:tools.agent_tools.task_authority:first_party_library_authorized` |
| `helper_inventory_guard.py` | `tools/agent_tools/helper_function_inventory.py` | `command-only:python3 tools/agent_tools/helper_function_inventory.py` |
| `helper_first_guard.py` | `tools/agent_tools/responsibility_scope.py` | `command-only:python3 tools/agent_tools/responsibility_scope.py --root .` |
| `log_surface_inventory_guard.py` | `tools/agent_tools/log_surface_inventory.py` | `command-only:python3 tools/agent_tools/log_surface_inventory.py --root . --check` |
| `notebook_quality_guard.py` | `tools/validation/notebook_quality.py` | `command-only:python3 tools/validation/notebook_quality.py` |
| `goal_completion_guard.py` | `$codex-goals-workflow` | `skill-only:$codex-goals-workflow` |
| `codex_runtime_summary_logger.py` | `tools/agent_tools/export_codex_runtime_summary.py` | `command-only:python3 tools/agent_tools/export_codex_runtime_summary.py` |
| `runtime_log_auto_sync.py` | `tools/agent_tools/runtime_log_archive_git.py` | `command-only:python3 tools/agent_tools/runtime_log_archive_git.py sync` |
| `execution_resource_plan_projection_guard.py` | `tools/agent_tools/execution_resource_projection.py` | `import-only:tools.agent_tools.execution_resource_projection:validate_projection_bytes` |
| `skill_usage_logger.py` | `tools/agent_tools/behavior_event_assembly.py` | `import-only:tools.agent_tools.behavior_event_assembly:assemble_behavior_event` |
| `prompt_secret_guard.py` | `tools/agent_tools/hook_safety.py` | `import-only:tools.agent_tools.hook_safety:secret_block_payload` |
| `branch_worktree_guard.py` | `tools/agent_tools/hook_safety.py` | `import-only:tools.agent_tools.hook_safety:first_block` |
| `cause_investigation_guard.py` | `tools/agent_tools/tool_rejection_preflight.py` | `command-only:python3 tools/agent_tools/tool_rejection_preflight.py --gate cause_investigation` |
| `module_boundary_guard.py` | `tools/agent_tools/import_responsibility.py` | `command-only:python3 tools/agent_tools/import_responsibility.py` |
| `library_implementation_guard.py` | `tools/agent_tools/task_authority.py` | `import-only:tools.agent_tools.task_authority:first_party_library_authorized` |
| `style_checker_guard.py` | `$md-style-check` | `docs-only:tools/bin/agent-canon docs check` |
| `completion_review_guard.py` | `tools/agent_tools/review_dispatch.py` | `import-only:tools.agent_tools.review_dispatch:resolve_current_review_state` |

The moved-source table is separate and has no `command_or_skill` field:

| filename | moved_to | import_contract | reason | artifact |
| --- | --- | --- | --- | --- |
| `hook_safety.py` | `tools/agent_tools/hook_safety.py` | `import-only:tools.agent_tools.hook_safety:secret_kind` | pure safety implementation moves out of `.codex/hooks/`; old path must be absent and unimportable | moved-source absence proof |

Manifest storage order and digest projection order are deliberately different. `RETIRED_CHILD_TOMBSTONES` is stored in the semantic retirement order: the 14 direct-retirement rows first, followed by the 9 blocking rows in the dependency order in the retirement ledger. `MOVED_SOURCE_ABSENCES` is stored in move-prerequisite order. This order is the human/readback order and must not be rewritten by a serializer. It is not the digest order.

`source_digest` is reproducible from the manifest and not from the checkout. Before hashing, the implementation creates a digest-only projection: child rows are copied and lexicographically sorted by `(filename, owner, command_or_skill, profile_trigger, decision_semantics, artifact)`; moved rows are copied and lexicographically sorted by `(filename, moved_to, import_contract, reason, artifact)`. The projection has no derived counts or readback paths. The exact preimage is:

```text
preimage = {
  "schema": TOMBSTONE_SCHEMA,
  "retired_child_tombstones": [
    asdict(row) for row in sorted(
      RETIRED_CHILD_TOMBSTONES,
      key=lambda row: (row.filename, row.owner, row.command_or_skill,
                       row.profile_trigger, row.decision_semantics, row.artifact),
    )
  ],
  "moved_source_absences": [
    asdict(row) for row in sorted(
      MOVED_SOURCE_ABSENCES,
      key=lambda row: (row.filename, row.moved_to, row.import_contract,
                       row.reason, row.artifact),
    )
  ],
}
preimage_bytes = json.dumps(
    preimage,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    allow_nan=False,
).encode("utf-8")
source_digest = hashlib.sha256(preimage_bytes).hexdigest()
```

There is no trailing newline, filesystem metadata, absolute root, timestamp, storage-order marker, or Python `repr` in the preimage. `source_digest` is exactly 64 lowercase hexadecimal characters. The dispatcher contract and `check_hook_retirement.py --contract` use this same digest; a mismatch is a manifest failure, not a warning. `--contract` exposes both the semantic storage order and the digest projection order so a readback cannot confuse the two.

`check_hook_retirement.py` imports both typed tuples and defines the exact contract payload. It does not maintain a third manifest or derive counts from a hardcoded number:

```text
{
  "schema": str == TOMBSTONE_SCHEMA,
  "retired_child_tombstones": list[{filename, owner, command_or_skill,
                                     profile_trigger, decision_semantics, artifact}],
  "moved_source_absences": list[{filename, moved_to, import_contract, reason, artifact}],
  "counts": {
    "retired_child_tombstones": 23,
    "moved_source_absences": 1,
    "retired_filenames": 24,
  },
  "active_events": list[str],
  "inactive_events": ["Stop"],
  "source_digest": str(64 lowercase hex),
  "missing_files": list[str],
  "executable_references": list[{path: str, line: int, token: str}],
  "generated_inventory_paths": list[str],
  "caller_audit": {
    "basenames": list[str] length 24,
    "matches": list[{basename: str, path: str, line: int, token: str}],
    "malformed_matches": list[{path: str, line: int, token: str}],
    "artifacts": list[{name: str, mode: str, producer: str, parser: str,
                        consumers: list[str]}],
  },
}
```

`--check` is fail-closed: the child tuple count is 23, the moved-source tuple count is 1, the union count is 24, all 24 files are absent, the two typed tuples are unique and disjoint from active handlers, executable references are zero, generated inventory contains no retired executable path, and all child `command_or_skill` values pass the grammar. `--contract` emits the payload above. The exact executable/template scan set is `.codex/hooks.json`, `.codex/config.toml`, `.codex/agents/`, `templates/`, `tools/catalog.yaml`, `tools/ci/run_python_quality_checks.sh`, `tools/agent_tools/check_agent_runtime_alignment.py`, `tools/agent_tools/check_convention_compliance.py`, `tools/agent_tools/convention_compliance_contracts.toml`, `tools/agent_tools/generate_agent_runtime_dashboard.py`, `tools/agent_tools/skill_lane_detector.py`, `tools/agent_tools/report_artifact_checks.py`, `tools/agent_tools/workflow_monitor.py`, `agents/skills/worktree-health.md`, `.agents/skills/worktree-health/SKILL.md`, `documents/experiments/gpu-admission-r5-source-packet.md`, `AGENTS.md`, `ROOT_AGENTS.md`, `README.md`, `documents/runtime/runtime-log-archive.md`, `tools/README.md`, `tools/experiments/execution_resource_plan.py`, and `tools/validation/notebook_quality.py`. Tests, closed issues, and historical evidence are readback inputs but not executable registration/template targets. Metadata-only allowlist is `tools/agent_tools/hook_retirement.py` and this design document; no allowlisted file may execute a retired path.

The dispatcher `--contract` readback uses the same field names and counts: `retired_child_tombstones`, `moved_source_absences`, `counts.retired_child_tombstones=23`, `counts.moved_source_absences=1`, `counts.retired_filenames=24`, and `source_digest`. The old `retired_hook_routes` key is absent from target readback; there is no compatibility alias.

The tombstone guard's artifact scan set is also fixed: `skill_usage.jsonl`, `behavior_events.jsonl`, and `workflow_monitoring.md`. `skill_usage.jsonl` may remain as an archived input and may be named by `historical_skill_usage_reader.py`, `generate_agent_improvement_guide.py`, or the historical dashboard readback only; it must not be an active producer, hook registration, catalog command, or inventory emitter. `behavior_events.jsonl` has exactly one active assembly owner, and `workflow_monitoring.md` has exactly one monitor owner. Any second writer or an executable route to the historical artifact fails closed.

### Deterministic 24-basename caller audit

The caller audit is generated from the manifest, never from a second regex or a hand-maintained filename list. Let `B = sorted({row.filename for row in RETIRED_CHILD_TOMBSTONES} ∪ {row.filename for row in MOVED_SOURCE_ABSENCES})`; the guard asserts `len(B)=24`, then searches every tracked file under the fixed audit roots with one exact fixed-string query per `basename`:

```text
CALLER_AUDIT_SCHEMA = "agent-canon.hook-retirement-caller-audit.v1"
CALLER_AUDIT_ROOTS = (".codex", ".agents", "agents", "documents", "evidence",
                      "templates", "tools", "tests", "README.md", "AGENTS.md",
                      "ROOT_AGENTS.md", "responsibility-scope.toml")
query = sorted(B)
matches = sorted((basename, path, line, token)
                 for basename in query
                 for path,line,token in git_fixed_string_matches(basename, CALLER_AUDIT_ROOTS))
```

The generated query order is lexical by basename; file order is lexical by repository-relative path; line numbers are ascending; the same line may produce one match per basename. The readback must include all 24 query basenames even when a target tree has zero non-metadata callers. `hook_retirement.py`, this design document, generated inventory metadata, and tests/fixtures are classified separately as manifest/metadata evidence; executable/template matches outside that allowlist are migration findings, not silently omitted results. `--contract` returns the query basenames and every match so implementation can prove that the audit covered all 23+1 names.

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
| spool context | `source_repo_key`, `hook_log_namespace` | non-empty strings added by `HookLogContext`; optional `codex_trace_key`, `codex_thread_id` are non-empty strings when environment provides them | namespace slug max 80; no-replace per-event path; mode 0600 temp file | `hook_event_log.py` remains sole transport owner |
| spool identity | `hook_run_id` | `hook-<compact timestamp>-<10 hex digest>-<10 hex nonce>`; path basename-safe; `fingerprint_json` helper returns 12 lowercase hex, while namespace disambiguation uses 8 lowercase hex | append-only no-replace; duplicate identical bytes is `duplicate`; conflict/I/O is failure | dispatcher catches all append failures and stays fail-open |
| append result | `status`, `hook_run_id`, `spool_path`, `event_sha256`, `error_code` | status is `spooled|duplicate|failed`; path is `Path`; event hash is 64 lowercase hex on success; error code is empty or `event_identity_missing|event_schema_invalid|spool_unavailable|spool_io_failure|spool_conflict` | returned by `HookLogContext.append`; not copied into dispatcher safety status | transport owner preserves result domain |
| telemetry | `safety_decision`, `operation` | optional non-empty strings; only block events emit them | UserPrompt block emits `safety_decision=block`; PreTool block additionally emits `operation`; no prompt, command, secret, stdout, stderr | field names and omission rules unchanged |
| behavior JSONL | `event_id`, `hook_invocation_id`, `hook_event_name`, `event_kind`, timestamp, and the complete logger parity field union | required fields use the domains above; empty strings/lists/bools/counts are explicit; no JSON null for an absent parity field | current `skill_usage.jsonl` has no independent event-byte limit; target `behavior_events.jsonl` retains that absence, while prompt excerpt remains 600 characters and all canonical JSON is UTF-8/one-line | `behavior_event_assembly.py` owns assembly/write; parser owns readback |

Dispatcher status domain is exactly `malformed_payload`, `pass`, `blocked_secret`, `blocked_destructive_git`, `projection_forwarded`, `unsuccessful_tool_response`, and `invalid_projection`; `Stop` emits none. `spooled`, `duplicate`, `failed`, and error codes belong to `HookAppendResult`, not dispatcher safety status. Spool failure never changes a safety decision.

## Skill logger replacement: classifier, lane emitter, dashboard, inventory

### Complete `skill_usage_logger` responsibility map

The old hook module is not replaced by one broad helper. Its complete responsibility set is split into single owners with one API and one write set per row. A caller may consume a result from an owner, but may not reimplement that responsibility or write the owner's artifact.

| responsibility | single owner | API contract | write set / side effect | callers |
| --- | --- | --- | --- | --- |
| prompt capture and redaction | `tools/agent_tools/prompt_capture.py` | `capture_prompt(payload, redaction_rules, excerpt_limit=600) -> PromptCapture` | none; immutable return containing status, redacted excerpt, original char count, fingerprint | `prompt_classifier.py`, behavior assembly |
| prompt classification | `tools/agent_tools/prompt_classifier.py` | `prompt_intake_signals(inputs: PromptClassifierInputs) -> PromptIntakeSignals` | none; no subprocess, Git, network, environment mutation, or file I/O | workflow evaluator and behavior assembly |
| feedback, candidate-reason, and related-skill normalization | `tools/agent_tools/prompt_classifier.py` | `feedback_targets(signals) -> tuple[str, ...]`; `should_log(signals) -> bool` | none; preserves current feedback labels/action/target and candidate-reason ordering | evaluator and behavior assembly consume the classifier result |
| tool selection | `tools/agent_tools/tool_selection.py` | `select_tools(payload) -> ToolSelection` | none; tuple/list ordering is part of return contract | behavior assembly and dashboard parser fixtures |
| subagent selection and attribution | `tools/agent_tools/subagent_selection.py` | `select_subagents(payload, workflow_context) -> SubagentSelection` | none; selection/workflow attribution is returned, not emitted directly | behavior assembly and workflow monitor |
| workflow context store/load | `tools/agent_tools/workflow_context.py` | `load_workflow_context(path) -> WorkflowContext`; `store_workflow_context(path, context) -> StoreResult` | only the existing paired `skill_usage_context.json` path (resolved under the selected log/report directory); atomic write; load/store failure is fail-open to an empty context, never a second event | subagent selection and behavior assembly |
| monitor emission | `tools/agent_tools/workflow_monitor.py` | existing `--behavior-event` and typed `emit_behavior_projection(report_dir, event)` | only report-dir `workflow_monitoring.md` and its existing monitor projection lines; never `skill_usage.jsonl` or `behavior_events.jsonl` | behavior assembly and closeout/readback consumers |
| behavior JSONL assembly | `tools/agent_tools/behavior_event_assembly.py` | `record_hook_invocation(parts) -> RecordHookInvocationResult`; internal `assemble_behavior_event(parts) -> BehaviorEvent` and `append_behavior_event(root, event) -> AppendResult` | only canonical `behavior_events.jsonl`, one record per eligible invocation; uses `hook_event_log.py` as transport and does not write monitor Markdown | dispatcher is the sole caller; dashboard is a read-only parser |
| historical skill-usage readback | `tools/agent_tools/historical_skill_usage_reader.py` | `read_skill_usage_history(path) -> HistoricalReadback` | none; opens `skill_usage.jsonl` read-only, never imports/executes the old logger, never appends or rewrites it | improvement guide, historical dashboard migration, fixture tests |

The ownership boundary is intentional: `workflow_monitor.py` owns monitor projection, while `behavior_event_assembly.py` owns the canonical JSONL bytes. Neither is a wrapper for the retired logger. `generate_agent_runtime_dashboard.py` and `generate_agent_improvement_guide.py` are read-only consumers; they do not become emitters. The target artifact is `behavior_events.jsonl`; `skill_usage.jsonl` remains a historical input only.

### Pure classifier owner

`tools/agent_tools/prompt_classifier.py` owns the current `PromptIntakeSignals` fields exactly: `skills`, `selected_workflows`, `candidate_skills`, `candidate_skill_reasons`, `candidate_workflows`, `candidate_tools`, `feedback_labels`, `feedback_action`, all as tuples of strings except `feedback_action: str`. `should_log()` and `feedback_targets()` remain pure. `prompt_intake_signals(inputs)` preserves current keyword, catalog, structural-lane, validation-repair, feedback, and related-skill ordering.

The classifier receives all repository-dependent knowledge as immutable input; it does not discover it. The exact input contract is:

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

`evaluate_workflow_selection.py` replaces `importlib.util.spec_from_file_location` and the `.codex/hooks/skill_usage_logger.py` path with a direct import of `prompt_classifier.prompt_intake_signals`. The evaluator retains the current case/result fields and expected/forbidden workflow oracle. No standalone classifier CLI or compatibility import is defined.

### Skill-lane detector and behavior emitter

The existing pure `tools/agent_tools/skill_lane_detector.py` remains the structural concept detector. Its implementation-ready output contract is:

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

The detector returns no record for an unmatched lane; it never writes logs. `tools/agent_tools/behavior_event_assembly.py` is the sole emitter for canonical durable behavior events, and `tools/agent_tools/workflow_monitor.py` is the sole emitter for durable monitor projections. The existing `--behavior-event` route accepts one assembled canonical object and emits a monitor projection line; it does not append `behavior_events.jsonl`. The event envelope is the fixed `agent-canon.behavior-event.v1` schema:

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

The classifier emits the existing behavior dimensions into this one event: selected/candidate skills and workflows, `candidate_skill_reasons`, feedback labels/action/targets, prompt capture, tool selection, subagent selection, workflow attribution/context, and structural lane evidence. This keeps one execution route and one event identity for dashboard aggregation. The assembly owner writes `behavior_events.jsonl`; the monitor owner writes the existing workflow monitoring artifact. Neither writes `skill_usage.jsonl`.

The remaining current logger fields are carried without semantic loss as follows; these are part of the behavior-event schema even when a dashboard view does not display them:

| current field family | exact type/nullability and domain |
| --- | --- |
| `hook_run_id` → `hook_invocation_id`, `hook_log_namespace`, `timestamp`, `root` | non-empty `str`; timestamp is UTC ISO text; `hook_invocation_id` is the current hook-run identity and is distinct from the derived behavior `event_id` |
| `event` (legacy logger field) → `event_kind` plus `hook_event_name` | legacy `event` is not copied as an alias; target kind is `behavior_snapshot`, transport name is required from dispatcher context |
| `event_declared`, `subagent_invoked`, `subagent_fork_context`, `prompt_feedback_detected` | `bool`, always present |
| `prompt_fingerprint`, `tool_input_fingerprint`, `payload_fingerprint`, `subagent_prompt_fingerprint` | `str`; empty sentinel or lowercase hex; prompt/subagent fingerprints are 16 hex characters, JSON fingerprints are 12 hex characters |
| `prompt_excerpt_truncated`, `skill_selection_kind`, `workflow_selection_kind`, `workflow_attribution_kind`, `workflow_context_kind`, `workflow_context_source`, `workflow_context_source_event`, `tool_selection_kind` | `str` or `bool` exactly as current emitter; empty string means not applicable; `workflow_attribution_kind` is `owner|context|missing`, `workflow_selection_kind` is empty or `declared_workflow|inherited_workflow|context_workflow`, and `tool_selection_kind` is empty or `executed_tool` |
| `skills`, `selected_skills`, `selected_workflows`, `workflow`, `workflow_owner_workflows`, `workflow_context_workflows`, `candidate_skills`, `candidate_skill_reasons`, `candidate_workflows`, `candidate_tools`, `selected_tools`, `subagent_targets`, `skill_source_fields`, `feedback_labels`, `feedback_targets`, `tool_input_keys` | `list[str]`, empty list means no value; preserve current sorted/tuple order after parser normalization |
| `selected_workflow`, `workflow_family`, `workflow_owner`, `tool_name`, `tool_command_verb`, `subagent_event_kind`, `subagent_tool_name`, `subagent_agent_type`, `subagent_target`, `subagent_model`, `subagent_reasoning_effort`, `feedback_action`, `workflow_context_timestamp`, `workflow_monitor_report_dir` | `str`, empty sentinel when absent; `subagent_event_kind` is empty or `spawn|send_input|wait|close|resume`; `feedback_action` is empty or `prompt_repair|memory_record`; workflow owner/family are first selected workflow only under current attribution rule |
| `skill_count`, `selected_workflow_count`, `candidate_skill_count`, `candidate_workflow_count`, `candidate_tool_count`, `selected_tool_count`, `subagent_target_count`, `subagent_prompt_char_count`, `subagent_item_count`, `observed_text_field_count`, `observed_text_value_count`, `payload_key_count`, `workflow_monitor_event_count`, `workflow_monitor_feedback_count`, `workflow_monitor_subagent_event_count`, `prompt_char_count`, `tool_input_key_count` | `int >= 0`; zero is the absent/empty sentinel |

The schema retains `prompt_fingerprint`, `prompt_excerpt_truncated`, tool input identity/key fields, feedback targets, selection counts, text-source counts, payload counts, monitor counts, and `root` so existing dashboard/readback and archive consumers can migrate by field projection rather than by behavior loss.

### Dashboard readback contract

`generate_agent_runtime_dashboard.py` reads only the canonical `behavior_events.jsonl`/workflow-monitor behavior-event rows for new evidence. It no longer treats `.codex/hooks/skill_usage_logger.py` or `skill_usage.jsonl` as an active source. `generate_agent_improvement_guide.py` may call `historical_skill_usage_reader.py` for archived evidence, but this is a read-only historical parser route, not a compatibility execution route. Historical files are never imported as Python, invoked as a CLI, appended to, or rewritten, and they are not regenerated into the target inventory.

The parser boundary is fixed:

| input artifact | parser owner | accepted purpose | forbidden behavior |
| --- | --- | --- | --- |
| `behavior_events.jsonl` and `behavior_event_json=` monitor lines | `behavior_event_assembly.py` schema/parser consumed by dashboard | active target behavior readback and dashboard oracle | no legacy-field guessing; no fallback to `skill_usage.jsonl` |
| historical `skill_usage.jsonl` | `historical_skill_usage_reader.py` | read-only migration/improvement-guide evidence, preserving old field names and nullability | no hook import, subprocess, execution, append, rewrite, or conversion into an active event |

Fixtures are exact: `tests/fixtures/behavior_events/accepted.jsonl`, `duplicate.jsonl`, `malformed.jsonl`, `out_of_order.jsonl`, `escaping.jsonl`, `oracle.json`, plus `tests/fixtures/skill_usage_history/historical.jsonl`, `malformed.jsonl`, and `oracle.json`. The historical fixtures prove that old records remain readable as evidence while the behavior fixtures prove that the active parser never accepts them as target records.

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

The parser aggregates malformed records without aborting the batch: `malformed_by_reason` uses stable reasons `json`, `duplicate_key`, `noncanonical_json`, `timestamp`, `schema`, `field_type`, `field_domain`, `conflicting_event_id`, and `line_encoding`. Dashboard actions, `report_artifact_checks.py` closeout readback, and `workflow_monitor.py` standard closeout events refer to `prompt_classifier.py`, `skill_lane_detector.py`, and `workflow_monitor.py`, never to the retired logger path.

### Inventory emitter and generated readback

`tools/agent_tools/log_surface_inventory.py` remains the sole inventory emitter. Its generated `documents/runtime/log-surface-inventory.json` keeps `schema_version: 1`, sorted `scanned_files`, and sorted records `{path,surface,emitter,field,line,certainty}`. The log-inventory gate is evaluated against the current `main` baseline after PR #471, never against a pre-PR-471 checkout or a stale vendored snapshot. The implementation validation packet records `baseline_branch=main`, `baseline_floor_pr=471`, `baseline_selector=current-main-after-pr-471`, and the exact `git rev-parse main` commit used for readback; an unproven or pre-471 baseline fails closed. After migration:

- `.codex/hooks/skill_usage_logger.py` is absent from both `scanned_files` and `records`;
- `tools/agent_tools/prompt_capture.py`, `tools/agent_tools/prompt_classifier.py`, `tools/agent_tools/tool_selection.py`, `tools/agent_tools/subagent_selection.py`, `tools/agent_tools/workflow_context.py`, `tools/agent_tools/behavior_event_assembly.py`, `tools/agent_tools/skill_lane_detector.py`, `tools/agent_tools/workflow_monitor.py`, `tools/agent_tools/generate_agent_runtime_dashboard.py`, and `tools/agent_tools/generate_agent_improvement_guide.py` are present with their new static/dynamic fields or read-only consumer surfaces;
- `behavior_events.jsonl` is the active target artifact; `skill_usage.jsonl` is classified as historical read-only evidence and is not an active emitter path;
- `behavior_event_json`, `agent-canon.behavior-event.v1`, `prompt_capture_status`, `prompt_excerpt_redacted`, `prompt_char_count`, `tool_name`, `tool_command_verb`, `selected_tools`, `feedback_labels`, `candidate_skill_reasons`, every `subagent_*` and `workflow_*` attribution field, and `skill_lane` are read back from the new emitter where statically discoverable;
- old hook child names are absent from executable inventory paths, while their names may occur only in the manifest/design metadata allowlist;
- `check_hook_retirement.py` verifies this generated readback and rejects an old path in either `scanned_files` or a record `path`; the dashboard parser verifies the behavior-event schema and oracle separately. The inventory gate also records the post-PR-471 baseline selector and refuses a comparison that cannot prove that provenance.

## Import, CLI, and owner contract matrix

| target | import/CLI contract | caller migration |
| --- | --- | --- |
| `tools/agent_tools/prompt_capture.py` | import-only: `PromptCapture`, `capture_prompt`; no CLI | classifier and behavior assembly direct import; no write |
| `tools/agent_tools/prompt_classifier.py` | import-only: `PromptClassifierInputs`, `PromptIntakeSignals`, `prompt_intake_signals`; no hook CLI | evaluator injects frozen repo root/catalog/routing rules; behavior assembly direct import |
| `tools/agent_tools/tool_selection.py` | import-only: `ToolSelection`, `select_tools`; no CLI | behavior assembly direct import; no write |
| `tools/agent_tools/subagent_selection.py` | import-only: `SubagentSelection`, `select_subagents`; no CLI | behavior assembly direct import; no write |
| `tools/agent_tools/workflow_context.py` | import-only: `WorkflowContext`, `load_workflow_context`, `store_workflow_context`; no hook CLI | selected report-directory context JSON only |
| `tools/agent_tools/behavior_event_assembly.py` | import-only: `HookInvocationParts`, `RecordHookInvocationResult`, `record_hook_invocation`, `BehaviorEvent`, `assemble_behavior_event`, `append_behavior_event`, `parse_behavior_events`; no hook CLI | dispatcher is the sole caller; sole writer of `behavior_events.jsonl`; calls monitor only after a new append |
| `tools/agent_tools/historical_skill_usage_reader.py` | import-only: `HistoricalReadback`, `read_skill_usage_history`; no CLI and no import of retired logger | read-only `skill_usage.jsonl` input |
| `tools/agent_tools/execution_resource_projection.py` | import-only: `validate_normalized_input`, `validate_projection_bytes`, `projection_context_payload`; no guard CLI | dispatcher and pure projection tests direct import |
| `tools/agent_tools/hook_safety.py` | import-only pure API listed above; no standalone safety CLI | dispatcher direct import; old hook safety path deleted |
| `tools/agent_tools/hook_retirement.py` | import-only constants/dataclass; no executable entrypoint | dispatcher and `check_hook_retirement.py` share one manifest |
| `tools/agent_tools/check_hook_retirement.py` | `python3 tools/agent_tools/check_hook_retirement.py --root . --check`; readback via `--contract` | imports both typed tuples, computes digest, and generates the 24-basename caller query |
| `tools/agent_tools/tool_rejection_preflight.py` | existing CLI and typed gate output | four old gate templates become direct owner commands |
| `tools/agent_tools/import_responsibility.py` | existing checker CLI/JSON | module-boundary owner |
| `tools/agent_tools/task_authority.py` | import-only final B7 route: `first_party_library_authorized` | `responsibility_scope.py` and `$dependency-module-change` consume its result read-only |
| `tools/agent_tools/review_dispatch.py` | import-only final B9 route: `resolve_current_review_state` | sole review decision producer |
| `tools/agent_tools/report_artifact_checks.py` | existing validation readback API; no B9 decision | consumes typed B9 state read-only |
| `tools/agent_tools/task_close.py` | existing closeout API; no B9 decision | consumes typed B9 state read-only |
| `tools/ci/run_python_quality_checks.sh` | existing shell quality route; no B9 decision | invokes validation consumers only |
| `.codex/hooks/hook_dispatcher.py` | direct import-only caller: `record_hook_invocation(parts)`; exactly once after each of the three finalized handler results; no JSONL/monitor write | sole active-hook caller; returns the finalized handler output unchanged |
| `workflow_monitor.py` | import-only `emit_behavior_projection(report_dir, event) -> MonitorProjectionResult`; existing `--behavior-event` CLI is the equivalent explicit projection route | consumes the assembled record and writes only `behavior_event_json=<JSON>` projection lines/monitor Markdown; it does not assemble or append canonical JSONL |
| `generate_agent_runtime_dashboard.py` | existing read-only dashboard CLI; `agent-canon.behavior-readback.v1` oracle and parser aggregation | reads active behavior events and monitor projections; retains prompt/tool/feedback/subagent/workflow/lane metrics |
| `generate_agent_improvement_guide.py` | existing read-only guide CLI | consumes `historical_skill_usage_reader.py` for archived `skill_usage.jsonl` and active dashboard evidence; no active emission |
| `log_surface_inventory.py` | existing `--check --baseline --baseline-ref current-main-after-pr-471` and generated JSON | emits updated inventory once after all path migrations, using the post-PR-471 current-main baseline |

## Exact implementation write set and fixture corpus

This is the exact future implementation write set `W`; this design wave does not touch these implementation paths.

**new files:**

`tools/agent_tools/prompt_capture.py`, `tools/agent_tools/prompt_classifier.py`, `tools/agent_tools/tool_selection.py`, `tools/agent_tools/subagent_selection.py`, `tools/agent_tools/workflow_context.py`, `tools/agent_tools/behavior_event_assembly.py`, `tools/agent_tools/historical_skill_usage_reader.py`, `tools/agent_tools/execution_resource_projection.py`, `tools/agent_tools/hook_safety.py`, `tools/agent_tools/hook_retirement.py`, `tools/agent_tools/check_hook_retirement.py`, `tests/agent_tools/test_prompt_capture.py`, `tests/agent_tools/test_prompt_classifier.py`, `tests/agent_tools/test_tool_selection.py`, `tests/agent_tools/test_subagent_selection.py`, `tests/agent_tools/test_workflow_context.py`, `tests/agent_tools/test_behavior_event_assembly.py`, `tests/agent_tools/test_historical_skill_usage_reader.py`, `tests/agent_tools/test_execution_resource_projection.py`, `tests/agent_tools/test_hook_safety.py`, `tests/agent_tools/test_hook_retirement.py`, `tests/agent_tools/test_behavior_event_parser.py`, `tests/fixtures/hook_retirement/clean/hooks.json`, `tests/fixtures/hook_retirement/clean/template.md`, `tests/fixtures/hook_retirement/clean/catalog.yaml`, `tests/fixtures/hook_retirement/clean/inventory.json`, `tests/fixtures/hook_retirement/violation/hooks.json`, `tests/fixtures/hook_retirement/violation/template.md`, `tests/fixtures/hook_retirement/violation/catalog.yaml`, `tests/fixtures/hook_retirement/violation/inventory.json`, `tests/fixtures/hook_retirement/violation/.codex/hooks/branch_worktree_guard.py`, `tests/fixtures/behavior_events/accepted.jsonl`, `tests/fixtures/behavior_events/duplicate.jsonl`, `tests/fixtures/behavior_events/malformed.jsonl`, `tests/fixtures/behavior_events/out_of_order.jsonl`, `tests/fixtures/behavior_events/escaping.jsonl`, `tests/fixtures/behavior_events/oracle.json`, `tests/fixtures/behavior_events/hook_invocation_parts_user_prompt.json`, `tests/fixtures/behavior_events/hook_invocation_parts_pre_tool.json`, `tests/fixtures/behavior_events/hook_invocation_parts_post_tool.json`, `tests/fixtures/behavior_events/ineligible_blocked.json`, `tests/fixtures/behavior_events/record_hook_invocation_oracle.json`, `tests/fixtures/skill_usage_history/historical.jsonl`, `tests/fixtures/skill_usage_history/malformed.jsonl`, `tests/fixtures/skill_usage_history/oracle.json`。

**modified/migrated files:**

`.codex/hooks/hook_dispatcher.py`, `.codex/hooks.json`, `.codex/README.md`, `README.md`, `agents/canonical/CODEX_SUBAGENTS.md`, `documents/conventions/coding-conventions-python.md`, `documents/design/codex-spark-implementation-routing.md`, `documents/design/responsibility-scope-management.md`, `documents/runtime/runtime-log-archive.md`, `documents/runtime/runtime-log-archive-migration.md`, `documents/tools/README.md`, `evidence/agent-evals/issue_eval_manifest.toml`, `evidence/agent-evals/workflow_selection_eval.toml`, `.agents/skills/worktree-health/SKILL.md`, `tools/README.md`, `tools/experiments/execution_resource_plan.py`, `tools/validation/notebook_quality.py`, `tools/agent_tools/evaluate_workflow_selection.py`, `tools/agent_tools/evaluate_skill_workflow_prompts.py`, `tools/agent_tools/tool_rejection_preflight.py`, `tools/agent_tools/import_responsibility.py`, `tools/agent_tools/task_authority.py`, `tools/agent_tools/review_dispatch.py`, `tools/agent_tools/report_artifact_checks.py`, `tools/agent_tools/task_close.py`, `tools/agent_tools/workflow_monitor.py`, `tools/agent_tools/skill_lane_detector.py`, `tools/agent_tools/generate_agent_runtime_dashboard.py`, `tools/agent_tools/generate_agent_improvement_guide.py`, `.github/workflows/agent-improvement-guide.yml`, `tools/agent_tools/log_surface_inventory.py`, `tools/agent_tools/runtime_log_paths.py`, `tools/agent_tools/runtime_log_archive_git.py`, `tools/agent_tools/export_codex_runtime_summary.py`, `tools/agent_tools/check_agent_runtime_alignment.py`, `tools/agent_tools/check_convention_compliance.py`, `tools/agent_tools/convention_compliance_contracts.toml`, `tools/ci/run_python_quality_checks.sh`, `tools/catalog.yaml`, `responsibility-scope.toml`, `documents/runtime/log-surface-inventory.json`, `documents/experiments/gpu-admission-r5-source-packet.md`, `agents/canonical/CODEX_WORKFLOW.md`, `agents/skills/worktree-health.md`, `AGENTS.md`, `ROOT_AGENTS.md`, `tests/agent_tools/test_codex_hooks.py`, `tests/agent_tools/test_hook_event_log.py`, `tests/tools/test_execution_resource_plan.py`, `tests/agent_tools/test_evaluate_workflow_selection.py`, `tests/agent_tools/test_evaluate_skill_workflow_prompts.py`, `tests/agent_tools/test_tool_rejection_preflight.py`, `tests/agent_tools/test_import_responsibility.py`, `tests/agent_tools/test_review_dispatch.py`, `tests/agent_tools/test_task_start_and_close.py`, `tests/agent_tools/test_check_agent_runtime_alignment.py`, `tests/agent_tools/test_check_convention_compliance.py`, `tests/agent_tools/test_generate_agent_runtime_dashboard.py`, `tests/agent_tools/test_generate_agent_improvement_guide.py`, `tests/agent_tools/test_workflow_monitor.py`, `tests/agent_tools/test_log_surface_inventory.py`, `tests/agent_tools/test_responsibility_scope.py`, `tests/agent_tools/test_task_authority.py`。

**runtime artifact write set:**

`behavior_events.jsonl` is written only by `tools/agent_tools/behavior_event_assembly.py`; `workflow_monitoring.md` and its projection lines are written only by `tools/agent_tools/workflow_monitor.py` after a new behavior JSONL append. `.codex/hooks/hook_dispatcher.py` writes neither artifact and `skill_usage.jsonl` has no active writer. A runtime append failure or monitor failure is telemetry-only and leaves the finalized handler output unchanged.

**deleted files, only after caller migration:**

`.codex/hooks/hook_safety.py`, `.codex/hooks/execution_resource_plan_projection_guard.py`, `.codex/hooks/skill_usage_logger.py`, `.codex/hooks/prompt_secret_guard.py`, `.codex/hooks/branch_worktree_guard.py`, `.codex/hooks/cause_investigation_guard.py`, `.codex/hooks/module_boundary_guard.py`, `.codex/hooks/library_implementation_guard.py`, `.codex/hooks/style_checker_guard.py`, `.codex/hooks/completion_review_guard.py`, `.codex/hooks/log_archive_mount_warning.py`, `.codex/hooks/reference_capture_guard.py`, `.codex/hooks/direct_rg_context_guard.py`, `.codex/hooks/task_authority_schema_guard.py`, `.codex/hooks/role_write_policy_guard.py`, `.codex/hooks/oop_readability_guard.py`, `.codex/hooks/first_party_library_guard.py`, `.codex/hooks/helper_inventory_guard.py`, `.codex/hooks/helper_first_guard.py`, `.codex/hooks/log_surface_inventory_guard.py`, `.codex/hooks/notebook_quality_guard.py`, `.codex/hooks/goal_completion_guard.py`, `.codex/hooks/codex_runtime_summary_logger.py`, `.codex/hooks/runtime_log_auto_sync.py`。

The exact tombstone scan includes every deleted path above, every path in the executable/template scan set, and the generated inventory. The broader caller/readback paths are searched by the manifest-generated caller audit; they are not all executable-reference scan targets. Fixture violation files are test data under a fixture root and are never treated as target-tree registrations.

## Retirement order and reverse trace

1. Establish the pure owners, historical read-only parser, behavior assembly owner, and their pure-owner tests; update dispatcher import bootstrap to the non-hook owner. Keep current child files only as migration evidence.
2. Move the complete safety implementation to `tools/agent_tools/hook_safety.py`; pass pure safety tests; delete `.codex/hooks/hook_safety.py`; prove the old path is absent before B3/B4 retirement.
3. Migrate dashboard, skill lane, workflow monitor, inventory, evaluator, convention/readback, report, worktree, and GPU source-packet callers; generate the new inventory in memory and compare it before writing the generated file.
4. Retire the 14 direct files in this order: `log_archive_mount_warning.py`, `reference_capture_guard.py`, `direct_rg_context_guard.py`, `task_authority_schema_guard.py`, `role_write_policy_guard.py`, `oop_readability_guard.py`, `first_party_library_guard.py`, `helper_inventory_guard.py`, `helper_first_guard.py`, `log_surface_inventory_guard.py`, `notebook_quality_guard.py`, `goal_completion_guard.py`, `codex_runtime_summary_logger.py`, `runtime_log_auto_sync.py`.
5. Retire the 9 blocking files in dependency order: `execution_resource_plan_projection_guard.py`, `skill_usage_logger.py`, `prompt_secret_guard.py`, `branch_worktree_guard.py`, `cause_investigation_guard.py`, `module_boundary_guard.py`, `library_implementation_guard.py`, `style_checker_guard.py`, `completion_review_guard.py`.
6. Run `check_hook_retirement.py`, dispatcher contract readback, dashboard/skill-lane readback, generated inventory readback, catalog, responsibility, convention, dependency, and pure-owner tests from one source snapshot; assert each active dispatcher handler calls `record_hook_invocation` exactly once after its finalized result and `Stop` calls it zero times.

Forward trace: each active registration in `hooks.json` invokes `hook_dispatcher.py`; the dispatcher finalizes `hook_safety.py` or `execution_resource_projection.py`, constructs `HookInvocationParts`, and calls `behavior_event_assembly.record_hook_invocation(parts)` exactly once; assembly applies `eligible_hook_invocation`/classifier `should_log`, writes one new `behavior_events.jsonl` snapshot, then calls `workflow_monitor.py --behavior-event` for projection; dashboard reads the active event/projection; archived `skill_usage.jsonl` → `historical_skill_usage_reader.py` → `generate_agent_improvement_guide.py` (read-only only); reviewer/closeout input → `review_dispatch.py` → `report_artifact_checks.py`/`task_close.py`; all retired names → `hook_retirement.py` → `check_hook_retirement.py`.

Reverse trace: every deleted filename maps to exactly one tombstone owner and one import/CLI/skill representation; the guard proves filesystem absence, zero executable references, updated inventory paths, and dispatcher readback count. The dispatcher test proves one post-result caller edge for each active event, assembly tests prove one eligible invocation → one JSONL snapshot → at most one new monitor projection, and fail-open tests prove assembly failure cannot alter handler output. A failed reverse edge blocks deletion and cannot be repaired with a wrapper.

## Fail-open/fail-closed parity

| boundary | fail-open | fail-closed |
| --- | --- | --- |
| UserPromptSubmit | malformed/empty payload, spool failure | high-confidence secret |
| PreToolUse | malformed/empty payload, spool failure | unauthorized protected Git; creation requires both creation and destructive authority |
| PostToolUse | malformed input, non-Bash, nonzero response, invalid projection, spool failure | no hook transport block; producer owns execution failure |
| Stop | inactive no-op | none |
| behavior-event dashboard | no event rows report `missing`; malformed JSON/field/timestamp rows aggregate as `malformed` without aborting valid rows | never convert missing/malformed into `present` |
| preflight/closeout | no implicit approval | unknown owner/gate, stale command, missing evidence, non-`APPROVE` review |
| tombstone guard | none | any absent-file, executable-reference, manifest, or inventory violation |

## Validation corpus

Exact fixture and test corpus:

- active contract: 3 registrations, inactive Stop, aliases, official schema, no subprocess/Git/network; each `UserPromptSubmit`/`PreToolUse`/`PostToolUse` handler calls `record_hook_invocation(parts)` exactly once after the finalized result, and `Stop` calls it zero times;
- safety: four secret classes, benign/malformed prompt, protected/read-only/authorized Git, same-segment creation AND gate, shell wrapper/backtick/opaque cases, exact redaction and hash;
- projection: raw six-key normalization, exact nine-key projection, nested nullable admission/error, duplicate/extra/nonfinite/schema/path/byte/LF/unsuccessful matrices;
- skill replacement: frozen workflow manifest, immutable injected `repo_root`/catalog/routing-rules classifier inputs, all eight `PromptIntakeSignals` fields, prompt capture/tool/feedback/candidate-reason/subagent/workflow-attribution fields with current empty-string/list/bool/int domains, structural lane observed/candidate/unmatched, one-snapshot-per-invocation cardinality, exact event-id preimage, canonical behavior-event JSON parse, duplicate/order/timestamp/escaping/malformed aggregation, historical `skill_usage.jsonl` read-only parsing, and missing/malformed dashboard readback against `oracle.json`;
- dispatcher-to-assembly: three event-specific parts fixtures, finalized pass/block/projection/unsuccessful results, eligible and `should_log` truth table, exactly-once post-result call assertions, JSONL-write-before-monitor ordering, duplicate/no-monitor retry, append/monitor fail-open, and `record_hook_invocation_oracle.json`;
- inventory: old logger and 24 old executable paths absent, new emitter paths and fields present, sorted generated schema and no stale `scanned_files`/record path;
- manifest: `retired_child_tombstones=23`, `moved_source_absences=1`, `retired_filenames=24`, reproducible `source_digest`, and caller audit containing all 24 generated basenames;
- conventions/readback: `check_convention_compliance.py`, `convention_compliance_contracts.toml`, `check_agent_runtime_alignment.py`, `run_python_quality_checks.sh`, `report_artifact_checks.py`, `agents/skills/worktree-health.md`, and `documents/experiments/gpu-admission-r5-source-packet.md` contain canonical owner paths only;
- pure-owner tests: `test_prompt_capture.py`, `test_prompt_classifier.py`, `test_tool_selection.py`, `test_subagent_selection.py`, `test_workflow_context.py`, `test_behavior_event_assembly.py`, `test_historical_skill_usage_reader.py`, `test_hook_safety.py`, `test_execution_resource_projection.py`, and `test_hook_retirement.py` prove import side-effect absence, immutable-input/no-subprocess behavior, domain/nullability, parity, event identity/cardinality, historical parser separation, and tombstone guard behavior; `test_codex_hooks.py` proves the dispatcher caller contract and ordering.

Target validation commands are `python3 tools/agent_tools/check_hook_retirement.py --root . --check`, `python3 tools/agent_tools/check_agent_runtime_alignment.py`, `python3 tools/agent_tools/check_convention_compliance.py`, `python3 tools/agent_tools/log_surface_inventory.py --root . --check --baseline documents/runtime/log-surface-inventory.json --baseline-ref current-main-after-pr-471`, `tools/bin/agent-canon docs check` on changed Markdown, the focused pytest corpus above, `python3 tools/agent_tools/responsibility_scope.py --root .`, and the repository dependency review selected by the implementation profile. The inventory command must resolve the baseline from current `main` after PR #471 and record its exact commit; a vendored or pre-471 baseline is invalid.

No code implementation, compatibility wrapper, parent pin update, root-view sync, branch publication, or commit is authorized by this design wave.

## Evidence ledger

| id | observation | source/readback | target proof |
| --- | --- | --- | --- |
| E1 | current registration has UserPromptSubmit, PreToolUse, PostToolUse; Stop is inactive | `.codex/hooks.json`, dispatcher contract | active contract test and readback |
| E2 | current dispatcher duplicates 23 child names into `FORMER_ACTIVE_HOOK_CHILDREN` and `RETIRED_HOOK_ROUTES` while moved `hook_safety.py` is a separate source absence | dispatcher lines 94–163 and safety import readback | typed 23/1/24 manifest counts and tombstone checker |
| E3 | current hook safety owner is `.codex/hooks/hook_safety.py` and dispatcher imports it | dispatcher/safety readback | new owner import and old path absence |
| E4 | evaluator dynamically imports old skill logger | evaluator `load_skill_usage_logger` | direct classifier import test |
| E5 | dashboard and generated inventory read old logger fields/path | dashboard and `documents/runtime/log-surface-inventory.json` grep/readback | new workflow-monitor lane schema and inventory diff |
| E6 | projection limit is 64 KiB and hook stdin limit is 256 KiB | current dispatcher/projection constants | byte-limit corpus |
| E7 | spool is bounded fingerprint/status telemetry with no explicit event-byte limit and no-replace identity | hook event log readback | field/domain/nullability parity test |
| E8 | requested convention, quality, report, worktree, GPU, catalog, responsibility, test, and fixture paths are caller/readback surfaces | exact path set above | exact write-set/tombstone scan |
| E9 | current skill logger emits prompt capture, tool selection, feedback, candidate reasons, subagent, and workflow-context fields consumed by dashboard readers | `skill_usage_logger.py` dataclasses/emitter and dashboard accumulators | canonical behavior-event schema and fixed dashboard oracle |
| E10 | manifest digest and behavior parser require independent deterministic serialization/order rules | typed manifest projection and dashboard readback design | source digest preimage and parser corpus |
| E11 | active dispatcher handlers have one finalized result before behavior telemetry can be assembled | dispatcher event handlers and behavior assembly caller contract | exactly-once `record_hook_invocation` call, eligible snapshot cardinality, JSONL-before-monitor order, and fail-open caller tests |
