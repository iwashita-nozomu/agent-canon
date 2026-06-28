# P7-P8 Research, Audit, And Retirement Checklist
<!--
@dependency-start
contract reference
responsibility Defines research, experiment, documentation, audit, metrics, and retirement checks for the completion-first review.
upstream design ../README.md completion-first review index
upstream design ../explanation/01-priority-layers.md priority layer explanation
upstream design ../../agents/workflows/research-workflow.md research workflow
upstream design ../../agents/workflows/experiment-workflow.md experiment workflow
upstream design ../../agents/workflows/agent-learning-workflow.md learning promotion workflow
@dependency-end
-->

## Reader Map

Use this checklist after completion judgment, evidence tooling, MCP honesty,
self-growth, surface ownership, and workflow contracts are in place. Read Scope
first, then P7 for research, experiment, claim, and documentation rigor. P8
covers audit, metrics, and retirement, and the final done condition states when
these late-layer checks are complete.

## Scope

P7 and P8 come after completion judgment, mechanical evidence, MCP honesty, self-growth, surface ownership, and workflow/skill contracts. They focus on durable claims, experiment rigor, long-form documentation consistency, and canon retirement.

## P7: research, experiment, claim, and docs rigor

### [ ] P7-001: claim ledger

- Target: research and long-form documentation outputs.
- Problem: durable claims can be added without explicit evidence.
- Violation: README or workflow claims are updated because an experiment seemed promising, but no claim-to-evidence mapping exists.
- Action: create `claim_ledger.md` or equivalent per run/report.
- Acceptance: every durable claim has `claim_id`, evidence path, confidence, and counterevidence field.

### [ ] P7-002: formal experiment manifest

- Target: experiment runs.
- Problem: debug and smoke runs can be treated as formal evidence.
- Violation: a partial debug run supports a durable claim.
- Action: require `run_type=formal|debug|smoke` and `comparison_allowed=yes|no` in `run_manifest.json`.
- Acceptance: claim ledger rejects non-formal runs as durable evidence.

### [ ] P7-003: source freshness ledger

- Target: research-backed docs and workflows.
- Problem: currentness of external information is unclear.
- Violation: old library or platform behavior is treated as current.
- Action: track source date, accessed date, currentness status, and replacement risk.
- Acceptance: stale or undated sources cannot support current operational claims without review.

### [ ] P7-004: counterevidence requirement

- Target: research claims.
- Problem: only supporting evidence is recorded.
- Violation: a claim is promoted while plausible counterexamples are ignored.
- Action: add counterevidence or counterexample review to claim ledger.
- Acceptance: high-impact claims without counterevidence review fail research closeout.

### [ ] P7-005: long-form contradiction scan

- Target: long-form docs, workflow docs, and migration guides.
- Problem: long documents can accumulate internal contradictions.
- Violation: one chapter says completion-first, another says agent settings are first.
- Action: create a consistency matrix or contradiction scan.
- Acceptance: unresolved contradictions block strict doc closeout.

### [ ] P7-006: term and command consistency

- Target: docs and guides.
- Problem: same term or command can drift across chapters.
- Violation: `ci-quick`, `ci`, and `ci-full` are used interchangeably.
- Action: record canonical term/command table.
- Acceptance: non-canonical command usage is resolved or justified.

### [ ] P7-007: artifact placement check

- Target: experiment outputs, reports, notebooks, generated data.
- Problem: important artifacts can be saved in arbitrary paths.
- Violation: notebook result is outside `reports/` or experiment result layout.
- Action: run artifact placement checker.
- Acceptance: required artifacts are under expected paths or explicitly linked.

### [ ] P7-008: formal report gate

- Target: experiment and research reports.
- Problem: report can summarize incomplete work as final.
- Violation: partial run is described as conclusive.
- Action: require report status: draft, partial, formal, or rejected.
- Acceptance: only formal reports can support durable claims.

## P8: audit, metrics, and retirement

### [ ] P8-001: executable audit profiles

- Target: repository audit checklist.
- Problem: huge checklists are hard to apply consistently.
- Action: define quick, strict, self-growth, release, and derived-repo audit profiles.
- Acceptance: audit runner produces profile-specific pass/fail report.

### [ ] P8-002: growth metrics

- Target: self-growth runs.
- Problem: learning is not measured.
- Action: track replay pass rate, false-negative reduction, unresolved feedback count, duplicate rule count, and retired rule count.
- Acceptance: self-growth closeout includes updated `growth_metrics.json`.

### [ ] P8-003: learning retirement sweep

- Target: memory, workflow rules, skill rules.
- Problem: canon grows without cleanup.
- Action: add `review_after`, `expiry`, `superseded_by`, or no-retirement rationale to durable learning items.
- Acceptance: expired or superseded items appear in retirement report.

### [ ] P8-004: duplicate rule detector

- Target: AGENTS, workflows, skills, memory.
- Problem: same rule can appear in many forms.
- Violation: completion requirements are repeated in ROOT_AGENTS and workflow docs with slight wording differences.
- Action: run similarity or rule-id based duplicate detection.
- Acceptance: duplicate rules are merged, scoped, or justified.

### [ ] P8-005: compatibility wrapper lifecycle

- Target: tool catalog.
- Problem: compatibility wrappers can become permanent.
- Action: add `deprecate_after`, `replacement`, and `removal_gate` metadata.
- Acceptance: old wrappers have retirement plans.

### [ ] P8-006: audit of verifier false positives

- Target: completion verifier and schemas.
- Problem: stricter gates may block legitimate work.
- Action: track accepted exceptions and false-positive reports.
- Acceptance: repeated false positives create self-growth repair items.

### [ ] P8-007: audit of verifier false negatives

- Target: completion verifier and negative fixture catalog.
- Problem: discovered false negatives may remain prose only.
- Action: require fixture or explicit unrepresentable reason.
- Acceptance: false negative catalog has no unprocessed entries.

### [ ] P8-008: periodic canon simplification

- Target: top-level entrypoints and workflow docs.
- Problem: completion-first improvements can increase document size and complexity.
- Action: periodically move detailed rules from entrypoints into canonical docs and contracts.
- Acceptance: entrypoints remain thin and point to authority surfaces.

## P7-P8 done condition

- [ ] Durable claims have formal evidence.
- [ ] Long docs have contradiction checks.
- [ ] Audit profiles are executable.
- [ ] Self-growth has metrics.
- [ ] Rules can retire.
- [ ] Compatibility wrappers have lifecycle.
