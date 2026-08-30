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

## Selection

`documents/runtime/runtime-profiles-and-check-matrix.md` を読み、変更した
責務に対応する profile と、その profile が要求する route だけを選びます。
この入口は command list や default sequence を再定義しません。選択した
route の結果（pass / fail / 未実行）と追加調査の要否だけを記録します。

full-confidence が必要な場合だけ、下記の shared runtime/read-only target
route に進みます。

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

- profile activation は runtime profile/check matrix が正本です。
- `static-validation` は選択結果の意味を説明する入口であり、別の default gate を追加しません。
- `run_all_checks.sh` は read-only target内で再利用する既存 check bodyです。Host checkoutからの direct full-confidence routeは使用しません。
- GitHub metadata、receipt publication、control-parent transactionを持つ `check_agent_canon_pr.sh` の移行は別責務です。
- 深い diff review は `change-review` または `code-review` を使います。
