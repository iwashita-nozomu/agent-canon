<!--
@dependency-start
contract design
responsibility Documents check_design_doc_claims.py operator usage.
upstream design ../dependency-manifest-design.md dependency manifest graph semantics
upstream design ../design/README.md design-document evidence policy
upstream implementation ../../tools/agent_tools/graph_client.py provides canonical graph status, query, and context responses
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py checks design-document claims
upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh optionally runs this checker
downstream implementation ../../tests/agent_tools/test_check_design_doc_claims.py validates checker behavior
@dependency-end
-->

# check_design_doc_claims.py

`check_design_doc_claims.py` is a thin consumer of the canonical knowledge
graph. It classifies design-document claim tokens, then asks `agent-canon graph`
for path resolution, dependency witnesses, owner/source evidence, and parent
context. It does not parse dependency headers, scan an evidence corpus, decode
a private schema, or establish graph facts. Semantic proof and domain judgement
stay with the proof, review, and domain skills.

Use it when a design document introduces implementation-backed claims, DSL
terms, problem standard forms, normalization rules, or structure-refactor
handoff decisions.

## Reader Map

- Owns operator usage for deterministic design-document claim evidence checks.
- Main path: Command, Evidence Model, Output, and Refactor Route.
- Read this before checking whether design-document claims have canonical graph
  evidence from implementations or upstream design docs.
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

- The checker first calls `graph status`. It evaluates no document unless the
  response is `fresh` and contains a verified
  `agent-canon.graph.integration.v1` record whose public profile is `default`,
  source producer profile is `parent`, fingerprints match the status response,
  and verification code is `graph.integration.verified`. Otherwise it emits
  `graph-integration-unverified` and performs no query or context call.
- `graph query --relation dependency --direction both` supplies recursive
  implementation and parent evidence up to `--recursive-depth`. The consumer
  uses only explicit facts projected through canonical graph node IDs; it does
  not read dependency headers.
- `graph context --path <claim-document> --token <token>` supplies authoritative
  `resolved_path`, exact `source_identity` (`snapshot_commit`, `source_path`,
  `content_sha256`), `source_span`, owner, dependency witnesses, producer, and
  evidence references. The shared typed graph adapter validates this tuple;
  the checker does not decode it again.
- Backticked claim tokens are classified as `path`, `path_or_evidence`,
  `evidence`, or `math_or_prose` before graph dispatch. Classification selects
  which canonical result fields are required; it is not fact authority.
  Explicit path syntax is supported only when context returns a non-null,
  tuple-validated `source_identity`. A `path_or_evidence` token may instead
  match a canonical context item or dependency witness. Unknown evidence fails
  closed.
- Python-compatible key/value tokens use exactly
  `^[A-Za-z][A-Za-z0-9_.-]*=\S+$` and require matching graph evidence.
- Path normalization belongs to the Rust graph context operation. `./` and
  `../` tokens resolve from the claim document; other relative paths resolve
  from the parent repository root; absolute and escaping paths are rejected.
- Math/prose tokens remain local input classification and are never promoted to
  graph facts.
- `Evidence And Assumption Ledger` records evidence sources, first-use DSL or
  standard-form assumptions, parent-doc alignment, and refactor handoff.
- Parent contradiction checks use only incoming dependency facts and parent
  `GraphContextItem` excerpts/values returned by the graph.

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
Rebuild the graph through `agent-canon graph build` when the finding is
`graph-integration-unverified`; never add a filesystem or header-parser
fallback to this checker.
