<!--
@dependency-start
contract policy
responsibility Defines public API traversal evidence before negative capability claims.
upstream design ../issues/closed/AC-20260518-api-surface-negative-conclusion.md records the original failure.
upstream design ../agents/workflows/hypothesis-validation-workflow.md requires cause and evidence before fixes.
upstream design ./coding-conventions-python.md defines helper and API-use discipline.
downstream implementation ../evidence/agent-evals/issue_eval_manifest.toml registers the API-surface eval case.
@dependency-end
-->

# API Surface Traversal Before Negative Conclusions

Before saying that a library, module, or existing project API cannot do
something, collect a bounded public-surface trail:

1. Public import/export surface, including `__all__` or documented exports.
1. Function/class signatures and constructor/config fields.
1. Nested public config fields and their public factory methods.
1. Examples, README snippets, and tests that show caller-side configuration.
1. The exact missing selector, method, field, or extension point if the
   conclusion remains negative.

This policy permits reading public surfaces needed to call the dependency
correctly. It does not authorize patching vendor internals, changing reusable
first-party APIs, or adding helper wrappers before the traversal is complete.

For implementation planning, record:

```text
api_surface_traversal=done
inspected_public_paths=<path or symbol list>
negative_conclusion=<exact missing selector or none>
selected_fix_surface=<caller/config/adapter/library>
```
