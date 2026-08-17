# comprehensive-development
<!--
@dependency-start
contract skill
responsibility Documents comprehensive-development for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../task_catalog.yaml workflow family spawn budget and role topology owner
upstream design ../agents_config.json permanent team role ownership and write policy owner
upstream design ../canonical/CODEX_SUBAGENTS.md Codex subagent inventory and activation contract
upstream design ../internal-routines/design-implementation-correspondence.md cross-surface design-to-implementation correspondence route
upstream design ../../documents/conventions/software-engineering-principles.md contract-first decision precedence and responsibility-boundary policy
upstream design ../../documents/design/semantic-responsibility-contract.md semantic action and verification-owner allocation
upstream design ../../documents/design/entrypoint-owner-map.md root entrypoint responsibility migration boundary
downstream implementation ../../evidence/agent-evals/issue_eval_manifest.toml issue-derived regression mapping eval
downstream implementation ../../tests/agent_tools/test_issue_eval_manifest.py verifies regression mapping and projection boundaries
@dependency-end
-->

## Purpose

複数 surface を束ねるときは、各 bounded slice の design locator、clause
fingerprint、implementation target、review evidence を
`../internal-routines/design-implementation-correspondence.md` に接続します。
この skill は umbrella integration stage の owner であり、共通 policy の別実装
を作りません。

code、docs、tests、workflow、tools、runtime をまたぐ repo-wide な変更を、1 本の umbrella workflow と explicit subagent routing で進めます。
この skill は route packet と reader contract に限定し、spawn budget、role topology、role ownership、write policy は正本 surface へ委譲します。

## Software Engineering Principle Integration

cross-surface plan は、[ソフトウェア工学原則](../../documents/conventions/software-engineering-principles.md)
の判断順序を使います。最初に user / domain contract、semantic invariant、state / lifecycle owner、
public compatibility、root mechanism を固定し、その後で responsibility boundary、validation、
simplicity、style を判断します。小さい diff、短い code、既存 workflow の形を、上位 contract
より優先しません。

handoff には、全原則の checklist ではなく、実際に判断へ影響した clause と task-specific evidence
だけを含めます。少なくとも次が material な場合に記録します。

- 守る contract / invariant と canonical owner
- code、docs、tests、workflow、tool、runtime を分ける responsibility / effect boundary
- 新しい public surface または abstraction の concrete caller と responsibility gap
- evidence-bounded complete owning unit と、scope に含めない unrelated cleanup
- selected validation、failure classification、cleanup / rollback、remaining external verification

`not applicable`、negative token、原則別 receipt、新しい general-purpose checker は作りません。
OOP / SOLID specialization は class、state、inheritance、`Protocol`、public object model が material に
変わる場合だけ選びます。

## Contract-Complete Implementation Basis

この skill が束ねる implementation は、行数、file 数、diff の小ささを completion condition にしません。
候補の中から、要求された contract、invariant、reachable failure、cleanup、migration、validation を
閉じる最小の owning unit を選びます。必要な責務を落とした「最小実装」、既存 check を通すだけの
wrapper / fallback、temporary route、test relaxation は、単純化ではなく未完了として扱います。

material な mechanism decision は、既存の task packet / design trace に次の情報を接続します。
新しい universal schema や全原則 checklist は作りません。

| Evidence | Required content |
| --- | --- |
| contract | input / output、invariant、failure semantics、compatibility のうち変更に関係するもの |
| owner | state、effect、recovery、validation を閉じる canonical owner と complete owning unit |
| mechanism | 採用する algorithm、architecture、protocol、resource strategy、migration route |
| basis | 数理導出、proof obligation、complexity / error bound、conditioning、停止条件、公式仕様、domain model、workload model、measurement、benchmark、failure analysis、標準のうち判断を支える evidence |
| alternatives | 少なくとも現実に競合した候補、棄却理由、cost / risk / compatibility trade-off |
| oracle | contract を判定できる test、static property、proof、measurement、readback |

数式や外部文献は、判断がそれを必要とするときだけ使います。単純な rename や明示された定数置換へ
形式的 proof を追加する必要はありません。一方、algorithm の停止、numerical tolerance、近似誤差、
concurrency ordering、resource capacity、performance claim、reliability boundary を material に変える場合、
直感や既存値の踏襲だけを basis にしません。

必要な basis または oracle が得られない場合は、placeholder implementation で成功へ変換せず、
不足する design clause、必要な evidence、owner、再開条件を blocker として残します。review は
「check が green」という事実と、変更した contract が立証されたことを区別します。

## Regression Evidence Admission

新しい regression test、fixture、mock、test-only adapter を追加すること自体を進捗や
root-cause closure とみなしません。追加前に、現在の task packet / design trace の既存 evidence
へ次の判断を接続します。これらのための新しい universal schema や checker は作りません。

- failure が反証した canonical contract / invariant と、その最小 contract-complete owner
- failure をその invariant の反例として表す最小 witness
- 既存の property / table-driven / finite-state / boundary acceptance へ witness を統合できるか
- test が private field、temporary path、helper topology、storage layout 等の replaceable representation を contract 化しないか
- parser、classifier、state construction、lifecycle、environment setup を production owner と別に test 側で再実装しないか
- 同じ invariant を固定する historical regression を削除・統合できるか
- focused test が診断する property と、正式 entrypoint / consumer boundary から判定する completion oracle

次の表は新しい regression taxonomy や全 repository 向けの必須 schema ではありません。
過去の failure 群を bug 名ごとの test owner にせず、既存の canonical invariant と
boundary oracle へ統合できることを示す代表 witness mapping です。実際の変更では各 domain の
production owner と public / canonical entrypoint を使います。

| Historical failure family | Canonical invariant / owner class | Minimal boundary / counterexample set | Canonical oracle |
| --- | --- | --- | --- |
| cleanup / rollback / audit preservation | lifecycle / recovery / audit owner | terminal / nonterminal、interruption、repeated attempt、partial-effect rollback | production lifecycle entrypoint を通る finite-state transition table と audit readback |
| concurrency / reservation / idempotent retry | reservation protocol / state-transition / idempotency owner | zero / one / many contenders、duplicate request、capacity boundary、interleaving | production reservation owner を通る table / property oracle と atomic state readback |
| wait / backoff / timeout / cancel | temporal / liveness / cancellation owner | pre-timeout / at-timeout / post-timeout、cancel before / after effect、retry exhaustion | public wait / cancel entrypoint と virtual-clock boundary acceptance |
| payment / refund / discount / tax normalization / rounding | monetary normalization / ordering / precision owner | zero / negative、discount-tax-refund ordering、precision limit、rounding tie | production money value / normalization owner の property oracle と known vectors |
| empty / malformed / legacy input shape | parser / compatibility owner | omitted、empty、scalar、malformed、legacy shape | production parser の public boundary acceptance table |
| multi-binding / submodule / generated-file ownership / projection drift | single-owner source identity / projection owner | zero / one / many bindings、stale pin / source digest、generated drift | canonical materializer / projection entrypoint の source readback |
| PASS / FAIL / NOT_RUN、missing artifacts、stale evidence | completion-state / evidence identity owner | status-artifact cross-product、missing artifact、stale evidence、clean-replay contradiction | canonical status evaluator、artifact identity readback、clean replay acceptance |

この代表 mapping の issue-derived evidence owner は
[`issue_eval_manifest.toml`](../../evidence/agent-evals/issue_eval_manifest.toml) です。
既存 checker
[`test_issue_eval_manifest.py`](../../tests/agent_tools/test_issue_eval_manifest.py) は、
表の family / invariant / boundary が欠ける場合、eval artifact の接続が欠ける場合、
generated consumer に policy が複製される場合、focused pass が canonical acceptance へ
昇格される場合、または completion state が矛盾する場合に fail closed します。

同じ invariant に属する複数の historical failure は、個別 bug 名ごとの test を増やすより、
可能な限り一つの canonical oracle と最小 counterexample 集合へ収束させます。有限 relation / state
space は table-driven または exhaustive check、入力空間に一般則がある場合は property test、
consumer contract は public/canonical entrypoint を通る boundary acceptance を優先します。

局所 algorithm 自体が独立した数学的・工学的 contract owner である場合は、owner-local unit test を
保持して構いません。逆に、正しい alternative implementation へ置換しただけで失敗する test は、
contract ではなく representation を固定していないか再評価します。coverage percentage、test count、
mutation score、追加 test 数を単独の品質目的にしません。

validation evidence は役割を分離します。focused test は counterexample の再現、root-cause isolation、
repair の高速確認に使います。handoff / completion は変更責務が選んだ canonical boundary / acceptance
oracle まで満たした evidence で判断します。canonical acceptance が環境上実行不能なら、focused pass を
verified completion に昇格させず remaining verification として残します。

## Use When

- implementation、docs、tooling、Docker、CI を同時に整理する
- agent canon、workflow、entrypoint、validation tool をまとめて改造する
- 1 つの局所 diff ではなく、複数 surface の整合を取りながら delivery したい

## Core References

- `agents/task_catalog.yaml` (`workflow_families[].id: comprehensive_development`)
- `agents/agents_config.json`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `documents/conventions/software-engineering-principles.md`
- `documents/design/semantic-responsibility-contract.md`

## Standard Bundle

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Default Sequence

1. family を `Comprehensive Development` に固定します。
1. current requirement と owning contract を読み、material な engineering principle clause、canonical owner、forbidden interpretation を固定します。
1. material な mechanism decision について、contract、owner、mechanism、basis、alternatives、oracle を既存 task packet / design trace に接続します。
1. regression / fixture / mock を追加する場合は、canonical invariant、minimal counterexample、existing oracle への統合可能性、representation independence、duplicate truth、旧 regression の consolidation、completion oracle を先に確認します。
1. `agents/task_catalog.yaml` の `comprehensive_development` family から `spawn_budget`、`role_topology`、`roles`、`subagent_prompt` を読みます。
1. `agents/agents_config.json` で permanent team role ownership、required output、write policy を確認します。
1. `agents/canonical/CODEX_SUBAGENTS.md` で Codex inventory、activation、runtime surface を確認します。
1. run bundle を作り、`workflow=<family>`, `skills=<...>`, `review=<...>` と catalog / config 由来の route を宣言します。
1. `agents/COMMUNICATION_PROTOCOL.md` の fresh context capsule と bounded source packet を使って、stage ごとに subagent handoff を作ります。
1. write-capable work は approved design trace から導いた bounded slice に限定し、親が integration order と validation rerun を管理します。
1. closeout では `project_reviewer` を integration gate として使い、canonical contract、selected principle clause、implementation basis、catalog / config / inventory と実 diff の同期を確認します。

## Parent-Managed Write Scope

- parent は `team_manifest.yaml` に writer ごとの allowed path / directory、integration order、validation route を固定します。
- colliding writer scope は current checkout 内の後続 wave に serialize します。
- reviewer は read-only を保ち、parent-managed write-scope discipline の確認は `plan_reviewer` と `project_reviewer` が行います。

## Boundary

- 局所修正なら `Scoped Change` を使います。
- chunk ごとに独立 pass を閉じたい delivery なら `Large Delivery` を使います。
- Docker / CI が中心なら `Platform And Environment` を使います。
- 外部調査と experiment が主役なら `Research-Driven Change` を使います。
- 一般原則の意味、優先順位、誤用防止はこの skill に複製せず、canonical policy を参照します。
- root `AGENTS.md` / `ROOT_AGENTS.md` は owner route だけを持ち、本節の basis contract を複製しません。
