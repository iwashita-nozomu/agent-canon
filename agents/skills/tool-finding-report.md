# tool-finding-report

<!--
@dependency-start
contract skill
responsibility Documents tool-finding-report for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design result-artifact-writeout.md raw result and summary artifact policy
upstream design report-writing.md reader-facing evidence report policy
downstream design refactor-loop.md consumes finding packets for repair slices
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py emits design evidence findings
downstream implementation ../../.agents/skills/tool-finding-report/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: run tools, checkers, hooks, static analysis, or structural analyzers
  to produce full raw, structured, prioritized finding packets.
- Section path: Purpose, Use When, and Boundary define ownership; Finding Packet
  and Procedure define artifacts and ranking; Refactor Integration explains how
  repair workflows consume the packet.
- Use when: baseline findings, mechanical priority order, before/after impact,
  or prompt-feedback evidence is needed before or after implementation.
- Boundary: this skill reports and ranks findings; repair choice belongs to the
  caller workflow, `refactor-loop`, or the relevant implementation skill.

## Purpose

tool、checker、hook、static analysis、構造解析を使って問題を探し、raw result、
structured artifact、mechanical priority order、full finding report、必要なら
before / after impact を同じ source packet で結びます。

この skill は実装修正を担当しません。実装は `refactor-loop`、通常 task execution、
または該当 workflow が担当し、この skill の finding packet を入力にします。

## Use When

- user が tool で問題を探して報告するよう求めたとき
- refactor / implementation の前に full baseline finding と mechanical priority order
  を固定するとき
- 実装後に finding が増えたか、priority が悪化したかを見たいとき
- tool / hook / reviewer / subagent feedback を、次の handoff prompt や shared
  skill / workflow prompt に戻す必要があるとき

## Boundary

- raw result、summary artifact、manifest、overwrite policy は
  `result-artifact-writeout` の責務です。
- reader-facing な narrative report、limitations、claim strength は
  `report-writing` の責務です。
- behavior-preserving な実装修正、repair slice、review gate、実際にどれを直すかの
  取捨選択は `refactor-loop` または呼び出し元 workflow の責務です。
- この skill は finding を自動で「削除対象」とは扱いません。tool は候補と根拠を
  出し、実装側が責務境界、数理契約、API 契約を見て採否を決めます。

## Finding Packet

tool finding report は次を 1 つの packet として残します。finding はこの skill
内で勝手に削らず、既定では repository 全体を対象 scope にした full artifact
として出します。mechanical
priority order まではこの skill が必ず作ります。repair slice、reader-facing
excerpt、実際に修正する対象の取捨選択は、この packet を使う上位 workflow や
実装エージェントが選びます。

- `scope`: 既定 `full repository`、対象 path、baseline ref、exclude、dependency roots。
  user が明示的に targeted / changed-only / slice scope を求めた場合、または tool
  が repo-wide 実行できない場合だけ狭め、その理由を `scope_exception` として残す
- `commands`: 実行 command、cwd、exit status、tool version または commit
- `raw_artifacts`: tool の raw text / JSON / JSONL
- `structured_artifacts`: 正規化 JSON、full table、summary
- `impact_artifacts`: before / after comparison、added / removed finding。比較が明示
  されたときだけ作る補助 artifact
- `mechanical_summary`: count、full finding table、mechanical priority order、
  actionability signals
- `tool_warning_ledger`: warning_id、source_tool、severity、status、
  repair_command、evidence / issue。非 blocking warning も closeout obligation
  として残し、fix-now / S0 / S1 は resolved 以外で閉じない
- `priority_policy`: deterministic ranking inputs and weights used for this run
- `interpretation`: agent の解釈。観測事実と推論を分ける
- `prompt_feedback_decision`: `not_required`、`handoff_prompt_gap`、
  `shared_skill_or_workflow_gap`、`tool_gap`、`test_or_design_gap`
- `handoff_boundary`: this skill reports and ranks findings; the consumer skill decides
  repair slices, implementation, deferral, or prompt/tool repair

## Procedure

1. 対象 scope、exclude rules、dependency roots、output directory を固定します。
   規定の対象 scope は `full repository` です。tool/checker の実行対象は
   repo-wide に取り、targeted / changed-only / selected-path run は user が明示した
   場合、tool が full repo を扱えない場合、または repo-wide run を補助する追加
   診断としてだけ使います。scope を狭めた場合は `scope_exception=<reason>`、
   `requested_scope=<...>`、`omitted_surfaces=<...>` を finding packet に残します。
   comparison ref / worktree は、差分 impact が明示されたときだけ固定します。
1. raw result を先に保存します。保存時は `result-artifact-writeout` を使い、
   failed / partial run も evidence として残します。
   failed validation / check output を implementation に渡す場合は、
   validation-failure-response packet の `failing_contract`、
   `observation_level`、`cause_classification`、`intent_preservation`、
   `evidence` を finding packet に含めます。
1. tool 固有の structured artifact を full repository scope で作ります。件数上限や top-N
   truncation は使わず、tool が出した finding を情報を減らさず保存します。
   - Python structural analysis: `python-structure-hash` ->
     `python-structure-hash-report`
   - Python structural planning: `python-structure-hash-scope-plan` after
     dependency review exists; this creates the full Change Impact Packet with
     `impact_blocks`, `scope_candidates`, `selected_scope`, and
     `repair_batches`
   - Before / after diff: `python-structure-hash-impact`。比較が明示されたときだけ使う
   - Algorithm modules: `python-algorithm-contract-check`
   - Module groups: `python-module-groups-check`
   - OOP readability: `tools/oop/<language>/readability.py --format json`
   - Dependency surface: `run_repo_dependency_review.sh` and related manifest tools
   - Design evidence drift: `check_design_doc_claims.py`
1. 全 finding に deterministic priority を付けます。tool が priority を持たない
   場合も、少なくとも severity、public API / algorithm contract 影響、dependency
   fan-in / fan-out、single-caller / duplicate / thin-structure signal、test /
   experiment / production scope、tool confidence を使って機械的に並べます。ranking
   rule は report に残し、同じ入力から同じ順序になるようにします。
1. report では機械結果と agent interpretation を分けます。reader-facing report に
   する場合は `report-writing` を使います。
   - user が「レポート」「まとめ」「結果を解釈」「Markdown にして」などを求めた場合、
     `report-writing` は必須です。validation summary、command log、top-N excerpt、
     raw JSON path だけで closeout してはいけません。
   - 非自明な finding packet では、draft 前に `structure-planning` を使い、source
     packet、reader guide、metric / count contract、priority policy、limitations、
     next actions を固定します。
   - report は full structured artifact を参照してよいですが、underlying artifact
     は削らず、report 側に full table の保存先と取捨選択境界を明記します。
1. finding を分類します。
   - `implementation_bug`: 実装を直す
   - `missing_test_or_design_evidence`: test / design artifact を直す
   - `missing_design_claim_evidence`: design claim を code、dependency header、parent-doc evidence に接続する
   - `handoff_prompt_gap`: 次の subagent handoff prompt を直す
   - `shared_skill_or_workflow_gap`: skill / workflow / task catalog prompt を直す
   - `tool_gap`: tool rule、false positive、structured output を直す
   - `review_required`: 機械判定だけでは採否を決めない
1. tool、hook、checker、migration wrapper が warning を出したら、その場で
   run-local `reports/agents/<run-id>/workflow_monitoring.md` の `## Tool Warnings`
   に登録します。再利用する template は
   `agents/templates/workflow_monitoring.md` です。warning は
   stdout / stderr の一時表示ではなく、owner / status / repair command 付きの
   closeout obligation です。

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --tool-warning "warning_id=<stable-id> source_tool=<tool> severity=<warning|fix-now|s0|s1> status=open message=<short-no-spaces> repair_command=<command-or-doc>"
```

   修復後は同じ `warning_id` を `status=resolved evidence=<path-or-command>` で
   追記します。通常 warning の `tool_warning_exit_status` は `resolved`、
   durable owner 付きの `deferred_with_issue issue=<issue-or-pr>`、または
   `explicit_approval_evidence` と durable rationale artifact 付きの
   `accepted_with_reason` に接続します。fix-now / S0 / S1 は resolved にします。
   警告がなければ次で `tool_warnings_status: none` を明示します。

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --tool-warning-status none
```
1. `handoff_prompt_gap` または `shared_skill_or_workflow_gap` は、次の
   write-capable subagent を起動する前に prompt を修正します。closeout へ先送り
   しません。
1. prompt feedback は run bundle に構造化して残します。

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --runtime-feedback "source=<tool|hook|reviewer|subagent|user> target=<skill-or-workflow-or-handoff> action=prompt_repair reason=<short-reason>"
```

1. shared skill / workflow prompt を直した場合は、該当 prompt eval を確認し、
   実行可能なら次を rerun します。

```bash
python3 tools/agent_tools/evaluate_skill_workflow_prompts.py \
  --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml
```

## Refactor Integration

`refactor-loop` は、この skill が作った finding packet を入力として使います。
実装前に baseline packet を作り、1 slice 後に同じ tool set を再実行し、
必要なら impact packet を作ってから次の slice を選びます。slice selection では
full finding packet と mechanical priority order から上位 agent が修正対象を選び、
`tool-finding-report` 自体は finding を隠さず、修正対象の採否判断もしません。

write-capable subagent への handoff には、finding packet path、current
`repair_slice`、`Forbidden Semantic Delta`、新規 finding を増やさない制約、
prompt feedback decision を含めます。
