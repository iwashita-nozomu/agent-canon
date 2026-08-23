<!--
@dependency-start
contract reference
responsibility Documents lean_recursive_proof_search.py operator usage.
upstream implementation ../../tools/agent_tools/lean_recursive_proof_search.py runs target-driven Lean proof attempts.
upstream design lean_capability_matrix.md routes Lean tactics and theorem search features.
upstream design ../../agents/skills/formal-proof-workflow.md defines recursive target-driven proof search.
@dependency-end
-->

# lean_recursive_proof_search.py

`lean_recursive_proof_search.py` runs a JSON list of Lean proof targets and
records whether each tactic attempt verifies, leaves structured unresolved
goals, or fails without a parseable next-goal frontier. It is a proof-search
evidence tool, not theorem authority: only a checked Lean file without proof
escapes closes a proof obligation.

Use it with a topic-local Lake package or a generated Lean proof environment:

```bash
python3 tools/agent_tools/lean_recursive_proof_search.py \
  --config lean/<topic>/proof_search_targets.json \
  --format markdown \
  --out lean/<topic>/recursive_proof_search.md
```

The config is a JSON object. Top-level fields may include `imports`, `opens`,
`options`, `prelude`, `cwd`, `command`, and `target_theorem`. Each `targets`
entry needs `name` and `statement`; optional fields include `binders`, `setup`,
`tactic`, and `next_targets`.

The default command is `lake env lean --stdin` in the config directory. Override
`command` only when the proof theme owns that execution surface. Output formats
are `text`, `markdown`, and `json`; nonzero Lean return codes make the command
return nonzero so CI and run bundles do not silently treat unresolved goals as
verified proofs.
