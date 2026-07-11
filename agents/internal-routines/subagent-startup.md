# Subagent Startup Internal Routine

<!--
@dependency-start
contract agent-runtime
responsibility Documents the canonical private subagent startup route and internal startup handoff routing.
upstream design README.md internal routine registry
upstream design ../COMMUNICATION_PROTOCOL.md owns Fresh Subagent Context Capsule fields
downstream design ../skills/subagent-bootstrap.md consumes the canonical private subagent startup route
downstream implementation ../../tools/agent_tools/agent_team.py emits run.subagent_prompt_packet.subagent_startup_route
downstream implementation ../../tools/agent_tools/route.py strips private startup labels from prompt skill activation
downstream implementation ../../tests/agent_tools/test_route.py checks historical startup labels are not public aliases
downstream implementation ../../tests/agent_tools/test_task_start_and_close.py checks generated run manifest fields
@dependency-end
-->

## Reader Map

- Purpose: defines the private startup route used inside subagent handoff
  packets and generated run artifacts.
- Use When: a parent, stage owner, or `$subagent-bootstrap` prepares a fresh
  subagent handoff and needs to name the internal startup owner without creating
  a public skill.
- Section path: Contract defines route identity and non-goals; Handoff Use
  explains what to carry into generated artifacts and prompts.
- Boundary: this file is an internal routine. It is not a public Codex skill,
  not a catalog entry, and not a `.codex/config.toml` activation surface.

## Contract

The canonical internal startup route is:

```text
agents/internal-routines/subagent-startup.md
```

Historical startup labels such as `subagent-beginning`,
`_subagent-beginning`, `subagent-startup`, and `_subagent-startup` are not
public skills, are not accepted route aliases, and must not be added to
prompt-routing lists. The leading underscore marks old private/internal label
text, not a public skill namespace.

Public skills remain plain hyphen-case, catalog-backed, and discoverable through
`agents/skills/catalog.yaml` plus `.agents/skills/<skill>/SKILL.md`. Do not add
these historical startup labels to public `SKILLS`, `ACTIVE_SKILLS`,
`agents/skills/catalog.yaml`, `.codex/config.toml`, `route.py --name` aliases,
or public prompt-routing skill lists.

## Handoff Use

`$subagent-bootstrap` cites this routine when preparing startup handoffs. The
schema for the handoff stays in `agents/COMMUNICATION_PROTOCOL.md`; this
routine only names the internal startup route owner.

Generated run artifacts carry the route structurally under:

```text
run.subagent_prompt_packet.subagent_startup_route
```

Subagent prompts carry the field when it is present and keep it structural. Do
not convert the route path or historical startup labels into prompt keywords,
public skill activation, accepted route aliases, or a second capsule schema.
