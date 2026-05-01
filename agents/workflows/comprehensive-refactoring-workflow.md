<!--
@dependency-start
responsibility Documents 包括的リファクタリングワークフロー for this repository.
upstream design README.md workflow catalog
upstream design ../TASK_WORKFLOWS.md workflow family routing contract
upstream design implementation-waterfall-workflow.md staged implementation gate
upstream design ../skills/behavior-preserving-refactor.md behavior-preserving refactor contract
upstream design ../../documents/object-oriented-design.md OOP boundary policy
upstream design ../../documents/algorithm-implementation-boundary.md algorithm boundary policy
upstream implementation ../../tools/agent_tools/analyze_refactor_surface.py static refactor surface analyzer
upstream implementation ../../tools/agent_tools/analyze_oop_readability.py OOP readability analyzer
@dependency-end
-->

# 包括的リファクタリングワークフロー

この workflow は、大規模 repo で「全体を把握しきれないまま局所修正を重ねる」失敗を避けるための refactor 専用 overlay です。
primary family は `Large Delivery` または `Comprehensive Development` とし、実装順序は [implementation-waterfall-workflow.md](implementation-waterfall-workflow.md) に従います。

## 目的

- 実装前に設計境界を見直し、repo 全体の責務分解を固定する。
- OOP を class 増殖ではなく責務、状態、契約、拡張点の整理として使う。
- 行数を増やす refactor ではなく、より短く、読める、検証可能な実装境界へ寄せる。
- 必要なら静的解析ツールを作り、合格点を validation gate に入れる。
- behavior change と構造変更を混ぜず、semantic delta を review で検出できる状態にする。

## 適用条件

次のいずれかに当たる場合、この workflow を追加します。

- 複数 package / module / directory をまたぐ refactor。
- class / function / module boundary の再設計。
- 大きな file 分割、rename、move、delete、dependency direction 整理。
- 既存実装が長大化し、局所修正では責務境界を説明できない状態。
- 設計見直し、OOP boundary、静的解析 score を同じ umbrella plan で管理したい場合。

## Gate A. 設計見直し

実装前に `Refactor Design Review Packet` を作ります。
最低限、次を含めます。

- `Current Responsibility Map:` 現在の module、class、function、state owner、external boundary。
- `Target Responsibility Map:` refactor 後の module、class、function、state owner、external boundary。
- `Behavior Contract:` 変えてはいけない observable behavior。
- `Allowed Structural Delta:` 許可する file split、rename、move、dependency direction、adapter 導入。
- `Forbidden Semantic Delta:` 今回混ぜない仕様変更、数値変更、protocol change、performance tuning。
- `Path Mapping:` old path / symbol から new path / symbol への対応。
- `Deletion Plan:` 消す file、helper、alias、fallback、旧 route。
- `Compatibility Plan:` 互換 layer を残すか、残すなら期限と削除 gate。

設計見直しは、既存コードを読まずに始めません。
`rg`、dependency graph、test inventory、必要なら `tools/agent_tools/analyze_refactor_surface.py` の baseline を取ってから target boundary を決めます。

## Gate B. OOP 的な最小実装方針

OOP は、実装行数を増やすためではなく、責務を短く保つために使います。
[object-oriented-design.md](../../documents/object-oriented-design.md) を正本とし、次を design artifact に書きます。

- `Value Objects:` immutable data、validated input、result、config。
- `State Owners:` mutable state を保持する object と lifecycle。
- `Protocols:` 差し替えが必要な最小振る舞い契約。
- `Services / Functions:` state を持たない処理として残す function。
- `Adapters:` IO、CLI、serialization、external framework boundary。
- `Rejected Abstractions:` 作らない class / Protocol / layer と、その理由。

合格条件:

- 新しい class は `object-oriented-design.md` の class 作成条件を満たす。
- `Manager`、`Helper`、`Util` のような責務不明名を増やさない。
- static method の寄せ集め class を作らない。
- 既存関数で足りる処理を class 化しない。
- public API は短い責務語彙で説明できる。

## Gate B.5. 以後の拡張への適用

refactor 後の拡張は、Gate B で固定した OOP boundary を迂回しません。
新しい機能、adapter、backend、format、protocol を足すときは、同じ design artifact または後続 design で次を確認します。

- 既存 value object、state owner、service function、adapter、Protocol のどこへ拡張するか。
- 既存 boundary へ入らない場合、新しい boundary が必要な理由。
- 既存 class を肥大化させず、composition、値オブジェクト、純粋関数で足りるか。
- public API、docstring、test が OOP boundary と一致しているか。
- 互換 alias、legacy route、temporary adapter を残す場合、削除 gate があるか。

拡張時に OOP boundary と合わない実装を見つけた場合は、局所追加で逃げず Gate A-B に戻ります。

## Gate C. 解析ツールと合格点

大規模 refactor では、人間の印象だけで「整理できた」と判断しません。
必要に応じて静的解析 baseline を取り、target score を設計に入れます。

Python code surface の size / surface baseline では次を使えます。

```bash
python3 tools/agent_tools/analyze_refactor_surface.py python tests --min-score 85
```

この tool は AST と file length から、長すぎる function / class / file、公開 method 過多の class を検出し、score を出します。

Python / C++ の OOP readability baseline では次を使います。

```bash
python3 tools/agent_tools/analyze_oop_readability.py python include src tests --min-score 85
```

この tool は `object-oriented-design.md` に合わせ、責務不明 class / helper 名、巨大 class / function、public method / field 過多、instance state 過多、static method namespace、引数過多、`None` / `nullptr` runtime routing、純粋変換と副作用の混在、control-flow の読みづらさを検出します。
score は設計判断の補助であり、behavior correctness の代替ではありません。
tool が足りない場合は、refactor 対象に合わせて小さい解析 tool を同じ pass で追加し、合格点、限界、false positive の扱いを design artifact に書きます。

合格点を使う場合、設計に次を書きます。

- `Baseline Score:` refactor 前の score。
- `Target Score:` closeout 前の最低 score。
- `Allowed Warnings:` 今回の scope 外として残す warning。
- `Tool Limits:` AST 解析で見えない behavior、dynamic dispatch、framework magic。
- `Human Review Gate:` tool pass 後も reviewer が見る責務境界。

## Gate D. 実装分割

refactor は chunk に切りますが、chunk completion を user-facing completion と扱いません。
各 chunk は次を満たします。

- behavior contract に触れない。
- 1 chunk で 1 種類の structural delta だけを扱う。
- path mapping の一部を完了させる。
- old route、旧 helper、compat alias を残す場合は期限付きで記録する。
- tests と docs を同じ chunk で更新する。

chunk の例:

- `baseline capture`
- `extract value objects`
- `split state owner`
- `move pure functions`
- `replace adapter boundary`
- `delete stale route`
- `documentation sweep`

## Gate E. Review と Closeout

closeout 前に次を確認します。

- `refactor_safety_case.md` または design artifact に Behavior Contract、Allowed Structural Delta、Forbidden Semantic Delta、Path Mapping、Deletion Plan がある。
- `analyze_refactor_surface.py`、`analyze_oop_readability.py`、または task 固有解析 tool を使った場合、baseline、target、actual score がある。
- `project_reviewer` が stale path、delete 漏れ、cross-module drift を確認している。
- language reviewer が OOP boundary、function/class length、public API、test placement を確認している。
- dependency review が full repo で pass している。
- runtime / behavior tests が pass している。
- static score pass は behavior evidence と混同していない。

これらを満たさない場合、refactor は未完了です。
