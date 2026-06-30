<!--
@dependency-start
contract policy
responsibility Documents ドキュメント運用 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../../../agents/skills/formal-proof-workflow.md mathematical claim grounding policy
downstream implementation ../../../tools/agent_tools/check_convention_compliance.py validates document claim grounding
downstream implementation ../../../tools/agent_tools/task_close.py validates document split decision closeout evidence
@dependency-end
-->

# ドキュメント運用

この章は、`documents/` の運用と Markdown の体裁に関する共通方針をまとめます。

## この文書の読み方

- この文書は、文書更新、依存関係明示、Markdown 体裁、claim grounding、
  規範表現、受け入れ条件、検証を定めます。
- 主な順路は、要約、規約、Claim Grounding、規範表現、受け入れ条件、検証です。
- `documents/` 配下の正本文書を作成または更新する前に読みます。
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
- 文書を分割、統合、移動、または現状維持する Markdown 変更では、
  `document_split_decision` を記録します。判断候補は
  `keep:<reason>`、`split:<new-owner-boundary>`、`merge:<target>`、
  `inline:<target-section>`、`rename:<new-path>`、
  `not_applicable:format-only:<reason>` のいずれかにします。
- 実装への参照は、実装ファイル名や実装上の制約を明示する必要がある場合に限ります。
- 各 `.md` ファイルは、タイトル、短い導入、`##` 見出しごとの本文という流れを基本にします。
- workflow、依存関係、責務境界、状態遷移、routing、review gate、multi-step 手順を説明する reader-facing Markdown では、Mermaid 図を既定の visual 候補にします。
- Mermaid 図は Markdown 内の fenced `mermaid` code block として保持し、本文の責務説明と併記して正本化します。
- Mermaid 図は本文と併用します。図の直前または直後に、図が答える問い、読者が入口として見る node / edge、本文で扱う制約を短く書きます。
- リポジトリ root の `.markdownlint.json` を Markdown 体裁チェックの既定設定として扱います。
- Markdown は `markdownlint` に準拠させ、例外が必要な場合は設定ファイルと規約文書を同時に更新します。
- まとまった Markdown 変更の前後では、少なくとも変更したファイルに対して `markdownlint` を実行して体裁崩れを確認します。
- 空行は 1 行に保ち、見出しには本文または箇条書きを続けます。
- 箇条書きは `-` を基本にし、パス・識別子・コマンドはバッククォートで示します。

## Document Split Decision

`document_split_decision` は、文書構造変更の自動判定に使う machine-readable
field です。本文量や分割読みの都合ではなく、文書責務、読者、source map、
validation route、更新頻度、正本 owner の組み合わせで判断します。

- `keep:<reason>`: 同じ owner、reader、source map、validation route、update cadence
  で読める内容は同じ文書に残します。章、reader map、Mermaid 図、または
  section contract で読者順序を直せる場合は `keep` を選びます。
- `split:<new-owner-boundary>`: 新しい責務 owner、別読者、別 validation route、
  別 source map、または独立した update cadence を持つ内容は別文書に分けます。
- `merge:<target>`: 2 つ以上の文書が同じ owner、reader、source map、
  validation route、update cadence を持ち、差し替え可能な境界を作らない場合は
  正本側へ統合します。
- `inline:<target-section>`: 独立文書にするほどの owner boundary がなく、親文書の
  受け入れ条件、例外、検証経路の一部として読むべき内容は section に戻します。
- `rename:<new-path>`: 責務は変えず、path 名だけが reader map または documents
  index とずれている場合に使います。
- `not_applicable:format-only:<reason>`: typo、link、format-only の変更で文書構造に
  触らない場合に使います。

受け入れ条件:

- `structure-planning` の `document_unit` は、owner、reader、source map、
  validation route、update cadence、canonical parent、downstream consumers を
  列として持ちます。
- `split_when` は上の `split` 条件のどれが成立したかを示します。
- `merge_when` は同じ owner、reader、source map、validation route、update cadence
  が揃い、別文書にしたときの差し替え可能な責務境界がないことを示します。
- `invalid_split_boundaries` は、本文量、token 量、読み込み chunk、章番号、近い path、
  一時的な作業都合、同じ validation oracle を共有する連続説明を含めます。
- closeout の Document Structure Evidence は `document_split_decision` を記録し、
  `python3 tools/agent_tools/check_convention_compliance.py` と
  `python3 tools/agent_tools/task_close.py` がこの field の有無を確認します。

## Claim Grounding

- `claim grounding` では、正本文書の claim を evidence class と一緒に書きます。
  evidence class は、実装 path、設定 surface、checker / tool output、
  proof obligation、外部 source packet、または run-local planning evidence の
  いずれかです。
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
- Provisional wording such as `まずは`, `for now`, or `first pass` belongs to run-local planning evidence.
  正本文書では、同じ内容を受け入れ条件、scope、
  validation route、または明示的な limitation として書きます。
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

- この文書の規範表現、positive label、検証経路は `python3 tools/agent_tools/check_convention_compliance.py` で確認します。
- `claim grounding`、provisional wording、proof obligation の wiring は
  `python3 tools/agent_tools/check_convention_compliance.py` で確認します。
