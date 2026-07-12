<!--
@dependency-start
contract design
responsibility Documents check_design_doc_claims.py operator usage.
upstream design ../dependency-manifest-design.md dependency manifest graph semantics
upstream design ../design/README.md design-document evidence policy
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py checks design-document claims
upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh optionally runs this checker
downstream implementation ../../tests/agent_tools/test_check_design_doc_claims.py validates checker behavior
@dependency-end
-->

# check_design_doc_claims.py

`check_design_doc_claims.py` compares design-document claim lines with
dependency-header evidence, implementation files, and upstream parent design
documents. Its authority is deterministic evidence routing; semantic proof and
domain judgement stay with the proof, review, and domain skills.

Use it when a design document introduces implementation-backed claims, DSL
terms, problem standard forms, normalization rules, or structure-refactor
handoff decisions.

## Reader Map

- Owns operator usage for deterministic design-document claim evidence checks.
- Main path: Command, Evidence Model, Output, and Refactor Route.
- Read this before checking whether design-document claims are wired to
  dependency headers, implementations, or upstream design docs.
- Boundary: semantic proof and domain judgement stay with proof, review, and
  domain skills.

## Command

```bash
python3 tools/agent_tools/check_design_doc_claims.py \
  --root . \
  --recursive-depth 3 \
  documents/design/<topic>.md
```

The dependency-review wrapper can run the same check after graph validation:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims
```

The wrapper's default claim scope is changed design documents. For an explicit
design document, pass:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims \
  --design-doc-claim-path documents/design/<topic>.md
```

## Evidence Model

- `@dependency-start` headers provide the design and implementation evidence
  graph.
- Recursive expansion follows `design` and `implementation` dependency edges
  up to `--recursive-depth`.
- Backticked claim tokens are classified as `path`, `evidence`, or
  `math_or_prose` before path resolution. Only `path` tokens reach filesystem
  APIs; unknown evidence is not auto-supported.
- Python-compatible key/value tokens use exactly
  `^[A-Za-z][A-Za-z0-9_.-]*=\S+$` and require same-record evidence.
- Root-relative paths resolve from `--root`. `./` and `../` paths, including
  wildcard paths, resolve from the claim document's directory. Absolute paths
  must remain inside the root. Invalid filesystem paths produce a typed finding
  and do not terminate the checker.
- Math notation such as set difference is checked as evidence, never as a path
  candidate, and still obeys strict claim support requirements.
- `Evidence And Assumption Ledger` records evidence sources, first-use DSL or
  standard-form assumptions, parent-doc alignment, and refactor handoff.
- Upstream parent design documents are scanned for deterministic modal
  contradictions over the same code token.

## Output

Text output is stable for run bundles and PR evidence:

```text
DESIGN_DOC_CLAIM_FINDING=<kind>:<path>:<line>:<detail>
DESIGN_DOC_CLAIMS_DOCUMENTS=<count>
DESIGN_DOC_CLAIMS_CHECKED=<count>
DESIGN_DOC_CLAIMS_SUPPORTED=<count>
DESIGN_DOC_CLAIMS_EVIDENCE_PATHS=<count>
DESIGN_DOC_CLAIMS_FINDINGS=<count>
DESIGN_DOC_CLAIMS=pass|fail
```

Use `--format json` when another tool needs structured results.

## Refactor Route

When this checker reports an evidence gap for a structural claim, route the
finding through `$dependency-analysis` first to produce the dependency-expanded
edit scope, then through `$structure-refactor` if the evidence points at
directory responsibility, root-view, or canonical document layout changes.
