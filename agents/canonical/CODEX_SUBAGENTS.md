# Codex Subagents

この文書は、Codex を primary runtime とする場合の subagent routing と inventory の正本です。
shared workflow は `agents/canonical/CODEX_WORKFLOW.md` に置き、この文書は inventory、mapping、activation に寄せます。
role ごとの具体的な禁止事項、handoff 条件、review separation は `.codex/agents/*.toml` を正本にします。

## Principles

- role behavior は docs より `.codex/agents/*.toml` を優先します
- parent agent が最終編集責任を持つ
- routing と required review を決める前に subagent を乱立させない
- repo-changing task では、stage ごとに適切な subagent を explicit に立てる
- 調査、レビュー、文書整備は分ける
- 再帰的 fan-out は避ける
- 探索、レビュー、仕様確認の並列化は使うが、parallel write-heavy implementation は避ける
- `max_depth = 1` を前提にし、subagent からの再帰的 fan-out を避ける
- `計画レビュー` と `詳細設計レビュー` は別の subagent で行う
- `文書通読レビュー` は `詳細設計レビュー` と別の subagent で行う
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別の subagent で行う
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなす
- 実装では既存コード、既存の命名、既存の文書スタイルの踏襲を優先する
- Codex の default は、文書・計画・review を `gpt-5.4` `high`、coding-specialist role を `gpt-5.3-codex` `high` に分ける
- `gpt-5.3-codex-spark` は、超低遅延の狭い coding loop に限る manual override とみなす
- plan mode や permissions のような mode は session 単位の設定なので、subagent TOML には持たせず、parent session 側で切り替える

## Codex Command Surface

- official Codex CLI では `/model` で model / reasoning、`/plan` で plan mode、`/permissions` で approval preset を切り替えます
- これらは session-level setting で、per-agent TOML には書きません
- runtime が `/agent` を提供する場合は inventory 確認に使います
- `/agent` が使えない runtime では `.codex/agents/*.toml` を直接見ます
- run bundle は `python3 scripts/agent_tools/bootstrap_agent_run.py ...` で先に作ります

## Permanent Team To Codex Mapping

| Permanent Team Role | Codex Subagent / Parent Role |
| ------------------- | ---------------------------- |
| `manager` | parent + `requirements_organizer` |
| `manager_reviewer` | parent review gate or `reviewer` |
| `scheduler` | `execution_planner` |
| `schedule_reviewer` | `plan_reviewer` |
| `designer` | `detailed_designer` |
| `design_reviewer` | `detailed_design_reviewer` |
| `document_flow_reviewer` | `document_flow_reviewer` |
| `notation_definition_reviewer` | `notation_definition_reviewer` |
| `logic_gap_reviewer` | `logic_gap_reviewer` |
| `implementer` | `worker` |
| `change_reviewer` | `reviewer` or `python_reviewer` |
| `final_reviewer` | `reviewer`, `project_reviewer`, `python_reviewer` の該当 reviewer |
| `critical_guardian` | `project_reviewer` |
| `researcher` | `literature_researcher` or `explorer` |
| `infra_steward` | parent + `docs_workflow_steward` or infrastructure-focused `worker` planning |

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
- `notation_definition_reviewer`
  - 記号、略語、technical term、unit、index、assumption の definition-before-use と一貫性を確認する
- `logic_gap_reviewer`
  - claim-to-evidence のつながり、hidden assumption、result と interpretation の飛躍を確認する
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
| 詳細設計レビュー | 専用の `detailed_design_reviewer` instance |
| 長文起草 | `long_form_writer`。README、workflow、guide、migration 文書では `long-form-writing` を前提に draft する |
| 学術文章起草 | `long_form_writer`。論文、thesis chapter、scholarly note では `academic-writing` を前提に draft する |
| 文書通読レビュー | 専用の `document_flow_reviewer` instance。詳細設計、README、workflow、reader-facing doc を上から順に読んで意味が通るかを見る |
| 記号定義レビュー | 専用の `notation_definition_reviewer` instance。記号、略語、technical term、unit、index、assumption の定義順と一貫性を見る |
| 論理接続レビュー | 専用の `logic_gap_reviewer` instance。主張の飛躍、隠れた仮定、result と interpretation の境界を見る |
| 実装 | bounded な切り出しだけを `worker` |
| 実装後レビュー | `reviewer`、`python_reviewer` |
| 包括的開発の統合レビュー | `project_reviewer`、`docs_workflow_steward`、`python_reviewer` を intake / wrap-up の固定 stack として使う |

運用ルール:
- role ごとの詳細な実行制約は `.codex/agents/*.toml` を見ます
- この文書では route と inventory だけを決め、各 role の禁止事項を重複記述しません
- parent は stage を暗黙にまとめず、別 role を別 instance で起動します
- 長文文書では `document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します
- 学術文章では `document_flow_reviewer` に加えて `notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通します

## Parallel Write Safety

- 軍隊式の既定では、同一 worktree の writer は常に 1 人です
- same directory を複数 writer が同時に触る運用を正本にしません
- 複数 writer が必要な task は、worktree を分けてから統合します
- review role は常に read-only とし、single-writer rule の確認は `plan_reviewer` と `project_reviewer` の固定責務です

## Codex Model Policy

| Role Bucket | Roles | Model | Reasoning |
| ----------- | ----- | ----- | --------- |
| Requirements / Planning / Detailed Design / Long-Form Writing | `requirements_organizer`, `execution_planner`, `detailed_designer`, `long_form_writer` | `gpt-5.4` | `high` |
| Research Synthesis / Workflow Canon Docs | `literature_researcher`, `docs_workflow_steward` | `gpt-5.4` | `high` |
| Codebase Survey / Implementation / Python Code Review | `explorer`, `worker`, `python_reviewer` | `gpt-5.3-codex` | `high` |
| Reviews And Final Judgment | `plan_reviewer`, `detailed_design_reviewer`, `document_flow_reviewer`, `notation_definition_reviewer`, `logic_gap_reviewer`, `reviewer`, `project_reviewer`, `report_reviewer`, `reproducibility_reviewer`, `scientific_computing_reviewer`, `benchmark_reviewer`, `artifact_reviewer`, `fair_data_reviewer`, `ml_science_reviewer` | `gpt-5.4` | `high` |

運用メモ:
- OpenAI の current docs では `gpt-5.4` は professional workflows 向けの default / highest-intelligence 枠、`gpt-5.3-codex` は agentic coding 専用最適化枠です
- この repo ではそれに合わせて、文書・計画・review を `gpt-5.4`、coding-specialist role を `gpt-5.3-codex` に寄せます
- repo default の reasoning は `high` にし、`xhigh` は parent が明示的に必要と判断したときの manual escalation に留めます
- planning session の mode は official Codex CLI なら `/plan`、model / reasoning の切替は `/model`、approval preset は `/permissions` を使います
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

設定運用メモ:
- stage 固有の禁止事項を増やしたいときは、この文書より先に `.codex/agents/*.toml` を更新します
- wrapper や root entrypoint に同じ規則を重ね書きしません

## Smoke Test

runtime inventory や review pack を変えたら、まず次を実行します。

    python3 scripts/agent_tools/smoke_test_research_perspective_pack.py

この smoke test は次を確認します。

- `agents/agents_config.json` に perspective reviewers と artifact mapping がある
- `agents/task_catalog.yaml` に `research_perspective_review` pack と `T9` がある
- `.codex/agents/*.toml` に対応 subagent 定義がある
- temporary run bundle を作って、各 perspective review artifact と `team_manifest.yaml` が実際に生成される
