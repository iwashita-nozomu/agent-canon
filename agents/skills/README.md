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

Skills are reusable methods for callers with different goals, inputs, paths,
environments, and validation routes. State the useful method briefly and let
the current request and its governing owner supply those concrete bindings.
Make related Skills and native capabilities conditional on the question that
needs them. Preserve an existing CLI/API's inputs and result semantics; do not
make a context manifest or handoff packet a prerequisite unless an existing
owner requires it.

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
| `$skill-installer` | External skill installation and curated skill listing. |
| `$imagegen` | Bitmap visual asset generation for HTML, reports, dashboards, or visual mockups. |
| `$plugin-creator` | Codex plugin scaffold, manifest defaults, marketplace entries, and plugin reinstall flow. |

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
distribution. Preserve the skill's reusable method; use the caller's current
request and governing owner for concrete goals, inputs, paths, environment,
validation, and output. Keep extra capabilities conditional, and retain native
CLI/API behavior instead of introducing a wrapper or mandatory context packet.
Prefer an existing capability identified in that context when it meets the
requested guarantee; extend it only to close a concrete gap. Compare functional
responsibility and contract, not names or paths alone.

Update the canonical document and only the catalog, dependency, caller, or
adapter surfaces affected by the change. The catalog owns public identity and
routing metadata; generated discovery views are updated by the maintainer's
[materializer](../../README.md#source-and-artifact-boundary), never by skill
use. Keep design rationale with its existing owner. Format changed Markdown
with [md-style-check](md-style-check.md); select additional checks only when the
changed surface requires them.
