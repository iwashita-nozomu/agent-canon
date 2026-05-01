<!--
@dependency-start
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

## 目的

- 変更前に、実コード依存と dependency header 依存を別々に抽出する。
- 抽出結果から「どこを直すべきか」の仮説を明文化する。
- 修正候補 file / symbol / document が仮説に対して妥当かを検証する。
- 妥当性が通ってから初めて実装へ進む。
- 実装後の結果ではなく、実装前の reasoning を review 可能な artifact に残す。

## 適用条件

次のいずれかに当たる場合、この workflow を overlay として追加します。

- bug の原因箇所が曖昧で、複数 file / layer にまたがる可能性がある。
- algorithm、protocol、module boundary、workflow rule のどこを直すべきか判断が必要。
- code 依存と header dependency manifest のズレを見ながら修正箇所を決めたい。
- user が「考察」「仮説」「妥当性検証」「まず設計」を求めている。
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
仮説は「症状」ではなく「修正すべき境界」として書きます。

必須項目:

- `Observation:` 事実。ログ、test failure、code dependency edge、header dependency edge、既存 docs。
- `Hypothesis:` なぜその file / symbol / workflow が原因または修正点だと考えるか。
- `Expected Fix Surface:` 修正候補 path、symbol、doc section。
- `Expected Non-Surface:` 触らない path と理由。
- `Disconfirming Evidence:` この仮説が間違いだと分かる条件。
- `Validation Before Edit:` 実装前に行う確認 command / read target / static check。

禁止:

- 仮説なしに「たぶんここ」として実装へ進む。
- code dependency と header dependency を混ぜて 1 つの依存図として扱う。
- downstream docs / tests を見ずに implementation file だけを修正対象にする。
- 修正候補が複数あるのに、比較せず最初の候補だけを選ぶ。

## Gate H2. 修正箇所の妥当性検証

実装前に、仮説ごとに修正箇所が妥当か検証します。
ここでの目的は「正しい修正をした」ではなく、「ここを修正するのが妥当」という判断を確認することです。

最低限の検証:

- code dependency edge が修正候補に到達している。
- header dependency edge が読むべき design / docs / tests を示している。
- 修正候補の近傍に既存実装、命名、test precedent がある。
- alternative surface を比較し、今回触らない理由を説明できる。
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
- `Fix Surface Justification` がある。
- `Expected Non-Surface` がある。
- `Validation Before Edit` が実行済み、または実行できない理由が artifact にある。
- reviewer または parent が `fix_surface_validated=yes` と判断している。

## Gate H4. Review と Closeout

closeout 前に、実装後 diff が仮説と一致しているか確認します。

- 実装 diff が `Expected Fix Surface` から逸脱していない。
- 逸脱した場合は Gate H1-H2 に戻って仮説を更新している。
- downstream docs / tests / workflows の更新漏れがない。
- dependency header review と code dependency scan を再実行している。
- 失敗した仮説がある場合、破棄理由を `decision_log.md` または task artifact に残している。

この workflow では、実装量が少なくても「仮説なし」「修正箇所妥当性なし」の completion を認めません。
