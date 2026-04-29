# tools
<!--
@dependency-start
responsibility Documents tools for this repository.
upstream design ../AGENTS.md shared canon runtime contract
@dependency-end
-->


`tools/` は shared automation の正本です。
agent helper、CI/check、container runner、experiment helper、Markdown 整備、validation はここに置きます。

## 含めるもの

- `agent_tools/`
  - task/doc start、waterfall gate、close gate、work log、runtime smoke
  - `task_start.py` と `bootstrap_agent_run.py` は task 入口で `make agent-canon-ensure-latest` preflight を自動実行します。worktree が dirty の場合は fail-open で理由を machine-readable に出力し、clean なら fail-closed で最新化を通します。
- `ci/`
  - repo check、container runner、server readiness、fresh clone acceptance
  - `python_env_policy.py` は host/container を判定し、container でだけ canonical `.venv` を許可します。
- `docs/`
  - Markdown lint、math check、link audit、format、mirror sync
- `experiments/`
  - topic scaffold、registry sync、managed run
- `shared/`
  - shared helper
- `validation/`
  - generic validation helper
- top-level helper
  - `sync_agent_canon.sh`
    - `plan` は derived repo から見た update route を read-only で出します。
    - `ensure-latest` は task 開始時に upstream `agent-canon` と local subtree snapshot を揃えます。
    - `agent-canon` remote が未設定で `/mnt/git/agent-canon.git` が存在する場合は自動追加します。
    - fresh clone で subtree metadata が無い場合は、fast-forward 更新に限って snapshot import へ切り替えます。
  - `update_agent_canon.sh`
    - `plan` は derived repo から `agent-canon` だけ更新するときの route を出します。
    - source repo が設定されている場合、`plan` は `refresh -> local sync` 後の実効 route を出します。source repo が missing / dirty なら fail-closed で止まります。
    - `refresh-remote` は configured source repo の branch を `agent-canon` remote へ push し、remote snapshot を先に最新化します。
    - `apply` は `refresh-remote` を先に実行できる場合は remote snapshot を最新化し、そのあと `ensure-latest` を呼びます。
    - `proposal-branch` は shared canon 差分の既定 push 先 branch を表示します。
    - `push-proposal` は shared canon 差分を repo 専用 proposal branch へ push します。
    - source repo の優先順位は `AGENT_CANON_SOURCE_REPO`、`git config agent-canon.sourceRepo` です。`register-local-bare` は project-local bare repo を seed し、proposal branch を用意し、`agent-canon` remote と optional source repo path を設定します。
  - `run_comprehensive_review.sh`
  - `run_pytest_with_logs.sh`
  - `docker_dependency_validator.sh`
  - `check_doc_test_triplet.py`
  - `agent_tools/waterfall_gate_check.py`
  - `agent_tools/evaluate_agent_run.py`

## Agent Evaluation Tools

`evaluate_agent_run.py` grades one `reports/agents/<run-id>/` bundle before closeout.
It turns workflow monitoring, review, validation, schedule, dependency, and retrospective evidence into `agent_evaluation.md` with a score and fix-now feedback actions.
This is the repo-local counterpart to trace / eval feedback loops: use it to identify missing tooling, guardrails, documentation, prompt policy, skill/config/workflow updates, or run evidence before the user-facing completion report.

```bash
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --write
```

`task_close.py` requires `agent_evaluation.md` to report `evaluation_status: pass`, `feedback_actions_resolved: yes`, and `learning_capture_complete: yes`.
`workflow_monitoring.md` is the in-workflow monitoring artifact consumed by the evaluation. Keep it current during the run, not only at closeout.

## Dependency Manifest Tools

Dependency manifest checks live under `tools/agent_tools/` and are Bash-first.

- `scan_dependency_headers.sh` reports missing `@dependency-start` / `@dependency-end` markers.
- `check_dependency_header_format.sh` validates manifest syntax, relative paths, kinds, and target existence.
- `check_dependency_graph.sh` builds upstream and downstream graphs and fails isolated manifests, self references, and cycles by default.
- `check_dependency_graph.sh --check-bidirectional` additionally checks reverse-edge presence and kind consistency during bidirectional migration.
- `run_repo_dependency_review.sh` runs scan, format, and graph checks against all tracked checkable repo files. Use this during checkpoint and final review, not only closeout.

Do not use Dockerfile or environment files as universal dependency anchors.
Use `environment` edges only for real Docker / CI / requirements / runtime coupling.
Generic canon files should connect to the nearest canon-owned anchor such as `AGENTS.md`, `README.md`, a directory README, a canonical workflow document, or this tool index.

## 含めないもの

- clone 直後の repo-local 初期化
- template 固有の name / slug / bare remote 置換

それらは root `scripts/` に残します。

## Bash 実装の扱い

- shared automation として配る Bash は `tools/` に置きます。
- repo ごとに変わる bootstrap Bash は root `scripts/` に残します。
- agent helper、CI、review、validation、container runner、experiment helper の Bash を root `scripts/` に置くことを禁止します。

## 入口

- template 利用者:
  - root `tools/` から使います
- shared canon 保守者:
  - `vendor/agent-canon/tools/` を source of truth として編集します

## 関連文書

- `documents/SHARED_RUNTIME_SURFACES.md`
- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`
