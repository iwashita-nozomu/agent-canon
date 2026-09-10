# agent-eval-accumulation

<!--
@dependency-start
contract skill
responsibility Documents accumulated AgentCanon eval evidence repair and validation.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../eval/definitions/README.md accumulated eval family contract
upstream design ../../documents/runtime/runtime-log-archive.md external log archive boundary
upstream implementation ../../eval/producers/run_accumulated_agent_evals.py runs registered eval producers
upstream implementation ../../eval/checkers/eval_accumulation_check.py validates accumulated eval families
downstream implementation ../../.codex/personal/skills/agent-eval-accumulation/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: accumulates AgentCanon eval evidence through registered producers
  and log-archive storage instead of hand-written summaries.
- Use When: eval collection or repair is selected to establish required evidence,
  not merely because read-only analysis observes missing, stale, or failing data.
- Section path: Purpose and Use When define scope; Required Flow is the
  checklist for selected collection/repair; Boundaries limits what this skill may generate or claim.
- Boundary: do not hand-write eval reports when a registered producer and
  archive path own the evidence.

## Purpose

AgentCanon の prompt / role / workflow / report-quality eval を
append-only evidence として外部 log archive に積み、`eval_accumulation_check.py`
で family gap を閉じるための skill です。

この skill は eval report を手で書きません。registered producer
（登録済み producer）を走らせ、transient stdout / stderr、accumulated report、
compact checker output を同じ run bundle の判断に結びます。再生成可能な
stdout / stderr は要約後に source tree から消し、durable evidence は compact
checker output と archive 側 accumulated report に残します。

## Use When

- `eval_accumulation_check.py` が返した `no-*-eval-reports`、duplicate run id、
  missing run id、legacy source-tree result などの修理が依頼範囲として選択された
- `$agent-log-analysis` の eval family gap について、観測・Issue 記録とは別に
  eval collection / repair を選択した
- skill、workflow、subagent role、router、report-writing、deterministic search routing を直した後、
  selected validation が accumulated eval evidence を PR / closeout gate に必要とする

過去 report の欠落・鮮度・失敗を読むだけの調査は `$agent-log-analysis` に留めます。
既存の checker output だけで報告できる場合は再実行しません。必要な検査を一度
選んでも、その fail だけで producer 再実行や履歴移行まで依頼範囲を広げません。

## Required Flow

以下は選択済みの eval collection / repair の手順です。読取分析や Issue 記録の
前提条件ではありません。修理が未選択なら、この loop は起動しません。

1. Run-local evidence directory を先に決めます。通常は
   `reports/agents/<run-id>/` を使い、producer の transient stdout / stderr は
   `reports/agent-eval-runs/<run-id>/` に出ます。
1. 先に compact checker を走らせ、欠けている family と blocking finding を固定します。

```bash
python3 eval/checkers/eval_accumulation_check.py \
  --root . \
  --compact-out reports/agents/<run-id>/eval-accumulation-before.json \
  --format text
```

1. `no-*-eval-reports` または stale family gap がある場合は、個別 report を手で作らず、
   登録済み producer をまとめて走らせます。実行に使った skill は `--skill-used` で
   渡します。

```bash
python3 eval/producers/run_accumulated_agent_evals.py \
  --root . \
  --run-id <run-id> \
  --report-dir reports/agents/<run-id> \
  --skill-used agent-orchestration \
  --skill-used agent-log-analysis
```

1. producer stdout / stderr は要約だけを読みます。必要な詳細は accumulated report
   path と compact checker output へ誘導し、`.agent-canon/log-archive/**` の raw
   Markdown / JSONL を広域検索しません。producer stdout / stderr は再生成可能な
   transient artifact なので、要点を run bundle の report に移したら削除します。
1. 同じ checker を再実行し、`EVAL_ACCUMULATION=pass` と
   `EVAL_ACCUMULATION_BLOCKING_FINDINGS=0` を closeout evidence にします。

```bash
python3 eval/checkers/eval_accumulation_check.py \
  --root . \
  --compact-out reports/agents/<run-id>/eval-accumulation-after.json \
  --format text
```

1. producer が fail した場合は、producer 名、stdout / stderr path、対象 skill /
   workflow / role、修復先を `workflow_monitor.py --runtime-feedback` で記録します。
   prompt / skill / workflow の gap は次の write-capable subagent や closeout の前に
   修復します。
1. eval producer または `eval_accumulation_check.py` が fail した場合は、eval
   family を green 扱いにする前に `failing_contract`、`observation_level`、
   `cause_classification`、`intent_preservation`、`evidence` を run bundle に
   記録します。pass 目的の producer 省略、intended eval / oracle 削除、oracle
   weakening、validation downscope、source-tree result の手書き代替は行いません。
   producer bug、eval oracle / spec mismatch、fixture / environment / stale
   generated artifact、unrelated failure、approved-design / user-request conflict を
   owner repair、residual、または escalation に分けます。
1. eval report が archive に積まれたら、`runtime_log_archive_git.py sync` または
   `push` で append-only log branch に保存します。source tree に runtime eval result
   を戻してはいけません。
1. closeout 前に `python3 tools/runtime/artifacts/generated_artifact_guard.py --root .` を走らせ、
   `GENERATED_ARTIFACT_GUARD=pass` を確認します。

## Boundaries

- Log aggregation と raw JSONL 回避は `$agent-log-analysis` の責務です。この skill は
  選択済みの eval producer / checker の repair loop だけを担当します。
- Raw / summary artifact placement は `$result-artifact-writeout` の責務です。再生成可能な
  producer stdout / stderr は durable artifact ではありません。
- Reader-facing な改善報告は `$report-writing` の責務です。
- Individual prompt repair は対象 skill / workflow が担当します。この skill は
  failing family を隠さず、producer と checker の evidence route を固定します。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read [agents/skills/agent-eval-accumulation.md](agent-eval-accumulation.md).
   Apply the following loop only to selected eval collection/repair. A gap found
   during read-only analysis or a selected checker invocation is not by itself
   authority to run producers, migrate historical logs, or block Issue recording.
1. Start with `python3 eval/checkers/eval_accumulation_check.py --root . --compact-out reports/agents/<run-id>/eval-accumulation-before.json --format text`; use the compact JSON and stdout counters as the first evidence.
1. If the checker reports missing eval family reports or stale accumulation gaps, run `python3 eval/producers/run_accumulated_agent_evals.py --root . --run-id <run-id> --report-dir reports/agents/<run-id>` and pass every used skill with repeated `--skill-used <skill>`.
1. Do not hand-generate eval reports under `.agent-canon/log-archive/**` or `agents/evals/results/**`; registered producers own accumulated reports.
1. Read producer stdout / stderr summaries from `reports/agent-eval-runs/<run-id>/`; avoid broad raw archive searches. Treat those stdout / stderr files as transient, summarize the needed lines into the run bundle, then remove them before closeout.
1. Rerun `eval_accumulation_check.py` with `--compact-out reports/agents/<run-id>/eval-accumulation-after.json` and require `EVAL_ACCUMULATION=pass` plus `EVAL_ACCUMULATION_BLOCKING_FINDINGS=0` before using the accumulated evidence as green closeout evidence.
1. If a producer fails, record `workflow_monitor.py --runtime-feedback "source=eval target=<skill-or-workflow-or-tool> action=prompt_repair reason=<producer-failure>"` and repair the target surface before closing the task.
1. If a producer or `eval_accumulation_check.py` fails, record
   `failing_contract`, `observation_level`, `cause_classification`,
   `intent_preservation`, and `evidence` before treating the family as green.
   Use `intent_preservation` for the same-intent repair or escalation route.
   Do not skip producers to pass, delete intended eval/oracle coverage, weaken
   an oracle, downscope validation, or hand-write source-tree substitutes.
   Route producer bugs, oracle/spec mismatches, fixture/environment/stale
   generated artifacts, unrelated failures, and approved-design/user-request
   conflicts to owner repair, residual, or escalation.
1. After producer runs create archive artifacts, use `python3 tools/runtime/archive/runtime_log_archive_git.py sync` or `push` so append-only eval evidence is saved on the log archive branch.
1. Run `python3 tools/runtime/artifacts/generated_artifact_guard.py --root .` and require `GENERATED_ARTIFACT_GUARD=pass`; do not leave regeneratable `reports/agent-eval-runs/<run-id>/*.stdout.txt` or `*.stderr.txt` files in the source tree.
