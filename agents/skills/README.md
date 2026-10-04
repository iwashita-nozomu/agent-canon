# Shared Skill Canon

<!--
@dependency-start
contract skill
responsibility Documents Shared Skill Canon for this repository.
upstream design ./catalog.yaml enumerates public skill families
upstream design ./skill-dependencies.yaml owns the typed public-skill dependency dictionary
downstream design ../canonical/CODEX_WORKFLOW.md consumes the shared skill canon during task routing
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates public and official skill boundaries
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../tools/agent/skills/skill_route_catalog.py validates visualization owner and adapter metadata
downstream implementation ../../tools/agent/skills/skill_dependency_map.py validates the dependency dictionary and generates its Mermaid projection
@dependency-end
-->

このディレクトリは public Codex skill 文書の人間向け正本です。

## Reader Map

作成・公開範囲は [Rules](#rules) と [Skill Visibility Naming](#skill-visibility-naming)、
選択は [Codex Defaults](#codex-defaults)、正本の変更は [Updating Skills](#updating-skills) を参照します。
各 skill の長い手順はその正本文書が所有し、この索引や [AGENTS.md](../../AGENTS.md) へ複製しません。
以下のリンクは必要時の参照先であり、全項目の起動・読了を要求する一覧ではありません。

## Visualization Ownership

[`code-visualization`](code-visualization.md) is the sole public visualization skill.
Visualization-producing skills remain native fact producers or renderer/formatter adapters
and use its `VisualizationSourceUniverse`, schema-bearing `ToolCall`,
`ProjectionCoverageManifest`, post-format readback, and final coverage status.
The public catalog adds neither a second visualization owner nor copies of the
universal omission/granularity policy in adapter entries.

## Rules

- skill の目的・使う場面・関連正本は `agents/skills/<skill>.md` に置きます。
- ユーザーが skill を明示する構文は `$skill-name` です。曖昧な prose より優先します。
  例: `$research-workflow`、`$adaptive-improvement-loop`、`$paper-writing`。
- 文書間参照は [Markdown リンク規約](../../documents/conventions/common/05_docs.md) に従い、
  [md-style-check](md-style-check.md) のように正本へリンクします。呼出し構文とは区別します。
- public skill はユーザーが直接選ぶ価値のあるものに限定します。細粒度の review checklist、
  CLI adapter、artifact placement、validation helper は既存の canonical docs と routing が所有します。
- 発表資料、token 効率、ローカル branch 統合の手順は、それぞれ [slides](slides.md)、
  [tokens](tokens.md)、[integration](integration.md) を正本とし、旧 workflow 文書へ戻しません。

## Skill Visibility Naming

| 所有者・用途 | 正本と公開方法 |
| --- | --- |
| AgentCanon public skill | `research-workflow` のような hyphen-case。本文はこの directory、列挙は `catalog.yaml`。保守時に `.codex/personal/skills/<skill>/SKILL.md` を生成し、正本と同じ commit で Git 配布する。Codex は管理された `~/.agents/skills/` directory link から読む。利用時には生成せず、`.codex/config.toml` に同じ inventory を列挙しない。 |
| runtime-internal shim | `_runtime-helper` のような先頭 underscore。所有者は呼出元 workflow / role / public skill であり、public catalog・public table・`.codex/config.toml` には列挙しない。 |
| workflow-only routine | `agents/internal-routines/`。Codex discovery shim が必要な場合だけ runtime-internal lane を使う。 |
| parent repository 固有 skill | parent 自身の `.agents/skills/<skill>/SKILL.md`。subtree-owned skill も含む。 |

生成先、native discovery、repository 固有入口の詳細は [Skill Paths](../canonical/skills.md#skill-paths) を参照します。
public への追加・昇格は [Updating Skills](#updating-skills) の同一変更で行います。

## Public Skill Surface

公開 skill の id、purpose、canonical doc、discovery shim、prompt routing trigger の列挙正本は
[`catalog.yaml`](catalog.yaml) です。必須前提、後続、順序制約、並列可能な独立関係、責務階層は
[`skill-dependencies.yaml`](skill-dependencies.yaml) が所有し、routing の呼出し順と関連候補も同じ辞書から導出します。

[agent-orchestration](agent-orchestration.md) は task 開始時の routing entry として public surface の先頭に置きます。
[subagent-bootstrap](subagent-bootstrap.md) も public とし、選択された repo-changing task の stage separation で使います。

`skill_dependency_map.py` が単一の Mermaid/JSON graph を生成します。通常は明示した外部 runtime artifact へ出力し、
source checkout の `documents/runtime/` を暗黙に更新しません。tracked reader pair の更新だけは、固定 Markdown/JSON
2 path の `--source-mutation-capability-json` と外部 before/after evidence を伴う明示保守操作です。
図を手編集せず、辞書の変更から再生成します。

次は既存の実行 owner が使う確認入口です。同じ検査を重複実行するチェックリストではありません。

| 目的 | 入口 |
| --- | --- |
| public / shim / doc / config 整合 | `python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py` |
| prompt に対する選択 | `python3 tools/agent/orchestration/route.py --prompt "<user request>" --mode routing-only --format json` |
| skill の command packet | `python3 tools/agent/skills/skill_tool_commands.py show --skill <skill> --format text` |
| 依存辞書の静的検査（source 非変更） | `python3 tools/agent/skills/skill_dependency_map.py check --root .` |
| 外部 graph 生成 | `python3 tools/agent/skills/skill_dependency_map.py graph --root . --runtime-root <external-runtime-root>` |
| tracked reader pair の明示更新 | `python3 tools/agent/skills/skill_dependency_map.py graph --root . --output documents/runtime/skill-dependency-graph.md --runtime-root <external-runtime-root> --source-mutation-capability-json <exact-two-path-capability.json>` |

## Internal Review And Runtime Routines

docs completeness / consistency、notation、logic gap、citation/evidence、critical/report、research perspective review は、
public skill ではなく workflow が必要時に要求する review pass です。artifact placement、CLI adapter、static validation は
`agents/internal-routines/`、`agents/canonical/`、[REVIEW_PROCESS](../../documents/conventions/REVIEW_PROCESS.md) に置きます。
一覧と route は [internal-routines/README.md](../internal-routines/README.md) が所有します。
carry-over は `documents/notes/` と worktree log を正本とし、独立 public skill を追加しません。

## Official System Skill Delegation

OpenAI system skill の本文は host runtime が提供します。AgentCanon は routing trigger、local evidence、repo 固有契約だけを持ちます。

| Official System Skill | AgentCanon Route |
| --- | --- |
| `$openai-docs` | 現行 OpenAI / Codex product docs、model guidance、API reference、Codex manual の source。 |
| `$skill-creator` | local owner surface を確定した後の skill 作成・refactor・指示品質改善。 |
| `$skill-installer` | external skill の導入と curated skill 一覧。 |
| `$imagegen` | HTML、report、dashboard、mockup 用 bitmap asset。 |
| `$plugin-creator` | Codex plugin scaffold、manifest defaults、marketplace、reinstall。 |

## Codex Defaults

[AGENTS.md](../../AGENTS.md) と [CODEX_WORKFLOW](../canonical/CODEX_WORKFLOW.md) を先に読み、
repo task の選択は [agent-orchestration](agent-orchestration.md) から始めます。
上記 `route.py` の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` を第一候補とし、本文と catalog で責務を確認します。
編集を明示的に許可する場合だけ `--mode repo-changing` を渡し、prompt 語彙だけで mode を拡張しません。

owner、差し替え可能な単位、validation route、`external public API/behavior/schema unchanged` が evidence で閉じる修正は通常の
owner route で進めます。既存 tool は読了 gate なしに先に実行し、owner boundary・existing-tool route・targeted validation を
記録します。typo / link / format-only、Routine docs、Focused code の label もこの条件を迂回しません。
public surface の追加・縮小・削除・rename・restriction・deprecation・意味変更は `scoped_change` または broader route で
`dependency/consumer/migration/docs closure` を形成し、file 数や owner の近さだけで route を固定しません。
execution stage で [codex-task-workflow](codex-task-workflow.md)、handoff / wave が ready になった stage で
[subagent-bootstrap](subagent-bootstrap.md) を追加します。specialist の Codex 固有方針は [CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md) を参照します。

以下は既存の条件付き選択先です。列挙は起動許可や全件必読を意味しません。

| 条件 | 選択する owner と境界 |
| --- | --- |
| template から新 repository を開始 | [start-repository](start-repository.md) |
| 長い tool / skill 候補を短い command へ解決 | [task-routing](task-routing.md) |
| dependency module の source clone / lifecycle / cleanup | 先に [dependency-module-change](dependency-module-change.md)。AgentCanon pin/update はこの一般規約を使う具体例。 |
| 既存 Dev Container 内の一時的な `devcontainer exec --workspace-folder <root> ...` | [devcontainer-exec](devcontainer-exec.md)。Dockerfile・dependency・設定・build・起動は [environment-maintenance](environment-maintenance.md) / [dependency-design](dependency-design.md)、GPU admission は [gpu-execution](gpu-execution.md) が所有。 |
| 文献調査が主 task | [literature-survey](literature-survey.md) |
| 自然言語の数学 claim を形式証明へ移す | [formal-proof-workflow](formal-proof-workflow.md)。既存 proof / 文献探索は [literature-survey](literature-survey.md)。 |
| production 実装前のアルゴリズム設計 | [lean-algorithm-design](lean-algorithm-design.md)。Lean 数学モデルと target theorem を先に検証する。 |
| 収束・停止・certificate soundness・finite-precision floor・solver-chain handoff の方式探索 | [algorithm-proof-exploration](algorithm-proof-exploration.md)。最終 theorem / counterexample / unprovable-under-assumptions claim は [formal-proof-workflow](formal-proof-workflow.md)。 |
| 一般説明 prose の README / workflow / guide / migration / specification | [long-form-writing](long-form-writing.md)。長さだけでは選択しない。 |
| 論文、thesis chapter、scholarly note | [academic-writing](academic-writing.md)。paper section を含む draft は [paper-writing](paper-writing.md) を先に参照。 |
| 研究 task / backlog 付きの tuning・探索・比較改善反復 | outer loop はそれぞれ [research-workflow](research-workflow.md) / [adaptive-improvement-loop](adaptive-improvement-loop.md)。 |
| experiment topic、`run.py` 直実行、GPU/JAX 所有、artifact schema、`visualization.py` readiness の review | [experiment-review](experiment-review.md) |
| 実験結果の保持・archive・externalization・削除を実行前に計画 | [retention](retention.md)。実験実行、artifact identity/checksum、archive serialization は各既存 owner。 |
| semantic delta・obligation・一次検証 owner・hard-edge closure の実装前割当 | [semantic-responsibility-contract](../../documents/design/semantic-responsibility-contract.md) と `templates/documents/semantic-responsibility-contract.template.toml`。 |
| owning mechanism の確立・修復後も既存 owner と targeted validation で閉じない test-owned runtime risk | [test-design](test-design.md)。contract-only wrapper は static contract validation と canonical command evidence を使う。 |
| 文書の正本・generated evidence・closed Issue record・重複見出しの整理 | [document-canon-cleanup](document-canon-cleanup.md) |
| dependency manifest、reverse edge、cycle、全 inventory、change-impact / repair-planning packet | [dependency-analysis](dependency-analysis.md) |
| 大規模 refactor | [refactor-loop](refactor-loop.md)。semantic delta を別管理し、target 選定・handoff 前に上記 change-impact packet を入力にする。 |
| directory / README / root view / path mapping / responsibility map の責務変更 | [structure-refactor](structure-refactor.md)。recursive directory responsibility graph を先に作る。 |
| ユーザーが1件ずつ共同デバッグする進め方を明示 | [user-guided-debugging](user-guided-debugging.md)。修正前の問題提示と修正後の次課題提示を保持。 |
| C / C++ 差分 | [cpp-review](cpp-review.md) を既定候補にする。 |
| OOP readability tool の実行・表出力・解釈 | [oop-readability-check](oop-readability-check.md)。`Mechanical Result` と `Agent Analysis` を分ける。 |
| tool / hook / eval / skill / experiment 結果の書出し | [result-artifact-writeout](result-artifact-writeout.md)。raw / summary / manifest / unique path / overwrite policy を区別。 |
| tool・checker・hook・static / structure analysis の report / repair packet | [tool-finding-report](tool-finding-report.md)。raw・structured full artifact、mechanical priority、任意 impact、prompt feedback decision を区別。finding の取捨選択は上位 workflow。 |
| skill / tool / workflow / hook / eval 蓄積ログの分析 | [agent-log-analysis](agent-log-analysis.md)。既存 summary を再利用。不足は対象限定読取と制限の明示で扱い、archive 保守・dashboard 修理を前提にしない。 |
| summary / prompt / run bundle / hook / routing / eval evidence から durable skill Issue を作る | [issue-finding-report](issue-finding-report.md)。抽象原因、重複検索、dependency-expanded edit scope、multi-agent partition を先に固定。 |
| accumulated eval family の収集・修理を選択した | [agent-eval-accumulation](agent-eval-accumulation.md)。registered producer / compact checker / archive loop を使う。missing / stale / fail の観測・Issue 記録だけで再実行せず、eval report を手生成しない。 |
| PR 処理・merge・conflict・ready 化・Issue triage・queue cleanup | [pr-processing](pr-processing.md)。mutation authority、merge order、validation evidence、Issue action table を先に固定。 |
| AgentCanon source・共有 bootstrap・parent の development clone 運用の更新 | [agent-canon-update](agent-canon-update.md)。source PR と parent change を分離し、parent に pin / vendor checkout / root projection を追加しない。 |
| agent-runtime branch や AgentCanon pin 更新の分離が必要 | [agent-update-branch](agent-update-branch.md) |
| report・status・eval / audit summary・decision brief・presentation narrative・PPT storyboard | [report-writing](report-writing.md)。source packet、visual asset plan、Report Quality Checklist を固定。 |
| 既存 prose の graph 分析を明示依頼、または具体的診断目的がある | [prose-reasoning-graph](prose-reasoning-graph.md)。段落接続、claim/evidence、experiment plan、split / merge / bridge / reorder、既存 skill handoff を扱う。 |
| report / experiment / Eval / decision / presentation / HTML / document / paper / refactor の構造が非自明 | 本文・renderer・run・編集の前に [structure-planning](structure-planning.md)。primary artifact、source map、metric / delta contract、invalid interpretation を固定。未決の reader path・section order・claim/support も対象。 |
| typo / link / format-only 文書変更 | [md-style-check](md-style-check.md) と `structure_contract=skipped` の理由を残す。 |
| 文書の process・dependency・ownership・routing・state・review gate・handoff が非自明 | [structure-planning](structure-planning.md) の `visual_plan` で Mermaid を既定の primary visual 候補にする。 |
| 明示的な HTML / browser view / dashboard / web page / 外部 browser 公開 | [html-output](html-output.md)。layout、ImageGen、server reuse / start command、local / external URL を固定。report の既定は Markdown。 |
| 既存 experiment / Eval artifact の HTML 表示 | [html-output](html-output.md) を直接使う。新規・再実行だけ [experiment-lifecycle](experiment-lifecycle.md)、解釈・claim が必要な場合だけ [report-writing](report-writing.md) を追加。中間 wrapper skill を作らない。 |
| stale worktree・古い `WORKTREE_SCOPE.md`・legacy action log | [worktree-health](worktree-health.md) で調査・cleanup 判断。 |
| optimizer / solver / preconditioner / gradient / Jacobian / Hessian / KKT / 収束 / tolerance / 数値 benchmark | [computational-optimization](computational-optimization.md)。数学・検証契約を実装や実験の前に固定。 |
| GPU / CUDA / JAX / XLA / IREE backend 実行、GPU 環境変数・nvidia-smi・JAX preallocation・GPU blocker | [gpu-execution](gpu-execution.md)。Python 実行は ExperimentRunner へ委譲。 |
| JIT-canonical IR・Lean 実装定義・theorem graph overlay から反復法/証明状態の Mermaid block chart | [algorithm-flowchart](algorithm-flowchart.md)。proof navigation として使い、証明済み判定は formal proof checker へ戻す。 |
| repo-wide の実装・文書・tooling・runtime 統合変更 | [comprehensive-development](comprehensive-development.md) |
| repo-wide tool 導入や Docker / CI 更新案 | [environment-maintenance](environment-maintenance.md) と [environment_change_proposal](../../templates/agents/environment_change_proposal.md)。 |
| private knowledge / feedback の検索・記録 | [agent-learning](agent-learning.md) と Rust `agent-canon k/f`。stable preference は対象 [AGENTS.md](../../AGENTS.md) への明示変更として昇格し、private log / source tree を第二正本にしない。 |

## Updating Skills

1. `agents/skills/<family>.md` と `agents/skills/catalog.yaml` を同じ変更で更新します。
1. [保守者用 materializer](../../README.md#source-and-artifact-boundary) で adapter を更新し、正本と一緒に commit します。利用時には生成しません。
1. routing に影響する場合は [CODEX_WORKFLOW](../canonical/CODEX_WORKFLOW.md) と [CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md) の該当箇所を更新します。
