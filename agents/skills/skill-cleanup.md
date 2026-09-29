# skill-cleanup
<!--
@dependency-start
contract skill
responsibility Routes canonical skill and generated runtime cleanup as one source-to-readback unit.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ../../documents/design/skill-runtime-shim-materialization.md generated shim materialization owner
upstream design ../../documents/design/skill-tool-invocation-graph.md generated skill/tool graph owner
upstream design ./agent-orchestration.md routing owner
upstream design ./task-routing.md route selection owner
upstream design ./document-canon-cleanup.md document canon reuse owner
upstream design ./empirical-prompt-tuning.md conditional behavioral evaluation owner
upstream design ./worktree-health.md worktree evidence reuse owner
upstream design ./agent-log-analysis.md log analysis reuse owner
upstream design ./runtime-log-repair.md runtime log repair reuse owner
upstream design ./result-artifact-writeout.md result evidence reuse owner
downstream implementation ../../.codex/personal/skills/skill-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
downstream implementation ../../tools/agent/skills/skill_shim_materializer.py generated shim materializer
downstream implementation ../../tools/agent/skills/skill_dependency_map.py generated graph materializer
downstream implementation ../../tools/validation/semantic/skills/check_skill_tool_invocation_graph.py graph readback checker
@dependency-end
-->

## Purpose

canonical skill doc、catalog、dependency DAG、route、tool command、generated shim、host config、
graph/readback を一つの source-to-generated cleanup unit として既存 owner へ渡します。
共通 unit schema と統合/rollback は [`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-05、RC-06、RC-07、RC-08 を参照します。

## Use When

- public skill を追加、整理、分割、統合、rename、route変更する
- canonical doc と catalog/DAG/route/tool command/generated shim/host config/graph の整合を直す
- generated artifact と readback の stale、欠落、projection mismatch を修復する

## Route

1. canonical skill doc と catalog/dependency/route/tool command の source owner を固定する。
   挙動を改訂する場合は、最初の変更前に [Behavioral Tuning](#behavioral-tuning) を適用する。
   関連スキルへの導線を追加・変更する場合は、[Caller-side wiring](#caller-side-wiring) に従う。
2. `.codex/config.toml` を host-wiring の source/input として読み、catalog skill id に対する
   entry set、source order、path、enabled を readback する。
3. 既存 materializer は保守時に `.codex/personal/skills/<skill>/SKILL.md` を生成し、正本と同じ commit に含める。利用時には呼ばない。
4. `skill_dependency_map.py graph` は通常、明示した外部 runtime root に graph JSON/Mermaid を生成し、既存 checker で source/readback equality を確認する。tracked reader pair を更新する場合だけ、固定2ファイルの mutation capability と外部 before/after evidence を明示する。
5. validation command の実行範囲は [Write-Capable Handoff Validation Trust Boundary](agent-orchestration.md#write-capable-handoff-validation-trust-boundary) を参照し、skill-cleanup 側で別の test/full-scan policy を作らない。作業途中の関連読込は、[Conditional maintenance reads](#conditional-maintenance-reads) の成立した条件だけを使う。

## Caller-side wiring

関連スキルが必要になる操作箇所に、成立条件、判断・操作の前に読む具体的な
Markdownリンク、復帰先を書きます。例えば「ログから挙動を判断する必要が出たら
[agent-log-analysis](agent-log-analysis.md) を読み、得られた根拠で元の判断へ戻る」とします。
読込時点と既存contextの再利用は [task-routing](task-routing.md#in-flight-skill-reads) に従います。
呼び出し先の `Use When`、末尾の関連一覧、catalogやdependency headerだけでは配線完了にしません。
呼び出し先の手順を複製せず、初回の全読込リストや必須前提にも変換しません。

変更したスキルと実際のcallerについて、条件成立時の到達先・復帰先と、未成立時に
読まない経路を確認します。既存候補・owner・読了規約を再利用し、生成viewを手書きしたり、
無関係な全スキルの再監査を完了条件に加えたりしません。

## Conditional maintenance reads

初回に下表の全スキルを読むのではなく、保守中に条件が成立した時点で該当先を読みます。
既読で有効な内容は再利用し、判断が閉じたら中断した保守操作へ戻ります。

| 保守中に成立した条件 | 次の判断・操作の前に読む関連スキル |
| --- | --- |
| 文書の正本や重複を整理する | [document-canon-cleanup](document-canon-cleanup.md) |
| checkoutの不整合や後片付けを扱う | [worktree-health](worktree-health.md) |
| 記録済みログから挙動を解析する | [agent-log-analysis](agent-log-analysis.md) |
| ログの生成・保存・公開の欠落を修復する権限がある | [runtime-log-repair](runtime-log-repair.md) |
| 実在する結果artifactを保存・更新する | [result-artifact-writeout](result-artifact-writeout.md) |

条件の成立は、環境修復・破壊的操作・追加検証の権限を新たに与えません。

## Behavioral Tuning

再利用する指示の新規作成・大幅な挙動改訂、指示の曖昧さに起因する失敗の修正、
または明示的な挙動評価依頼では、既存の
[empirical-prompt-tuning](empirical-prompt-tuning.md) を選択する。
formatter-only、path-only、生成ビューだけの stale 修正や one-off prompt には、
その作業だけを理由に経験的評価を必須化しない。

最初の挙動変更前に同 Skill の Iteration 0 と Scenario Packet の凍結を行い、
選択された [agent-orchestration](agent-orchestration.md) の既存評価 route へ渡す。
評価の起動条件、fresh/read-only evaluator、Fixed Report、採点、再実行、収束条件は
empirical owner に従い、ここで別の規則やモデル設定を作らない。
受け入れた原因テーマを一つずつ修正し、同じ凍結 packet で再評価する。
各改訂は上記 source-to-generated route で検証するが、構造整合の成功を
挙動評価の成功・収束に読み替えない。

必須 evaluator が利用不能なら、親の自己採点や別モデルで代用せず、未実行の理由と
凍結 packet を既存 Issue に残す。安全に進められる source 修正と PR 公開は続け、
[pr-processing](pr-processing.md) で検証待ちとして引き継ぐ。
この評価のためだけに環境再構築、全 Skill の改訂、無関係な完了条件を追加しない。

## Tool Commands

```bash
python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py
python3 tools/agent/skills/skill_shim_materializer.py materialize --root . --all
python3 tools/agent/skills/skill_shim_materializer.py readback --root . --all
python3 tools/agent/skills/skill_dependency_map.py graph --root . --runtime-root <external-runtime-root>
# tracked reader pair の更新（capability は documents/runtime の md/json だけを列挙）
python3 tools/agent/skills/skill_dependency_map.py graph --root . \
  --output documents/runtime/skill-dependency-graph.md \
  --runtime-root <external-runtime-root> \
  --source-mutation-capability-json <exact-two-path-capability.json>
python3 tools/validation/semantic/skills/check_skill_tool_invocation_graph.py --root .
```

## Boundary

generated shim と graph は source owner から生成し、手書き projection を authority にしません。
`.codex/config.toml` は materializer の生成 target ではなく、host-wiring の source/input と
set/order readback owner です。
個別の document/worktree/log policy は既存 skill を読み、この skill では新しい代替 skill を作りません。
