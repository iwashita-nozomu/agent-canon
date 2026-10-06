# code-cleanup
<!--
@dependency-start
contract skill
responsibility Routes public/module code cleanup by responsibility and reachability through dependency analysis, refactor loop, and change review.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ../../documents/conventions/software-engineering-principles.md existing provider reuse and abstraction admission owner
upstream design ./dependency-analysis.md dependency and reachability owner
upstream design ./refactor-loop.md behavior-preserving refactor owner
upstream design ../internal-routines/incremental-code-change.md opt-in coverage traversal and incremental update sequence
upstream design ./change-review.md findings-first review owner
upstream design ./responsibility-cleanup.md responsibility-unit dispatch owner
downstream implementation ../../.codex/personal/skills/code-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
@dependency-end
-->

## Purpose

public/module responsibility と到達性を一つの cleanup unit として閉じ、既存の
`dependency-analysis -> refactor-loop -> change-review` route に渡します。unit schema、
analyzer の candidate 扱い、validation/rollback は [`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-02、RC-04、RC-07、RC-08 を参照します。通常の置換・統合と重複旧実装の廃止は
[RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
に従い、旧コードの削除と必要な利用側移行を同じ修正で閉じます。

## Use When

- public API、module responsibility、consumer reachability、dependency closure を整理する
- analyzer finding を候補として調査し、実装 owner と refactor boundary を確定する
- 実装の置換・統合・廃止を、不要な旧コードの削除と findings-first review まで閉じる

## Route

全対象の走査と逐次修正、またはタスク内の重複読取・引継ぎ・再レビューの修正を
依頼された場合は、[依存順走査による逐次コード変更](../internal-routines/incremental-code-change.md)
をこのrouteの走査・更新順として使います。通常の局所修正に全走査を追加しません。
同じ `reuse_survey` と依存根拠を使い、検証・レビュー・commitの正本を置き換えません。

1. 合意した完成形から、対象ownerと実際の利用側を特定する。既存の意味・能力・判断を再利用し、
   失われた既存機能が疑われる場合は、その判断に必要なGit履歴や過去の設計を確認する。
2. 既知のowner、利用案、意味、検証結果を再利用し、今回の判断を変える未確認点だけを調べる。
   必要な根拠は既存Issue、設計、またはhandoffに残す。
3. 候補の意味、invariant、state transition、side effect、I/Oと実際のcallerを確認する。
   [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
   に従い、通常の置換でも不要になる旧実装・入口・専用補助コードを同じ pass で削除する。
   別の廃止依頼、active caller ゼロ、後続 cleanup を待たない。独自責務、未確認の意味、
   必要な利用側移行は同じ RC-09 を使い、ここへ規則を複製しない。
4. 数値コードを削除・置換する前に equations、units、state、stopping rule、convergence contract、
   failure semantics を復元する。未解決の数学的意味は既存の semantic math owner に戻し、architecture、
   compiler、JIT の変更で吸収しない。
5. `dependency-analysis` で public/module responsibility、到達性、consumer、impact を閉じる。
   根幹の修正で契約・接続が変わる利用側も修正対象に含める。RC-09 の残存参照は
   移行漏れとして追い、影響情報を記録しただけで修正を終えない。
   responsibility slices と `allowed_paths` はこの asset universe と disposition から導き、
   同じ asset に触れる slices を一つへ merge する。既存 provider の利用案が合意した完成形を
   最も単純に満たすなら、直接利用・設定・合成へ置換し、第三の helper へ再実装しない。
   candidate がない場合も、ローカル検索ゼロだけで新 surface を admission しない。
   SEP-08 の capability 比較で残った具体的な不足責務だけを新設理由にする。実在する
   candidate の `reject` は能力不足と、旧構造の維持で増える複雑さを区別し、SEP-06/08 の
   根拠を使う。必要な部品まで再実装せず、実在しない candidate や synthetic な `reject` は作らない。
6. 選択した変更を実装し、必要な移行と旧実装・専用supportの撤去を同じ単位で閉じる。
   委譲する場合だけ、受け手の判断に必要な既存根拠と検証範囲を渡す。
7. 変更した意味、利用側の接続、旧コードの撤去を既存reviewと対象検証で確認する。

再利用先の比較は今回の責務に限り、contract を満たす選択が決まれば終える。全 library の
網羅調査、provider 内部の再監査、調査用の依存導入を追加しない。置換時の検証は既存の
consumer boundary と変更した意味・接続に向け、provider の実装や test suite を複製しない。

## Tool Commands

```bash
python3 tools/validation/semantic/dependencies/check_dependency_headers.py --changed
bash tools/analysis/dependencies/scan_code_dependencies.sh --changed
bash tools/analysis/dependencies/run_repo_dependency_review.sh
```

## Boundary

このcleanup routeを新規実装の一律前提にしません。新規部分はSEP-06の既存機能の組合せから始め、
修正部分だけを本routeで扱います。挙動保存のrefactorは必要な挙動を保ち、構造の保存とは区別します。
削除、rename、移動の oracle は analyzer ではなく public/module contract、到達性、validation、
rollback の owner evidence です。`dependency-analysis`、`refactor-loop`、`change-review` の
policy をこの skill に複製しません。search tool、asset registry、reuse database、
public code-splitting Skill は追加せず、既存 `reuse_survey` と write handoff の単一路線を使います。
