# task-routing
<!--
@dependency-start
contract skill
responsibility Documents task-routing skill.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/tool-skill-routing-refactor.md short tool and skill naming policy
downstream implementation ../../tools/agent_tools/route.py selects short routing areas
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
- prompt routing の場合は `MODE`, `SKILLS`, `ACTIVE_SKILLS`,
  `DEFERRED_SKILLS`, `MATCHED_SKILLS`, `RELATED_SKILL_CANDIDATES`,
  `RELATED_SKILLS`, `REASONS`

Long candidate names are aliases. Do not create a new public tool or skill
until `route.py --name <candidate>` returns `STATUS=unknown` and the missing
route is genuinely reusable.

Runtime skill command packets are owned by `skill_tool_commands.py`. Use
`python3 tools/agent_tools/skill_tool_commands.py check` when changing
`.agents/skills/*/SKILL.md` files.
Run bootstrap surfaces publish the selected-skill command packets under
`run.repo_tool_routing_policy`. The sequential order is:
`show_skill_packet`, `required_commands`, `task_matching_conditional_commands`,
`validation_commands`. Related skill candidates remain dynamic triggers; when a
candidate becomes active, regenerate that skill's command packet with
`python3 tools/agent_tools/skill_tool_commands.py show --skill <skill> --format text`
before continuing the handoff.

## Official System Skill Delegation

Task routing keeps official system skills as host-provided capabilities:

- OpenAI / Codex current product facts route to `$openai-docs`.
- Skill creation or skill-instruction refactor guidance routes to
  `$skill-creator` after the local AgentCanon owner surface is identified.
- External skill installation routes to `$skill-installer`.
- Bitmap image asset creation routes to `$imagegen`.
- Codex plugin scaffolding routes to `$plugin-creator`.
