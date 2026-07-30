---
name: agent-canon-update
description: Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates.
---
<!--
@dependency-start
contract skill
responsibility Documents AgentCanon Update for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/agent-canon-update.md human-facing skill canon
upstream design ../../../documents/agent-canon/agent-canon-update-route.md canonical AgentCanon update route
upstream design ../../../documents/rule/dependency-module-changes.md generic dependency module change contract
upstream design ../../../documents/agent-canon/agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
upstream design ../../../agents/skills/refactor-loop.md shared-structure refactor execution order
upstream implementation ../../../tools/update_agent_canon.sh high-level AgentCanon update wrapper
upstream implementation ../../../tools/sync_agent_canon.sh root-view and submodule sync helper
upstream implementation ../../../tools/agent_tools/agent_canon_preflight.py blocks unsafe task-entry updates
@dependency-end
-->

# AgentCanon Update

## Reader Map

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
  defined only by the [`AgentCanon parent state decision table`](../../../documents/rule/dependency-module-changes.md#agentcanon-parent-state-decision-table).
  `latest` の更新対象 branch 引数を topic slug に転用しません。
  Under that decision table, a dirty vendor checkout is a refusal condition
  when it is not the intended source working branch; do not preserve or resume
  that state. For parent pin/root projection, only a clean vendor pin projection
  is eligible, while a differing requested topic may use the managed workspace
  clone only through the table's topic-identity rule.
- Standalone local source-branch publication follows the canonical transport
  contract in `documents/tools/github_publish.md`: verified remote identity/
  permission, named branch, captured local identity, exact SHA ref push, remote
  readback, and local invariance. It does not generate G1/G2/G3; packet-bound
  push and PR operations retain the sealed publication requirements. CI
  fresh-clone fixtures are not publication evidence.

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-update --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->


1. Read the `AgentCanon parent state decision table` in
   `documents/rule/dependency-module-changes.md`, then
   `agents/skills/agent-canon-update.md`.
1. Read `documents/agent-canon/agent-canon-update-route.md` and
   `documents/agent-canon/agent-canon-parent-repo-latest-checklist.md`.
1. Classify the repo as standalone AgentCanon, parent submodule repo, or legacy
   compatibility repo before running update commands.
1. Before any branch, tag, PR, merge, or pin mutation, record source
   `origin/main` commit/tree and clean status, parent `origin/main` gitlink and
   clean status, target tree, selected merge strategy, and selected remote.
   Do not rebase, alter unrelated history, or preserve internal commit ids by
   ancestry engineering when reviewed final-tree identity is the contract.
1. In parent repos, classify the AgentCanon projection surface using the rule
   decision table:
   `vendor/agent-canon/`, the parent gitlink, `.gitmodules`, and AgentCanon-owned
   root views. If the parent vendor state is corrupt、書込先が誤っている、または
   mismatch の場合は、restore/逆パッチで旧状態へ戻さず `origin/main` からの
   clean checkout 再構築に切替え、意図した差分のみを再 materialize して再PR化します。
   別 topic dirty checkout は、requested topic identity が named current branch
   と異なる場合だけ `workspace/<topic-slug>/agent-canon` フォールバックを使用。
   `parent` 側が `main` のみの checkout ではまず `checkout_or_create_topic_branch_from_main`
   の next action とし、同ブランチを編集 source route の開始点にしません。
1. Before the high-level update runs, task-start preflight fails closed when an
   exact `reports/agent-eval-runs/<run-id>/<producer>.stdout.txt` or
   `.stderr.txt` capture remains tracked, untracked, or ignored. Preserve the
   capture, sync and verify the eval archive, write its bounded summary, delete
   the transient explicitly, and rerun preflight. Ordinary unrelated parent
   dirt remains allowed.
1. Prefer the high-level parent projection route for clean pins:

Run `make agent-canon-update-plan` first. If it reports an update, request
current-task user approval and rerun
`AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:<sha256-of-exact-authorization-evidence-bytes> make agent-canon-ensure-latest`
with all four inline Git authority/reason fields in the same command segment.

1. If `vendor/agent-canon/` contains local AgentCanon source commits or source
   dirty state that is not the intended source working branch, stop. Do not invoke
   `merge-main-into-current*`, stash, preserve, or resume that vendor state.
   Run the generic dependency-module tool from the parent with owner evidence:
   `prepare --topic <topic> --module vendor/agent-canon --branch <source-branch>`.
   Make the source branch/PR in `workspace/<topic-slug>/agent-canon` only when the
   parent vendor is occupied by another topic's dirty state and the requested
   topic differs from the named current branch; otherwise follow the decision
   table's typed stop or edit the parent vendor branch directly. Standalone
   source clones retain the source-mode merge/publication route.

   Reuse the current AgentCanon source branch / PR when it already owns the
   shared-canon work. Do not create a fresh branch for a bounded follow-up,
   mid-task user instruction, dirty-state avoidance, or checklist addendum.
   Record a reason before requesting approval for any new branch. A reason or
   workflow route does not authorize creation: current-task user approval and
   all four same-command authority/reason values are required.

1. After a safe update or PR merge, project the accepted source tree into parent
   root views exactly once, then repair and verify root views:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh link-root
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
```

   Treat this as the mandatory `agentcanon_structure_followup` gate whenever
   AgentCanon source, the parent submodule pin, `.gitmodules`, root runtime
   views, shared root-copy surfaces, or parent root sync state changed. Record
   `agentcanon_structure_followup=required` before the commands and
   `agentcanon_structure_followup=pass` only after the sync check passes.
   Template / derived parent roots must run this gate from the parent root after
   AgentCanon source changes are integrated, or while preparing the parent
   pin/root-view PR.

## Final-Topology Adjudication

Follow the canonical
`agents/skills/agent-canon-update.md#Final-Topology-Adjudication` section; this
runtime mirror does not restate the adjudication rule.

1. Check and apply parent update TODOs before unrelated work:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py status
python3 tools/agent_tools/agent_canon_update_todos.py plan --write
```

1. Use `$agent-update-branch` only for parent-repo `canon-pin` update branches.
   AgentCanon source edits use a standalone AgentCanon branch and PR. Reuse the
   current parent branch if it already owns the same pin/update lane.
1. Close out with update route, dirty-surface classification, submodule pin or
   AgentCanon commit, PR URL if any, root-view check, TODO status, and selected
   validation evidence.
