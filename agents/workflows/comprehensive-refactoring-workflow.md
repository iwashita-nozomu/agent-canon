<!--
@dependency-start
contract workflow
responsibility Documents 包括的リファクタリングワークフロー for this repository.
upstream design README.md workflow catalog
upstream design ../TASK_WORKFLOWS.md workflow family routing contract
upstream design implementation-waterfall-workflow.md staged implementation gate
upstream design ../skills/refactor-loop.md refactor loop contract
upstream design ../../documents/object-oriented-design.md OOP boundary policy
upstream design ../../documents/algorithm-implementation-boundary.md algorithm boundary policy
downstream implementation ../../tools/agent_tools/analyze_refactor_surface.py static refactor surface analyzer
downstream implementation ../../tools/oop/python/readability.py Python OOP readability analyzer
downstream implementation ../../tools/oop/cpp/readability.py C++ OOP readability analyzer
@dependency-end
-->

# 包括的リファクタリングワークフロー

この workflow は、大規模 repo で「全体を把握しきれないまま局所修正を重ねる」失敗を避けるための refactor 専用 overlay です。
primary family は `Large Delivery` または `Comprehensive Development` とし、実装順序は [implementation-waterfall-workflow.md](implementation-waterfall-workflow.md) に従います。

## この文書の読み方

- この文書は、大規模 refactor の責務境界、OOP 方針、静的解析、実装分割、review / closeout overlay を所有します。
- `Gate A-B` は設計と OOP 境界、`Gate C` は解析 tool と合格点、`Gate D-E` は分割実装と closeout を扱います。
- refactor planner は `## Gate A. 設計見直し` から responsibility map と behavior contract を固定し、実装者は `Gate D` まで進む前に semantic delta の禁止条件を確認します。
- chunked reading では、現在の refactor gate を単位にし、path mapping、allowed structural delta、forbidden semantic delta を同じ chunk で読むようにします。

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
- `Deletion Plan:` 消す file、helper、alias、alternate route、旧 route。
- `Removal and Caller Migration Plan:` compatibility-preservation drift と duplicate implementation を残さず、旧 entry、旧 alias、alternate route の caller migration と削除順序を固定する。

設計見直しは、既存コードを読まずに始めません。
構造化された owner 探索、`git grep`、dependency graph、test inventory、必要なら `tools/agent_tools/analyze_refactor_surface.py` の baseline を取ってから target boundary を決めます。

## Gate B. OOP 的な責務境界方針

OOP は、実装行数を増やすためではなく、責務を短く保つために使います。
[object-oriented-design.md](../../documents/object-oriented-design.md) を正本とし、次を design artifact に書きます。

- `Value Objects:` immutable data、validated input、result、config。
- `State Owners:` mutable state を保持する object と lifecycle。
- `Protocols:` 差し替えが必要な振る舞い契約。
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
- compatibility-preservation drift と duplicate implementation を避けるため、旧 alias、legacy route、temporary adapter が見つかった場合は canonical owner、caller migration、削除順序を固定する。

拡張時に OOP boundary と合わない実装を見つけた場合は、局所追加で逃げず Gate A-B に戻ります。

## Gate C. 解析ツールと合格点

大規模 refactor では、人間の印象だけで「整理できた」と判断しません。
必要に応じて静的解析 baseline を取り、signal class outcome、accepted-warning
ledger、human review gate を設計に入れます。strict score floor は明示的な
根拠がある場合だけ使い、size-only split で score を上げることを成功条件に
してはいけません。

Python code surface の size / surface baseline では次を使えます。

```bash
python3 tools/agent_tools/analyze_refactor_surface.py python tests --min-score 85
```

この tool は AST と file length から、長すぎる function / class / file、公開 method 過多の class を検出し、score を出します。

Python の OOP readability baseline では次を使います。

```bash
python3 tools/oop/python/readability.py \
  --exclude vendor \
  --exclude reports \
  python tools tests \
  --min-score 95
```

Python tool は `object-oriented-design.md` に合わせ、責務不明 class / helper 名、巨大 class / function、public method 過多、instance state 過多、static method namespace、引数過多、`None` runtime routing、純粋変換と副作用の混在、control-flow の読みづらさを検出します。`OOP_READABILITY` は score threshold ではなく signal class で判定します。size / surface / parameter / complexity finding は boundary review signal であり、caller contract や ownership から安定した境界が読めない限り分割指示にしません。
C / C++ surface がある場合は別 entrypoint を使います。

```bash
python3 tools/oop/cpp/readability.py \
  --exclude vendor \
  --exclude reports \
  include src tests/cpp \
  --min-score 95
```

C++ tool は責務不明 type 名、巨大 class / function、public field / method 過多、base class / parameter 過多、`nullptr` runtime routing、純粋変換と副作用の混在、redundant wrapper を検出します。`OOP_READABILITY` は score threshold ではなく signal class で判定します。size / surface / parameter / complexity finding は boundary review signal であり、caller contract や ownership から安定した境界が読めない限り分割指示にしません。
score は設計判断の補助であり、behavior correctness の代替ではありません。
tool が足りない場合は、refactor 対象に合わせて targeted 解析 tool を同じ pass で追加し、signal class outcome、限界、false positive の扱いを design artifact に書きます。

外部 repo、bare repo、または派生 template snapshot を調べる場合は、元 repo を編集せず `git archive` などで読み取り専用 snapshot を作り、run bundle に `OOP Analysis Scope:` として次を残します。

- `Repository:` repo 名、remote / bare path、commit SHA。
- `Extraction:` snapshot 作成 command と一時 root。
- `Paths:` 実際に analyzer へ渡した path。
- `Excludes:` `vendor`、`reports`、生成物、別 canon snapshot など対象 repo の product surface ではない path。
- `Reports:` Markdown report、JSON report、`oop_readability_reviewer` prompt。
- `Interpretation:` 最上位 dimensions、finding kinds、hotspot files。score / counts / path / line は機械 report から変更しません。

調査目的で score floor を評価条件にしたくない場合は、survey report だけ `--min-score 0` で完走させます。
closeout gate に使う report は、signal class outcome、accepted-warning ledger、
human review gate を残します。strict score floor は task が根拠を明示した場合
だけ closeout 条件に含めます。

解析 report を使う場合、設計に次を書きます。

- `Baseline Score:` refactor 前の score。
- `Signal Class Outcome:` error / gate / review signal の扱い。
- `Allowed Warnings:` 今回の scope 外として残す warning。
- `Accepted Warning Ledger:` 意図的に残す warning とその根拠。
- `Tool Limits:` AST 解析で見えない behavior、dynamic dispatch、framework magic。
- `Human Review Gate:` tool pass 後も reviewer が見る責務境界。

## Gate D. 実装分割

refactor は two-stage refactor に一本化します。stage 1 は `forced migration`、
stage 2 は `usage-surface repair` です。chunk 名で作業を増やさず、この二段に
入る対象だけを扱います。

stage 1 `forced migration` は次をまとめて行います。

- canonical surface の移動、rename、delete。
- old route、旧 helper、compat alias、alternate route の削除。
- generated surface、config route、public entrypoint の正本更新。
- `Path Mapping:` と `Removal and Caller Migration Plan:` の更新。

stage 2 `usage-surface repair` は次をまとめて行います。

- caller、import、CLI、hook、workflow、skill、document、report consumer を新しい surface に合わせる。
- compatibility-preservation drift または duplicate implementation finding を Gate A に戻す。
- return-gate validation の対象 command、static check、behavior evidence を一括して確定する。

test、smoke、behavior execution は二段完了後の return-gate validation に集約します。

## Gate E. Review と Closeout

closeout 前に次を確認します。

- `refactor_safety_case.md` または design artifact に Behavior Contract、Allowed Structural Delta、Forbidden Semantic Delta、Path Mapping、Deletion Plan がある。
- `analyze_refactor_surface.py`、`tools/oop/*/readability.py`、または task 固有解析 tool を使った場合、baseline、signal class outcome、accepted-warning ledger、human review gate がある。
- `project_reviewer` が stale path、delete 漏れ、cross-module drift を確認している。
- language reviewer が OOP boundary、function/class length、public API、test placement を確認している。
- dependency review が full repo で pass している。
- runtime / behavior tests が pass している。
- static score pass は behavior evidence と混同していない。

これらを満たさない場合、refactor は未完了です。

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
