<!--
@dependency-start
contract reference
responsibility Owns canonical GitHub Issue/PR template sources and their generated AgentCanon projections.
upstream design ../../../.github/AGENTS.md GitHub subtree runtime boundary.
upstream design ../../../documents/operations/issue-label-taxonomy.md issue taxonomy and routing contract.
upstream design ../../../agents/evals/README.md eval evidence and issue capture contract.
upstream design ../../../agents/workflows/agent-canon-pr-workflow.md AgentCanon PR workflow.
downstream implementation ./issue/config.yml GitHub Issue configuration source.
downstream implementation ./issue/agentcanon-maintenance.yml maintenance Issue Form source.
downstream implementation ./issue/eval-capture.yml eval Issue Form source.
downstream implementation ./pull-request/agent_canon.md AgentCanon PR template source.
downstream implementation ../../../documents/runtime/shared-runtime-surfaces.toml source-to-target projection manifest.
@dependency-end
-->

# GitHub template sources

このディレクトリが GitHub template の唯一の canonical owner です。GitHub が認識する
path と format は、生成された `.github/ISSUE_TEMPLATE/` と
`.github/PULL_REQUEST_TEMPLATE/` へ投影した結果であり、そこを直接編集しません。

## 責務

- Issue Form YAML と PR Markdown の必須 evidence 欄を正本として定義する。
- AgentCanon 自身の `.github` projection と、親rootへ投影される target の対応を明示する。
- Issue taxonomy、eval capture、PR workflow、GitHub subtree instructions を同じ reader
  pathへ接続する。
- GitHub schema と認識 path を保ち、source→target の向きを surface manifest と readback
  で検証する。

## 読者 map

- **Issue/PR作成者**: source の必須欄と evidence の粒度を確認する。
- **reviewer / maintainer**: owner、scope、options、acceptance、失敗・cleanup証跡を判断する。
- **親repo integrator**: manifest が指定する AgentCanon/root `.github` projection のみを更新する。
- **GitHub automation owner**: YAML form schema、認識 path、生成のreadbackを確認する。

## 含む内容

| canonical source | GitHub-recognized AgentCanon target | format |
| --- | --- | --- |
| `issue/config.yml` | `.github/ISSUE_TEMPLATE/config.yml` | GitHub Issue configuration YAML |
| `issue/agentcanon-maintenance.yml` | `.github/ISSUE_TEMPLATE/agentcanon-maintenance.yml` | GitHub Issue Form YAML |
| `issue/eval-capture.yml` | `.github/ISSUE_TEMPLATE/eval-capture.yml` | GitHub Issue Form YAML |
| `pull-request/agent_canon.md` | `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` | GitHub Markdown template |

`.github/PULL_REQUEST_TEMPLATE.md` は standalone AgentCanon のPR checklistであり、
manifest の `standalone_only` surface としてAgentCanon内だけに残します。これは
template/derived repo向け `agent_canon.md` の第二正本ではなく、異なる読者・責務の
standalone routeです。親rootへは投影しません。

親rootの同じ `.github` target は、surface manifest の `source` と `path` が表す generated
projectionです。`templates/documents/github/` と `.github/` の間に手作業の duplicate
owner を作りません。source を編集した後、surface render/readbackで4件すべての対応と
projection向きを確認します。

## 更新と検証

- source の依存header、Issue taxonomy、eval reference、PR workflow referenceを更新する。
- template / derived repo の AgentCanon PR checklist は parent gate command
  `make agent-canon-pr-check` を一つだけ公開する。dependency graph などの internal
  subcommand は `check_agent_canon_pr.sh` の実行責務であり、checklist authority として
  重複掲載しない。
- `documents/runtime/shared-runtime-surfaces.toml` で source→AgentCanon/root target を
  一意に登録する。
- `python3 tools/agent_tools/surface_manifest.py --manifest documents/runtime/shared-runtime-surfaces.toml copy-specs`
  で projection spec を renderし、同じ manifest の `check-doc` と source/target readback を実行する。
- GitHub YAML parse と Markdown/docs format/check を実行する。
