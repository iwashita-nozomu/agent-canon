# tools

`tools/` は shared automation の正本です。
agent helper、CI/check、container runner、experiment helper、Markdown 整備、validation はここに置きます。

## 含めるもの

- `agent_tools/`
  - task/doc start、waterfall gate、close gate、work log、runtime smoke
- `ci/`
  - repo check、container runner、server readiness、fresh clone acceptance
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
