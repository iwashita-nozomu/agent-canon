<!--
@dependency-start
responsibility Indexes legacy OOP check support tools imported from jax_solver_util.
upstream design ../../../../documents/repo-local-tool-imports.md records canonical disposition and legacy import policy
downstream implementation restructure_code_review_skill.py legacy review-rule restructuring provenance
downstream implementation read_conventions.sh legacy convention listing provenance
downstream implementation view_conventions.sh legacy convention viewer provenance
@dependency-end
-->

# Legacy OOP Check Support

This directory keeps jax_solver_util scripts that influenced AgentCanon's OOP
readability and convention-checking workflow. They are provenance files, not
canonical workflow entrypoints. The shell helpers accept an optional repository
root argument and resolve either standalone AgentCanon `documents/conventions`
or a template parent `vendor/agent-canon/documents/conventions` path.

Canonical replacements:

- `tools/agent_tools/analyze_oop_readability.py`: mechanical Python / C++ OOP readability scoring.
- `tools/agent_tools/oop_rule_inventory.py`: OOP rule source and legacy support placement inventory.
- `documents/object-oriented-design.md`: human-readable OOP policy and machine-evaluation contract.
- `.codex/agents/oop_readability_reviewer.toml`: read-only reviewer for mechanical reports.

Do not call files in this directory from default CI, Docker smoke checks, or
workflow closeout. Promote specific behavior by rewriting it into a repo-neutral
tool with tests and dependency manifests.
