<!--
@dependency-start
responsibility Documents formal_proof.py operator usage and proof-status boundary.
upstream implementation ../../tools/agent_tools/formal_proof.py builds proof scaffold artifacts.
upstream design ../../agents/skills/formal-proof-workflow.md defines the natural-language to formal-proof workflow.
upstream design ../../references/agent-canon-technology-bibliography.md records proof-assistant source evidence.
downstream implementation ../../tests/agent_tools/test_formal_proof.py tests CLI output.
@dependency-end
-->

# formal_proof.py

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

For implementation-derived proof planning, pass a Python AST source reference:

```bash
python3 tools/agent_tools/formal_proof.py \
  --python-symbol python/jax_util/optimizers/pdipm.py::_pdipm_accept_candidate \
  --target lean \
  --domain "interior point method" \
  --out-dir reports/formal-proof/pdipm-acceptance \
  --format markdown
```

The AST route reads the file as UTF-8 and parses it with `ast.parse`; it does
not import or execute the module. The plan records `source_kind=python_ast`,
`source_path`, `source_symbol`, a signature summary, and additional obligations
for extracted branch and return-expression structure. These fields are
provenance and planning evidence only, not proof evidence.

The generated query files are inputs for `$formal-proof-workflow` and
`$literature-survey`. Search formal libraries and existing proofs before writing
new lemmas. Verification authority remains with the target checker command
reported in the plan, for example `lake env lean <stub>.lean`, `isabelle
process`, `coqc`, `z3`, or `cvc5`.
