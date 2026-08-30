# static-check
<!--
@dependency-start
contract agent-runtime
responsibility Documents static-check selection and read-only full-confidence execution for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime/bootstrap-runtime.md shared runtime and target registration boundary
upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh read-only target admission and full-check dispatch
@dependency-end
-->


## Purpose

実装変更の直後に、速く回せる基礎検査をまとめて扱います。

## Use When

- 型エラーの早期検出
- pytest の早期失敗確認
- Markdown とリンクの基礎確認
- Docker / 実行環境の破綻確認

## Core References

- `agents/internal-routines/static-validation.md`
- `documents/tools/README.md`
- `tools/validation/ci/runners/run_standalone_static_gate_unit.sh`
- `tools/validation/ci/runners/run_all_checks.sh`
- `tools/bin/agent-canon docs check`
- `tools/validation/ci/checks/check_docker_build.sh`

## Expected Outcome

- 今回の変更に対して最低限必要な gate が実行されている
- `pass / fail / 未実行` が短く整理されている
- deeper review や追加 validation が必要か判断できる
- full-confidence check の前後で caller checkout の tracked working tree と index が変化していない

## Check Selection

- agent runtime、skill、mirror を触ったら `make agent-checks` を先に実行します。
- code / docs 変更では、まず `make ci-quick` を基礎 gate にします。
- Python / C++ 実装変更では `python3 tools/validation/semantic/code/check_hardcoded_numbers.py --changed --exclude tests --exclude vendor --exclude reports` を追加します。
- Markdown 中心の変更では `tools/bin/agent-canon docs check` を追加します。
- Docker / runtime / dependency 変更では `make docker-build-check` を追加します。
- 失敗が出た場合は、追加コマンドを増やす前に、どの gate が不足しているかを明示します。

## Default Sequence

1. 変更対象を見て、code、docs、runtime、agent のどこを触ったかを固定します。
1. 最低限必要な gate を選び、`make agent-checks`、`make ci-quick`、`tools/bin/agent-canon docs check`、`make docker-build-check` から組み合わせます。
1. 速い gate を先に実行し、失敗したらその時点で原因を切り分けます。
1. full-confidence が必要な場合は、下記の shared runtime/read-only target routeを使います。
1. 追加の深い検証が必要なら `static-validation` へ進みます。
1. closeout では、通ったもの、失敗したもの、まだ回していないものを分けて残します。

## Default Commands

- `make agent-checks`
- `make ci-quick`
- `tools/bin/agent-canon docs check`
- `make docker-build-check`

## Read-only Full Confidence

`tools/validation/ci/runners/run_all_checks.sh` は full-confidence body であり、caller checkout 上から直接起動しません。既存 bootstrap runtime に source checkout を read-only targetとして登録し、image-owned unit runnerの `full` unitから起動します。

```bash
SOURCE_ROOT="$(git rev-parse --show-toplevel)"
CONTROL_PARENT_ROOT="$(cd "${SOURCE_ROOT}/.." && pwd -P)"
RUNTIME_ROOT="${CONTROL_PARENT_ROOT}/workspace/agent-canon-runtime/full-check"
COMMON=(
  --control-parent-root "${CONTROL_PARENT_ROOT}"
  --runtime-root "${RUNTIME_ROOT}"
)

./bootstrap.sh "${COMMON[@]}" install
./bootstrap.sh "${COMMON[@]}" start
./bootstrap.sh "${COMMON[@]}" target add \
  --root "${SOURCE_ROOT}" \
  --mode read-only
./bootstrap.sh "${COMMON[@]}" exec \
  --root "${SOURCE_ROOT}" \
  -- bash /usr/local/share/agent-canon/runtime/tools/validation/ci/runners/run_standalone_static_gate_unit.sh \
  full --quick
```

`full` の後ろは `run_all_checks.sh` の optionです。unit runnerは `/proc/self/mountinfo` の最深一致 mountが `ro` であることを確認してから、既存の `run_all_checks.sh` bodyをそのまま呼びます。bodyの exit code と finding は変更せず、失敗を成功に変換しません。graph checkを抑制したり、失敗を別の合否判定へ置き換えたりもしません。`CARGO_HOME`、`RUSTUP_HOME`、Cargo targetは外部runtime配下に置き、CLIはimage-owned `/usr/local/bin/agent-canon`を使います。`.gitignore`、`git restore`、`git reset`、`git clean`、`git stash` による隠蔽・復元は行いません。

この経路で保証するのは実行境界だけです。read-only targetのtracked treeとindexが実行前後で変わらないこと、引数とbodyの終了状態がcallerへ戻ることを確認します。既存bodyが返した失敗は、その失敗原因の調査対象として残ります。

## Boundary

- この repo では `static-validation` が基礎 gate の正本です。
- `run_all_checks.sh` は read-only target内で再利用する既存 check bodyです。Host checkoutからの direct full-confidence routeは使用しません。
- GitHub metadata、receipt publication、control-parent transactionを持つ `check_agent_canon_pr.sh` の移行は別責務です。
- 深い diff review は `change-review` または `code-review` を使います。
