<!--
@dependency-start
responsibility Documents proof_path_analyzer.py operator usage.
upstream implementation ../../tools/agent_tools/proof_path_analyzer.py analyzes proof-status overlays.
upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py emits lemma graphs.
upstream design ../../agents/skills/formal-proof-workflow.md defines proof path workflow.
downstream implementation ../../tests/agent_tools/test_proof_path_analyzer.py tests CLI behavior.
@dependency-end
-->

# proof_path_analyzer.py

`proof_path_analyzer.py` checks a proof-status overlay against one or more lemma
dependency graphs. It does not regenerate Algorithm Expansion IR, does not edit
IR-backed nodes, and does not prove mathematics. It verifies that the current
proof path is mechanically connected and that remaining holes are represented
as named witnesses, assumptions, checked negative results, or algorithm-change
guidance.

Typical use:

```bash
python3 tools/agent_tools/proof_path_analyzer.py \
  --algorithm-ir lean/pdipm_convergence/pdipm_solve_ir.json \
  --lemma-graph lean/pdipm_convergence/pdipm_local_convergence_lemma_graph.json \
  --lemma-graph lean/pdipm_convergence/pdipm_solver_chain_lemma_graph.json \
  --proof-status lean/pdipm_convergence/proof_status.json \
  --adoption-text notes/themes/pdipm_convergence_proof.md \
  --format markdown \
  --out lean/pdipm_convergence/pdipm_proof_path_analysis.md
```

## What It Checks

The analyzer fails for proof-path integrity defects:

- lemma edges that reference missing nodes;
- target chains that cannot reach every selected lemma;
- frontier rows with bare `unverified` instead of a terminal or next-witness
  status;
- verified checker fragments that are not adopted in the supplied proof text;
- implementation tokens in `proof_status.json` that are not present in the
  lemma graph text or as real files;
- duplicate B-labels that name different frontier obligations;
- code-derived facts with unsupported derivability classes, empty statements,
  missing `fact_id`, or IR-backed `source_id` values that are absent from the
  supplied lemma graphs and Algorithm Expansion IR files;
- nonminimal returned frontier blockers: an open witness must be represented on
  the selected target chain and must not hide a smaller open target-chain
  descendant.

Open mathematical witnesses do not make the command fail. They keep
`proof_complete=false` while preserving a connected proof path. This distinction
lets a proof note say "the path is connected up to these named assumptions or
bridge lemmas" without pretending that the final theorem is already checked.

## Inputs

- `--lemma-graph`: one or more JSON files emitted by `algorithm_lemma_graph.py`.
- `--algorithm-ir`: optional Algorithm Expansion IR JSON files used to validate
  `code_derived_facts[].source_id` for facts marked `ir_or_lemma_graph`.
- `--proof-status`: the topic-local status file with `checked_fragments`,
  `unprovable_under_assumptions`, and `open_frontier`.
- `--proof-frontier`: Markdown text used to inspect frontier labels and status
  terms.
- `--adoption-text`: additional reader-facing proof text used to confirm that
  checked fragments were adopted.

## Outputs

Formats:

- `text`: stable key-value lines for shell gates.
- `json`: machine-readable report.
- `markdown`: reader-facing proof-path summary.

The report distinguishes:

- `validation.valid`: graph/path integrity succeeded.
- `validation.connected`: target chains are structurally connected.
- `frontier_minimal`: all returned open witnesses are the first nonterminal
  rows on the selected target chain.
- `proof_complete`: no open witnesses or unprovable-under-assumption rows remain.
- `code_fact_count`: number of classified code-derived or explicitly non-code
  facts attached to open/refuted proof rows.
- `code_fact_derivability_counts`: counts for classes such as
  `ir_or_lemma_graph`, `code_only_ir_algorithm_gap`,
  `code_only_code_style_opacity`, `external_backend_assumption`, and
  `mathematical_assumption`.

Use `validation.valid` as the gate for artifact health; use `proof_complete`
only when deciding whether the mathematical proof is finished. Use
`frontier_minimal` when preparing a nonterminal proof return; if it is false,
decompose the blocker further or switch to the theorem/profile whose graph
contains that witness. After algorithm changes, reset generated IR-backed lemma
groups by regenerating Algorithm Expansion IR, lemma graphs, and the
proof-status overlay from the current root.

`open_frontier` may contain rows that have already been explored to
`unprovable_under_assumptions` for the selected theorem/profile. Those rows are
not counted as open witnesses; the analyzer folds them into
`unprovable_under_assumptions` so their code-derived facts remain attached to
the terminal negative result. Use this when a frontier item has been tried and
the current Algorithm Expansion IR plus assumption ledger does not entail the
needed witness.

## Code-Derived Fact Rows

`proof_status.json` rows may include `code_derived_facts`:

```json
{
  "fact_id": "B2-F2",
  "statement": "MINRES computes final_true_norm_r/final_true_rel_r at finish.",
  "derivability": "ir_or_lemma_graph",
  "source_kind": "lemma_node",
  "source_id": "lemma__python_jax_util_solvers_minres_py_minres_finish",
  "gap_owner": "none",
  "proof_effect": "Use returned true-residual evidence in the outer handoff."
}
```

Use `ir_or_lemma_graph` only when the `source_id` is present in the supplied
graphs or IR. Use `code_only_ir_algorithm_gap` when the code contains the fact
but current IR generation does not retain enough equation or constant
structure. Use `code_only_code_style_opacity` when the fact is recoverable but
spread across helper/control-flow shape. Use `external_backend_assumption` and
`mathematical_assumption` for facts that cannot be derived from Python code or
AST IR.

External assumptions may also carry code-derived fact rows. For example, the
PDIPM B5 backend boundary records `lean/lib/backend_profiles.json` and
`lean/lib/backend_fp32_evidence.json` facts under `external_assumptions`; the
analyzer includes those facts in `code_fact_count` and derivability counts so
the backend evidence packet is visible instead of being reported as an open
algorithm blocker.
