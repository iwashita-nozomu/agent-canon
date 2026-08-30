<!--
@dependency-start
contract reference
responsibility Owns canonical GitHub Issue/PR template sources and their checked-in standalone targets.
upstream design ../../../.github/AGENTS.md GitHub subtree runtime boundary.
upstream design ../../../documents/operations/issue-label-taxonomy.md issue taxonomy and routing contract.
upstream design ../../../agents/evals/README.md eval evidence and issue capture contract.
upstream design ../../../agents/workflows/agent-canon-pr-workflow.md AgentCanon PR workflow.
downstream implementation ./issue/config.yml GitHub Issue configuration source.
downstream implementation ./issue/agentcanon-maintenance.yml maintenance Issue Form source.
downstream implementation ./issue/eval-capture.yml eval Issue Form source.
downstream implementation ./pull-request/agent_canon.md AgentCanon PR template source.
downstream implementation ../../../tools/validation/ci/checks/check_github_workflows.py validates GitHub workflow and PR template conventions.
@dependency-end
-->

# GitHub template source（GitHub template の正本）

このディレクトリが standalone AgentCanon の GitHub template の唯一の canonical owner
です。GitHub が認識する path と format は、checked-in AgentCanon 自身の
`.github/ISSUE_TEMPLATE/` と `.github/PULL_REQUEST_TEMPLATE/` へ投影した結果であり、
そこを直接編集しません。Template / derived parent の `.github` は parent-owned regular
content であり、ここから投影しません。

## Reader Map

この README は、Issue/PR source、standalone の checked-in target、owner、cleanup の境界を
最初に説明します。Maintenance Issue は発生事象、変更目的、作業進捗、残作業、更新
blocker を current snapshot として先に示し、詳細 evidence 欄へ接続します。PR の本文は
concise な PR Essence、canonical route、changed-surface validation、mutation authority、
risk/follow-up の順で記録します。Alternatives / independent review は実際の選択肢または
リスクがある場合だけ記録します。

- purpose: GitHub Issue/PR source を一つの canonical path で提供する。
- intended reader and decision: issue author、PR author/reviewer、maintainer、親repo integrator。
- what this directory contains: Issue Form YAML、config、AgentCanon PR Markdown source。
- checked-in surface: standalone AgentCanon の `.github/ISSUE_TEMPLATE/` と `.github/PULL_REQUEST_TEMPLATE/`。
- validation: YAML parse、`agent-canon docs check`、`python3 tools/validation/ci/checks/check_github_workflows.py --root .`。
- lifecycle: checked-in targets、temporary clone、run-local evidence の retention/cleanup owner。

## 責務

- Issue Form YAML と PR Markdown の必須 evidence 欄を正本として定義する。
- Maintenance Issue の operational current snapshot を、発生事象、変更目的、進捗、残作業、
  blocked operation と解除条件の一つの reader route として定義する。
- AgentCanon 自身の `.github` checked-in targets の対応を明示する。親rootへの projection は定義しない。
- Issue taxonomy、eval capture、PR workflow、GitHub subtree instructions を同じ reader
  pathへ接続する。
- GitHub schema と認識 path を保ち、canonical source と checked-in standalone target を
  同じ変更で更新する。

## 読者 map

- **Issue/PR作成者**: source の必須欄と evidence の粒度を確認する。
- **reviewer / maintainer**: owner、scope、options、acceptance、失敗・cleanup証跡を判断する。
- **親repo maintainer**: parent-owned regular `.github` content を管理し、AgentCanon source を親rootへ copy/render しない。
- **GitHub automation owner**: YAML form schema、認識 path、`check_github_workflows.py` の結果を確認する。

## 含む内容

| canonical source | GitHub-recognized standalone AgentCanon target | format |
| --- | --- | --- |
| `issue/config.yml` | `.github/ISSUE_TEMPLATE/config.yml` | GitHub Issue configuration YAML |
| `issue/agentcanon-maintenance.yml` | `.github/ISSUE_TEMPLATE/agentcanon-maintenance.yml` | GitHub Issue Form YAML |
| `issue/eval-capture.yml` | `.github/ISSUE_TEMPLATE/eval-capture.yml` | GitHub Issue Form YAML |
| `pull-request/agent_canon.md` | `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` | GitHub Markdown template |

`.github/PULL_REQUEST_TEMPLATE.md` は standalone AgentCanon のPR checklistであり、
AgentCanon内だけに残します。これは
template/derived repo向け `agent_canon.md` の第二正本ではなく、異なる読者・責務の
standalone routeです。親rootへは投影しません。

Template / derived parent の `.github` target は parent-owned regular content です。
`templates/documents/github/` と standalone AgentCanon `.github/` の間に手作業の
duplicate owner を作らず、source と checked-in standalone targets を同時に更新します。

## 更新と検証

- source の依存header、Issue taxonomy、eval reference、PR workflow referenceを更新する。
- template / derived repo の AgentCanon PR checklist は parent gate command
  `make agent-canon-pr-check` を一つだけ公開する。この gate が changed-surface
  checker route として、対象 surface に対応する検証結果を束ねる。dependency graph
  などの internal subcommand は `check_agent_canon_pr.sh` の実行責務であり、checklist
  authority として重複掲載しない。
- GitHub YAML parse、Markdown/docs format/check、および gate が呼び出す
  `python3 tools/validation/ci/checks/check_github_workflows.py --root .` を実行する。
- Maintenance Issue Form は canonical source と checked-in standalone target の
  `name:` 以下を read back し、operational field ID、required flag、表示順の一致を確認する。

## Operational current snapshot

Maintenance Issue Form の先頭では、Issue の履歴全文ではなく、現在の handoff と更新可否を
判断するための最小状態を必須にします。

| field ID | owner |
| --- | --- |
| `current_behavior` | 具体的に何が起きたかと観測証拠 |
| `change_purpose` | 誰のどの判断・操作を可能にし、どの状態へ到達させるか |
| `work_progress` | 完了済み、作業中、branch / commit / PR / validation evidence |
| `remaining_work` | 現在未達の作業、次の owner、完了証拠 |
| `update_blocker` | blocked operation、blocker、分類、証拠、解除条件 |

この snapshot は起票時の固定 plan ではありません。branch、commit、PR、validation、
blocker が変わるたびに Issue 本文を更新します。blocker がない場合も `none` と理由を
記録し、未観測と block なしを区別します。

`remaining_work` は現在未達の差分を所有し、最終契約は `acceptance` が所有します。
`update_blocker` は現在止まっている操作と再開条件を所有し、原因の詳細分類と最終 close
condition は `failure_cause` が所有します。`work_progress` は current snapshot、
`closeout_evidence` は完了時の固定証拠です。この境界により同じ事実を複数欄へ全文複製
しません。

## Required evidence vocabulary（必要な evidence 用語）

source の変更では、`source_commit`、`template_pin`、`pr_head` を一つの identity relation
として記録し、canonical route、changed-surface validation、mutation authority、risk /
follow-up を入力します。不要な alternatives / independent review は
`not_applicable` と理由を記録します。固定の全チェック一覧、事前の Plan / route pause、
issue・memory・failure の全件 sweep、毎回の mirror、Copilot 設定レビューは必須にしません。
