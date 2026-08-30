# agent-log-analysis
<!--
@dependency-start
contract skill
responsibility Documents agent-log-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime/runtime-log-archive.md accumulated eval and hook result storage
upstream design ../../documents/tools/search-coordination.md coordinated search policy
upstream design ../../documents/runtime/runtime-log-archive.md defines the external log archive mount
downstream design issue-finding-report.md converts compact log findings into durable issues
upstream implementation ../../eval/producers/generate_agent_runtime_dashboard.py owns structured dashboard API fields
upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py resolves the mounted log archive
downstream implementation ../../.codex/personal/skills/agent-log-analysis/SKILL.md exposes this workflow as a runtime skill
downstream design agent-eval-accumulation.md repairs missing accumulated eval family evidence
@dependency-end
-->

The consumed stable-branch and retention policy provenance is recorded in
[agent-canon-log PR #4](https://github.com/iwashita-nozomu/agent-canon-log/pull/4).
This external evidence link is intentionally prose metadata; dependency headers
contain only repository-local owner paths.

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

1. Source-bound runtime-event collection requires the runtime owner to provide
   `AGENT_CANON_CODEX_SESSION_ROOT` for the active container-local session
   directory. It does not inspect host `HOME`, `CODEX_HOME`, or
   `~/.codex/sessions`; an absent root is a fail-closed source absence.

```bash
python3 tools/runtime/archive/runtime_log_archive_git.py ensure
python3 tools/runtime/archive/runtime_log_archive_git.py status --porcelain
python3 tools/runtime/archive/runtime_log_archive_git.py sync
python3 tools/runtime/archive/runtime_log_archive_git.py check-clean --porcelain
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
./bootstrap.sh --control-parent-root <control-parent-root> \
  --runtime-root <runtime-root> \
  tool run --root <registered-source-root> generate-agent-runtime-dashboard -- \
  --root . \
  --compact-out reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-out reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

The outer `--root` selects the registered read-only target for the shared
container. The dashboard arguments are evaluated inside that container, and
the relative report paths are resolved below the external runtime root; the
source checkout is never used as an output directory.

1. `agent-log-analysis-api.json` または `agent-log-analysis-compact.md` を
   既定入力として読みます。log archive repo は append-only evidence を所有し、
   AgentCanon source dashboard が集計、移動平均、routing evidence cell を
   所有します。
1. structured summary で足りない観点がある場合は、AgentCanon source
   dashboard API owner に `dashboard_api_contract_gap` として修復を route してから
   API / report profile を拡張します。
1. API JSON では、少なくとも次の field を normal analysis contract として確認します: `unknown_event_count`, `status_by_hook_family`, `failure_by_hook_family`, `skip_by_hook_family`, `namespace_debt_by_hook_family`, `oop_applicability`。IssueWorker の公開結果を扱う場合は、`github_issue_refs` と `issue_publication_action_counts` を private archive の published receipt から読み、`issue_worker.qualified` などの candidate counts と混ぜません。receipt に Issue/private body、digest、fingerprint、認証情報がないことも確認します。
1. IssueWorker の publisher は GitHub mutation 前に external runtime/spool の receipt route を確認します。成功後は canonical `bootstrap.sh ... tool run/exec issue-sync -- --stage-publication-receipt` で resident container の body-free receipt を spool へ書き、host shell の private-log sync 後に dashboard が published namespace を読みます。route がない成功や pending 消失から公開済みとは推定しません。
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
   `generate-agent-runtime-dashboard` の API output、structured summary、
  generated evidence cell を既定にします。
- Normal analysis reads structured API fields first. `unknown_event_count` routes missing event taxonomy, `status_by_hook_family` routes status distribution, `failure_by_hook_family` routes failure ownership, `skip_by_hook_family` routes skipped hook ownership, `namespace_debt_by_hook_family` routes legacy namespace debt, and `oop_applicability` routes OOP hook applicability findings.

## Archive branch policy

Stable branch identity is owned by the `agent-canon-log` policy repository. The
source adapter reads the normalized Git remote and uses its
`logs/<stable-source-repository-id>` branch. Filesystem paths and chat/session
IDs remain metadata only. Migration inventory and retention are read-only
policy-owner workflows; this skill consumes dashboard evidence and does not
restate or implement their schema.

## Work Amplification And Wave Interpretation

Work amplification is an evidence relationship, not a raw file, line, spawn, or
wave count. Compare tool selections, spawn records, planned and actual wave
rows, packet materialization, checker execution, and the resulting owner action
before proposing a repair. A large packet or manifest is evidence of work
surface; it is not evidence that every planned action was launchable or needed.

Classify every missing actual wave before proposing reconciliation:

- `overplanning`: the planned row has no launch evidence and its surrounding
  evidence is conditional, authority-blocked, skipped, or otherwise not
  launchable;
- `logging_gap`: launch, completion, or delegated execution evidence exists but
  the corresponding actual row is absent; only this class is eligible for a
  logging repair;
- `unresolved`: the structured evidence cannot distinguish planning from
  logging and must remain an owner-held unknown.

Do not backfill `overplanning` or `unresolved` rows as executions. Group related
findings by the owning replaceable responsibility and compatible context, then
create one route or handoff per responsibility. A finding count does not create
one agent, packet, wave, or review instance per finding; split only when owner,
write authority, context integrity, validation route, or review gate is
independent.

## Finding Route Packet

Log analysis から修復 wave へ進むときは、次の structured route packet を
handoff message、tool result、または coordination/resumption 用の durable
file に残します。repo-changing work alone does not require a run bundle or a
file-backed packet.

```text
finding_class=<wave_execution|skill_selection|tool_selection|workflow_selection|workflow_attribution|eval_gap|token_coverage|archive_hygiene|prompt_or_config_drift|structure_boundary>
evidence_cells=<structured dashboard section or API field paths>
route_target=<skill-or-role>
instance_partition=<repo_key|hook_family|skill_name|workflow_name|issue_id|path_scope>
required_packet=<structured handoff or durable artifact path when needed>
closeout_gate=<command or evidence field>
```

| finding_class | route_target | required_packet | closeout_gate |
| --- | --- | --- | --- |
| `wave_execution` | `subagent-bootstrap` + `prompt_config_reviewer` when role config is implicated | compact Wave And Subagent Execution drilldown, planned-vs-actual wave ids, and the overplanning/logging-gap classification | logging-gap rows reconciled or the unresolved owner finding is recorded |
| `skill_selection` | affected skill + `prompt_config_reviewer` | Selection Evidence drilldown row, skill source path, reset basis | skill prompt eval or dashboard miss rate after reset window |
| `tool_selection` | `tools/catalog.yaml`, owning tool docs, and invocation guidance | Selection Evidence drilldown row, tool catalog entry, owning tool doc path | tool catalog validation and dashboard miss rate after reset window |
| `workflow_selection` | `agents/TASK_WORKFLOWS.md` and owning workflow guide | Selection Evidence drilldown row, workflow registry row, owning workflow doc path | workflow selection eval or dashboard miss rate after reset window |
| `workflow_attribution` | `agent-learning` or hook owner role | Workflow Attribution drilldown, missing event class, hook namespace | dashboard workflow missing count reduced or exemption recorded |
| `eval_gap` | `agent-eval-accumulation` | eval accumulation structured output, missing / stale / fail families | `eval_accumulation_check.py` pass or issue updated |
| `token_coverage` | `agent-learning` + runtime logging owner | Token Consumption drilldown and token moving-average status | token comparison / summary evidence present or unsupported claim recorded |
| `archive_hygiene` | `result-artifact-writeout` or log archive owner | `runtime_log_archive_git.py status/check-clean` output | `RUNTIME_LOG_ARCHIVE_CLEAN=yes` |
| `prompt_or_config_drift` | `prompt_config_reviewer` | affected prompt/config path and structured evidence cell | reviewed patch or routing issue updated |
| `structure_boundary` | `structure-refactor` | evidence cell plus candidate path / view boundary | structure repair contract or structure issue updated |

When one structured summary contains several findings, group them by owning
replaceable responsibility before splitting follow-up work. Use
`instance_partition` only for independent owner, write-authority, context,
validation, or review boundaries. Suggested same-role instance id:
`<role_type>:<repo_key>:<finding_class>:<partition>:<seq>`.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read the API JSON or compact Markdown as the default analysis input. The
   archive repo owns append-only evidence; the AgentCanon source dashboard owns
   aggregation, moving averages, and routing evidence cells.
1. Classify missing actual wave rows before proposing reconciliation as
   `overplanning`, `logging_gap`, or `unresolved`. Do not backfill overplanning
   or unresolved rows; only a supported logging gap routes to logging repair.
   Group findings by owning replaceable responsibility and compatible context,
   not one agent, packet, wave, or review per finding.
1. Confirm the API JSON includes the normal analysis fields `unknown_event_count`, `status_by_hook_family`, `failure_by_hook_family`, `skip_by_hook_family`, `namespace_debt_by_hook_family`, and `oop_applicability`.
1. When `generate_agent_runtime_dashboard.py` lacks a needed compact field,
   record `dashboard_api_contract_gap`, route that finding to the dashboard API owner,
   and rerun it after the source tool is repaired.
1. For eval family gaps, run `python3 eval/checkers/eval_accumulation_check.py --root . --compact-out reports/agents/<run-id>/eval-accumulation-before.json --format text`; if it reports missing, stale, or failing families, add `$agent-eval-accumulation` and use its producer/checker/archive loop.
1. Event-file drilldown is for tool development, schema debugging, corruption audit, or an API-named drilldown path; record an explicit rationale before reading it.
1. Answer token-use questions from the API token coverage/moving-average fields. If token status is missing, say token claims are unsupported.
1. Report observations separately from interpretation, repair target, and unknowns.
1. When the user asks to turn structured evidence into durable skill issues, hand
   the structured API output, structured Markdown summary, and Finding Route Packet to
   `$issue-finding-report`.
1. If the analysis drives a prompt, skill, workflow, or tool change, write the `Finding Route Packet` from `agents/skills/agent-log-analysis.md` before editing or spawning the repair wave. A structured handoff message or tool result satisfies it; use a durable file only for coordination or resumption. The packet must include `finding_class`, `evidence_cells`, `route_target`, `instance_partition`, `required_packet`, and `closeout_gate`.
1. Route by finding class:
   wave execution findings to `$subagent-bootstrap`;
   skill selection findings to the affected skill plus `prompt_config_reviewer`;
   tool selection findings to `tools/catalog.yaml` plus the owning tool docs;
   workflow selection findings to `agents/TASK_WORKFLOWS.md` plus the owning
   workflow guide; workflow attribution or token coverage findings to
   `$agent-learning` or the logging owner; eval gaps to
   `$agent-eval-accumulation`; archive hygiene findings to
   `$result-artifact-writeout` or the log archive owner; prompt/config drift to
   `prompt_config_reviewer`; and structure-boundary findings to
   `$structure-refactor`.
1. When one structured summary contains independent findings, split same-role review instances by `repo_key`, `hook_family`, `skill_name`, `workflow_name`, `issue_id`, or path scope. Use an instance id shaped like `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>`.
1. If the user asks for a durable report, pair this skill with `$result-artifact-writeout`.
