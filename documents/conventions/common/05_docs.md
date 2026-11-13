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

- この文書は、文書更新、依存関係明示、Markdown 体裁、claim grounding、
  規範表現、受け入れ条件、検証を定めます。
- 主な順路は、要約、規約、Claim Grounding、規範表現、受け入れ条件、検証です。
- `documents/` 配下の正本文書を作成または更新する際、該当する節だけを読みます。
- 境界: 個別文書の責務や正本リンクは、その文書の dependency header と
  documents index が所有します。

## 要約

- 変更が入った場合は文書も更新します。
- 役割と依存関係を明示します。
- 文書は単体で読める入口と、必要な参照先を持ちます。
- 規範は共通ラベルで整理し、規約の性質を明示します（`必須`、`許可`、`任意`、`受け入れ条件`、`例外`）。

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
- Mermaid 図は本文と併用します。図の直前または直後に、図が答える問い、読者が入口として見る node / edge、本文で扱う制約を短く書きます。
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
- 親文書の受け入れ条件、例外、検証経路の一部は、独立 owner がない限り親の section に
  戻します。
- 責務を変えず path 名だけが reader map や documents index とずれた文書は、正本の path
  を整理します。
- typo、link、format-only の変更は、文書構造変更として扱いません。

## Claim Grounding

- `claim grounding` では、正本文書の claim を evidence class と一緒に書きます。
  evidence class は、実装 path、設定 surface、checker / tool output、
  proof obligation、または外部 source evidence のいずれかです。
- 数学的 claim は、claim、assumptions、definitions、theorem target または
  proof obligation、`proof_status`、checker evidence を分けて書きます。
  実装由来の数学 claim は public entrypoint、入力 schema、戻り値 projection、
  実装 trace / checker evidence へ接続し、`$formal-proof-workflow` の証明状態表へ渡します。
- 数学的判定は `mathematical necessity gate` を通します。判定ごとに
  `Judgment / Mathematical Role / Necessity Evidence / Owner / Validation Route`
  を固定し、`necessary-and-sufficient condition`、program contract の
  precondition / invariant / postcondition、theorem target / proof obligation、
  user request、approved design のいずれかから採用根拠を示します。
- 採用根拠が未接続の判定候補は `non-contractual mathematical judgment` として
  proof / review backlog へ回し、実装 branch、runtime diagnostic gate、
  test oracle、checker pass condition へ昇格する前の修復対象にします。
- `program contract` は実装由来 claim の入口です。public entrypoint、入力 schema、
  設定 / runtime profile、return projection、observable state / effect、
  assumptions / preconditions、validation command を並べます。
- 実装 claim は、対象 file / symbol / command と validation route を添えます。
  未実装 behavior の文書形は、設計候補または open obligation です。
- Provisional wording such as `まずは`, `for now`, or `first pass` remains draft language.
  正本文書では、同じ内容を受け入れ条件、scope、validation route、または明示的な limitation
  として書きます。
- 誇張に見える claim は、測定対象、条件、evidence path、`proof_status` を持つ
  限定 claim へ分解します。`verified` は checker が通った artifact と対応している場合に
  使います。

## 規範表現

- `documents/` 配下の正本文書では、実行条件を `必須`、`受け入れ条件`、`完了条件`、`例外` などの positive label で整理します。
- `documents/` 配下の正本文書では、必須事項を `必須`、`必要です`、`実行します` などの肯定形で明記します。
- `documents/` 配下の正本文書では、許可事項を `許可` と明記します。
- `documents/` 配下の正本文書では、任意事項を `任意` と明記します。
- 例外がある場合は `例外` 見出しまたは `例外:` ラベルで条件を限定して明記します。
- 遵守確認対象の規約では、`原則`、`望ましい`、`できれば`、`構いません`、`してよい`、`必要なら` などの曖昧語を、該当する positive label へ置換して明示します。
- `推奨` は非拘束の参考情報または読了順の案内に限定し、必須条件や完了条件は直接の positive label で書きます。
- 規制目的の規定がある文書は、まず `## 受け入れ条件`、`## 完了条件`、`## 実行条件` などの独立見出しで整理し、本文内で条件を追跡しやすい形にします。
- 既存文書に残っている曖昧な規範表現は、更新タイミングを見て移行対象として取り、次回作成／改訂時に positive label へ置換します。

## 受け入れ条件

- 規約の可読性は、曖昧表現を具体的な positive label へ置換できているかで評価します。
- `推奨` の使用範囲は参考情報までに限定し、必須条件や完了条件は直接の positive label に置き換えます。
- Mermaid 図を追加する場合は、図の前後で責務説明・入力・出力・例外・検証経路の本文を同時に置き、文書全体で正本が成立する状態を確認します。

## 検証

- この文書の規範表現、positive label、検証経路は `agent-canon check-convention-compliance` で確認します。
- `claim grounding`、provisional wording、proof obligation の wiring は
  `agent-canon check-convention-compliance` で確認します。
