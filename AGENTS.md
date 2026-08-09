# AgentCanon Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Documents AgentCanon Repository Instructions for this repository.
downstream design documents/rule/README.md document filename, placement, and structure rules.
upstream design documents/design/request-intent-and-update-relation.md positive rule, request authority, and sparse reconciliation projection contract.
downstream design README.md shared canon overview must reflect runtime contract
downstream design ROOT_AGENTS.md template-root runtime entrypoint owner map
downstream implementation tools/agent_tools/check_agent_runtime_alignment.py validates runtime owner-map alignment
downstream implementation tools/agent_tools/hook_safety.py blocks unconfirmed shared-checkout Git mutations
@dependency-end
-->

This tree is the standalone AgentCanon source of truth. Template and derived
repositories consume it through `vendor/agent-canon/` and root runtime views.

## Reader Map

Target-State-First, Decision Sufficiency, model/profile, ToolCall, capacity,
and lifecycle behavior is projected from the canonical owners:
[workflow](agents/canonical/CODEX_WORKFLOW.md),
[subagents](agents/canonical/CODEX_SUBAGENTS.md),
[communication](agents/COMMUNICATION_PROTOCOL.md), and the approved
[implementation contract](documents/design/codex-spark-implementation-routing.md).
This entrypoint does not create a second policy source.

This repository entrypoint maps agents working inside the standalone
AgentCanon source tree to the canonical owner surfaces. Use `Read First` for
the initial document path, `Scope` to identify the source area, `Runtime Owner
Map` to find the owner of runtime contracts, `Task Entry` to start
repo-changing work, and `Validation` before closeout. This file routes readers;
the detailed workflow, skill, role, profile, and closeout rules remain in the
owner surfaces it names.

## Positive Rule Contract

各規約は、実行する操作、到達する状態、完了を示す証拠を肯定形で記述する。
制約は対応する操作の事前条件・適用境界・正規代替ルートとして配置する。
この契約の設計正本は
[`documents/design/request-intent-and-update-relation.md`](documents/design/request-intent-and-update-relation.md)
であり、`ROOT_AGENTS.md` はその canonical reader route を所有する。
`AGENTS.md` は同じ契約を source-tree root view として投影する。
各変更は `operation -> resulting state -> completion evidence` の順に
`Design-To-Implementation Trace` へ接続する。
質問・明示 write clause・進行中 update・integration cleanup の compact flow は
[`documents/design/request-intent-and-update-relation.md`](documents/design/request-intent-and-update-relation.md)
から各 canonical owner へ投影する。
Related Document Closure は active DIC route でだけ DIC-010 の path+section+clause/ref receipt を
owner packet が消費する。bounded owner/path/targeted-validation route には適用しない。

この projection は `operation -> resulting state -> completion evidence` の順で
materialize します。質問は read scope と evidence を読み、evidence-backed answer
complete state に到達し、回答と read-scope packet readback を完了 evidence にします。
明示 write clause は target、operation、owner、write set、acceptance evidence を結合し、
owner handoff-ready state に到達し、既存 write packet readback を完了 evidence にします。
追加または変更された request clause は既存 write gate を通って active context に overlay
され、goal/artifact/order/handoff sparse delta state に到達し、変更 clause と delta packet
readback および context reuse または必要並列 handoff を完了 evidence にします。
completed integration は tree/remote readback を受け、既存 cleanup executor dispatch state
に到達し、executor receipt、CleanupProof、closeout packet readback を完了 evidence にします。

public API / behavior / schema、algorithm、ownership / path、runtime contract の変更、または
明示的に選択した design workflow の implementation stage は、
[`agents/internal-routines/design-implementation-correspondence.md`](agents/internal-routines/design-implementation-correspondence.md)
を先に通ります。これは各 skill に共通規則を複製するための新しい policy
source ではなく、owning design の read、clause fingerprint、handoff、
forward/reverse review coverage、design drift block の内部 route です。
owner、path、targeted validation が固定された bounded edit は通常の owner route として
短い owner/path/validation note で完了し、この routine の fingerprint/closure を要求しません。
- After context compaction, invoke the final-objective declaration required by
  `agents/COMMUNICATION_PROTOCOL.md` section `Post-Compaction Objective
  Re-Declaration Contract` before any work resumes.

## Codex Loading Priority In This Tree

Codex still applies global Codex-home guidance before repository guidance. For
repository guidance, it walks from the detected project root to the current
working directory, selecting at most one instruction file in each directory:
`AGENTS.override.md`, then `AGENTS.md`, then fallback names listed in
`project_doc_fallback_filenames`. Empty instruction files are skipped, and
Codex stops adding project-doc content when the combined size reaches
`project_doc_max_bytes`.

When the detected project root is this AgentCanon checkout, this `AGENTS.md` is
the source-tree repo instruction entrypoint. When Codex starts from a template
or derived parent root, the parent `/AGENTS.md` runtime view loads
`ROOT_AGENTS.md` instead. In that parent-root session, this file is not
automatically loaded merely because a task mentions AgentCanon or edits
`vendor/agent-canon/`; read it manually only when the AgentCanon source
checkout is selected as owner evidence. It becomes automatic repo instruction
context only when Codex's project-root/CWD chain is inside the AgentCanon
checkout.

Do not copy rules between these files to "make sure" Codex sees them. Put
template-root runtime behavior in `ROOT_AGENTS.md`, standalone AgentCanon source
entry behavior in this file, GitHub-subtree overlay behavior in
`.github/AGENTS.md`, and workflow / skill / closeout policy in the owner
surfaces listed below.

## Read First

- `README.md`
- `documents/README.md`
- `documents/rule/README.md`（文書 filename は英語、本文は日本語）
- `agents/README.md`
- `agents/workflows/README.md`
- `agents/canonical/README.md`
- `.codex/README.md`

## Scope

- root runtime entrypoint source: `ROOT_AGENTS.md`
- Codex runtime defaults: `.codex/`
- public skill registry and shims: `agents/skills/`, `.agents/skills/`
- internal workflow routines: `agents/internal-routines/`
- workflow, subagent, and review contracts: `agents/`
- shared runtime surface ownership: `documents/`
- agent support tools and validation: `tools/`
- agent-specific regression tests: `tests/agent_tools/`

Multiple chats or sessions may use this checkout concurrently. Treat every
unknown dirty, staged, untracked, branch, and worktree state as owned by the
user or another chat, and preserve that state across routing and repair.
Protected Git operations include `git restore`, `git reset`, forced `git clean`,
mutating `git stash`, checkout/switch, and branch/worktree create, delete, move,
rename, or prune. Normal branch/worktree creation records creation authority and
reason; force-create/ref overwrite additionally requires destructive authority and
reason. Existing checkout/switch, delete/rename/reset, and other history/ref
mutations require destructive authority and reason. Reversible tracking metadata
and `git worktree lock/unlock` do not mutate refs, history, or worktrees and are
not destructive. Proven exact task ownership only bounds which paths may be
named in an approval request; explicit destructive approval remains required for
destructive operations.
A protected destructive mutation proceeds only when the user explicitly approves
it and the same command segment carries
`AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval` plus a nonempty
`AGENT_CANON_DESTRUCTIVE_GIT_REASON`. Normal branch/worktree creation instead
requires same-segment
`AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request` or
`agent_canon_workflow` plus a nonempty `AGENT_CANON_BRANCH_WORKTREE_REASON`;
force-create/ref overwrite requires both authority pairs. `latest` / `apply` /
merge wrappers require destructive authority only unless their owner route
actually creates a branch/worktree. Collision handling keeps the current
branch/worktree and requests user direction.

Canonical repo-local lifecycle commands are bounded to a separate workspace route:
`repository_topic_clone.py` and `dependency_module_change.py` may prepare, reuse, and use
`<project-root>/workspace/<topic-slug>/<repo-name>` without operation-level approval when
non-empty owner evidence and exact computed identity are present. This does not authorize raw
shared-checkout Git mutations or bypass the hook. At closeout, lifecycle skills dispatch proof-
gated cleanup with computed clone identity, owner/marker evidence, clean state, and remote
head/tree readback; publication artifacts are optional coherent enrichment. Only ordinary
`CleanupProof` / cleanup receipt authorizes deletion. Collisions,
unknown dirty state, and proof mismatch remain preserved typed holds.

## Runtime Owner Map

| Contract | Owner Surface | Validation |
| -------- | ------------- | ---------- |
| root runtime entrypoint | `ROOT_AGENTS.md`; `documents/runtime/shared-runtime-surfaces.toml` | `PYTHONPATH=tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check` |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| role behavior and stage conditions | `.codex/agents/*.toml`; `agents/agents_config.json` | `check_agent_runtime_alignment.py` |
| public skill registry | `agents/skills/catalog.yaml`; `.agents/skills/*/SKILL.md` | `check_agent_runtime_alignment.py` |
| internal routine placement | `agents/internal-routines/README.md`; `documents/structure/repo-structure-contract.toml` | `repo_structure_contract.py` |
| design-to-implementation correspondence | `agents/internal-routines/design-implementation-correspondence.md`; `documents/design/*.md` | `check_design_doc_claims.py`; design/review readback |
| implementation flow and handoff packet | `agents/workflows/implementation-waterfall-workflow.md`; `agents/COMMUNICATION_PROTOCOL.md` | task run bundle review |
| shared-checkout Git mutation and branch/worktree creation route | `agents/canonical/CODEX_WORKFLOW.md`; `tools/agent_tools/hook_safety.py`; `agents/skills/worktree-health.md` | operation-risk Git authority matrix; critical PreToolUse guard; `check_convention_compliance.py` |
| runtime profile and validation routing | `documents/runtime/runtime-profiles-and-check-matrix.md` | profile-specific checks |
| closeout evidence | `tools/agent_tools/task_close.py`; `tools/agent_tools/report_artifact_checks.py` | closeout artifact gate |
| AgentCanon update transaction | `documents/agent-canon/agent-canon-update-route.md`; `tools/agent_tools/update_lifecycle_contract.py` | boundary-owned G1-G6 receipts; `tools/agent_tools/task_close.py` |

Update the owner surface first, then adjust this entrypoint when reader routing
changes. `AGENTS.md` is a repository-local map; it is not the policy source for
workflow stages, skill routing, role behavior, or closeout gates.

## Task Entry

AgentCanon source updates enter only through
`documents/agent-canon/agent-canon-update-route.md`. Its machine-readable transaction and
ToolCall records are owned by `tools/agent_tools/update_lifecycle_contract.py`;
the Decision Sufficiency policy remains owned by
`agents/skills/agent-orchestration.md#Decision Sufficiency Packet`.

For repo-changing work, create or reuse a run bundle only when coordination,
resumption, or the selected workflow requires durable lifecycle evidence. A
bounded owner/path/validation request may use a direct structured handoff and
targeted validation without a bundle. When a packet is selected, follow the
machine-readable output emitted by:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --owner "codex" \
  --workspace-root "$PWD"
```

The emitted workflow, skills, review roles, document packets, wave plan, and
validation route are the task packet for downstream agents.

## Validation

- runtime alignment: `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- structure contract: `python3 tools/agent_tools/repo_structure_contract.py --root . --contract documents/structure/repo-structure-contract.toml`
- responsibility scope: `python3 tools/agent_tools/responsibility_scope.py --root .`
- shared runtime views: `PYTHONPATH=tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check`
- closeout: `python3 tools/agent_tools/task_close.py ...`
