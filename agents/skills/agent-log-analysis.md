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

- Purpose: interpret accumulated AgentCanon logs using existing structured
  evidence by default, with bounded drilldown when it cannot answer the question.
- Use When: analyzing skill, tool, workflow, hook, eval, wave, or subagent logs
  for repeated misses or selection gaps.
- Section path: Required Flow owns read-only analysis; Selected Acquisition And
  Repair owns optional follow-up; Boundaries and Finding Route Packet separate
  supported claims from repair work.
- Boundary: analysis does not require archive maintenance, dashboard repair, or
  eval reruns. Do not expand raw logs broadly or claim evidence that is absent.

## Purpose

skill、tool、workflow、hook、eval の蓄積ログを、既存の dashboard API /
structured summary を既定入力として分析する skill です。
必要な要約がない場合は、対象を限定した読取で確認できる範囲を報告します。

既存 snapshot `S` に対する分析 `A(S)` は、archive を別の snapshot に更新する
操作の成功を必要としません。鮮度・欠落・対象範囲は結論を制限する根拠であり、
周辺システムの修理を分析の終了条件へ加える理由ではありません。

## Use When

- user が skill / tool / workflow / hook のログ分析、弱い skill、routing miss、selection gap、蓄積分析を求めている
- user が skill が呼ばれない、呼び出しが遅い、関連 skill 候補が狭い、
  または違う後続 surface に route されるという runtime feedback を出している
- `.agent-canon/log-archive/**`、`reports/**`、event file から対象を限定して調査する
- dashboard や improvement guide の signal をもとに、どの skill / tool / workflow を直すか判断する
- token 消費を抑えながら AgentCanon runtime evidence を見る
- accumulated eval family の missing / stale / fail を観測・報告する
- 蓄積 evidence を durable skill issue 候補に変換する前段分析を行う

## Required Flow

1. 質問、読む repository / artifact、snapshot、期間、coverage を取得済みの
   evidence から特定します。保存済み記録を現行 runtime の再現と扱いません。
   読める snapshot の分析に `ensure`、`sync`、`check-clean`、最新版化、
   foreign dirty の解消を要求しません。mutable な入力は観測時点と範囲を明示します。
1. 既存の `agent-log-analysis-api.json` または
   `agent-log-analysis-compact.md` などの structured summary を再利用します。
   両形式の用意や再生成は不要です。必要な項目がない場合は
   `dashboard_api_contract_gap` として不足を記録し、API 修理を待たず、既知の
   path・期間・行範囲に限定した `tail`、focused parser、path 限定
   `git grep -n`、connector の読取で調査を進めます。drilldown の理由と範囲を
   明示し、無制限な raw JSONL 展開は行いません。
1. 質問に必要な API field と、その snapshot での意味・coverage を確認します。
   通常の観点は `unknown_event_count`、`status_by_hook_family`、
   `failure_by_hook_family`、`skip_by_hook_family`、
   `namespace_debt_by_hook_family`、`oop_applicability` です。欠落をゼロ・成功に
   変換せず、証拠がない主張だけを unknown / 未検証にします。未選択の観点を
   埋めるための一律 checklist や否定値の記録は作りません。
1. eval family の missing / stale / fail は、既存の checker output や report の
   snapshot とともに観測事項として扱います。必要なら Issue へ記録しますが、
   観測だけで `agent-eval-accumulation`、producer 再実行、過去ログ移行へ
   自動的に進みません。追加の検査・収集が必要な場合は次の節に従います。
1. 観測、解釈、修正先、未確認仮説、調査範囲の制限を分けて報告します。
   Issue 起票が依頼範囲なら、取得できた summary / checker output / bounded
   excerpt と snapshot を `issue-finding-report` に渡します。分析と起票は
   修理完了を待ちません。取得不能な入力はそのまま示し、証拠を作りません。

## Selected Acquisition And Repair

追加操作は、依頼された成果物または特定の主張に必要な証拠取得のためにだけ
選びます。新規収集、archive 保守・公開、dashboard API 修理、eval 修理は
読取分析とは別の操作です。実際に選択した操作の権限・入力・検証境界を
各 owner から消費し、その失敗を成功へ変換しません。独立した確認済み観測は
報告でき、修理待ちを元の分析の終了条件へ追加しません。

新しい structured summary が必要で実行可能な場合は、既存の source dashboard
owner を使います。tool が AgentCanon root と mounted log archive を解決します。

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
source checkout is never used as an output directory. An unavailable tool
limits new evidence, not access to already readable evidence.

Source-bound runtime-event collection, only when selected, requires the runtime
owner to provide `AGENT_CANON_CODEX_SESSION_ROOT` for the active container-local
session directory. It does not inspect host `HOME`, `CODEX_HOME`, or
`~/.codex/sessions`; an absent root is a fail-closed source absence for that
collection operation, not a blocker on reading archived snapshots.

An eval-family verification may use `eval_accumulation_check.py --compact-out ...`
when its result is needed. Its missing / stale / fail output is reportable
without repair. Only selected eval repair uses
[agent-eval-accumulation](agent-eval-accumulation.md)'s producer/checker/archive
loop. Archive writes and synchronization use
[the archive owner](../../documents/runtime/runtime-log-archive.md), not a
second sync/clean protocol in this analysis skill. Foreign dirty state remains
untouched by read-only analysis.

## Boundaries

- この skill は log archive API、structured summary、routing miss、selection gap、
  missed / late skill invocation、over-constrained related-skill coverage、
  wave execution reconciliation の観測と解釈を所有します。
- log archive repo は append-only evidence、AgentCanon source dashboard は
  集計、移動平均、routing evidence cell を所有します。bounded drilldown を
  新しい集計正本や欠落データの推定値へ変えません。
- 実際の prompt / workflow / tool 修正を選択した場合は、下の route packet を
  対象 skill / role へ渡します。finding の記録だけでは修理を起動しません。
- Token budget、baseline、role footprint、efficiency decision は `$tokens` が
  所有します。token coverage / moving-average evidence がなければ token の
  主張は unsupported とし、件数から使用量を推定しません。
- IssueWorker の公開実績は `github_issue_refs` と
  `issue_publication_action_counts` の published receipt を読み、
  `issue_worker.qualified` などの candidate counts と混ぜません。receipt に
  Issue/private body、digest、fingerprint、認証情報を含めません。receipt 欠落や
  pending 消失から公開済みとは推定しません。実際の GitHub publication / remote
  readback と post-publication receipt は
  [issue-finding-report](issue-finding-report.md) の既存 owner に委譲します。
- Durable report を書く場合だけ `$result-artifact-writeout` を使います。
  分析の結論を報告・Issue 化するために、archive 全体の clean 化を要求しません。

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
file-backed packet. The table's closeout gates apply only to selected repair
work, not to analysis or Issue recording. Missing evidence stays explicit;
producing a packet does not authorize its repair action.

```text
finding_class=<wave_execution|skill_selection|tool_selection|workflow_selection|workflow_attribution|eval_gap|token_coverage|archive_hygiene|prompt_or_config_drift|structure_boundary>
evidence_cells=<available summary/API fields or snapshot-bound excerpt locators and gaps>
route_target=<skill-or-role>
instance_partition=<repo_key|hook_family|skill_name|workflow_name|issue_id|path_scope>
required_packet=<structured handoff or durable artifact path when needed>
closeout_gate=<selected repair command or evidence field>
```

| finding_class | route_target | required_packet | closeout_gate |
| --- | --- | --- | --- |
| `wave_execution` | `subagent-bootstrap` + `prompt_config_reviewer` when role config is implicated | compact Wave And Subagent Execution drilldown, planned-vs-actual wave ids, and the overplanning/logging-gap classification | logging-gap rows reconciled or the unresolved owner finding is recorded |
| `skill_selection` | affected skill + `prompt_config_reviewer` | Selection Evidence drilldown row, skill source path, reset basis | skill prompt eval or dashboard miss rate after reset window |
| `tool_selection` | `tools/catalog.yaml`, owning tool docs, and invocation guidance | Selection Evidence drilldown row, tool catalog entry, owning tool doc path | tool catalog validation and dashboard miss rate after reset window |
| `workflow_selection` | [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md) and owning workflow guide | Selection Evidence drilldown row, workflow registry row, owning workflow doc path | workflow selection eval or dashboard miss rate after reset window |
| `workflow_attribution` | `agent-learning` or hook owner role | Workflow Attribution drilldown, missing event class, hook namespace | dashboard workflow missing count reduced or exemption recorded |
| `eval_gap` | `agent-eval-accumulation` when repair is selected | existing checker output or snapshot-bound missing / stale / fail evidence | selected repair's `eval_accumulation_check.py` pass or unresolved finding recorded |
| `token_coverage` | `tokens` + runtime logging owner | Token Consumption drilldown and token moving-average status | token comparison / summary evidence present or unsupported claim recorded |
| `archive_hygiene` | `result-artifact-writeout` or log archive owner when maintenance is selected | available archive state and affected snapshot / paths | selected archive operation's own validation; clean state is not an analysis gate |
| `prompt_or_config_drift` | `prompt_config_reviewer` | affected prompt/config path and structured evidence cell | reviewed patch or routing issue updated |
| `structure_boundary` | `structure-refactor` | evidence cell plus candidate path / view boundary | structure repair contract or structure issue updated |

When one structured summary contains several findings, group them by owning
replaceable responsibility before splitting follow-up work. Use
`instance_partition` only for independent owner, write-authority, context,
validation, or review boundaries. Suggested same-role instance id:
`<role_type>:<repo_key>:<finding_class>:<partition>:<seq>`.

## Runtime Contract Clauses

The runtime discovery adapter delegates these operating clauses to this canonical owner.

1. Follow Required Flow for read-only analysis. Reuse an existing API JSON or
   compact Markdown summary; neither fresh generation, both output formats,
   archive sync/clean, nor foreign dirty repair is an analysis prerequisite.
1. When a needed field or summary is unavailable, record
   `dashboard_api_contract_gap` and use a bounded, snapshot-qualified drilldown
   with an explicit reason. Do not wait for dashboard repair or broaden raw
   log access. Missing evidence limits the affected claim, not other findings.
1. Check the question-relevant API fields and coverage described in Required
   Flow. Report observations, interpretation, repair target, and unknowns
   separately; absent fields are not zero or successful observations.
1. Record eval missing / stale / fail evidence without automatically running
   producers or migrating old logs. Selected verification may run the existing
   checker; only selected repair uses `$agent-eval-accumulation`'s loop.
1. Apply Selected Acquisition And Repair only to operations actually selected.
   Preserve collection source authority, read-only targets, external outputs,
   credentials, and archive/publication integrity. Do not claim an unavailable
   collection, failed write, or missing publication receipt succeeded.
1. Classify missing actual wave rows as `overplanning`, `logging_gap`, or
   `unresolved` before reconciliation. Only supported logging gaps are eligible
   for repair; never backfill overplanning or unresolved rows as executions.
1. Answer token-use questions from token coverage/moving-average evidence.
   Without it, say token claims are unsupported.
1. For durable Issues, give `$issue-finding-report` the available evidence,
   snapshot, limitations, and tentative cause. Issue recording does not require
   a dashboard repair, eval rerun, or archive maintenance success.
1. Before a selected prompt, skill, workflow, or tool repair, use Finding Route
   Packet and its owner table. A structured handoff or tool result suffices;
   durable files are for coordination/resumption, not every finding.
1. Group findings by owning replaceable responsibility and compatible context;
   split instances only across independent boundaries. Use
   `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>` when needed.
1. For a requested durable report, pair this skill with `$result-artifact-writeout`.
