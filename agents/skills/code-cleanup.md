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

1. split / extraction または suspected predecessor の現行欠落を検出したら、
   current module/helper/type/test/docs と `git log`、`-S`、deleted paths、prior
   PR / Issue、predecessor tests から一つの shared current+historical asset
   universe を作り、decomposition / prototyping より先に調べる。bounded
   non-split edit では historical scan を必須にしない。
2. known な asset path、capability、disposition、reason、test paths は既存の
   `reuse_survey` に advisory context として記録する。context の不在は
   dispatch や write を block しない。
3. 削除、置換、移動の候補は filename、symbol、search hit、行数では決めない。候補を行または
   block ごとに読み、各寄与の数学的・domain 上の意味、invariant、state transition、side effect、
   I/O、reachable caller / consumer を既存 handoff または review context に対応付ける。名前が誤解を
   招くときは definition、caller、dataflow、history、consumer をたどり、全寄与が unreachable、
   canonical owner へ委譲済み、または replacement に保存済みと確認できた場合だけ file 全体を削除する。
4. 数値コードを削除・置換する前に equations、units、state、stopping rule、convergence contract、
   failure semantics を復元する。未解決の数学的意味は既存の semantic math owner に戻し、architecture、
   compiler、JIT の変更で吸収しない。
5. `dependency-analysis` で public/module responsibility、到達性、consumer、impact を閉じる。
   responsibility slices と known な `allowed_paths` はこの asset universe から導き、
   同じ asset に触れる slices を一つへ merge する。
6. approved mechanism を `refactor-loop` へ渡し、同じ known asset context と
   tests を各 child に伝播して behavior-preserving change として実装する。
7. `change-review` で current snapshot、reachable path、contract、witness を readback する。

## Tool Commands

```bash
python3 tools/validation/semantic/dependencies/check_dependency_headers.py --changed
bash tools/analysis/dependencies/scan_code_dependencies.sh --changed
bash tools/analysis/dependencies/run_repo_dependency_review.sh
```

## Boundary

削除、rename、移動の oracle は analyzer ではなく public/module contract、到達性、validation、
rollback の owner evidence です。`dependency-analysis`、`refactor-loop`、`change-review` の
policy をこの skill に複製しません。
