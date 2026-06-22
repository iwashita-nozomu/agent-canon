# OOP Readability: changed_design_paths Effect Boundary

<!--
@dependency-start
contract issue
responsibility Tracks OOP readability refactor work for changed design path selection.
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py checks design claims.
upstream implementation ../../tools/oop/python/readability.py reports OOP readability findings.
upstream design ../../agents/skills/oop-readability-check.md defines OOP readability evidence handling.
@dependency-end
-->

issue_id: AC-20260621-oop-changed-design-paths-effect-boundary
status: resolved
source: runtime
severity: S2
evidence: reports/agents/oop-readability-20260621-refactor-issues/oop_readability_check_design_doc_claims.md
affected_surfaces: tools/agent_tools/check_design_doc_claims.py, tools/oop/python/readability.py, tests/agent_tools/test_check_design_doc_claims.py
edit_scope: tools/agent_tools/check_design_doc_claims.py changed_design_paths, reports/agents/oop-readability-20260621-refactor-issues/oop_readability_check_design_doc_claims.md
required_action: Refactor `changed_design_paths` so process execution and returned path normalization are separated into named effect and pure transform steps.
close_condition: `python3 tools/oop/python/readability.py --root . --language all --min-score 95 tools/agent_tools/check_design_doc_claims.py tests/agent_tools/test_check_design_doc_claims.py` no longer reports `changed_design_paths`.
resolved_by: reports/agents/oop-readability-20260621-refactor-fix/oop_readability_after.md

## Finding

The OOP readability checker reports:

- `tools/agent_tools/check_design_doc_claims.py:313`
- symbol: `changed_design_paths`
- kind: `mixed_morphism_effect`
- dimension: `morphism/effect separation`
- actual_vs_limit: `return+effect` > `pure-or-effect-boundary`

The function both crosses the process boundary to inspect changed paths and
returns normalized values. This should be split so the effectful command
boundary and pure selection / normalization contract can be tested and reviewed
independently.

## Closure Notes

Keep the checker behavior unchanged. The closeout must include the OOP
readability command above and the design-claim checker regression tests.

## Resolution

Resolved by splitting Git changed-path collection from pure design-document
path filtering in `tools/agent_tools/check_design_doc_claims.py`.

Validation:

- `python3 tools/oop/python/readability.py --root . --language all --min-score 95 tools/agent_tools/check_design_doc_claims.py tests/agent_tools/test_check_design_doc_claims.py`
- `python3 -m pytest tests/agent_tools/test_check_design_doc_claims.py tests/agent_tools/test_check_convention_compliance.py -q`
