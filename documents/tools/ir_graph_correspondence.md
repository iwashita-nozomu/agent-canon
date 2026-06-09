<!--
@dependency-start
responsibility Documents ir_graph_correspondence.py operator usage.
upstream implementation ../../tools/agent_tools/ir_graph_correspondence.py checks IR equation fact coverage.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits Algorithm Expansion IR code facts.
upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py emits code-fact lemma nodes.
upstream design ../../agents/skills/formal-proof-workflow.md defines proof graph workflow.
downstream implementation ../../tests/agent_tools/test_ir_graph_correspondence.py tests CLI behavior.
@dependency-end
-->

# ir_graph_correspondence.py

`ir_graph_correspondence.py` checks whether Algorithm Expansion IR equation
facts are represented in the Lemma Dependency Graph and, optionally, adopted by
`proof_status.json`.

Use it between `algorithm_lemma_graph.py` and `proof_path_analyzer.py`:

```bash
python3 tools/agent_tools/ir_graph_correspondence.py \
  --algorithm-ir lean/pdipm_convergence/pdipm_run_impl_ir.json \
  --lemma-graph lean/pdipm_convergence/pdipm_run_impl_local_convergence_lemma_graph.json \
  --proof-status lean/pdipm_convergence/proof_status.json \
  --target-profile local_convergence \
  --equation-tag step_update \
  --format markdown \
  --out lean/pdipm_convergence/pdipm_ir_graph_correspondence.md
```

For a proof fragment that consumes specific intermediate formulas, pass those
fact ids explicitly and require adoption:

```bash
python3 tools/agent_tools/ir_graph_correspondence.py \
  --algorithm-ir lean/pdipm_convergence/pdipm_run_impl_ir.json \
  --lemma-graph lean/pdipm_convergence/pdipm_run_impl_local_convergence_lemma_graph.json \
  --proof-status lean/pdipm_convergence/proof_status.json \
  --fact-id fact__python_jax_util_optimizers_pdipm__py___PDIPMStepper___step_update__assignment_equation__line_1329__next_residuals \
  --require-proof-status-adoption
```

## What It Checks

For each selected IR code fact, the checker validates:

- an expected `code_fact` lemma node exists;
- a `lemma_consumes_code_fact` edge connects an implementation lemma to that
  fact node;
- the fact is on the selected target chain;
- when `--require-proof-status-adoption` is set, the fact is referenced by a
  `proof_status.json` `code_derived_facts` row.

The default inspected fact kinds are `assignment_equation` and
`return_equation`, because those are the intermediate computation formulas that
should be consumed by proof lemmas. Use `--fact-kind class_default` only when a
theorem depends on default parameter values.

## Iteration Units

The report groups facts by `source_path`, `source_symbol`, and `equation_tags`.
For iterative algorithms this gives a reproducible per-iteration slice such as
`_step_update:step_update` or `_step_status:local_convergence`.

This grouping is navigation evidence. It does not prove the math. It ensures
that the formulas used by a theorem are the formulas extracted from the current
implementation, rather than hand-written equations drifting in prose or Lean.

## Outputs

Formats:

- `text`: stable key-value lines for shell gates.
- `json`: machine-readable report.
- `markdown`: reader-facing correspondence report.

The command exits nonzero only for structural errors, such as a selected IR
fact missing from the graph. Facts that are graph-covered but not adopted in
`proof_status.json` are informational unless
`--require-proof-status-adoption` is set.
