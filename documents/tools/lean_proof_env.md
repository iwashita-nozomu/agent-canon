<!--
@dependency-start
responsibility Documents lean_proof_env.py operator usage and environment boundary.
upstream implementation ../../tools/agent_tools/lean_proof_env.py creates Mathlib/Aesop proof environments.
upstream design ../../agents/skills/formal-proof-workflow.md routes Lean proofs through checked environments.
upstream design lean_capability_matrix.md documents Lean/Mathlib/Aesop tactic and environment selection.
downstream implementation ../../tests/agent_tools/test_lean_proof_env.py tests generated files and dry-run commands.
@dependency-end
-->

# lean_proof_env.py

`lean_proof_env.py` creates a reusable Lean 4 Lake package for exploratory or
fallback formal-proof checks that need Mathlib and Aesop. It is AgentCanon proof
tooling, not a project theorem package. Active proof themes should own their
theory dependencies in their topic-local Lake package when those dependencies
are part of the durable theorem surface; this tool remains the shared smoke
check and generated-stub checker.

Use [lean_capability_matrix.md](lean_capability_matrix.md) before deciding
whether a proof attempt belongs in a topic-local package or in this reusable
environment.

Initialize the environment without executing Lake:

```bash
python3 tools/agent_tools/lean_proof_env.py init \
  --env-dir reports/formal-proof/lean-proof-env
```

Smoke-check Mathlib and Aesop when network/cache access is available:

```bash
python3 tools/agent_tools/lean_proof_env.py smoke \
  --env-dir reports/formal-proof/lean-proof-env \
  --execute
```

Check a generated Lean proof stub through the same environment:

```bash
python3 tools/agent_tools/lean_proof_env.py check-file \
  --env-dir reports/formal-proof/lean-proof-env \
  --lean-file reports/formal-proof/example/example.lean \
  --execute
```

The tool writes:

- `lean-toolchain`
- `lakefile.lean`
- `AgentCanonLeanProofEnv.lean`
- `AgentCanonLeanProofEnvSmoke.lean` for `smoke`

By default it pins `leanprover/lean4:v4.30.0` and Mathlib `v4.30.0`, matching
the current Lean toolchain used by the proof artifacts. Use `--lean-toolchain`
and `--mathlib-rev` together when updating the proof environment. Do not add
Mathlib/Aesop ad hoc for a single throwaway proof attempt; either use this
reusable environment, or make the topic-local package explicitly own the
Mathlib/Aesop dependency as part of its checked theorem surface.

`--execute` runs `lake update` and then `lake env lean ...` in the generated
environment. Without `--execute`, the tool is a deterministic setup dry run and
prints the exact commands to run later.
