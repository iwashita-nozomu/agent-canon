<!--
@dependency-start
contract reference
responsibility Documents lean_proof_env.py operator usage and environment boundary.
upstream implementation ../../tools/analysis/proof/lean_proof_env.py creates Lean proof-search, theorem-search, and counterexample environments.
upstream design ../../agents/skills/formal-proof-workflow.md routes Lean proofs through checked environments.
upstream design lean_capability_matrix.md documents Lean/Mathlib/Aesop tactic and environment selection.
downstream implementation ../../tests/agent_tools/test_lean_proof_env.py tests generated files and dry-run commands.
@dependency-end
-->

# lean_proof_env.py

`lean_proof_env.py` creates a reusable Lean 4 Lake package for exploratory or
fallback formal-proof checks that need Mathlib, Aesop, Plausible, and
LeanSearchClient. It is AgentCanon proof tooling, not a project theorem
package. Active proof themes should own their theory dependencies in their
topic-local Lake package when those dependencies are part of the durable theorem
surface; this tool remains the shared smoke check, counterexample probe, agent
interface probe, and generated-stub checker.

Use [lean_capability_matrix.md](lean_capability_matrix.md) to select proof
features. The helper owns its generated package defaults; installed toolchains
are declared in `.devcontainer/dependencies.toml`.

## Reader Map

- Owns the operator usage and environment boundary for `lean_proof_env.py`.
- Main path: the opening description defines the reusable Lean environment,
  followed by setup assumptions, command usage, generated files, and boundary
  notes.
- Read this before creating a reusable Lean proof-search or smoke-check
  environment.
- Boundary: durable theorem dependencies for an active proof theme belong in
  that topic's own Lake package.

Initialize the environment without executing Lake.  The environment directory
is runtime state and must be below the explicit external AgentCanon runtime
root; a checkout-local `reports/` or package directory is not a valid target.

```bash
RUNTIME_ROOT=/abs/path/to/external/agent-canon-runtime/<run>
python3 tools/analysis/proof/lean_proof_env.py init \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env"
```

Smoke-check local proof-search tactics when network/cache access is available:

```bash
python3 tools/analysis/proof/lean_proof_env.py smoke \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --execute
```

Smoke-check agent-facing theorem-search imports without making a live external
search request:

```bash
python3 tools/analysis/proof/lean_proof_env.py agent-smoke \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --execute
```

Smoke-check counterexample discovery. This action intentionally runs a false
property; it succeeds only when Plausible finds a concrete counterexample:

```bash
python3 tools/analysis/proof/lean_proof_env.py counterexample-smoke \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --execute
```

Run all reusable proof-tooling checks:

```bash
python3 tools/analysis/proof/lean_proof_env.py all-smoke \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --execute
```

Check a generated Lean proof stub through the same environment:

```bash
python3 tools/analysis/proof/lean_proof_env.py check-file \
  --env-dir "$RUNTIME_ROOT/tasks/formal-proof/lean-proof-env" \
  --lean-file "$RUNTIME_ROOT/tasks/formal-proof/example/example.lean" \
  --execute
```

The tool writes:

- `lean-toolchain`
- `lakefile.lean`
- `AgentCanonLeanProofEnv.lean`
- `AgentCanonLeanProofEnvSmoke.lean` for `smoke`
- `AgentCanonLeanProofEnvAgent.lean` for `agent-smoke`
- `AgentCanonLeanProofEnvCounterexample.lean` for `counterexample-smoke`

`--execute` runs `lake update`, `lake build`, and then `lake env lean ...` in the
generated environment. Without `--execute`, the tool is a deterministic setup
dry run and prints the exact commands to run later. `counterexample-smoke` is
special: Lean returns a failing check when Plausible finds the intended
counterexample, and the helper normalizes that expected failure to a passing
tool result only when the counterexample marker is present.
