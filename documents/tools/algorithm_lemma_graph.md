<!--
@dependency-start
responsibility Documents algorithm_lemma_graph.py operator usage.
upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py builds lemma graphs.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits source IR.
upstream design ../../agents/skills/formal-proof-workflow.md defines proof graph workflow.
downstream implementation ../../tests/agent_tools/test_algorithm_lemma_graph.py tests CLI behavior.
@dependency-end
-->

# algorithm_lemma_graph.py

`algorithm_lemma_graph.py` converts Algorithm Expansion IR JSON into a lemma
dependency graph. The graph is separate from the implementation expansion IR:
IR nodes and edges explain how the algorithm is wired; lemma graph nodes and
edges explain which auxiliary mathematical claims, assumptions, and theorem
targets depend on each other.

Use it after `algorithm_expansion_ir.py`:

```bash
python3 tools/agent_tools/algorithm_expansion_ir.py \
  --root . \
  --python-symbol python/jax_util/optimizers/pdipm.py::_solve \
  --target-theorem "PDIPM local floor-limited convergence" \
  --format json \
| python3 tools/agent_tools/algorithm_lemma_graph.py \
  --target-profile local_convergence \
  --target-profile solver_chain \
  --format markdown \
  --out reports/formal-proof/pdipm_lemma_graph.md
```

## Graph Shape

The output has three graph layers:

- `lemma_nodes`: auxiliary claims, assumptions, and target theorem/profile nodes.
- `lemma_edges`: directed `depends_on` style edges. A source node consumes the
  target node.
- `target_chains`: per-target/profile reachability summaries proving that the
  selected lemma set is mechanically connected from the theorem node.

Lemma ids are derived from IR `node_id`, not from `obligation_id`, because one
algorithm can import multiple modules with the same implementation symbol such
as `_solve`. This keeps PDIPM, KKT, MINRES, and LOBPCG `_solve` lemmas distinct.

## Target Profiles

One expanded algorithm can support multiple theorem targets. The tool currently
materializes these profiles:

- `all`: every non-excluded selected IR obligation.
- `certificate_soundness`: certificate and diagnostic lemmas.
- `local_convergence`: solve and state-transition lemmas.
- `fp32_floor`: precision/backend-floor assumptions and lemmas.
- `solver_chain`: KKT, MINRES, LOBPCG, preconditioner, and rank-r solver lemmas.
- `reduced_kkt`: reduced-KKT equation and bridge lemmas.
- `step_update`: implemented step-map and residual-recompute lemmas.
- `floor_preserving_step`: fraction-to-boundary and positivity-floor lemmas.
- `minres_defaults`: MINRES default tolerance, stopping, and dtype-floor facts.
- `pdipm_initialization_path`: reset/cold-start and initial inequality repair
  facts.

Code-derived facts become `code_fact` lemma nodes. Backend profile records from
the proof-only profile library become `backend_profile` lemma nodes connected
from the backend assumption node. These nodes are structural evidence, not
mathematical proof completion. If the algorithm changes, regenerate the IR and
lemma graph from the current root, then rebuild the proof-status overlay; do not
carry IR-backed generated lemmas forward by editing prose or labels.

Profiles do not prove the claims. They create explicit target nodes and
`target_requires` edges so that a proof note can choose one theorem target and
audit exactly which auxiliary claims it consumes.

## Editable Overlay

The generated graph is the initial graph derived from the current Algorithm
Expansion IR. Agents and humans may edit a separate proof-search overlay by
adding auxiliary lemmas, bridge lemmas, dependency edges, proof attempts,
failed routes, adoption decisions, and missing-frontier records.

Do not hand-edit IR-backed obligation nodes to remove, rename, or reinterpret
them. If the source program changes, regenerate the Algorithm Expansion IR and
then regenerate the initial lemma graph. If an IR-backed node is irrelevant to
the current proof path, leave it in the graph and exclude it from the active
target chain, certified subgraph, or missing frontier.

Proof paths are Try-and-Error artifacts. A proof note can mention failed or
blocked attempts, but it may claim `verified` only for a certified subgraph
whose theorem/lemma nodes and dependency edges are backed by checker evidence.

## Validation

The tool validates:

- every lemma edge endpoint exists;
- dependency edges are acyclic;
- every target chain reaches the lemmas selected by its profile.

If validation fails, the command exits nonzero and sets
`status=lemma_graph_invalid`. A valid graph only proves structural connectivity;
individual lemma nodes still need `verified`, `assumption`, or `blocked` proof
status from checker evidence or a proof note.
