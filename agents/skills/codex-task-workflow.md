# codex-task-workflow

<!--
@dependency-start
contract skill
responsibility Documents codex-task-workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../COMMUNICATION_PROTOCOL.md defines pre-edit investigation and context capsule handoff packets
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest requirements
upstream design tool-finding-report.md tool-based finding packet and prompt feedback workflow
downstream design ../../.agents/skills/codex-task-workflow/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

Codex が会話コンテキストに依存せず、毎回同じ順序で task を進めるための標準フローです。

## Use When

- Codex で task を最初から最後まで進める
- 手順を固定したい
- task ごとの skill 選択を標準化したい

## Core Reference

- `agents/canonical/CODEX_WORKFLOW.md`

## Stages

1. intake
1. required context and library sweep
1. workflow selection
1. artifact placement
1. explicit subagent bootstrap
1. execution plan and plan review for full staged routes
1. detailed design and detailed design review for full staged routes
1. document flow review for reader-facing docs, new terms, public APIs, or full staged routes
1. implementation
1. validation
1. closeout

## Required Output

- 着手時の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- Shared canon / Large delivery / high-risk / multi-step task では `python3 tools/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` から始める
- `Scoped Change Lite` では cheap local route を使い、document-flow / broad design review は escalation 条件がある場合だけ起動する
- Routine docs / Focused code では、実装前に parent-direct route と targeted validation が固定された場合に parent-direct を使う
- repo-changing execution の編集では、選択済み runtime `SKILL.md` の本文を読む。これは `Scoped Change Lite`、Routine docs、Focused code、typo / link / format-only、parent-direct route を含む selected_runtime_skill_read 契約です。小規模修正は `$small-change-routing` に流し、patch 前の作業 evidence に small_change_skill_read、skill 名、path を残す
- ユーザーが coding / implementation / patch / editing を明示的に依頼した場合は、read-only wave を completion ルートにしない。要件整理・allowed_paths 固定・write scope 固定・validation route 固定・`tool_rejection_preflight` 固定後に `spark_worker` / `worker` を起動してから実装へ進む
- repo-changing task では `$agent-orchestration` を先頭に置き、`$subagent-bootstrap` は subagent が必要な risk class でだけ併用する
- workflow family、public skill set、review stack は `agent-orchestration` の出力を入力として受け取り、この skill で routing matrix を重複定義しない
- ユーザー向けの作業報告と最終報告は自然な文章にします。内部の項目名、列挙値、役割名、補助関数風の語は、コマンド、パス、表、正確な根拠の引用に閉じます。専門語が必要な場合は、既存のリポジトリ用語または外部標準の用語を使い、自然文で説明します。
- AgentCanon update surface が repairable なら `make agent-canon-ensure-latest` を実行する。submodule repo では親 repo の無関係な dirty state はこの実行を block しない。update surface 自体が unsafe な場合だけ、`agents/workflows/agent-canon-pr-workflow.md` または `agents/workflows/derived-agent-canon-diff-workflow.md` に入り、AgentCanon PR / proposal merge 後に `make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` で template / derived repo へ持ち帰る
- 普通の相談、壁打ち、routing-only advice、説明だけの turn はこの skill の実行対象ではありません。その場合は shell / GitHub checks を走らせず、会話だけで応答します。
- GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は repository task に昇格させない
- 編集手段は、小〜中規模は patch-based edit、機械生成・一括変換は repo script / formatter の順に選ぶ
- sweep と原因調査は、次の具体的な作業に結び付けます。各結果は、実装経路、再利用判断、古い面の修復、依存範囲、検証経路、Issue、または担当者付きの保留のどれかを更新します。更新先が同じ根拠は記録内の短い引用に圧縮し、現在の作業へ戻ります。
- 検証は軽量な根拠から始めます。静的解析、依存確認、文書確認、経路確認、変更ファイル対象のテストを先に使います。CI 全体、長いテスト一式、ベンチマーク、実験、GPU / CPU 数値実行、ソルバーの一括確認、大きな乱択ケースは、今回の依頼、期待する確認結果、時間と資源の上限、停止条件、成果物の場所を持つ実行前の確認記録から実行します。
- 詳細設計が編集対象 path に絞る前に、責務 model、概念 graph または layer model、非対象、将来拡張 layer、評価軸、canonical surface 関係を含む `Abstract Design Frame` を書くか引用する。実装 scope、file list、validation は nearest editable path や current finding ではなく、この frame から導く
- 実装 path を選ぶ前に、承認済み design packet が owner、canonical paths、forbidden paths、required checks をすでに固定していない限り、`agent-canon local-llm route-implementation-surface --request-file <request-or-design-question.txt> --format text` を走らせるか引用する。code、tool、skill、workflow、document、runtime instruction のどこに置くかは、この compact route を source packet seed にして決める。LocalLLM が無い場合は deterministic fallback の `PRIMARY_PATHS` / `FORBIDDEN_PATHS` を provisional source-packet seed として使うか `router_unavailable_blocker` として記録し、responsibility search と dependency scope で owner と edit scope を確定する。fallback routing は `fallback_exit_status` として `canonical_rerun_pass`、`durable_blocker_or_issue`、`explicit_approval_evidence` のいずれかに接続する
- 編集前の repo 調査は `agents/COMMUNICATION_PROTOCOL.md` の `Pre-Edit Repository Investigation Packet` として固定する。packet には implementation surface route、responsibility search、reuse survey、stale surface scan、dependency scope、validation route を入れる。既存 repo 調査が甘いまま実装へ進んだ場合は、差分を広げる前にこの packet を作り直す
- `Pre-Edit Repository Investigation Packet` は、次に進む具体的な作業と担当者を 1 つ書いて閉じます。別の探索へ広げる前に、その作業を実装、検証、Issue 処理のいずれかへ進めます。
- 検証経路は、静的確認だけで閉じるか、広い実行の承認まで得ているかを明記し、担当者も書いて閉じます。方針、文書、メタデータ、契約だけの薄い包み、既存の確認コマンドが所有する性質では、静的確認だけを使います。
- 実装前に承認済み `design_brief.md` の `Abstract Design Frame`、`Implementation Source Packet`、`Design Side-Effect Map`、`Design-To-Implementation Trace` を読み、各 implementation slice と downstream side effect が抽象責務 model から導かれていることを確認してから design artifact path、design section、test-plan item、user-request clause ID を引用する
- 実装中に設計上の問題を見つけたら、勝手に実装で吸収せず `design_issue_blocker` と evidence を記録して詳細設計 / design review へ戻る。API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾を、local fallback、wrapper、helper、分岐、互換 route、test 緩和、説明だけの上書きで処理してはいけない
- implementation slice は contract-complete implementation として閉じる。request clause、acceptance contract、`Implementation Source Packet`、validation route を結び、要求を縮める implementation shortcut を見つけたら `design_issue_blocker` と evidence を記録して design review へ戻る
- 同じ implementation pass で直せるのは、承認済み design、局所 precedent、既存責務境界から一意に導ける typo、format、import、狭い機械的追従だけです。判断が必要なら設計問題として扱う
- class、dataclass、`Protocol`、継承、public API、型境界、依存方向を触る implementation slice は `$oop-readability-check` を validation route に入れ、SOLID principle signal、OOP dimension、finding kind、`tools/oop/shared/readability_core.py` の mapping を design artifact に結びます。
- 実装前に `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら Abstract Design Frame と design trace から導かれた narrow slice は `spark_worker` を使い、design interpretation / conflict resolution / broad architecture judgment / scope judgment を含む slice は `worker` を使う
- 変更対象の `Dependency Manifest Plan` を設計で固定し、編集前に upstream、編集後に downstream を読む
- parent 直編集でも write-capable subagent でも、実装前に cause investigation artifact を固定し、`Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を残してから code edit に入る
- parent 直編集でも write-capable subagent でも、実装前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、予測された cause investigation / OOP / helper / dependency / hook runtime / skill mirror / tool catalog / protocol / log-surface gate と repair plan を handoff または work log に残す
- fresh subagent に渡す prompt は chat history 依存にしない。`Fresh Subagent Context Capsule` に objective、request clauses、state snapshot、exact read-before-work paths、compact artifacts、allowed / forbidden paths、expected output schema、validation route、return contract を詰める。full transcript、raw logs、full dashboard、repo root 全体を context として渡さない
- runtime/tool gate が write-capable spawn を阻害する場合は `WRITE_SUBAGENT_AUTHORIZATION=required` または該当 gate blocker を記録し、slice を `fallback_exit_status` に接続する。継続 route は canonical gate rerun による `canonical_rerun_pass`、`durable_blocker_or_issue`、または `explicit_approval_evidence` 付き revised workflow route とする
- tool / checker / hook / reviewer / subagent feedback から実装へ入る場合は `tool-finding-report` で finding packet を作り、write-capable subagent handoff に artifact path、structured findings、prompt feedback decision を渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` が出た場合は、次の write-capable subagent を起動する前に handoff prompt、skill、workflow、または task catalog prompt を修正する
- prompt/config drift が shared canon surface をまたぐ場合は、親がその場で prose を増やす前に `prompt_config_reviewer` で audit し、この workflow はその監査結果を消費して最小差分だけ適用する
- nontrivial document creation / revision では `prose-reasoning-graph` と `structure-planning` を構造先行 gate として通し、その後に `long-form-writing` / `paper-writing` / `academic-writing` へ渡す。typo / link / format-only では `md-style-check` と `structure_contract=skipped` の理由を evidence に残す
- closeout 前に `check_dependency_headers.py --changed`、`scan_dependency_headers.sh --changed --fail-missing`、`check_dependency_header_format.sh --changed --require-header` を通す
- dependency edge を変更した場合は `check_dependency_graph.sh --print-edges` の結果、または移行中 baseline と今回差分で新規 graph error を増やしていない evidence を残す
- Shared canon / Large delivery / high-risk / workflow-tooling change では closeout 前に `python3 tools/agent_tools/check_convention_compliance.py` を通し、workflow prohibition、convention tool gate、skill-routing hook の欠落を tool で検出する
- 検証は該当する範囲で最も軽いコマンドから始めます。広い実行は実行前の確認記録を使い、軽い確認で残った未確認点を記録します。
