# AgentCanon Consumer Instructions

<!--
@dependency-start
contract agent-runtime
responsibility Provides the portable minimum shared by source and consumer roots.
upstream design documents/design/entrypoint-owner-map.md reading and composition boundary
downstream implementation tools/runtime/dispatch/agent-canon/src/entrypoint_composer.rs consumer composition
@dependency-end
-->

## Repository Role

Consumers own their product, environment, tests, credentials, and local
instructions. Their generated [AGENTS.md](AGENTS.md) is self-contained and needs
no AgentCanon checkout/runtime. Subtree instructions add local requirements
without copying parent or Skill policy.

## Reader Map

Read applicable instructions and the selected owner; consult an index only for
an unresolved owner and conditional references only when needed. Reuse unchanged
context/evidence. The contracts below apply without an installed Skill/runtime.

## Always-On Boundary

- **Authority:** the latest explicit user agreement defines outcome, acceptance,
  and authority. Current conversation instructions override repository/Skill
  guidance and past procedures, subject to system/developer instructions.
  Preserve explicit read limits across continuation, handoff, and Skill use,
  including instructions, Issues, and logs; continue authorized work from known
  facts when further reading is forbidden. Honor agreed stop boundaries.
- **State and scope:** confirm checkout/revision; preserve unknown Git state and
  user data. Task authority excludes unrelated changes/publication. Code cleanup
  must reduce the owning implementation while preserving guarantees; unrelated
  document/artifact deletion does not offset source growth. Functional expansion
  needs separate current-user agreement.
- **Memory safety:** preserve ownership, lifetimes, access bounds, and
  synchronization before performance or implementation convenience.
- **Reuse:** extend the existing capability owner first. A separate implementation
  needs a concrete requirement, responsibility, or contract gap extension cannot fill.
- **Investigation:** start local repair at target code, diff, and contract, without
  requiring use-site/out-of-scope investigation. For an unresolved decision, state
  the missing fact and smallest needed reference. Cross-module/API migrations use
  their declared dependency scope only.
- **Correctness:** follow current requirements and input/output contracts while
  preserving external boundaries. History explains causes, not correctness;
  restore old behavior only when required. Source and applicable tests can establish
  a stale description: follow established in-scope behavior and report the mismatch,
  while keeping governing requirements, authorized migrations, safety, and permissions.
  Record consequential changes at their owner: why needed, why the old approach did
  not fit, and retained/retired behavior; consult this rationale when reconsidering.
- **Repair:** compare expected/actual inputs, outputs, and what the target consumed.
  Inspect only the relevant target boundary.
  For another responsibility's failure, also compare completed behavior and recorded
  purpose; preserve shared purpose/invariants, distinguish changed inputs, and extend the
  existing contract/type/interface/abstraction when required valid cases need it. Fix the
  established cause and rerun the selected route. Preserve an interrupted task's
  target, operation, and acceptance in its existing record; resume it after repair.
  Cause-local success is not task completion. No speculative guards, fallbacks,
  retries, gates, or hypothetical-input layers; never alter tests or switch routes
  just to pass. Distinguish observations, established causes, and unverified results.
- **Transport:** use configured Git/GitHub transports. Do not discover, create,
  copy, link, or configure credentials/auth agents; return auth failures to the owner.
- **Experiment context:** before work, record the origin base ref and exact commit,
  purpose/research question, and intended delta in the existing branch README, plan,
  or task record. Keep that origin immutable and later comparison bases separate.
  Carry this context through progress, handoff, and resumption; compare actual
  diff/evidence with the purpose. Ask only about genuinely unsettled major direction,
  otherwise proceed from the known agreement without new manifests or paperwork.
- **Experiment branches:** keep topic code/config on its experiment branch and
  active raw logs in ignored scratch. Preserve reproduction inputs, execution commit,
  and selected archived evidence. Complete its manuscript and selected report
  before closing the research experiment branch;
  retain a self-contained, arXiv-quality manuscript source at the project's existing
  manuscript owner/path, grounded in the actual question, related work, method,
  evidence/results, limitations, and reproduction. State missing evidence honestly;
  this requires neither arXiv upload nor a new paper for each run. For experiment
  repositories, `main` retains shared models/helpers, execution/regression infrastructure,
  concise completed `summary.md` files, and stable manuscript/result/archive references
  with retrieval method, execution commit, results, and limits. Preserve the manuscript
  and these references before retiring topic/diagnostic code or deleting its branch.
  Treat closed verification/diagnosis separately; ordinary product code may live on `main`.

## Runtime Owner Map

| Responsibility | Consumer owner |
| --- | --- |
| product implementation and behavior | consumer source and design owners |
| build, tests, and runtime environment | consumer build and test owners |
| repository structure and file placement | consumer structure owner |
| root instruction extension | consumer-specific section in this file |
| AgentCanon source maintenance | selected AgentCanon development checkout |

## Task Entry

- The selected workflow owns execution, delegation, and validation; activate
  specialists only when applicable. AgentCanon maintenance does not authorize
  edits to consumers' generated instructions.
- Prefer the current agent. Delegate when explicit requirements, needed independent
  judgment, or separable parallel work justify transfer/integration cost.
- Complete the authorized in-scope outcome, including existing failures; diagnosis,
  checkpoints, and no-op checks are insufficient. Each owner completes its repair
  unit and required check before another; independent units may proceed in parallel.
  If blocked, name the failed operation, unverified property, and next owner/action;
  finish independent work.
- Report commit/push separately and distinguish implemented, verified, published,
  and applied. Support claims with source, checked derivation, or the owner's
  operation; disclose material uncertainty/limits without exposing secrets.

## Validation Routing

Validate changed guarantees, adding consumer checks for explicit consumer migration.
Reuse unchanged results; broaden suites only when those guarantees require it.
Format final edited files with the configured formatter before delivery and include
its diff; unavailable formatting stays unverified. Tests, observations, and proofs
establish different properties: report only what the evidence establishes.
