<!--
@dependency-start
contract design
responsibility Defines the typed consumer-static role projection for Issue #715.
upstream design ../contracts/static-seed-export.md static-seed boundary
upstream design ../../agents/internal-routines/design-implementation-correspondence.md DIC route
upstream implementation ../../agents/model_profiles.toml canonical role/profile registry
upstream implementation ../../tools/agent/orchestration/model_profile_registry.py role materializer
downstream implementation ../../tools/runtime/source/export_static_seed.py exact-byte exporter
downstream implementation ../../tools/validation/documentation/checks/check_bootstrap_docs.py source-free checker
downstream implementation ../../eval/producers/evaluate_codex_agent_roles.py committed-role evaluator
@dependency-end
-->

# Static Seed Consumer-Static Projection

## Responsibility and committed-tree boundary

Issue #715 owns one replaceable unit: the consumer-static projection of the canonical
35-role seed. The existing model/profile registry and materializer remain the only
instruction authority. The materializer renders and validates all 35 consumer-static
role blobs before the source commit is selected. The exporter then reads only that
committed Git tree and copies exact bytes; it never renders, imports the registry, or
consults a second source/role registry.

The run-local packet under `.agent-canon/reports/20260815-issue715-static-role-closure/`
is evidence and handoff transport. This document is the canonical design owner.

## Typed source-to-consumer projection

Keep `RoleInstructionClause`'s existing `role_instruction_clause_v1` identity and add a
typed optional projection record rather than changing any generated-role schema. The
projection record is `ConsumerStaticClauseProjection` with schema
`consumer_static_clause_projection_v1` and fields
`clause_id`, `consumer_static_text`, and `static_obligations`. `text` remains the
live-role text byte-for-byte. A clause containing a producer path must provide a
nonempty, source-neutral `consumer_static_text`; a clause without one may inherit
`text` only after the static prefix gate passes.

The exact typed obligation owner in `tools/agent/orchestration/model_profile_registry.py` is:

```text
StaticObligation(schema_id="consumer_static_obligation_v1",
                 obligation_id, fragment)
STATIC_OBLIGATION_TABLE: tuple[StaticObligation, ...]
```

The closed table has these exact IDs and path-free canonical fragments:

- `validation_owner`: follow the selected closed validation route;
- `parent_assignment`: act only on the assigned child packet and scope;
- `parent_authority`: respect child-owned integration publication and final-review decisions;
- `stop_handback`: return branch/head/check evidence or the role result and stop.

The static renderer resolves `static_obligations` through
`STATIC_OBLIGATION_TABLE`, composes the selected fragments, and returns the selected IDs.
Validation compares the typed render result with the expected fragment composition; it
does not search prose for obligation keywords. `consumer_static_text` may equal `text`
only for a source-neutral clause.

The canonical path-bearing clauses and required obligation sets are:

| canonical clause ID | producer reference in live `text` | required static obligations |
| --- | --- | --- |
| `python_solid_boundary` | `agents/skills/python-review.md` and `agents/skills/agent-orchestration.md` | `validation_owner`, `parent_assignment` |
| `luna_impl` | `agents/skills/agent-orchestration.md` | `validation_owner`, `parent_assignment`, `parent_authority`, `stop_handback` |
| `spark_impl` | `agents/skills/agent-orchestration.md` | `validation_owner`, `parent_assignment`, `parent_authority`, `stop_handback` |

`consumer_static_text` is mandatory for every clause whose case-normalized live text
contains any exact forbidden prefix, and for any future clause that names a producer,
source, runtime, updater, or network path. The materializer rejects a missing projection,
an unknown obligation ID, an obligation set outside the table, or a static text that
contains a forbidden prefix. The generated dependency headers are not clause text and
are handled by the mode-specific renderer.

Keep the existing `GeneratedRoleView` schema, `generated_role_view_v1`, and its existing
field order; projection mode is an input selector to the materializer, never a persisted
public field:

```text
schema_id, view_id, role_id, profile_id, name, description, nickname_candidates,
sandbox_mode, approval_policy, rendered_instructions, model, reasoning_effort,
capabilities, allowed_context, forbidden_context, return_schema_id, checkpoint_policy,
continuation_policy, source_canonical_digest, logical_role_id, role_contract_ref,
capsule_schema_id
```

Generated role TOML and `agents_config.json` keep their current serialized executable and
projection shapes, including `generated_role_profile_projection_v1` and the existing
`projection_digest` field; no mode key or new runtime field is added. The live renderer
keeps its current dependency headers and path-bearing comments. The consumer-static
renderer emits only path-free schema/digest comments (the v1 generated-view marker and
the hexadecimal digest); it omits dependency headers, materializer/registry references,
source paths, and all other producer-path comments. Invocation mode exists only in the
in-memory render request. Source-only registry/materializer metadata is never part of the
seed allowlist.

## Digest, live invariance, and coherence proof

Use the existing `projection_digest` field for one mode-independent digest in both render
modes. Its canonical payload is:

```text
{profile_id, role_id,
 clauses: [{id, priority, live_text, consumer_static_text, static_obligations}]}
```

The materializer renders both modes, verifies that both use the same digest, and verifies
the static render by exact typed-fragment composition for each selected obligation ID. The
runtime alignment checker compares the committed static role bytes and the existing-shape
`agents_config` against the static render and the same per-role digest.

Live invariance is deliberately narrow and testable: the pre-change and post-change live
render must have identical `developer_instructions` bytes and identical existing
executable role fields (`name`, `description`, `nickname_candidates`, `sandbox_mode`,
`approval_policy`, `model`, and `model_reasoning_effort`). Path-free digest or other
non-normative metadata comments may change. This proves live behavior is unchanged while
allowing the digest to bind both live and static clause variants.

## Committed-role evaluator contract

`eval/producers/evaluate_codex_agent_roles.py#evaluate_generated_role_projection` is
also a downstream consumer of the committed projection. It must request
`generate_role_views(..., projection="consumer-static")`, because `agents_config.json`
and `.codex/agents/*.toml` are the consumer-static committed tree. The evaluator keeps
the existing v1 eight-field executable-role assertion and compares every committed
`developer_instructions` value with the static render; it must not silently fall back to
the live default. The stale test assertion that requires
`agents/model_profiles.toml` in a generated role TOML is removed and replaced with the
source-free comment/prefix negative assertion.

The live invariance test is separate from evaluator/static parity. The implementation
must maintain a pre-change live golden for all 35 role IDs, covering each role's
`developer_instructions` bytes and existing executable fields, and compare it with a
post-change `generate_role_views(..., projection="live")` render for the same 35 IDs.
The test fails on role-set, field, or byte drift; comparing live output only with the
static output is not a substitute. The evaluator test suite also runs the CLI against
the committed tree and requires zero generated-view findings.

## Export/checker gates

The exporter and source-free checker lower-case payload bytes and reject these exact five
byte prefixes by substring scan:

```text
agents/skills/
agents/model_profiles.toml
tools/agent_tools/
../../agents/
../../tools/
```

The exporter applies the gate to every allowlisted blob before destination creation. The
checker applies it to provenance, `.codex/config.toml`, and every role payload. Both also
enforce exact 35-role config closure, regular `0644` files, no symlink/gitlink, exact
allowlist closure, deterministic bytes, and source-hidden/no-source/no-runtime/no-network/
no-updater/no-import/no-secret behavior.

## SSE clauses

- `SSE-001`: The consumer-static projection is materialized for all 35 canonical roles before a commit is selected; the exporter copies only committed-tree bytes and never renders or consults a second registry.
- `SSE-002`: A typed projection mode selects live text or consumer-static text from the single canonical model-profile registry; closed typed obligation fragments preserve validation-owner, parent-assignment, authority, stop, and handback obligations without producer paths, and validation compares typed composition rather than prose keywords.
- `SSE-003`: The generated role schema remains generated_role_view_v1 with the existing TOML and agents_config field sets; projection mode is an input selector only, the existing projection_digest field carries the canonical digest, live executable fields/instructions remain invariant, consumer-static TOML emits only path-free schema/digest comments, and evaluate_codex_agent_roles.py explicitly validates the committed consumer-static projection rather than its live default.
- `SSE-004`: One mode-independent projection digest covers role/profile identity, priorities, live text, consumer-static text, and obligation identifiers; live and static renders and agents_config must read back the same digest.
- `SSE-005`: Exporter and source-free checker lower-case payload bytes and reject the exact five prefixes agents/skills/, agents/model_profiles.toml, tools/agent_tools/, ../../agents/, and ../../tools/; exporter rejects before destination creation and checker scans every role and config payload.
- `SSE-006`: The committed static seed has exact allowlist closure: config references exactly the 35 same-named role files; every file is a regular 0644 blob; exports are byte-for-byte deterministic.
- `SSE-007`: Source-hidden validation proves no source checkout, vendor, runtime, updater, network, import, symlink, gitlink, secret, or unallowlisted file is required to parse and validate the complete 35-role seed.
- `SSE-008`: No new dependency graph, dependency-header system, source resolver, runtime checkout, updater, network access, or manually maintained role registry is introduced.

## DIC-010 closure locators

- `documents/design/static-seed-consumer-static-projection.md#Typed source-to-consumer projection` → SSE-001..003
- `documents/design/static-seed-consumer-static-projection.md#Digest, live invariance, and coherence proof` → SSE-004
- `documents/design/static-seed-consumer-static-projection.md#Export/checker gates` → SSE-005..008
- `documents/contracts/static-seed-export.md#生成規則`, `#Source-free Consumer Validation`, `#禁止 Surface`
- `documents/contracts/static-seed-allowlist.toml#files`
- `agents/model_profiles.toml#role_instruction_templates`, `#model_profiles`
- `tools/agent/orchestration/model_profile_registry.py#RoleInstructionClause`, `#ConsumerStaticClauseProjection`, `#StaticObligation`, `#STATIC_OBLIGATION_TABLE`, `#generate_role_views`, `#_render_role_view`, `#write_role_views`
- `tools/runtime/source/export_static_seed.py#_validate_content`, `#load_export_plan`, `#_validate_codex_config`
- `tools/validation/documentation/checks/check_bootstrap_docs.py#iter_static_seed_consumer_findings`
- `eval/producers/evaluate_codex_agent_roles.py#evaluate_generated_role_projection`, `#evaluate_static_agent_configs`
- `tests/agent_tools/test_model_profile_registry.py#typed obligation projection`
- `tests/agent_tools/test_evaluate_codex_agent_roles.py#committed consumer-static evaluator`, `#pre-change live golden for all 35 roles`
- `tests/agent_tools/test_export_static_seed.py#canonical 35-role source-hidden export`
- `tests/tools/test_check_bootstrap_docs.py#static seed consumer source-hidden validation`

The real canonical 35-role source-hidden fixture and its exact closure/coherence/
determinism assertions are implementation acceptance evidence, not preimplementation
evidence. The implementation must add that fixture before this design is marked complete.

## Migration and rollback

Materialize and validate all 35 static blobs, commit the generated source snapshot, export
from that commit, then run the source-hidden checker before template import. Rollback reverts
the complete projection/materializer/checker/export contract to regular tracked files only;
it never restores a live source link, runtime checkout, updater, or network fallback.
