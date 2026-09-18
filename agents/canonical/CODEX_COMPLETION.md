# Codex Completion

<!--
@dependency-start
contract agent-runtime
responsibility Owns completion evidence, validation, and delegation to the terminal closeout owner.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for validation, completion evidence, or publication closeout.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## Completion Bar

user-facing completion は、全 active clause、selected work unit、selected owning
review gate (when activated)、validation、closeout gate が揃った状態です。
closeout 前に reviewer と auditor は次を明示的に確認します。

- 各 must-do clause と completion-evidence clause が、実装、文書、test、command、artifact、または明示された deferred / rejected clause に対応している
- request に含まれる仕様と実際の product surface の間に未実装の gap が残っていない
- SEP-09 の complete target state は実装開始前に固定され、implementation sequencing / waves はその work の順序だけを担っている。未完了の target を段階実装として completion に昇格しない
- LCPが選択された場合は、[`agent-orchestration.md#Local Capability Priority`](../skills/agent-orchestration.md#local-capability-priority) の既存canonical record locatorを完了証拠として引用する
- validation は `necessary_presence`、`forbidden_presence`、`sufficient_behavior` を区別する。必要なpath・linkの存在や禁止された旧経路の不在をbehavior成立の十分条件へ昇格させず、behaviorの十分条件が要求されない作業に実行テスト・完全一致比較・網羅レビューを追加しない
- schedule、review、validation、shared canon sync、follow-up 判断、および今回の scope で選択された commit / push operation の判断・結果を含む task が 1 つも未完了で残っていない
- task が数式、擬似コード、仕様、method contract を持つ場合、runtime success ではなく
  静的解析・読み取りによる implementation alignment evidence が review artifact に
  主証跡として残っている
- accepted review findings が実装へ反映され、behavior、owner/design boundary、correctness、validation、または publication state を変えた same-owner repair だけが selected gate の rerun を要求している
- review reject、requested-change、または `required_change` への応答が、user
  request や design intent を捨てる rollback になっていない。実装 slice の
  revert / discard がある場合は、撤回、置換、owner 外、unsafe replacement、
  または escalation の authority と、保持された request clause が artifact に残っている
- deferred findings は今回の completion readiness への影響、理由、escalation を artifact に記録している

[`task_close.py`](../../tools/runtime/lifecycle/task_close.py) consumes the
CompletionCoverage consumer, typed owner boundary, canonical formatter/dispatcher,
validation-response, and review-integration evidence as inputs to its sole
terminal readiness predicate.

## Mechanical Completion Loop

実装後から user-facing completion までの間は、parent の自己判断だけで閉じず、次の機械的 loop を `closeout_gate.md` に evidence として残します。

1. `user_request_contract.md` の active clause、`schedule.md` の planned work unit、直近 review findings、validation blockers、commit / push の判断・結果、shared canon sync、follow-up 判断を一覧化します。
1. 最新 diff と tracked / untracked state を確認し、変更対象 file の dependency manifest、downstream edge、旧参照、copy / snapshot / backup path を見ます。
1. 静的解析、読み取り確認、docs / targeted tests / agent checks を先に実行します。
   repo-wide dependency review や broad execution は、最終候補の touched contract
   が要求して次の判断または最終 validation を変える場合だけ一度選択します。
   completion predicate は選択した canonical route で確定します。
1. 選択された owning review gate が diff-check を要求する場合だけ、read-only diff-check reviewer を起動し、選択された handoff、latest diff、validation evidence、dependency evidence を渡します。
1. 選択された review の output は hypothesis として decision-owning reviewer または ship reviewer が adjudicate します。current snapshot、reachable path、contract、witness/static proof があり、behavior、owner boundary、correctness、validation、または publication state を変える accepted finding だけ same-owner repair loop を開きます。rejected hypothesis は `reason_code` と `evidence_ref` を残し、wave / rollback を起こしません。
   この修正 loop では、review finding への応答を、同じ意図を保つ修正、
   再設計、または authority 付き escalation / replacement として扱います。
   Follow [agents/skills/agent-orchestration.md#Review Activation And Adjudication](../skills/agent-orchestration.md#review-activation-and-adjudication)
   after final validation topology selection; this workflow surface does not
   duplicate that semantic rule.
1. [`task_close.py`](../../tools/runtime/lifecycle/task_close.py) が、選択された
   stage evidence と closeout inputs を消費して terminal readiness を判定します。
   選択されていない diff-check と no-change route は stage evidence に
   `not_applicable` と rationale を残します。

## CompletionCoverage Applicability And State Contract

This document owns applicability and state transitions for the checked
CompletionCoverage read model. Existing ledger owners append facts; the W2
projection/check boundary derives the read model; `task_close` and
`report_artifact_checks` consume it. No reader may write back to the schema
owner or become a second state machine.

The minimal state is `context_binding`, `coverage_map`, `gate_evidence`,
`failure_response`, `completion_boundary`, and `projection_metadata`. State
transitions are `context_bound` → `design_pending` → `design_approved` →
`writer_release_pending` → `writer_released` → `source_freeze_pending` →
`source_frozen` → `change_review_pending` → `change_review_approved` →
`integration_pending` → `publication_ready` → `delivered`. A validation
failure enters `repair_pending`; same-intent repair returns to the owning gate,
and unresolved or intent-changing work enters `escalation_pending`.

`evaluate_completion_boundary` accepts one
`control_topology_ledger.json` snapshot for all routing/publication facts. Its
other inputs are schedule, open-work, repair, and crossing-edge state only;
parent-route and global-publication state remain outside a second direct
argument. It derives the independent predicates
`all_planned_chunks_complete` and `overall_delivery_complete`. Each chunk, slice,
checkpoint, or subpass remains an internal progress observation.

W2-20 is ordered as W2 design `APPROVE`, exactly one isolated-branch writer
release with collision preservation and
`branch_creation_reason=convergence_w2_gate_completion_authority`, source
freeze/review, then W3/integration-executor integration. `routing_gate=verified` is observed at
later integration/publication, while writer release authority remains the W2
design `APPROVE` plus isolated branch release.

W1 remains the producer of `ExecutionResourcePlan`. W2 consumes one broad
W2-12 plan/actual/readback/failure certificate mapping and one W2-19 ordered
GPU consumer mapping: candidate UUID set `A`, process-held `O_t` PID/start
identities, active reservations `R_t`, selected UUIDs, atomic lock/lease plus
post-lock readback, effective environment, terminal GPU identities, release
versus retained-for-descendant disposition, and typed insufficient-eligible or
mismatch failure. W2 does not parse NVML, select, reserve, construct the
environment, produce resources, or duplicate tests/gates.

## 6. Validation

- Validation uses one canonical formatter/check path for Markdown, math, and
  Mermaid plus selected non-Python static evidence. Duplicate CI, format,
  check, and synthetic retest paths are not additional completion predicates.
- After any validation failure, record `failing_contract`,
  `observation_level`, `cause_classification`, `intent_preservation`, and
  `evidence`. The canonical token-safe slug lists are owned by
  `documents/runtime/runtime-profiles-and-check-matrix.json` and projected into
  [documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md); this workflow only points
  to that taxonomy. Completion advances after response resolution through the
  owning repair route or recorded escalation.
- Shared canon、Large delivery、高 risk 変更では差分限定ではなく全 repo 対象で `bash tools/analysis/dependencies/run_repo_dependency_review.sh --fail-missing` を通し、dependency graph、header 欠落、header format を確認する。Routine docs / Focused code は changed-file dependency checks と relevant downstream review を evidence にできる
- Source freeze 後は canonical formatter/check path と選択した非 Python static
  evidence を一度記録する。別 CI、別 formatter、別 checker、checker-retest
  は W2 completion gate にならない。
- 編集前の補助診断は [Optional Rejection Prediction](../COMMUNICATION_PROTOCOL.md#optional-rejection-prediction) に従い、変更した契約の検証と区別する。
- tool / checker / hook / reviewer / subagent feedback から実装へ進む場合は `$tool-finding-report` で finding packet を作り、raw artifact、structured artifact、impact、prompt feedback decision を handoff に渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` は次の write-capable subagent 起動前に prompt を修正し、`workflow_monitor.py --runtime-feedback ... action=prompt_repair` で記録する
- agent runtime / skill 変更では active profile に応じて `make agent-checks` または relevant subchecks を使う
- 文書変更では canonical formatter/check path が Markdown、math、Mermaid の
  format/check を一つの証跡として記録する。
- report を閉じる前には [documents/experiments/experiment-report-style.md](../../documents/experiments/experiment-report-style.md) を確認する
- 研究系 task では [critical-review](../internal-routines/critical-review.md) と [report-review](../internal-routines/report-review.md) の decision state を確認し、必要なら [research-perspective-review](../internal-routines/research-perspective-review.md) を追加する

## 7. Closeout

### Completion Readiness

`task_close.py` is the sole terminal readiness predicate. This workflow records
stage-specific evidence and sends it to that owner; it does not define a second
closeout checklist or readiness state. 作業 update は progress readback であり、final
report ではありません。required operation、validation、integration、publication、または
cleanup が残る間は request を active のまま保ち、既存の dependency order に従う次の
具体的な操作へ進みます。受領・謝罪・約束、child の claim/handoff、事後的な healthy
status、または incomplete result は、actual operation や success の証拠になりません。
各 clause は request → actual operation → result の対応を保ち、失敗・未完了の result は
既存の `failure_response` / `repair_pending` または owning stage に戻して、権限を持つ
owner が利用可能な次の安全な recovery/readback を実行します。十分な operation を
繰り返しません。権限または外部状態のために次の安全な操作を実行できない場合だけ、
closeout を non-terminal のまま、genuine blocker の根拠と次の owner/action を報告します。
これは無限 retry や新しい readiness predicate を要求する規則ではありません。

- repo に残す差分がある task では、validation 後の作業単位が coherent でレビュー済みか、未完了・混在変更として保持すべきかを判断し、commit の実行または保留理由と次条件を既存の work log / final status に反映する
- commit は [documents/operations/BRANCH_SCOPE.md](../../documents/operations/BRANCH_SCOPE.md) の Git 上の runnable unit として作る。validation が参照した source、config、schema、fixture、文書、tool entrypoint を tracked tree に含める。code 変更では file-level code dependency と関数 / public entrypoint 単位の call-site evidence も残す。commit SHA、source checkout SHA、validation command、対象 path、残った dirty / untracked path の分類を evidence に残す
- commit / PR の切り方は [documents/operations/BRANCH_SCOPE.md](../../documents/operations/BRANCH_SCOPE.md) の範囲分割契約に従う。commit は実行単位、PR はレビュー単位として扱い、複数の問題、canonical owner、behavior or contract delta、validation route にまたがる差分は範囲表を作ってから merge 前に別 PR または別 commit へ分ける
- commit とは独立に、sharing、handoff、remote backup、PR などの目的、既存権限、指定宛先から branch push の要否を判断する。push を選択した場合だけ実行し、user が明示的に停止した場合や外部 blocker の場合は既存の final status に理由を残す
- `task_close.py` に渡す stage-specific evidence として、verification、request
  contract、completion coverage、selected validation/static/dependency results、
  review disposition、commit / push の判断・結果、shared canon sync、follow-up 判断を記録する
- 既存 closeout status の `commit_created` と `push_completed` は、選択した operation では `yes`、選択しなかった operation では `not_applicable` とする。`no` または欠落は未完了として扱い、選択理由は既存の work log / final status に残す
- creator-owned temporary files, directories, and containers must have a cleanup
  receipt naming the exact created paths or resource IDs and an absence readback
  before `task_close.py`; missing creator-owned cleanup evidence keeps closeout
  non-terminal
- `closeout_gate.md` の `review_findings_integrated=yes` は、review reject /
  requested-change への応答として、user request と design intent が保持された
  evidence を要求します。revert / discard が含まれる場合は、撤回、置換、owner
  外、unsafe replacement、または escalation の authority を示します
- selected review gate の post-fix evidence と findings disposition を stage
  evidence として残す。diff-check はその gate が選択した場合だけ artifact、
  latest diff ref、read-only independent result を記録し、未選択または no-change
  route は `not_applicable` と rationale を記録する
- `task_close.py` の terminal result が、canonical tree-head、subagent、runtime
  log、evaluation、completion coverage の各 stage evidence を読み、closeout を
  判定する
- `workflow_monitoring.md` の signals / behavior events / interventions / improvement decisions を埋め、skill / config / workflow / memory の改善判断を `applied`、`recorded`、`not_applicable` のいずれかにする
- hook、code checker、static analysis、CI、review tool の結果が parent protocol または subagent protocol を変えるべきかは protocol reviewer が確認し、`workflow_monitoring.md` に `hook_tool_feedback=reviewed`、`parent_protocol_update=<applied|recorded|not_required>`、`subagent_protocol_update=<applied|recorded|not_required>`、`protocol_feedback_reason=...` を残す
- evidence を確認済みの closeout では、`python3 tools/runtime/lifecycle/workflow_monitor.py --report-dir reports/agents/<run-id> --closeout-token-preset` で `evaluate_agent_run.py` が消費する standard behavior tokens を記録できます。この preset は記録 shortcut であり、canonical formatter/check、dependency review、diff-check approval、review finding resolution は個別 evidence として残します。
- evaluation reviewer が `eval/producers/evaluate_agent_run.py --report-dir reports/agents/<run-id> --behavior-manifest eval/definitions/agent_behavior_eval.toml --write` を pass し、`closeout_gate.md` の `agent_evaluation_complete=yes` と `agent_evaluation.md` の `feedback_actions_resolved: yes` が揃ったら、agent behavior evaluation と feedback resolution を complete にする
- `schedule.md` を TODO 正本として埋め、`work_log.md` に execution trail を残す
- [documents/notes/guardrails/engineering_avoidances.md](../../documents/notes/guardrails/engineering_avoidances.md) の log-derived avoid に当たる変更は、修正または reviewer escalation の対象にする
- user request が generic path の usable smoke を求める場合、generic path の producer / consumer evidence を completion evidence にする
- JAX export / native runtime の generic path は、`jax.export` artifact producer と consumer/runtime evidence を completion evidence にする
- 実験・性能改善では、planned comparison run、acceptance criteria、raw result、interpretation evidence を分けて示す
- trainer replacement、scalability、superiority、広い theorem は baseline comparison と scope-limited evidence で主張する
- failure-onset dimension を記録し、implementation bug と frontier limit を分けて扱う
- 実験・性能改善では、correctness evidence と performance evidence を別項目で示す
- final report には branch と、判断した commit / push の結果を短く残す
- push を選択して失敗した場合は commit を保持し、安全な in-scope recovery または具体的 blocker とその理由を final status に明記する。push を選択しなかった場合も、既存の作業記録に判断理由を残す
- push の目的・権限・宛先から実行が適切と判断できる場合は、追加の許可取りに戻らず実行する。これは push を常に要求する規則ではない
- closeout 前に今回の観測を既存 record の update、独立 record の create、canonical owner への
  明示変更、issue/failure/evidence のいずれかに分類する。memory は `agent-learning` owner
  から on-demand に検索し、stable preference は対象 [AGENTS.md](../../AGENTS.md) へ直接変更する。
- closeout 前に `agent_evaluation.md` の feedback actions を見直し、stable な失敗防止は `agent-learning` で記録し、確定した guardrail 候補は positive operational condition として昇格可否を判断する
- review-only task や no-change task では、review result と no-change rationale を completion evidence にする

そのうえで、何を変えたか、何を確認したか、何を確認していないかを短く残して完了する
