# task-routing
<!--
@dependency-start
responsibility Documents task-routing skill.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/tool-skill-routing-refactor.md short tool and skill naming policy
downstream implementation ../../tools/agent_tools/route.py selects short routing areas
@dependency-end
-->

## Purpose

短い tool / skill 名で、task に必要な profile、check、runtime、closeout、
AgentCanon update、docs、log/eval の経路を選びます。

## Use When

- 候補 tool 名や skill 名が長く、どれを使うべきか迷う。
- `template_agent_canon_tool_skillization_500_candidates.md` 系の提案を実装へ落とす。
- workflow 本文を読む前に、最小 check や runtime profile を機械的に決めたい。

## Standard Command

```bash
python3 tools/agent_tools/route.py --area checks --changed <path>
python3 tools/agent_tools/route.py --name profile_surface_resolver.py
```

## Outputs

- `ROUTE`
- `AREA`
- `NEXT_ACTION`
- `COMMANDS`
- `EVIDENCE`

Long candidate names are aliases. Do not create a new public tool or skill
until `route.py --name <candidate>` returns `STATUS=unknown` and the missing
route is genuinely reusable.
