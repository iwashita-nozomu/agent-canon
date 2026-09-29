<!--
@dependency-start
contract policy
responsibility Defines public API traversal evidence and its repair-versus-preservation boundary.
upstream design ../../ROOT_AGENTS.md necessary API changes and consumer migration
upstream design ../../agents/skills/dependency-analysis.md requires cause and evidence before fixes.
upstream design ../conventions/coding-conventions-python.md defines helper and API-use discipline.
downstream implementation ../../eval/definitions/issue_eval_manifest.toml registers the API-surface eval case.
downstream design ../../agents/canonical/ROOT_IMPLEMENTATION.md applies traversal to necessary API changes
@dependency-end
-->

# API Surface Traversal Before Negative Conclusions

Fix the latest explicit user agreement under
[SEP-01](../conventions/software-engineering-principles.md#sep-01-contract-first),
then use the task-specific starting point in
[SEP-06](../conventions/software-engineering-principles.md#sep-06-kiss): composition
for new functionality, preservation review for the structure being repaired.
Traversal informs that target; it does not redesign the target around an existing
API or require deletion for every task. Before concluding that an API cannot
satisfy it, collect a bounded public-surface trail:

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

## After traversal: repair and migration

Traversal selects the existing capability and responsible owner; it does not
freeze the current API. New functionality starts with direct use, configuration,
and composition, implementing only the evidenced gap. Under the
[API change boundary](../../agents/canonical/ROOT_IMPLEMENTATION.md#public-api-additions),
a requested fix also reconsiders preservation of the affected owner. Reuse sound
parts, but do not add adaptation solely to protect an unnecessary or defective
structure. Correct, remove, or replace it as needed for the simplest agreed result;
update affected callers, tests, and documentation and remove superseded paths.
Keep explicit compatibility requirements and actual access or authority limits
visible, without inferring a freeze from public visibility or active use.

A blanket rule that a bug-fix request cannot authorize a public change confuses
unrelated expansion with necessary repair. When the existing surface cannot
express the required behavior, freezing it leaves the defect unresolved or
encourages duplicate implementations and caller workarounds. The governing
boundary is the requested behavior and its affected contracts, not an unchanged
signature. This follows [SEP-01](../conventions/software-engineering-principles.md#sep-01-contract-first):
preserve required semantics while closing the API change and its migration.
Do not turn this into permission for unrelated APIs, a new approval gate, or
an obligation to audit consumers whose contracts are unchanged.
