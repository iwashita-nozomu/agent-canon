<!--
@dependency-start
contract reference
responsibility Documents Templates for this repository.
upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../../documents/rule/README.md document filename, placement, and language rules
downstream implementation ./github/README.md GitHub template source and checked-in standalone target map
downstream implementation ./experiment/README.template.md experiment topic planning contract
downstream implementation ./experiment/experiment-provenance.template.toml machine-readable provenance contract
downstream implementation ../../tools/experiments/create_experiment_topic.py places experiment templates in new topics
@dependency-end
-->

# Templates

このディレクトリは、reader-facing な canonical template の owner です。filename は英語、
本文は日本語とし、実値は各利用 repo、topic、host、GitHub event へ投影します。実値を
この階層へ戻して別の正本にしません。

## Reader Map

この README は、文書 template の責務、source/checked-in target 境界、含む内容、更新順、
formatter/validation、retention/cleanup を最初に示します。各 template の冒頭にも同じ
reader path の要約を置き、読者が本文を逆戻りせずに owner と完了条件へ到達できるようにします。

- purpose: 設計・README・experiment・GitHub の適応可能な文書雛形を提供する。
- intended reader: 文書作成者、実装者、reviewer、親repo integrator。
- what this directory contains: Markdown、TOML、GitHub Issue Form、PR source。
- canonical source: `templates/documents/`。checked-in standalone `.github` targets と run-local report は source とは別の責務を持つ。
- validation: dependency header、YAML/TOML parse、`agent-canon docs check`、`python3 tools/ci/check_github_workflows.py --root .`。
- lifecycle: checked-in standalone targets と result/report artifact の retention/cleanup owner を本文で固定する。

## 責務

- 設計、README、experiment の項目名・責務境界・再構築・受入構造を正本として提供する。
- AgentCanon の GitHub Issue/PR template は、standalone AgentCanon 自身の source と
  `.github/` checked-in targets を同時更新する。
- Template / derived repo の `.github`、`.devcontainer`、`.vscode`、`agents`、`.agents`
  は parent-owned regular content であり、この source から親rootへ反映しない。

## 読者 map

- **文書作成者**: 該当する template の責務と必須欄を埋める。
- **実装者 / 実験者**: design、README、experiment の source と runnable scaffold を分ける。
- **reviewer / maintainer**: canonical owner、checked-in target、再現性、受入、failure semantics を確認する。
- **親repo maintainer**: parent-owned regular surfaces を管理し、AgentCanon source の
  GitHub template を親rootへ投影しない。

## 含む内容

| surface | canonical path | natural format | role |
| --- | --- | --- | --- |
| design document | `design-document.template.md` | Markdown | authority、責務、型境界、依存、effects、options、review、reconstruction、acceptance |
| semantic responsibility contract | `semantic-responsibility-contract.template.toml` | TOML | run-local semantic delta、obligation、一次検証 owner、hard-edge closure |
| README | `README.template.md` | Markdown | purpose、structure、owner、entrypoint、reproduce、canonical/non-canonical boundary |
| experiment plan | `experiment/` | directory + Markdown/TOML | plan、resource/GPU、run/result provenance、accepted failure、reproducibility |
| GitHub Issue | `github/issue/*.yml` | GitHub Issue Form YAML | observed facts、reproduction、owner、impact、options、acceptance、non-goal |
| GitHub PR | `github/pull-request/agent_canon.md` | GitHub Markdown template | essence、dependency closure、head/review/validation/artifact/cleanup evidence |

GitHub template の canonical source は `github/` 配下です。GitHub が実際に認識する
standalone AgentCanon の `.github/ISSUE_TEMPLATE/` と `.github/PULL_REQUEST_TEMPLATE/`
は source と同時更新する checked-in targets であり、手作業の第二正本ではありません。
Template / derived parent の `.github` target は parent-owned regular content として
保持し、AgentCanon source から反映しません。GitHub semantic validation は
`python3 tools/ci/check_github_workflows.py --root .` を使用します。

## Remote Execution

- `remote_execution_target.template.toml`
  - 手動登録する SSH target の template
- `remote_execution_repo.template.toml`
  - repo ごとの clone URL と runtime profile の template

## Server Host

- `server_host_inventory.template.md`
  - main server host の inventory と readiness gap を記録する template
- `server_runtime_layout.template.toml`
  - main server host の path、mount、builder 前提を記録する template

## Rule

- host 固有の実値は repo に置きません
- template の key 追加や意味変更は、関連設計文書と同じ変更で行います
- 実値の例は匿名化し、必要なら `documents/notes/` に補助説明を書きます
- checked-in standalone targets、run-local report、raw log、Issue/PR mirror は canonical
  template source と別の責務として扱います。
- 新しい template を追加したら、owner、entrypoint、reconstruct command、validation、
  checked-in target/non-canonical boundary をこのREADMEまたは対応templateに記録します。

## 共通の最小契約

設計・README・experiment・Issue/PR template は、必要に応じて次の欄を同じ語彙で投影します。
owner/responsibility と OOP/type boundary、design-to-implementation trace、dependency/
side-effect map、algorithm contract before tests、necessary-and-sufficient oracle、failure
cause、conflict intent、alternatives と独立 review、再現用 environment/result provenance、
formatter/semantic validation、lifecycle cleanup です。不要な欄は `not_applicable` と理由を残し、
空欄のまま成功扱いにしません。

Markdown/math/Mermaid は `tools/bin/agent-canon docs check <paths...>` を必須 route とし、
formatter/fixer の後に canonical source と checked-in standalone target を同時確認します。
