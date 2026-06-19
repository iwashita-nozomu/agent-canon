# OOP Hook Warning Mode

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where the OOP readability hook blocked ordinary editing instead of warning and leaving enforcement to validation gates.
upstream design ../README.md defines durable AgentCanon operational issue conventions.
upstream implementation ../../.codex/hooks/oop_readability_guard.py runs changed-source OOP checks after editing tools.
upstream implementation ../../.codex/hooks.json wires the OOP readability hook.
upstream implementation ../../tools/oop/python/readability.py provides the Python OOP analyzer used by the hook.
upstream implementation ../../tools/oop/cpp/readability.py provides the C++ OOP analyzer used by the hook.
downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates OOP hook behavior.
downstream design ../../documents/runtime-log-archive.md documents hook-run result semantics.
@dependency-end
-->

issue_id: AC-20260519-oop-hook-warning-mode
status: resolved
source: user
severity: S2
evidence: reports/dependency-review/oop-hook-warning-mode-20260519/search_hits.txt
affected_surfaces: .codex/hooks/oop_readability_guard.py, .codex/hooks.json, tests/agent_tools/test_codex_hooks.py, documents/runtime-log-archive.md
edit_scope: reports/dependency-review/oop-hook-warning-mode-20260519/dependency_edit_scope.txt
required_action: Change the OOP readability hook from a source-edit blocker to a warning/logging hook while keeping explicit readability validation available as a closeout gate.
close_condition: OOP hook findings no longer stop editing tools, hook logs preserve warning evidence, and targeted hook tests cover the warning behavior.
github_issue: pending
resolved_by: PR #144; the OOP hook warning path approves edits while preserving finding evidence, and targeted hook tests cover warning behavior.
resolved_at: 2026-06-07

## Finding

On 2026-05-19, the OOP readability hook emitted a Codex `decision=block` after a
dependency-header-only edit touched Python files with pre-existing OOP findings.
That stopped ordinary editing even though the finding was not introduced by the
header change and should have been handled by an explicit validation or closeout
gate.

## Impact

The hook turned existing OOP debt into an immediate tool-level blocker. This
made unrelated small edits harder to complete, and it encouraged scope creep
toward repairing broad model-code OOP findings during a focused experiment
runner change.

## Required Fix

The hook should keep collecting evidence, but it should not stop editing tools
for readability findings. The intended split is:

1. Hook invocation logs changed-source OOP analyzer output.
1. Codex receives a warning/approve payload rather than `decision=block`.
1. Dedicated validation commands such as `tools/oop/python/readability.py` still
   fail when used as explicit gates.
1. Closeout can decide whether to fix, document, or defer the warning based on
   the active request scope.

## Evidence

Durable surface search was recorded at
`reports/dependency-review/oop-hook-warning-mode-20260519/search_hits.txt`.
The immediate failure was observed when `apply_patch` completed the file edit
but returned an OOP hook block for pre-existing findings in
`python/docomo_bt_management/model/models/calculate.py`.
