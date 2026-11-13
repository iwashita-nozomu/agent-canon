<!--
@dependency-start
contract reference
responsibility Documents check-proof-trace-alignment operator usage.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/check_proof_trace_alignment.rs checks proof trace anchors.
upstream design ../../agents/skills/formal-proof-workflow.md defines proof trace alignment policy.
downstream implementation ../../tests/agent_tools/test_check_proof_trace_alignment.py tests CLI behavior.
@dependency-end
-->

# check-proof-trace-alignment

`check-proof-trace-alignment` verifies that a package-retained formal-proof
trace still points at the implementation code path claimed by its contracts.
It checks recorded theorem references and source anchors before formal proof work.

Use it from a repository root:

```bash
agent-canon check-proof-trace-alignment \
  --root . \
  --trace-module python/<package>/proof_traces/<claim>_proof_trace.py
```

The [native runtime provider](../../tools/runtime/python-provider/README.md)
loads the existing Python trace and uses CPython's AST parser and unparser.
The checker orchestration and validation logic are implemented in Rust.

The checker reads `FORMAL_PROOF_TRACE` from the trace module and validates:

- `checked_fragment` names are retained in `checked_proof_fragments`.
- `source_path` files exist.
- `source_symbol` or `qualname` anchors resolve through Python AST parsing.
- `required_source_tokens` are present in the anchored source segment.
- `forbidden_source_tokens` are absent from the anchored source segment.
- `required_ast_patterns` are present in normalized AST expression candidates.
- optional return/branch count bounds match the anchored AST subtree.

This tool separates code-path/proposition alignment from theorem checking. A
passing result means the trace contract is still attached to the code path it
names. It does not change `proof_status` to `verified`; that still requires the
target proof assistant or solver to check the theorem without proof escapes.

Text output is stable for CI and agent closeout:

```text
PROOF_TRACE_ALIGNMENT=pass
PROOF_TRACE_ALIGNMENT_CONTRACTS=12
PROOF_TRACE_ALIGNMENT_ANCHORS=18
PROOF_TRACE_ALIGNMENT_FINDINGS=0
```

Use `--format json` when another tool needs the structured finding list.
