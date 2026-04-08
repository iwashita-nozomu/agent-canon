# レビュー手順とポリシー

この文書は、コード、文書、workflow、環境設定の変更を main-first 運用で安全に閉じるための review 手順を定めます。
現行の agent canon、skill canon、artifact placement に合わせて、必要な review family と evidence の残し方を固定します。

## 適用範囲

- 既定の統合先は `main` です。
- レビューが必要な変更では、コード、テスト、文書、必要なら環境設定をまとめて確認します。
- repo-wide な workflow 改造、agent system の変更、研究系の完了判定にも適用します。

## 変更前に固定すること

- 変更スコープ
- 受け入れ条件
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
- Markdown / 文書差分の review
  - `md-style-check`
  - 長文なら `docs-completeness-review`
  - 必要なら `docs-consistency-review`
  - 文書が completion gate の一部なら `document_flow_reviewer`
  - 学術文章なら `notation-definition-review`
  - 学術文章なら `logic-gap-review`
- 研究・実験 scope の review
  - `critical-review`
  - `report-review`
- methodology、benchmark protocol、artifact policy、reporting policy を大きく変える review
  - `research-perspective-review`
- repo-wide な棚卸しや canon 整理
  - `change-review` を基底にし、必要なら `docs-consistency-review` と `research-perspective-review` を追加

## 実行チェック

- 通常の軽い検証は `make ci-quick` を使います。
- agent runtime / skill / canon 変更では `make agent-checks` を先に見ます。
- Python 差分を含む場合は、必要に応じて次を追加します。
  - `python3 -m pyright`
  - `python3 -m pytest tests/ -q --tb=short`
  - `python3 -m ruff check python tests --select D,E,F,I,UP`
- Markdown 差分を含む場合は、少なくとも `make docs-check` を実行します。
- README、workflow、guide、migration 文書のような長文では、`document_flow_reviewer` と別 reviewer による `docs-completeness-review` を省略しません。
- 学術文章では、`document_flow_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer による `docs-completeness-review` を省略しません。
- 論文や thesis chapter では、さらに `citation_evidence_reviewer` を省略しません。
- 実験結果や user-facing report を含む場合は、`critical-review` と `report-review` を省略しません。

## Review Flow

1. requirements review で scope、non-goals、acceptance criteria を確認します。
1. 必要なら research review で外部根拠と既存 code 調査の妥当性を確認します。
1. plan review で execution order、担当 subagent、rollback point を確認します。
1. detailed design review で reuse plan、existing-style adherence、design doc completeness を確認します。
1. 長文文書では、別 reviewer による docs completeness review で reader が不足なく作業できるか確認します。
1. document flow review で、上から順に読んだときの section order、用語導入、reader path を確認します。
1. 学術文章では notation review で、記号、略語、technical term、unit、index、assumption の definition-before-use と一貫性を確認します。
1. 学術文章では logic-gap review で、claim-to-evidence のつながり、hidden assumption、result と interpretation の飛躍を確認します。
1. 実装中に checkpoint review を入れ、設計逸脱を早めに落とします。
1. validation 実行後に final acceptance review を行い、必要なら追加修正や追加検証を行います。
1. audit review で required reviews と evidence の欠落を確認します。
1. run 固有の review artifact は `reports/agents/<run-id>/` に残します。
1. repo-wide の恒久ルール変更がある場合は、対応する `documents/` または `agents/` の正本を同じ変更で更新します。

## マージ条件

- 必要な review family が完了していること
- requirements review、計画レビュー、詳細設計レビュー、文書通読レビュー、checkpoint review、final acceptance review、audit review が揃っていること
- 長文文書では、別 reviewer による docs completeness review も揃っていること
- 学術文章では、notation review と logic-gap review も揃っていること
- 対象に応じた validation 結果が確認されていること
- 変更理由と影響範囲が追えること
- コンフリクトがないこと

## エビデンス保存

- run 固有の intake、design、review、verification、retrospective は `reports/agents/<run-id>/` に置きます。
- project-wide な分析や再利用する長文 report は `reports/` に置きます。
- 一時メモや cross-run の補助知見は `notes/` に置きます。
- dated な completion summary や古い review 文書を `documents/` や repo root に残すことを禁止します。

## Findings の扱い

findings は少なくとも次に分けます。

- `fix now`
  - この変更で直さないと回帰や矛盾が残るもの
- `follow-up`
  - 今回の受け入れを阻害しないが、後続で管理すべきもの
- `delete-ok`
  - stale asset や重複導線のように安全に削除できるもの

## 関連正本

- [agents/TASK_WORKFLOWS.md](/mnt/l/workspace/project_template/agents/TASK_WORKFLOWS.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](/mnt/l/workspace/project_template/agents/canonical/ARTIFACT_PLACEMENT.md)
- [agents/skills/README.md](/mnt/l/workspace/project_template/agents/skills/README.md)
- [documents/workflow-references.md](/mnt/l/workspace/project_template/documents/workflow-references.md)
