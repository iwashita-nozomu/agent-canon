---
name: lean-algorithm-design
description: Use when an algorithm should be designed and checked in Lean before production implementation; models candidate algorithms independently of existing code paths, proves or refutes convergence, stopping, certificate, filter/restoration, and inner-solver contracts, then hands a checked design contract to implementation or implementation-derived proof workflows.
---
<!--
@dependency-start
contract skill
responsibility Exposes Lean-first algorithm design to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/lean-algorithm-design.md canonical skill document
upstream design ../../../agents/skills/formal-proof-workflow.md terminal checker-backed proof workflow
upstream design ../../../agents/skills/algorithm-proof-exploration.md implementation-derived proof exploration
upstream design ../../../agents/skills/computational-optimization.md numerical optimization contract
@dependency-end
-->

# Lean Algorithm Design

1. Read `agents/skills/lean-algorithm-design.md`.
1. Use this skill when the algorithm should be designed in Lean before
   production implementation, or when an implementation proof attempt needs a
   clean mathematical algorithm model independent of current code.
1. Pair with `$computational-optimization` for numerical optimization contracts,
   `$formal-proof-workflow` for terminal proof adoption/refutation, and
   `$algorithm-proof-exploration` only after a production entrypoint exists and
   the checked Lean design is being mapped to code.
1. Fix the design target before writing Lean: problem family, allowed
   assumptions, state, transition map, stopping/certificate predicate, result
   classification semantics, and inner-solver contract.
1. Create or update a fresh Lean design namespace under `lean/<topic>/`. Do not
   import generated implementation evidence unless the task explicitly asks to
   compare the design with existing code.
1. Encode candidate algorithms as Lean definitions: problem structure, state,
   transition relation/function, acceptance/restoration predicates, inner-solver
   contracts, and returned certificate predicates.
1. State the target theorem over the Lean design API. For iterative algorithms,
   consume the transition map and stopping scalar/certificate predicate; do not
   start from production helper names.
1. Use Mathlib, Aesop, theorem search, SMT/counterexample tools, and existing
   local Lean libraries where they fit. Do not build a private proof framework
   when standard Lean libraries cover the reasoning.
1. If a design theorem fails, classify the checked reason as algorithm too weak,
   assumptions too weak, theorem too strong, inner-solver contract insufficient,
   or Lean model missing a required algorithm component. Iterate on the Lean
   design before touching production code.
1. Return to implementation only with an `implementation_handoff` that lists the
   checked Lean definitions/theorems, `lake build` command, production API
   fields required by the theorem, forbidden proof-only runtime fields, and the
   later implementation-derived proof route.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill lean-algorithm-design --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

## Completion Gate

- A design task is complete only when the Lean design target is checked,
  checker-refuted, or restricted to a checked problem class.
- A missing lemma, open frontier, or unchecked algorithm idea is not completion.
- A production implementation may start only after the checked design handoff
  exists.
