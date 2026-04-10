# tools

`tools/` は shared automation の正本です。
agent helper、CI/check、container runner、experiment helper、Markdown 整備、validation はここに置きます。

## 含めるもの

- `agent_tools/`
  - task/doc start、close gate、work log、runtime smoke
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
    - `ensure-latest` は task 開始時に upstream `agent-canon` と local subtree snapshot を揃えます。
  - `run_comprehensive_review.sh`
  - `run_pytest_with_logs.sh`
  - `docker_dependency_validator.sh`
  - `check_doc_test_triplet.py`

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
- `documents/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`
