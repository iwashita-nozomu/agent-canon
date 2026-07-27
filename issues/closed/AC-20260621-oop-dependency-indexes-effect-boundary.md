# OOP Readability: dependency_indexes Effect Boundary

<!--
@dependency-start
contract issue
responsibility Tracks OOP readability refactor work for dependency edge indexing.
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py checks design claims.
upstream implementation ../../tools/oop/python/readability.py reports OOP readability findings.
upstream design ../../documents/dependency-manifest-design.md defines dependency graph semantics.
@dependency-end
-->

issue_id: AC-20260621-oop-dependency-indexes-effect-boundary
status: resolved
source: runtime
severity: S2
evidence: reports/agents/oop-readability-20260621-refactor-issues/oop_readability_check_design_doc_claims.md
affected_surfaces: tools/agent_tools/check_design_doc_claims.py, documents/dependency-manifest-design.md, tests/agent_tools/test_check_design_doc_claims.py
edit_scope: tools/agent_tools/check_design_doc_claims.py dependency_indexes, dependency_closure, reports/agents/oop-readability-20260621-refactor-issues/oop_readability_check_design_doc_claims.md
required_action: Refactor `dependency_indexes` so index construction exposes explicit source and target maps without mixed return/effect morphology.
close_condition: `python3 tools/oop/python/readability.py --root . --language all --min-score 95 tools/agent_tools/check_design_doc_claims.py tests/agent_tools/test_check_design_doc_claims.py` no longer reports `dependency_indexes`.
resolved_by: reports/agents/oop-readability-20260621-refactor-fix/oop_readability_after.md

## Finding

The OOP readability checker reports:

- `tools/agent_tools/check_design_doc_claims.py:343`
- symbol: `dependency_indexes`
- kind: `mixed_morphism_effect`
- dimension: `morphism/effect separation`
- actual_vs_limit: `return+effect` > `pure-or-effect-boundary`

The dependency index builder is on the path to `dependency_closure`, so unclear
index construction makes later traversal refactors harder. The repair should
keep dependency manifest semantics intact while making the returned maps and
construction steps explicit.

## Closure Notes

Keep this issue scoped to the index construction boundary. The broader closure
algorithm complexity is tracked separately.

## Resolution

Resolved by replacing subscript mutation in `dependency_indexes` with explicit
source and target grouping helpers in `tools/agent_tools/check_design_doc_claims.py`.

Validation:

- `python3 tools/oop/python/readability.py --root . --language all --min-score 95 tools/agent_tools/check_design_doc_claims.py tests/agent_tools/test_check_design_doc_claims.py`
- `python3 -m pytest tests/agent_tools/test_check_design_doc_claims.py tests/agent_tools/test_check_convention_compliance.py -q`
