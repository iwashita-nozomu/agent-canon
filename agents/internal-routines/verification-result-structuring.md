# Writing and verification results

<!--
@dependency-start
contract agent-runtime
responsibility Guides prose and ties verification conclusions to existing evidence.
upstream design ../../ROOT_AGENTS.md portable evidence and delivery boundary
upstream design ../skills/README.md internal skill visibility boundary
downstream design ../canonical/ROOT_DELIVERY.md general writing, chat, and handoff caller
downstream design ../skills/report-writing.md report drafting caller
downstream design ../skills/pr-processing.md Issue and PR publication caller
downstream design github-connected-work.md connected publication caller
downstream design README.md internal routine index
@dependency-end
-->

## Terms and translation

1. Read unfamiliar terms against the relevant specification, source definition,
   or existing project usage. Keep the same term for the same concept and make
   a changed meaning explicit. If the meaning is unresolved, state that gap.
2. At first use, briefly explain a necessary term's role in this task. An acronym's
   English expansion alone may leave that role unclear. When the reader has no
   reason to learn an internal name, describe the actual action or object instead.
3. In Japanese, use a conventional Japanese term or retain the established
   original spelling. Preserve searchable product, API, command, and identifier
   names. Explain them in ordinary Japanese instead of coining a Japanese name.

Apply these decisions while drafting and rereading. A brief inline explanation
usually suffices; a glossary is useful only when the document needs repeated
reference. Use [notation-definition review](notation-definition-review.md) for
an unresolved definition or inconsistent meaning that needs separate review.

## Japanese revision

説明文は肯定形で書き、対象・目的・作用・結果を直接述べます。
否定形による説明を禁止します。例えば「私は既存の学習経路で損失を変更し、
学習を実行します」と、主体と実行内容を肯定形で示します。

返答・進捗・完了報告では、各文から「誰・何が、何に対して、何をしたか」が
分かるように書きます。処理主体や対象が切り替わる文・箇条書きには、その名前を
明示します。完了・成功・失敗を報告するときは、処理名と対象を含めます。
例えば「取り込みました」は「私は修正PRをmainへマージしました」、
「成功しました」は「CIのLinux版起動試験が成功しました」と具体化します。
主体を確認できない場合は、その主体が未確認であることを明記します。

日本語を推敲するときは、動作主・対象・述語を確かめ、操作や結果が追えない抽象語・
比喩を、資料で確認できる内容へ具体化します。接続語・指示語、修飾・否定・条件の
掛かり先を読み直し、文を分割・統合しても関係を保ちます。資料にない主体や因果は
補いません。自然な表現、意味を担う比喩、必要な専門用語や箇条書きはそのまま使います。

推敲前後で、数値・対象・時制・主張の比重、断定と可能性、許可と義務、説明・依頼・
予定の区別を照合します。次の例では、右欄の条件を維持します。

| 原文 → 推敲例 | 保持する意味・根拠 |
| --- | --- |
| 「APIが入力を整える」→「APIが入力の前後の空白を除去する」 | 空白除去が前後の説明や実装から確認できる場合の具体化 |
| 「入力が妥当な場合、APIは結果を保存できる」→「入力が妥当なら、APIは結果を保存できる」 | 妥当性の条件と可能性。「必ず保存する」へ変えない |
| 「実装は完了。検証は明日予定」→「実装は完了しました。検証は明日行う予定です」 | 実装の完了と検証の予定 |
| 「設定変更後に処理が失敗。変更者は不明」→「設定変更後に処理が失敗しました。変更した担当者は不明です」 | 時間的な順序と不明な主体。担当者や因果を創作しない |
| 「readbackする」→「保存した内容を読み直し、期待した内容と一致するか確認する」 | 実際の確認内容を説明する。内部の手順名を新しい日本語名へ置き換えない |
| 「SCIPで定義を探す」→「SCIP（ソースコードの索引を交換するプロトコル）で定義を探す」 | 原語を保ち、読者に必要な役割を初出で説明する |

## Structure before writeout

主要な結論と判断理由を同じ段落に置きます。決め手の事実と、その事実が判断基準を
満たす理由を本文で述べます。仮定、重要な反証、検証の範囲は対応する判断に添え、
操作の詳細は既存の根拠資料を参照します。

観測したこと、そこからの推論、未確認の点を区別します。IssueとPRがある場合は、
チャットと同程度の結論・根拠・限界を記載します。進捗報告は新しく判明した結果を伝えます。

## Completion reports

依頼された結果、判断理由、実際に確かめた範囲を示します。採否を変えた試行があれば、
観測と判断理由を残します。公開・適用は確認できた状態を述べます。
未完了の結果は、残っている成果とその理由を明記します。

## Choose the presentation

説明は文章、比較は表、独立した結果は箇条書きにすると読みやすくなります。
読者と依頼に合う形を選び、各結論とその根拠を近くに置きます。
