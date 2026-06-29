# agent-log-analysis
<!--
@dependency-start
contract skill
responsibility Documents agent-log-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime-log-archive.md accumulated eval and hook result storage
upstream design ../../documents/search-coordination.md coordinated search policy
upstream design ../../documents/runtime-log-archive.md defines the external log archive mount and branch policy
downstream design issue-finding-report.md converts compact log findings into durable issues
upstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py owns structured dashboard API fields
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py resolves the mounted log archive
downstream implementation ../../.agents/skills/agent-log-analysis/SKILL.md exposes this workflow as a runtime skill
downstream design agent-eval-accumulation.md repairs missing accumulated eval family evidence
@dependency-end
-->

## Reader Map

- Purpose: turns accumulated AgentCanon logs into structured dashboard evidence
  before interpreting routing misses, skill gaps, or workflow behavior.
- Use When: analyzing skill, tool, workflow, hook, eval, wave, or subagent logs
  for repeated misses or selection gaps.
- Section path: Purpose and Use When define the trigger; Required Flow is the
  mandatory checklist; Boundaries and Finding Route Packet define what may be
  claimed and handed off.
- Boundary: do not read raw logs broadly before generating the structured summary.

## Purpose

skill、tool、workflow、hook、eval の蓄積ログを、AgentCanon source tree
ではなく dashboard API / structured summary に変換してから
分析するための skill です。

## Use When

- user が skill / tool / workflow / hook のログ分析、弱い skill、routing miss、selection gap、蓄積分析を求めている
- user が skill が呼ばれない、呼び出しが遅い、関連 skill 候補が狭い、
  または違う後続 surface に route されるという runtime feedback を出している
- `.agent-canon/log-archive/**`、`reports/**`、event file を読みそうな調査で、先に要約が必要
- dashboard や improvement guide の signal をもとに、どの skill / tool / workflow を直すか判断する
- token 消費を抑えながら AgentCanon runtime evidence を見る
- accumulated eval family の missing / stale / fail を見つけ、producer / checker loop
  に戻す必要がある
- structured evidence を durable skill issue 候補に変換する前段分析を行う

## Required Flow

1. 通常分析の入力を structured API / Markdown summary に固定します。
1. AgentCanon 側では external log archive の mount / branch 状態だけを確認します。

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py sync
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

1. archive hygiene は `sync`、`check-clean`、dashboard 生成、final `sync`
   の順で扱います。望ましい閉じ状態は
   `RUNTIME_LOG_ARCHIVE_CLEAN=yes` です。直前 command の runtime hook が
   current repo key の live hook file だけを追記し、
   `RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no` の場合は、その path を
   `live_hook_tail_dirty` として記録し、dashboard 生成へ進みます。closeout
   では final `sync` の `RUNTIME_LOG_ARCHIVE_SYNC=pass`、foreign dirty
   なし、live hook tail path を evidence にします。foreign dirty key がある場合は
   該当 repo_key の sync / migration を先に解消します。
1. source repo root から AgentCanon source dashboard tool を呼びます。tool が
   AgentCanon root と mounted log archive を解決するため、`<source-root>` は
   解析対象 repo の root とします。

```bash
python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
  --root <source-root> \
  --compact-out reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-out reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

1. `agent-log-analysis-api.json` または `agent-log-analysis-compact.md` を
   既定入力として読みます。log archive repo は append-only evidence を所有し、
   AgentCanon source dashboard が集計、移動平均、routing evidence cell を
   所有します。
1. structured summary で足りない観点がある場合は、AgentCanon source
   dashboard API owner に `dashboard_api_contract_gap` として修復を route してから
   API / report profile を拡張します。
1. API JSON では、少なくとも次の field を normal analysis contract として確認します: `unknown_event_count`, `status_by_hook_family`, `failure_by_hook_family`, `skip_by_hook_family`, `namespace_debt_by_hook_family`, `oop_applicability`。
1. eval family gap を見るときは、dashboard の推測ではなく
   `eval_accumulation_check.py --compact-out ...` を走らせます。missing / stale / fail
   があれば `$agent-eval-accumulation` に移り、`run_accumulated_agent_evals.py`、
   再 check、archive sync の順で閉じます。
1. event file drilldown は tool 実装、schema debugging、破損 audit、または API が明示した drilldown path に限定します。読む場合は理由を明示し、`tail`、focused parser、または path 限定 `git grep -n` を使います。
1. user-facing report では、観測値、解釈、修正先、未確認仮説を分けます。
1. structured evidence を durable skill issue に変換する場合は、`issue-finding-report`
   に渡し、抽象原因、重複検索、dependency-expanded edit scope、multi-agent
   partition をそこで固定します。

## Boundaries

- この skill は log archive API、structured summary、routing miss、selection gap、
  missed / late skill invocation、over-constrained related-skill coverage、
  wave execution reconciliation の観測と解釈を所有します。
- 実際の prompt / workflow / tool 修正は、下の route packet を作ってから対象
  skill / role へ渡します。
- durable issue 作成は `issue-finding-report` の責務です。この skill は issue
  作成に必要な structured evidence と finding route packet を渡します。
- Durable report を残す必要がある場合は `$result-artifact-writeout` を使います。
- Full dashboard は human review 用です。agent の通常分析入力は
  `generate_agent_runtime_dashboard.py --api-out` の JSON、structured summary、
  generated evidence cell を既定にします。
- Normal analysis reads structured API fields first. `unknown_event_count` routes missing event taxonomy, `status_by_hook_family` routes status distribution, `failure_by_hook_family` routes failure ownership, `skip_by_hook_family` routes skipped hook ownership, `namespace_debt_by_hook_family` routes legacy namespace debt, and `oop_applicability` routes OOP hook applicability findings.

## Finding Route Packet

Log analysis から修復 wave へ進むときは、次の deterministic packet を run
bundle に残します。

```text
finding_class=<wave_execution|skill_selection|tool_selection|workflow_selection|workflow_attribution|eval_gap|token_coverage|archive_hygiene|prompt_or_config_drift|structure_boundary>
evidence_cells=<structured dashboard section or API field paths>
route_target=<skill-or-role>
instance_partition=<repo_key|hook_family|skill_name|workflow_name|issue_id|path_scope>
required_packet=<artifact path>
closeout_gate=<command or evidence field>
```

| finding_class | route_target | required_packet | closeout_gate |
| --- | --- | --- | --- |
| `wave_execution` | `subagent-bootstrap` + `prompt_config_reviewer` when role config is implicated | compact Wave And Subagent Execution drilldown, affected run bundle paths, planned-vs-actual wave ids | `workflow_monitoring.md` actual wave rows reconciled or issue updated |
| `skill_selection` | affected skill + `prompt_config_reviewer` | Selection Evidence drilldown row, skill source path, reset basis | skill prompt eval or dashboard miss rate after reset window |
| `tool_selection` | `tools/catalog.yaml`, owning tool docs, and invocation guidance | Selection Evidence drilldown row, tool catalog entry, owning tool doc path | tool catalog validation and dashboard miss rate after reset window |
| `workflow_selection` | `agents/TASK_WORKFLOWS.md` and owning workflow guide | Selection Evidence drilldown row, workflow registry row, owning workflow doc path | workflow selection eval or dashboard miss rate after reset window |
| `workflow_attribution` | `agent-learning` or hook owner role | Workflow Attribution drilldown, missing event class, hook namespace | dashboard workflow missing count reduced or exemption recorded |
| `eval_gap` | `agent-eval-accumulation` | eval accumulation structured output, missing / stale / fail families | `eval_accumulation_check.py` pass or issue updated |
| `token_coverage` | `agent-learning` + runtime logging owner | Token Consumption drilldown and token moving-average status | token comparison / summary evidence present or unsupported claim recorded |
| `archive_hygiene` | `result-artifact-writeout` or log archive owner | `runtime_log_archive_git.py status/check-clean` output | `RUNTIME_LOG_ARCHIVE_CLEAN=yes` |
| `prompt_or_config_drift` | `prompt_config_reviewer` | affected prompt/config path and structured evidence cell | reviewed patch or routing issue updated |
| `structure_boundary` | `structure-refactor` | evidence cell plus candidate path / view boundary | structure repair contract or structure issue updated |

When one structured summary contains several independent findings, split follow-up
subagents by `instance_partition`. Suggested same-role instance id:
`<role_type>:<repo_key>:<finding_class>:<partition>:<seq>`.
