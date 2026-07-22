---
name: wiki-publication
description: Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks.
---
<!--
@dependency-start
contract skill
responsibility Documents runtime skill wiring for wiki publication.
upstream design ../../../agents/skills/wiki-publication.md canonical skill contract and workflow.
upstream implementation ../../../tools/agent_tools/wiki_publish.py wiki publication gate tool.
@dependency-end
-->

# Wiki Publication Skill

## Reader Map

- Canonical owner: `agents/skills/wiki-publication.md`.
- Runtime contract: `tools/agent_tools/wiki_publish.py`.

## Tool Command

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill wiki-publication --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/wiki-publication.md`.
2. Run the wiki publication command with explicit `--writer` and `--reviewer` roles,
   source commit binding, and default-branch push intent.
3. Treat missing wiki page state as typed `REMOTE_UNINITIALIZED` and refuse mutation
   before explicit initialization.
4. Always publish to `<repo>.wiki.git` sidecar and never to in-tree `wiki` content.
5. Preserve only narrow, tool-defined validation gates in this route.
