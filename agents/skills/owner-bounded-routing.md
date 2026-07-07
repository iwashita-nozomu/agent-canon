# owner-bounded-routing

<!--
@dependency-start
contract skill
responsibility Documents owner-bounded-routing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../task_catalog.yaml owns Owner-Bounded Change workflow identity
upstream design ../../documents/runtime-profiles-and-check-matrix.md owns Routine docs and Focused code validation profiles
downstream implementation ../../tools/agent_tools/convention_compliance_contracts.toml declares owner-bounded marker contract
downstream implementation ../../.agents/skills/owner-bounded-routing/SKILL.md exposes this route as a runtime skill
@dependency-end
-->

## Purpose

owner boundary、差し替え可能な単位、targeted validation route、public behavior /
schema impact が evidence で閉じている repo-changing 修正で、広い workflow prose を
読み足さずに、既存 tool の直接利用、軽量 preflight、targeted validation、
closeout evidence を固定します。

この skill は `Owner-Bounded Change`、Routine docs、Focused code、
typo / link / format-only の薄い実行面を担当します。workflow family、
spawn budget、risk profile は `agents/task_catalog.yaml` と
`documents/runtime-profiles-and-check-matrix.md` に委譲します。

## Use When

- owner boundary、差し替え可能な単位、targeted validation route、public impact
  boundary が evidence で閉じている局所修正を行う
- typo / link / format-only の Markdown 修正を行う
- owner-bounded route で既存 tool を読了 gate なしに先に使う
- user request が bounded route または `Owner-Bounded Change` を示す
- broad design review より先に targeted validation で閉じられるかを判定する
- file 数や抽象の数は補助 signal に留め、それだけではこの route を固定しない

## Route Contract

1. `$agent-orchestration` の後にこの skill を選びます。
1. 既存 tool の実行や patching の前提として runtime `SKILL.md` 読了を要求しません。
   既存 tool が対象 property を持つ場合は tool を先に使い、出力の解釈や修正に
   必要な owner surface だけを開きます。
1. owner boundary、existing-tool route、targeted validation を作業 evidence に残します。
1. `python3 tools/agent_tools/tool_rejection_preflight.py --root .
   <planned-edit-paths>` を使い、予測される checker / hook / dependency repair
   commands を記録します。
   `responsibility_scope` 行の owner scope と protecting tools を実装ディレクトリの
   選択前に記録します。
1. typo / link / format-only では `$md-style-check` を併用し、
   `structure_contract=skipped` と理由を残します。
1. owner-bounded code 修正では、changed-file dependency checks、該当 static checker、
   型 / lint / OOP readability などの owner checker、直接関連 test を validation
   route に置きます。
1. targeted validation が fail した場合は、pass 目的の実装単純化、revert、
   intended behavior / test の削除、oracle weakening、validation downscope へ進む前に
   `failing_contract`、`observation_level`、`cause_classification`、
   `intent_preservation`、`evidence` を記録します。approved intent を保てる
   implementation bug は同じ owner-bounded slice で修復し、oracle / spec、
   fixture / environment / stale artifact、unrelated failure、approved-design /
   user-request conflict はそれぞれ owner route、residual、または escalation に分けます。
1. public behavior、dependency direction、document responsibility、claim grounding、
   schema、runtime profile、複数 writer が入った場合は、`codex-task-workflow` の
   broader route に戻します。

## Evidence

- owner boundary and owner path
- existing tool or command packet used first
- nearby owner context opened only when needed to interpret or repair tool output
- route: `Owner-Bounded Change` / Routine docs / Focused code / format-only
- targeted validation commands and results
- escalation reason when broader route is selected
