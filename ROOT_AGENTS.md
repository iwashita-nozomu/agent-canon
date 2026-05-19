<!--
@dependency-start
responsibility Documents Agent Instructions for this repository.
upstream design README.md repository entrypoint and clone/update guidance.
upstream design documents/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface policy.
upstream design documents/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream design documents/github-copilot-configuration.md GitHub Copilot configuration and PR-template routing.
upstream design documents/template-agent-canon-audit-resolution.md audit resolution ledger for profile and gate simplification.
upstream design issues/README.md durable AgentCanon operational finding storage.
downstream implementation tools/sync_agent_canon.sh updates AgentCanon submodule pins and shared root views.
downstream implementation tools/agent_tools/goal_loop.py controls active goal iteration state.
downstream implementation tools/agent_tools/task_close.py validates run-bundle closeout gates.
@dependency-end
-->

# Agent Instructions

This file is the template-root runtime entrypoint for Codex and GitHub Copilot.
The shared agent canon lives in `vendor/agent-canon/`. In this template and migrated derived repositories, that path is the AgentCanon Git submodule pin, and the root discovery paths are runtime views into that pin.

Path note: `documents/...` entries in AgentCanon-owned packets are logical
AgentCanon source paths. In standalone AgentCanon they resolve under root
`documents/`; in template or derived repo roots they resolve under
`vendor/agent-canon/documents/` unless the path is a template-owned active
contract listed in `documents/README.md`.

## Subagent Usage

- repo-changing task では、task の risk class を先に決めます。trivial / Routine docs / Focused code は parent-direct を許可し、Shared canon / Large delivery / high-risk では requirements / planning / detailed design / review / implementation を stage ごとに分けます。
- subagent は task の複雑さ、review 独立性、write scope 分離で使います。使わない場合は user update または run bundle に parent-direct rationale を短く残します。
- parent agent は subagent を chat 要約だけで動かさず、run bundle と `team_manifest.yaml` に書かれた文書パスを明示して渡します。
- detailed design には `DESIGN_DOCUMENT_PACKET`、implementation には `IMPLEMENTATION_DOCUMENT_PACKET` を明示参照させ、必要文書を読ませてから作業させます。
- subagent の depth や fan-out は固定値で規定しません。task の複雑さ、review の独立性、write scope 分離で決め、追加する各層に owner、入力 packet、write scope、review gate を明示します。
- `.codex/config.toml` の `max_threads` を超えて同時 spawn しません。role が多い task は wave に分け、同時に動かすのはその stage で今必要な subagent だけに絞ります。
- active な subagent 数は固定 depth ではなく spawn budget で縛ります。既定は `Scoped Change` で同時 8 体まで、`Large Delivery` / `Platform And Environment` で同時 10 体まで、`Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです。これを超える場合は `schedule.md` と `work_log.md` に理由を書きます。
- 同時に write-capable な subagent は常に 1 体までです。追加分は read-only review / research / survey に限ります。
- 新規 user request では前 task の subagent に `send_input` せず、run bundle ごとに fresh subagent を起動します。
- `team_manifest.yaml` の `run.subagent_lifecycle_policy` を handoff prompt に含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を明示します。
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` が揃うまで user-facing completion を返しません。

## Plan Mode

- repo-changing task では、実装前に Plan mode を積極的に使います。Codex runtime では `/plan` を使い、Plan mode が無い runtime では同等の written plan を run bundle、issue、PR body、または作業 update に固定します。
- GitHub Actions、Copilot settings、PR template、AgentCanon sync、runtime entrypoint、multi-file shared surface の変更では、trivial でない限り Plan mode を先に起動します。
- Plan mode は validation の代替ではありません。実装後に dependency review、static analysis、test、shared-surface sync、PR checklist evidence を別途揃えます。

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
- `documents/runtime-profiles-and-check-matrix.md`
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

## Runtime Profiles And Risk

- Runtime surface が存在することと、その task で active であることを分けます。
- Profile と validation matrix の正本は `documents/runtime-profiles-and-check-matrix.md` です。
- Routine docs / Focused code / Profile change / Shared canon / Large delivery の risk class を使い、changed path と user request に合う check を選びます。
- `make ci` は full confidence gate です。small docs や narrow code では docs check、targeted tests、changed-file dependency checks を evidence にできます。
- AgentCanon-owned path、root shared views、hooks、skills、workflows、tools、submodule pin を触る場合は Shared canon profile として扱い、AgentCanon PR gate を通します。
- 普通の相談、壁打ち、routing-only advice、説明だけの turn は repository task ではありません。その場合は repo state 確認、MCP inventory、repo MCP tool、shell / GitHub check を走らせず、会話だけで応答します。
- GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は repository task に昇格させません。`agent-canon mcp-preflight-policy --request-kind github-actions-read` は `MCP_PREFLIGHT_DECISION=skip` を返します。
- local repo state 確認、file edit、validation、PR / issue mutation、local CI 実行、または実装作業へ切り替わった時だけ repository task として扱います。その場合、MCP inventory check は現行 runtime requirement なので維持します。これは optional profile 化しません。

## Experiment And Log Diagnostics

- 数値実験、収束、optimizer、KKT / linear solver、preconditioner の失敗を診断するときは、最後の `NaN`、`Inf`、巨大 residual だけで原因を断定してはいけません。
- run log は時系列で追い、最初に悪化した iteration / step、直前の finite state、RHS / reference norm、tolerance、residual、preconditioner summary、converged flag を分けて確認します。
- user-facing diagnosis では、観測された最終状態、最初の破綻点、推定原因、未確認仮説を明確に分離します。

## AgentCanon Submodule Update Flow

- Default AgentCanon routing is submodule-first: update the standalone AgentCanon repository, push AgentCanon `main` or open the AgentCanon PR, update the template `vendor/agent-canon` submodule pin, run `bash tools/sync_agent_canon.sh link-root`, validate, commit the template pin/root-view changes, then push the template.
- Legacy subtree or committed-snapshot wording is compatibility-only for repositories not yet migrated. It must not be presented as the normal path in this template or in newly migrated repositories.
- Missing shared-surface files must be checked in the template root, `vendor/agent-canon/`, the standalone AgentCanon checkout, `.gitmodules`, and the shared surface manifest before recreating files. In template roots, read that manifest at `vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md`; in standalone AgentCanon, read `documents/SHARED_RUNTIME_SURFACES.md`.
- AgentCanon changes found while working on a template PR must first be evaluated against the standalone AgentCanon PR/checklist path. Do not hide shared-canon changes inside a template-only diff unless the scope explicitly says the change is template-local.
- Root shared-surface edits must be made in `vendor/agent-canon/` unless the file is intentionally template-local. Root symlink/copy views should be repaired with `bash tools/sync_agent_canon.sh link-root` instead of edited as a separate truth surface.
- In submodule repos, unrelated parent dirty state does not block `make agent-canon-ensure-latest`. The required clean surface is `vendor/agent-canon/`, the parent gitlink, `.gitmodules`, and AgentCanon-owned root symlink/copy views that `link-root` may mutate.
- `goal.md` is always repo-local state. It must not be restored as a shared symlink and must not be copied from AgentCanon during `link-root` repair.
- For shared-canon tasks, closeout evidence must include `git submodule status vendor/agent-canon`, the AgentCanon GitHub `main` SHA or PR head SHA, and the template submodule pin SHA.
- Local bare mirror status is required only when the user request, goal, or workflow scope mentions `/mnt/git` or local mirror propagation.
- Root `AGENTS.md` is an allowed edit target during workflow-wide reviews, but the edit must be applied to its AgentCanon source file when `AGENTS.md` is a shared root view.
- Before judging AgentCanon submodule drift by parent-tree diff, inspect `vendor/agent-canon/` directly. If it contains local commits on a branch, treat that local checkout branch as valid shared-canon work: run `bash tools/update_agent_canon.sh merge-main-into-current`, resolve conflicts inside the submodule, validate, push that AgentCanon branch to GitHub, and open or update the AgentCanon PR. Local branches are allowed, but `merge-main-into-current` must prove that fetched remote `main` is contained by emitting `agent_canon_merge_remote_main_in_post_head=yes` and `agent_canon_merge_remote_main_verified=yes`. Do not discard or overwrite the local checkout just to make the parent pin look clean. If GitHub `main` already contains the work, use `bash tools/update_agent_canon.sh apply` or `make agent-canon-ensure-latest` to update the parent submodule pin. Removed local proposal, local bare, and safe-align compatibility commands are not normal user-facing routes.

## PR Mutation Authority

- Agents may inspect PR state, checks, reviews, branches, and mergeability with `gh` or GitHub MCP tools when those tools are available.
- Agents may create PRs, push owned branches, update PR titles/bodies, add evidence comments, convert a PR to draft, or keep a PR in draft when that action is part of the active workflow or user request.
- Agents must not merge PRs, close PRs/issues, mark draft PRs ready for review, dismiss reviews, delete branches, enable auto-merge, request reviewers, or bypass failing/missing checks unless the user explicitly authorizes that mutation in the current task or a repository-maintainer policy in tracked docs grants that exact action.
- A generic statement that `gh` is available is permission to inspect and prepare PR operations, not permission to merge or close. If merge/close/readiness is the next required step but authority is absent, record the blocker in the PR body, run bundle, issue, or `goal.md` instead of guessing.
- `goal.md` may record `pr_mutation_authority`. Default `inspect_and_prepare_only` means local agents inspect, push owned branches, create/update PRs, and publish evidence only.
- `github_copilot_merge_when_green` delegates merge authority to GitHub-hosted Copilot / PR automation after required checks and reviews are green. It does not authorize local Codex to merge from `gh`, dismiss reviews, bypass checks, or rely on chat-only evidence.
- Copilot / PR automation decisions must be visible in the PR through `COPILOT_PR_AUTHORITY`, `COPILOT_PR_DECISION`, `COPILOT_PR_CHECKS`, `COPILOT_VISIBLE_EVIDENCE`, and `COPILOT_BLOCKER` lines before readiness or merge mutation.
- After an authorized PR merge or close, immediately update the downstream template/submodule pin evidence and rerun the relevant freshness, sync, dependency, and CI gates.

## Required Before Implementation

- task 開始時とは repository task の開始時を指します。普通の相談、壁打ち、routing-only advice、説明だけの turn や GitHub-only read inspection では `make agent-canon-ensure-latest`、MCP inventory、repo MCP tools、local CI / GitHub checks を実行しません。
- repository task で MCP preflight が必要な場合は `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache` を既定にし、run bundle の `workflow_monitoring.md` へ evidence を直接追記する必要がある場合だけ `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>` を併用します。
- repository task 開始時、AgentCanon update surface が clean なら `make agent-canon-ensure-latest` を実行し、`vendor/agent-canon/` submodule pin を upstream AgentCanon の最新にします。親 repo の無関係な dirty path だけを理由に skip しません。
- task 開始時に AgentCanon update surface が dirty で `make agent-canon-ensure-latest` が実行できない場合は、`bash tools/sync_agent_canon.sh ensure-latest` の未実行理由を最初の作業 update に書き、AgentCanon branch / PR / pin commit 後に再実行します。shared-canon task では再実行後の submodule pin evidence を closeout に残します。
- repo-changing task では、Plan mode または同等の written plan で scope、source packet、reuse survey、validation sequence、review route を固定してから編集します。
- 設計変更、実装、文書改訂、実験計画の前に、`documents/`、`issues/`、`memory/`、`notes/knowledge/`、`notes/guardrails/`、`notes/failures/`、`notes/themes/`、`notes/branches/`、`notes/worktrees/`、`notes/experiments/`、`references/` を topic keyword で探索します。
- raw `rg` hit で編集対象を決めず、必要な場合は `rg -l "<topic>" > reports/search_hits.txt` のあと `bash tools/agent_tools/run_repo_dependency_review.sh --report-dir <run-or-review-dir> --search-hits-file reports/search_hits.txt` で dependency-expanded edit scope を出し、issue / PR / run bundle に残します。
- 実装前に、task に効く dependency surface を見ます。少なくとも `docker/requirements.txt`、`pyproject.toml`、lockfile、build file、package manager file、必要なら `pipdeptree` / `deptry` の出力を確認し、導入済みライブラリで拡張・設定変更・薄い wrapper で済まないかを先に確認します。
- 新しい code path、module、helper、test、script を足す前に、`python/`、`tests/`、`src/`、`include/`、`lib/`、`tools/`、`scripts/` を topic keyword で探索し、既存実装の再利用候補と、既存実装では足りない理由を確認します。
- ファイル横断の実装では、修正対象 file だけでなく call site、import/export surface、既存 helper、既存 test fixture、既存 workflow/tool を先に読み、既存の責務境界へ寄せます。
- 新しい helper、module、script、workflow branch、設定 surface は最後の手段です。既存実装の拡張、既存 API の薄い adapter、既存 tool の option 追加、既存 test fixture の再利用で達成できる場合は、それを優先します。
- 新規実装を選ぶ場合は、run bundle または作業 artifact に `Reuse Survey` として、見た path、再利用した path、再利用しなかった候補、既存では足りない具体理由を残してから編集します。
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を短く宣言します。
- skill を user-facing に明示する場合の既定表記は `$skill-name` です。
- durable な user preference を観測したら `python3 tools/agent_tools/log_user_preference.py --preference "<...>" --kind provisional --source chat` で `memory/USER_PREFERENCES.md` へ追記し、closeout 前に `python3 tools/agent_tools/persist_agent_memory.py --commit --push` で AgentCanon 側へ永続化します。
- agent-side の作業哲学、対話上の再発防止、task retrospective を観測したら `python3 tools/agent_tools/log_agent_learning.py --kind interaction-observation --statement "<...>" --source chat --evidence "<...>"` で `memory/AGENT_PHILOSOPHY.md` へ追記し、closeout 前に `python3 tools/agent_tools/persist_agent_memory.py --commit --push` で AgentCanon 側へ永続化します。
- hook、skill eval、OOP/readability guard、workflow monitor が `agents/evals/results/**` または `reports/agents/<run-id>/` に記録を出した場合、その記録は closeout evidence です。append-only / unique-id file として扱い、上書き・削除・未説明の dirty log を残したまま完了報告しません。
- tool / hook / review / CI の finding は、まず severity と修正先を決めます。S0/S1 または `fix-now` finding は新規機能や追加整理より先に直し、直せない場合は `issues/open/AC-YYYYMMDD-*.md`、PR body、run bundle のすべてに blocker として残します。
- PreToolUse / PostToolUse / Stop hook が block または `decision=block` 相当の feedback を返した場合は、その hook が要求した修復を現在の最優先作業にします。元の編集・検証・PR 操作へ戻る前に、指示された正本 file、baseline、ログ、依存 header、style/OOP finding、または issue evidence を修正し、同じ hook / 対応する checker を再実行して pass evidence を残します。false positive と判断する場合も、回避ではなく issue または run artifact に根拠と再発防止を記録してから進めます。
- workflow defect、ログ欠落、hook 誤判定、PR gate 欠陥、検索/依存展開の欠落を見つけた場合は、同じ task 内で durable finding を作るか、既存 issue に追記します。会話上の指摘だけ、または run bundle だけに残して closeout しません。
- Shared canon、Large delivery、goal task、multi-step work では `reports/agents/<run-id>/user_request_contract.md` を最初に埋め、must-do / must-not-do / completion-evidence clause を固定します。Routine docs / trivial parent-direct edit では user-facing summary で代替できます。
- Shared canon、Large delivery、goal task、multi-step work では `reports/agents/<run-id>/schedule.md` を TODO の正本として埋め、stage と planned work units を空のままにしません。
- Shared canon、Large delivery、goal task、long-running worktree では `reports/agents/<run-id>/work_log.md` を作業開始から closeout まで維持し、意味のある step ごとに更新します。
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

- Long README、workflow、guide、migration docs では `$long-form-writing` または workflow の long-form overlay を使い、docs-impact がある場合だけ subagent review を closeout 前に通します。
- Academic papers、thesis chapters、scholarly notes、symbol-dense claim-heavy documents では `agents/skills/academic-writing.md` を使い、notation reviewer と logic reviewer を closeout 前に分離して通します。
- 投稿論文や thesis chapter の draft では `agents/skills/paper-writing.md` を優先し、citation / evidence reviewer も通します。
- tuning、比較改善、探索的改造を backlog 付きで継続反復する task では `agents/skills/adaptive-improvement-loop.md` を outer loop にします。
- worktree で作業する場合は `bash tools/worktree_start.sh <branch> [worktree-path]` で kickoff し、継続ログは `python3 tools/agent_tools/work_log.py --kind <kind> --message "<what changed>" --next "<next>"` で残します。`WORKTREE_SCOPE.md` に `user_request_contract.md` が入っていれば、同じコマンドで action log と run bundle の `work_log.md` を両方更新できます。
- `WORKTREE_SCOPE.md` の `Branch` と `Worktree path` が current state と一致しない場合は編集を始めず、`python3 tools/agent_tools/worktree_scope_lint.py --current` で直します。
- worktree では `Editable Directories` 外と `Read-Only Or Avoid Directories` 内を編集してはいけません。scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断は action log に残します。
- Python 差分では `python-review`、C / C++ 差分では `cpp-review` を既定候補にし、bootstrap は changed path から reviewer を自動で足します。
- file 構成変更を含む branch を `main` に戻すときは `agents/workflows/main-integration-workflow.md` に従い、integration worktree 上で `python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- closeout 前に AgentCanon の `documents/notes-lifecycle.md` を見て、worktree log から `notes/knowledge/`、`notes/themes/`、`notes/failures/`、`memory/` への昇格先を決めます。template roots では `vendor/agent-canon/documents/notes-lifecycle.md` を読む。
- closeout 前に `agents/workflows/agent-learning-workflow.md` を見て、今回の task から `memory/AGENT_PHILOSOPHY.md` へ残す observation があるか確認します。
- closeout 前に、planned work、review findings、validation、dependency review、static analysis、commit / push、shared canon sync、follow-up 判断を機械的に列挙し、未完了項目があれば実装または該当 stage へ戻ります。
- closeout 前に `python3 tools/agent_tools/task_close.py ...` の結果を mechanical closeout authority として扱い、chat 上の自己申告だけで完了扱いにしてはいけません。
- Shared canon、Large delivery、高 risk 変更では closeout 前に independent diff-check を通します。user が multi-agent work を明示した場合は read-only diff-check agent を起動し、run bundle、request contract、schedule、latest diff、validation evidence、dependency evidence を渡して approve / revise / escalate decision を artifact に残します。
- runtime の上位制約で spontaneous subagent spawn が禁止され、user も multi-agent work を明示していない場合は、read-only diff-check agent を起動せず、no-spawn rationale、mechanical diff review、`task_close.py` evidence を artifact に残します。
- eval feedback action は chat で認めるだけでは完了ではありません。`workflow_monitoring.md`、eval report、goal backlog、workflow、skill、memory、または closeout artifact の該当箇所へ反映してから closeout します。
- `workflow_monitoring.md` は `evaluate_agent_run.py` が読める machine-readable token を含めます。少なくとも skills、subagent routing、MCP preflight、dependency review、web research decision、eval feedback decision、intervention、next improvement target を token 化します。
- adaptive-improvement-loop では `python3 tools/agent_tools/goal_loop.py` または repo MCP `goal_loop_status` の `NEXT_ACTION` が closeout 判断を支配します。
- `NEXT_ACTION=run_next_iteration` は active goal の完了報告を禁止し、次の backlog iteration へ戻ります。
- `NEXT_ACTION=close_goal_loop` は closeout 候補にすぎません。validation、dependency review、static analysis、commit / push、shared-canon evidence が揃って初めて user-facing completion report を返せます。

## Close-Out Gate Model

- Product gates confirm the durable repository state: implementation/doc diffs, shared-canon sync, dependency headers, dependency graph, static analysis, tests, stale reference sweep, commit, push, and submodule pin evidence.
- Artifact gates confirm the run process: user request contract, schedule, work log, workflow monitoring tokens, eval feedback handling, review decisions, subagent lifecycle evidence or no-spawn rationale, and `task_close.py` status.
- Product gates and artifact gates are both required, but they are not interchangeable. A clean run bundle cannot excuse a broken product diff, and passing tests cannot excuse missing required closeout artifacts.
- user-facing completion report は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` になるまで出してはいけません。
- user-facing completion report は、`user_request_contract.md` が `all_clauses_resolved=yes` で、`forbidden_drift_detected=no` になるまで出してはいけません。
- user-facing completion report は、`closeout_gate.md` が `spec_product_coverage_complete=yes`、`review_findings_integrated=yes`、`post_fix_full_review_complete=yes` になるまで出してはいけません。
- user-facing completion report は、`closeout_gate.md` が `mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes` になるまで出してはいけません。
- user-facing completion report は、`closeout_gate.md` が `unfinished_tasks_absent=yes` で、予定作業、review 対応、validation、commit / push、shared canon sync、follow-up 判断が今回 scope に残っていないことを示すまで出してはいけません。
- user-facing completion report は、作成・編集した human-authored text file の冒頭に `@dependency-start` / `@dependency-end` manifest block があり、`closeout_gate.md` が `dependency_headers_complete=yes` になるまで出してはいけません。
- Shared canon、Large delivery、高 risk 変更では、user-facing completion report 前に全 repo 対象の `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を通します。Routine docs / Focused code は changed-file dependency checks と relevant downstream review を evidence にできます。
- Shared canon、Large delivery、高 risk 変更では、user-facing completion report 前に全 repo 対象の静的解析を通します。既定は `make ci` です。Routine docs / Focused code は check matrix に従った targeted validation を evidence にできます。
- `make ci` が環境要因で実行不能な場合は、少なくとも `python3 -m pyright` と `python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501` を全 repo 設定で実行し、不足 toolchain は修復します。未実行のまま user-facing completion report を返してはいけません。
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
- 既存 helper、既存 tool、既存 workflow、既存 fixture を拡張できるのに、自前の並行実装を追加してはいけません。
- 変更対象 file だけを読んで、関連する call site、test、script、docs、dependency manifest を読まずに横断的な実装判断をしてはいけません。
- `Reuse Survey` に既存候補と不採用理由が無い状態で、新しい abstraction、utility、wrapper、script、module を追加してはいけません。
- `notes/guardrails/engineering_avoidances.md` の log-derived avoid を無視してはいけません。
- user request が generic path の usable smoke を求めているのに、specialized path の tuning だけで完了扱いにしてはいけません。
- JAX export / native runtime の task では、generic callable path、specialized coeff path、export-based generic path を混同してはいけません。generic path は `jax.export` artifact と consumer/runtime evidence で確認します。
- export worker に live Python object reference を渡してはいけません。cross-process 境界は serializable manifest と reconstruction recipe で渡します。
- spot run、debug run、smoke run、partial run を正式 evidence や比較表の根拠にしてはいけません。
- 最小実装、仕様の一部だけの実装、または未反映の required review findings が残る状態で完了扱いにしてはいけません。
- review を受けて修正したあと、tiny fix だからといって risk class と changed surface に対する active required review set を省略して closeout してはいけません。
- parent 自身の差分確認だけで mechanical completion loop や diff-check agent approval を完了扱いにしてはいけません。
- correctness evidence と performance evidence を混同してはいけません。
- code change、protocol change、XLA / runtime flag change を 1 つの iteration に混ぜてはいけません。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` を同じ instance で兼務してはいけません。
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を省略してはいけません。
- required review、validation、tracked change の commit / push を省略して完了扱いにしてはいけません。
- stale または別 branch / 別 path の `WORKTREE_SCOPE.md` を根拠に closeout してはいけません。
- worktree action log に scope、edit、test、experiment、carry-over の必要 entry が無い状態で closeout してはいけません。
- `schedule.md` の TODO 行が空、または `work_log.md` に意味のある作業 entry が無い状態で closeout してはいけません。
- 未完了の planned work、review finding、validation、commit / push、shared canon sync、follow-up 判断が残る状態で user-facing completion を返してはいけません。
- read-only diff-check agent が最新 diff を approve していない状態で user-facing completion を返してはいけません。
- 作成・編集した text file の冒頭に依存 file header が無い状態で user-facing completion を返してはいけません。
- active profile と risk class に応じた依存解析、header scan / format / graph check、静的解析を通さないまま user-facing completion を返してはいけません。Shared canon、Large delivery、高 risk 変更では全 repo 対象の evidence が必要です。
- 正本でない設計文書、実装 copy、snapshot tree、backup file を tracked tree に残したまま closeout してはいけません。
- 大規模改修や構成変更のあとに、削除済み・置換済みの implementation / document surface への参照を README、guide、workflow、規約文書、script help、validation 出力へ残したまま closeout してはいけません。
- current tree head 以外を durable な product state として扱ってはいけません。履歴保持は `git` と run bundle artifact に限ります。
- `verification.txt` が `status=pass` でない、または `closeout_gate.md` が `user_completion_report=unlocked` でない状態で user-facing 完了報告を出してはいけません。

## Validation

- `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`
- `make agent-checks`
- `make ci`
- `make docs-check`
- `python3 -m pytest tests/ -q --tb=short`
- `python3 -m pyright`
- `python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501`
- C / C++ 変更では project-native configure / build / test evidence
