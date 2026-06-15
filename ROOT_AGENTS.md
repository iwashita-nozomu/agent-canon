<!--
@dependency-start
responsibility Documents Agent Instructions for this repository.
upstream design README.md repository entrypoint and clone/update guidance.
upstream design documents/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface policy.
upstream design documents/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream design documents/SHARED_RUNTIME_SURFACES.md shared runtime surface and PR-template routing.
upstream design documents/template-agent-canon-audit-resolution.md audit resolution ledger for profile and gate simplification.
upstream design issues/README.md durable AgentCanon operational finding storage.
downstream implementation tools/sync_agent_canon.sh updates AgentCanon submodule pins and shared root views.
downstream implementation tools/agent_tools/goal_loop.py controls active goal iteration state.
downstream implementation tools/agent_tools/task_close.py validates run-bundle closeout gates.
@dependency-end
-->

# Agent Instructions

This file is the template-root runtime entrypoint for Codex.
The shared agent canon lives in `vendor/agent-canon/`. In this template and migrated derived repositories, that path is the AgentCanon Git submodule pin, and the root discovery paths are runtime views into that pin.

Path note: `documents/...` entries in AgentCanon-owned packets are logical
AgentCanon source paths. In standalone AgentCanon they resolve under root
`documents/`; in template or derived repo roots they resolve under
`vendor/agent-canon/documents/` unless the path is a template-owned active
contract listed in `documents/README.md`.

## Subagent Usage

- repo-changing task では、task の risk class を先に決めます。trivial / Routine docs / Focused code は parent-direct を許可し、Shared canon / Large delivery / high-risk では requirements / planning / detailed design / review / implementation を stage ごとに分けます。
- subagent は task の複雑さ、review 独立性、write scope 分離で使います。parent-direct を選ぶ場合は user update または run bundle に rationale を短く残します。
- canonical tool が正本判定を持つ question では、subagent 起動や広い文書読解の前に tool を呼びます。tool-covered property は compact pass / finding output を信頼し、subagent に同じ文書を読ませて再判定させません。
- parent agent は subagent を chat 要約だけで動かさず、run bundle と `team_manifest.yaml` に書かれた文書パスを明示して渡します。
- subagent handoff は role ごとに bounded path list、対象 checker / compact artifact、読むべき canon 節、scope 外 surface、expected output を明示します。bounded path list は編集候補、検索 hit、checker finding、changed path を seed に dependency header graph で再帰展開した `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。`/workspace` や repo root は作業場所であり、入力 packet は bounded artifact として別に渡します。
- すべての repo-changing work と subagent wave は current checkout と、その checkout 内の `vendor/agent-canon/` submodule checkout で行います。
- detailed design には `DESIGN_DOCUMENT_PACKET`、implementation には `IMPLEMENTATION_DOCUMENT_PACKET` を明示参照させ、必要文書を読ませてから作業させます。
- subagent の depth や fan-out は task の複雑さ、review の独立性、write scope 分離で決め、追加する各層に owner、入力 packet、write scope、review gate を明示します。
- 同時 spawn は `.codex/config.toml` の `max_threads` 内に収めます。role が多い task は wave に分け、同時に動かすのはその stage で今必要な subagent だけに絞ります。
- active な subagent 数は固定 depth ではなく spawn budget で縛ります。spawn budget は上限であると同時に workflow family の既定 first-wave target です。既定は `Scoped Change Lite` で同時 4 体、`Scoped Change` で同時 8 体、`Large Delivery` / `Platform And Environment` で同時 10 体、`Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです。これを超える場合、または multi-agent family で既定より少ない wave から始める場合は `schedule.md` と `work_log.md` に理由を書きます。
- write-capable subagent は既定 1 体ですが、parent が `team_manifest.yaml` の write policy と handoff で dependency order、wave plan、disjoint write scope、allowed / out-of-scope files、integration order、review gate を明示した場合は spawn budget 内で複数体を並列化できます。同一 path、同一 ownership surface、同じ file / canonical surface / shared root contract に触る作業は順序制約として先行 / 後続 wave に分けます。安全に分離できる writer は並列化し、分離が難しい writer は current checkout 内の後続 wave へ直列化します。
- 新規 user request では run bundle ごとに fresh subagent を起動します。
- `team_manifest.yaml` の `run.subagent_lifecycle_policy` を handoff prompt に含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を明示します。
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` を揃えてから user-facing completion を返します。

## Plan Mode

- repo-changing task では、実装前に Plan mode を積極的に使います。Codex runtime では `/plan` を使い、Plan mode が無い runtime では同等の written plan を run bundle、issue、PR body、または作業 update に固定します。
- GitHub Actions、PR template、AgentCanon sync、runtime entrypoint、multi-file shared surface の変更では、trivial でない限り Plan mode を先に起動します。
- Plan mode は validation 前の設計固定です。実装後に dependency review、static analysis、test、shared-surface sync、PR checklist evidence を別途揃えます。

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
- 文書読解は task family、runtime profile、router / semantic-index / dependency review の compact output を先に固定し、その route が必要にした Base Runtime Packet と Cross-Cutting Packet の slice に絞ります。inactive profile の docs は `not_applicable` として扱います。

## Template Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Template-default implementation lives in `python/`.
- Template-default environment and runtime guidance live in `docker/`.
- Repo-wide durable rules live in `documents/`.

## Execution Priorities

- 規定の実行 target は GPU です。CPU 実行は user request、環境制約、または task scope 上の明示理由がある場合だけ使い、その理由と影響を validation evidence に残します。
- 数値的 test / experiment / benchmark の failure は、code・数学仕様・文書 contract の修正先を判定してから扱います。tolerance 緩和、assertion 削除、case skip、expected 値の追従変更、CPU alternate route などは、正しい修正先がそこにある場合だけ採用し、必要なら failure として残します。
- すべての変更では、コードと文書それぞれの責務を第一に考えます。完了判断は実装 surface と document surface が担うべき責務、境界、読者への契約に合っていることを優先します。
- 設計では、先に抽象責務、概念モデル、非対象、将来 layer、評価軸、既存正本との関係を固定し、そこから実装 slice と validation を導きます。
- 修正実装は user request、責務、依存 graph、既存正本、検証 gate に結び付けます。局所的に失敗を隠す patch、未設計の alternate route / wrapper / helper、責務にない分岐、test / warning だけを黙らせる変更を検出した場合は、design / skill / workflow / tool の正本を先に直します。
- Reader-facing な docs、reports、plans、workflow guides で process、dependency、ownership、routing、state transition、review gate、multi-step flow が非自明な場合は、Mermaid diagram を既定の visual 候補にします。diagram が単純な箇条書きの重複にしかならない場合だけ省略し、省略理由を structure contract、work log、または文書内に短く残します。

## Mechanical Guardrail Policy

- AGENTS / ROOT_AGENTS に新しい制約を増やす前に、機械的 checker、warning hook、closeout artifact gate、role TOML、または workflow eval に寄せられるかを判定します。実行時 hook は作業を進めるための context / evidence 収集を既定とし、プロンプト内 secret など高確信で公開事故になるものだけを block 対象にします。
- process / search / reuse / planning / review completeness の規律は warning、run bundle evidence、`check_convention_compliance.py`、`task_close.py`、PR gate、または reviewer finding として扱います。hook finding が出た場合も、read-only 調査、validation、修復作業、PR evidence 作成は hook 設定を維持したまま進めます。
- hook や checker が非重大 finding を返した場合は、現在の作業を続け、closeout 前の修復対象として扱います。strict block mode は明示的な hook 開発・強制検証のときだけ有効にします。
- legacy forwarder / migration wrapper が `*_FORWARDER=deprecated`、`*_FORWARDER_SEVERITY=fix-now`、または caller chain 付きの移行警告を出した場合は、元の作業を続ける前に呼び出し元を特定し、canonical command へ移行します。即時移行が難しい場合は blocker として run bundle、issue、PR body に残します。
- migration wrapper を呼び得る subagent handoff、tool prompt、workflow prompt には、警告に含まれる caller chain と移行先 command を入れ、「legacy forwarder warning が出たら呼び出し元を移行してから元 task へ戻る」と明記します。
- GitPush、GitHub branch publish、`gh pr create/edit/checks/comment`、および `github_publish.py` による PR evidence 作成は user task の実行そのものです。prompt secret 以外の hook / checker finding を理由に publish / PR 作業を止めず、finding は warning、PR body、run bundle、または closeout 修復対象へ回します。
- 新しい guardrail を追加するときは、`documents/codex-configuration-reference.md` の hook severity policy に従い、block / warning / closeout gate のどれか、修復 command、ログ保存先、false-positive 時の記録先を同じ差分に含めます。

## Default Search And Routing

- 検索語や調査 surface を選ぶ前に、今回の topic を 1 文で固定し、最初の作業 update で `topic=...` としてチャットに出します。固定する内容は、user request が問う対象、現在追跡する code / proof / document path、明示的に外す非対象です。隣接する backend、tool、export、runtime surface は、この topic 文から必要性が導ける場合だけ検索対象に入れます。
- AgentCanon を使うすべての repo task では、standalone / template / derived repo の種別に関係なく、実装設計より先に skill、tool、workflow の既存 surface を検索します。最低限、`agents/skills/`、`tools/catalog.yaml`、`agents/TASK_WORKFLOWS.md`、`agents/workflows/` を task keyword と目的語で確認し、既存の責務、入口 command、review route に沿って作業を設計します。
- checker、router、semantic index、dashboard、compact report が対象判断を所有している場合は、manual prose reading より先にその tool を呼びます。tool が返す compact output で足りる場合は、その output を source packet にします。不足する場合は tool contract の gap として修正または記録します。
- 実装前に置き場所が明示 path と source packet で固定されている場合はその packet を使います。未固定の場合は、編集 path を選ぶ前に `agent-canon local-llm route-implementation-surface --request-file <request-or-design-question.txt> --format text` を走らせます。`PRIMARY_SURFACE`、`PRIMARY_PATHS`、`FORBIDDEN_PATHS`、`REQUIRED_PRE_EDIT_CHECKS` を source packet seed とし、write-capable handoff では `PRIMARY_PATHS` を `allowed_paths`、`FORBIDDEN_PATHS` を `do_not_read` に流します。LocalLLM が使える場合はその route を使い、使えない場合は deterministic fallback output または router-unavailable blocker を記録します。
- 検索結果に基づいて `workflow=...`、`skills=...`、`review=...`、source packet、validation route を固定します。skill、tool、workflow は chat 上の印象ではなく、route evidence から選びます。
- exact path、symbol、literal error message、短い一意 token 以外の検索では、`rg` より先に responsibility-based route を走らせます。まず task / question を `reports/.../query.txt` に書き、`agent-canon semantic-index context-pack --query-file <file> --max-cells <N> --format text`、`agent-canon semantic-index search --query-file <file> --top-k <N> --format text`、または `agent-canon local-llm search --purpose "<purpose>" --providers llm,tool,header-deps,code-deps,vector --format json` で responsibility bucket、dependency-header provider、tool/workflow/document surface を絞ります。directory ownership や責務 coverage が問題なら `agent-canon semantic-index responsibility-tree --root . --check-directory-coverage --report <path>` も先に使います。
- 広い概念、長い user request、文書統合、薄い文書洗い出し、既存 helper / workflow / tool の再利用候補探索では、責務ベースの bounded 結果を source packet の第一候補にします。長い文章は `--query-file` または `--query-stdin` で渡します。
- semantic-index が `unable to open database file`、missing DB、または stale cache で失敗した場合は、その場で `agent-canon semantic-index build --root .` を実行してから同じ bounded semantic-index command を再試行します。build 自体が toolchain / permission / model endpoint 理由で失敗した場合だけ、失敗理由を run bundle に残して bounded `rg -l` 比較へ降ります。
- semantic-index の JSON が必要な場合は、`--top-k` を必ず小さくし、全体 JSON を agent が読むのではなく `--format jsonl` または `jq -r '.results[] | ...'` で必要 field だけ取り出します。JSONL / compact text で足りない場合だけ、tool 実装や schema debugging の根拠を残して full JSON を開きます。
- 当面は検索 Eval 収集のため、責務ベースの bounded 結果を先に残したうえで `rg -l` も併走してよいです。この場合も raw `rg` は比較 evidence であり、編集対象は dependency review と source packet で確定します。
- `rg -l "<pattern>" <source dirs>` は、responsibility route で絞った source dirs / candidate paths に対する比較・補助 evidence、または exact path / symbol / literal error search に使います。repo root からの大量 `rg -n` は、schema debugging など根拠がある場合に限定します。
- 通常の code / docs / routing 調査では、`.agent-canon/log-archive/**`、`reports/**`、`*.jsonl`、generated dashboard / inventory / eval artifact を検索対象から除外します。skill、tool、workflow ログの分析は生ログの広域 `rg` ではなく、蓄積分析 tool、dashboard、専用 eval report で要約してから必要箇所だけ読みます。
- skill、tool、workflow、hook、eval の蓄積ログ分析では `$agent-log-analysis` を使い、compact summary、generated drilldown、prompt/token rolling trend を生成して分析します。token 利用は recent moving average と coverage status を優先します。compact summary で足りない場合は分析 tool を拡張します。
- 検索で見つけた既存 skill、tool、workflow を採用対象から外す場合は、run bundle、PR body、または作業 update に理由を残します。

## Runtime Profiles And Risk

- Runtime surface が存在することと、その task で active であることを分けます。
- Profile と validation matrix の正本は `documents/runtime-profiles-and-check-matrix.md` です。
- Routine docs / Focused code / Profile change / Shared canon / Large delivery の risk class を使い、changed path と user request に合う check を選びます。
- `make ci` は full confidence gate です。small docs や narrow code では docs check、targeted tests、changed-file dependency checks を evidence にできます。
- AgentCanon-owned path、root shared views、hooks、skills、workflows、tools、submodule pin を触る場合は Shared canon profile として扱い、AgentCanon PR gate を通します。
- 普通の相談、壁打ち、routing-only advice、説明だけの turn は conversation-only として扱います。その場合は会話だけで応答します。
- GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は GitHub-only read route として扱います。
- local repo state 確認、file edit、validation、PR / issue mutation、local CI 実行、または実装作業へ切り替わった時だけ repository task として扱います。

## Experiment And Log Diagnostics

- 数値実験、収束、optimizer、KKT / linear solver、preconditioner の失敗を診断するときは、最初に悪化した iteration / step と直前の finite state を原因推定の起点にします。
- run log は時系列で追い、最初に悪化した iteration / step、直前の finite state、RHS / reference norm、tolerance、residual、preconditioner summary、converged flag を分けて確認します。
- user-facing diagnosis では、観測された最終状態、最初の破綻点、推定原因、未確認仮説を明確に分離します。

## AgentCanon Submodule Update Flow

- Default AgentCanon routing is submodule-first: update the standalone AgentCanon repository, push AgentCanon `main` or open the AgentCanon PR, update the template `vendor/agent-canon` submodule pin, run `bash tools/sync_agent_canon.sh link-root`, validate, commit the template pin/root-view changes, then push the template.
- Legacy subtree or committed-snapshot wording is compatibility-only for repositories awaiting migration. Present the submodule-first path as the normal route in this template and in newly migrated repositories.
- Missing shared-surface files must be checked in the template root, `vendor/agent-canon/`, the standalone AgentCanon checkout, `.gitmodules`, and the shared surface manifest before recreating files. In template roots, read that manifest at `vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md`; in standalone AgentCanon, read `documents/SHARED_RUNTIME_SURFACES.md`.
- AgentCanon changes found while working on a template PR must first be evaluated against the standalone AgentCanon PR/checklist path. Shared-canon changes go through the AgentCanon path; template-only diffs are reserved for explicitly template-local scope.
- Root shared-surface edits must be made in `vendor/agent-canon/` unless the file is intentionally template-local. Root symlink/copy views should be repaired with `bash tools/sync_agent_canon.sh link-root` instead of edited as a separate truth surface.
- In submodule repos, `make agent-canon-ensure-latest` evaluates `vendor/agent-canon/`, the parent gitlink, `.gitmodules`, and AgentCanon-owned root symlink/copy views that `link-root` may mutate; unrelated parent dirty state is recorded separately.
- `goal.md` is always repo-local state. During `link-root` repair, preserve it as a repo-local file.
- For shared-canon tasks, closeout evidence must include `git submodule status vendor/agent-canon`, the AgentCanon GitHub `main` SHA or PR head SHA, and the template submodule pin SHA.
- Root `AGENTS.md` is an allowed edit target during workflow-wide reviews, but the edit must be applied to its AgentCanon source file when `AGENTS.md` is a shared root view.
- Before judging AgentCanon submodule drift by parent-tree diff, inspect `vendor/agent-canon/` directly. If it contains local commits on a branch, treat that local checkout branch as valid shared-canon work: run `bash tools/update_agent_canon.sh merge-main-into-current`, resolve conflicts inside the submodule, validate, push that AgentCanon branch to GitHub, and open or update the AgentCanon PR. Local branches are allowed, and `merge-main-into-current` must prove that fetched remote `main` is contained by emitting `agent_canon_merge_remote_main_in_post_head=yes` and `agent_canon_merge_remote_main_verified=yes`. Preserve local checkout work and make the parent pin clean through the AgentCanon branch / PR route. If GitHub `main` already contains the work, use `make agent-canon-ensure-latest` or `bash tools/update_agent_canon.sh latest` to update the parent submodule pin. Removed local proposal, safe-align, and direct `apply` compatibility commands are compatibility routes for legacy diagnosis.
- Existing branch / PR reuse is the default. If the current branch or PR already owns the same task, added user instruction, shared-canon surface, or small follow-up, continue it. A new branch requires a recorded reason such as merged / closed / unpushable current branch, separate ownership lane, explicit review isolation, protected-surface conflict, unsafe divergent state, or explicit user request. Record `branch_creation_reason=<reason>` in the run bundle, work log, or PR body before creating it.

## PR Mutation Authority

- Agents may inspect PR state, checks, reviews, branches, and mergeability with `gh` or GitHub MCP tools when those tools are available.
- Agents may create PRs, push owned branches, update PR titles/bodies, add evidence comments, convert a PR to draft, or keep a PR in draft when that action is part of the active workflow or user request.
- Agents may merge PRs, close PRs/issues, mark draft PRs ready for review, dismiss reviews, delete branches, enable auto-merge, request reviewers, or bypass failing/missing checks when the user explicitly authorizes that mutation in the current task or a repository-maintainer policy in tracked docs grants that exact action.
- A generic statement that `gh` is available grants inspection and PR preparation authority. If merge/close/readiness is the next required step and authority is absent, record the authority blocker in the PR body, run bundle, issue, or `goal.md`.
- `goal.md` may record `pr_mutation_authority`. Default `inspect_and_prepare_only` means local agents inspect, push owned branches, create/update PRs, and publish evidence only.
- `github_pr_automation_when_green` delegates merge authority to GitHub PR automation after required checks and reviews are green. Local Codex merge, review dismissal, check bypass, and chat-only evidence require their own explicit authority.
- GitHub PR automation decisions must be visible in the PR through `GITHUB_PR_AUTOMATION_AUTHORITY`, `GITHUB_PR_AUTOMATION_DECISION`, `GITHUB_PR_AUTOMATION_CHECKS`, `GITHUB_AUTOMATION_VISIBLE_EVIDENCE`, and `GITHUB_AUTOMATION_BLOCKER` lines before readiness or merge mutation.
- After an authorized PR merge or close, immediately update the downstream template/submodule pin evidence and rerun the relevant freshness, sync, dependency, and CI gates.

## Required Before Implementation

- task 開始時とは repository task の開始時を指します。普通の相談、壁打ち、routing-only advice、説明だけの turn は conversation-only、GitHub-only read inspection は GitHub-only read route として扱います。
- repository task 開始時、`make agent-canon-ensure-latest` を high-level latest route として実行し、`vendor/agent-canon/` submodule pin を upstream AgentCanon の最新にします。親 repo の無関係な dirty path は別 evidence として扱います。
- `vendor/agent-canon/` の dirty state が古い checkout 由来の AgentCanon-owned eval / hook result under `agents/evals/results/` だけなら、latest route は互換処理として `agent-logs/<parent-repo>` branch へ退避してから続行できます。新規蓄積は `.agent-canon/log-archive/` に置き、runtime source、workflow、skill、tool、document、test の dirty state は AgentCanon branch / PR workflow に送ります。
- task 開始時に AgentCanon update surface が dirty で `make agent-canon-ensure-latest` が実行できる状態にない場合は、`bash tools/update_agent_canon.sh latest` の未実行理由を最初の作業 update に書き、AgentCanon branch / PR / pin commit 後に再実行します。clean な pushed branch checkout と stale parent gitlink の mismatch は `deferred_branch_pr` evidence として扱い、dirty / detached / unpushed / divergent source state は AgentCanon workflow の修復対象にします。shared-canon task では再実行後の submodule pin evidence を closeout に残します。
- repo-changing task では、Plan mode または同等の written plan で scope、source packet、reuse survey、validation sequence、review route を固定してから編集します。
- 設計変更、実装、文書改訂、実験計画の前に、`documents/`、`issues/`、`memory/`、`notes/knowledge/`、`notes/guardrails/`、`notes/failures/`、`notes/themes/`、`notes/branches/`、`notes/worktrees/`、`notes/experiments/`、`references/` を topic keyword で探索します。
- 広い概念や修正 surface 探索では、先に responsibility-based search / context-pack で source dirs と候補責務を絞ります。必要な場合だけ bounded `rg -l "<topic>" <responsibility-scoped dirs> > reports/search_hits.txt` を併走し、そのあと `bash tools/agent_tools/run_repo_dependency_review.sh --report-dir <run-or-review-dir> --search-hits-file reports/search_hits.txt` で dependency-expanded edit scope を出し、issue / PR / run bundle に残します。
- skill、tool、workflow、HTML report、実験 script を追加または変更するときは、実装前に既存資産の調査、責務境界の解析、その後の実装という順序を固定します。調査した既存資産、再利用したもの、再利用しなかった候補と理由、責務 owner、生成 artifact の置き場所を run bundle、work log、issue、または PR body に残します。
- 実装前に、task に効く dependency surface を見ます。少なくとも `docker/requirements.txt`、`pyproject.toml`、lockfile、build file、package manager file、必要なら `pipdeptree` / `deptry` の出力を確認し、導入済みライブラリで拡張・設定変更・薄い wrapper で済まないかを先に確認します。
- 新しい code path、module、helper、test、script を足す前に、`python/`、`tests/`、`src/`、`include/`、`lib/`、`tools/`、`scripts/` を topic keyword で探索し、既存実装の再利用候補と、既存実装では足りない理由を確認します。
- ファイル横断の実装では、修正対象 file だけでなく call site、import/export surface、既存 helper、既存 test fixture、既存 workflow/tool を先に読み、既存の責務境界へ寄せます。
- 既存実装の拡張、既存 API の薄い adapter、既存 tool の option 追加、既存 test fixture の再利用で達成できる場合は、それを優先します。新しい helper、module、script、workflow branch、設定 surface は、既存 surface では足りない理由を固定してから選びます。
- 新規実装を選ぶ場合は、run bundle または作業 artifact に `Reuse Survey` として、見た path、再利用した path、採用対象から外した候補、既存では足りない具体理由を残してから編集します。
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を短く宣言します。
- skill を user-facing に明示する場合の既定表記は `$skill-name` です。
- durable な user preference を観測したら `python3 tools/agent_tools/log_user_preference.py --preference "<...>" --kind provisional --source chat` で `memory/USER_PREFERENCES.md` へ追記し、closeout 前に `python3 tools/agent_tools/persist_agent_memory.py --commit --push` で AgentCanon 側へ永続化します。
- agent-side の作業哲学、対話上の再発防止、task retrospective を観測したら `python3 tools/agent_tools/log_agent_learning.py --kind interaction-observation --statement "<...>" --source chat --evidence "<...>"` で `memory/AGENT_PHILOSOPHY.md` へ追記し、closeout 前に `python3 tools/agent_tools/persist_agent_memory.py --commit --push` で AgentCanon 側へ永続化します。
- hook、skill eval、OOP/readability guard、workflow monitor が `.agent-canon/log-archive/**` または `reports/agents/<run-id>/` に記録を出した場合、その記録は closeout evidence です。append-only / unique-id file として扱い、上書き・削除・dirty log の説明を closeout 前に解決します。
- cross-run で保持する agent report は、`python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>` で `.agent-canon/log-archive/agent-reports/<repo-key>/...` に機械的 snapshot と JSONL index を積みます。eval / hook / runtime summary も同じく tool が直接 archive path へ追記します。
- tool / hook / review / CI の finding は、まず severity と修正先を決めます。S0/S1 または `fix-now` finding は新規機能や追加整理より先に直し、直せない場合は `issues/open/AC-YYYYMMDD-*.md`、PR body、run bundle のすべてに blocker として残します。
- PreToolUse / PostToolUse / Stop hook が guardrail finding を返した場合は、指示された正本 file、baseline、ログ、依存 header、style/OOP finding、または issue evidence を修正対象にします。非重大 finding は作業を続けながら closeout 前の修復 / 記録対象とし、prompt secret など実 runtime が block を維持した場合は同じ hook / 対応 checker の pass evidence を得てから元操作へ戻ります。false positive と判断する場合も、issue または run artifact に根拠と再発防止を記録してから進めます。
- workflow defect、ログ欠落、hook 誤判定、PR gate 欠陥、検索/依存展開の欠落を見つけた場合は、同じ task 内で durable finding を作るか、既存 issue に追記します。closeout evidence には durable finding または issue link を含めます。
- Shared canon、Large delivery、goal task、multi-step work では `reports/agents/<run-id>/user_request_contract.md` を最初に埋め、must-do / must-not-do / completion-evidence clause を固定します。Routine docs / trivial parent-direct edit では user-facing summary で代替できます。
- Shared canon、Large delivery、goal task、multi-step work では `reports/agents/<run-id>/schedule.md` を TODO の正本として埋め、stage と planned work units を記録します。
- Shared canon、Large delivery、goal task、long-running multi-step work では `reports/agents/<run-id>/work_log.md` を作業開始から closeout まで維持し、意味のある step ごとに更新します。
- 詳細設計へ入る前に、その task で正本として残す設計文書 path と実装 path を固定します。tracked tree は canonical design doc と canonical implementation にそろえます。
- 実装 file / module / class / algorithm の正本名は 1 つの canonical 名に固定します。差し替えや改修が必要な場合は既存正本を更新し、旧実装は同じ change で参照ごと除去します。
- repo に残す durable state は current tree head 上の canonical path だけです。履歴、review、作業メモは `git` と `reports/agents/<run-id>/` に残します。
- 大規模改修、統合、rename、構成変更の直後は、旧実装 path、旧 helper 名、旧 guide / workflow / README / 規約文書への参照を sweep し、current tree head の canonical surface だけを reader に見せます。旧参照の扱いは同じ closeout 内で解決します。

## Shared Canon

- Shared workflow, skills, subagents, docs, and support scripts are maintained in the vendored canon.
- role behavior, stage execution conditions, and review separation rules は `.codex/agents/*.toml` を正本にします。この file は薄い entrypoint のまま保ちます
- Repo-changing tasks follow the workflow family selected from `agents/task_catalog.yaml`. `Scoped Change Lite` uses cheap-first local routing; full staged routes follow `agents/canonical/CODEX_WORKFLOW.md`: requirements -> research -> execution plan -> plan review -> detailed design -> detailed design review -> document flow review -> implementation.
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
- `task_start.py` / `bootstrap_agent_run.py` が出す `CROSS_CUTTING_DOCUMENT_PACKET` を、designer / implementer / reviewer への handoff に含めます。
- `memory/USER_PREFERENCES.md` は毎回読む runtime note とし、stable になった項目だけを periodic sweep で `AGENTS.md` へ昇格します。
- `memory/AGENT_PHILOSOPHY.md` は毎回読む runtime note とし、stable な作業哲学だけを periodic sweep で workflow / guardrail / `AGENTS.md` へ昇格します。
- 自己学習と対話記録の追記は shared canon `memory/` の責務として扱い、closeout までに shared canon 側へ反映します。
- host runtime では repo-local virtual environment を作りません。container runtime では canonical tool `python3 tools/ci/python_env_policy.py --create` から `.venv` だけを許可し、`venv/`、`env/`、`.conda/`、`conda-env/` や ad hoc env manager は使いません。
- user request clause を持たない planning、design、implementation、review は無効です。active work は必ず clause ID に結び付けます。

- Long README、workflow、guide、migration docs では `$long-form-writing` または workflow の long-form overlay を使い、docs-impact がある場合だけ subagent review を closeout 前に通します。
- Academic papers、thesis chapters、scholarly notes、symbol-dense claim-heavy documents では `agents/skills/academic-writing.md` を使い、notation reviewer と logic reviewer を closeout 前に分離して通します。
- 投稿論文や thesis chapter の draft では `agents/skills/paper-writing.md` を優先し、citation / evidence reviewer も通します。
- tuning、比較改善、探索的改造を backlog 付きで継続反復する task では `agents/skills/adaptive-improvement-loop.md` を outer loop にします。
- 新規作業は current checkout で kickoff します。`bash tools/worktree_start.sh ...` と `WORKTREE_SCOPE.md` は legacy cleanup / drift diagnosis 専用です。
- stale な `WORKTREE_SCOPE.md`、別 branch、別 path の action log を見つけた場合は、current checkout の `reports/agents/<run-id>/work_log.md` に観測事実と扱いを残します。
- scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断は current checkout の run-local work log に残します。
- Python 差分では `python-review`、C / C++ 差分では `cpp-review` を既定候補にし、bootstrap は changed path から reviewer を自動で足します。
- file 構成変更を含む branch を `main` に戻すときは `agents/workflows/main-integration-workflow.md` に従い、current checkout 上で integration branch を扱い、`python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- closeout 前に AgentCanon の `documents/notes-lifecycle.md` を見て、run-local work log から `notes/knowledge/`、`notes/themes/`、`notes/failures/`、`memory/` への昇格先を決めます。template roots では `vendor/agent-canon/documents/notes-lifecycle.md` を読む。
- closeout 前に `agents/workflows/agent-learning-workflow.md` を見て、今回の task から `memory/AGENT_PHILOSOPHY.md` へ残す observation があるか確認します。
- closeout 前に、planned work、review findings、validation、dependency review、static analysis、commit / push、shared canon sync、follow-up 判断を機械的に列挙し、未完了項目があれば実装または該当 stage へ戻ります。
- closeout 前に `python3 tools/agent_tools/task_close.py ...` の結果を mechanical closeout authority として扱い、chat 上の自己申告は補助説明にします。
- Shared canon、Large delivery、高 risk 変更では closeout 前に independent diff-check を通します。user が multi-agent work を明示した場合は read-only diff-check agent を起動し、run bundle、request contract、schedule、latest diff、validation evidence、dependency evidence を渡して approve / revise / escalate decision を artifact に残します。
- runtime の上位制約で spontaneous subagent spawn の許可が必要で、user も multi-agent work を明示していない場合は、no-spawn rationale、mechanical diff review、`task_close.py` evidence を artifact に残します。
- eval feedback action は `workflow_monitoring.md`、eval report、goal backlog、workflow、skill、memory、または closeout artifact の該当箇所へ反映してから closeout します。
- `workflow_monitoring.md` は `evaluate_agent_run.py` が読める machine-readable token を含めます。少なくとも skills、subagent routing、dependency review、web research decision、eval feedback decision、intervention、next improvement target を token 化します。
- adaptive-improvement-loop では `python3 tools/agent_tools/goal_loop.py` の `NEXT_ACTION` が closeout 判断を支配します。
- `NEXT_ACTION=run_next_iteration` は次の backlog iteration へ戻る合図です。
- `NEXT_ACTION=close_goal_loop` は closeout 候補です。validation、dependency review、static analysis、commit / push、shared-canon evidence が揃ってから user-facing completion report を返します。

## Close-Out Gate Model

- Product gates confirm the durable repository state: implementation/doc diffs, shared-canon sync, dependency headers, dependency graph, static analysis, tests, stale reference sweep, commit, push, and submodule pin evidence.
- Artifact gates confirm the run process: user request contract, schedule, work log, workflow monitoring tokens, eval feedback handling, review decisions, subagent lifecycle evidence or no-spawn rationale, and `task_close.py` status.
- Product gates and artifact gates are both required and complementary. Product diff health and closeout artifacts must both be complete.
- user-facing completion report は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` になってから出します。
- user-facing completion report は、`user_request_contract.md` が `all_clauses_resolved=yes` で、`forbidden_drift_detected=no` になってから出します。
- user-facing completion report は、`closeout_gate.md` が `spec_product_coverage_complete=yes`、`review_findings_integrated=yes`、`post_fix_full_review_complete=yes` になってから出します。
- user-facing completion report は、`closeout_gate.md` が `mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes` になってから出します。
- user-facing completion report は、`closeout_gate.md` が `unfinished_tasks_absent=yes` で、予定作業、review 対応、validation、commit / push、shared canon sync、follow-up 判断が今回 scope に残っていないことを示してから出します。
- user-facing completion report は、作成・編集した human-authored text file の冒頭に `@dependency-start` / `@dependency-end` manifest block があり、`closeout_gate.md` が `dependency_headers_complete=yes` になってから出します。
- Shared canon、Large delivery、高 risk 変更では、user-facing completion report 前に全 repo 対象の `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を通します。Routine docs / Focused code は changed-file dependency checks と relevant downstream review を evidence にできます。
- Shared canon、Large delivery、高 risk 変更では、user-facing completion report 前に全 repo 対象の静的解析を通します。既定は `make ci` です。Routine docs / Focused code は check matrix に従った targeted validation を evidence にできます。
- `make ci` が環境要因で実行できる状態にない場合は、少なくとも `python3 -m pyright` と `python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501` を全 repo 設定で実行し、不足 toolchain は修復します。
- If a shared surface drifts, repair it with `bash tools/sync_agent_canon.sh link-root`.
- `link-root` restores both symlink views and root files that are intentionally synced as copies.
- If you need to change shared canon itself, treat `vendor/agent-canon/` as the source of truth.
- shared canon PR では `agents/workflows/agent-canon-pr-workflow.md` を使い、`make agent-canon-pr-check` を merge 前の固定 gate にします。
- `.codex/config.toml` is the default shared Codex config; replace the symlink only when a repo-local override is intentional.
- closeout 前に、正本でない設計文書、実装 copy、dated mirror、backup path が tracked tree に残っていないことを review artifact と `closeout_gate.md` で確認します。

## Close-Out Readiness Checklist

この節は closeout gate の readiness checklist です。runtime hook blocker を増やす根拠ではなく、可能なものは warning hook、checker、artifact gate、または reviewer finding に寄せます。

- 実装開始前に source packet、route evidence、または approved design packet を固定します。
- 新規実装や新規 helper 追加の前に、導入済みライブラリ棚卸しと既存実装棚卸しを完了します。
- 新しい file や module を増やす前に reuse sweep を完了します。
- 既存 helper、既存 tool、既存 workflow、既存 fixture の拡張で足りる場合はその route を採用します。
- 横断的な実装判断では、関連する call site、test、script、docs、dependency manifest まで確認します。
- 新しい abstraction、utility、wrapper、script、module を追加する場合は、`Reuse Survey` に既存候補と採用対象から外した理由を記録します。
- `notes/guardrails/engineering_avoidances.md` の log-derived avoid を確認し、該当する場合は対応を work log に記録します。
- user request が generic path の usable smoke を求める場合は、generic path の evidence を completion に含めます。
- JAX export / native runtime の task では、generic callable path、specialized coeff path、export-based generic path を分けます。generic path は `jax.export` artifact と consumer/runtime evidence で確認します。
- export worker の cross-process 境界は serializable manifest と reconstruction recipe で渡します。
- 正式 evidence や比較表は、required run、accepted experiment、または documented validation artifact を根拠にします。
- completion は仕様対象全体、反映済み required review findings、validation evidence をそろえて判断します。
- review 後の tiny fix でも、risk class と changed surface に対する active required review set を確認して closeout します。
- mechanical completion loop や diff-check agent approval は、parent diff review と別 evidence として残します。
- correctness evidence と performance evidence は別項目として扱います。
- code change、protocol change、XLA / runtime flag change は iteration を分けるか、同一 iteration 内の結合理由を design trace に残します。
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は separate instance にします。
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を通します。
- required review、validation、tracked change の commit / push を completion evidence に含めます。
- stale または別 branch / 別 path の `WORKTREE_SCOPE.md` は観測事実として扱い、current checkout の scope と closeout 根拠は run-local artifact に置きます。
- current checkout の run-local work log に scope、edit、test、experiment、carry-over の必要 entry を残します。
- `schedule.md` の TODO 行と `work_log.md` に意味のある作業 entry を残します。
- user-facing completion は planned work、review finding、validation、commit / push、shared canon sync、follow-up 判断を resolved としてから返します。
- read-only diff-check agent が必要な profile では、最新 diff の approve evidence を残します。
- 作成・編集した text file の冒頭に依存 file header を置きます。
- active profile と risk class に応じた依存解析、header scan / format / graph check、静的解析を通します。Shared canon、Large delivery、高 risk 変更では全 repo 対象の evidence を残します。
- tracked tree には canonical design document、canonical implementation、current source tree だけを残します。
- 大規模改修や構成変更のあとに、削除済み・置換済みの implementation / document surface への参照を README、guide、workflow、規約文書、script help、validation 出力から sweep します。
- durable な product state は current tree head の canonical path に置きます。履歴保持は `git` と run bundle artifact に寄せます。
- user-facing 完了報告は `verification.txt` が `status=pass` で、`closeout_gate.md` が `user_completion_report=unlocked` になってから出します。

## Validation

- `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`
- `make agent-checks`
- `make ci`
- `tools/bin/agent-canon docs check`
- `python3 -m pytest tests/ -q --tb=short`
- `python3 -m pyright`
- `python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501`
- C / C++ 変更では project-native configure / build / test evidence
