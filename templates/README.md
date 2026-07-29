<!--
@dependency-start
contract reference
responsibility Indexes the centralized AgentCanon template owner and its parent-root projections.
upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md shared template surface ownership
upstream design ../documents/rule/README.md document filename, placement, and language rules
downstream implementation ./agents/README.md reusable agent artifact template source
downstream implementation ./documents/README.md reader-facing document template source
downstream implementation ./experiments/_template/run.py runnable experiment scaffold source
downstream implementation ../tools/agent_tools/agent_team.py renders agent templates
downstream implementation ../tools/experiments/create_experiment_topic.py copies experiment templates
downstream implementation ../tools/sync_agent_canon.sh projects the root templates view
@dependency-end
-->

# Centralized Templates

このディレクトリは、AgentCanon が提供する template の唯一の source owner です。旧来の
`agents/templates/`、`documents/templates/`、`experiments/_template/` は存在せず、alias、
wrapper、互換コピーも作りません。

## Source-view index

| Source view | Responsibility | Materialization rule |
| --- | --- | --- |
| `templates/agents/` | task-start、run bundle、review、closeout の artifact template | Agent team がこの path を直接 render する |
| `templates/documents/` | README、design、experiment、host、remote execution、GitHub template source | GitHub surface は manifest 経由で `.github/` へ copy projection する |
| `templates/experiments/_template/` | runnable experiment scaffold の frozen source | `create_experiment_topic.py` が新規 `experiments/<topic>/` へ copy する |

親 template / derived repo では、`bash tools/sync_agent_canon.sh link-root` が root の
`templates -> vendor/agent-canon/templates` managed symlink を materialize します。親側の
`experiments/_template` は source owner ではないため削除し、親の
`experiments/registry.toml` から `_template` entry と対応する docs / tests を削除します。
GitHub Issue / PR projection は `templates/documents/github/` を source として再生成します。

## Experiment copy boundary

`create_experiment_topic.py` は `templates/experiments/_template/`、
`templates/documents/experiment/README.template.md`、および
`templates/documents/experiment/experiment-provenance.template.toml` を読み、生成先だけを
`experiments/<topic>/` に書き込みます。source scaffold、source registry、GPU 実行経路は
直接変更しません。managed runner の実行入口は常に生成後の
`experiments/<topic>/run.py` です。

## Parent follow-up packet

この source change を parent repo に反映するときは、次を同じ parent update packet に記録します。

- root managed symlink: `templates -> vendor/agent-canon/templates`
- delete parent `experiments/_template/`
- delete the parent registry `_template` entry
- delete parent docs and tests that only exercise the removed scaffold
- regenerate and check `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE/` projections
- pass `bash tools/sync_agent_canon.sh check` from the parent root after the pin/root-view update

Parent `experiments/registry.toml` remains project-owned: only the obsolete `_template` entry is
removed, and all real topic identities stay intact.
