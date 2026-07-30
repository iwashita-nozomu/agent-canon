<!--
@dependency-start
contract skill
responsibility Documents pre-implementation OOP and type-boundary design for this repository.
upstream design ../canonical/skills.md public skill registry and visibility contract
upstream design ../../documents/conventions/object-oriented-design.md shared OOP boundary policy
upstream design ../../documents/design/protocols.md Protocol and dependency-direction policy
upstream design ../../documents/design/dependency-manifest-design.md dependency-header DSL
upstream design ../internal-routines/design-implementation-correspondence.md universal design-to-implementation correspondence route
downstream implementation ../../.agents/skills/oop-type-design/SKILL.md runtime discovery shim
downstream implementation ../../agents/skills/catalog.yaml public skill and capability metadata
downstream implementation ../../tools/agent_tools/route.py explicit capability route
downstream implementation ../../evidence/agent-evals/skill_workflow_prompt_eval.toml prompt-evaluation targets
@dependency-end
-->

# oop-type-design

## Reader path and boundary

この stage は owning design の read、clause ID/fingerprint、responsibility map
を `../internal-routines/design-implementation-correspondence.md` の record に
接続します。universal invariant と failure semantics は routine 側にあり、
ここでは OOP/type contract owner の設計 packet だけを定義します。

This is the pre-implementation OOP/type-design route. Invoke it explicitly with
the capability ID `oop_type_design`:

```bash
python3 tools/agent_tools/route.py --capability oop_type_design
```

The `--capability` route selects the owner
`pre_implementation_oop_type_design` in phase `pre_implementation_design`.
Natural-language keywords do not activate this skill. `$oop-readability-check`,
`$python-review`, and `$cpp-review` are separate downstream consumers: they
produce post-hoc OOP/SOLID, Python, or C/C++ evidence after an implementation
diff exists. They do not select this design owner, and this skill does not
duplicate their checks or scores.

## Purpose

Create one language-neutral `oop_type_design_packet` before implementation.
Use a minimal `Protocol` or interface, immutable value object, aggregate, and
constructor/factory contract where the responsibility model requires them;
record legal state transitions and dependency direction explicitly.
The packet fixes responsibility, type, state, boundary, dependency, static
delegation, implementation, and review contracts. It is a design producer, not
an implementation, checker, post-hoc score, language-specific review, test
first, or evaluator-writing route.

## Required output

Produce exactly one packet in this order:

1. `Scope`: user request clauses, public behavior/schema impact, and owner boundary.
2. `Reuse Survey`: existing functions, values, dataclasses, aggregates, Protocols,
   interfaces, factories, adapters, checkers, docs, and tests with path and symbol.
3. `Responsibility Map`: component, subject, reason, replaceable unit, owned state,
   effects, and collaborators.
4. `Responsibility Split Ledger`: the labeled operation/dependency graph, candidate
   partitions, indivisible edges, coordination-only root, and split/cohesion decision.
5. `Type Contract`: abstract roles, minimal Protocol/interface methods and typed
   signatures, type parameters, value-object fields, aggregate root, constructor or
   factory API, and error type.
6. `Invariant Ledger`: constructor, field, and aggregate invariants; legal and
   illegal transitions; ownership/lifetime; and failure semantics.
7. `Composition Map`: composition root, dependency direction, injected contracts,
   concrete-construction and adapter boundaries, and forbidden reverse edges.
8. `Boundary Contract Matrix`: API, serialization, external input, CLI/config, and
   I/O/effect raw forms, normalized types, owners, validation points, and failures.
9. `Static Delegation`: existing owner tool, command, expected evidence, and why no
   runtime guard or test duplicates a statically decidable fact.
10. `Implementation Trace`: exact files, symbols, names, edit order, validation, and
    review gate.
11. `Open Decisions`: genuine external blockers only; no worker naming or API choice.

## Responsibility Split Ledger

Record a directed labeled graph `G=(V,E)` before naming a class or aggregate.
Vertices may be candidate types/objects, invariants, legal transitions, policies,
effects, owners, change reasons, and operations. Every edge uses one of these
labels: `maintains-invariant`, `atomic-transition`, `owns-state`, `owns-policy`,
`owns-effect`, `changes-for`, `verified-by`, `replaced-by`,
`shared-transaction`, `consistency-boundary`, `substitutability-boundary`,
`calls`, `depends-on`, or `coordinates`.

Use the fixed ledger columns below; do not decide from connected components alone:

```text
name, node_kind, invariant, state_transitions, policy, owner,
verification_owner, change_reasons, external_effects,
substitutability_boundary, replacement_boundary, cohesive_operations,
dependency_edges, partition_cut_edges, indivisible_edges, candidate_partition,
coordination_cost, baseline_coordination_cost, handoff_edges_current,
handoff_edges_retained, handoff_edges_new, partition_status, rejection_reason,
coordination_only, decision, coordination_owner, rejected_mechanical_reason
```

`node_kind` is one of `type|invariant|transition|policy|effect|owner|change_reason|operation`.
Serialize graph edges as `source->target:label`, partitions as
`part-<n>=<comma-separated node names>`, partition cuts as
`part-<n>=[source->target:label,...]`, and coordination costs as non-negative
two-decimal `Decimal` values.

First close over `maintains-invariant`, `atomic-transition`,
`shared-transaction`, `consistency-boundary`, and
`substitutability-boundary`; none may cross a partition. Then enumerate every
non-empty candidate partition, including `part-0` containing all nodes in
first-seen order. Keep all current semantic handoffs and add only new semantic
handoffs required by a partition. The baseline is the actual cost of the
current handoff multiset, not zero. Use
`coordination_cost(P) <= baseline_coordination_cost` and a coherent owner and
contract for every part. This is a labeled graph decision, not a
connected-components shortcut. A higher-cost partition is `keep_cohesive`, even when
the responsibility dimensions look independent. Fixed rejection reasons are
`empty-part`, `duplicate-node`, `cuts-indivisible-edge`,
`splits-atomic-operation`, `incoherent-owner`, `not-independent`, and
`coordination-cost-increased`.

The required numeric example is an `OrderService` whose current trace has
`place->parse_json` (1.00), `place->pricing_policy` (1.00),
`place->repository` (1.00), `place->retry_lifecycle` (1.00), and
`place->event_io` (1.00). Its baseline is `5.00`. A partition into adapter,
order aggregate, pricing policy, repository Protocol, retry coordinator, event
adapter, and a creation/connection/ordering-only coordinator retains `5.00` and
is admissible. A partition that adds a second consistency/retry handoff costs
`6.00` and must remain cohesive; the graph records that added handoff.

## Type, state, and responsibility rules

- Add a class only for a named invariant, owned mutable state, resource lifecycle,
  or a behavioral contract with multiple implementations that existing functions,
  values, or Protocols cannot express.
- Accept the smallest caller-facing Protocol/interface at a replacement boundary;
  do not add a one-implementation abstraction without substitution evidence.
- Prefer immutable value objects for identifiers, configuration, validated input,
  results, and events. Keep equality, normalization, units, and ranges in their
  constructor/factory contract.
- An aggregate owns its invariant and children. Cross-boundary operations are
  named legal state transitions; callers do not mutate children directly.
- Constructors/factories establish invariants, methods perform legal transitions,
  and adapters perform one raw-external-to-typed normalization.
- Policy depends on stable abstractions and typed values; details do not import
  policy. Composition roots create, connect, and order only.
- Split independently changeable, verifiable, owned, effectful, or substitutable
  dimensions only when the ledger admits a partition. Keep operations tied by one
  invariant or atomic transition together. Preserve each independent invariant
  and owner. Never use line/function count, method, file, or class size as the
  split oracle; responsibility accumulation or an oversized responsibility is
  evidence to model, not a mechanical partition decision.

The packet must reject these accumulated responsibilities: an `OrderService` that
also owns order invariants, pricing, repository access, JSON parsing, retry/lifecycle,
and event I/O; a `CheckoutController` that parses input, decides policy, mutates an
aggregate, persists it, and publishes effects; and a `CompositionRoot` that also
validates domain rules, queries repositories, parses configuration, retries
resources, or writes output.

For each mutable state owner, record its named fields, constructor invariant,
factory, legal transitions with preconditions/postconditions/failures, and forbidden
transitions. For each value object, record typed immutable fields, one normalization
boundary, equality, serialization, and typed construction failure. For each
abstract role, record minimal operations, associated values, substitution law, and
forbidden concrete dependencies. Every independent external effect and change reason
is assigned to an owner before a partition is selected.

## Boundary and composition contract

Every boundary records raw input, normalized typed form, owner, runtime validation,
serialization, failure, and static evidence. Public API, serialization,
external-input, and effect boundaries remain distinct. The external adapter may
parse and validate untrusted data once, construct a typed DTO/value object, and pass
it inward. Internal methods do not repeat guards already guaranteed by that type.

The composition root owns object creation, dependency wiring, and ordering only.
Domain invariants, policy decisions, repository queries, adapter parsing, lifecycle,
resource ownership, I/O, and boundary behavior remain delegated.

## Static delegation and test boundary

Delegate compiler, language, OOP, schema, and dependency facts to their existing
owners:

- Python public annotations and Protocol shape: `pyright`; Python review owns the
  changed-diff review.
- Python lint and formatting signals: `ruff`; it remains an existing static owner.
- C/C++ build, headers, and ownership: `$cpp-review` and its project-native checks.
- Explicit `Any`: `python3 tools/agent_tools/check_static_any.py --submodule-aware`.
- OOP/SOLID signals: `$oop-readability-check`; do not copy its score into this skill.
- Dependency headers/graph: `bash tools/agent_tools/run_repo_dependency_review.sh --report-dir <run-dir>/dependency-review --fail-missing`.
- Schema or algorithm checks: existing checker only when the changed implementation
  path is in that checker’s scope; otherwise `not_applicable`.

These static facts are not runtime guards and are not compiler-fact test oracles.
External malformed input may have one adapter guard and one boundary behavior test.
Behavioral tests are considered only after the owning production mechanism exists
and an unresolved invariant or failure risk remains. This skill has no test first
route.

## Design trace vocabulary

The packet is derived from the `Abstract Design Frame`, the
`Implementation Source Packet`, the `Design Side-Effect Map`, and the
`Design-To-Implementation Trace`. These artifacts keep the responsibility model,
implementation source paths, reader-facing effects, and validation/review order
traceable from design to implementation. They do not grant this skill ownership
of compiler facts or parent-owned evaluation artifacts.

## Downstream handoff and evaluation boundary

The implementation trace points to exact paths, symbols, validation, and review
owners. `$oop-readability-check`, `$python-review`, and `$cpp-review` consume the
later implementation diff; they do not feed ownership backward into this skill.
T14 uses a fresh read-only `gpt-5.4-mini` evaluator. The evaluator reports observed
status only; the parent owns raw bytes, score, critical-pass, convergence, final
completion, and graph artifacts.

The packet schema is `agent_canon.oop_type_design_packet.v1`. No new checker,
registry, task role, evaluator writer, compatibility path, or keyword route is
introduced by this skill.
