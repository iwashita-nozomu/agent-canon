---
name: oop-type-design
description: Use before implementation to define language-neutral OOP/type contracts, responsibility boundaries, and explicit capability-owned design packets.
---
<!--
@dependency-start
contract skill
responsibility Provides the runtime discovery shim for pre-implementation OOP/type design.
upstream design ../../../agents/canonical/skills.md public skill registry and visibility contract
upstream design ../../../agents/skills/oop-type-design.md canonical skill contract
downstream implementation ../../../.codex/config.toml runtime skill enablement
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py command packet checker
@dependency-end
-->

# oop-type-design

## Reader path

Select this skill only through the explicit capability `oop_type_design`:

```bash
python3 tools/agent_tools/route.py --capability oop_type_design
```

It owns `pre_implementation_oop_type_design` in phase
`pre_implementation_design`. Prompt keywords do not activate it. The
downstream `$oop-readability-check`, `$python-review`, and `$cpp-review` routes
remain separate consumers for later implementation evidence and review; they
are not this skill's owner.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill oop-type-design --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/oop-type-design.md`.
1. Invoke the explicit `oop_type_design` capability before implementation.
1. Produce one `agent_canon.oop_type_design_packet.v1` in the canonical order:
   scope, reuse survey, responsibility map, split ledger, type contract,
   invariant ledger, composition map, boundary matrix, static delegation,
   implementation trace, and open decisions.
1. Use the labeled dependency graph and constrained partition ledger. Preserve
   cohesive operations tied by shared invariants or atomic transitions; split
   independently changing/owned/verified/substitutable responsibilities only
   when indivisible edges and measured coordination cost allow it. Record each
   independent invariant and owner, including Protocol/interface, value-object,
   aggregate, constructor, state transition, and dependency direction facts.
   Prefer an immutable value object for validated values and keep its constructor
   or factory invariant explicit.
1. Keep composition roots limited to construction, wiring, and ordering. Delegate
   domain, policy, repository, adapter, lifecycle, and I/O responsibilities.
1. Delegate static/compiler/OOP/language/schema facts to existing owners. Do not
   add runtime or compiler-fact test duplication and do not use a test-first route.
   Statically decidable facts, static type checks, and static checker findings
   belong to those owners; runtime guards and runtime validation belong only at
   the relevant untrusted boundary.
1. Keep `$oop-readability-check`, `$python-review`, and `$cpp-review` as downstream
   implementation/review consumers, not automatic activation or design owners.
1. Keep T14 evaluator use fresh, read-only, eval-only, and parent-owned for raw
   bytes, scoring, convergence, and graph artifacts.
