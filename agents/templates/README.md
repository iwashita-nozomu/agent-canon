<!--
@dependency-start
contract template
responsibility Documents reusable run artifact templates for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract.
downstream implementation ../../tools/agent_tools/agent_team.py renders templates and partials.
@dependency-end
-->

# Agent Templates

`agents/templates/` contains source templates for run-bundle artifacts.
`tools/agent_tools/agent_team.py` renders these files into
`reports/agents/<run-id>/`.

## Partials

Reusable sections live under `agents/templates/_partials/`. A template includes
a partial with this marker:

```text
{{>partial_name}}
```

The renderer expands partials before replacing run variables such as
`{{RUN_ID}}`, `{{TASK}}`, `{{OWNER}}`, and `{{CREATED_AT}}`. Partial dependency
manifest blocks are stripped during expansion so generated run artifacts keep
only the top-level artifact manifest.

Use partials only for repeated structure whose generated meaning must stay the
same across artifacts, such as common findings tables or decision sections.
Do not use partials to hide role-specific review focus, required evidence, or
approval criteria.
