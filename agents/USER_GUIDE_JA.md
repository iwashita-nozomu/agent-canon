<!--
@dependency-start
contract reference
responsibility Documents the Japanese user journey for the standalone AgentCanon runtime.
upstream design ../documents/runtime/bootstrap-runtime.md shared runtime guide
upstream implementation ../bootstrap.sh Host lifecycle entrypoint
downstream design ../documents/runtime/runtime-log-archive.md eval archive route
@dependency-end
-->

# AgentCanon 利用ガイド

このガイドは、AgentCanon の source checkout を親レポに埋め込まずに、共有
tool runtime として使う人向けです。project のビルド、テスト、GPU、GitHub 操作は
project / host workflow の責務であり、AgentCanon の tool container に持ち込みません。

## 最初の一回

`<authorized-parent-root>` は明示的に許可された親レポの root、`<project-root>` は
解析対象の project root とします。runtime は AgentCanon source の外に置きます。

```bash
ROOT=<authorized-parent-root>
RUNTIME="$ROOT/workspace/agent-canon-runtime/<installation>"
BOOTSTRAP=/path/to/agent-canon/bootstrap.sh

"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" install
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" start
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" \
  target add --root <project-root> --mode read-only
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" status
```

control root と runtime root は必須です。runtime root は control root の下でなければ
ならず、symlink を通した脱出も拒否されます。`$HOME/.cache`、`$HOME/.local`、global
`CODEX_HOME`、source tree を暗黙の保存先にしません。

## Codex を起動する

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" codex prepare
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" \
  codex launch --project-root <project-root>
```

`prepare` は runtime root 内の isolated `codex-home/` に manifest 管理の skill、agent、
hook、設定リンクを作ります。global `$CODEX_HOME` は変更しません。衝突する既存パスは
fail closed で、uninstall が削除できるのはこの installation が作成したリンクだけです。
install / update 後は新しい Codex session を起動し、manifest、link target、source digest
を readback してください。

## Tool を呼ぶ

Rust の既存 first-class command は公開形を保ちます。

```bash
agent-canon docs check ...
agent-canon semantic-index ...
agent-canon structured-analysis ...
```

Python tool は flat な global executable にしません。schema-v2 parity fixture が確認済み
の catalog entry だけを使います。

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" \
  tool run --root <project-root> <verified-catalog-id> -- <args...>
```

parity は argv、cwd、stdin/stdout/stderr、exit/signal、written paths を比較します。
未確認の entry は legacy の正確なコマンドを、登録済み target に対する `exec` または
既存 workflow から実行します。

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" \
  exec --root <project-root> -- <existing-command> <args...>
```

shell string、未知の catalog id、internal Python file の自動公開は許可しません。

## Eval と agent-canon-log

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" \
  eval sync --run-id <run-id>
```

`collect` は tool container 内の producer を実行し、runtime root の spool に run/task、
source HEAD、AgentCanon/tool digest、family status、metrics、source unchanged を含む
collection と receipt を作ります。source tree の `reports/`、`.agent-canon/`、`target/`
には出力しません。

`sync` は typed host Git adapter を通して、別リポジトリ
[`iwashita-nozomu/agent-canon-log`](https://github.com/iwashita-nozomu/agent-canon-log) へ
append-only の archive として公開します。branch と retention は log repository が所有
します。通信や archive が失敗したら spool と failure receipt を残して再試行します。
push 後の remote ref/tree/blob readback まで成功扱いにしません。

## Target mode とコンテナ

通常は `read-only` target を使います。意図的な source mutation は
`explicit-target-write` を持つ operation だけが、target、allowed paths、purpose、
before/after、receipt を要求して行います。

tool container は全プロジェクトで共有する一個だけです。CPU 2、memory 4 GiB、PIDs 512、
network 無効、read-only rootfs、capability 全 drop、`no-new-privileges`、task timeout
30分、termination grace 10秒が既定です。daemon が rootful でも rootless でも分岐せず、
container process は常に non-root UID です。project image、project test、GPU、Docker
socket、host HOME、GitHub token は渡しません。

## 失敗、rollback、終了

target 変更は active task が0になるまで admission を閉じて generation を切り替えます。
active task 中は `mount_update_blocked`、candidate の health/readback 失敗は candidate
quarantine と旧 generation 維持、旧 generation も復旧できなければ
`runtime_unavailable` です。`status` で generation、container、mount、limit、receipt
を確認し、必要なら active task がない状態で `rollback` します。

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" stop
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" gc
"$BOOTSTRAP" --control-parent-root "$ROOT" --runtime-root "$RUNTIME" uninstall
```

`stop` は container を消して state と未同期 spool を残します。`gc` は完了かつ pin の
ない、この installation の所有物だけを削除します。`uninstall` は managed image、
container、links、state を削除しますが、親レポ、global Codex、pre-existing Docker
resource は削除しません。uninstall 前に `eval sync`、`status`、archive readback、
resource absence を確認してください。`docker system prune` は使いません。

## AgentCanon を編集する場合

Template や派生 repo の編集は、親レポが指定する ignored clone
`workspace/agent-canondevelop/<qualified-task>/agent-canon` で行います。親レポに
submodule、vendor checkout、source symlink、AgentCanon の tests や eval 名を追加しません。
AgentCanon を変更したら AgentCanon 側の branch/PR/main readback を完了し、親レポ側は
その後に必要な source revision だけを更新します。

Issue の責務を混ぜないでください。[#841](https://github.com/iwashita-nozomu/agent-canon/issues/841)
は local bootstrap、shared runtime、source side-effect、skill isolation、eval/archive
lifecycle、[#821](https://github.com/iwashita-nozomu/agent-canon/issues/821) は prebuilt
artifact の build/distribution です。

## 詳細な owner

- [Standalone Bootstrap And Shared Tool Runtime](../documents/runtime/bootstrap-runtime.md)
- [Container Operations](../CONTAINER_OPERATIONS.md)
- [Runtime Log Archive](../documents/runtime/runtime-log-archive.md)
- [Runtime Profiles And Check Matrix](../documents/runtime/runtime-profiles-and-check-matrix.md)
- [AgentCanon Update Skill](skills/agent-canon-update.md)
