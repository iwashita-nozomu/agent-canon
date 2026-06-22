# small-change-routing

<!--
@dependency-start
contract skill
responsibility Documents small-change-routing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../task_catalog.yaml owns Scoped Change Lite workflow identity
upstream design ../../documents/runtime-profiles-and-check-matrix.md owns Routine docs and Focused code validation profiles
upstream implementation ../../tools/agent_tools/convention_compliance_contracts.toml declares small change marker contract
downstream implementation ../../.agents/skills/small-change-routing/SKILL.md exposes this route as a runtime skill
@dependency-end
-->

## Purpose

小規模な repo-changing 修正で、広い workflow prose を読み足さずに、選択済み
runtime skill の読了、軽量 preflight、targeted validation、closeout evidence を
固定します。

この skill は `Scoped Change Lite`、Routine docs、Focused code、
typo / link / format-only の薄い実行面を担当します。workflow family、
spawn budget、risk profile は `agents/task_catalog.yaml` と
`documents/runtime-profiles-and-check-matrix.md` に委譲します。

## Use When

- 1 file または 1 abstraction unit の局所修正を行う
- typo / link / format-only の Markdown 修正を行う
- 小規模修正でも selected runtime `SKILL.md` を読む必要がある
- user request が「小規模修正」「軽微な修正」「small change」
  「Scoped Change Lite」を示す
- broad design review より先に targeted validation で閉じられるかを判定する

## Route Contract

1. `$agent-orchestration` の後にこの skill を選びます。
1. `selected_runtime_skill_read`、`small_change_skill_read`、skill 名、runtime
   `SKILL.md` path を作業 evidence に残します。
1. `python3 tools/agent_tools/tool_rejection_preflight.py --root .
   <planned-edit-paths>` を使い、予測される checker / hook / dependency repair
   commands を記録します。
1. typo / link / format-only では `$md-style-check` を併用し、
   `structure_contract=skipped` と理由を残します。
1. code の小規模修正では、changed-file dependency checks、該当 static checker、
   型 / lint / OOP readability などの owner checker、直接関連 test を validation
   route に置きます。
1. public behavior、dependency direction、document responsibility、claim grounding、
   schema、runtime profile、複数 writer が入った場合は、`codex-task-workflow` の
   broader route に戻します。

## Evidence

- selected skill: `<skill-name>`
- selected runtime skill path: `.agents/skills/<skill>/SKILL.md`
- `selected_runtime_skill_read`: yes
- `small_change_skill_read`: yes
- route: `Scoped Change Lite` / Routine docs / Focused code / format-only
- targeted validation commands and results
- escalation reason when broader route is selected
