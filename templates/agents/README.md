<!--
@dependency-start
contract template
responsibility Documents reusable run artifact templates for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract.
downstream implementation ../../tools/agent_tools/agent_team.py renders templates and partials.
downstream implementation ./_partials/reader_map.md shared reader-path fields.
downstream implementation ./_partials/review_contract.md shared review evidence boundary.
@dependency-end
-->

# Agent Templates

`templates/agents/` contains source templates for run-bundle artifacts.
`tools/agent_tools/agent_team.py` renders these files into
`reports/agents/<run-id>/`.

## Reader Map

この README は、run-bundle artifact template の source owner、partial の再利用境界、
active design packet の射影、生成後の readback を説明します。読者はまず各 artifact の
`Reader Map`、次に責務・入力・validation・cleanup を読みます。

- purpose: run-local artifact の構造と renderer 境界を固定する。
- intended reader: task owner、実装者、reviewer、closeout verifier。
- what this directory contains: role artifact と再利用可能な partial source。
- canonical source: `templates/agents/`。
- generated projection: `reports/agents/<run-id>/`（手編集しない）。
- validation/readback: renderer の partial 展開、dependency header、選択 gate の証跡。
- lifecycle: run closeout 後に retention policy と cleanup owner が扱う。

## Partials

Reusable sections live under `templates/agents/_partials/`. A template includes
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

共通 partial `reader_map.md` は読者経路・内容・owner・validation・cleanup の欄を提供し、
`review_contract.md` は review の design trace、dependency/effect、oracle、failure cause、
conflict intent を提供します。role 固有の判断は各 top-level template に残します。

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
