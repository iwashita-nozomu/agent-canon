# AgentCanon Update Skill
<!--
@dependency-start
contract skill
responsibility Documents AgentCanon Update Skill for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/agent-canon/agent-canon-update-route.md canonical AgentCanon update route
upstream design ../../documents/agent-canon/source-publication-parent-handoff.md owns source packet handoff to the parent namespace
upstream design ../../documents/rule/dependency-module-changes.md generic dependency module change contract
upstream design ./agent-orchestration.md owns Decision Sufficiency policy
upstream design ./structure-refactor.md owns final-structure-first scope formation
upstream design ./refactor-loop.md owns shared-structure refactor execution order
upstream implementation ../../tools/update_agent_canon.sh high-level AgentCanon update wrapper
upstream implementation ../../tools/sync_agent_canon.sh root-view and submodule sync helper
upstream implementation ../../tools/agent_tools/skill_tool_commands.py resolves optional parent Make aliases without evaluating Make
upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns transaction, queue, frontier, and cleanup records
upstream implementation ../../tools/agent_tools/source_projection_handoff.py materializes the sole cross-namespace packet
downstream design ./agent-update-branch.md separates parent update branch lanes from source AgentCanon PR work
downstream implementation ../../tests/agent_tools/test_skill_tool_commands_update_entrypoint.py live command-packet regression contract
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

  In a parent submodule, the stage-0 mode-`160000` gitlink is the pin authority.
  A clean detached checkout whose `HEAD` equals that pin is an accepted
  `main` attach candidate; local `main` absent/equal/ancestor states use only
  create/switch or `merge --ff-only`. Dirty, non-pin, descendant/divergent,
  topic, worktree-collision, and remote/tracking readback states remain typed
  holds. Plan resolves remote S1/S2 through a parent-owned disposable probe
  with source-object alternates; source refs, objects, and `FETCH_HEAD` remain
  bytewise unchanged. Missing local `origin/main` is an attach prerequisite,
  while unrelated or rewound tracking is a typed hold. `latest` prints the complete plan stream and returns its plan status
  before dependency-frontier lookup, so a remote failure cannot be masked by
  frontier handling. No reset, stash, force ref update, or clone fallback is
  introduced by detached attachment. Attach fetch/upstream/readback failures
  use an old-value-guarded transaction rollback with explicit rollback evidence.

## Use When

- The user asks to update, latest, refresh, or sync AgentCanon.
- `make agent-canon-update-plan`, `make agent-canon-latest`, and
  `make agent-canon-ensure-latest` are optional parent-owned aliases. The runtime
  command packet keeps an alias only when the selected parent Makefile declares
  that exact literal target; otherwise it emits the source-root resolver route
  to `tools/update_agent_canon.sh`.
- `tools/update_agent_canon.sh` or `tools/sync_agent_canon.sh` is the canonical
  owner entrypoint independently of parent Makefile shape.
- A parent repo has AgentCanon submodule pin drift, root-view drift, safe
  dirty checkout state, or pending `.agent-canon/update-state.toml` TODOs.
- `vendor/agent-canon/` contains the named topic branch for current source work,
  including collision-free local state, or another topic's state requires the
  generic repository topic clone lifecycle.
  A `main` checkout is the topic-creation starting point, not a source-edit owner.

## Core References

- `documents/agent-canon/agent-canon-update-route.md`
- `documents/agent-canon/source-publication-parent-handoff.md`
- `documents/runtime/SHARED_RUNTIME_SURFACES.md`
- `agents/skills/structure-refactor.md#Pre-Task Structure Repair Contract`
- `agents/skills/refactor-loop.md#共有構造 refactor の実行順`
- `tools/update_agent_canon.sh`
- `tools/agent_tools/skill_tool_commands.py`
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
1. The source publication owner materializes exactly one typed
   source-publication packet and hands that packet, never derived receipts, to
   the parent-owned `.agent-canon/update-lifecycle` namespace. The canonical
   `latest` front door binds all mutable lifecycle outputs to the explicit
   parent root, validates remote-main publication commit/tree, and derives the
   QueueReceipt, `#388 -> #389 -> current transaction` frontier, marker, and G4
   there. This source-root-to-parent-root route also repairs a parent whose pin
   predates the fix, without staging the gitlink. Manual gitlink fast-forward,
   receipt fabrication/copy, and a second updater remain prohibited. See
   `documents/agent-canon/source-publication-parent-handoff.md`.
1. `PullRequestLifecycle` carries immutable base/head repository, owner, ref,
   fork/contributor, permission, Essence, review, and contributor-diff state.
   Unknown or false push permission is a typed refusal rather than assumed
   authority.
1. Standalone `github_publish.py push` is reversible branch transport. Without
   a packet it verifies remote identity/permission, requires a named current
   branch, captures local `HEAD`/tree, pushes the exact SHA refspec, reads back
   the remote SHA, and requires local identity invariance across push. It does
   not generate or claim G1/G2/G3 or PR lifecycle evidence. A supplied sealed
   packet may add candidate matching as optional enrichment. PR create/update
   and check readback consume the current user task, verified
   remote/permission/topology, and exact head/base identities; only merge keeps
   the G3 authority requirement.
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

Generate the command packet from the current repository root. The packet treats
`agent-canon-update-plan`, `agent-canon-latest`, and
`agent-canon-ensure-latest` consistently as optional parent-owned Make aliases.
It keeps an alias only when the first default Makefile selected from
`GNUmakefile`, `makefile`, or `Makefile` declares that exact literal target.
The detector reads text only: it does not execute Make, expand variables, load
dynamic target names, or evaluate parse-time functions. Variable-definition
bodies, assignment text, and unevaluated conditional branches are not target
evidence. Any absent, dynamic, conditional, or unreadable alias fails closed to
the canonical owner command; the parent
Makefile is never projected or modified.

The direct plan command is:

```bash
PYTHONPATH=vendor/agent-canon/tools:tools \
  python3 -m agent_tools.agent_canon_source_root exec \
  tools/update_agent_canon.sh plan
```

If the plan reports an update, request current-task user approval and run the
packet's `latest` command with the same inline authority and provenance fields.
Both `agent-canon-latest` and `agent-canon-ensure-latest` fall back to:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> \
AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
AGENT_CANON_DESTRUCTIVE_GIT_REASON=<reason> \
PYTHONPATH=vendor/agent-canon/tools:tools \
  python3 -m agent_tools.agent_canon_source_root exec \
  tools/update_agent_canon.sh latest
```

The source-root resolver, not chat text or parent Makefile shape, decides
standalone versus vendored execution. Existing explicit aliases remain valid;
the fallback is the same owner route rather than a second updater. Add creation
authority/reason only when the route creates a branch or worktree; force-create
or ref-overwrite routes require both authority pairs.

Treat this as the mandatory `agentcanon_structure_followup` gate when this
owner route reports the parent sync trigger is active for active root projection.
Record
`agentcanon_structure_followup=required` before the commands and
`agentcanon_structure_followup=pass` only after the sync check passes.
   Template / derived parent roots must run this gate from the parent root after
   AgentCanon source changes are integrated, or while preparing the parent
   pin/root-view PR.

`make agent-canon-pr-check` keeps this owner boundary: both standalone
AgentCanon and template/derived parents run only shared AgentCanon surfaces.
Derived parents emit `AGENT_CANON_PR_PROJECT_QUALITY=delegated` with owner
`parent_ci`; the workflow checker requires that parent workflows expose the
owner marker and canonical `make ci` command, independent of job name. Project
tests, type checks, and lint are blocking only through that selected parent CI
route. AgentCanon development prompt and accumulated eval producers run only in
the standalone AgentCanon `static-gates` owner; derived shared gates do not
invoke them or evaluate parent-owned documents. Standalone AgentCanon keeps its
existing shared owner and adds no repository-wide project-quality job. The
shared gate does not add a parent-project baseline scanner or invoke
`run_all_checks.sh`.

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh link-root
python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
```

- Purpose: runtime skill for AgentCanon source updates, parent submodule pin
  refreshes, root-view repair, and latest-state checklist work.
- Use When: updating `vendor/agent-canon/`, applying AgentCanon update TODOs,
  or routing local AgentCanon commits through source PRs before parent pins.
- Tool Commands: run this skill's command packet from the current repository
  root. The packet resolves optional parent aliases before execution, then read
  the canonical update-route and parent latest-state documents.
- Boundary: use `dependency-module-change` for source edits. Parent source編集は
  原則 `vendor/agent-canon` の topic-named branch で行い、別 topic の dirty
  親 vendor 状態がある場合のみ `workspace/<topic-slug>/agent-canon` の
  standalone clone に fallback します。Parent pin/root projection は clean
  `main` と staged index gitlink と worktree `HEAD` の一致が pass 条件です。
  `main` は source edit owner ではなく topic 作成の起点です。
  Parent state, requested topic identity, and dirty fallback next actions are
  defined only by the [`AgentCanon parent state decision table`](../../documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table).
  `latest` の更新対象 branch 引数を topic slug に転用しません。
  Parent submodule の stage-0 mode-`160000` gitlink が pin authority です。clean
  detached `HEAD ==` pin は default `main` attach candidate として扱い、
  absent/equal/ancestor の local main は create/switch または
  `merge --ff-only` のみを許可します。dirty、non-pin、descendant/divergent、
  topic、worktree collision、remote/tracking readback failure は typed hold
  とし、`latest` は plan の全診断を出して同じ non-zero を frontier 前に返します。
  plan の remote S1/S2 は parent-owned disposable probe と source object の
  read-only alternates で取得し、source refs、objects、`FETCH_HEAD` を変更しません。
  local `origin/main` の absent は attach prerequisite、unrelated/rewind は mismatch hold
  です。attach の fetch/upstream/readback failure は old-value guard 付き rollback
  と rollback evidence を伴います。rollback または transaction cleanup が失敗した
  ときは typed hold とし、transaction directory を保持して復元済みと報告しません。
  probe cleanup も removal 成功時だけ pass とし、失敗時は probe path/evidence を保持した
  cleanup hold を返します。plan detail は stage-0、remote、tracking、materialization
  の named facts を各 owner から直接出力します。
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
  readback, and local invariance. It does not generate G1/G2/G3; a packet may
  optionally enrich push/PR evidence, while PR create/update and checks consume
  the current task, verified topology/permission, and exact identities. Merge
  alone retains the G3 publication authority. CI fresh-clone fixtures are not
  publication evidence.

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
