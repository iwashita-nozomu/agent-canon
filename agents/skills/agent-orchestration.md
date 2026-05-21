# agent-orchestration
<!--
@dependency-start
responsibility Documents agent-orchestration for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../workflows/hypothesis-validation-workflow.md analysis-first overlay routing
@dependency-end
-->


## Purpose

task 開始時の mandatory routing skill です。
task を workflow family に分類し、skill set、handoff、review、runtime entrypoint を一貫した形にそろえます。

## Use When

- repository task を開始する
- どの workflow family を使うか決めたい
- skill、subagent、review、model / team policy、run bundle、runtime entrypoint を選ぶ
- run bundle や review artifact の要否を決めたい
- Codex / Claude / Copilot 間で共通ルールを保ちたい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `documents/runtime-profiles-and-check-matrix.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`

## Decision Order

1. 他の task-shape skill を選ぶ前に、この skill で request が `repo-changing execution` か `routing-only/advisory` かを先に分ける
1. `agents/TASK_WORKFLOWS.md` から primary workflow family を 1 つ選ぶ
1. `agents/skills/README.md` から必要最小限の public skill を足す
1. starter command と review / specialist stack を family と mode に合わせて決める
1. repo-changing execution では `python3 tools/agent_tools/check_convention_compliance.py` を closeout gate に入れ、機械化済み規約を prompt 内で再実装しない
1. implementation が scope に入るときだけ Codex routing を出す

mode の意味:

- `repo-changing execution`
  - repo を今から触る
  - run bundle や kickoff command が必要
  - `$codex-task-workflow` を足す
  - `$subagent-bootstrap` は Shared canon / Large delivery / high-risk / multi-step / explicit subagent work の時だけ足す
  - task-shape skill は `$agent-orchestration` の後に足す
- `routing-only/advisory`
  - workflow family、skill、review、starter guidance だけを先に決める
  - full kickoff や repo-changing-only skill を勝手に足さない
  - 普通の相談、壁打ち、説明だけの turn を含む
  - repo state 確認、MCP inventory、repo MCP tool、shell / GitHub check を走らせず、会話だけで応答する
  - user が repo inspection、file edit、validation、PR / issue 処理、CI 確認、または実装作業を求めた時点で `repo-changing execution` へ切り替え、切り替えを user-facing update で明示してから preflight へ進む

## Outputs

- chosen workflow family
- request mode (`repo-changing execution` or `routing-only/advisory`)
- 必要な role / specialist
- review と handoff の最小構成
- repo-editing task なら、requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation の順序
- 最初の作業 update 用の `workflow=<family>`, `skills=<...>`, `review=<...>` 宣言。`skills=<...>` では `$agent-orchestration` を先頭に置く
- PR を作る task では、同じ routing 宣言と `route.py --prompt "<user request>" --format json` の確認結果を PR body、run bundle、または linked comment に残す
- 必要な run bundle command と specialist activation
- `IMPLEMENTATION_CODEX_AGENTS` による `spark_worker` / `worker` routing
- parallel write が要るなら file 単位の write-scope 方針

## Workflow Family Mapping

| Task Shape | Primary Family | Notes |
| ---------- | -------------- | ----- |
| local bug fix, CI fix, docs/test sync | `Scoped Change` | `T1`-`T3` |
| research-backed implementation, benchmark/experiment optimization, academic paper/thesis/scholarly note | `Research-Driven Change` | `T4`, `T5`, `T9`, `T10` |
| large refactor or large multi-surface delivery | `Large Delivery` | `T6`, `T7` |
| environment, CI, Docker, dependency rollout | `Platform And Environment` | `T8` |
| repo-wide workflow/tooling/canon rearchitecture | `Comprehensive Development` | `T11`, `T12` |
| backlog-driven tuning and empirical improvement loop | `Adaptive Improvement Loop` | `T13` |

task id が分かる場合は、task catalog 側の family を正本にします。

## Public Skill Selection

- user が明示した `$skill-name` は preserve します
- `$agent-orchestration` は routing skill として常に先頭に置きます
- `repo-changing execution` では `$codex-task-workflow` を足します
- `$subagent-bootstrap` は Shared canon / Large delivery / high-risk / multi-step / explicit subagent work の時だけ足します
- README、workflow、guide、migration のような長文 docs では `long-form-writing` を足します
- 投稿論文や thesis chapter の draft では `paper-writing` を優先します
- paper draft ではない scholarly note や broader academic text では `academic-writing` を使います
- scope が paper draft と broader academic prose をまたぐなら、`paper-writing` を優先し、必要なときだけ `academic-writing` を追加します
- research-backed implementation や比較改善では `research-workflow` を使います
- large refactor では `behavior-preserving-refactor`、environment task では `environment-maintenance`、repo-wide rearchitecture では `comprehensive-development`、outer loop tuning では `adaptive-improvement-loop` を使います
- 原因考察、仮説、修正箇所選定、複数候補比較が task の中心にある場合は `dependency-analysis` を足し、`agents/workflows/hypothesis-validation-workflow.md` を overlay として明示します
- 関係のない family skill は足しません
- tool 化済みの規約検証は task-shape skill として増やさず、`check_convention_compliance.py` の gate に委譲します

## Entrypoint Precedence

- repo-editing task や kickoff command が必要な task では `bootstrap_agent_run.py` を優先します
- `task_start.py` は routing-only starter guidance に向きます
- `task id がある` ことだけでは `task_start.py` を優先する理由にはなりません。repo-changing execution なら task id 付きでも bootstrap を使います

## Review And Specialist Expectations

- family に応じた reviewer / specialist stack まで出します
- `Research-Driven Change` では research / report / reproducibility / benchmark / artifact 系 reviewer を落としません
- long-form docs では docs-impact がある場合に `document_flow_reviewer` と docs completeness review を使います
- academic/paper work では notation / logic review を落とさず、paper draft では `citation_evidence_reviewer` も追加します

## Codex Implementation Routing

- implementation が scope に入るときだけ routing を出します
- `bootstrap_agent_run.py` か `task_start.py` の output で `IMPLEMENTATION_CODEX_AGENTS` を確認してから route します
- Routine docs / Focused code では parent-direct を許可します。subagent 実装では、design trace、identifier naming、test plan、write scope が固定済みで、1 file または単一抽象ユニット、public interface 変更なし、依存追加なし、仕様解釈なし、局所 validation で閉じる低リスク slice は `spark_worker` を先に使います。
- 設計解釈、衝突解決、広い architecture 判断、scope 判断を含む slice は `worker` を使います。
- `spark_worker` は詳細設計、review、final judgment には使いません。
