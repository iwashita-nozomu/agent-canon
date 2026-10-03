<!--
@dependency-start
contract design
responsibility Defines root instruction ownership, conditional reader routes, and the finite entrypoint grammar.
upstream design ../conventions/software-engineering-principles.md single-owner and contract-complete change policy
downstream design ../../AGENTS.md source entrypoint
downstream design ../../ROOT_AGENTS.md portable common base
downstream design ../../agents/canonical/SOURCE_ROUTING.md source owner selection
downstream design ../../.github/AGENTS.md GitHub subtree overlay
downstream implementation ../../tools/agent/templates/entrypoint_composer.py consumer root composition
downstream implementation ../../tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py structural verification
downstream implementation ../../tools/validation/semantic/convention/convention_compliance_contracts.toml canonical marker ownership
downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py entrypoint regression
downstream implementation ../../tests/agent_tools/test_point_of_use_skill_routes.py conditional candidate regression
downstream design ../../agents/canonical/ROOT_DELIVERY.md source delivery detail
downstream design ../../agents/canonical/ROOT_EXECUTION.md source execution detail
downstream design ../../agents/canonical/ROOT_IMPLEMENTATION.md source implementation detail
downstream design ../../agents/canonical/CODEX_WORKFLOW.md phase selection
downstream design ../../agents/canonical/CODEX_BOOTSTRAP.md selected run bootstrap
downstream design ../../agents/canonical/CODEX_COMPLETION.md selected validation and closeout
downstream design ../../agents/canonical/CODEX_IMPLEMENTATION.md selected implementation procedure
downstream design ../../agents/canonical/CODEX_INTAKE.md intake and context continuity
downstream design ../../agents/canonical/CODEX_ROUTING.md unresolved routing decisions
@dependency-end
-->

# Root entrypoint owner-map contract

## Purpose

[AGENTS.md](../../AGENTS.md) is the source entrypoint;
[ROOT_AGENTS.md](../../ROOT_AGENTS.md) is the portable common base. Keep shared
constraints self-contained and task-specific procedures with their owners. A short
entrypoint is not sufficient if its links require all details to be read at startup.
The governing goal is a usable route at the point of the dependent decision/action.

## Model

Let `E` be the entrypoints, `H(e)` their ordered level-2 headings, `A(e)` the permitted
headings, `P(e)` procedural syntax, and `owner(r)` the canonical owner of a responsibility.
The entrypoint invariants are `H(e) = A(e)` and `P(e) = empty`: no fenced commands,
numbered recipes, nested procedure headings, or duplicated owner policy. An entry
routes a task-specific responsibility to its owner instead of reimplementing it.
Operational marker contracts are owned outside `E`.

A reader route connects a source section, a condition decidable before the dependent
action, and an existing destination section. Reachability, activation, and timing are
distinct obligations. An index establishes discovery; the actual consumer's conditional
link establishes where to apply the rule. A link or dependency header alone activates
neither the entire document nor all its descendants. Reuse unchanged owner context.

These are design invariants over existing Markdown links, catalog entries, and
workflow conditions, not a new routing registry, include language, or reading ledger.
Code/LSP dependency traversal still follows the changed contract through affected
consumers; document reading stops at the facts needed for the current decision.

## Allowed information architecture

Source AGENTS, common ROOT, and the optional source map use the same ordered headings:
`Repository Role`, `Reader Map`, `Always-On Boundary`, `Runtime Owner Map`, `Task Entry`,
`Validation Routing`. ROOT retains portable shared constraints. Source AGENTS starts
with literal `@ROOT_AGENTS.md` and has one optional-map route for unknown owners.
That directive is an explicit reading request, not a native include implementation.

The source map contains short conditional starting points. Known owners bypass it.
Its required document rows use ordinary inline Markdown links to their canonical
repository paths; displayed path text or a code span is not a usable replacement.
Relative destinations are resolved from the containing document, not the product cwd.

## Ownership and distribution boundary

| Surface | Owns | Reading / distribution boundary |
| --- | --- | --- |
| source `AGENTS.md` | source identity, common-base read, conditional owner selection | no duplicate common policy or consumer configuration |
| optional `SOURCE_ROUTING.md` | source-specific owner and starting section | only the matching unresolved decision |
| `ROOT_AGENTS.md` | portable common behavior and consumer owner roles | self-contained without an AgentCanon checkout |
| consumer-specific fragment | product, build/test, placement and local instructions | maintained by the consumer |
| generated consumer `AGENTS.md` | exact ROOT plus consumer-specific text | one regular tracked file, no live source dependency |

Common constraints cannot be replaced by links to source-only Skills: a source-free
consumer would lose the rule. Compact repetition and place source-specific procedures
behind conditional routes, while retaining valid inputs, safety/authority, root fixes,
verification, reporting, formatting and cleanup guarantees in the portable base.

## Responsibility migration

| Decision or operation | Existing procedure owner |
| --- | --- |
| Implementation basis and complete affected unit | ROOT_IMPLEMENTATION and engineering principles |
| Design correspondence when selected | design-implementation-correspondence routine |
| Execution failure, checkout, branch/storage, team | matching ROOT_EXECUTION section |
| Reader-facing writing and delivery evidence | matching ROOT_DELIVERY section |
| Current task phase | CODEX_WORKFLOW Reader Map |
| Unresolved family, Skill, profile, or placement | the matching CODEX_ROUTING section |
| Design/implementation and dependency context | CODEX_IMPLEMENTATION Reader Map |
| Validation and delivery | CODEX_COMPLETION Reader Map |

The transport Skill `codex-task-workflow` carries these selections and results. It
must not reproduce full implementation or closeout checklists in both prose and
Runtime Contract Clauses. Its existing named anchors remain routing surfaces.

## Verification contract

`check_entrypoint_owner_map.py` retains its title, ordered heading, procedure-syntax,
required-row, optional-map, and operational-marker ownership checks. It also verifies:

- source AGENTS begins with the explicit common-base directive;
- required document rows actually link to their canonical destinations, rather than
  merely displaying those names or sending the reader to a different file;
- those required document targets exist.

Only the finite required owner-row grammar is parsed here. Existing docs tools own
general Markdown syntax, path/anchor checks, and broader document references. The
checker does not infer prose activation, dynamically execute routes, or claim actual
agent reading. Existing focused tests exercise missing/moved directives, wrong or
unlinked destinations, missing targets, equivalent relative paths, and prior grammar
rejections. `test_point_of_use_skill_routes.py` uses the production catalog loader
and candidate projector to check the three repaired conditional handoffs.

Review checks conditions before branch bodies, complete required behavior, and the
following positive and negative scenarios. It does not replace execution evidence
for changed code with prose or require full agent-behavior measurement for a link fix.

| Scenario | Applicable route | Inactive procedure |
| --- | --- | --- |
| Resolved bounded document change | current owner, targeted validation, authorized delivery | DIC fingerprint, run-bundle bootstrap and coordinated task_close |
| Selected full-staging coordination | persisted design packet and selected review/closeout | a second packet or terminal predicate |
| C++ Docstring/convention-only change | semantic documentation/static evidence | native build and performance benchmark |
| Numerical C++ solver performance question | computational-optimization candidate under solver condition | mandatory solver record for unrelated C++ work |
| Public failed verification | immediate topic record, exact-record readback, reuse | private capture and behavior evaluation |
| Private knowledge lookup | agent-learning private record/search route | automatic behavior-eval run |
| Ordinary task/Issue report | ROOT_DELIVERY reporting owner | experiment-only report style |
| Selected local branch integration | integration candidate and its Git owner | activation merely from listing the Skill |

For connected-session validation failures, preserve the operation and its limits in
the existing [failure topic](../notes/failures/connected-rule-routing-validation.md).
A draft with pending materialization or unavailable formatting is not merge-ready.

These checks establish source contracts and candidate behavior, not measured token
savings, speed, compliance frequency, all-run coverage, or deployment to consumers.

## Consumer root composition

The existing `entrypoint_composer.py` retains its public API and exact base/specific
byte handling. It atomically publishes only a coherent regular-file output with
managed source-commit, byte-count, digest and separator markers. New outputs or valid
managed replacements are allowed; unmarked/corrupt output, directories and symlinks
are preserved as typed failures. No recursive expansion, source AGENTS import, new
loader, live projection, or alternate singular `AGENT.md` alias is added.

## Template boundary

`project_template` owns its static generated AGENTS and consumer-specific fragment.
This source change does not update that generated file, add a vendor/submodule or
symlink dependency, or require all consumers to adopt it before PR delivery. Existing
static-seed role/config boundaries and source-free composition tests remain in force.

## Responsibility-based document split

Source details remain in ROOT_IMPLEMENTATION, ROOT_EXECUTION and ROOT_DELIVERY.
The five Codex phase owners keep their established section anchors, including
`4. Run Bootstrap` and `5. Implementation`, for existing readers and packet producers.
Operational markers stay in their actual canonical owner rather than being copied
to root entrypoints to satisfy a test.

Bounded execution consumes existing structured task evidence. Full staging, DIC,
child handoff, and coordinated completion have separate explicit conditions before
their detail sections. `task_close.py` remains the single coordinated terminal owner;
bounded delivery uses the existing `execution_route_policy` instead of materializing
a new ledger to satisfy unrelated fields. Family selection comes from task_catalog,
not an independently maintained six-family prose list.

Source execution failures route directly to Notes Lifecycle. Artifact creation routes
to document placement/naming and consumer-reference updates at the moment a document
is created, split, moved or retired. Skill dictionary entries expose conditional
candidates without changing prerequisite order; public failure notes stay with their
owning Notes Lifecycle rather than widening private-learning discovery metadata.

## Codex automatic loading and on-demand reading

The discovery distinction is documented by the existing
[AGENTS guidance](https://developers.openai.com/codex/guides/agents-md/) and
[Skill progressive disclosure](https://developers.openai.com/codex/skills/).
This design relies on explicit common-base reading and static consumer composition;
it does not reinterpret ROOT's name or `@` as a native include.

For entry `A` and needed, not-yet-read sections `S(task)`, the design reading amount
is `bytes(A) + sum(bytes(s) for s in S(task))`. This counts selected document bytes,
not actual model tokens or measured performance. Keep automatic/subtree instructions
thin and do not move the same full-reading obligation to fallback names, comments,
Skill descriptions, or linked files.

[Skill Paths](../../agents/canonical/skills.md#skill-paths) already defines partial
canonical reading and real-file-relative links. Root/common instructions now expose
that meaning for thin generated adapters. Advertised commands are logical packets
executed through the existing CLI owner; adapters remain pointers and need no new
copy of procedure or generator schema. The existing materializer still owns generated
adapter updates: `build_record` hashes the catalog, dependency dictionary, and canonical
Skill bytes. Changing the dictionary invalidates every adapter record digest, so a
coherent delivery regenerates and reads back the complete adapter set with that owner.
A thin body does not exempt its provenance from regeneration. Verify the affected
graph projection through its existing owner as well; do not hand-edit digest comments.
Reuse resolved roots and routes without setup or preflight probes.

The scope is this entry/owner/consumer reading contract and its direct tests. Runtime
reconstruction, all-profile validation, unrelated Issue closure, template deployment,
and all-agent empirical evaluation are not added as completion requirements.
