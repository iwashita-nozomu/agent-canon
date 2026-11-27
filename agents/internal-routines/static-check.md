# static-check
<!--
@dependency-start
contract agent-runtime
responsibility Documents static-check selection and read-only full-confidence execution for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime/bootstrap-runtime.md shared runtime and target registration boundary
upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh static check dispatch
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

- [runtime profile/check matrix](../../documents/runtime/runtime-profiles-and-check-matrix.md)
- [documents/tools/README.md](../../documents/tools/README.md)
- `tools/validation/ci/runners/run_standalone_static_gate_unit.sh`
- `tools/validation/ci/runners/run_all_checks.sh`
- `tools/bin/agent-canon docs check`
- `tools/validation/ci/checks/check_docker_build.sh`

## Selection

[documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md) を読み、変更した
責務に対応する profile と、その profile が要求する route だけを選びます。
導入済みの環境で起こり得る条件を確認し、実行したツールの診断と終了状態を使います。

full-confidence が必要な場合だけ、下記の shared runtime/read-only target
route に進みます。

単体の文書検査はホストの AgentCanon CLI と既存の文書ツールでも実行できます。
生成物を伴う検証では外部ランタイムのパスを指定します。

## Read-only Full Confidence

`tools/validation/ci/runners/run_all_checks.sh` は full-confidence body であり、caller checkout 上から直接起動しません。既存 bootstrap runtime に source checkout を read-only targetとして登録し、image-owned unit runnerの `full` unitから起動します。

```bash
SOURCE_ROOT="$(git rev-parse --show-toplevel)"
CONTROL_PARENT_ROOT="$(cd "${SOURCE_ROOT}/.." && pwd -P)"
COMMON=(--control-parent-root "${CONTROL_PARENT_ROOT}")

./bootstrap.sh "${COMMON[@]}" install
./bootstrap.sh "${COMMON[@]}" target add \
  --root "${SOURCE_ROOT}" \
  --mode read-only
./bootstrap.sh "${COMMON[@]}" exec \
  --root "${SOURCE_ROOT}" \
  -- bash /usr/local/share/agent-canon/runtime/tools/validation/ci/runners/run_standalone_static_gate_unit.sh \
  full --quick
```

`full` の後ろの引数は `run_all_checks.sh` に渡ります。実行結果は同スクリプトの診断と終了状態で確認します。
