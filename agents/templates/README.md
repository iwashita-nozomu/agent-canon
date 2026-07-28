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

## Active Design Packet Projection

`agents_config.json#artifacts.active_design_packet` defines one neutral closed
`waterfall.design_packet.v1` record. Its selected design, technical review,
and document-flow review paths plus the clause registry and four typed entries
are projected into one run bundle and persisted at
`team_manifest.yaml#run.active_design_packet`. The companion
`active_design_packet_reference_projection` records the selected packet SHA,
source-byte identities, dependency endpoints, selected outputs, and reviewer
artifact identities. The four entries are projected into the matching sections
of `design_brief.md`;
`design_review.md` reviews the exact artifact identity and all four entries;
`document_flow_review.md` reviews the source packet and reader-visible side
effects; `change_review.md` and `final_review.md` verify the integrated trace.

Templates do not parse or infer packet authority. `create_run_bundle` resolves
the packet, validates its closed field set, relative artifact paths, typed graph
references, and materialized source/dependency identity, renders all selected
templates in memory, and publishes one complete bundle for task-start,
bootstrap, and document-start producers. Review templates are authorization
records only and cannot write or advance the active run pointer.
