---
name: change-review
description: Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions.
---
<!--
@dependency-start
contract skill
responsibility Documents Change Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../issues/README.md durable issue and GitHub mirror policy
@dependency-end
-->


# Change Review

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill change-review --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/change-review.md`.
1. Review the actual diff first.
1. Report findings before summaries.
1. Prioritize:
   - behavioral regressions
   - missing validation
   - missing tests
   - stale documentation
1. For Python diffs that touch classes, dataclasses, `Protocol`, inheritance, public APIs, type boundaries, or dependency direction, add `python-review` and `$oop-readability-check`; require an OOP readability report with SOLID principle signal evidence plus `python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>` path coverage.
1. Run `bash tools/agent_tools/run_repo_dependency_review.sh` against the full repository during checkpoint and final review; changed-file dependency checks alone are not enough.
1. Separate `fix now` from `follow-up`.
1. For fixes made after validation failure, check that the diff records
   `failing_contract`, `observation_level`, `cause_classification`,
   `intent_preservation`, and `evidence` before any pass-only simplification.
   Use `intent_preservation` for the same-intent repair or escalation route before
   revert, intended behavior/test deletion, oracle weakening, or validation
   downscope. Findings must preserve approved intent or route oracle/spec,
   fixture/environment/stale artifact, unrelated, and approved-design/user-
   request conflicts to the proper repair, residual, or escalation path.
1. A `revise`, `required_change`, rejected diff, or requested-change review is
   not authority to roll back the user request. Findings must name the same
   user-request or design intent to preserve, then require repair, redesign, or
   escalation. Recommend revert / discard only with evidence that the clause was
   withdrawn or superseded, outside the canonical owner, or unsafe and replaced
   by an intent-preserving alternative.
1. Add `issue_route` to every `fix now` and `follow-up` finding: use
   `run_local_resolution:<evidence>` for findings closed in the current review
   loop, `existing_issue:<path-or-url>` for known durable findings,
   `new_local_issue:<issues/open/AC-YYYYMMDD-slug.md>` for durable local records,
   and `github_mirror:<issue_sync.py command-or-url>` for operator-facing
   GitHub Issue visibility.
1. Use `issues/README.md` for required issue fields and
   `python3 tools/agent_tools/issue_sync.py --root .` for local validation or
   GitHub mirror planning.
1. Use `documents/REVIEW_PROCESS.md` for repo review expectations.
   In template or derived repo roots, `documents/...` is a logical AgentCanon
   path: resolve it under `vendor/agent-canon/documents/` unless
   `documents/README.md` lists the path as a template-owned active contract.
