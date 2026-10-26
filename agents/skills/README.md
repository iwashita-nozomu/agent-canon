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
選択は [Codex Defaults](#codex-defaults)、正本の変更は [Updating Skills](#updating-skills) を参照します。
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

OpenAI system skill の本文は host runtime が提供します。AgentCanon は routing trigger、local evidence、repo 固有契約だけを持ちます。

| Official System Skill | AgentCanon Route |
| --- | --- |
| `$openai-docs` | Current OpenAI / Codex product docs, model guidance, API reference, and Codex manual source route. |
| `$skill-creator` | Direct owner for general skill creation, refactoring, and instruction quality; AgentCanon source changes also use [Updating Skills](#updating-skills). |
| `$skill-installer` | External skill installation and curated skill listing; follow [the local install/update route](#external-skill-installation-and-updates). |
| `$imagegen` | Pass a bitmap brief and, when relevant, a visible reference image; it returns a raster artifact for the selected consumer to place and validate. Vector diagrams, code-native visuals, and scientific plots keep their existing owners. |
| `$plugin-creator` | Codex plugin scaffold, manifest defaults, marketplace entries, and plugin reinstall flow. |

## Installed External Skill Handoffs

The host Skill registry and each installed provider own their names, availability,
and operating procedures, as defined by
[Skill procedure derivation](../../documents/design/responsibility-rationale.md#skill-procedure-derivation).
Use a handoff only when its request condition applies;
pass the relevant task input and return the provider's result to the AgentCanon
owner that retains the local content, source facts, and acceptance contract.

| Provider | Select when | AgentCanon handoff and returned result |
| --- | --- | --- |
| `$frontend-design` | A new or substantially restyled user interface is in scope. | Provide the audience, UI goal, brief, applicable constraints, and existing design references when supplied; receive a design direction and UI artifact. `html-output` or the project UI owner integrates it and checks accessibility and acceptance. |
| `$nessa-docs` | A browsable system map or high-level statechart for the Nessa Docs browser is requested. | Provide the reviewed source boundary and reader goal; receive `docs/state` pages with their source checkpoint and check result. `code-visualization` selects the source facts. |
| `$imozuru` | The user requests chain research, or a selected research question needs a trail through unfamiliar terms, people, venues, and original sources. | Provide the topic and claims; receive a map and raw-source locators in its research area. `literature-survey` evaluates those sources and owns AgentCanon claim/citation records. |
| `$yomiyasu:yomiyasu` | The user names Yomiyasu or explicitly requests Japanese polishing with that Skill. | Provide the approved prose and constraints; receive revised prose. The selected writing owner checks that claims, source meaning, and requirements remain intact; Japanese text alone does not select this handoff. |
| `$google-drive:google-drive` → `$google-drive:google-docs` | Native Google Docs creation or editing is requested. | Use Drive to ground the target (discover it only when unknown), then Docs for the document operation; receive the provider's verified native Doc result. The selected AgentCanon writing owner retains claims, structure, and evidence. |
| `$google-drive:google-drive` → `$google-drive:google-slides` | An existing native Slides deck or reference deck is part of the requested edit. | Use Drive to ground the deck (discover it only when unknown), then Slides for the native edit; receive the updated native deck. [`slides`](slides.md) retains the narrative and source evidence; new PPTX decks stay with its local authoring route. |
| `$visualize:visualize` | An in-conversation interactive visual materially helps explain or explore a question. | Provide the question and selected evidence; receive an inline visual. The source owner retains factual correctness; use existing renderers for exported diagrams and standard plotting for static scientific figures. |
| `$sites:sites` | A requested website build, existing Sites edit, or hosting task matches the provider. | Pass the site brief or target and existing-project/deployment conditions; receive a saved result or deployed URL. Sites handles local-only versus deployment. Repository-file edits and standalone HTML stay with their current owners. |

The mapping does not register external providers in the public catalog or grant
authority for an external write. Follow the active provider's procedure when it
is selected and keep AgentCanon-owned evidence and acceptance with their current
owners.

## External Skill Installation And Updates

外部配布Skillの一覧・導入は、host の `$skill-installer` と現行helperに委譲します。
取得方式・導入先はその標準に従い、ユーザーの版指定がなければ配布元の既定・最新経路を使います。

既存Skillの更新では、導入済み内容と候補の差分、local変更への影響を示し、置換前にユーザーへ確認します。
回答までは既存内容を使います。local変更を保全し、承認した内容と一致するものを適用します。

出典・取得revision・実際の結果は既存taskに残し、導入物がruntimeに検出されることを確かめます。
AgentCanonの管理source・生成adapterは、この節の外部導入先と分けて既存の保守経路で扱います。

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
distribution. Before changing a procedure, use
[Skill procedure derivation](../../documents/design/responsibility-rationale.md#skill-procedure-derivation)
to map the applicable rule to necessary operations, decisions, observable
results, and reasons, and assess existing requirements as well as new steps.
Preserve the skill's reusable method; use the caller's current
request and governing owner for concrete goals, inputs, paths, environment,
validation, and output. Keep extra capabilities conditional, and retain native
CLI/API behavior instead of introducing a wrapper or mandatory context packet.
Prefer an existing capability identified in that context when it meets the
requested guarantee; extend it only to close a concrete gap. Compare functional
responsibility and contract, not names or paths alone.

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
