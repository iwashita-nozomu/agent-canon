<!--
@dependency-start
contract policy
responsibility Documents ドキュメント運用 for this repository.
upstream design ../../../agents/skills/formal-proof-workflow.md mathematical claim grounding policy
downstream design ../../../agents/skills/structure-planning.md applies responsibility and reading-activation split decisions
downstream design ../../../agents/skills/structure-refactor.md repairs overloaded document boundaries
downstream implementation ../../../tools/runtime/dispatch/agent-canon/src/docs.rs enforces Markdown math notation and fence rules
downstream implementation ../../../tools/runtime/dispatch/agent-canon/src/convention_compliance.rs validates document claim grounding
@dependency-end
-->

# ドキュメント運用

この章は、`documents/` の運用と Markdown の体裁に関する共通方針をまとめます。

## この文書の読み方

- この文書は、文書更新、依存関係、Markdown の体裁と根拠の示し方を扱います。
- `documents/` 配下の正本文書を作成または更新する際、該当する節だけを読みます。
- 境界: 個別文書の責務や正本リンクは、その文書の dependency header と
  documents index が所有します。

## 要約

- 変更が入った場合は文書も更新します。
- 役割と依存関係を明示します。
- 文書は単体で読める入口と、必要な参照先を持ちます。
- 説明文書には一般的な事実と根拠を記載します。操作手順と実行条件は、
  それらを管理する既存の手順書や実行記録を参照します。

## 規約

- 変更が入った場合は、該当する `documents/` 内の文書を同時に更新します。
- モジュールの役割と依存関係は、文書に明示します。
- 文書は **そのファイル単体で概要と主要判断が読める**ように書きます。
- 長めの reader-facing Markdown、または分割読みされる可能性が高い Markdown は、
  先頭付近に reader map を置きます。reader map は、その文書が扱う内容、
  主な章のまとまり、読むべき場面、誤用を避ける境界を短く示します。
- `documents/` 内の編成は、参照先の一覧ではなく、責務ごとの分割を優先します。
- 実装への参照は、実装ファイル名や実装上の制約を明示する必要がある場合に限ります。
- 読者が移動する意味を持つ文書または skill の参照は、標準 Markdown リンクで記述します。
  リンク先は、リンクを含む Markdown ファイルを基準にした相対 path とし、存在する
  `.md` ファイルと必要な fragment（`#section-anchor`）だけを指定します。path に空白がある場合は
  `%20` にエスケープし、リンク label は読者に対象が分かる名前にします。path を label に
  含めるかどうかは可読性で選べます。例えば、この規約の関連 skill は
  [`Markdown style check`](../../../agents/skills/md-style-check.md) として参照します。
- 文書ナビゲーションではない command、実行例、glob、placeholder、machine-readable header
  / directive（`@ROOT_AGENTS.md` を含む）、および literal output は code span または
  code block のままにします。skill の invocation syntax（`$skill-name`）も literal のままにし、
  reader-facing な skill の正本参照だけを canonical `agents/skills/<skill>.md` へリンクします。
- `[[wikilink]]` は採用せず、存在しない file や section への fake link も作りません。
  生成 consumer template のリンクは、展開後の containing file を基準に解決するため、
  source checkout 内だけで成立する相対 path に合わせて書き換えません。
- 各 `.md` ファイルは、タイトル、短い導入、`##` 見出しごとの本文という流れを基本にします。
- workflow、依存関係、責務境界、状態遷移、routing、review gate、multi-step 手順を説明する reader-facing Markdown では、Mermaid 図を既定の visual 候補にします。
- Mermaid 図は Markdown 内の fenced `mermaid` code block として保持し、本文の責務説明と併記して正本化します。
- Mermaid 図には、図が示す関係を本文で短く説明します。
- Markdown の整形は、変更したファイルを対象に AgentCanon の `agent-canon docs format` を実行します。
  [Markdown style check の実行手順](../../../agents/skills/md-style-check.md#procedure) に従い、共有 runtime と登録 target を使います。
- 体裁チェックの設定はリポジトリ root の [`.markdownlint-cli2.jsonc`](../../../.markdownlint-cli2.jsonc) を使います。
  例外が必要な場合は設定ファイルと規約文書を同時に更新します。
- 空行は 1 行に保ち、見出しには本文または箇条書きを続けます。
- 箇条書きは `-` を基本にし、literal な path・識別子・command はバッククォートで示します。
  reader-facing な文書・skill の navigation は、上記の標準 Markdown link を使います。

## 数式の表記

- インライン数式は `$...$` で記述する。
- 表示数式は double-dollar delimiter をそれぞれ独立行に置き、block の前後に
  空行を入れる。
- 数式の記述先は、本文中の inline `$...$` と standalone double-dollar block の
  2 形式に限定する。
- fence info の listed aliases は大文字・小文字の双方を同一 alias として正規化し、
  すべて同じ数式表記規約に従う。`text` / `plaintext` / `txt` / `plain` は literal
  output 用、`math` / `latex` / `tex` は standalone display math への移行対象として
  扱う。

## 文書構造の判断

文書を分割、統合、移動、または現状維持する場合は、本文量ではなく、責務、読者、読む
契機、source map、validation route、更新頻度、正本 owner の組み合わせで判断します。
読む契機は、その内容が必要になる判断・操作です。同じ owner や読者でも、通常実行と
環境再構築のように独立して必要になる手順は別の読取責務です。

- 同じ責務の読者順序を見出し、reader map、Mermaid 図、section contract で直せる場合は、
  正本に残して構成を整えます。
- 新しい owner、別読者、独立した読む契機、別 validation route、別 source map、または
  独立した update cadence を持つ内容は別の正本を検討します。
- 同じ owner と読む契機を持ち、差し替え可能な境界がない文書は正本側へまとめます。
- 責務を変えず path 名だけが reader map や documents index とずれた文書は、正本の path
  を整理します。
- typo、link、format-only の変更は、文書構造変更として扱いません。

## Claim Grounding

文書の主張は、仕様、実装、観測結果、論文などの根拠へつなぎます。
数理的な主張は結論の意味に必要な定義と仮定を示します。
検証用の入力、コマンド、判定は、対応するテストや実行記録を参照します。

## 検証

体裁とリンクは既存の `agent-canon docs check` で確認します。
