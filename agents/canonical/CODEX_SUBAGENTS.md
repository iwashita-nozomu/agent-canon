# Codex Subagents

この文書は、Codex を primary runtime とする場合の subagent routing と inventory の正本です。
shared workflow は `agents/canonical/CODEX_WORKFLOW.md` に置き、この文書は specialist 起動の補足に限定します。

## Principles

- parent agent が最終編集責任を持つ
- repo-changing task では、stage ごとに適切な subagent を explicit に立てる
- 調査、レビュー、文書整備は分ける
- 再帰的 fan-out は避ける
- `計画レビュー` と `詳細設計レビュー` は別の subagent で行う
- `文書通読レビュー` は `詳細設計レビュー` と別の subagent で行う
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなす
- 実装では既存コード、既存の命名、既存の文書スタイルの踏襲を優先する
- Codex の default は `gpt-5.4` `xhigh` を判断役に、`gpt-5.4-mini` `xhigh` を高頻度 subagent に使う
- `gpt-5.3-codex-spark` は、超低遅延の狭い coding loop に限る manual override とみなす
- `Plan` collaboration mode は session 単位の設定なので、要件整理と実行計画立案では parent 側で有効化し、subagent TOML には model / reasoning だけを持たせる

## Built-In Or Project-Scoped Roles
- `requirements_organizer`
  - 変更要求、scope、acceptance criteria、reuse target を整理する
- `execution_planner`
  - stage 順序、担当 subagent、validation 順序、rollback point を固定する
- `plan_reviewer`
  - 実行計画の順序、review 分離、rollback readiness を確認する
- `detailed_designer`
  - reuse-first の detailed design 文書を起こす
- `detailed_design_reviewer`
  - 実装前の最重要 gate として設計文書を独立に確認する
- `document_flow_reviewer`
  - 文書を上から順に読み、用語導入、section 順序、reader path が自然かを確認する
- `long_form_writer`
  - README、workflow、guide、migration 文書のような長文を roadmap-first に起草する
- `explorer`
  - 読み取り専用で codebase / docs / workflow の調査を行う
- `reviewer`
  - 読み取り専用で diff と risk を findings-first で洗う
- `python_reviewer`
  - Python diff を型、pytest、ruff 前提で洗う
- `worker`
  - bounded な実装変更を切り出す
- `docs_workflow_steward`
  - agent 文書、workflow、adapter file の整理を行う
- `project_reviewer`
  - repo-wide な inventory と workflow health を確認する
- `literature_researcher`
  - 論文、survey、比較論文、仕様資料の調査と先行研究整理を行う
- `report_reviewer`
  - experiment report の根拠と reader-facing quality を確認する
- `reproducibility_reviewer`
  - provenance、seed、command、environment、rerunability を確認する
- `scientific_computing_reviewer`
  - incremental change、testing、automation、prototype discipline を確認する
- `benchmark_reviewer`
  - fairness、case mix、confounder、benchmark anti-pattern を確認する
- `artifact_reviewer`
  - code、script、raw result、environment、artifact package の十分性を確認する
- `fair_data_reviewer`
  - metadata、命名、result path、再利用性を確認する
- `ml_science_reviewer`
  - assumptions、limitations、uncertainty、reader-facing reporting を確認する

棲み分け:
- `document_flow_reviewer` は design / README / workflow などの top-down readability を見る
- `report_reviewer` は experiment report の evidence traceability と overclaim を見る

## Recommended Routing

| Stage | Default Subagent Pattern |
| ----- | ------------------------ |
| 要件整理 | `requirements_organizer`。local precedent 調査が要るなら `explorer` を補助に使う |
| 調査 | 外部文献は `literature_researcher`、local precedent は `explorer` |
| 実行計画立案 | `execution_planner` |
| 計画レビュー | 専用の `plan_reviewer` instance |
| 詳細設計 | `detailed_designer`。既存 code path 調査が要るなら `explorer` を補助に使う |
| 詳細設計レビュー | 専用の `detailed_design_reviewer` instance。Python 差分が中心なら `python_reviewer` を追加。repo-wide 影響が大きければ `project_reviewer` を追加 |
| 長文起草 | `long_form_writer`。README、workflow、guide、migration 文書では `long-form-writing` を前提に draft する |
| 文書通読レビュー | 専用の `document_flow_reviewer` instance。詳細設計、README、workflow、reader-facing doc を上から順に読んで意味が通るかを見る |
| 実装 | bounded な切り出しだけを `worker` |
| 実装後レビュー | `reviewer`、Python 差分なら `python_reviewer` |

運用ルール:
- parent は、上の stage を 1 つの思考の中で暗黙にまとめません
- 計画レビュー用 `plan_reviewer` と詳細設計レビュー用 `detailed_design_reviewer` は同じ instance を再利用しません
- `document_flow_reviewer` は `detailed_design_reviewer` と同じ instance を再利用しません
- 詳細設計レビューが unresolved のまま `worker` を起動しません
- 文書通読レビューで major rewrite 指摘が残っている間は `worker` を起動しません
- 長文文書では、`document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します
- `requirements_organizer`、`execution_planner`、`detailed_designer`、`worker` は、既存コードと既存の書き方を踏襲することを最優先にします
- `docs_workflow_steward` は canonical docs と workflow 文書の更新に限定して使います

## Codex Model Policy

| Role Bucket | Roles | Model | Reasoning |
| ----------- | ----- | ----- | --------- |
| Requirements / Planning / Detailed Design | `requirements_organizer`, `execution_planner`, `detailed_designer`, `long_form_writer` | `gpt-5.4` | `xhigh` |
| Research Synthesis / Workflow Canon Docs | `literature_researcher`, `docs_workflow_steward` | `gpt-5.4` | `xhigh` |
| High-Frequency Local Survey | `explorer` | `gpt-5.4-mini` | `xhigh` |
| Implementation Default | `worker` | `gpt-5.4-mini` | `xhigh` |
| Reviews | `plan_reviewer`, `detailed_design_reviewer`, `document_flow_reviewer`, `reviewer`, `python_reviewer`, `project_reviewer`, `report_reviewer`, `reproducibility_reviewer`, `scientific_computing_reviewer`, `benchmark_reviewer`, `artifact_reviewer`, `fair_data_reviewer`, `ml_science_reviewer` | `gpt-5.4` | `xhigh` |

運用メモ:
- OpenAI の現行 Codex 向け guidance に合わせ、`gpt-5.4` に planning、coordination、final judgment を任せ、`gpt-5.4-mini` subagent に狭い並列 task を割り当てます
- interactive Codex で要件整理と実行計画立案を回すときは、可能なら parent session を `/collab` の `Plan` mode に切り替えてから planning specialist を起動します
- `Plan` collaboration mode は session-level setting なので、`.codex/agents/*.toml` には書かず、この文書と `agents/canonical/CODEX_WORKFLOW.md` にだけ明記します
- terminal 操作や patch 適性を強く優先したい implementation では、parent 判断で `worker` を `gpt-5.3-codex` に override して構いません
- 極端に狭く、待ち時間が支配的な implementation loop では、parent 判断で `worker` を `gpt-5.3-codex-spark` に override して構いません
- `gpt-5.3-codex-spark` は smaller / text-only / 128k context の preview 系なので、詳細設計、最終判断、重要 review の default には使いません

## Research Perspective Review Pack

- `reproducibility_reviewer` に provenance、seed、command、environment、rerunability を見させる
- `scientific_computing_reviewer` に incremental change、testing、automation、prototype discipline を見させる
- `benchmark_reviewer` に fairness、case mix、confounder、benchmark anti-pattern を見させる
- `artifact_reviewer` に code、script、raw result、environment、artifact package の十分性を見させる
- `fair_data_reviewer` に metadata、命名、result path、再利用性を見させる
- `ml_science_reviewer` に assumptions、limitations、uncertainty、reader-facing reporting を見させる
- parent が findings を `fix now`、`follow-up`、`delete-ok` に再分類して反映する

## Runtime Surfaces

- human canon: `agents/`
- skill shim: `.agents/skills/`
- Codex project config: `.codex/config.toml`
- Codex subagent definitions: `.codex/agents/*.toml`

## Smoke Test

runtime inventory や review pack を変えたら、まず次を実行します。

    python3 scripts/agent_tools/smoke_test_research_perspective_pack.py

この smoke test は次を確認します。

- `agents/agents_config.json` に perspective reviewers と artifact mapping がある
- `agents/task_catalog.yaml` に `research_perspective_review` pack と `T9` がある
- `.codex/agents/*.toml` に対応 subagent 定義がある
- temporary run bundle を作って、各 perspective review artifact と `team_manifest.yaml` が実際に生成される
