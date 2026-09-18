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
の RC-02、RC-04、RC-07、RC-08 を参照します。重複旧実装の廃止は
[RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
に従い、未使用コード削除や全面 consumer 移行と区別します。

## Use When

- public API、module responsibility、consumer reachability、dependency closure を整理する
- analyzer finding を候補として調査し、実装 owner と refactor boundary を確定する
- behavior-preserving refactor または明示された重複旧実装の廃止の後に findings-first review を行う

## Route

全対象の走査と逐次修正、またはタスク内の重複読取・引継ぎ・再レビューの修正を
依頼された場合は、[依存順走査による逐次コード変更](../internal-routines/incremental-code-change.md)
をこのrouteの走査・更新順として使います。通常の局所修正に全走査を追加しません。
同じ `reuse_survey` と依存根拠を使い、検証・レビュー・commitの正本を置き換えません。

1. file/worker slice より先に、今回の責務を担う current module/helper/type/test/docs と、
   標準ライブラリ、採用済み framework/dependency、既存 CLI の公開機能を一つの
   shared asset universe で比較する。provider の比較は
   [SEP-08 の再利用可能性の判断支援](../../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
   を使い、既存の呼出元・公開 API から最小の利用案と要求・保証の対応を作る。
   disposition の根拠はその対応から導き、名前やシグネチャの一致だけで決めない。
   同名のローカル実装がないことを、再利用先がない根拠にしない。split / extraction
   または suspected predecessor の現行欠落では、同じ universe を `git log`、`-S`、
   deleted paths、prior PR / Issue、predecessor tests、関連 design docs まで必要範囲で
   拡張する。bounded non-split edit では historical scan を必須にしない。
2. 各 candidate の `asset_path`、`asset_origin`、`capability`、`disposition`
   (`reuse|extend|restore|consolidate|replace|delete|reject`)、`reason`、非空の
   `test_paths` を既存 `reuse_survey` に一度だけ記録する。調査 dimension が
   非適用なら categorized `bounded_omission` と根拠を残す。候補の重複、未分類、
   根拠/test path 欠落を含む survey は write handoff へ進めない。bounded
   non-split edit で reuse choice 自体がない場合だけ、明示理由付き
   `scope=not_applicable` を使う。
3. 削除、置換、移動の候補は filename、symbol、search hit、行数では決めない。候補を行または
   block ごとに読み、各寄与を数学的・domain 上の意味、invariant、state transition、side effect、I/O、
   reachable caller / consumer として既存 handoff または review context に対応付ける。
   [RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
   により既存正本との重複が確認され廃止対象となった旧実装・旧入口は、active caller が
   残っていても同じ pass で削除する。未使用コードは到達性と副作用を確認して別に判断し、
   独自責務や未確認の意味が残る候補は重複扱いしない。全寄与の判断が閉じた場合だけ
   file 全体を削除し、全 file の監査や追加 review は待たない。旧参照の通常エラーは
   伝播させ、caller の残存を理由に wrapper、fallback、alias、互換実装を戻さない。
4. 数値コードを削除・置換する前に equations、units、state、stopping rule、convergence contract、
   failure semantics を復元する。未解決の数学的意味は既存の semantic math owner に戻し、architecture、
   compiler、JIT の変更で吸収しない。
5. `dependency-analysis` で public/module responsibility、到達性、consumer、impact を閉じる。
   RC-09 の廃止では残存参照を影響情報として残し、全面移行や編集範囲拡大の条件にしない。
   responsibility slices と `allowed_paths` はこの asset universe と disposition から導き、
   同じ asset に触れる slices を一つへ merge する。既存 provider の利用案が要求 contract を
   満たすなら、その直接利用・設定・合成へ置換し、第三の helper へ再実装しない。
   candidate がない場合も、ローカル検索ゼロだけで新 surface を admission しない。
   SEP-08 の capability 比較で残った具体的な不足責務だけを新設理由にする。実在する
   candidate の `reject` はその不足を満たせない根拠で判断し、既に満たす部分まで
   捨てない。実在しない candidate や synthetic な `reject` は作らない。
6. approved mechanism を `refactor-loop` へ渡し、同じ serialized `reuse_survey` と
   tests を各 write-capable child と read-only reviewer に伝播する。挙動保存対象と
   RC-09 による旧入口の廃止・通常エラーを区別し、子 prompt 側で disposition を再構築しない。
7. `change-review` で current snapshot、reachable path、contract、witness と
   worker packet と同一の asset/disposition/test-path evidence を readback する。targeted
   validation は各行ではなく owning-unit boundary で一度だけ実行する。

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

削除、rename、移動の oracle は analyzer ではなく public/module contract、到達性、validation、
rollback の owner evidence です。`dependency-analysis`、`refactor-loop`、`change-review` の
policy をこの skill に複製しません。search tool、asset registry、reuse database、
public code-splitting Skill は追加せず、既存 `reuse_survey` と write handoff の単一路線を使います。
