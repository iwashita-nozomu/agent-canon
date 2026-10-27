# Shared Skill Canon

<!--
@dependency-start
contract skill
responsibility Indexes public skills and owns AgentCanon-specific skill maintenance.
upstream design ../../documents/design/responsibility-rationale.md skill procedure derivation contract
upstream design ./catalog.yaml enumerates public skill families
upstream design ./skill-dependencies.yaml owns the typed public-skill dependency dictionary
upstream design ../../documents/design/responsibility-cleanup.md skill maintenance delegation rationale
downstream design ../canonical/CODEX_WORKFLOW.md consumes the shared skill canon during task routing
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates public and official skill boundaries
upstream design code-visualization.md visualization selection and native renderer delegation
downstream implementation ../../tools/agent/skills/skill_route_catalog.py validates public skill routing
downstream implementation ../../tools/agent/skills/skill_dependency_map.py validates the dependency dictionary and generates its Mermaid projection
@dependency-end
-->

このディレクトリは public Codex skill 文書の人間向け正本です。

## Reader Map

作成・公開範囲は [Rules](#rules) と [Skill Visibility Naming](#skill-visibility-naming)、
選択は [Task Skill Sets](#task-skill-sets) と [Codex Defaults](#codex-defaults)、正本の変更は [Updating Skills](#updating-skills) を参照します。
外部配布物の導入・更新は [External Skill Installation And Updates](#external-skill-installation-and-updates) を参照します。
各 skill の長い手順はその正本文書が所有し、この索引や [AGENTS.md](../../AGENTS.md) へ複製しません。
以下のリンクは必要時の参照先であり、全項目の起動・読了を要求する一覧ではありません。

## Visualization Ownership

[`code-visualization`](code-visualization.md) selects the visualization family,
source evidence owner, renderer, and final artifact checks. Visualization-
producing skills retain native source-fact and renderer responsibilities; the
public catalog does not impose a private intermediate representation or a
second omission/granularity policy.

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

## Skill Authoring

Use the host [$skill-creator](#official-system-skill-delegation) for general
instruction design. Keep shared procedures at their existing owner and let
callers add their local conditions, inputs, and acceptance. AgentCanon-specific
source and registration changes use [Updating Skills](#updating-skills).

## Skill Visibility Naming

| 所有者・用途 | 正本と公開方法 |
| --- | --- |
| AgentCanon public skill | plain hyphen-case。公開にはcanonical docと `catalog.yaml` の登録を使う。 |
| runtime-internal shim | 先頭 underscore。呼出元workflow / role / public skillが所有し、public catalogには登録しない。 |
| workflow-only routine | workflow内の手順であり、Codex discoveryが必要でなければ独立Skillにしない。 |
| parent repository 固有 skill | 公開・配置はparentまたはsubtree ownerが決める。 |

source / adapter / installed / repository-owned のpathと、選択済みSkillの読取は
[Skill Paths](../canonical/skills.md#skill-paths) が所有します。publicへの追加・昇格は
[Updating Skills](#updating-skills) の同一変更で行います。

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

次は既存 owner の確認入口です。検査を一律に実行するチェックリストではありません。

| 目的 | 入口 |
| --- | --- |
| public skill / shim / doc / config の整合 | `python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py` |
| prompt に対する skill 選択 | `python3 tools/agent/orchestration/route.py --prompt "<user request>" --mode routing-only --format json` |
| 選択した tool の実行 | 既存 CLI / API / script を native argv で呼び、実行と検証は各 owner に委譲します。 |
| 依存辞書の静的検査 | `python3 tools/agent/skills/skill_dependency_map.py check --root .` |
| 外部 graph 生成 | `python3 tools/agent/skills/skill_dependency_map.py graph --root . --runtime-root <external-runtime-root>` |
| tracked reader pair の明示更新 | `python3 tools/agent/skills/skill_dependency_map.py graph --root . --output documents/runtime/skill-dependency-graph.md --runtime-root <external-runtime-root> --source-mutation-capability-json <exact-two-path-capability.json>` |

## Internal Review And Runtime Routines

docs completeness / consistency、notation、logic gap、citation/evidence、critical/report、research perspective review は、
public skill ではなく workflow が必要時に要求する review pass です。artifact placement、CLI adapter、static validation は
`agents/internal-routines/`、`agents/canonical/`、[REVIEW_PROCESS](../../documents/conventions/REVIEW_PROCESS.md) に置きます。
一覧と route は [internal-routines/README.md](../internal-routines/README.md) が所有します。
carry-over は `documents/notes/` と worktree log を正本とし、独立 public skill を追加しません。

## Official System Skill Delegation

The host provides `$skill-creator`, `$skill-installer`, `$openai-docs`, and
`$imagegen` as the built-in base for this skill set. Their availability is an
assumption, not a per-task installation or discovery step. Select only the
capability needed by the request and use its registered entry directly.
AgentCanon adds the local contract that the built-in does not own.
`$plugin-creator` is an additional host capability only when registered; it is
not part of this assumed base. Provider procedures stay with their owners.

<a id="installed-external-skill-handoffs"></a>

## Task Skill Sets

Choose the smallest applicable composition once from the requested outcome.
Reuse the selected owners, available definitions, and task facts while they
remain valid. A set describes how responsibilities compose; it does not activate
every member or create another routing state. External members are selected
from the active registry when their condition applies.

| Requested outcome | Primary skill and AgentCanon additions | Conditional members and result boundary |
| --- | --- | --- |
| Create or revise a Skill | Built-in `$skill-creator` owns generic authoring. Use [Updating Skills](#updating-skills) for AgentCanon source/distribution changes. | Local formatting, generated adapter and owner checks follow the changed contract; generic instruction design is not repeated here. |
| Install or update an external Skill | Built-in `$skill-installer` owns acquisition and destination behavior. | Apply [the update-choice policy](#external-skill-installation-and-updates) for existing different content; return the actual installed/discovered result. |
| OpenAI/Codex guidance | Built-in `$openai-docs` owns official product, API and model guidance. | Add the project source owner only for local behavior or implementation; reuse known project facts. |
| Repository implementation or repair | The existing project owner and selected [repository workflow](codex-task-workflow.md) carry the local change. | Add only checks, language/type/design owners, or dependency work required by changed guarantees. A built-in is selected only for a capability it owns. |
| MCP server implementation | The project owner supplies the agreed API surface, language, transport and acceptance. | Registered `$mcp-builder` owns MCP-specific design and implementation; return server source and actual validation to the project owner. |
| UI or website | `$frontend-design` supplies a new visual direction/UI artifact from the audience, brief and project references; the project/UI or [`html-output`](html-output.md) owner integrates it and accepts the result. | Built-in `$imagegen` receives selected bitmap brief/reference and returns a raster asset for placement. `$sites:sites` owns matching website/Site/hosting work with project/deployment constraints; save-only or publication follows that provider. Selected repository-file and standalone-HTML work retains its owner. |
| Browser interaction checks | The project test/UI owner supplies the artifact or running URL and expected behavior. | Registered `$webapp-testing` owns browser interactions; return observed assertions, screenshots and console findings. Server lifecycle stays with the environment/preview owner. |
| Report or prose | Select the relevant writing owner, such as [report](report-writing.md), [long-form](long-form-writing.md), or [paper](paper-writing.md). Reuse sufficient structure; create missing structure before prose, even when order is obvious, through [Before prose](structure-planning.md#before-prose). | Explicitly named Yomiyasu or explicit Skill-based Japanese polishing adds `$yomiyasu:yomiyasu`: selected prose and constraints in, revised prose back for meaning/evidence acceptance. Requested native Docs adds `$google-drive:google-drive` → `$google-drive:google-docs`, using the known target or discovering it when unknown; return the verified native Doc result. |
| Presentation | [`slides`](slides.md) owns the narrative and local new-PPTX authoring. | An existing native Slides/reference deck adds `$google-drive:google-drive` → `$google-drive:google-slides`; pass the known deck/content constraints and return the native edit result. Requested theme work adds registered `$theme-factory`: supplied theme choice and deck/template constraints in, palette/font choices back. Built-in `$imagegen` is added for selected raster assets. |
| Literature and source discovery | [`literature-survey`](literature-survey.md) owns claim evaluation, contrary evidence and citation records. | `$imozuru` performs selected link-trail discovery through unfamiliar terms/people/venues/originals; topic/claims in, source map and raw-source locators back. Reuse those locators rather than a second source store. |
| Diagram or visual explanation | [`code-visualization`](code-visualization.md) selects source facts and an existing renderer; scientific figures keep standard plotting. | Requested Nessa browser maps add `$nessa-docs`: reviewed source scope/reader goal in, `docs/state` pages with per-page checkpoints and check results back. In-conversation exploration adds `$visualize:visualize`; exported figures keep their output owner. Bitmap generation/editing uses built-in `$imagegen`. |

Use an already-known provider directly when its task boundary is resolved;
this table is a selection aid, not an extra read or validation before every
provider call. Keep caller-specific input, source/evidence and acceptance with
their owner. Native APIs, permissions and operation completion belong to the
selected provider. An actual missing required capability remains an explicit
limit; it does not select installation or a substitute implicitly.

## External Skill Installation And Updates

利用するCodexで、導入するSkill名または配布元URLを `$skill-installer` へ渡します。
候補を探す場合は同じSkillへ一覧を依頼します。

```text
$skill-installer <Skill名または配布元URL> を、このCodex環境へ導入して。
```

取得・導入先の解決はinstallerに委譲し、版指定がなければ配布元の既定・最新経路を使います。
配布元の必要な同梱物も、同じ取得revisionから保全します。

導入済みの同一内容は保持します。更新時は差分とlocal変更への影響を示し、置換前にユーザーへ確認します。
回答までは既存内容を使います。local変更を保全し、承認した内容と一致するものを適用します。

対象Codexで導入物の登録名と有効状態を確認し、出典・取得revision・導入先・結果を既存taskに残して完了とします。
AgentCanon自身のsource・生成adapterの変更は [Updating Skills](#updating-skills) で扱います。

### OfficeCLI

[配布元Skill](https://github.com/iOfficeAI/OfficeCLI/tree/main/skills/officecli) は、
上記の `$skill-installer` で対象Codexへ導入します。
本体は共有imageの [依存manifest](../../bootstrap/container/image/dependencies.toml) が管理し、
配置と `officecli --version` の実行を検証します。
共有runtimeでの呼び出しは [既存のexec経路](agent-canon-bootstrap.md#command-shape) を使います。

共有imageは `OFFICECLI_NO_AUTO_INSTALL=1` と `OFFICECLI_SKIP_UPDATE=1` を設定します。
既存host CLIを使う場合も、この2変数を呼出しに適用します。
Skill配置やMCP登録を行う `officecli install` / `officecli skills install` は、
対象Codexのinstaller管理と競合するため使いません。
専門Skillは必要時に配布元の `officecli load_skill` で読みます。
根拠は配布元の [Installer](https://github.com/iOfficeAI/OfficeCLI/blob/v1.0.158/src/officecli/Core/Installer.cs) と
[更新仕様](https://github.com/iOfficeAI/OfficeCLI/tree/v1.0.158#installation) にあります。

PowerPointコメントは [slides](slides.md#powerpoint-comments) の手順を使います。
対象CodexでのSkill検出と、CLIでの文書操作をそれぞれ確認します。

## Codex Defaults

When a repository task has no selected workflow or owner, start with
[agent-orchestration](agent-orchestration.md) and the current task catalog.
Reuse settled context and follow the selected owner's procedure. A related
Skill is added only when its capability is needed for this request. Repository
changes use [codex-task-workflow](codex-task-workflow.md); add
[subagent-bootstrap](subagent-bootstrap.md) only when delegation is selected.
For host-runtime policy, see [CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md).

## Updating Skills

Use this route when changing AgentCanon's skill source, registration, or
distribution. Keep the reusable method with its owner; take concrete goals,
inputs, paths, execution conditions and acceptance from the current task.

### Improvement cycle

Adapt the relevant stages to the task's goal, inputs, constraints, and evidence
before a substantive procedure change or delegation. Put a task-specific
sequence in the existing task or handoff when batching, delegation,
interruption, or resumption needs one; a bounded same-writer edit can use the
applicable steps in place.

1. Establish the requested outcome, any observed problem or preference, the
   current Skill contract, and its owner. Reuse valid source and results; do not
   infer a gap from wording alone.
2. Use [procedure derivation](../../documents/design/responsibility-rationale.md#skill-procedure-derivation)
   to select the operations, decisions, and observable results needed for the
   requested guarantee. For a mandatory instruction under review, identify the
   request, invariant, reachable failure, or decision it serves and whether an
   existing owner already supplies that result. Preserve authority, safety, and
   accepted behavior; remove unsupported or duplicate work, or make
   context-specific work conditional. This keeps required guarantees while
   reducing steps that add no needed evidence or protection. Resolve material
   scope or approach choices through the existing decision owner.
3. Keep work with the current agent by default. Use
   [delegation selection](agent-orchestration.md#delegation-selection) when a
   separate judgment or bounded task has a concrete benefit. When a child is
   selected, pass the adapted workflow, source binding, bounded write paths,
   current evidence, and validation route through [subagent-bootstrap](subagent-bootstrap.md).
4. Improve the owning procedure and its rationale together. If actual work
   reveals a missing step, an unnecessary mandate, or a branch that is too broad,
   update the task sequence before continuing. Amend this reusable cycle only
   when the lesson applies to other Skill changes; keep case-specific inputs in
   the task. Return repairs to a compatible active writer and ask before
   expanding the agreed outcome or authority.
5. Run checks selected for changed guarantees, format changed Markdown, and
   refresh affected generated views through their owner. Use
   [empirical-prompt-tuning](empirical-prompt-tuning.md) when a behavior question
   needs fresh observations. Reuse valid checks whose inputs and contracts have
   not changed; source consistency does not establish changed behavior.
6. Compare the result with the whole requested outcome. In the final user-facing
   [completion report](../internal-routines/verification-result-structuring.md#completion-reports),
   use facts from the existing task record to include material attempts,
   acceptance or rejection grounds, validation limits, and workflow corrections.
   Continue authorized repairs until acceptance is established, or return a
   concrete unresolved boundary.

Update the canonical document and only the catalog, dependency, caller, or
adapter surfaces affected by the change. The catalog owns public identity and
routing metadata; generated discovery views are updated by the maintainer's
[materializer](../../README.md#source-and-artifact-boundary), never by skill
use. Keep design rationale with its existing owner. Format changed Markdown
with [md-style-check](md-style-check.md); select additional checks only when the
changed surface requires them.
