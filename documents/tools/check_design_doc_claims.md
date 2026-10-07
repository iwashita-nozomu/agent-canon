<!--
@dependency-start
contract design
responsibility Documents check_design_doc_claims.py operator usage.
upstream design ../design/dependency-manifest-design.md dependency manifest graph semantics
upstream design ../design/README.md design-document evidence policy
upstream implementation ../../tools/validation/semantic/documents/check_design_doc_claims.py checks design-document claims
upstream implementation ../../tools/analysis/dependencies/run_repo_dependency_review.sh optionally runs this checker
downstream implementation ../../tests/agent_tools/test_check_design_doc_claims.py validates checker behavior
@dependency-end
-->

# check_design_doc_claims.py

`check_design_doc_claims.py` checks implementation-facing design claims against
source-derived dependency evidence and explicit local Markdown links. It reads
dependency headers for the selected evidence closure and verifies that linked
paths resolve inside the repository. Semantic proof and domain judgement stay
with the proof, review, and domain skills.

Use it when a design document makes an implementation-backed claim and names
the supporting source or design document with a Markdown link.

## Reader Map

- Owns operator usage for deterministic design-document claim evidence checks.
- Main path: Command, Evidence Model, Output, and Refactor Route.
- Read this before checking whether design-document claims have source evidence
  from implementations or upstream design docs.
- Boundary: semantic proof and domain judgement stay with proof, review, and
  domain skills.

## Command

```bash
python3 tools/validation/semantic/documents/check_design_doc_claims.py \
  --root . \
  --recursive-depth 3 \
  documents/design/<topic>.md
```

The dependency-review wrapper can run the same check after graph validation:

```bash
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims
```

The wrapper's default claim scope is changed design documents. For an explicit
design document, pass:

```bash
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims \
  --design-doc-claim-path documents/design/<topic>.md
```

## Evidence Model

- `@dependency-start` headers provide the source evidence closure. Recursive
  `design` and `implementation` edges are followed up to
  `--recursive-depth`.
- A claim is checked only when its line contains an explicit local Markdown
  link and a claim cue. The link target is resolved relative to the document
  for `./` and `../` paths, or relative to the repository root otherwise.
  Existing paths and readable evidence texts support the claim; missing paths
  are reported.
- Ordinary inline code, `key=value` examples, issue references, and prose are
  not claim tokens. External URLs, anchors, and mail links are not local source
  evidence.
- An `Evidence And Assumption Ledger` remains the human-readable section for
  the evidence rationale of checked claim documents. The checker does not
  require a graph receipt, profile, fingerprint, or persisted graph snapshot.
- Parent contradiction checks compare the modal wording attached to the same
  explicit Markdown link in the selected upstream design documents.
- Explicit graph analysis remains an independent opt-in capability; invoking
  `agent-canon graph` is not part of this checker’s normal route.

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
If a separate task explicitly chooses graph analysis, use its graph command and
runtime contract; do not add that optional analysis as a prerequisite here.
