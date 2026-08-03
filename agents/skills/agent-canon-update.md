# AgentCanon Update Skill
<!--
@dependency-start
contract skill
responsibility Documents AgentCanon Update Skill for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/agent-canon/agent-canon-update-route.md canonical AgentCanon update route
upstream design ../../documents/rule/dependency-module-changes.md generic dependency module change contract
upstream design ./agent-orchestration.md owns Decision Sufficiency policy
upstream design ./structure-refactor.md owns final-structure-first scope formation
upstream design ./refactor-loop.md owns shared-structure refactor execution order
upstream implementation ../../tools/update_agent_canon.sh high-level AgentCanon update wrapper
upstream implementation ../../tools/sync_agent_canon.sh root-view and submodule sync helper
upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns transaction, queue, frontier, and cleanup records
downstream design ./agent-update-branch.md separates parent update branch lanes from source AgentCanon PR work
@dependency-end
-->

Use this skill when the task is about bringing AgentCanon itself, a vendored
`vendor/agent-canon` pin, root runtime views, or parent-repo AgentCanon update
TODO state up to date.

## Reader Map

- Purpose: describes the route for updating AgentCanon itself, parent submodule
  pins, shared root views, and AgentCanon update TODOs.
- Use When: the task touches `vendor/agent-canon/`, AgentCanon pins, root view
  repair, or latest-state update checks.
- Section path: Use When identifies triggers; Core References lists owner
  documents; Route contains the operational rules; Closeout Evidence names the
  required validation and PR evidence.
- Boundary: use `dependency-module-change` first when an AgentCanon source edit
  is required. Parent projection passes only with a clean named `main` checkout
  whose worktree `HEAD` equals the staged index gitlink. Source edits and update
  materialization use the intended named topic branch in `vendor/agent-canon`;
  collision-free uncommitted paths remain in place. A managed workspace clone
  is a fallback only when another topic owns the parent vendor state.
  Parent state, requested topic identity, and dirty fallback next actions are
  defined only by the [`AgentCanon parent state decision table`](../../documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table).
  The `cmd_latest` update-target branch is never a topic slug.

## Use When

- The user asks to update, latest, refresh, or sync AgentCanon.
- `make agent-canon-ensure-latest`, `make agent-canon-latest`,
  `tools/update_agent_canon.sh`, or `tools/sync_agent_canon.sh` is the likely
  entrypoint.
- A parent repo has AgentCanon submodule pin drift, root-view drift, safe
  dirty checkout state, or pending `.agent-canon/update-state.toml` TODOs.
- `vendor/agent-canon/` contains the named topic branch for current source work,
  including collision-free local state, or another topic's state requires the
  managed workspace fallback.
  A `main` checkout is the topic-creation starting point, not a source-edit owner.

## Core References

- `documents/agent-canon/agent-canon-update-route.md`
- `documents/runtime/SHARED_RUNTIME_SURFACES.md`
- `agents/skills/structure-refactor.md#Pre-Task Structure Repair Contract`
- `agents/skills/refactor-loop.md#共有構造 refactor の実行順`
- `tools/update_agent_canon.sh`
- `PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh`
- `agents/skills/agent-update-branch.md`

## Route

1. Consume the semantic decision-sufficiency record from
   `agents/skills/agent-orchestration.md#Decision Sufficiency Packet`: owner,
   replaceable unit, implementation mechanism, validation route, and unresolved
   branches that can change them. A durable packet reference is conditional on
   coordination or resumption; this skill does not create a second form.
1. Consume the final-structure-first owner in
   `agents/skills/structure-refactor.md#Pre-Task Structure Repair Contract` and
   fix the target structure, owner graph, and namespace. Evidence reads are
   permitted only when the imported Decision Sufficiency packet names the
   downstream structure/owner decision they can change.
1. Read the `AgentCanon parent state decision table` in
   `documents/rule/dependency-module-changes.md` first. Accept exactly two
   repository shapes: the standalone AgentCanon source namespace, or a parent
   consumer with the `vendor/agent-canon` submodule. Legacy subtree/snapshot
   placement is rejected; it is not a compatibility route.
1. Enter parent source edits through the intended named topic branch in the current
   `vendor/agent-canon` checkout. A parent checkout on `main` stops at the topic
   creation action; it is not a source-edit owner. If another topic has dirty
   state in that vendor checkout, apply the decision table's requested-topic
   identity rule: a missing identity stops, a matching named current branch
   materializes the current vendor topic, and only a differing topic uses the
   managed workspace clone fallback.
   Parent pin/root projection resumes only from clean `main` with the staged
   gitlink matching worktree `HEAD`. In standalone mode
   `tools/update_agent_canon.sh` owns source-main rebind and branch publication.
   Within the intended named branch, apply the exact local-state acceptance
   predicate from
   `documents/agent-canon/agent-canon-update-route.md#update-materialization-acceptance`.
   Named branch and ahead/diverged history are state evidence.
   Dirty state remains evidence, not a blocker. Non-colliding local materialized
   paths stay in place, including ignored untracked paths, while committed
   differences use the normal merge and review flow. The exact update write set
   is the path diff from `HEAD` to Git's virtual merge result tree.
   Materialization blocks only an independently typed merge conflict or an
   unpreservable materialization collision; the skill does not derive a second
   rename heuristic.
   Every mutating wrapper or low-level sync invocation must carry the validated
   branch/destructive authority fields and
   `AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<64 lowercase hex>` in the same
   command segment. The digest is the SHA-256 of the exact bytes of the user
   request record or canonical workflow authorization packet; no fallback
   identity or authority input is accepted.
1. Before any branch, tag, PR, merge, or pin mutation, record the authoritative
   integration identities: source `origin/main` commit/tree and clean status,
   parent `origin/main` gitlink and clean status, target tree, selected merge
   strategy, and selected remote. Fetch is readback evidence; do not rebase or
   alter unrelated history, and do not engineer ancestry to preserve internal
   commit ids when reviewed final-tree identity is the contract.
1. Once the target graph is coherent, immediately implement the complete source
   mechanisms and generated views. `UpdateTransaction` and `Snapshot` preserve
   resumable state; preparation/generation labels are internal state and do not
   create an update-specific preflight, micro-step gate, or review wave.
1. Validate the completed transaction, then continue in this order:
   `G1 -> G2 -> SourceMainRebindReceipt ->
   CandidateFreezeReceipt -> CandidateReviewReceipt -> CandidateCasReceipt/G3
   -> PullRequestLifecycle -> merge -> PublicationReadbackReceipt ->
   source-main readback -> QueueReceipt -> DependencyFrontier acceptance -> parent
   projection/G4 -> remote readback/G5`.
   `CandidateCasReceipt` derives its base only from the preceding
   `SourceMainRebindReceipt` new origin/main commit/tree. Publication retains
   the candidate head and authoritative merge commit/tree as distinct
   identities.
1. A passed checkpoint with the same candidate/tree/input/tool version returns
   its receipt with replay timing and does not rerun its invariant. Changed
   identity creates an explicit successor and leaves the old transaction
   immutable.
1. The source clone enqueues once under
   `.agent-canon/update-lifecycle/projection-queue`. The ordered predecessor
   oracle is `#388 -> #389 -> current transaction`. Parent pin/root sync cannot
   start from a pending or failed frontier. After publication readback, the
   state machine writes the typed source-publication packet and the existing
   `latest` entry advances queue/frontier/G4 internally; no queue CLI alias is
   exposed.
1. `PullRequestLifecycle` carries immutable base/head repository, owner, ref,
   fork/contributor, permission, Essence, review, and contributor-diff state.
   Unknown or false push permission is a typed refusal rather than assumed
   authority.
1. Standalone `github_publish.py push` is reversible branch transport. Without
   a packet it verifies remote identity/permission, requires a named current
   branch, captures local `HEAD`/tree, pushes the exact SHA refspec, reads back
   the remote SHA, and requires local identity invariance across push. It does
   not generate or claim G1/G2/G3 or PR lifecycle evidence. A supplied sealed
   packet may add candidate matching; `publish-pr`, PR mutation, and merge keep
   their sealed packet/G1/G2/G3 requirements.
1. After G5, materialize `DurableHandback`, close every declared descendant,
   release every reservation, prove task-owned cleanup and unchanged unknown
   shared state, pass G6, and execute only the canonical `close_agent` ToolCall
   token. Cleanup before readback and prose close checklists are invalid.
1. Parent root projection uses the accepted frontier exactly once after source
   publication. Parent-owned
   validation, remote CI, merge, and readback follow there; they do not rerun
   source correctness, generated completeness, or source PR CAS.

## Final-Topology Adjudication

Apply the full adjudication rule from
`agents/skills/agent-orchestration.md#Review Activation And Adjudication` after
final validation topology selection. For this update route, G1 source
correctness and G4 parent projection remain separate; G4 does not import
failures unreachable outside its final topology.

## Closeout Evidence

Record:

- update route decision and dirty-surface classification
- semantic decision-sufficiency record; durable packet reference only when
  coordination or resumption required it
- exact `RecordBinding`, timing, first-missing checkpoint, G1-G6 evidence IDs,
  source-main rebind/freeze/review/CAS/readback receipt chain
- immutable `PullRequestLifecycle`, source PR/merge/main readback, accepted
  QueueReceipt, and pending/accepted DependencyFrontier records
- no parent projection evidence while pending; accepted-frontier evidence before
  parent pin/root projection
- DurableHandback, closed descendant receipts, released reservations,
  CleanupProof, G6, and terminal `CloseAgentToolCall`
- remote readback before task-owned temp/cache deletion and evidence that
  unknown shared state is unchanged

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

Run `make agent-canon-update-plan` first. If it reports an update, request
current-task user approval and rerun
`AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> make agent-canon-ensure-latest`
with all four inline Git authority/reason fields in the same command segment.

Treat this as the mandatory `agentcanon_structure_followup` gate when this
owner route reports the parent sync trigger is active for source, submodule pin,
root runtime views, root-copy surfaces, or sync-control surfaces. Record
`agentcanon_structure_followup=required` before the commands and
`agentcanon_structure_followup=pass` only after the sync check passes.
   Template / derived parent roots must run this gate from the parent root after
   AgentCanon source changes are integrated, or while preparing the parent
   pin/root-view PR.

`make agent-canon-pr-check` keeps this owner boundary: standalone AgentCanon
source runs the full `run_all_checks.sh` route, while template/derived parents
emit `AGENT_CANON_PR_PROJECT_QUALITY=delegated` with owner `parent_ci` and leave
project tests, type checks, and lint to the selected parent CI job. The shared
gate does not add a parent-project baseline scanner.

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh link-root
python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
```

- Purpose: runtime skill for AgentCanon source updates, parent submodule pin
  refreshes, root-view repair, and latest-state checklist work.
- Use When: updating `vendor/agent-canon/`, applying AgentCanon update TODOs,
  or routing local AgentCanon commits through source PRs before parent pins.
- Tool Commands: run this skill's command packet, then read the canonical
  update-route and parent latest-state documents.
- Boundary: use `dependency-module-change` for source edits. Parent source編集は
  原則 `vendor/agent-canon` の topic-named branch で行い、別 topic の dirty
  親 vendor 状態がある場合のみ `workspace/<topic-slug>/agent-canon` の
  standalone clone に fallback します。Parent pin/root projection は clean
  `main` と staged index gitlink と worktree `HEAD` の一致が pass 条件です。
  `main` は source edit owner ではなく topic 作成の起点です。
  Parent state, requested topic identity, and dirty fallback next actions are
  defined only by the [`AgentCanon parent state decision table`](../../documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table).
  `latest` の更新対象 branch 引数を topic slug に転用しません。
  Under that decision table, a vendor checkout owned by another topic is a
  refusal condition for this topic. Within the intended source branch, use the
  canonical update materialization predicate: dirty state remains evidence, not
  a blocker, and non-colliding local materialized paths remain in place. Block
  only an independently typed merge conflict or an unpreservable materialization
  collision with the exact update write set. For parent pin/root projection,
  only a clean vendor pin projection is eligible, while a differing requested
  topic may use the managed workspace clone only through the table's
  topic-identity rule.
- Standalone local source-branch publication follows the canonical transport
  contract in `documents/tools/github_publish.md`: verified remote identity/
  permission, named branch, captured local identity, exact SHA ref push, remote
  readback, and local invariance. It does not generate G1/G2/G3; packet-bound
  push and PR operations retain the sealed publication requirements. CI
  fresh-clone fixtures are not publication evidence.

1. If `vendor/agent-canon/` belongs to a source branch other than the intended
   source working branch, stop and leave that state unchanged.
   Run the generic dependency-module tool from the parent with owner evidence:
   `prepare --topic <topic> --module vendor/agent-canon --branch <source-branch>`.
   Make the source branch/PR in `workspace/<topic-slug>/agent-canon` only when the
   parent vendor is occupied by another topic's dirty state and the requested
   topic differs from the named current branch; otherwise follow the decision
   table's typed stop or edit the parent vendor branch directly. On the intended
   named branch, `merge-main-into-current` blocks only the collision/conflict
   predicate owned by the canonical update route. Standalone source clones
   retain the source-mode merge/publication route.

1. Use `$agent-update-branch` only for parent-repo `canon-pin` update branches.
   AgentCanon source edits use a standalone AgentCanon branch and PR. Reuse the
   current parent branch if it already owns the same pin/update lane.
1. Close out with update route, dirty-surface classification, submodule pin or
   AgentCanon commit, PR URL if any, root-view check, TODO status, and selected
   validation evidence.

```bash
python3 tools/agent_tools/agent_canon_update_todos.py status
python3 tools/agent_tools/agent_canon_update_todos.py plan --write
```

1. Check and apply parent update TODOs before unrelated work:
