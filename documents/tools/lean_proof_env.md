<!--
@dependency-start
contract reference
responsibility Documents the native Lake and Lean boundary of lean_proof_env.py.
upstream implementation ../../tools/analysis/proof/lean_proof_env.py runs native setup and selected checks
upstream design ../../agents/skills/formal-proof-workflow.md owns proof workflow selection
upstream design lean_capability_matrix.md distinguishes proof and theorem-search capabilities
@dependency-end
-->

# Lean proof environment

`tools/analysis/proof/lean_proof_env.py` は、選択済みの Lake package で証明自動化、
LeanSearchClient の公開型、Plausible の反例検査を実行する入口です。
package・依存・toolchain の設定と更新は Lake の標準形式を正本とし、この tool で再生成しません。

## 実行境界と使い方

以下は既存の認可済み proof/tool runtime 内で実行する CLI payload です。
ホストへの直接実行、別 runtime の作成、ネットワーク・再実行制限の解除を認める例ではありません。
`RUNTIME_ROOT` は既存の外部 artifact 保存先、`--env-dir` は今回使う package の実体を指定します。

```bash
python3 tools/analysis/proof/lean_proof_env.py init \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --lean-toolchain "<selected exact toolchain>" --execute --format json
python3 tools/analysis/proof/lean_proof_env.py all-smoke \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" --execute --format json
python3 tools/analysis/proof/lean_proof_env.py check-file \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --lean-file "$RUNTIME_ROOT/tasks/formal-proof/example.lean" --execute --format json
```

`--execute` を省略すると計画だけを返し、directory、設定、probe を書きません。
`status=dry_run` は検査成功ではありません。新規 package では
`--lean-toolchain` で exact toolchain を選びます。既存 package はその
`lean-toolchain` 宣言を使い、明示 selector と食い違えば失敗します。既存の
`--env-dir`、`--lean-file`、`--package-name`、`--format` と action 名は引き続き使用できます。

| action | 実行する確認 |
| --- | --- |
| `init` | 必要な場合だけ標準 `lake +<selected-toolchain> init <package-name> math` と native version readback |
| `smoke` | Aesop、Mathlib、omega、linarith、grind、真の Plausible property |
| `agent-smoke` | LeanSearchClient の import と公開型。外部検索サービスは呼ばない |
| `counterexample-smoke` | Lean の `#guard_msgs` による期待した反例診断の確認 |
| `all-smoke` | 上記3つの probe |
| `check-file` | 指定した Lean file を同じ Lake package context で確認 |

## 所有権と更新

空の directory では `--lean-toolchain` で選択した toolchain の標準 `math` template が
初期化を所有します。`lean-toolchain` だけがある directory も標準初期化の入力として
受け入れ、その宣言を選択値として使います。既存 `lakefile.lean` / `lakefile.toml` がある場合は
その package を使い、Python は設定を上書きしません。Lake 設定のないその他の非空 directory は
拒否し、旧環境の削除や自動改造を行いません。

既存 package は `lean-toolchain` ファイル、または明示 selector が必要です。全 native command は
`lake +<selected-toolchain>` で同じ選択を使います。確認時は Lake/Lean の native version を記録し、
`lake --keep-toolchain build` と `lake --keep-toolchain env lean <file>` を実行します。
毎回の `lake update` は行いません。
依存未取得時に Lake が行う取得・build は、その package と runtime の既存契約に従います。
依存を変更する必要がある場合は、project owner が標準の Lake 設定・manifest を更新します。
選択した `lean-toolchain` と、native manifest の `mathlib_revision` を結果から確認できます。

手書き Lakefile、再export用 root module、独自の Lean/Mathlib default revision は撤去しました。
`--lean-toolchain` に固定 default はありません。`--mathlib-rev`、`--module-name`、`--force` は
使いません。Lake の標準設定と exact toolchain 選択を使い、互換 flag や別設定 schema は設けません。

Python が書くのは選択した smoke source だけです。同内容は再利用しますが、異なる既存内容や
symlink は上書きしません。旧版が生成した probe と衝突した場合は、所有者がその probe の差分を
確認して移行するか、別の空の作業用 directory を選びます。package 全体を消して解決しません。

## 成功・失敗の意味

反例用の proposition は `forall (n : Nat), n < n` です。どの標本も反例となるため、
たまたま反例を発見できるかに依存する命題を使いません。`quiet := true` による診断を
Lean 自身の `#guard_msgs` が確認します。期待診断の欠落、追加の型エラー、import failure は
Lean の通常の検査失敗です。Python は stdout の部分文字列を見て nonzero を 0 に変換しません。

各 command の argv 表示、native stdout/stderr、終了コードを結果へ残し、最初の nonzero で
後続 command を起動しません。外部 file のパスは1つの argv 要素として渡します。
`lean_toolchain` は実在する package file の読取値、`lake_version`、`lean_version` は成功した
native version command の出力です。`lake_manifest` は実在する native manifest の保存先、
`mathlib_revision` はその manifest にある Mathlib package の解決済み revision です。dry-run では
選択値は表示commandの argv に残りますが、native readback として扱いません。

`initialized`、`checked`、`failed`、`dry_run` を区別します。smoke 成功は個別定理の証明完了でも、
LeanSearchClient の外部サービス疎通でもありません。期待反例の成功は反例検出機能の確認です。

## 検証

既存 `tests/agent_tools/test_lean_proof_env.py` は process fake を用いて、exact toolchain 選択、
toolchain-only bootstrap、native command、manifest/version readback、既存設定の保全、no-write dry run、
初期化/build/Lean失敗時の停止、native終了コードの保持を確認します。
これだけで実際の Lean/Mathlib/Plausible の互換性を検証したとは扱いません。

正規 runtime では、同じ package で `all-smoke` と `check-file` を実行します。
`example : True := by trivial` が成功し、`example : False := by trivial` が nonzero になること、
反例 probe に別の型エラーを加えた file も nonzero になることを分けて確認してください。
反例成功のログ文字列が含まれていても、別のエラーがある file を成功扱いしない回帰です。
検証に使った source head、native version、native manifest、command と実結果を Issue/PR に残します。

AgentCanon source の native regression には、既存の disposable test image を使う
`bash tests/bootstrap/docker.sh lean-proof` を用います。`lean-proof` profile は同じ
disposable test container 内で既存の typed dependency installer を実行し、container 内の
一時 install workspace と task-owned runtime に exact Lean toolchain を導入してから、
`all-smoke` と `check-file` の成功・失敗例を同じ Lake package で確認します。Lean は default の
`live-projection` profile では導入しません。
この profile は Docker socket、host home、credential を mount せず、通常の proof
作業用 runtime や共有 AgentCanon tool image を変更しません。

```bash
bash tests/bootstrap/docker.sh lean-proof
```

この entrypoint は host Docker CLI を使い、task-owned の一時 workarea と runtime を
作成し、image とともに task 終了時に削除します。これは source qualification route であり、
通常の proof package を実行する runtime の選択や構築方法を変更するものではありません。

## 根拠

- [Lake の package 作成と標準 CLI](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/)
- [Lean の診断検査コマンド](https://lean-lang.org/doc/reference/4.30.0/Other-Commands/)
- [Mathlib v4.30.0 が選ぶ依存](https://github.com/leanprover-community/mathlib4/blob/v4.30.0/lake-manifest.json)
- [同依存の Plausible.Testable.check](https://github.com/leanprover-community/plausible/blob/a456461b368b71d2accd95234832cd9c174b5437/Plausible/Testable.lean)

これらは設計・API確認の根拠であり、利用者の稼働環境で実行したという証拠ではありません。
