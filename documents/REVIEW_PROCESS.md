# レビュー手順とポリシー
<!--
@dependency-start
upstream design README.md durable document index
@dependency-end
-->


この文書は、コード、文書、workflow、環境設定の変更を main-first 運用で安全に閉じるための review 手順を定めます。
現行の agent canon、skill canon、artifact placement に合わせて、必要な review family と evidence の残し方を固定します。

## 適用範囲

- 既定の統合先は `main` です。
- レビューが必要な変更では、コード、テスト、文書、必要なら環境設定をまとめて確認します。
- repo-wide な workflow 改造、agent system の変更、研究系の完了判定にも適用します。

## 変更前に固定すること

- 変更スコープ
- 受け入れ条件
- user request clause
- clause ごとの source bucket
- 必要な review family
- 必要な validation
- evidence の保存先

run-local の review artifact は `reports/agents/<run-id>/` を正本にします。
repo-wide の恒久ルールは `documents/` と `agents/` に残し、run 固有メモを混ぜません。

## Review Family の選び方

- 局所実装の review
  - `change-review`
- Python 差分の review
  - `python-review`
- C / C++ 差分の review
  - `cpp-review`
- 大規模 refactor の review
  - `change-review`
  - `project_review`
  - language reviewer
  - docs consistency review
- Markdown / 文書差分の review
  - `md-style-check`
  - 長文なら docs completeness review
  - 必要なら docs consistency review
  - 文書が completion gate の一部なら `document_flow_reviewer`
  - readability や reader flow の accept / reject は tool check ではなく reviewer judgement で決める
  - 実装を説明する文書では、reader が現行実装だけで作業できること、旧挙動や旧手順が残っていないことを確認する
  - packet-first intake や workflow routing を変える場合は cross-doc coverage review
  - 学術文章なら notation review
  - 学術文章なら logic-gap review
- 研究・実験 scope の review
  - critical review
  - report review
  - 数式、擬似コード、仕様記述、method contract を伴う場合は、runtime success とは独立に equation/spec alignment を確認する
- methodology、benchmark protocol、artifact policy、reporting policy を大きく変える review
  - research perspective review pack
- repo-wide な棚卸しや canon 整理
  - `change-review` を基底にし、必要なら docs consistency review と research perspective review pack を追加

## 実行チェック

- 軽い検証では `make ci-quick` を使います。
- agent runtime / skill / canon 変更では `make agent-checks` を先に見ます。
- Python 差分を含む場合は、必要に応じて次を追加します。
  - `python3 -m pyright`
  - `python3 -m pytest tests/ -q --tb=short`
  - `python3 -m ruff check python tests --select D,E,F,I,UP`
- C / C++ 差分を含む場合は、project-native configure / build / test evidence を追加します。
  - CMake project なら `cmake -S . -B build`
  - CMake project なら `cmake --build build`
  - test target があれば `ctest --test-dir build`
- Markdown 差分を含む場合は、少なくとも `make docs-check` を実行します。
- `make docs-check`、lint、link check、smoke run は readability や reader flow の accept evidence ではありません。可読性は `document_flow_reviewer`、docs completeness review、または task に応じた reviewer judgement で確認します。
- README、workflow、guide、migration 文書のような長文では、`document_flow_reviewer` と別 reviewer による docs completeness review を省略しません。
- 学術文章では、`document_flow_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer による docs completeness review を省略しません。
- 論文や thesis chapter では、さらに `citation_evidence_reviewer` を省略しません。
- 実験結果や user-facing report を含む場合は、critical review と report review を省略しません。

## Review Flow

1. requirements review で scope、non-goals、acceptance criteria を確認します。
1. requirements review で `user_request_contract.md` の must-do、must-not-do、completion-evidence clause が揃っていることを確認します。
1. requirements review で、各 clause が `current_request`、`durable_user_preference`、`repo_or_code_precedent`、`domain_or_external_constraint`、`unknown_or_open_question` のいずれかに分類されていることを確認します。
1. requirements review で、過去ログ由来の user trait が現在の task requirement へ silent に混入していないことを確認します。
1. requirements review または management review で、導入済みライブラリ棚卸しと既存実装棚卸しを先に行い、何を見たか、何を再利用するか、既存では足りない理由が artifact に残っていることを確認します。
1. 必要なら research review で外部根拠と既存 code 調査の妥当性を確認します。
1. plan review で execution order、担当 subagent、rollback point を確認し、decision が `approve` でなければ planner に戻します。
1. detailed design review で reuse plan、existing-style adherence、design doc completeness を確認し、decision が `approve` でなければ designer に戻します。
1. detailed design review で、`Installed Libraries And Existing Implementation Survey` が dependency surface、導入済みライブラリ候補、既存実装候補、reuse / extend / replace / add-new の判断、既存では足りない理由を列挙していることを確認します。
1. detailed design review で、新規または rename する identifier、path、CLI flag、config key、public API が design または local precedent で固定され、worker が reusable / user-facing な名前を発明しなくてよいことを確認します。
1. detailed design review で、tree 上の親文書だけを読んで sibling / cross-cutting 文書を見落としていないか、`Cross-Doc Coverage Review` を確認します。
1. 数式、擬似コード、仕様記述、method contract を伴う task では detailed design review か checkpoint review で、implementation がどの式・仕様項目に対応するかを artifact に固定し、runtime success だけを acceptance 根拠にしないことを確認します。
1. 大規模 refactor では project review で stale path、delete 漏れ、cross-module drift、semantic delta 混入を確認します。
1. 大規模改修、統合、rename、構成変更では review 中に、旧実装 path、旧 helper 名、旧 guide / workflow / README / 規約文書 path への参照 sweep を行い、reader が削除済み・置換済み surface へ誘導されないことを確認します。残っていれば `fix now` です。
1. 長文文書では、別 reviewer による docs completeness review で reader が不足なく作業できるか確認します。
1. document flow review で、上から順に読んだときの section order、用語導入、reader path を確認し、decision が `approve` でなければ designer に戻します。
1. 学術文章では notation review で、記号、略語、technical term、unit、index、assumption の definition-before-use と一貫性を確認します。
1. 学術文章では logic-gap review で、claim-to-evidence のつながり、hidden assumption、result と interpretation の飛躍を確認します。
1. 実装中に checkpoint review を入れ、decision が `approve` でない限り implementer に戻します。
1. checkpoint review と final acceptance review では、旧実装、移行用の別経路、temporary fallback、implementation copy、dated snapshot、backup file が tracked tree に残っていないことを確認します。残っていれば `fix now` です。
1. checkpoint review と final acceptance review では、README、guide、workflow、規約文書が最新実装と一致し、削除済み・置換済みの挙動や手順を reader に案内していないことを確認します。文書が現行実装を説明できていなければ `fix now` です。
1. checkpoint review と final acceptance review では、README、guide、workflow、規約文書、script help、validation 出力が旧 implementation / 旧 document surface を参照していないことを確認します。参照が残っていれば `fix now` です。
1. checkpoint review と final acceptance review では、task が数式、擬似コード、仕様、protocol を持つ場合、implementation がその記述と一致しているか、どこに近似や逸脱があるかを確認します。run が成功しても alignment が崩れていれば `fix now` です。
1. checkpoint review と final acceptance review では、文書や prompt の readability / reader flow を tool 結果だけで accept せず、`document_flow_reviewer` や別 reviewer の judgement が artifact に残っていることを確認します。
1. review artifact が `revise`、`required_change`、または fix-now finding を返し、その指摘に応じて実装・文書・test・workflow を修正した場合は、修正の大小に関係なく required review family 全体を最新 diff に対してやり直します。直前の approve を流用して closeout してはいけません。
1. 各 review では artifact に `request_clause_ids` があるか確認し、無い場合は差し戻します。
1. final acceptance review では、全 must-do / completion-evidence clause が product surface、実装、文書、test、command、artifact、または明示された deferred / rejected clause に対応しているか確認します。
1. final acceptance review では、cross-cutting packet に含まれる文書のうち今回の task に効くものが review から漏れていないか確認します。
1. final acceptance review では、required review の `fix now` findings が実装へ反映済み、再レビュー済み、または明示的に escalated であることを確認します。
1. review artifact が `revise`、`required_change`、または `fix now` finding を返し、その後に code / docs / workflow / config の修正が入った場合は、その修正量に関わらず full required review set を最初から再実行します。
1. post-fix full review では、少なくとも `change_review.md`、`final_review.md`、task に必要な language / docs / specialist review artifact を最新の fix 後に作り直します。
1. validation 実行後に final acceptance review を行い、必要なら追加修正や追加検証を行います。
1. audit review で required reviews と evidence の欠落を確認します。
1. run 固有の review artifact は `reports/agents/<run-id>/` に残します。
1. repo-wide の恒久ルール変更がある場合は、対応する `documents/` または `agents/` の正本を同じ変更で更新します。

## マージ条件

- 必要な review family が完了していること
- requirements review、計画レビュー、詳細設計レビュー、文書通読レビュー、checkpoint review、final acceptance review、audit review が揃っていること
- 計画レビュー、詳細設計レビュー、文書通読レビュー、checkpoint review の decision がすべて `approve` であること
- `user_request_contract.md` の全 clause が source bucket を持ち、unknown が silent assumption に変換されていないこと
- 詳細設計の identifier naming plan が解決済みで、worker に命名裁量を残していないこと
- 詳細設計に導入済みライブラリ棚卸しと既存実装棚卸しがあり、新規追加が必要な理由が明記されていること
- 長文文書では、別 reviewer による docs completeness review も揃っていること
- 学術文章では、notation review と logic-gap review も揃っていること
- 対象に応じた validation 結果が確認されていること
- runtime success だけでなく、task に式、仕様、protocol、method contract がある場合は alignment evidence が review artifact に残っていること
- review-driven fix が入った場合、最新 diff に対する full review rerun evidence が残っていること
- 変更理由と影響範囲が追えること
- コンフリクトがないこと
- tracked tree に current tree head 以外の implementation truth や古い説明文書が残っていないこと
- README、guide、workflow、規約文書が最新実装を説明していること
- `verification.txt` が `status=pass` であること
- `closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` であること
- `closeout_gate.md` が `spec_product_coverage_complete=yes` かつ `review_findings_integrated=yes` であること
- `closeout_gate.md` が `post_fix_full_review_complete=yes` であること
- `user_request_contract.md` が `all_clauses_resolved=yes` かつ `forbidden_drift_detected=no` であること

## エビデンス保存

- run 固有の intake、design、review、verification、retrospective は `reports/agents/<run-id>/` に置きます。
- project-wide な分析や再利用する長文 report は `reports/` に置きます。
- 一時メモや cross-run の補助知見は `notes/` に置きます。
- dated な completion summary や古い review 文書を `documents/` や repo root に残すことを禁止します。
- current tree head 以外の design truth や implementation truth を tracked tree に残すことを禁止します。parallel design doc、implementation copy、snapshot tree、backup file は削除対象です。

## Findings の扱い

findings は少なくとも次に分けます。

- `fix now`
  - この変更で直さないと回帰や矛盾が残るもの
  - 修正後は、どんなに小さい差分でも full required review set を再実行する
  - 旧実装、移行用の別経路、temporary fallback、copied implementation、古い説明のままの README / guide / workflow を残すもの
  - runtime success はあるが数式、仕様、protocol、reader path と実装 / 文書が一致していないもの
- `follow-up`
  - 今回の受け入れを阻害しないが、後続で管理すべきもの
- `delete-ok`
  - stale asset や重複導線のように安全に削除できるもの
  - non-canonical design doc、implementation copy、dated snapshot のように tree head 以外の truth surface を増やすもの

## 関連正本

- [agents/TASK_WORKFLOWS.md](../agents/TASK_WORKFLOWS.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](../agents/canonical/ARTIFACT_PLACEMENT.md)
- [agents/skills/README.md](../agents/skills/README.md)
- [agents/workflows/workflow-references.md](../agents/workflows/workflow-references.md)
