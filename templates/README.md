<!--
@dependency-start
contract reference
responsibility Indexes the centralized AgentCanon template owner and the parent-owned boundary.
upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md shared template surface ownership
upstream design ../documents/rule/README.md document filename, placement, and language rules
upstream design ../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse projection traces
downstream implementation ./agents/README.md reusable agent artifact template source
downstream implementation ./documents/README.md reader-facing document template source
downstream implementation ./code/README.md materializable code and Docstring template source
downstream implementation ./experiments/_template/run.py runnable experiment scaffold source
downstream implementation ../tools/agent_tools/code_template_rendering.py renders materializable code templates
downstream implementation ../tools/agent_tools/agent_team.py renders agent templates
downstream implementation ../tools/experiments/create_experiment_topic.py copies experiment templates
downstream implementation ../tools/ci/check_github_workflows.py validates checked-in GitHub template targets
@dependency-end
-->

# Centralized Templates

このディレクトリは、AgentCanon が提供する template の唯一の source owner です。旧来の
`agents/templates/`、`documents/templates/`、`experiments/_template/` は存在せず、alias、
wrapper、互換コピーも作りません。

## Reader Map

この README は、template source の全体像、各 source view の責務、checked-in target、
親repoとの境界、更新・再現・cleanup の入口を提供します。最初にこの表で source owner
を決め、次に対象 template の `what this document contains`、owner、設計 trace、
validation/readback、lifecycle を読みます。

- purpose: adaptable な AgentCanon template source を一つの canonical path で提供する。
- intended reader: template利用者、実装者、reviewer、親repo integrator、保守者。
- what this directory contains: agent artifact、reader-facing document、materializable code、experiment scaffold、GitHub source。
- canonical source: `templates/`。
- checked-in / local surfaces: standalone AgentCanon `.github/` targets、run/result、reports。derived parent の `.github` と runtime directories は parent-owned regular content。
- update owner: 各 source template と対応する checked-in target。
- required validation: source/target identity、formatter/docs、dependency header、semantic checker。
- lifecycle: run-local data と generated copies は retention policy / producer owner が cleanup する。

## Source-view index

| Source view | Responsibility | Materialization rule |
| --- | --- | --- |
| `templates/agents/` | task-start、run bundle、review、closeout の artifact template | Agent team がこの path を直接 render する |
| `templates/documents/` | README、design、experiment、host、remote execution、GitHub template source | standalone AgentCanon の checked-in GitHub targets を source と同時に更新する |
| `templates/code/` | parse-valid module/class/function と Docstring の materializable source | `render_code_template()` または明示 copy で destination owner へ materialize する |
| `templates/experiments/_template/` | runnable experiment scaffold の frozen source | `create_experiment_topic.py` が新規 `experiments/<topic>/` へ copy する |
| `templates/agents/_partials/` | reader map、review contract、finding/decision の再利用部品 | top-level agent artifact の render 時だけ展開する |

親 template / derived repo は、この正本を
`vendor/agent-canon/templates/` から直接解決します。root `templates` symlink
view は materialize しません。親側の `experiments/_template` は source owner
ではないため削除し、親の `experiments/registry.toml` から `_template`
entry と対応する docs / tests を削除します。GitHub Issue / PR の checked-in standalone
targets は `templates/documents/github/` source と同時に更新します。derived parent の
`.github`、`.devcontainer`、`.vscode`、`agents`、`.agents` は parent-owned regular content
であり、この source から親rootへ反映しません。

## Experiment copy boundary

`create_experiment_topic.py` は `templates/experiments/_template/`、
`templates/documents/experiment/README.template.md`、および
`templates/documents/experiment/experiment-provenance.template.toml` を読み、生成先だけを
`experiments/<topic>/` に書き込みます。source scaffold、source registry、GPU 実行経路は
直接変更しません。managed runner の実行入口は常に生成後の
`experiments/<topic>/run.py` です。`run.py` は orchestration だけを担当し、
`case_model.py`（case/record 型）、`case_execution.py`（case worker と failure 分類）、
`artifact_schema.py`（summary/manifest schema）、`artifact_io.py`（atomic serialization）、
`visualization.py`（optional consumer status）が利用者の replaceable extension point です。

## Parent follow-up packet

この source change を parent repo に反映するときは、次を同じ parent update packet に記録します。

- parent integration commit では、tracked entry が旧 `templates -> vendor/agent-canon/templates`
  symlink であることを確認してからだけ `git rm templates` を実行する。
- `vendor/agent-canon/templates/` と parent-owned の通常 `templates/` directory を保持する。
- parent の `experiments/_template/` を削除する。
- parent registry の `_template` entry を削除する。
- 削除した scaffold だけを使う parent docs と tests を削除する。
- derived parent の `.github` regular content を保持し、AgentCanon source の GitHub
  targets を親rootへ再生成しないことを確認する。
- pin/root-view 更新後、parent root で
  `PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check`
  を pass させる。

Parent `experiments/registry.toml` remains project-owned: only the obsolete `_template` entry is
removed, and all real topic identities stay intact.

## Docstring projection

Template Docstring の semantic owner は [Docstring Semantic Contract](../documents/conventions/DOCSTRING_GUIDE.md)
です。各 consumer は responsibility region と selected semantic delta だけを記録し、固定 section
や signature、type、namespace、field の事実を繰り返しません。design document または generated
experiment は、その trace を materialize するとき guide reference と projection anchor を記録します。

`templates/documents/semantic-responsibility-contract.template.toml` は空の instance
shape を提供します。値を埋めた semantic responsibility contract は run-local artifact
として active design packet から参照し、template source へ戻しません。

## Required document and artifact fields

各 template の利用者は、必要性を判断できる最小の field を埋めます。reader map は文書の
冒頭に置き、設計・実装・review・experiment・PR の選択がある場合は次を相互参照します。

- owner / responsibility と OOP/type boundary
- design-to-implementation trace と dependency / side-effect map
- tests より前の algorithm contract
- necessary-and-sufficient oracle/test boundary
- failure-cause classification、accepted failure、conflict intent
- 複数の viable alternatives と独立 reviewer / selection evidence
- Markdown/math/Mermaid formatter、post-format readback、targeted validation
- artifact retention、再構築、lifecycle cleanup owner

Markdown の整形・数式・Mermaid は `tools/bin/agent-canon docs check` を必須の一つの入口とし、
formatter/fixer 後は同じ source path を read back します。examples は適応可能な placeholder
にし、単一 repo の path、GPU 番号、serial throttle、固有 API を template の意味として固定しません。
