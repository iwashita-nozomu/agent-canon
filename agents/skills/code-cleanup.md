# code-cleanup
<!--
@dependency-start
contract skill
responsibility Routes public/module code cleanup by responsibility and reachability through dependency analysis, refactor loop, and change review.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./dependency-analysis.md dependency and reachability owner
upstream design ./refactor-loop.md behavior-preserving refactor owner
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
の RC-02、RC-04、RC-07、RC-08 を参照します。

## Use When

- public API、module responsibility、consumer reachability、dependency closure を整理する
- analyzer finding を候補として調査し、実装 owner と refactor boundary を確定する
- behavior-preserving refactor の後に findings-first review を行う

## Route

1. file/worker slice より先に current module/helper/type/test/docs を調べ、一つの
   shared asset universe を作る。split / extraction または suspected predecessor
   の現行欠落では、同じ universe を `git log`、`-S`、deleted paths、prior PR /
   Issue、predecessor tests、関連 design docs まで必要範囲で拡張する。bounded
   non-split edit では historical scan を必須にしない。
2. 各 candidate の `asset_path`、`asset_origin`、`capability`、`disposition`
   (`reuse|extend|restore|consolidate|replace|delete|reject`)、`reason`、非空の
   `test_paths` を既存 `reuse_survey` に一度だけ記録する。調査 dimension が
   非適用なら categorized `bounded_omission` と根拠を残す。候補の重複、未分類、
   根拠/test path 欠落を含む survey は write handoff へ進めない。bounded
   non-split edit で reuse choice 自体がない場合だけ、明示理由付き
   `scope=not_applicable` を使う。
3. 削除、置換、移動の候補は filename、symbol、search hit、行数では決めない。候補を行または
   block ごとに読み、各寄与を数学的・domain 上の意味、invariant、state transition、side effect、I/O、
   reachable caller / consumer として既存 handoff または review context に対応付ける。この mapping は
   streaming とし、重複・unreachable・委譲済みで semantic / caller / effect の寄与が残らない行や
   block は同じ pass で削除する。全 file の監査や追加 review を待たない。名前が誤解を招くときは
   definition、caller、dataflow、history、consumer をたどり、全寄与が unreachable、canonical owner
   へ委譲済み、または replacement に保存済みと確認できた場合だけ file 全体を削除する。削除した
   責務を wrapper、fallback、compatibility branch、snapshot、test として戻すのは、active caller
   または contract が要求する場合に限る。
4. 数値コードを削除・置換する前に equations、units、state、stopping rule、convergence contract、
   failure semantics を復元する。未解決の数学的意味は既存の semantic math owner に戻し、architecture、
   compiler、JIT の変更で吸収しない。
5. `dependency-analysis` で public/module responsibility、到達性、consumer、impact を閉じる。
   responsibility slices と `allowed_paths` はこの asset universe と disposition から導き、
   同じ asset に触れる slices を一つへ merge する。新 surface は、調査済みの全 candidate
   が根拠付き `reject` になっている場合だけ admission する。
6. approved mechanism を `refactor-loop` へ渡し、同じ serialized `reuse_survey` と
   tests を各 write-capable child と read-only reviewer に伝播して
   behavior-preserving change として実装する。子 prompt 側で disposition を再構築しない。
7. `change-review` で current snapshot、reachable path、contract、witness と
   worker packet と同一の asset/disposition/test-path evidence を readback する。targeted
   validation は各行ではなく owning-unit boundary で一度だけ実行する。

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
