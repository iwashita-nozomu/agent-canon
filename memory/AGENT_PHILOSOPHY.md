# Agent Philosophy

<!--
@dependency-start
contract data
responsibility Documents Agent Philosophy for this repository.
upstream design README.md memory surface index
@dependency-end
-->

この file は、agent の作業哲学、対話から得た学習、repo-wide な判断原則を逐次追記する append-first note です。
`AGENTS.md` や workflow 正本へ入れる前の観測をここへ集め、十分に安定した項目だけを periodic sweep で昇格させます。

## この文書の読み方

- この note は、agent 自身の作業哲学、判断癖、対話上の再発防止、retrospective を集める append-first surface です。
- `Use` で追記対象と昇格前の扱いを確認し、`Working Principles` と `Interaction Observations` で蓄積された観測を読みます。
- 安定化した候補を確認するときは `Promotion Candidates`、未解決の論点を見るときは `Open Questions` を読みます。

## Use

- user preference は `memory/USER_PREFERENCES.md` に残します。
- agent 自身の作業哲学、判断癖、対話上の再発防止、作業後 retrospective はこの note に残します。
- 会話ログを raw に貼らず、1 observation 1 entry の短い抽象化として残します。
- source、evidence、scope、confidence を明示し、推測と確定事項を混ぜません。
- stable な運用 rule へ昇格するまでは、`AGENTS.md` や runtime entrypoint へ直接書きません。
- shared canon の `memory/` を正本にし、template 側では runtime view を使います。

## Stable Philosophy

- まだなし

## Working Principles

- 2026-04-10 | work-principle | requirements は current request、durable user preference、repo/code precedent、domain/external constraint、unknown/open question を source bucket として分離してから planning へ渡す

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to make requirements definition more careful beyond user traits from prior logs

- 2026-04-10 | work-principle | identifier naming は worker の自由裁量にせず、既存 precedent または詳細設計の naming plan に結び付ける

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request about whether variable names can be decided freely

- 2026-05-13 | work-principle | task 開始時の agent-canon ensure-latest は親 repo 全体の clean/dirty ではなく AgentCanon update surface で判断し、無関係な parent dirty state では止めない

  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: 2026-05-13 user corrected stale clean-repo freshness wording for submodule-based AgentCanon updates

- 2026-04-10 | work-principle | waterfall workflow は最終 closeout だけでなく、requirements、plan、design、test、implementation、final の中間 gate を機械チェックで fail closed にする

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request reporting weak waterfall flow and mid-process errors

- 2026-04-10 | work-principle | adaptive improvement は agile outer loop に Extension Backlog を持たせ、各 extension を 1 waterfall run-id、1 change pass、1 decision state として閉じてから次へ進む

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to strengthen Agile as one waterfall loop per extension

- 2026-04-10 | work-principle | implementation は approved design packet を読んで artifact/section を引用してから始め、設計と違う場合は Gate 5/6 に戻す

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to organize implementation around existing documents/design

- 2026-04-10 | work-principle | requirements は user に戻す前に accumulated context sweep で解決し、残った unknown だけを deferred/escalation に残す

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to avoid unnecessary runtime stops by using past logs and accumulated information

- 2026-04-10 | work-principle | Spark は design trace が固定済みの狭い implementation slice に使い、requirements/design/review/final judgment には使わない

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to delegate possible work to Codex Spark because rate limits are strict

- 2026-04-10 | work-principle | chunks, slices, checkpoints, and subpasses are internal progress; user-facing completion waits for all planned work units, active clauses, final review, validation, closeout gate, commit, and push

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to fix the habit of stopping after work-unit decomposition

- 2026-05-13 | work-principle | GitHub Actions は memory/eval/hook/issues から read-only improvement guide を生成し、実際の skill/workflow/tool 修正は branch を取り込んだ local Agent または Copilot PR が行う

  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: User asked whether Actions or local Agent should inspect evidence and accepted the hybrid PR/push guide policy

- 2026-05-18 | work-principle | 数値実験や solver failure の診断では、最後の `NaN`、`Inf`、巨大 residual を原因扱いせず、run log を時系列に追って最初の破綻点と直前の finite state を特定してから原因を述べる

  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: User corrected a PDIPM/KKT diagnosis that relied on the final failed log state instead of the first divergence point.

## Interaction Observations

- 2026-04-10 | interaction-observation | agent personality は自由作文ではなく、source/evidence/scope/confidence を持つ作業哲学として repo に蓄積する

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-10 request about agent knowledge/philosophy/personality formation

- 2026-04-10 | interaction-observation | Closeout must verify specification-to-product coverage and review-finding incorporation, not just that a minimal implementation and tests exist.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User reported a recurring pattern of closing after minimal implementation, possibly ignoring code review, and implementing only part of the specification.

- 2026-04-11 | interaction-observation | When push is a natural completion step for a tracked repo change, do not surface a separate push proposal; execute push directly unless the user explicitly forbids it or an external block exists.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-11 user: '毎回Pushの運用はやりすぎかもしれません... Pushするのが自然なら許可を取らずにpushです'

- 2026-04-11 | interaction-observation | 文書導線を tree-first にすると sibling docs への注意が落ちやすいので、subagent handoff は cross-cutting packet を先に固定してから task packet に入れる

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-11 user feedback on document intake and subagent startup

- 2026-04-27 | interaction-observation | When updating vendored agent-canon from a derived repository, apply fixes to the shared canon head and validate the resulting vendor snapshot before committing; do not rely on subtree history merges when split metadata diverges.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: During 20260427-041425, subtree-sync fixes had to be reapplied after agent-canon remote advanced and ci-quick caught the regression.

- 2026-04-27 | interaction-observation | Implementation closeout must use a mechanical completion loop plus independent read-only diff-check agent approval to prevent shortcutting user-request scope.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User requested: 実装をはしょりすぎる癖があります。機械的なループを強制的に入れ，差分チェックエージェントに確認させましょう

- 2026-05-01 | interaction-observation | File-cross coding quality regresses when the agent edits only the local target and invents parallel helpers instead of reading existing call sites, tools, workflows, and fixtures.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User requested AGENTS.md explicitly state reuse because the agent is weak at cross-file coding and tends to self-implement.

- 2026-05-13 | interaction-observation | Hook、skill eval、memory、issues の観測は root-local artifact で終わらせず、AgentCanon-owned accumulation surface に残して PR/push guide の入力にする

  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: User reported hook logs, memory, and skill results were not accumulating and asked for PR/push-time guide generation

- 2026-05-23 | interaction-observation | When launching write-capable subagents in refactor-loop tasks, the parent should verbalize the exact object-level repair intent: target qualname, current problem, intended structural change, non-goals, semantic invariants, and validation signal.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback after reports/agents/20260523-051658-pcg-refactor-loop-stopping-dependency-cl retrospective; updated refactor-loop skill handoff contract.

- 2026-05-23 | interaction-observation | For refactor-loop delegation, the parent should build a dependency-DAG orchestration plan before spawning writers: repair low-level/root slices sequentially with few agents, validate and rerun tools, then parallelize only independent downstream slices with disjoint write scopes.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback on refactor-loop subagent orchestration; updated Refactor Orchestration Plan in refactor-loop skill.

- 2026-05-31 | interaction-observation | Do not create production or test-only wrapper/subclass surfaces merely to exercise a utility; unit tests may use existing minimal protocol fixtures, and integration tests must use real repository surfaces such as existing Info/Config classes.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User objected to adding \_Nested\* test-only amp.Info/Config classes and pointed out that unit and integration tests should be separated instead.

- 2026-06-03 | interaction-observation | When a user asks for coding subagent delegation, read-only survey and review waves waste context if they do not escalate to write-capable spark_worker or worker once bounded write scope is fixed, or record the blocker.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback on 2026-06-03: coding tasks delegated to subagents are not starting often enough, while read-only agents consume context.

- 2026-06-03 | interaction-observation | AGENTS.md prose alone is too weak for preventing context-polluting direct rg usage; broad search discipline should be enforced through shell-command guards, compact-output patterns, and closeout evidence instead of relying only on instructions.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback on 2026-06-03: direct rg prohibition for context pollution prevention remains weak when written only in AGENTS.md.

- 2026-06-03 | interaction-observation | For repo searches, do not run broad rg -n over data-heavy trees; follow AGENTS.md by using semantic-index or rg -l to bound files first, then inspect selected files.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User pointed out direct rg prohibition after a broad rg -n hit bmu_tracked_intermediate CSV data and produced huge output.

- 2026-06-07 | interaction-observation | 設計時に実装対象を早く絞りすぎず、先に抽象責務、概念モデル、非対象、拡張余地、評価軸を固定してから実装 slice に落とす。

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback: 設計を行う際にスコープを絞り杉です。もっと抽象的に設計するべきです

- 2026-06-08 | interaction-observation | runtime feedback を記録しても improvement decision に接続しなければ自己成長 flow は弱い。user/reviewer 指摘を受けた時点で target/action を分類し、action=no_op 以外は skill/config/workflow/memory decision の少なくとも 1 つを applied または recorded にする

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-06-08 user feedback: 自己成長のフローが弱いです

- 2026-06-08 | interaction-observation | runtime log repository operation is incomplete when agents only emit logs locally. Log archive API compatibility, dirty-state visibility, sync/push evidence, and closeout gates must be treated as part of the agent workflow, not as optional cleanup.

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-06-08 user feedback: ログリポジトリの運用が甘いです

- 2026-06-08 | interaction-observation | Tool warnings are likely to be ignored when they are emitted only as transient stdout/stderr and are not converted into owned, status-bearing workflow obligations before closeout.

  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: User reported agents tend to ignore tool warnings; current workflow monitor has behavior events but no dedicated unresolved-warning gate.

- 2026-06-08 | interaction-observation | When using prose-reasoning-graph for document revision, close diagnostics through DSL/projection artifacts and rewrite packets before projecting to reader-facing prose; do not iterate by direct prose edits first.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User pointed out that the skill already requires DSL/projection-stage closure before prose projection during time-series probabilistic distribution design document work.

- 2026-06-11 | interaction-observation | Before ordinary tasks, agents should repair expected AgentCanon repository-structure drift using the structure-refactor pre-task route instead of recreating missing paths or choosing nearby directories.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User requested a skill for AgentCanon expected repo structure drift before tasks.

- 2026-06-11 | interaction-observation | RunBundle and Agent report collection routes should be exposed in bootstrap and dashboard output so agents do not search raw logs or invent parallel archive paths.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User noted the route for collecting past RunBundles and Agent reports was weak.

- 2026-06-11 | interaction-observation | For substantive document additions or revisions, agents should run structure analysis before adding prose; typo, link, and format-only edits can skip the gate with an explicit reason.

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User stated document additions/revisions should also perform structure analysis.

- 2026-06-11 | interaction-observation | 途中追加の user 指示は新規 task と同じ扱いにせず、same active task delta と scope change を parent checkpoint で分類してから subagent wave へ再配送する。

  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User observed that multi-agent work tends to break when additional instructions arrive mid-task.

- 2026-06-13 | interaction-observation | Conservative editing should mean evidence-backed and behavior-respecting, not file-count-driven diff; when the root cause is stale structure or an underspecified harness, the agent should choose a cohesive structural repair instead of adding only a bounded wrapper.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-06-13 user feedback: code edits are too conservative

- 2026-06-13 | interaction-observation | Before editing, repo investigation must be fixed as a packet with implementation surface route, responsibility search, reuse survey, stale-surface scan, dependency scope, and validation route; fresh subagents need a structured context capsule because they do not retain context across launches.
  - source: chat
  - scope: shared-canon
  - confidence: likely
  - evidence: User feedback on 2026-06-13; updated COMMUNICATION_PROTOCOL, agent-orchestration, codex-task-workflow, subagent-bootstrap, TASK_WORKFLOWS, CODEX_SUBAGENTS, and prompt eval coverage.

- 2026-06-14 | interaction-observation | Test-design routing must treat complaints about unnecessary numerical tests as an active test-design task, not as a generic implementation request.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User said: 不要な数値テストを入れるのをやめさせてください

- 2026-06-15 | interaction-observation | Tool-side requests to implement iterative methods should be routed through an explicit iteration-map contract and existing solver/library reuse survey before adding local loop code.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 20260615 iterative-method routing repair: route-implementation-surface now returns numerical_iterative_algorithm_contract

- 2026-06-17 | interaction-observation | Contract-only wrappers should route verification to static contract checks and existing checker evidence before adding runtime or pytest wrappers.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User reported agents forcing tests around contract-only wrappers and creating unnecessary work.

- 2026-06-18 | interaction-observation | When explaining formal proof or implementation status, avoid invented labels that are not code/theorem artifacts. Use exact file symbols, theorem names, equations, and public input/output terms; if a temporary label is unavoidable, mark it as non-canonical.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User said: 勝手に定義した名前で解説するのをやめて

- 2026-06-19 | interaction-observation | When a run-local subagent does not return, parent workflow should investigate cause evidence before close, replacement, or escalation.
  - source: chat
  - scope: subagent-lifecycle
  - confidence: stable
  - evidence: 2026-06-19 user feedback: サブエージェントが帰らないとき，止めるのではなく原因探索をするべきです

- 2026-06-21 | interaction-observation | Repository-task investigation should converge on a canonical route, edit surface, validation route, or durable issue target; exploration outside those outputs becomes supporting evidence and returns to active work.
  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: 2026-06-21 user feedback: unnecessary consideration causes many side-track cases

- 2026-06-21 | interaction-observation | Expensive commands should start from a task-linked approval note after lightweight evidence, with an owner, a budget, and a stop condition.
  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: 2026-06-21 user feedback: 勝手に重い計算を実行するのをやめさせる

- 2026-06-21 | interaction-observation | User-facing reports should use ordinary language; internal names belong only in commands, paths, tables, and exact evidence references, and new terms should come from established repository or external standard vocabulary.
  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: 2026-06-21 user feedback: 出力にコード命名由来の単語を使わない．存在しない単語を作らない

- 2026-06-22 | interaction-observation | Small repo-changing edits still require reading every selected runtime SKILL.md before patching; treat owner_bounded_skill_read evidence as a required task-route evidence item alongside bounded context.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback: 責務境界が閉じた修正のときもスキルを読む

- 2026-06-22 | interaction-observation | PR processing should preserve the change essence as a distinct PR body contract covering problem, design intent, canonical owner, behavior delta, and evidence route.
  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: 2026-06-22 user feedback that PR essence tends to be absent from documentation

- 2026-06-27 | interaction-observation | For repository investigation, start from declared repository structure and owner maps before broad text search; use text search only after selecting context by AGENTS.md, README, responsibility scope, task packets, or structure contracts.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User feedback: initial rg-first search was wrong; search from repo structure instead.

- 2026-06-27 | interaction-observation | 分割は差し替え可能な単位に限る。数理的に差し替えが発生しない境界、記法だけの境界、同じ oracle を共有する連続導出は同じ packet と owner scope に残し、過剰な subagent / document split を避ける。
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-06-27 user feedback: 分割が過剰がち。数理的に差し替えが発生しない境界を分割する必要はない。

## Task Retrospectives

- 2026-05-24 | task-retrospective | For large implementation tasks that intentionally grow agent skills, keep product eval metrics and agent-routing eval metrics in separate artifacts, and send post-fix diffs back through read-only reviewers before closeout.
  - source: run:20260524-064200-rust-semantic-index-mvp-with-eval-harnes
  - scope: shared-canon-workflows
  - confidence: likely
  - evidence: Semantic-index MVP run separated semantic_index_eval.json from workflow_monitoring.md/agent_evaluation.md and reran reviewer/docs checks after fix-now findings.

## Promotion Candidates

- 2026-05-05 | failure-avoidance | AgentCanon memory logging is incomplete unless the memory note change is committed and pushed in AgentCanon; leaving it as a submodule dirty diff makes the observation disappear from durable shared memory.
  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: User reported that AgentCanon memory is not accumulating; root memory is a symlink into vendor/agent-canon, but log tools only appended files without persistence.

- 2026-06-16 | failure-avoidance | Subagent handoffs for proof or implementation work must carry the protocol-owned `Target Binding Packet`; file lists and broad objectives alone lead to broken implementation.
  - source: chat
  - scope: subagent-handoff formal-proof implementation
  - confidence: likely
  - evidence: User feedback on 2026-06-16: weak subagent context caused broken implementation.

- 2026-06-16 | failure-avoidance | Names introduced by agents must be fixed from responsibility vocabulary, public-root/call-path context, existing naming family, and explicit forbidden names before implementation; vague labels and process-oriented names should be rejected in handoff and review.
  - source: chat
  - scope: naming subagent-handoff implementation-proof-artifacts
  - confidence: likely
  - evidence: User feedback on 2026-06-16: file and function naming was poor.

- 2026-06-16 | failure-avoidance | When an agent finds a design issue, it must not silently absorb it in implementation; it must record a design_issue_blocker and return to the design/review gate or user decision.
  - source: chat
  - scope: design-gate implementation subagent-handoff
  - confidence: likely
  - evidence: User feedback on 2026-06-16: prohibit agents from handling design problems on their own.

- 2026-06-16 | failure-avoidance | When current actions deviate from active instructions, workflow, skill, design packet, plan, allowed paths, validation gate, or review gate, the agent must stop, record policy_deviation_blocker with evidence, and return to the governing gate or user decision instead of continuing with a workaround.
  - source: chat
  - scope: runtime-entrypoint workflow-compliance
  - confidence: likely
  - evidence: User feedback on 2026-06-16: agents tend to deviate from rules; write it clearly in Agent.MD.

- 2026-06-16 | failure-avoidance | Do not make proof, validation, experiment, or implementation claims pass by fixing a backend, runtime target, compiler route, device, or dtype. Keep backend as a top-level profile/config/witness/evidence surface unless the user request or approved design explicitly fixes it; otherwise record backend_evidence_blocker.
  - source: chat
  - scope: backend-evidence proof-workflow runtime-profile
  - confidence: likely
  - evidence: User feedback on 2026-06-16: stop agents from trying to fix the backend.

- 2026-06-16 | failure-avoidance | Do not run numerical, solver, optimizer, JAX/XLA/IREE lowering, convergence, residual, benchmark, or experiment validation as CPU computational tests. Use GPU target evidence or record gpu_validation_blocker; CPU is allowed only for non-computational static/docs/tooling checks.
  - source: chat
  - scope: validation-policy numerical-tests gpu-runtime
  - confidence: likely
  - evidence: User feedback on 2026-06-16: prohibit doing computation tests on CPU.

- 2026-06-27 | failure-avoidance | Full CI is a confidence gate, not the default evidence for docs-focused, prompt-only, or focused changes; select validation by runtime profile and risk class, and record targeted evidence instead of escalating automatically to make ci.
  - source: chat
  - scope: agent-runtime-validation
  - confidence: stable
  - evidence: User feedback on 2026-06-27: CI may be excessive.

- 2026-06-28 | failure-avoidance | Conflict repair must be semantic integration: inspect base/current/incoming intent, owning contract, and validation surface before choosing clauses; never mark a conflict resolved by mechanical ours/theirs selection.
  - source: chat
  - scope: pr-processing merge-conflict-resolution
  - confidence: likely
  - evidence: 2026-06-28 user feedback: コンフリクト解決が下手です.

- 2026-06-28 | failure-avoidance | When feedback arrives while a skill is active, repair the active skill prompt and its eval anchor first; memory-only learning is insufficient for skill-behavior feedback.
  - source: chat
  - scope: agent-learning active-skill-repair
  - confidence: likely
  - evidence: 2026-06-28 user feedback: 利用中のスキル修正が甘いです.

- 2026-06-28 | failure-avoidance | When incorporating a PR, perform diff intake against the target base and repair required head-branch changes before ready/merge/pin sync; PR processing is not complete from metadata or checks alone.
  - source: chat
  - scope: pr-processing diff-intake
  - confidence: likely
  - evidence: 2026-06-28 user feedback: PR取り込み時に差分を修正するというのを忘れないようにスキル修正.

- 2026-06-28 | failure-avoidance | When codifying feedback into skills or workflow rules, calibrate the durable form first; prefer scoped guidance or examples over hard rules unless the failure is invariant, checker-backed, or repeatedly observed.
  - source: chat
  - scope: agent-learning skill-repair-calibration
  - confidence: likely
  - evidence: 2026-06-28 user feedback: 固定するときに言い過ぎ，過剰固定が目立ちます.

- 2026-06-28 | failure-avoidance | When OOP checker findings drive design action, treat size, public-surface, parameter-count, and complexity findings as boundary review signals; split only when caller contracts, ownership, or source shape show a stable boundary.
  - source: chat
  - scope: oop-readability judgement
  - confidence: likely
  - evidence: 2026-06-28 user feedback: 分割の仕方が不自然; OOPチェッカがまだ悪さして; 判定の仕方を見直してほしい.

- 2026-06-28 | failure-avoidance | For OOP readability, do not let a numeric score become the design decision; classify findings by signal class and use score only as a diagnostic index.
  - source: chat
  - scope: oop-readability scoring
  - confidence: likely
  - evidence: 2026-06-28 user feedback: 点数化の仕方が下手.

- 2026-06-28 | failure-avoidance | When closeout already has enough local validation and PR metadata, do not spend user time watching long remote CI unless the user asked for it or the result can change the next action.
  - source: chat
  - scope: closeout-validation
  - confidence: likely
  - evidence: 2026-06-28 user feedback after PR closeout: 余計な確認をした結果，時間を無駄にしています

- 2026-07-02 | failure-avoidance | Review rejection must not be handled by simply reverting or discarding user-requested behavior; preserve the request/design intent through repair, redesign, or explicit escalation, and require authority evidence before rollback.
  - source: chat
  - scope: repo-wide
  - confidence: stable
  - evidence: 2026-07-02 user feedback: review rejection rollback makes the change meaningless

## Open Questions

- まだなし
