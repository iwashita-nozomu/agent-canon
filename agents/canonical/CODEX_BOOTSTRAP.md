# Codex Bootstrap

<!--
@dependency-start
contract agent-runtime
responsibility Owns selected run bootstrap, goal state, and adaptive context materialization.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for a selected route requiring a run bundle, goal state, or token adaptation.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## Codex Goal Session State

Codex の goal は session runtime state として使い、repository に mirror file を作りません。

- stable な goal 機能は Codex runtime の既定を使い、shared config に feature flag を重ねません。
- user が goal-driven intent を示したが exact objective を渡していない場合は、parent が target-state-complete Objective を組み立てます。intake draft は read-only discovery として扱い、edit authorization は target-state-complete Objective と implementation handoff の固定後に開始します。
- coordination、resumption、または選択された workflow が durable lifecycle evidence を要求する場合だけ run bundle を materialize し、work unit と iteration state は `schedule.md`、実行結果と next action は `work_log.md`、acceptance は validation evidence に記録します。
- run bundle を選択しない task は semantic handoff または tool result で owner、replaceable unit、mechanism、validation route、unresolved branch を満たします。session goal の存在は write authorization、implementation readiness、closeout の追加 gate にしません。
- user が goal-driven task を指定した場合、session goal と実装計画は同じ objective と acceptance criteria を参照します。durable evidence が必要な場合は、その work breakdown を run bundle の `schedule.md` へ直接記録します。
- iteration の継続は `schedule.md` の open work、`work_log.md` の next action、未完了の validation evidence から判断します。session goal はその判断を表示できますが、repository state の正本にはしません。

## Token Observation And Adaptive Materialization

When the user asks to reduce token usage, or current session evidence shows
repeated context loading, duplicate agent decisions, oversized tool output, or
retry loops, apply `$tokens`.

- Start from the project model and topology config. Runtime evidence owns any
  later task/profile classification or profile change.
- Materialize one accountable child for the current decision. Add a specialist
  only when a distinct input artifact, review focus, and output decision exist.
- Context may be large. Remove duplicated or decision-irrelevant copies, not
  context required by request clauses, owner boundaries, or traceability.
- Keep `worker` as the implementation default. Select `spark_worker` only from
  the typed parent packet. Explicit bounded owner/path/validation requests may
  close through the selected write-capable child route when the typed route
  requires one.
- Attribute change with the existing session comparison, role evaluator, and
  runtime dashboard tools. Missing post-change runtime evidence remains
  `missing`; it is not inferred from fewer configured roles.

Token-saving changes context loading while preserving correctness gates. The
active gates are those selected by runtime profile and risk class.

## 4. Run Bootstrap

repo-changing task では semantic handoff を既定にし、coordination、resumption、または
selected workflow が durable lifecycle evidence を要求する場合だけ bundle と
explicit subagent activation を materialize します。
stage の具体的な責務と実行条件は prose ではなく `.codex/agents/*.toml` を正本にします。
この文書は executable stage flow の正本です。workflow family 選定は
`agent-orchestration`、prompt / config drift 監査は `prompt_config_reviewer`
を先に通し、ここは executable stage flow に保ちます。
goal-driven task でも provisional bundle は coordination/resumption または owner-critical
evidence が次の判断を変える場合だけ作り、candidate role の handoff plan を先に
materialize しません。active runtime が明示許可を要求する場合は、許可があるときだけ
実際に起動します。

- repo を編集する
- specialist handoff を明示したい
- review artifact を残したい
- 長めの task で run 単位の記録が必要
- subagent と parent の責務を分けたい

Full staging、bounded execution、child handoff の positive selectionは、
`agents/task_catalog.yaml#workflow_activation_policy` と選択 family の
`roles` / `role_topology` records から解決します。owner-critical decision、distinct
unresolved claim/risk、または selected validation route が要求した role だけを
materialize します。W2 の completion predicate は approved typed contract evidence と
active owner route に結び付けます。bounded owner route は
`external public API/behavior/schema unchanged` の場合だけ維持します。public surface
の追加、縮小、削除、rename、restriction、deprecation、意味変更がある場合は
`scoped_change` または broader route へ進み、`dependency/consumer/migration/docs closure`
を scope 形成します。reader-facing docs、新用語、cross-surface risk がある場合も
従来どおり broader route へ進みますが、その理由だけで同 closure を無条件要求しません。
Agent Wave に固定 plan-review-edit 順序はありません。bootstrap は selected stages だけを
`team_manifest.yaml`、`schedule.md`、`workflow_monitoring.md` に記録します。
bootstrap は `run.pre_handoff_scope_policy` も出します。implementation
surface route は source packet seed であり、responsibility search、reuse
survey、stale-surface scan、dependency expansion を通してから
`allowed_paths`、`do_not_read`、`write_scope`、`validation_route`、
`review_gate` の handoff scope にします。
`bootstrap_agent_run.py` は
`run.default_quality_check_policy` も出します。この policy は active な
`change_reviewer`、`docs_workflow_steward`、
`python_reviewer`、`cpp_reviewer` と、それらから展開される Codex
`agent_type`、task-default / changed-path / manual enable / review-pack
provenance、軽量 static check command を記録します。review と edit の
handoff はこの policy を含めます。
学術文章では、これに `notation_definition_reviewer` と `logic_gap_reviewer` を追加します。
論文や thesis chapter では、さらに `citation_evidence_reviewer` を追加します。
interactive Codex で要件整理と実行計画立案を行う場合は、parent session 側の plan-mode command を使ってから planning specialist を起動します。official Codex CLI では `/plan` です。
default の model / reasoning authority は `agents/model_profiles.toml` の closed registry です。`.codex/agents/*.toml` は generated runtime readback view です。code survey、tool drift survey、機械 report 要約、execution-only experiment / log work は Luna/high profile、通常の planning / authoring / review child は `gpt-5.6-luna/high`、`worker` と `ship_reviewer` は `gpt-5.6-luna/xhigh`、final judgment は `ship_reviewer` または decision-owning reviewer、`spark_worker` は fixed-packet `gpt-5.3-codex-spark/low`、fresh read-only T14 `skill_evaluation` は evaluator-only `gpt-5.4-mini/medium` profile を使います。
- subagent の depth は `.codex/config.toml` と active spawn budget で管理します。必要な追加層がある場合は delegated stage owner が owner、入力 packet、write scope、review gate を明示して展開します。
- active frontier、write scope、nested reservation、queue は capacity handshake owner が宣言 topology から生成し、その typed contract を workflow capacity policy の唯一の authority とします。fixed packet の標準経路は one Spark と one post-completion owning gate で、Luna は ambiguous design、causal repair、graph-owned cross-owner integration、review を保持します。
- workflow family ごとの subagent prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です。
- budget を超える場合は例外扱いにし、`schedule.md` と `work_log.md` に理由、追加 role、expected output、write scope を残します。
- write-capable frontier は `team_manifest.yaml` の dependency order、wave plan、disjoint write scope、integration order、review gate と capacity readback から生成します。衝突する target は順序制約として扱い、同じ file / canonical surface / shared root contract に触る作業は先行 wave の validation と tool rerun 後に後続 waveへ回します。分離済み writer は available write capacity 内の同一 wave、追加判断が要る writer は current checkout 内の後続 wave へ直列化します。

Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。

標準コマンド:

    python3 tools/runtime/lifecycle/bootstrap_agent_run.py \
      --task "short task summary" \
      --task-id T1 \
      --owner "codex" \
      --workspace-root "$PWD"

bundle 出力には少なくとも次が含まれます。

- `CROSS_CUTTING_DOCUMENT_PACKET`
- `DESIGN_DOCUMENT_PACKET`
- `IMPLEMENTATION_DOCUMENT_PACKET`
- `WORKFLOW_SUBAGENT_PROMPT_PACKET`
- `IMPLEMENTATION_SURFACE_ROUTE_STATUS` と route command
- `TOOL_REUSE_LEDGER_STATUS`
- `PRE_EDIT_REJECTION_PREDICTION_STATUS`
- task id / fan-out budget / active role evidence

parent は subagent handoff でこの packet path 群と `team_manifest.yaml` の `run.subagent_prompt_packet` / role 別 `prompt_contract` を local/tool context 参照として持ち、prompt には [agents/COMMUNICATION_PROTOCOL.md](../COMMUNICATION_PROTOCOL.md) の `Fresh Subagent Context Capsule` で選択した fields だけを入れて requested scope を保持した bounded packet routing を維持します。
handoff には `allowed_paths`、`do_not_read`、context artifact path、expected output schema、
`PRIMARY_PATHS` / `FORBIDDEN_PATHS`、reuse ledger、pre-edit rejection prediction を含めます。
`cross_cutting_document_packet` は利用可能な reference list であり、role ごとの work packet を選ぶために使います。広い request では、packet に含めなかった reference を `omitted_surfaces` として理由付きで残します。

研究・実験つき変更:

    python3 tools/runtime/lifecycle/bootstrap_agent_run.py \
      --task "research-backed change" \
      --task-id T4 \
      --owner "codex" \
      --workspace-root "$PWD"

環境変更:

    python3 tools/runtime/lifecycle/bootstrap_agent_run.py \
      --task "platform or environment change" \
      --task-id T8 \
      --owner "codex" \
      --workspace-root "$PWD"

学術文章:

    python3 tools/runtime/lifecycle/bootstrap_agent_run.py \
      --task "academic writing task" \
      --task-id T10 \
      --owner "codex" \
      --workspace-root "$PWD"

包括的開発:

    python3 tools/runtime/lifecycle/bootstrap_agent_run.py \
      --task "comprehensive development pass" \
      --task-id T12 \
      --owner "codex" \
      --workspace-root "$PWD"

反復改善:

    python3 tools/runtime/lifecycle/bootstrap_agent_run.py \
      --task "adaptive improvement loop" \
      --task-id T13 \
      --owner "codex" \
      --workspace-root "$PWD"

Adaptive Improvement Loop では、outer run の `experiment_change_loop.md` に `Extension Backlog` を持ち、各 extension で別の waterfall run-id を作ります。
次の extension へ進む前に、直前 extension で選択された `waterfall-gate-check`、review、`task-close`、および commit / push の判断・結果を完了させます。未選択の review artifact や full rerun は作りません。

`--task-id` を指定しても、`agents/task_catalog.yaml` の task-default specialist と `default_for_tasks` review pack は候補です。owner-critical decision または distinct unresolved claim/risk が有効化したものだけ materialize し、空の reviewer/template artifact は生成しません。
language-specific reviewer は `bootstrap_agent_run.py` が `--changed-path` か workspace の `git status --short` から自動で足します。
run bundle を起こしたら、`user_request_contract.md` を planning 前に埋めます。stage artifact、handoff、review では clause ID を明示します。
各 waterfall gate を次段へ進める前に `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <gate>"` で中間 gate を確認します。

包括的開発の固定 Codex stack:

- `requirements_organizer`
- `manager_reviewer`
- `literature_researcher`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `project_reviewer`
- `docs_workflow_steward`
- `prompt_config_reviewer`
- `python_reviewer`
- `cpp_reviewer`
- `worker`

cost を無視して review coverage を優先する run では、research-driven change と comprehensive development は `--full-team` を許可します。
