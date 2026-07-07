---
name: pr-processing
description: "Use when processing GitHub pull requests or issue queues: inventory open PRs, preserve PR Essence in bodies and run bundles, resolve conflicts, order merges, update branch protection evidence, merge only with authority, triage stale issues, and sync AgentCanon source PRs with parent pin PRs."
---
<!--
@dependency-start
contract skill
responsibility Documents PR Processing runtime skill for this repository.
upstream design ../../../agents/skills/pr-processing.md documents the human-facing workflow
upstream design ../../../agents/workflows/pr-queue-cleanup-workflow.md defines AgentCanon source and parent pin queue cleanup
upstream design ../../../agents/workflows/agent-canon-pr-workflow.md defines AgentCanon source PR gates
upstream design ../../../documents/agent-canon-update-route.md defines source PR versus parent pin update routing
upstream design ../../../agents/skills/result-artifact-writeout.md defines run-local result artifact writeout
upstream implementation ../../../tools/agent_tools/bootstrap_agent_run.py creates run-local report bundles
upstream implementation ../../../tools/agent_tools/github_publish.py publishes PRs and writes summary artifacts
downstream implementation ../../../tools/agent_tools/check_convention_compliance.py validates PR Essence runtime skill markers
@dependency-end
-->

# PR Processing

## Reader Map

- Purpose: runtime skill for GitHub PR and issue queue processing, including
  inventory, conflict handling, ordered merges, and stale issue triage.
- Use When: summarizing, triaging, reviewing, merging, or preserving PR/issue
  evidence through the GitHub workflow.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/pr-processing.md` route before using GitHub commands.
- Boundary: merge authority and branch protection evidence must come from the
  PR-processing route, not ad hoc local state.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill pr-processing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/pr-processing.md`.
1. If AgentCanon source PRs or parent pin PRs are involved, also read
   `agents/workflows/pr-queue-cleanup-workflow.md` and
   `agents/workflows/agent-canon-pr-workflow.md`.
1. Before creating or updating a PR, identify the active run bundle. If none
   exists, run `python3 tools/agent_tools/bootstrap_agent_run.py --task "<task>"
   --owner codex --workspace-root "$PWD"` and record `RUN_ID`, `REPORT_DIR`,
   and `AGENT_CANON_PREFLIGHT_*` lines in `work_log.md` or
   `workflow_monitoring.md`.
1. Keep PR publication artifacts inside the run bundle:
   - write the reviewed PR body to `reports/agents/<run-id>/pr_body.md`;
   - include a `PR Essence` section in `pr_body.md` with problem / user
     request, design intent, canonical owner, behavior or contract delta, and
     evidence route;
   - pass `--summary-out reports/agents/<run-id>/github_publish.json` to
     `github_publish.py publish-pr`;
   - record PR number / URL, branch, head SHA, authority decision, checks
     summary, issue actions, and blockers in `work_log.md` or a run-local
     `pr_processing_log.md`.
1. Fix the authority boundary before mutation:
   - inspecting PRs, checks, comments, reviews, and issues is allowed when the
     task asks for PR / Issue processing;
   - merging, closing, marking ready, deleting branches, or dismissing reviews
     needs current user authority or tracked maintainer policy for that action;
   - never bypass failed checks, branch protection, requested reviews, or draft
     state.
1. Snapshot the queue before editing:
   - `gh pr list --state open --json number,title,headRefName,baseRefName,isDraft,mergeable,reviewDecision,statusCheckRollup,updatedAt`
   - `gh issue list --state open --json number,title,labels,updatedAt,url`
   - for each candidate PR, inspect `gh pr view` and `gh pr checks`.
1. Classify each PR as `ready`, `behind`, `conflicting`, `draft`,
   `checks-failing`, `review-blocked`, `stale`, or `dependent-pin`.
1. For `checks-failing` or validation failure after branch repair, record
   `failing_contract`, `observation_level`, `cause_classification`,
   `intent_preservation`, and `evidence` in the PR log or run bundle before
   pass-only simplification, revert, intended behavior/test deletion, oracle
   weakening, or validation downscope. Preserve the PR Essence for
   implementation bugs; route oracle/spec, fixture/environment/stale artifact,
   unrelated, and approved-design/user-request conflicts to owner repair,
   residual, or escalation before the merge gate.
1. Treat requested-change or rejecting reviews as branch repair signals, not
   authority to revert the PR's user request or PR Essence. Repair the head
   branch so the original design intent remains covered, or record withdrawal,
   supersession, owner-boundary, unsafe-replacement, or escalation evidence
   before discarding a slice.
1. Before marking a PR ready, merging it, or syncing a dependent parent pin,
   perform diff intake against the target base. Compare the head diff with the
   PR Essence, user request, canonical owner, and validation route; repair
   missing, stale, unintended, or over-broad diff entries on the PR head branch
   before the merge gate. Record the diff intake decision and repaired paths in
   the PR log or run bundle.
1. Plan merge order from dependency and conflict evidence:
   - source / library / AgentCanon PRs before parent pin or template PRs;
   - PRs touching shared root/runtime surfaces before dependent docs-only PRs;
   - conflicting PRs after the branch they conflict with has landed, unless the
     conflict repair is independent.
1. Resolve conflicts on the PR head branch, then rerun validation that covers
   the touched surface. Do not resolve conflicts by discarding user
   changes or force-pushing without explicit authority.
   Conflict repair is semantic integration, not "ours/theirs" selection: inspect
   the merge base, current branch intent, incoming branch intent, owning
   contract, and validation surface; record which clauses from each side are
   preserved, rewritten, or intentionally rejected before marking the conflict
   resolved.
1. Before merging a PR, require:
   - open, non-draft PR;
   - mergeable state;
   - required checks passing;
   - no blocking review request or requested-change review;
   - PR body, comment, or run bundle includes `PR Essence`, validation
     evidence, and any automation authority lines required by the repo.
   - PR body, comment, or run bundle shows that the
     `documents/BRANCH_SCOPE.md` scope-split contract was applied: the PR is one
     review unit, or it has a scope table plus the split/group decision for
     every slice.
1. For AgentCanon source PRs, merge source first, then update parent repos with
   `make agent-canon-ensure-latest`, `bash tools/sync_agent_canon.sh link-root`,
   diff intake / repair, and the parent PR gate.
1. Process issues with the same evidence rule:
   - close only resolved, duplicate, obsolete, or intentionally not-planned
     issues with a concrete PR, commit, or policy reference;
   - update active issues with residual work and owner;
   - keep stale issues open when evidence is insufficient.
1. Close out with a table of PR actions, issue actions, merge SHAs, remaining
   blockers, validation commands, final open PR / Issue counts, and the run
   bundle paths that contain the bootstrap log, PR body, publish summary, and
   check evidence.
