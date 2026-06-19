---
name: change-review
description: Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions.
---
<!--
@dependency-start
contract skill
responsibility Documents Change Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
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
1. Run `bash tools/agent_tools/run_repo_dependency_review.sh` against the full repository during checkpoint and final review; changed-file dependency checks alone are not enough.
1. Separate `fix now` from `follow-up`.
1. Use `documents/REVIEW_PROCESS.md` for repo review expectations.
   In template or derived repo roots, `documents/...` is a logical AgentCanon
   path: resolve it under `vendor/agent-canon/documents/` unless
   `documents/README.md` lists the path as a template-owned active contract.
