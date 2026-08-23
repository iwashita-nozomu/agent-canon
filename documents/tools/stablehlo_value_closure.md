<!--
@dependency-start
contract reference
responsibility Documents tools/agent_tools/stablehlo_value_closure.py.
upstream implementation ../../tools/agent_tools/stablehlo_value_closure.py traces scoped StableHLO SSA dependencies.
upstream design jit_canonical_ir.md defines the JIT-canonical operational IR input.
downstream design ../../agents/skills/formal-proof-workflow.md consumes scoped closure reports for proposition-tree proof search.
@dependency-end
-->

# stablehlo_value_closure.py

`tools/agent_tools/stablehlo_value_closure.py` traces the dependency closure of
one StableHLO SSA value from a JIT-canonical operational IR file.

The tool keeps SSA names scoped by function and region. This is required for
proof work because names such as `%cst` are reused in private functions and must
not be treated as global values. Calls are traced through callee arguments and
return operands. StableHLO while initial operands are parsed as the right-hand
side values of `stablehlo.while(%iterArg = %value, ...)`, not as the region
argument aliases.

## Command

```bash
python3 tools/agent_tools/stablehlo_value_closure.py \
  --ir lean/<topic>/<root>_jit_canonical_ir.json \
  --function main \
  --value '%276' \
  --format text
```

Use `--format json` when a theorem graph or proof-status overlay needs to
consume the result mechanically.

## Output

The report contains:

- the scoped root value;
- operation rows in the closure;
- dense `stablehlo.constant` payload rows with result name, literal text, tensor
  type, and scalar dtype;
- scalar `stablehlo.convert` rows with source and target tensor types;
- terminal leaves such as public arguments, callee argument mappings, and
  unresolved values;
- a `truncated` flag when `--max-nodes` was hit.

## Boundary

This tool does not prove numerical progress, convergence, payload decoding, or
backend finite-precision correctness. It gives the scoped implementation
substitution tree and literal payload inventory that theorem search can consume.
