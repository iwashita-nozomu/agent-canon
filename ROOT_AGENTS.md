# Agent Instructions

Dependency Files:
- vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md
- vendor/agent-canon/agents/templates/closeout_gate.md
- vendor/agent-canon/tools/agent_tools/task_close.py

This file is the template-root runtime entrypoint for Codex and GitHub Copilot.
The shared agent canon lives in `vendor/agent-canon/`, and the root discovery paths are runtime views into that snapshot.

## Subagent Usage

- repo-changing task では、requirements / planning / detailed design / review / implementation を parent 1 人で抱え込まず、stage ごとに適切な subagent を明示して進めます。例外は trivial な単発編集だけで、その場合も run bundle に parent 直処理の理由を残します。
- parent agent は subagent を chat 要約だけで動かさず、run bundle と `team_manifest.yaml` に書かれた文書パスを明示して渡します。
- detailed design には `DESIGN_DOCUMENT_PACKET`、implementation には `IMPLEMENTATION_DOCUMENT_PACKET` を明示参照させ、必要文書を読ませてから作業させます。
- subagent の depth や fan-out は固定値で規定しません。task の複雑さ、review の独立性、write scope 分離で決め、追加する各層に owner、入力 packet、write scope、review gate を明示します。
- `.codex/config.toml` の `max_threads` を超えて同時 spawn しません。role が多い task は wave に分け、同時に動かすのはその stage で今必要な subagent だけに絞ります。
- active な subagent 数は固定 depth ではなく spawn budget で縛ります。既定は `Scoped Change` で同時 8 体まで、`Large Delivery` / `Platform And Environment` で同時 10 体まで、`Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです。これを超える場合は `schedule.md` と `work_log.md` に理由を書きます。
- 同時に write-capable な subagent は常に 1 体までです。追加分は read-only review / research / survey に限ります。

## Read Packets

### Base Runtime Packet

- `README.md`
- `agents/workflows/README.md`
- `agents/README.md`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`

### Cross-Cutting Packet

- `documents/REVIEW_PROCESS.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/coding-conventions-python.md`
- `documents/notes-lifecycle.md`
- `agents/workflows/agent-learning-workflow.md`
- `documents/agent-canon-subtree-migration.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `docker/README.md`
- `memory/USER_PREFERENCES.md`
- `memory/AGENT_PHILOSOPHY.md`

### Task Packet

- task 固有の workflow、design、implementation packet は `task_start.py` / `bootstrap_agent_run.py` の packet 出力を使って補います。
- 文書を木構造で辿るだけで終わらせず、Base Runtime Packet と Cross-Cutting Packet を先に読んでから task 固有 packet へ入ります。

## Template Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Template-default implementation lives in `python/`.
- Template-default environment and runtime guidance live in `docker/`.
- Repo-wide durable rules live in `documents/`.

## Required Before Implementation

- task 開始時、repo が clean なら `make agent-canon-ensure-latest` を実行し、`vendor/agent-canon/` snapshot を upstream `agent-canon` の最新にします。
- task 開始時に repo が dirty で `make agent-canon-ensure-latest` が実行できない場合は、`bash tools/sync_agent_canon.sh ensure-latest` の未実行理由を最初の作業 update に書き、commit / stash 後に再実行します。
- 設計変更、実装、文書改訂、実験計画の前に、`documents/`、`memory/`、`notes/knowledge/`、`notes/guardrails/`、`notes/failures/`、`notes/themes/`、`notes/branches/`、`notes/worktrees/`、`notes/experiments/`、`references/` を topic keyword で探索します。
- 実装前に、task に効く dependency surface を見ます。少なくとも `docker/requirements.txt`、`pyproject.toml`、lockfile、build file、package manager file、必要なら `pipdeptree` / `deptry` の出力を確認し、導入済みライブラリで拡張・設定変更・薄い wrapper で済まないかを先に確認します。
- 新しい code path、module、helper、test、script を足す前に、`python/`、`tests/`、`src/`、`include/`、`lib/`、`tools/`、`scripts/` を topic keyword で探索し、既存実装の再利用候補と、既存実装では足りない理由を確認します。
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を短く宣言します。
- skill を user-facing に明示する場合の既定表記は `$skill-name` です。
- durable な user preference を観測したら `python3 tools/agent_tools/log_user_preference.py --preference "<...>" --kind provisional --source chat` で `memory/USER_PREFERENCES.md` へ追記します。
- agent-side の作業哲学、対話上の再発防止、task retrospective を観測したら `python3 tools/agent_tools/log_agent_learning.py --kind interaction-observation --statement "<...>" --source chat --evidence "<...>"` で `memory/AGENT_PHILOSOPHY.md` へ追記します。
- repo-changing task では `reports/agents/<run-id>/user_request_contract.md` を最初に埋め、must-do / must-not-do / completion-evidence clause を固定します。
- repo-changing task では `reports/agents/<run-id>/schedule.md` を TODO の正本として埋め、stage と planned work units を空のままにしません。
- repo-changing task では `reports/agents/<run-id>/work_log.md` を作業開始から closeout まで維持し、意味のある step ごとに更新します。
- 詳細設計へ入る前に、その task で正本として残す設計文書 path と実装 path を固定します。tracked tree に parallel design doc、backup implementation、snapshot copy、`*_old`、`*_copy`、dated mirror を残しません。
- repo に残す durable state は current tree head 上の canonical path だけです。履歴、review、作業メモは `git` と `reports/agents/<run-id>/` に残し、repo tree に別の truth surface を増やしません。
- 大規模改修、統合、rename、構成変更の直後は、旧実装 path、旧 helper 名、旧 guide / workflow / README / 規約文書への参照を sweep し、current tree head の canonical surface だけを reader に見せます。旧参照の温存や「後で消す」前提で closeout してはいけません。

## Shared Canon

- Shared workflow, skills, subagents, docs, and support scripts are maintained in the vendored canon, not in this wrapper.
- role behavior, stage prohibitions, and review separation rules は `.codex/agents/*.toml` を正本にします。この file は薄い entrypoint のまま保ちます
- Repo-changing tasks follow the staged flow in `agents/canonical/CODEX_WORKFLOW.md`: requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation.
- code-changing tasks add `test_designer` before implementation and fix nasty cases into tests in the same pass.
- Keep `plan_reviewer`, `detailed_design_reviewer`, and `document_flow_reviewer` as separate agent instances.
- Repo-changing task では run bundle と explicit stage activation を先に作ります。
- skill を user から指定するときは `$research-workflow` や `$paper-writing` のような `$skill-name` を使います。
- Codex で planning を回すときは、parent session 側の plan-mode command を使います。official Codex CLI では `/plan` です。
- Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。
- 標準 bundle の入口は次です。

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

- `--task-id` を使うと、task catalog の default specialist と default review pack を自動で有効化します。
- `task_start.py` / `bootstrap_agent_run.py` が出す `CROSS_CUTTING_DOCUMENT_PACKET` を、designer / implementer / reviewer への handoff で省略しません。
- `memory/USER_PREFERENCES.md` は毎回読む runtime note とし、stable になった項目だけを periodic sweep で `AGENTS.md` へ昇格します。
- `memory/AGENT_PHILOSOPHY.md` は毎回読む runtime note とし、stable な作業哲学だけを periodic sweep で workflow / guardrail / `AGENTS.md` へ昇格します。
- 自己学習と対話記録の追記は shared canon `memory/` の責務として扱い、template-local note だけ更新して closeout しません。
- host runtime では repo-local virtual environment を作りません。container runtime では canonical tool `python3 tools/ci/python_env_policy.py --create` から `.venv` だけを許可し、`venv/`、`env/`、`.conda/`、`conda-env/` や ad hoc env manager は使いません。
- user request clause を持たない planning、design、implementation、review は無効です。active work は必ず clause ID に結び付けます。

- Long README、workflow、guide、migration docs では `agents/skills/long-form-writing.md` を使い、subagent review を closeout 前に通します。
- Academic papers、thesis chapters、scholarly notes、symbol-dense claim-heavy documents では `agents/skills/academic-writing.md` を使い、notation reviewer と logic reviewer を closeout 前に分離して通します。
- 投稿論文や thesis chapter の draft では `agents/skills/paper-writing.md` を優先し、citation / evidence reviewer も通します。
- tuning、比較改善、探索的改造を backlog 付きで継続反復する task では `agents/skills/adaptive-improvement-loop.md` を outer loop にします。
- worktree で作業する場合は `bash tools/worktree_start.sh <branch> [worktree-path]` で kickoff し、継続ログは `python3 tools/agent_tools/work_log.py --kind <kind> --message "<what changed>" --next "<next>"` で残します。`WORKTREE_SCOPE.md` に `user_request_contract.md` が入っていれば、同じコマンドで action log と run bundle の `work_log.md` を両方更新できます。
- `WORKTREE_SCOPE.md` の `Branch` と `Worktree path` が current state と一致しない場合は編集を始めず、`python3 tools/agent_tools/worktree_scope_lint.py --current` で直します。
- worktree では `Editable Directories` 外と `Read-Only Or Avoid Directories` 内を編集してはいけません。scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断は action log に残します。
- Python 差分では `python-review`、C / C++ 差分では `cpp-review` を既定候補にし、bootstrap は changed path から reviewer を自動で足します。
- file 構成変更を含む branch を `main` に戻すときは `agents/workflows/main-integration-workflow.md` に従い、integration worktree 上で `python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- closeout 前に `documents/notes-lifecycle.md` を見て、worktree log から `notes/knowledge/`、`notes/themes/`、`notes/failures/`、`memory/` への昇格先を決めます。
- closeout 前に `agents/workflows/agent-learning-workflow.md` を見て、今回の task から `memory/AGENT_PHILOSOPHY.md` へ残す observation があるか確認します。
- user-facing completion report は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` になるまで出してはいけません。
- user-facing completion report は、`user_request_contract.md` が `all_clauses_resolved=yes` で、`forbidden_drift_detected=no` になるまで出してはいけません。
- user-facing completion report は、`closeout_gate.md` が `spec_product_coverage_complete=yes`、`review_findings_integrated=yes`、`post_fix_full_review_complete=yes` になるまで出してはいけません。
- user-facing completion report は、`closeout_gate.md` が `unfinished_tasks_absent=yes` で、予定作業、review 対応、validation、commit / push、shared canon sync、follow-up 判断が今回 scope に残っていないことを示すまで出してはいけません。
- user-facing completion report は、作成・編集した human-authored text file の冒頭に `Dependency Files` block があり、`closeout_gate.md` が `dependency_headers_complete=yes` になるまで出してはいけません。
- If a shared surface drifts, repair it with `bash tools/sync_agent_canon.sh link-root`.
- `link-root` restores both symlink views and root files that are intentionally synced as copies.
- If you need to change shared canon itself, treat `vendor/agent-canon/` as the source of truth.
- shared canon PR では `agents/workflows/agent-canon-pr-workflow.md` を使い、`make agent-canon-pr-check` を merge 前の固定 gate にします。
- `.codex/config.toml` is the default shared Codex config; replace the symlink only when a repo-local override is intentional.
- closeout 前に、正本でない設計文書、実装 copy、dated snapshot、backup path が tracked tree に残っていないことを review artifact と `closeout_gate.md` で確認します。

## Close-Out Prohibitions

- 会話だけを根拠に実装へ進めてはいけません。
- 導入済みライブラリ棚卸しと既存実装棚卸しをせずに、新規実装や新規 helper 追加へ進めてはいけません。
- reuse sweep をせずに新しい file や module を増やしてはいけません。
- `notes/guardrails/engineering_avoidances.md` の log-derived avoid を無視してはいけません。
- user request が generic path の usable smoke を求めているのに、specialized path の tuning だけで完了扱いにしてはいけません。
- JAX export / native runtime の task では、generic callable path、specialized coeff path、export-based generic path を混同してはいけません。generic path は `jax.export` artifact と consumer/runtime evidence で確認します。
- export worker に live Python object reference を渡してはいけません。cross-process 境界は serializable manifest と reconstruction recipe で渡します。
- spot run、debug run、smoke run、partial run を正式 evidence や比較表の根拠にしてはいけません。
- 最小実装、仕様の一部だけの実装、または未反映の required review findings が残る状態で完了扱いにしてはいけません。
- review を受けて修正したあと、tiny fix だからといって full required review set を省略して closeout してはいけません。
- correctness evidence と performance evidence を混同してはいけません。
- code change、protocol change、XLA / runtime flag change を 1 つの iteration に混ぜてはいけません。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` を同じ instance で兼務してはいけません。
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を省略してはいけません。
- required review、validation、tracked change の commit / push を省略して完了扱いにしてはいけません。
- stale または別 branch / 別 path の `WORKTREE_SCOPE.md` を根拠に closeout してはいけません。
- worktree action log に scope、edit、test、experiment、carry-over の必要 entry が無い状態で closeout してはいけません。
- `schedule.md` の TODO 行が空、または `work_log.md` に意味のある作業 entry が無い状態で closeout してはいけません。
- 未完了の planned work、review finding、validation、commit / push、shared canon sync、follow-up 判断が残る状態で user-facing completion を返してはいけません。
- 作成・編集した text file の冒頭に依存 file header が無い状態で user-facing completion を返してはいけません。
- 正本でない設計文書、実装 copy、snapshot tree、backup file を tracked tree に残したまま closeout してはいけません。
- 大規模改修や構成変更のあとに、削除済み・置換済みの implementation / document surface への参照を README、guide、workflow、規約文書、script help、validation 出力へ残したまま closeout してはいけません。
- current tree head 以外を durable な product state として扱ってはいけません。履歴保持は `git` と run bundle artifact に限ります。
- `verification.txt` が `status=pass` でない、または `closeout_gate.md` が `user_completion_report=unlocked` でない状態で user-facing 完了報告を出してはいけません。

## Validation

- `make agent-checks`
- `make ci-quick`
- `make docs-check`
- `python3 -m pytest tests/ -q --tb=short`
- C / C++ 変更では project-native configure / build / test evidence
