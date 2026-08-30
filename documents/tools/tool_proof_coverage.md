<!--
@dependency-start
contract reference
responsibility Documents the tool proof coverage checker.
upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog.
upstream design lean_capability_matrix.md Lean capability routing policy.
upstream design ../../agents/skills/formal-proof-workflow.md formal proof status policy.
upstream implementation ../../tools/analysis/proof/tool_proof_coverage.py reports proof coverage.
downstream implementation ../../tests/agent_tools/test_tool_proof_coverage.py tests checker behavior.
@dependency-end
-->

# Tool Proof Coverage

`tools/analysis/proof/tool_proof_coverage.py` reports formal proof-obligation
coverage for catalog entries selected by the caller. Without a selection it is
an observational report; it does not create a universal Lean backlog.

The checker does not prove that tools are correct. It prevents the stronger
mistake: claiming Lean verification when the catalog only has tests, docs, or
external runtime assumptions.

## Contract

For each cataloged tool, the checker emits:

- intended-behavior proof status;
- performance proof status;
- performance model shape;
- the next witness needed before the claim can become Lean verified.

By default the checker passes when catalog rows can be classified. A workflow
that genuinely needs a proof selects the exact tool IDs and enables strict
mode:

```bash
python3 tools/analysis/proof/tool_proof_coverage.py \
  --tool-id check-dependency-headers \
  --require-lean-verified
```

Strict mode without `--tool-id` fails with a typed selection error. Missing or
unavailable proof evidence remains a failure for the selected tool; it is not
reported as pass or deferred success.

## Verified Proof Metadata

A catalog entry may declare a checked Lean proof using a `proofs` block:

```yaml
proofs:
  behavior:
    status: lean_verified
    theorem: ToolBehavior
    artifact: proofs/tool_behavior.lean
    checker: lake env lean proofs/tool_behavior.lean
    checked: true
```

`lean_verified` requires a theorem name, proof artifact, checker command, and
`checked: true`. The proof artifact must not contain proof escape hatches such
as `sorry`, `admit`, or unchecked `axiom`.

## Output

```bash
python3 tools/analysis/proof/tool_proof_coverage.py
python3 tools/analysis/proof/tool_proof_coverage.py --format markdown
python3 tools/analysis/proof/tool_proof_coverage.py --format json
python3 tools/analysis/proof/tool_proof_coverage.py --tool-id <catalog-id> --require-lean-verified
```

The compact text output includes counts such as:

- `TOOL_PROOF_COVERAGE_TOOLS`;
- `TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED`;
- `TOOL_PROOF_COVERAGE_PERFORMANCE_LEAN_VERIFIED`;
- `TOOL_PROOF_COVERAGE_FINDINGS`;
- `TOOL_PROOF_COVERAGE`.

This keeps proof coverage separate from ordinary test evidence. Tests can show
observed behavior; Lean proof status is only upgraded when checker-backed proof
artifacts exist.
