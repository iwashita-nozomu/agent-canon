# Agent Learning Workflow

<!--
@dependency-start
contract workflow
responsibility Routes agent-side recurrence learning to records, owners, issues, failures, or evidence.
upstream design ../skills/agent-learning.md skill contract
upstream design ../../memory/README.md on-demand one-topic record contract
upstream implementation ../../rust/agent-canon/src/memory.rs Rust memory CLI owner
downstream implementation ../../tools/agent_tools/memory_record.py thin adapter
downstream implementation ../../tools/agent_tools/workflow_monitor.py runtime observation route
@dependency-end
-->

## Reader Map

この workflow は、task 中または closeout で得た観測を「次回同じ問題に遭遇したときに
検索して使う知識」へ変換する route です。固定 packet に memory を注入せず、選択済み
context から必要な record だけを on-demand で read します。

## 1. Classify Before Writing

観測は最初に次のいずれかへ分類します。

- raw chat、時系列、hook/event、run bundle evidence: runtime log/evidence owner
- actionable defect と修正 action: `issues/open/`
- 再発した failure pattern: `notes/failures/`
- owner を参照する独立した problem-solving knowledge: `memory/records/*.md`
- repo-wide rule、workflow、stable preference: canonical owner への明示変更

一度きりの指示、既に owner に昇格した規約、#536 open draft 固有の未確認内容は memory
record にしません。user preference は第二の memory canon にせず、安定したものは対象の
`AGENTS.md` または canonical owner へ直接変更します。

## 2. Search Before Create

search input は keyword routing ではなく、決定済みの owner/path、failure evidence、
recurrence decision から組み立てます。

```bash
python3 tools/agent_tools/memory_record.py search --root . \
  --search-owner-ref agents/skills/agent-learning.md \
  --failure-evidence "repeated routing miss"
python3 tools/agent_tools/memory_record.py plan --root . \
  --record-id <domain>--<problem-slug> \
  --search-path <selected/owner/path> \
  --recurrence-decision "independent recurrence knowledge"
```

`plan` は read-only で、既存 hit なら update、hit がなければ create を返します。複数 hit
は duplicate/ambiguous として停止します。create は selected context がない場合、既存 hit
がある場合、または required section/owner ref が欠ける場合に失敗します。

## 3. Record or Promote

各 record は lowercase ASCII の `<domain>--<problem-slug>.md` であり、日付を付けません。
同じ問題は同じ file を `update` します。本文は次の section をすべて持ちます。

`Problem/Symptom`、`Context/Trigger`、`Root Cause`、`Effective Resolution`、
`Failed Approaches`、`Applicability/Limits`、`Evidence/Source`、
`Promoted Owner Refs`、`Related Records`。

```bash
python3 tools/agent_tools/memory_record.py update --root . \
  --record-id <record-id> --section "Effective Resolution" \
  --text "<evidence-backed resolution>"
python3 tools/agent_tools/memory_record.py promote --root . \
  --record-id <record-id> --owner-ref <canonical/owner.md#section> \
  --reason "permanent contract is owned here"
```

Rust `memory` moduleがschema、parser、validator、search、duplicate detection、plan、
Markdown/JSON serialization と mutation を所有します。Python adapter はその CLI を起動
するだけで、旧 append route や旧 path compatibility は提供しません。

## 4. Runtime Feedback and Evaluation

利用中の skill invocation、routing、review feedback、hook/tool gate は、必要なら
`workflow_monitor.py` の behavior/runtime feedback として raw evidence owner に記録します。
prompt、workflow、eval の修理が必要な feedback はその owner を更新し、memory-only で閉じません。
result artifact は raw/summary/manifest を分離します。

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --behavior-event "skill_invocation=agent-learning status=observed"
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --runtime-feedback "source=user target=agent-learning action=memory_record evidence=<short-observation>"
```

## 5. Closeout

```bash
python3 tools/agent_tools/memory_record.py validate --root .
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write
```

closeout packet には、分類（record update/create、owner change、issue/failure/evidence）、
search context、record_id/owner refs、validation result を記録します。raw chronology を
memory に append したことや、削除済み旧writerで publish したことを成功条件にしません。
