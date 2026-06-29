# PR Queue Cleanup Workflow

<!--
@dependency-start
contract workflow
responsibility Defines the ordered cleanup workflow for linked AgentCanon source PRs and dependent template PRs.
upstream design agent-canon-pr-workflow.md defines AgentCanon source PR and template pin PR gates.
upstream design codex-goals-workflow.md defines goal.md authority and loop-state handling.
upstream design goal-plan-implementation-loop.md defines blocked-goal next-action handling.
downstream design README.md lists this workflow in the maintenance catalog.
downstream implementation ../../tools/ci/check_agent_canon_pr.sh enforces template-side AgentCanon PR gates.
downstream implementation ../../tools/ci/check_agent_canon_latest.sh enforces AgentCanon freshness gates.
downstream implementation ../../tools/agent_tools/check_convention_compliance.py validates PR Essence queue markers.
@dependency-end
-->

Use this workflow when an AgentCanon source PR and one or more template /
derived pin PRs are both open, and the user asks to clean up that PR queue.
The normal example is:

1. AgentCanon source PR is open.
1. Template PR is draft or failing because it pins the source PR head.
1. The next useful action is to merge or replace the source PR, then realign
   the template pin to AgentCanon `main`.

## Reader Map

This workflow owns cleanup order for a named AgentCanon source PR and its
dependent template or derived pin PRs. Read `Authority` before touching the
queue, then follow `Cleanup Order`, stop on any `Stop Conditions`, and use
`Goal Integration` only when `goal.md` is part of the queue state. The boundary
is bounded PR-queue maintenance: this document does not grant branch deletion,
review dismissal, bypass, force-merge, or unrelated PR mutation authority.

## Authority

PR queue cleanup is more bounded than general PR mutation authority.
The current user request must name the PR queue, or a tracked maintainer policy
must authorize this exact queue. A generic statement that `gh` works is not
enough.

For the named queue only, the cleanup operator may:

- inspect PRs, checks, reviews, and mergeability;
- update PR bodies or comments with evidence;
- merge the AgentCanon source PR when it is mergeable and required checks are
  passing or absent;
- update the dependent template / derived pin PR after the source PR lands;
- mark the dependent PR ready for review only after freshness, sync,
  dependency, PR-template, and CI gates pass;
- merge the dependent PR only when the current request explicitly asks to clear
  that PR and all required gates pass.

Do not delete branches, dismiss reviews, bypass failing checks, or force merge
as part of default cleanup.

## Cleanup Order

1. Snapshot the queue.
   - `gh pr view <source-pr> --json state,isDraft,mergeable,headRefOid,baseRefOid,statusCheckRollup,reviews,comments`
   - `gh pr view <dependent-pr> --json state,isDraft,mergeable,headRefOid,baseRefOid,statusCheckRollup,reviews,comments`
   - `gh pr checks <pr> --watch=false || true`
1. If the source PR still needs a small workflow/documentation repair, make that
   repair in the source branch first and rerun source validation.
1. Merge the AgentCanon source PR only when:
   - it is open;
   - it is not draft;
   - mergeability is `MERGEABLE`;
   - no review requests block it;
   - required checks pass or no checks are configured for that repository;
   - the PR body contains `PR Essence`, validation evidence, and GitHub
     automation evidence when applicable.
1. After source merge, update the template / derived repo:
   - fetch AgentCanon `main`;
   - run `make agent-canon-ensure-latest`;
   - run `bash tools/sync_agent_canon.sh link-root`;
   - run `bash tools/sync_agent_canon.sh check`;
   - commit and push the template pin / root-view update.
1. Validate the dependent PR:
   - `python3 tools/ci/check_github_workflows.py`;
   - `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`;
   - task-focused tests;
   - `make agent-canon-pr-check`;
   - `make ci`.
1. Update the dependent PR body with:
   - `PR Essence`: problem / user request, design intent, canonical owner,
     behavior or contract delta, and evidence route;
   - AgentCanon source PR URL and merge SHA;
   - template pin SHA;
   - validation pass lines or exact blockers;
   - goal loop status;
   - GitHub Automation Output fields when relevant.
1. Mark ready or merge only after all required gates pass. If any gate fails,
   keep the dependent PR draft or blocked and record the exact next action.

## Stop Conditions

Stop and update the PR body, issue, run bundle, or `goal.md` instead of
continuing when:

- the source PR is not mergeable;
- required checks fail;
- reviews request changes;
- `make agent-canon-ensure-latest` cannot align to AgentCanon `main`;
- `make agent-canon-pr-check` or `make ci` fails for a non-expected reason;
- a new source change would be needed outside the named PR queue.

## Goal Integration

When `goal.md` was blocked on the source PR, update it after each queue step:

- after source merge, mark the source PR backlog item complete;
- after template pin realignment, mark the freshness item complete;
- after dependent validation passes, mark the validation items complete;
- only set `goal_status: achieved` when `goal_loop.py status` reports
  `NEXT_ACTION=close_goal_loop`.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
