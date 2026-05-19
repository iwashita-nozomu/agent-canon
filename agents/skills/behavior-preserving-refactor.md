# behavior-preserving-refactor
<!--
@dependency-start
responsibility Documents behavior-preserving-refactor for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

大きめの refactor を、feature 追加ではなく挙動保存つきの再編として扱います。

## Use When

- file 分割、rename、module 境界整理
- 依存方向の整理
- implementation の差し替えを伴う構造再編
- branch 側で file 構成変更を含む整理

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/workflows/implementation-waterfall-workflow.md`
- `agents/workflows/comprehensive-refactoring-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/workflows/main-integration-workflow.md`

## Required Contract

1. refactor pass では `Behavior Contract:` を先に固定します。
1. `Allowed Structural Delta:` と `Forbidden Semantic Delta:` を分けて書きます。
1. 新機能追加は同じ pass に混ぜません。必要なら先に分離します。
1. delete、rename、move、module split は `Files To Remove Or Move:` として先に列挙します。
1. old path と new path の対応を `Path Mapping:` として残します。
1. 大規模 repo では `Current Responsibility Map:` と `Target Responsibility Map:` を先に作り、OOP 的に責務、状態、契約、adapter を最小境界へ分けます。
1. 必要に応じて `python3 tools/agent_tools/analyze_refactor_surface.py <paths> --min-score <score>`、`python3 tools/oop/python/readability.py <paths> --min-score <score>`、C++ surface では `python3 tools/oop/cpp/readability.py <paths> --min-score <score>` で baseline と target score を固定します。
1. 外部 repo や bare snapshot の OOP survey では、元 repo を編集せず、commit SHA、解析 path、`--exclude vendor --exclude reports` などの除外条件、Markdown / JSON report を run bundle に残します。
1. implementation 前に `test_designer` で regression case と nasty case を固定します。
1. 既存 test が薄い場合は baseline capture を追加してから rework します。
1. closeout 前に `python3 tools/ci/check_merge_structure.py ...` の要否を確認します。

## Dependency-Guided Repair Slice Loop

構造重複、OOP readable finding、module boundary finding など、依存関係で
修正順を決める refactor では、単発の上位一覧を一括修正しません。次の
repair-slice loop で 1 slice ずつ進めます。

1. 解析 tool で `priority_order` と `repair_slice` を生成します。
   Python structural duplicate では次を既定入口にします。
   `python-structure-hash` -> `python-structure-hash-report`
1. `repair_slice.root_finding` を今回の最小修正単位にします。
1. `repair_slice.preferred_home_group` を共通化候補にします。ただし、
   その group の設計責務に合わない helper / base / protocol / alias を追加
   してはいけません。
1. `repair_slice.affected_downstream_groups` と `affected_files` を call-site /
   downstream 修正候補として読みます。
1. `repair_slice.related_findings` に同じ home/downstream group の finding が
   あれば、同じ責務で同時に消せるものだけ同じ pass に含めます。
1. root finding が薄い marker class、例外型、Protocol、型 alias、config
   marker など複数責務をまたいでいる場合は、共通化せず
   `review_required` として次の actionable slice に進みます。
1. 修正は依存 graph の根本側へ寄せます。呼び出し側ごとの専用 helper 増設を
   既定解にしてはいけません。
1. 根本 group の既存責務で足りる場合は既存実装を拡張します。責務拡張が必要な
   場合は親 repo の設計文書を先に更新します。責務が合わない場合は、直近の
   共通 ancestor group か現状維持を選び、理由を report に残します。
1. 1 slice を修正したら必ず全走査を再実行します。差分 finding だけで次の
   slice を判断してはいけません。
1. 再走査後の `priority_order` と `repair_slice` を新しい正本として、次の
   slice を選びます。

この loop では、機械的な順序決定と人間/agent の設計判断を分離します。
tool は候補と影響面を出し、実装者は責務境界に反する共通化を拒否します。

## Subagent Routing

refactor が trivial な単発編集を超える場合、parent agent は実装と review を
兼務しません。run bundle または作業 update に、どの subagent がどの stage を
担当するかを固定します。

1. Parent agent
   - `Behavior Contract`、`Allowed Structural Delta`、
     `Forbidden Semantic Delta`、scan artifact、repair slice、validation
     sequence を固定します。
   - write-capable agent と read-only reviewer の入力 artifact を分けます。
   - 実装後に reviewer finding を統合する責任を持ちますが、review 判定を
     自分だけで完了扱いにしません。
1. `test_designer`
   - code-changing refactor では implementation 前に起動します。
   - regression case、nasty case、behavior-preservation assertions を設計し、
     実装 agent へ渡します。
1. Write-capable implementation agent
   - 既定は `worker` または小さい slice では `spark_worker` です。
   - 同時に write-capable agent は 1 体だけにします。
   - repair slice、affected files、forbidden semantic delta、既存 dirty
     state の扱い、validation command を明示して渡します。
   - 実装 agent は review を完了扱いにしてはいけません。
1. Read-only review agent
   - 実装 agent とは別 instance にします。
   - Python 差分は `python_reviewer`、C/C++ 差分は `cpp_reviewer`、Rust/tool
     差分や mixed diff は `reviewer` または task-specific reviewer を使います。
   - reviewer には latest diff、scan before/after、impact diff、test evidence、
     behavior contract を渡します。
   - reviewer は approve / revise / escalate を artifact または parent への
     final message に明示します。
1. Design/document review
   - module boundary、public API、workflow/skill 文書を変えた場合は
     `detailed_design_reviewer`、`document_flow_reviewer`、または
     `docs_workflow_steward` を追加します。
   - 単なる実装差分 review の代替にしません。

## Review Emphasis

- `design_reviewer`
  - semantic delta が混入していないか
- `document_flow_reviewer`
  - path mapping と migration 説明が上から読んで追えるか
- `project_reviewer`
  - cross-module drift、stale path、残骸がないか
- language reviewer
  - Python なら `python-review`
  - C / C++ なら `cpp-review`
- `docs_workflow_steward`
  - design 見直し、OOP boundary、解析 score gate が workflow と docs に残っているか
