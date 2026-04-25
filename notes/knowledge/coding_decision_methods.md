# Coding Decision Methods
<!--
@dependency-start
@dependency-end
-->


## Scope

- Reuse surface: coding tasks, implementation plans, code review follow-up, and closeout checks.
- Applies when: changing code, scripts, tests, agent workflow files, or technical docs that describe executable behavior.
- Does not apply when: the task is pure translation, casual chat, or a one-off command with no durable decision.

## Known

- Source: IEEE Computer Society, [SWEBOK Guide v4.0a](https://ieeecs-media.computer.org/media/education/swebok/swebok-v4.pdf), Software Construction KA.
- Coding skill is not only writing statements. Treat construction as coding plus detailed design, debugging, unit/integration testing, construction planning, dependency management, quality work, and feedback loops.
- Prioritize readable, simple code over clever code. SWEBOK frames complexity reduction as a central construction goal, supported by standards, modular design, and quality techniques.
- Build for verification while coding: organize code for automated tests, follow coding standards that make review feasible, avoid hard-to-understand constructs, and add useful logs when behavior needs later diagnosis.
- Reuse existing assets before creating new ones. SWEBOK lists frameworks, libraries, modules, components, source code, and COTS assets as construction reuse candidates; in this repo, that maps to searching `python/`, `tests/`, `src/`, `include/`, `lib/`, `tools/`, and `scripts/` before adding new paths.
- Keep dependency decisions explicit. New dependencies can improve productivity, but they also add supply-chain, license, defect, vulnerability, and build-efficiency risk.
- Use test-first thinking when behavior is unclear. Even when not practicing strict TDD, writing or sketching the failing case first forces requirements and design gaps to surface before implementation.
- Use early feedback loops. Prefer small validated increments with automated checks over large unvalidated rewrites.

## Coding Task Decision Ladder

- Requirements: map every user-visible requirement to a clause in `user_request_contract.md`; do not implement from conversation memory alone when repo context can resolve details.
- Reuse: search local docs and code for existing patterns, helpers, scripts, tests, and known failures before introducing a new file, helper, or workflow branch.
- Options: list viable options only when the choice changes behavior, maintainability, risk, cost, or future reversibility.
- Quality attributes: choose based on correctness, maintainability, readability, testability, security, performance, reliability, and operational risk; do not argue from personal preference when technical evidence or local style applies.
- Verification: define the failing case, smoke, unit, integration, doc, or manual evidence before or during implementation, not after closeout.
- Review integration: convert reviewer confusion into clearer code or docs first; use review-thread explanations only when the product surface is already clear.
- Closeout: finish only when each must-do and completion-evidence clause maps to a concrete code/doc/test/command artifact, and every fix-now review finding is fixed, escalated, or explicitly accepted as follow-up.

## Architecture And Design Decisions

- Source: Carnegie Mellon SEI, [The Architecture Tradeoff Analysis Method](https://www.sei.cmu.edu/library/the-architecture-tradeoff-analysis-method/).
- Use a tradeoff lens for architectural or cross-cutting implementation choices. ATAM evaluates architecture fitness across competing quality attributes such as modifiability, security, performance, and availability; improving one can worsen another.
- For significant decisions, record:
  - context and constraint
  - options considered
  - chosen option
  - rejected options and why
  - quality-attribute tradeoffs
  - validation evidence
  - rollback or supersession path
- Source: GOV.UK GDS, [Documenting architecture decisions](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html).
- ADRs are useful when a decision affects service architecture or future change context. Keep them in version control and include title, status, context, decision, and positive/negative consequences.
- The decision is not done just because an ADR exists. GDS explicitly treats unimplemented ADRs as follow-up work; in this repo, closeout must stay locked until the decision has product evidence or an explicit deferred/rejected clause.

## Code Review Decision Rules

- Source: Google, [The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html).
- Prefer code health improvement over perfection. A change can be accepted when it definitely improves the worked-on system, but not when it definitely worsens overall code health.
- Technical facts, data, and project standards outrank opinion. If no other rule applies, follow current codebase consistency as long as it does not worsen code health.
- Source: Google, [What to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html).
- Review design, functionality, complexity, tests, names, comments, style, consistency, documentation, every relevant line, and broader system context.
- Watch for over-engineering: solving speculative future problems is a review risk, but this is different from stopping at a partial implementation. The right target is complete requested behavior with no unnecessary generality.
- Tests should match the risk and should usually land with production-code changes. Tests themselves must be readable, useful, and capable of failing when behavior breaks.
- Comments should usually explain why, not restate what. If a reviewer cannot understand code, first clarify the code; add a comment only when the reason cannot live in the code itself.
- Source: Google, [Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html).
- Keep changes self-contained and reviewable, include related tests, and separate large refactors from behavior changes when that improves review quality and rollback.
- Small does not mean incomplete. A small change still needs enough context, usage, tests, and working behavior for reviewers and future developers.
- Source: Google, [How to handle reviewer comments](https://google.github.io/eng-practices/review/developer/handling-comments.html).
- If a reviewer flags confusion, improve the code or docs before relying on a review comment. If disagreeing, frame the answer around tradeoffs and the original goal.

## Repo Use

- Before coding: run the required startup checks, fill `user_request_contract.md`, and search local docs/code for reuse candidates.
- During coding: keep implementation tied to clause IDs and avoid mixing unrelated refactors, protocol changes, runtime flags, or performance experiments into the same change unless the contract requires it.
- During review: require review artifacts to state spec-to-product gaps and unapplied findings; the implementation is not complete while such gaps remain.
- During closeout: `closeout_gate.md` must have `spec_product_coverage_complete: yes` and `review_findings_integrated: yes`; `task_close.py` should be the mechanical final gate.

## Practical Commands Or Paths

- `python3 tools/agent_tools/bootstrap_agent_run.py --task "<task>" --task-id T1 --owner codex --workspace-root "$PWD"`
- `python3 tools/agent_tools/task_close.py --report-dir <reports/agents/run-id>`
- `notes/knowledge/`
- `reports/agents/<run-id>/user_request_contract.md`
- `reports/agents/<run-id>/closeout_gate.md`

## References

- IEEE Computer Society, [SWEBOK Guide v4.0a](https://ieeecs-media.computer.org/media/education/swebok/swebok-v4.pdf), Software Construction KA, accessed 2026-04-10.
- Carnegie Mellon SEI, [The Architecture Tradeoff Analysis Method](https://www.sei.cmu.edu/library/the-architecture-tradeoff-analysis-method/), 1998, accessed 2026-04-10.
- Google Engineering Practices, [The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html), accessed 2026-04-10.
- Google Engineering Practices, [What to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html), accessed 2026-04-10.
- Google Engineering Practices, [Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html), accessed 2026-04-10.
- Google Engineering Practices, [How to handle reviewer comments](https://google.github.io/eng-practices/review/developer/handling-comments.html), accessed 2026-04-10.
- GOV.UK Government Digital Service, [Documenting architecture decisions](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html), reviewed 2026-03-05, accessed 2026-04-10.
