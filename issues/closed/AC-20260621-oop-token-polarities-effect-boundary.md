# OOP Readability: token_polarities Effect Boundary

<!--
@dependency-start
contract issue
responsibility Tracks OOP readability refactor work for token polarity extraction.
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py checks design claims.
upstream implementation ../../tools/oop/python/readability.py reports OOP readability findings.
upstream design ../../documents/tools/check_design_doc_claims.md documents design-claim checking.
@dependency-end
-->

issue_id: AC-20260621-oop-token-polarities-effect-boundary
status: resolved
source: runtime
severity: S2
evidence: reports/agents/oop-readability-20260621-refactor-issues/oop_readability_check_design_doc_claims.md
affected_surfaces: tools/agent_tools/check_design_doc_claims.py, documents/tools/check_design_doc_claims.md, tests/agent_tools/test_check_design_doc_claims.py
edit_scope: tools/agent_tools/check_design_doc_claims.py token_polarities, polarity_for_line, check_parent_contradictions, reports/agents/oop-readability-20260621-refactor-issues/oop_readability_check_design_doc_claims.md
required_action: Refactor `token_polarities` so token extraction, polarity classification, and map accumulation are explicit named steps.
close_condition: `python3 tools/oop/python/readability.py --root . --language all --min-score 95 tools/agent_tools/check_design_doc_claims.py tests/agent_tools/test_check_design_doc_claims.py` no longer reports `token_polarities`.
resolved_by: reports/agents/oop-readability-20260621-refactor-fix/oop_readability_after.md

## Finding

The OOP readability checker reports:

- `tools/agent_tools/check_design_doc_claims.py:662`
- symbol: `token_polarities`
- kind: `mixed_morphism_effect`
- dimension: `morphism/effect separation`
- actual_vs_limit: `return+effect` > `pure-or-effect-boundary`

`token_polarities` combines Markdown body iteration, token extraction,
prefix-based polarity classification, and accumulation into one returned map.
The refactor should keep parent/child contradiction behavior unchanged while
making the intermediate contracts visible.

## Closure Notes

The closeout should include contradiction regression tests and the OOP
readability command above.

## Resolution

Resolved by separating token polarity entry extraction from polarity map
construction in `tools/agent_tools/check_design_doc_claims.py`.

Validation:

- `python3 tools/oop/python/readability.py --root . --language all --min-score 95 tools/agent_tools/check_design_doc_claims.py tests/agent_tools/test_check_design_doc_claims.py`
- `python3 -m pytest tests/agent_tools/test_check_design_doc_claims.py tests/agent_tools/test_check_convention_compliance.py -q`
