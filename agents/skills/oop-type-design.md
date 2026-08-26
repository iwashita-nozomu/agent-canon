<!--
@dependency-start
contract skill
responsibility Documents pre-implementation OOP and type-boundary design for this repository.
upstream design ../canonical/skills.md public skill registry and visibility contract
upstream design ../../documents/conventions/object-oriented-design.md shared OOP boundary policy
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and sparse projection skeleton
upstream design ../../documents/conventions/coding-conventions-cpp.md C++ source/header ownership contract
upstream design ../../documents/design/protocols.md Protocol and dependency-direction policy
upstream design ../../documents/design/dependency-manifest-design.md dependency-header DSL
upstream design ../internal-routines/design-implementation-correspondence.md universal design-to-implementation correspondence route
downstream implementation ../../.codex/personal/skills/oop-type-design/SKILL.md runtime discovery shim
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
duplicate their checks or evidence.

When the changed surface includes a Docstring or template projection, read
`documents/conventions/DOCSTRING_GUIDE.md` as the semantic owner. The packet
records the responsibility region, selected semantic relation, and projection
anchor; it does not copy the guide’s clause text or force `Args`, `Returns`,
`Raises`, or other fixed sections. The catalog capability `oop_type_design` selects this
language-neutral OOP/type design owner only. After that owner selection, existing
`agent_team.language_review_candidates` selects `python_reviewer` or `cpp_reviewer` for
language implementation paths and `docs_workflow_steward` for convention/template docs.
No new routing branch is introduced.

## Purpose

Create one language-neutral `oop_type_design_packet` before implementation.
Use a minimal `Protocol` or interface, immutable value object, aggregate, and
constructor/factory contract where the responsibility model requires them;
record legal state transitions and dependency direction explicitly.
The packet fixes responsibility, type, state, boundary, dependency, static
delegation, implementation, and review contracts. It is a design producer, not
an implementation, checker, language-specific review, test-first, or
evaluator-writing route.

## Required output

Produce exactly one packet in this order:

1. `Scope`: user request clauses, public behavior/schema impact, and owner boundary.
2. `Reuse Survey`: existing functions, values, dataclasses, aggregates, Protocols,
   interfaces, factories, adapters, checkers, docs, and tests with path and symbol.
3. `Responsibility Map`: component, subject, reason, replaceable unit, owned state,
   effects, and collaborators.
4. `Semantic Responsibility Contract`: semantic deltas, one implementation action per
   delta, obligations, primary verification owners, supporting properties/roles, and
   hard-edge closure. Use the run-local instance referenced by the active design packet.
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

## Semantic Responsibility Contract

Before naming a class, aggregate, module, or file, create or reuse the run-local
semantic responsibility contract referenced by the active design packet. A delta has
one action from `reuse|extend|replace|introduce` and one or more obligations. Each
obligation has exactly one primary verification owner from the contract's owner kinds.
Supporting evidence is recorded only for a distinct property or role.

Close the following hard edges before describing semantic grouping:
`invariant`, `atomic_transition`, `transaction`, `lifecycle`, `effect`,
`consistency`, and `substitutability`. The grouping explains meaning and verification
ownership. It does not prescribe a class, module, file, directory, or function.

The semantic contract is allocated before implementation. An `existing_test` owner
records `contract_ref -> changed_mechanism_ref -> observable_assertion ->
decidable_oracle` and a `removal_witness`. `test_designer` is a post-implementation
route only for unresolved test-owned runtime risk after the owning mechanism is
established or repaired.

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
- Group independently changeable, verifiable, owned, effectful, or substitutable
  meanings only after the hard-edge closure. Keep operations tied by one invariant
  or atomic transition together and preserve each independent owner. The semantic
  contract is the decision record; implementation shape follows the owning design,
  dependency direction, and validation route.

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
is assigned to an owner before semantic grouping is selected.

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
- C++ target responsibility: `cpp-core` is the provider; individual test and experiment
  targets are consumers; root-anchored build/install paths and lifecycle-owned result paths
  are read back from `documents/design/cpp-build-layout.md`.
- Explicit `Any`: `python3 tools/agent_tools/check_static_any.py --submodule-aware`.
- OOP/SOLID signals: `$oop-readability-check`; keep its evidence with the owning review.
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
status only; the parent owns raw bytes, critical-pass, convergence, final completion,
and graph artifacts.

The packet schema is `agent_canon.oop_type_design_packet.v1`. No new checker,
registry, task role, evaluator writer, or keyword route is introduced by this skill.
