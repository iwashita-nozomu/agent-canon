<!--
@dependency-start
contract template
responsibility Documents reusable run artifact templates for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract.
downstream implementation ../../tools/agent/orchestration/agent_team.py renders templates and partials.
downstream implementation ./_partials/reader_map.md shared reader-path fields.
downstream implementation ./_partials/review_contract.md shared review evidence boundary.
@dependency-end
-->

# Agent 用テンプレート

`templates/agents/` は run-bundle artifact の正規 source template を収録します。
`tools/agent/orchestration/agent_team.py` がこれらを `reports/agents/<run-id>/` へ展開します。

## Reader Map（読者 map）

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

## Partial の再利用

再利用する節は `templates/agents/_partials/` に置き、次の marker で取り込みます。

```text
{{>partial_name}}
```

renderer は run variable（`{{RUN_ID}}`、`{{TASK}}`、`{{OWNER}}`、`{{CREATED_AT}}`）を置換する前に
partial を展開します。展開時に partial の dependency manifest block を除去し、生成 artifact
には top-level artifact manifest だけを残します。

partial は findings table や decision 節など、artifact 間で生成上の意味を同じに保つ反復構造に
限って使います。role 固有の review focus、必要証跡、承認基準を partial に隠しません。

共通 partial `reader_map.md` は読者経路・内容・owner・validation・cleanup の欄を提供し、
`review_contract.md` は review の design trace、dependency/effect、oracle、failure cause、
conflict intent を提供します。role 固有の判断は各 top-level template に残します。

## Active Design Packet の射影

`agents_config.json#artifacts.active_design_packet` は中立な閉じた
`waterfall.design_packet.v1` record を定義します。選択された design、technical review、
document-flow review の経路、clause registry、4 つの typed entry は 1 つの run bundle に
射影され、`team_manifest.yaml#run.active_design_packet` に保存されます。付属する
`active_design_packet_reference_projection` は packet SHA、source-byte identity、dependency
endpoint、選択 output、reviewer artifact identity を記録します。4 entry は `design_brief.md`
の対応節へ射影し、`design_review.md` は artifact identity と entry を、
`document_flow_review.md` は source packet と読者可視の副作用を、`change_review.md` と
`final_review.md` は統合 trace を検証します。

template は packet authority を parse や推論で作りません。`create_run_bundle` が packet を解決し、
closed field set、relative artifact path、typed graph reference、materialized source/dependency
identity を検証してから selected template を memory 上で render し、task-start、bootstrap、
document-start producer 用の完全な bundle を公開します。review template は承認記録だけを持ち、
active run pointer を書き換えたり進めたりしません。
