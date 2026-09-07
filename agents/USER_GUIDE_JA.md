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
解析対象の project root とします。既定 runtime は install root の
`.runtime/` です。これは bootstrap だけが所有する ignored directory で、一般の
eval/report/log output を source tree に置く許可ではありません。

```bash
ROOT=<authorized-parent-root>
BOOTSTRAP=/path/to/agent-canon/bootstrap.sh

"$BOOTSTRAP" --control-parent-root "$ROOT" install
"$BOOTSTRAP" --control-parent-root "$ROOT" update
"$BOOTSTRAP" --control-parent-root "$ROOT" start
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  target add --root <project-root> --mode read-only
"$BOOTSTRAP" --control-parent-root "$ROOT" status
```

control root は必須です。runtime root を指定した場合も control root の下でなければ
ならず、symlink を通した脱出も拒否されます。`$HOME/.cache`、`$HOME/.local`、global
`CODEX_HOME`、source tree の一般ディレクトリを暗黙の保存先にしません。

## Codex を起動する

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" codex prepare
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  codex launch --project-root <project-root>
```

`prepare` は runtime root 内の isolated `codex-home/` に manifest 管理の skill、agent、
hook、設定リンクを作ります。これは global link とは別の実行用経路です。衝突する既存
パスは fail closed で、uninstall が削除できるのはこの installation が作成したリンクだけです。

control root に `$HOME` を明示した場合、install / update は次のリンクを管理します。

```text
~/.agents/skills               -> ~/agent-canon/.codex/personal/skills
~/.codex/agents/<role>.toml   -> ~/agent-canon/.codex/agents/<role>.toml
~/.codex/config.toml           -> ~/agent-canon/.codex/personal/config.toml
```

install / update は ignored な `~/agent-canon/.codex/personal/skills/` を
`~/.agents/skills` へディレクトリ単位でリンクします。旧skill farmの列挙や期待値照合は
せず、変更は `agents/skills/<skill>.md` と catalog に加えます。uninstall が削除するのは
AgentCanon所有のディレクトリリンクだけです。

既存の regular な `~/.codex/config.toml` は内容と mode を保持したまま ignored な
personal source に移してからリンクします。update はその内容を保持し、uninstall は
regular file に戻します。project hook、認証、session、history、cache、plugin、rule、
MCP、TUI/trust 設定はリンクしません。install / update 後は新しい Codex session を
起動してください。

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
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  tool run --root <project-root> <verified-catalog-id> -- <args...>
```

parity は argv、cwd、stdin/stdout/stderr、exit/signal、written paths を比較します。
未確認の内部Python entryはpublic bootstrap commandとして公開されません。

shell string、未知の catalog id、internal Python file の自動公開は許可しません。

## Eval と agent-canon-log

```bash
"$BOOTSTRAP" --control-parent-root "$ROOT" \
  eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" --control-parent-root "$ROOT" \
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
"$BOOTSTRAP" --control-parent-root "$ROOT" stop
"$BOOTSTRAP" --control-parent-root "$ROOT" gc
"$BOOTSTRAP" --control-parent-root "$ROOT" uninstall
```

`stop` は container を消して state と未同期 spool を残します。`gc` は完了かつ pin の
ない、この installation の所有物だけを削除します。`uninstall` は managed image、
container、links、state を削除しますが、親レポ、foreign な global Codex entry、
pre-existing Docker resource は削除しません。AgentCanon が所有した exact link だけを
削除し、personal config は regular file に戻します。legacy の per-skill farm は列挙せず、
`~/.agents/skills` の AgentCanon-owned directory link だけを削除します。
uninstall 前に `eval sync`、
`status`、archive readback、resource absence を確認してください。`docker system prune`
は使いません。

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
