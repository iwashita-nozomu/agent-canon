# task-routing
<!--
@dependency-start
contract skill
responsibility Documents task-routing skill.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/tool-skill-routing-refactor.md short tool and skill naming policy
upstream design ./agent-orchestration.md owns Decision Sufficiency policy and verdict validation
downstream implementation ../../tools/agent_tools/route.py selects short routing areas
downstream implementation ../../tools/agent_tools/agent_team.py materializes route ToolCall tokens
@dependency-end
-->

## Reader Map

- Purpose: chooses short AgentCanon tool, skill, profile, check, runtime,
  closeout, or evidence routes from long candidate lists.
- Use When: a prompt, changed area, or broad routing surface needs compact
  active/deferred skill selection or official system-skill delegation.
- Section path: Purpose and Use When define triggers; Standard Command gives
  the operational entrypoint; Outputs and Official System Skill Delegation
  describe route products.
- Boundary: this skill selects routes; the selected skills still own execution
  rules and validation.

## Purpose

短い tool / skill 名で、task に必要な profile、check、runtime、closeout、
AgentCanon update、docs、log/eval の経路を選びます。
prompt から public skill set を選ぶときは fast path の
`python3 tools/agent_tools/route.py --prompt` で `$agent-orchestration`
first の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` /
`RELATED_SKILL_CANDIDATES` を機械的に確認します。
`RELATED_SKILL_CANDIDATES` は次 stage で evidence が揃ったときに追加する
候補であり、初期 skill 読み込みには含めません。
skill が呼ばれない、呼び出しが遅い、関連 skill 候補が狭いという
runtime feedback では、prompt routing の結果を入口にし、観測 evidence は
`agent-log-analysis`、durable issue 候補は `issue-finding-report`、再発防止の
学習は `agent-learning` へ分けます。
公式 system skill で足りる task は、AgentCanon 側で別 skill を増やさず、
`$openai-docs`、`$skill-creator`、`$skill-installer`、`$imagegen`、
`$plugin-creator` へ route します。

## Use When

- 候補 tool 名や skill 名が長く、どれを使うべきか迷う。
- user prompt から repo-changing / routing-only と public skill set を確認したい。
- skill が呼ばれない、関連 skill が狭い、公式 skill へ移譲できるかなど、
  skill / tool routing の入口と後続候補を機械的に確認したい。
- `template_agent_canon_tool_skillization_500_candidates.md` 系の提案を実装へ落とす。
- workflow 本文を読む前に、変更 surface と risk に合う check や runtime profile を機械的に決めたい。

## Standard Command

Consume the semantic decision-sufficiency record before selecting a route. It
must identify the owner, replaceable unit, implementation mechanism, validation
route, and any unresolved branch that could change them. A handoff message or
tool result is sufficient; `run.decision_sufficiency.packet_ref` is used only
when coordination or resumption needs durable state. This skill forwards the
record and does not create a second sufficiency form or threshold policy.

Executable routing is supplied directly in
`run.repo_tool_routing_policy.*.tool_call_token` when a route operation is
selected. The canonical route token has
`tool_id=route`, an `agent-canon.route.args.v1` argument schema, typed
arguments, intent, and typed failure semantics. The selected-skill packet token
has `tool_id=skill-tool-commands` and
`agent-canon.skill-tool-commands.args.v1`. Do not reconstruct either token as a
prose shell command.

Model/profile policy and implementation capacity are not `route.py` policy.
Use the canonical model-profile/materializer and capacity-handshake owners for
those projections; `route.py` remains the public skill-route composer.

```bash
python3 tools/agent_tools/route.py --area checks --changed <path>
python3 tools/agent_tools/route.py --name profile_surface_resolver.py
python3 tools/agent_tools/route.py --prompt "<user request>" --format json
python3 tools/agent_tools/skill_tool_commands.py show --skill <skill> --format text
```

## Outputs

- `ROUTE`
- `AREA`
- `NEXT_ACTION`
- `COMMANDS`
- `EVIDENCE`
- `DECISION_SUFFICIENCY_PACKET_REF`
- owner-produced semantic sufficiency fields: `owner`, `replaceable_unit`,
  `implementation_mechanism`, `validation_route`, and `unresolved_branch`
- machine-readable `TOOL_CALL_TOKEN`
- prompt routing の場合は `MODE`, `SKILLS`, `ACTIVE_SKILLS`,
  `DEFERRED_SKILLS`, `MATCHED_SKILLS`, `RELATED_SKILL_CANDIDATES`,
  `RELATED_SKILLS`, `REASONS`

## Activation Boundary

Task-catalog roles, default review packs, and related-skill candidates are
candidate evidence, not automatic work. Activate an owner-critical skill before
its edit, artifact, PR, pin, or integration operation. Activate a reviewer only
when the selected validation or unresolved branch needs that review. Deferred
candidates do not create packets, waves, or follow-up work.

Long candidate names are aliases. Do not create a new public tool or skill
until `route.py --name <candidate>` returns `STATUS=unknown` and the missing
route is genuinely reusable.

Runtime route tokens are materialized by `agent_team.py` under
`run.repo_tool_routing_policy`. Related skill candidates remain dynamic
triggers; activation materializes a new token and retains the same owner DSV
verdict unless changed input creates a successor decision.

## Official System Skill Delegation

Task routing keeps official system skills as host-provided capabilities:

- OpenAI / Codex current product facts route to `$openai-docs`.
- Skill creation or skill-instruction refactor guidance routes to
  `$skill-creator` after the local AgentCanon owner surface is identified.
- External skill installation routes to `$skill-installer`.
- Bitmap image asset creation routes to `$imagegen`.
- Codex plugin scaffolding routes to `$plugin-creator`.
