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

主要な結論と判断理由を同じ段落に置きます。決め手となった事実と、その事実が判断基準を
満たす理由を本文で述べ、根拠資料へリンクします。
たとえば「新版を採用できます。全12件で集計値が一致し、採用基準の全件一致を満たしたためです。」

1. At normal work boundaries, retain established findings and evidence in the
   existing task/Issue record, rather than reconstructing them from memory at
   closeout. Before each output, reconcile that record with the results obtained
   so far. Organize each distinct finding using the relationships below. These
   are semantic relationships, not prescribed output columns or headings;
   no empty fields or serialization are required.

   | Relationship | Content |
   | --- | --- |
   | Established fact | What was observed or demonstrated; distinguish inference and hypothesis |
   | Evidence | Observed result and its source, with a link to the existing record |
   | Meaning and scope | What the result establishes for the reader |
   | Limits and contrary evidence | Failed or unrun checks, blockers, counterevidence, rejected hypotheses and reasons |
   | Disposition | Decision and its factual basis |

2. Merge repeated observations, not distinct findings. Preserve each established
   in-scope result and material counterevidence even when no code change follows,
   it does not support the final conclusion, later verification fails, or the
   overall task is unfinished. Preserve unresolved hypotheses as hypotheses.
   When new evidence corrects a result, retain the correction and its reason;
   do not keep presenting the superseded claim as current.
3. Check both directions before writeout: each output claim has evidence or is
   labelled as inference, and each established finding has a place in the output
   or an explicitly identified retained record. Do not silently omit facts to
   shorten the response. Unrun is not passed, partial validation is not complete
   validation, and a document edit is not evidence of runtime behavior.
   For parent/worker execution failures, preserve process-local scope and
   counterevidence through the existing [execution diagnosis owner](../canonical/ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis);
   do not generalize a child's access failure into a host/environment defect.
4. Before drafting, [choose the presentation](#choose-the-presentation) from this
   structure. Write to the applicable, authorized destinations in the current task.
   Adapt presentation, not facts or their limits. For Issue-backed work, leave
   comparable conclusions, grounds, and limitations on the Issue and
   the applicable PR body/comment as well as chat; a link alone is insufficient.
   Progress updates may carry the new or corrected findings and identify the
   earlier retained results; final reports consolidate the current result.
   Refer to the existing evidence for procedures and execution details.
5. On interruption or publication failure, write out the established portion and
   separate the unverified or unpublished portion with its reason and next
   owner/action. Retain the result for the existing publication route; never
   claim a destination was updated without that route's readback. A blocked
   destination does not erase results or justify withholding them from another
   authorized output.

## Completion reports

Build a task completion report from the retained findings and decisions. Lead
with the requested outcome, its concrete effect, and the completed scope. Explain
the material approach choices before giving supporting validation and limits.

For an approach actually tried that affected implementation, validation, or the
conclusion, state its purpose, observed result, grounds for retaining, rejecting,
or replacing it, and effect on the final choice. Preserve a material failed
attempt after a successful retry. Identify relevant source-based assessments and untried
proposals as such; distinguish observed outcomes from hypotheses about causes
or expected benefits.

Put these decisive findings and choice grounds in the final chat itself. Use
Issue, PR, and artifact references for supporting detail; a link or a statement
that the details were recorded cannot replace that explanation. Carry the
relevant validation coverage, remaining uncertainty, and delivery state through
the existing result structure.

Choose detail by the significance of the findings and decisions. Include
material discarded approaches and the observations that decided them.

## Choose the presentation

After structuring the content and before drafting or revising the output, choose
its form by the relationship the reader needs to see. Honor explicit user and
destination format requirements. Structuring does not imply a table, list,
fixed headings, or the same layout for every destination.

| Information relationship | Suitable form |
| --- | --- |
| Compare multiple targets or map them across shared attributes | Table with meaningful row and column labels |
| Enumerate independent findings or actions with no meaningful order | Bulleted list |
| Show execution order, dependencies, or a meaningful sequence | Numbered list |
| Explain a conclusion, rationale, cause, context, or qualification | Prose |

Choose per section when relationships differ: a short conclusion, a comparison
table, and an explanation can coexist. Use prose for a single brief point; do
not fragment connected reasoning into bullets or invent a comparison axis to
justify a table. Keep cells concise and columns relevant. When long explanations,
sparse cells, or excessive width make a table harder to read, move explanations
to prose or use a list instead. Never omit material evidence or qualifications
to fit a layout, and keep them visibly associated with the finding they support.

Before writeout, check that the form exposes the intended comparison or order,
reads clearly at the destination's width, and preserves the facts and limits
already structured. Change the form rather than distort the content. This is
part of the existing writing step, not a separate approval or validation gate.

Keep credentials and private logs within their authorized storage.
