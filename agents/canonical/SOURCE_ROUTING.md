# AgentCanon Source Routing
<!--
@dependency-start
contract agent-runtime
responsibility Routes source readers to one responsibility-specific starting section when its decision is unresolved.
upstream design ../../documents/design/entrypoint-owner-map.md root entrypoint grammar and responsibility boundary
upstream design ../../AGENTS.md minimal always-loaded source entrypoint
downstream design CODEX_WORKFLOW.md conditional phase selection
downstream design ROOT_IMPLEMENTATION.md implementation decisions
downstream design ROOT_EXECUTION.md execution and checkout decisions
downstream design ROOT_DELIVERY.md writing and delivery decisions
downstream implementation ../../tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py structural verification
@dependency-end
-->

## Repository Role

Optional source-only index. Use one matching starting section for an unresolved
decision; its owner selects any further detail. Known owners and unchanged
selections bypass the index. Generated consumers keep their own owner routes.

## Reader Map

| Active decision or operation | Start with |
| --- | --- |
| ChatGPT conversation closure or workspace execution is unresolved | [request modality](../internal-routines/chatgpt-codex-routing.md) |
| The next Codex task phase is unresolved | [workflow reader map](CODEX_WORKFLOW.md#reader-map) |
| Workflow, Skill, role, or handoff selection is unresolved | [orchestration decision order](../skills/agent-orchestration.md#decision-order) |
| A selected Skill's discovery path or command context is unresolved | [Skill paths](skills.md#skill-paths) |
| Contract, implementation mechanism, or simpler alternative must be chosen | [implementation decisions](ROOT_IMPLEMENTATION.md#simplest-complete-implementation) |
| Mathematical or numerical verification obligations must be allocated | [semantic responsibility contract](../../documents/design/semantic-responsibility-contract.md) |
| The selected design correspondence route is active | [design correspondence](../internal-routines/design-implementation-correspondence.md) |
| Execution failed or an execution-route change is authorized | [configured execution and bounded diagnosis](ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis) |
| Repository structure or responsibility boundaries change | [structure refactor](../skills/structure-refactor.md) |
| A document is added, split, moved, or removed | [placement and references](ARTIFACT_PLACEMENT.md#この文書の読み方) |
| Checkout or dependency identity changes | [checkout identity](ROOT_EXECUTION.md#checkout-and-dependency-identity) |
| A branch or annex operation is about to run | [branch and storage owners](ROOT_EXECUTION.md#branch-and-storage-owners) |
| A task-owned temporary checkout is no longer needed | [temporary checkout cleanup](ROOT_EXECUTION.md#temporary-checkout-cleanup) |
| AgentCanon source update or publication is requested | [AgentCanon update](../skills/agent-canon-update.md) |
| A team is selected, changed, or delegated | [team ownership](ROOT_EXECUTION.md#team-ownership) |
| Selected validation or closeout is due | [completion reader map](CODEX_COMPLETION.md#reader-map) |
| Any reader-facing text is about to be written | [reader-facing writing](ROOT_DELIVERY.md#reader-facing-writing) |
| Verification results are about to be reported | [result reporting](ROOT_DELIVERY.md#result-reporting) |
| Verification has failed | [failed verification record](../../documents/operations/notes-lifecycle.md#failed-verification-record) |
| Prior failed attempts may determine adoption or rejection | [retrieve before deciding](../../documents/operations/notes-lifecycle.md#retrieve-before-deciding) |
| Connected GitHub Issue or PR publication/status is requested | [connected publication](../skills/pr-processing.md#work-from-the-current-connected-session) |

## Always-On Boundary

Shared constraints remain in [ROOT_AGENTS.md](../../ROOT_AGENTS.md). This map
selects source owners; their active sections own procedures and further routes.
The reader map is neither a startup packet nor an execution checklist.

## Runtime Owner Map

| Responsibility | Canonical owner | Validation / reader route |
| --- | --- | --- |
| root runtime entrypoint | `bootstrap.sh` | `bash bootstrap.sh --help` |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| public skill registry | `agents/skills/catalog.yaml` | `check_agent_runtime_alignment.py` |
| AgentCanon source publication | [agents/skills/agent-canon-update.md](../skills/agent-canon-update.md) | repository-topic-clone and PR checks |
| entrypoint responsibility grammar | [documents/design/entrypoint-owner-map.md](../../documents/design/entrypoint-owner-map.md) | `check_entrypoint_owner_map.py` |
| implementation decision precedence | [engineering principles](../../documents/conventions/software-engineering-principles.md) | selected implementation/review evidence |

## Task Entry

Resolve request modality only while undecided. After admission, select only the
missing owner or phase and read its current-action section before proceeding.
Keep resolved decisions through retries, handoffs, and user updates unless their
premises change. Candidate roles and related Skills become active under their
owner's condition, not by appearing in a list.

## Validation Routing

Use the selected validation route for the affected contract. Reference existence
is checked by the existing docs route; grammar belongs to the entrypoint checker,
and applicability belongs to the selected workflow/Skill and its focused tests.
