<!--
@dependency-start
responsibility Documents proof_bridge_candidate_extractor.py operator usage.
upstream implementation ../../tools/agent_tools/proof_bridge_candidate_extractor.py extracts bridge candidates from Algorithm IR facts.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits Algorithm Expansion IR code facts.
upstream design ../../agents/skills/formal-proof-workflow.md requires bridge-candidate exploration before proof weakening.
@dependency-end
-->

# proof_bridge_candidate_extractor.py

`proof_bridge_candidate_extractor.py` scans Algorithm Expansion IR `code_facts`
and proposes bridge propositions for proof planning. The candidates are
mechanical prompts for the next proof step; they are not accepted lemmas and they
must be discharged through the formal proof workflow before they can support a
claim.

Run it after regenerating Algorithm Expansion IR:

```bash
python3 tools/agent_tools/proof_bridge_candidate_extractor.py \
  --ir-json lean/<topic>/pdipm_solve_ir.json \
  --ir-json lean/<topic>/kkt_solve_ir.json \
  --target-theorem "PDIPM local convergence" \
  --format markdown \
  --out lean/<topic>/proof_bridge_candidates.md
```

The extractor currently recognizes bridge families around reduced KKT right-hand
sides, reduced answer projection, back-substitution, step-update residual
recomputation, scalar IPM residual metrics, fraction-to-boundary step lengths,
and nested solver residual certificates. If no matching facts are present, it
reports zero candidates rather than inventing mathematical statements.
