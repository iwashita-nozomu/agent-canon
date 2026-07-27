<!--
@dependency-start
contract reference
responsibility Documents formal_proof.py operator usage and proof-status boundary.
upstream implementation ../../tools/agent_tools/formal_proof.py builds proof scaffold artifacts.
upstream design ../../agents/skills/formal-proof-workflow.md defines the natural-language to formal-proof workflow.
upstream design ../../references/agent-canon-technology-bibliography.md records proof-assistant source evidence.
downstream implementation ../../tests/agent_tools/test_formal_proof.py tests CLI output.
@dependency-end
-->

# formal_proof.py

## Reader Map

- Owns the operator usage and proof-status boundary for `formal_proof.py`.
- Main path: the opening description defines purpose, followed by the command
  example, output behavior, and proof-status limits.
- Read this before generating proof-planning scaffolds from natural-language
  claims or Python symbols.
- Boundary: the tool scaffolds proof obligations; proof validity remains with
  the target proof assistant and formal-proof workflow.

`formal_proof.py` turns a natural-language mathematical claim, or a selected
Python symbol parsed through `ast.parse`, into a proof-planning scaffold. It
does not prove the claim. Its output status is
`scaffold_only_unverified` until a target proof assistant checks a completed
formalization without placeholders such as `<FORMAL_TARGET>`, `sorry`, or
`Admitted`.

Use it from the repository root:

```bash
python3 tools/agent_tools/formal_proof.py \
  --claim-file reports/formal-proof/claim.md \
  --target lean \
  --domain "linear algebra" \
  --name spd_quadratic_form_positive \
  --out-dir reports/formal-proof/spd \
  --format markdown
```

The output directory contains:

- `formal_proof_plan.json`
- `formal_proof_plan.md`
- `existing_proof_queries.txt`
- `literature_queries.txt`
- a target-language theorem scaffold such as `spd_quadratic_form_positive.lean`
- an importable Python trace module such as
  `spd_quadratic_form_positive_proof_trace.py`

For implementation-derived proof planning, pass a Python source reference:

```bash
python3 tools/agent_tools/formal_proof.py \
  --python-symbol path/to/algorithm.py::<implementation_symbol> \
  --target lean \
  --domain "<mathematical domain>" \
  --out-dir reports/formal-proof/<topic> \
  --format markdown
```

With `--python-symbol`, the tool reads the file as UTF-8 and does not import or
execute the module. The plan records source path, source symbol, a signature
summary, and additional obligations for extracted branch and return-expression
structure. These fields are provenance and planning evidence only, not proof
evidence.

To keep the trace when a project is distributed as a Python library, write the
output directory inside the package tree or copy the generated
`*_proof_trace.py` file into a package module. Python source files are retained
by ordinary setuptools package discovery, so downstream users can import the
trace after installing the wheel:

```python
from my_package.proof_traces.spd_quadratic_form_positive_proof_trace import (
    FORMAL_PROOF_TRACE,
)

assert FORMAL_PROOF_TRACE["status"] == "scaffold_only_unverified"
```

When imported, the generated module rewrites
`FORMAL_PROOF_TRACE["library_trace_module_path"]` from its own `__file__`, so
that field points to the installed package location. The generation-time paths
are preserved separately as `origin_library_trace_module_path` and
`origin_theorem_stub_path`. If the theorem stub is distributed beside the trace
module, `runtime_theorem_stub_candidate_path` points to the co-located installed
stub candidate.

If a project stores JSON traces instead of Python trace modules, its
`pyproject.toml` must include those JSON files as package data. The generated
Python trace module avoids that extra packaging requirement.

The generated query files are inputs for `$formal-proof-workflow` and
`$literature-survey`. Search formal libraries and existing proofs before writing
new lemmas. Verification authority remains with the target checker command
reported in the plan, for example `python3
tools/agent_tools/lean_proof_env.py check-file --env-dir
reports/formal-proof/lean-proof-env --lean-file <stub>.lean --execute`,
`isabelle process`, `coqc`, `z3`, or `cvc5`. Lean stubs should use the
AgentCanon Mathlib/Aesop proof environment unless the theorem package itself
owns a Mathlib-based theory.

For algorithm-derived claims, a generated single-lemma scaffold is only one
candidate proof route. If that route is too strong or fails, do not report the
downstream theorem as false or impossible from that scaffold alone. Feed the
attempt back into `$algorithm-proof-exploration` / `$formal-proof-workflow` as
overlay evidence, then look for a weaker lemma, adjacent graph facts,
code-derived identities, problem witnesses, or an algorithmic-blocker analysis
whose combined certified subgraph can close the target theorem. Adopt
`refuted` or `unprovable_under_assumptions` only when checker-backed evidence
rules out the target under the current theorem scope, not merely one generated
proof route.

When proof graph structural analysis finds a condition that closes only by
unfolding into the target predicate itself, classify it as `projection_only` or
`circularity_check`, not as a substantive necessary/sufficient condition. Such
nodes are useful because they identify the public return projection or stopping
scalar, but the graph must continue to a separate non-circular edge rooted in
code facts, public `Problem` / config inputs, backend evidence, or a formal
library theorem. A certified convergence or finite-stop subgraph must not rely
on `Condition := Target` as its terminal problem-class witness.

When a scaffold becomes a checked proof fragment, keep the package-retained
trace current instead of leaving the evidence only in a work log. Add the
checked theorem or solver artifact to the trace module, record the checker
command and version, and keep any remaining implementation-instantiation
obligations as explicit proof boundaries. Do not let a checked mathematical
fragment imply that the corresponding runtime code path, residual unit,
stopping guard, backend arithmetic, or final-status projection has also been
instantiated unless that bridge is separately checked.
