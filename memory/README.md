# Memory

<!--
@dependency-start
contract data
responsibility Provides on-demand, problem-solving memory records for repeated AgentCanon failures.
upstream implementation ../rust/agent-canon/src/memory.rs owns record schema, validation, search, and mutation planning
downstream implementation ../tools/agent_tools/memory_record.py forwards optional Python calls to the Rust CLI
@dependency-end
-->

## Reader Map

ここは、同じ問題に再遭遇したときに検索して使う知恵置き場です。起動時に固定
read する packet ではありません。次の判断が済んだ後に、選択済みの owner/path、
failure evidence、recurrence decision を検索入力として、必要な record だけ読みます。

- `records/*.md`: 1 topic 1 Markdown の問題解決 record。
- `rust/agent-canon/src/memory.rs`: schema、parser、validator、search、duplicate
  detection、create/update plan、Markdown/JSON serialization の正本。
- `agent-canon memory ...`: record の validate/search/plan/create/update/promote CLI。
- `tools/agent_tools/memory_record.py`: Rust CLI を呼ぶ必要がある既存 Python surface
  用の thin adapter。判定ロジックは持ちません。

## 何があるか

現行 records は、main の根拠から再発時の調査を短縮する次の独立 topic を収録します。

- 数値処理で最初に有限性を失う breakpoint の診断。
- テストで最小 protocol fixture と実 repository surface を使い分ける判断。
- runtime archive の publish 後に remote readback まで確認する手順。
- 欠落 path を作る前に owner と責務を解決する triage。
- repository symlink の外部解決先を container mount inventory に含める判断。

## Record Contract

filename は英語の lowercase ASCII で `<domain>--<problem-slug>.md` とし、日付を含めません。
同じ問題は同じ file を更新します。各 record は問題解決知識として自足し、次の section を
すべて持ちます。

`Problem/Symptom`、`Context/Trigger`、`Root Cause`、`Effective Resolution`、
`Failed Approaches`、`Applicability/Limits`、`Evidence/Source`、
`Promoted Owner Refs`、`Related Records`。

record は規約の正本ではありません。恒久契約や安定 preference は canonical owner へ
明示変更し、record の `Promoted Owner Refs` からその owner を参照します。raw chat、
時系列観測、runtime event、issue、failure log は各ログ/evidence/issues/failures の
owner に残し、memory へ append dump しません。

## CLI Route

新規 topic は、選択済み context を付けた `search` または read-only の `plan` で既存
record を確認してから `create` します。既存 topic は同じ `record_id` の `update` を使い、
owner 昇格は `promote` で明示します。tree の整合性は次で確認します。

```bash
agent-canon memory validate --root .
agent-canon memory search --root . --search-path agents/canonical/CODEX_WORKFLOW.md
```

固定 packet/read に memory record を追加しません。旧 append writer と旧単一 note path は
廃止済みです。#536 固有の open draft はこの base tree に推測で取り込みません。
