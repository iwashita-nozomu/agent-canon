# agent-learning

<!--
@dependency-start
contract skill
responsibility Owns AgentCanon agent-side recurrence learning and its promotion decisions.
upstream design ../workflows/agent-learning-workflow.md learning workflow and lifecycle
upstream design ../../memory/README.md on-demand memory record contract
upstream implementation ../../rust/agent-canon/src/memory.rs Rust memory CLI owner
downstream implementation ../../tools/agent_tools/memory_record.py thin Python adapter
downstream implementation ../../tools/agent_tools/workflow_monitor.py runtime feedback evidence
@dependency-end
-->

## Reader Map

- Purpose: 同じ agent-side failure、routing miss、skill invocation gap、または
  task retrospective に再遭遇したときに使う問題解決知識を record 化する。
- Use when: recurrence decision があり、owner/path/failure evidence を選べるとき。
- Boundary: raw chat、時系列 runtime observation、issue、failure log はそれぞれの
  owner に置く。恒久契約は canonical owner へ直接昇格する。

## Purpose

この skill は、会話や task の観測を append dump するためのものではありません。まず
`agent-canon memory search` で既存 topic を検索し、同じ問題なら同じ record を update
します。独立した再発防止知識だけを `memory/records/<domain>--<problem-slug>.md` に残し、
record の `Promoted Owner Refs` に契約正本を記録します。

## Use When

- user が `agent-learning` または `$agent-learning` を明示した。
- agent behavior、routing、skill invocation、review feedback、task retrospective に
  次回の実行を変える再発防止判断がある。
- 既存 owner に昇格済みでない、独立した problem-solving knowledge がある。

stable user preference はこの skill の第二正本にしません。安定した preference は対象の
`AGENTS.md` または他の canonical owner への明示変更として扱い、個別の作業観測は runtime
logs/evidence/issues/failures に置きます。旧 preference-sync route はありません。

## Required Record Contract

Rust CLI が次を検査・生成・更新します。

- filename: lowercase ASCII の `<domain>--<problem-slug>.md`、日付なし、1 topic 1 file
- metadata: `record_id` と `record_schema`
- sections: `Problem/Symptom`、`Context/Trigger`、`Root Cause`、`Effective Resolution`、
  `Failed Approaches`、`Applicability/Limits`、`Evidence/Source`、
  `Promoted Owner Refs`、`Related Records`
- owner refs: 実在する canonical path を持つこと
- duplicate: selected context の search-before-create と record topic fingerprint の両方を
  pass すること

## Operating Route

1. 現在の owner/path、failure evidence、recurrence decision を選ぶ。
2. 同じ context で `search` または read-only `plan` を実行する。
3. hit があれば同じ `record_id` の `update`、hit がなく独立 topic なら `create` を使う。
4. stable rule を owner に昇格したら `promote` で ref を追加し、実際の owner 変更を別途
   明示する。
5. `validate` と targeted readback を実行する。

例:

```bash
python3 tools/agent_tools/memory_record.py search --root . \
  --search-path agents/canonical/CODEX_WORKFLOW.md \
  --failure-evidence "missing path owner resolution"
python3 tools/agent_tools/memory_record.py plan --root . \
  --record-id structure--missing-path-owner-resolution \
  --search-path agents/canonical/CODEX_WORKFLOW.md \
  --recurrence-decision "reuse owner"
python3 tools/agent_tools/memory_record.py validate --root .
```

`tools/agent_tools/memory_record.py` は Rust CLI への薄い transport です。schema、parser、
search、duplicate 判定、serialization を Python に複製しません。CI は既存 AgentCanon
static gate が一度 build した binary の `agent-canon memory validate --root .` を再利用します。

## Evidence Boundary

- raw runtime event、chat transcript、日時付き観測: runtime archive / evidence owner
- actionable workflow defect: `issues/open/`
- failure analysis: `notes/failures/`
- 繰り返す問題解決知識: `memory/records/*.md`
- repo-wide permanent rule: canonical documents / `AGENTS.md`

## Closeout Decision

closeout では、今回の観測が既存 record の update、独立 record の create、owner への明示変更、
issue/failure/evidence のいずれかを決めます。単なる chronology や既に owner にある内容を
memory に複製しません。#536 固有の open draft は、main へ追従して意味を確認する follow-up
までこの base tree に取り込みません。
