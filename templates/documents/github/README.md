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
downstream implementation ../../../tools/ci/check_github_workflows.py validates GitHub workflow and PR template conventions.
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
最初に説明します。Issue/PR の本文は reader map、PR Essence または observed facts、
owner/OOP boundary、design trace、dependency/effect、oracle/failure、conflict intent、
alternatives/independent review、validation の順で記録します。

- purpose: GitHub Issue/PR source を一つの canonical path で提供する。
- intended reader and decision: issue author、PR author/reviewer、maintainer、親repo integrator。
- what this directory contains: Issue Form YAML、config、AgentCanon PR Markdown source。
- checked-in surface: standalone AgentCanon の `.github/ISSUE_TEMPLATE/` と `.github/PULL_REQUEST_TEMPLATE/`。
- validation: YAML parse、`agent-canon docs check`、`python3 tools/ci/check_github_workflows.py --root .`。
- lifecycle: checked-in targets、temporary clone、run-local evidence の retention/cleanup owner。

## 責務

- Issue Form YAML と PR Markdown の必須 evidence 欄を正本として定義する。
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
  `make agent-canon-pr-check` を一つだけ公開する。dependency graph などの internal
  subcommand は `check_agent_canon_pr.sh` の実行責務であり、checklist authority として
  重複掲載しない。
- GitHub YAML parse、Markdown/docs format/check、および
  `python3 tools/ci/check_github_workflows.py --root .` を実行する。

## Required evidence vocabulary（必要な evidence 用語）

source の変更では、必要な範囲で owner/responsibility と OOP/type boundary、design-to-
implementation trace、dependency/side-effect map、algorithm contract before tests、
necessary-and-sufficient oracle、failure-cause classification、conflict intent、複数案と
independent review、formatter/readback、lifecycle cleanup を同じ terms で入力します。
不要な欄は `not_applicable` と理由を記録します。
