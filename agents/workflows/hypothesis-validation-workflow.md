<!--
@dependency-start
contract workflow
responsibility Documents analysis-first hypothesis validation workflow before edits.
upstream design README.md workflow catalog
upstream design ../TASK_WORKFLOWS.md workflow family routing contract
upstream design implementation-waterfall-workflow.md staged implementation gate
upstream design ../../documents/dependency-manifest-design.md manifest dependency model
downstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts code dependency edges
downstream implementation ../../tools/agent_tools/check_dependency_graph.sh validates header dependency graph
@dependency-end
-->

# 仮説検証ワークフロー

この workflow は、考察が弱いまま局所修正へ進む失敗を防ぐための analysis-first overlay です。
primary family は `Scoped Change`、`Large Delivery`、`Research-Driven Change`、`Comprehensive Development` のいずれかを使い、実装順序は [implementation-waterfall-workflow.md](implementation-waterfall-workflow.md) に従います。

## この文書の読み方

- この文書は、原因仮説、依存抽出、修正候補比較、編集前妥当性検証の overlay workflow を所有します。
- `Gate H0` は code dependency と header dependency の分離、`Gate H1-H3` は仮説と着手条件、`Gate H4-H5` は実装後判定と closeout を扱います。
- 実装前の原因特定では `## Gate H0. 依存抽出` と `## Gate H1. 仮説` を先に読み、修正候補が固定されてから `Gate H2-H3` へ進みます。
- chunked reading では、現在の gate 番号を作業単位にし、support / disconfirming evidence と validation route を見失わないようにします。

## 目的

- 変更前に、実コード依存と dependency header 依存を別々に抽出する。
- 抽出結果から「どこを直すべきか」と「なぜそれで改善するか」の仮説を明文化する。
- 複数の修正候補 file / symbol / document を比較し、採用候補と不採用候補を分ける。
- 修正候補が仮説に対して妥当か、編集前に検証する。
- 仮説が間違いだと分かる反証条件と、改善が支持されたと見なす検証条件を先に固定する。
- 妥当性が通ってから初めて実装へ進む。
- 実装前の reasoning と実装後の supported / rejected / inconclusive decision を review 可能な artifact に残す。

## 適用条件

次のいずれかに当たる場合、この workflow を overlay として追加します。

- bug の原因箇所が曖昧で、複数 file / layer にまたがる可能性がある。
- algorithm、protocol、module boundary、workflow rule のどこを直すべきか判断が必要。
- code 依存と header dependency manifest のズレを見ながら修正箇所を決めたい。
- user が「考察」「仮説」「妥当性検証」「まず設計」を求めている。
- user が「コード改善」「リファクタリング」「性能改善」「可読性改善」を求め、どの surface を直すべきか判断が必要。
- 大規模 repo で、差分だけを見て修正すると stale path や別 truth surface を残しそうな場合。

## Gate H0. 依存抽出

最初に code dependency と header dependency を分けて取得します。
この 2 つは目的が違うため、同じ tool や同じ判断材料として扱いません。

### Code Dependency Surface

code dependency は import、include、source など、実行時または build 時の参照関係を抜き出します。
標準入口は次です。

```bash
bash tools/agent_tools/scan_code_dependencies.sh --changed
```

必要に応じて対象 path を明示します。

```bash
bash tools/agent_tools/scan_code_dependencies.sh python/jax_util/solvers/kkt.py python/jax_util/solvers/pcg.py
```

記録すること:

- `Code Dependency Evidence:` 実行 command、対象 path、主要 edge。
- `Code Fan-In/Fan-Out:` 変更候補が呼ぶもの、変更候補を呼ぶもの。
- `Unresolved Imports:` tool が解決できない import / include と、人間が補った判断。

### Header Dependency Surface

header dependency は `@dependency-start` manifest に書かれた設計・実装・環境・test の明示的な文脈関係です。
標準入口は次です。

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges
```

repo-wide baseline を見たい場合は次を使います。

```bash
bash tools/agent_tools/run_repo_dependency_review.sh
```

記録すること:

- `Header Dependency Evidence:` 実行 command、対象 path、主要 edge。
- `Design Context:` upstream design / environment / test のどれを読む必要があるか。
- `Downstream Risk:` 変更候補から見て影響を受ける docs / tests / tools / workflows。

## Gate H1. 仮説

依存抽出のあと、実装前に仮説を 1 つ以上書きます。
仮説は「症状」ではなく「修正すべき境界」と「期待する改善メカニズム」として書きます。

必須項目:

- `Observation:` 事実。ログ、test failure、code dependency edge、header dependency edge、既存 docs。
- `Hypothesis:` なぜその file / symbol / workflow が原因または修正点だと考えるか。
- `Expected Mechanism:` その変更がどう改善へつながるか。可読性、正しさ、性能、保守性などの改善軸を明示する。
- `Expected Fix Surface:` 修正候補 path、symbol、doc section。
- `API Surface Traversal:` dependency/API capability 仮説では
  `documents/api-surface-traversal-policy.md` に従い、public import/export、
  signature、nested config、example を確認してから negative conclusion を出す。
- `Expected Non-Surface:` 触らない path と理由。
- `Disconfirming Evidence:` この仮説が間違いだと分かる条件。
- `Support Evidence:` 変更後に仮説が支持されたと見なす command、metric、test、static analysis、review finding。
- `Validation Before Edit:` 実装前に行う確認 command / read target / static check。

複数候補がある場合の必須項目:

- `Candidate Surfaces:` 候補ごとの path / symbol / expected mechanism。
- `Candidate Comparison:` impact、risk、reuse、testability、blast radius、rollback cost の比較。
- `Selected Surface:` 採用候補と理由。
- `Rejected Surfaces:` 今回採用しない候補と理由。後で使う可能性がある場合も、この iteration から外す理由を書く。

禁止:

- 仮説なしに「たぶんここ」として実装へ進む。
- code dependency と header dependency を混ぜて 1 つの依存図として扱う。
- downstream docs / tests を見ずに implementation file だけを修正対象にする。
- 修正候補が複数あるのに、比較せず最初の候補だけを選ぶ。
- support evidence だけを後付けで選び、disconfirming evidence を先に固定しない。

## Gate H2. 修正箇所の妥当性検証

実装前に、仮説ごとに修正箇所が妥当か検証します。
ここでの目的は「正しい修正をした」ではなく、「ここを修正するのが妥当」という判断を確認することです。

最低限の検証:

- code dependency edge が修正候補に到達している。
- header dependency edge が読むべき design / docs / tests を示している。
- 修正候補の近傍に既存実装、命名、test precedent がある。
- alternative surface を比較し、今回触らない理由を説明できる。
- expected mechanism と validation command が対応している。可読性改善なら readability / refactor surface / review、性能改善なら benchmark、公理的 correctness なら unit / property / parity test を使う。
- disconfirming evidence が実行可能で、失敗した場合の戻り先が決まっている。
- 変更後に必要な downstream docs / tests / workflow update が列挙されている。

妥当性が弱い場合:

- Gate H0 へ戻り、依存抽出対象を広げる。
- Gate H1 へ戻り、仮説を分割または破棄する。
- primary workflow の要件整理または詳細設計へ戻す。

## Gate H3. 実装着手条件

次が揃うまで実装してはいけません。

- `Code Dependency Evidence` がある。
- `Header Dependency Evidence` がある。
- `Hypothesis` と `Disconfirming Evidence` がある。
- `Expected Mechanism` と `Support Evidence` がある。
- `Candidate Comparison` と `Selected Surface` がある。単一候補の場合は、候補が 1 つで足りる理由がある。
- `Fix Surface Justification` がある。
- `Expected Non-Surface` がある。
- `Validation Before Edit` が実行済み、または実行できない理由が artifact にある。
- reviewer または parent が `fix_surface_validated=yes` と判断している。

## Gate H4. 実装後の仮説判定

実装後は「変更した」ではなく、仮説が支持されたかを判定します。

Validation test/check が失敗した場合は、通すために仮説、intended behavior/test、oracle、
または required validation を縮めません。先に `failing_contract`、
`observation_level`、`cause_classification`、`intent_preservation`、`evidence` を
記録します。`cause_classification` と `intent_preservation` の slug set と route
semantics は `documents/runtime-profiles-and-check-matrix.md`、
`agents/canonical/CODEX_WORKFLOW.md`、`agents/canonical/CODEX_SUBAGENTS.md`、
`documents/REVIEW_PROCESS.md` を参照します。`cause_classification=implementation_bug`
で contract と oracle が安定している場合は、追加 test planning で止めず owning
code / config / docs / workflow repair へ進みます。

必須項目:

- `Post-Change Evidence:` 実行した test / static analysis / benchmark / review と結果。
- `Hypothesis Decision:` `supported`、`rejected`、`inconclusive` のいずれか。
- `Evidence-To-Hypothesis Trace:` 各 evidence が `Expected Mechanism` と `Support Evidence` にどう対応するか。
- `Disconfirming Evidence Result:` 反証条件を満たしたか。満たした場合は closeout せず H1-H2 へ戻る。
- `Next Hypothesis:` `rejected` または `inconclusive` の場合に次に試す仮説、または scope 外として止める理由。

判定ルール:

- `supported`: 事前に固定した support evidence が通り、disconfirming evidence が出ていない。
- `rejected`: disconfirming evidence が出た、または expected mechanism と逆方向の結果が出た。
- `inconclusive`: evidence が不足、測定が不安定、または correctness / performance / readability の改善軸が混同された。

`rejected` または `inconclusive` の場合は、実装を広げず、H1 に戻って仮説を分割または破棄します。

## Gate H5. Review と Closeout

closeout 前に、実装後 diff が仮説と一致しているか確認します。

- 実装 diff が `Expected Fix Surface` から逸脱していない。
- 逸脱した場合は Gate H1-H2 に戻って仮説を更新している。
- downstream docs / tests / workflows の更新漏れがない。
- dependency header review と code dependency scan を再実行している。
- `Hypothesis Decision` が `supported` でない場合、user-facing completion ではなく次仮説、rollback、または explicit stop decision に進んでいる。
- 失敗した仮説がある場合、破棄理由を `decision_log.md` または task artifact に残している。
- 次回の agent が同じ誤った候補を選ばないよう、必要なら workflow monitoring、agent learning、eval、guardrail のいずれかへ feedback を残している。

この workflow では、実装量が少なくても「仮説なし」「修正箇所妥当性なし」の completion を認めません。

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
