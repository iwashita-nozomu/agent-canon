<!--
@dependency-start
responsibility Indexes legacy scripts imported from jax_solver_util.
upstream design ../README.md explains legacy import policy
upstream design ../../../catalog.yaml records legacy provenance status
@dependency-end
-->

# Legacy Scripts

The files below are preserved for provenance only. Do not call them from
AgentCanon workflows, Docker smoke checks, or default CI until a promotion PR
generalizes and validates them.

The structured AgentCanon tool catalog groups this directory under
`legacy-jax-solver-util-scripts` with `callable_by_default: false`.

OOP / convention-check support provenance was moved to
`../oop_check_support/`. Canonical OOP checks live in
`tools/agent_tools/analyze_oop_readability.py` and
`tools/agent_tools/oop_rule_inventory.py`.
