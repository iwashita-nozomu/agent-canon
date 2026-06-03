---
name: formal-proof-workflow
description: Use when natural-language mathematical claims, Python AST-derived implementation claims, proof sketches, or theory assumptions should be converted into formal-proof obligations, existing-proof search packets, proof-assistant stubs, and checker-gated evidence.
---
<!--
@dependency-start
responsibility Exposes formal-proof-workflow to Codex/Copilot skill discovery.
upstream design ../../../agents/skills/formal-proof-workflow.md canonical skill document
upstream implementation ../../../tools/agent_tools/formal_proof.py builds proof scaffold artifacts
upstream design ../../../agents/skills/literature-survey.md source search policy
@dependency-end
-->

# Formal Proof Workflow

1. Read `agents/skills/formal-proof-workflow.md`.
1. Read `agents/skills/literature-survey.md` before web or paper search.
1. Split the natural-language claim into assumptions, definitions, target theorem, proof sketch, and proof obligations; for implementation-derived claims, use `--python-symbol path.py::qualname` to extract side-effect-free AST provenance first.
1. Run `python3 tools/agent_tools/formal_proof.py` to generate the proof plan, target-language scaffold, existing-proof queries, and literature queries.
1. Search local repo sources, `references/`, `notes/`, and `documents/` before external web search.
1. Search existing formal proofs in the target ecosystem before creating new lemmas. For Lean/mathlib include docs, LeanSearch/Loogle/Moogle-style tools, Zulip archive, and in-editor tactic search when available. For Isabelle include AFP and Sledgehammer reconstruction evidence. For Coq/Rocq include library search and CoqHammer-related routes.
1. Use `$literature-survey` for external papers, official docs, source packets, adoption/exclusion reasons, and contrary or narrowing evidence.
1. Do not mark a claim verified unless the target proof assistant or solver checks the exact artifact without placeholders, `sorry`, `Admitted`, unchecked axioms, or equivalent proof escape hatches.
1. When a checked fragment is adopted, register it in the package-retained proof trace with consumed fragments, checker command, and any remaining implementation-instantiation obligations instead of hiding those boundaries in prose.
1. If the checker cannot be run, record `proof_status=not_run`, the exact command, and the missing environment or dependency.
