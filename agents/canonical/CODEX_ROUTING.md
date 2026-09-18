# Codex Routing

<!--
@dependency-start
contract agent-runtime
responsibility Owns task classification, skill and profile selection, and Codex-specific routing.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for task family, skill, placement, or applicable validation selection.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## Runtime Profile And Risk Selection

Establish structure, owner, and touched-surface evidence before selecting a
runtime profile. Use
[documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md) only after that evidence fixes
the applicable validation and checker obligations.

- A runtime profile selects validation and checker obligations only. It does
  not limit context size, work scope, team mode, or task size.
- For repo-changing implementation / patch / doc-edit work, use the selected
  write-capable `worker` / `spark_worker` handoff only when the catalog typed
  route requires a child. Spawn or tool blockers produce typed
  blocked/retry/user-report evidence; the parent does not write.
- Record the selected profile and the evidence that made it applicable;
  inactive profiles remain unrecorded unless an active workflow explicitly
  asks for their status.

## Task Classification

次の 6 つから 1 つ選びます。

- `Scoped Change`
- `Research-Driven Change`
- `Large Delivery`
- `Platform And Environment`
- `Comprehensive Development`
- `Adaptive Improvement Loop`

分類規則:
- code / docs / tools / runtime をまとめて rework するなら `Comprehensive Development`
- Docker / CI / dependency の設定・構築契約の変更が要求範囲にある場合だけ `Platform And Environment`
  - `environment-maintenance` の既存手順で、必要な変更とその根拠を扱う。既存環境を使うコード変更や検証不能という事実だけでは、この family や `environment_change_proposal.md` を起動しない
  - Host にrepo-local virtual environmentを作らず、認可された AgentCanon environment 変更の検証だけに bootstrap container contract と実 lifecycle readback を使う。project environmentはproject-owned validatorへ委譲する
- 外部調査や比較実験が必要なら `Research-Driven Change`
- tuning、比較改善、探索的 protocol refinement を backlog 付きで回すなら `Adaptive Improvement Loop`
  - Agile outer loop とし、1 extension ごとに 1 waterfall run-id / 1 waterfall pass / 1 decision state へ分解する
- chunk ごとの delivery なら `Large Delivery`
- それ以外は `Scoped Change`

## Contract-Required Skill Set

Codex では、まず `$agent-orchestration` を起点にし、[agents/skills/README.md](../skills/README.md) から current stage と contract に必要な skill を選びます。
user が skill を明示したい場合は `$skill-name` を使います。例: `$repo-onboarding`、`$research-workflow`、`$paper-writing`
細粒度の review pass、CLI adapter、artifact placement、validation helper は public skill ではなく、[documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md) と `agents/canonical/` に寄せます。
repo-changing task では `python3 tools/agent/orchestration/route.py --prompt "<request>" --mode repo-changing --format json` の `ACTIVE_SKILLS` を routing declaration に使い、`$codex-task-workflow` は execution stage、`$subagent-bootstrap` は `agents/task_catalog.yaml#workflow_activation_policy` が child handoff を要求する typed route で current stage に入った時点だけ active にします。prompt-only bounded routing では `--mode routing-only` を使い、child を要求しません。
`bootstrap_agent_run.py` は `--task` 文面から prompt-derived
skill を追加し、選択済み skill ごとの repo tool route を
`run.repo_tool_routing_policy` に出します。repo tool route は skill ごとに
`show_skill_packet`、`required_commands`、
`task_matching_conditional_commands`、`validation_commands` の順で扱います。
後続 wave で関連 skill が active になった場合は、同じ
`skill_tool_commands.py show --skill <skill> --format text` を再生成してから
handoff に入ります。

Before a capability gap claim about an existing API, dependency, config,
or extension point, the implementation plan includes the
[documents/design/api-surface-traversal-policy.md](../../documents/design/api-surface-traversal-policy.md) evidence trail. Helper wrappers,
native reusable API patches, and vendor/library edit proposals follow
after the public import/export/signature/nested-config/example path has been
checked and cited.

- workflow / runtime routing:
  - `agent-orchestration`
- repo 入口確認:
  - `repo-onboarding`
- subagent 起動:
  - `subagent-bootstrap`
- code review:
  - `change-review`
- Python diff:
  - `python-review`
- C / C++ diff:
  - `cpp-review`
- test design:
  - `test-design`
- owning implementation mechanism の確立または修復後に、semantic responsibility contract の owner と targeted validation で閉じない test-owned runtime risk が残る場合だけ `test-design` / `test_designer` を起動し、Activation Decision と boundary classification を先に返す。起動後は未解決oracleを必要十分に覆うケースだけを設計し、checker-owned property、重複契約、no-crash、内部形状固定をtestへ追加しない
- paper writing:
  - `paper-writing`
- general explanatory docs:
  - `long-form-writing` as the DSL-to-prose adapter when file/document responsibility is README, workflow, guide, migration, specification, or similar explanatory prose
- academic docs:
  - `academic-writing`
- Markdown diff:
  - `md-style-check`
- worktree drift and cleanup:
  - `worktree-health`
- experiment inner loop:
  - `experiment-lifecycle`
- experiment review:
  - `experiment-review`
- tuning / research / experiment の backlog-driven outer loop:
  - `adaptive-improvement-loop`
- literature and prior art:
  - `literature-survey`
- research outer loop:
  - `research-workflow`
- 包括的 repo-wide delivery:
  - `comprehensive-development`
- environment and tool rollout:
  - `environment-maintenance`
- private knowledge / feedback の検索・記録と agent-side 対話学習:
  `agent-learning` と Rust `agent-canon k/f` を使う。stable preference は対象
  [AGENTS.md](../../AGENTS.md) または canonical owner への明示変更として扱う。

## 2. Workflow Selection

- [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md) から family を 1 つ選ぶ
- family をまたぐ場合も、主 family を 1 つ決める

## 3. Placement

- run 固有のメモは `reports/agents/<run-id>/`
- repo-wide の恒久文書は `agents/` か `documents/`
- 知見の蓄積は `documents/notes/`
- packet 出力は tree 順ではなく、`CROSS_CUTTING_DOCUMENT_PACKET`、`DESIGN_DOCUMENT_PACKET`、`IMPLEMENTATION_DOCUMENT_PACKET`、`WORKFLOW_SUBAGENT_PROMPT_PACKET` の順で handoff に使う

## Codex-Specific Rules

- [AGENTS.md](../../AGENTS.md) は Codex のruntime 入口として保つ
- `.codex/personal/skills/` を正規 skill path とする
- repo-changing task では、selected stage の subagent / specialist だけを明示し、候補 stage や未選択 reviewer を work にしない
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は active な
  distinct unresolved claim/risk がそれぞれ必要とした場合だけ選択し、選択した別 gate
  の場合にだけ別 instance にする
- 学術文章の notation / logic reviewer と論文 draft の citation evidence reviewer は候補であり、同じ owner、context、validation route で判定できる場合は active review instance を再利用し、distinct unresolved claim の場合だけ別 instance にする
- 包括的開発では、parent が dependency order、wave plan、dependency-expanded disjoint write scope、integration order、review gate を handoff packet に載せます
- 複数 writer を要する場合は、衝突 target を先行 / 後続 wave に分けます。安全に分離できる writer は同一 wave、追加判断が要る writer は current checkout 内の後続 wave へ直列化します
- writer ごとの path / directory / object は `team_manifest.yaml` の write policy で管理します
- selected owner/design review gate が resolved または not-needed になってから `worker`
  相当の実装を始める
- tracked repo change がある task では、selected review gate (when activated)、validation、
  および既存の commit / push 判断を完了させ、その結果を closeout evidence にする。commit と push を無条件の完了条件にはしない
- standalone local source-branch push を選択した場合は reversible branch transport として、
  verified remote identity/permission、named branch、commit/tree、SHA ref
  push、remote `ls-remote` readback、push 前後の local identity 不変を
  completion evidence にする。G1/G2/G3/PR lifecycle は生成・主張しない。
  packet-bound push と PR mutation は既存 sealed 要件を使い、CI fresh-clone
  fixture は通常 publication の証拠に数えない
- tracked repo change で sharing、handoff、remote backup、PR などの目的、権限、宛先から push が自然な完了条件と判断できる場合は、push の許可を取りに戻らず実行する。user が明示的に停止した場合や external block がある場合は、理由を evidence に残す
- planned work、review finding、validation、commit / push の判断・結果、shared canon sync、follow-up 判断の completion evidence を揃えて user-facing completion を返す
- `verification.txt`、`closeout_gate.md`、`user_request_contract.md` の close 条件を満たして user-facing completion を返す
- Codex 専用事情でも、再利用可能なルールは `agents/` に昇格する
- 会話文脈由来の運用は repo 正本へ昇格してから使う
