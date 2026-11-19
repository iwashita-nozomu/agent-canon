<!--
@dependency-start
contract reference
responsibility Documents Templates for this repository.
upstream design ../../documents/rule/README.md document filename, placement, and language rules
downstream implementation ./github/README.md GitHub template source and checked-in standalone target map
downstream implementation ../experiments/_template/README.md runnable experiment topic planning contract
downstream implementation ../experiments/_template/provenance.toml machine-readable provenance contract
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/experiment_registry/create_experiment_topic.rs places experiment templates in new topics
@dependency-end
-->

# Templates

このディレクトリは、reader-facing な canonical template の owner です。filename は英語、
本文は日本語とし、実値は各利用 repo、topic、host、GitHub event へ投影します。実値を
この階層へ戻して別の正本にしません。

## 含む内容

| surface | canonical path | natural format | role |
| --- | --- | --- | --- |
| design document | [design-document.template.md](design-document.template.md) | Markdown | 設計の目的、責務、公開境界、判断と根拠 |
| semantic responsibility contract | `semantic-responsibility-contract.template.toml` | TOML | run-local semantic delta、obligation、一次検証 owner、hard-edge closure |
| README | [README.template.md](README.template.md) | Markdown | 目的、構成、責務、正本への参照 |
| experiment topic scaffold | `../experiments/_template/` | directory + Python/Markdown/TOML | plan、resource/GPU、run/result provenance、accepted failure、reproducibility |
| GitHub Issue | `github/issue/*.yml` | GitHub Issue Form YAML | observed facts、reproduction、owner、impact、options、acceptance、non-goal |
| GitHub PR | [github/pull-request/agent_canon.md](github/pull-request/agent_canon.md) | GitHub Markdown template | essence、dependency closure、head/review/validation/artifact/cleanup evidence |

GitHub template の canonical source と更新対象は [GitHub templates](github/README.md) を参照します。GitHub が実際に認識する
standalone AgentCanon の `.github/ISSUE_TEMPLATE/` と `.github/PULL_REQUEST_TEMPLATE/`
は source と同時更新する checked-in targets であり、手作業の第二正本ではありません。
Template / derived parent の `.github` target は parent-owned regular content として
保持し、AgentCanon source から反映しません。GitHub semantic validation は
`tools/bin/agent-canon check-github-workflows --root .` を使用します。

## Remote Execution

- `remote_execution_target.template.toml`
  - 手動登録する SSH target の template
- `remote_execution_repo.template.toml`
  - repo ごとの clone URL と runtime profile の template

## Server Host

- [server_host_inventory.template.md](server_host_inventory.template.md)
  - main server host の inventory と readiness gap を記録する template
- `server_runtime_layout.template.toml`
  - main server host の path、mount、builder 前提を記録する template

## Rule

- host 固有の実値は repo に置きません
- template の key 追加や意味変更は、関連設計文書と同じ変更で行います
- 実値の例は匿名化し、必要なら `documents/notes/` に補助説明を書きます
- checked-in standalone targets、run-local report、raw log、Issue/PR mirror は canonical
  template source と別の責務として扱います。
