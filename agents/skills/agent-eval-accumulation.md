# agent-eval-accumulation

<!--
@dependency-start
contract skill
responsibility Documents accumulated AgentCanon eval evidence repair and validation.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../evidence/agent-evals/README.md accumulated eval family contract
upstream design ../../documents/runtime-log-archive.md external log archive boundary
upstream implementation ../../tools/agent_tools/run_accumulated_agent_evals.py runs registered eval producers
upstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates accumulated eval families
downstream implementation ../../.agents/skills/agent-eval-accumulation/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: accumulates AgentCanon eval evidence through registered producers
  and log-archive storage instead of hand-written summaries.
- Use When: eval evidence is missing, stale, failing, or needs family-level
  accumulation before claims are accepted.
- Section path: Purpose and Use When define scope; Required Flow is the
  mandatory checklist; Boundaries limits what this skill may generate or claim.
- Boundary: do not hand-write eval reports when a registered producer and
  archive path own the evidence.

## Purpose

AgentCanon の prompt / role / local-LLM / workflow / report-quality eval を
append-only evidence として外部 log archive に積み、`eval_accumulation_check.py`
で family gap を閉じるための skill です。

この skill は eval report を手で書きません。registered producer
（登録済み producer）を走らせ、transient stdout / stderr、accumulated report、
compact checker output を同じ run bundle の判断に結びます。再生成可能な
stdout / stderr は要約後に source tree から消し、durable evidence は compact
checker output と archive 側 accumulated report に残します。

## Use When

- `eval_accumulation_check.py` が `no-*-eval-reports`、duplicate run id、
  missing run id、legacy source-tree result などを返した
- `$agent-log-analysis` が structured dashboard / API の後に eval family gap を見つけた
- skill、workflow、subagent role、router、report-writing、local LLM routing を直した後、
  accumulated eval evidence を PR / closeout gate に戻す必要がある
- 過去 run の反復課題を skill / workflow / role prompt に還元する前に、どの eval
  family が evidence を持っているか確認したい

## Required Flow

1. Run-local evidence directory を先に決めます。通常は
   `reports/agents/<run-id>/` を使い、producer の transient stdout / stderr は
   `reports/agent-eval-runs/<run-id>/` に出ます。
1. 先に compact checker を走らせ、欠けている family と blocking finding を固定します。

```bash
python3 tools/agent_tools/eval_accumulation_check.py \
  --root . \
  --compact-out reports/agents/<run-id>/eval-accumulation-before.json \
  --format text
```

1. `no-*-eval-reports` または stale family gap がある場合は、個別 report を手で作らず、
   登録済み producer をまとめて走らせます。実行に使った skill は `--skill-used` で
   渡します。

```bash
python3 tools/agent_tools/run_accumulated_agent_evals.py \
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
python3 tools/agent_tools/eval_accumulation_check.py \
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
1. closeout 前に `python3 tools/agent_tools/generated_artifact_guard.py --root .` を走らせ、
   `GENERATED_ARTIFACT_GUARD=pass` を確認します。

## Boundaries

- Log aggregation と raw JSONL 回避は `$agent-log-analysis` の責務です。この skill は
  eval producer / checker の repair loop だけを担当します。
- Raw / summary artifact placement は `$result-artifact-writeout` の責務です。再生成可能な
  producer stdout / stderr は durable artifact ではありません。
- Reader-facing な改善報告は `$report-writing` の責務です。
- Individual prompt repair は対象 skill / workflow が担当します。この skill は
  failing family を隠さず、producer と checker の evidence route を固定します。
