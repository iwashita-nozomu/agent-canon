# python-review
<!--
@dependency-start
contract skill
responsibility Reviews Python changes for selected type, API, lint, test, readability, and OOP risks without freezing helper order.
upstream design ../canonical/skills.md skill canon registry
upstream design ./catalog.yaml public skill and capability projection
upstream design ./skill-dependencies.yaml prerequisite and reviewer order
upstream design ./agent-orchestration.md canonical validation trust boundary owner
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and sparse Python projection
upstream design ../../documents/design/responsibility-rationale.md Python readability and OOP-review activation rationale
@dependency-end
-->

## Purpose

Review Python diffs against the owning API/type/runtime contract and the exact validation route selected by the parent workflow. This reviewer does not expand every Python change into full-suite, OOP, SOLID, or layout work.

## Validation selection

Run the exact parent-selected commands and any additional static/read-only confirmation needed by the changed mechanism. Pyright, Ruff/quality checks, convention checks, targeted tests, or docstring review are selected when their contracts are reachable. `pytest tests/` is not automatically added by this reviewer.

## OOP/SOLID sensitivity

Select OOP/SOLID evidence only when the diff changes inheritance/substitutability, responsibility ownership, stateful lifecycle/mutation, dependency inversion/DI, factory/plugin boundaries, or a public object model. Annotation-only edits, bounded dataclass/parser models, simple typed payloads, and ordinary helper functions do not activate SOLID review by category alone.

## Readability

Helper placement is guidance, not a blocking contract. A helper need not immediately follow its sole caller, and shared helpers need not be physically placed after public entries. Raise a blocking readability finding only for a concrete failure such as:

- cyclic or inverted dependencies;
- duplicated responsibility/logic that can diverge;
- public/private API ambiguity;
- state ownership or side effects that are materially hard to trace;
- naming/layout that demonstrably obscures a safety/correctness boundary.

Do not create a line/order checker or exact-layout test.

## Review outcome

Report findings first, distinguish blocking from advisory items, and tie each blocking item to the API/type/runtime contract or a concrete maintenance failure. Reuse `change-review` for durable follow-up escalation; ordinary resolved Python findings do not require issue publication.
