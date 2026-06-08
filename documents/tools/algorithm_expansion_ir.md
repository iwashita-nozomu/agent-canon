<!--
@dependency-start
responsibility Documents algorithm_expansion_ir.py operator usage.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py builds Algorithm Expansion IR.
upstream design ../../agents/skills/formal-proof-workflow.md defines Algorithm Expansion IR workflow.
downstream implementation ../../tests/agent_tools/test_algorithm_expansion_ir.py tests CLI behavior.
@dependency-end
-->

# algorithm_expansion_ir.py

`algorithm_expansion_ir.py` builds an Algorithm Expansion IR from a Python
algorithm entrypoint without importing or executing the target module. It is a
proof-planning tool. The generated IR is not proof evidence; it is the
intermediate structure used by `$formal-proof-workflow` to choose the local
lemmas and assumptions needed by a final theorem.

Use it from a repository root:

```bash
python3 tools/agent_tools/algorithm_expansion_ir.py \
  --root . \
  --import-root ../other-source-tree \
  --python-symbol python/jax_util/optimizers/pdipm.py::_solve \
  --target-theorem "PDIPM local floor-limited convergence" \
  --backend-profile-library lean/lib/backend_profiles.json \
  --format markdown \
  --out reports/formal-proof/pdipm_algorithm_ir.md
```

The `--python-symbol` value uses `path.py::qualname` syntax. The target file is
read as UTF-8 and parsed with `ast.parse`; module top-level code is not run.
The optional `--import-root` flag may be supplied multiple times to resolve
imports from source trees outside the repository root. The tool still does not
runtime-import those modules; it only parses matching `.py` sources.
The optional `--backend-profile-library` flag points to proof-only profile data
such as `lean/lib/backend_profiles.json`. The IR builder reads that file and
emits backend assumptions; the target algorithm does not read it.

## IR Grain

The intended graph grain is the known-lemma or selected-local-obligation unit.
Nodes and edges keep enough information to decide which local theorem is needed
for the final proof target. The report also emits `code_facts` for
AST-derived assignment, return, module-constant, and class-default expressions
that are relevant to proof-topic equation tags such as reduced KKT, step
updates, floor-preserving steps, MINRES defaults, and PDIPM initialization.

Node fields include:

- `source_symbol`: the `path.py::qualname` style implementation anchor.
- `math_role`: state transition, solve, certificate, diagnostic, performance
  helper, or bookkeeping.
- `runtime_object`: coarse runtime object such as `State`, `Info`,
  residual, direction, or certificate.
- `precision_model`: dtype/backend floor involvement when mechanically visible.
- `equation_tags`: proof-topic tags visible from the symbol and local code.
- `proof_relevance`: `required` or `excluded` for the goal-directed proof slice.

Edge fields include:

- `edge_kind`: call, initialization, instance construction, instance method
  call, state update, or certificate request.
- `assigned_to`: assignment target names for constructor and state-flow edges.
- `receiver_name` and `receiver_type`: mechanically inferred instance
  interaction information for calls such as `algorithm.step(...)`.
- `resolved`: whether the target was resolved to a same-module AST symbol.

Code fact fields include:

- `fact_id`: stable source-derived id usable from proof-status records.
- `fact_kind`: `assignment_equation`, `return_equation`, `module_constant`,
  or `class_default`.
- `target` and `expression`: normalized AST source text.
- `equation_tags` and `target_profiles`: proof-topic routing for lemma graphs.

Static check records include:

- `check_kind`: currently constructor resolution or instance method resolution.
- `edge_id`: the structural edge discharged before mathematical proof selection.
- `status`: `statically_checked`, `static_checker_required`, or
  `static_resolution_gap`.
- `proof_effect`: how the static fact changes proof selection. Instance
  dispatch edges are dropped from local proof obligations; the callee theorem,
  when mathematical, remains a node or child proof scope.

Backend assumption records include:

- `assumption_id`: stable id for the proof-only arithmetic assumption.
- `profile_variable`: theorem variable such as `backend_profile`.
- `scope`: always `proof_only_overlay`; this must not become production runtime
  config.
- `applies_to_nodes`: precision-related IR nodes, or a target-level assumption
  when the theorem itself asks for FP32 / backend semantics.
- `required_witnesses`: dtype, unit roundoff, precision-reduction flag,
  fast-math/contraction semantics, reassociation semantics, denormal mode,
  min/max semantics, and lowered-IR or backend-flag evidence.
- `checker_route`: where the proof must discharge or record the assumption
  before using finite-precision error bounds.

Obligation records include:

- `obligation_id`: stable id consumed by a proof note or trace.
- `grain`: `known_lemma`, `local_obligation`, `assumption`, or `excluded`.
- `consumes_nodes` and `consumes_edges`: IR slice evidence for the local claim.
- `existing_proof_search`: query seed for proof libraries and literature search.
- `checker_route`: target route for a proof assistant, solver, or assumption ledger.
- `remaining_gap`: the current missing theorem or instantiation boundary.

## Limits

The tool saturates recursively over AST-resolved calls and stops by already
expanded `path.py::qualname` keys. It resolves same-module functions, classes,
and methods. It also
infers instance method calls from argument annotations and simple constructor
assignment. Resolved instance interactions are emitted as static checks and are
not consumed by proof obligations. If the receiver type is known but the method
body is outside the AST root, the dispatch is delegated to static checking and
the external callee may still appear as a child proof scope or assumption when
its mathematical role is relevant. If the receiver type is unknown, the IR keeps
a `static_resolution_gap` instead of turning the dispatch fact into a
mathematical assumption.

Import resolution is source-root based. The tool resolves `import module as m`,
`from module import symbol`, and relative imports to AST-readable source files
under `--root`, conventional `python/` or `src/` children, and any explicit
`--import-root`. It also resolves callback references such as
`jax.lax.while_loop(..., stepper.step, ...)` when the receiver type is statically
known, and callable algorithm fields such as `runtime.solver_algorithm(...)`
from class field annotations like `solver_algorithm: minres.Algorithm`.
Function-pointer variant fields are expanded conservatively when the variant
targets are visible in the same AST module. For example, a field such as
`update: _Update` in a preconditioner algorithm expands `self.update(...)` to
same-module `*_update` functions, including LOBPCG and dense-eigendecomposition
preconditioner update branches. The variant selection fact is a static dispatch
check; the mathematical content remains in the selected variant function nodes.

External non-instance module calls remain in the IR as unresolved external nodes
so the proof note can decide whether to expand them with another root command.
The `--target-theorem` value labels the goal-directed slice; it does not prove
that the slice is complete.

The tool intentionally does not mark claims as verified. A selected local
obligation still needs a formal theorem, existing-proof source, literature
evidence, or explicit problem-class/backend assumption.

Backend arithmetic profiles are proof IR overlays. For example, an IREE FP32
proof target should bind `backend_profile` from `lean/lib/backend_profiles.json`
plus compiler/runtime evidence or a lowered-IR witness in the proof graph. The
profile library is read by `algorithm_expansion_ir.py`, not by the production
optimizer. It should not add `iree_*`, `floating_point_profile`, or other
proof-only fields to an algorithm `InitializeConfig`, because those values are
not algorithm inputs and would make the production API carry proof bookkeeping.
