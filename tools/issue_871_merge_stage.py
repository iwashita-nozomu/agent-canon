#!/usr/bin/env python3
"""Resolve the bounded #871/#874 semantic overlap on a staged merge tree."""

from __future__ import annotations

from pathlib import Path
import subprocess

MAIN = "979a2dd977a1afd3b2d349fa5da01b4f5cd46c7f"


def show(path: str) -> str:
    return subprocess.check_output(["git", "show", f"{MAIN}:{path}"], text=True)


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def merge_protocol() -> None:
    path = "agents/COMMUNICATION_PROTOCOL.md"
    text = read(path)
    if "## Owner and invalidation packets" not in text:
        source = show(path)
        start = source.index("## Owner and invalidation packets")
        anchor = "Before the generic runtime-event artifact exists"
        end = source.index(anchor, start)
        text = text.replace(anchor, source[start:end] + anchor, 1)
    write(path, text)


def merge_orchestration() -> None:
    path = "agents/skills/agent-orchestration.md"
    text = read(path)
    if "## Distributed owner correspondence" not in text:
        source = show(path)
        start = source.index("## Distributed owner correspondence")
        anchor = "### Canonical Skill Invocation Order"
        end = source.index(anchor, start)
        text = text.replace(anchor, source[start:end] + anchor, 1)
    write(path, text)


def merge_catalog() -> None:
    path = "agents/task_catalog.yaml"
    text = read(path)
    old_focus = (
        "Review roles provide their named findings; integration_executor owns "
        "merge/conflict resolution and ship_reviewer owns final approval."
    )
    merged_focus = (
        "Review roles provide hypotheses and named findings; owner-local receipts "
        "establish correspondence. The parent owns transport, dependency ordering, "
        "status reporting, and remote readback without approval or merge authority; "
        "integration_executor owns merge/conflict resolution and ship_reviewer owns "
        "final approval."
    )
    replacements = text.count(old_focus)
    if replacements < 6:
        raise RuntimeError(
            f"expected at least 6 task-catalog authority clauses, found {replacements}"
        )
    text = text.replace(old_focus, merged_focus)

    old_design = (
        "For analysis-heavy changes, require separate code dependency and header "
        "dependency evidence before design approval."
    )
    new_design = (
        "For analysis-heavy changes, require separate code dependency and header "
        "dependency evidence before implementation selection; design prose remains "
        "a proposal until an owner receipt establishes correspondence."
    )
    if old_design in text:
        text = text.replace(old_design, new_design, 1)
    write(path, text)


def merge_closeout() -> None:
    path = "tools/agent_tools/task_close.py"
    text = read(path)
    source = show(path)

    dependency = (
        "# upstream implementation ./packets.py owns owner-local receipt "
        "normalization and compatibility.\n"
    )
    if dependency not in text:
        anchor = (
            "# upstream implementation ./update_lifecycle_contract.py owns gate, "
            "cleanup, handback, and terminal ToolCall identities.\n"
        )
        if anchor not in text:
            raise RuntimeError("task_close dependency anchor missing")
        text = text.replace(anchor, anchor + dependency, 1)

    packet_import = next(
        line for line in source.splitlines() if line.startswith("from packets import ")
    ) + "\n"
    if packet_import not in text:
        anchor = "from autonomous_convergence import validate_closeout_projection\n"
        if anchor not in text:
            raise RuntimeError("task_close import anchor missing")
        text = text.replace(anchor, anchor + packet_import, 1)

    if "def owner_receipt_closeout_consumer(" not in text:
        start = source.index("OWNER_GUARANTEE_RECEIPTS_ARTIFACT_NAME")
        end = source.index("\n\ndef _resolve_report_root", start)
        block = source[start:end] + "\n\n"
        anchor = "def _resolve_report_root"
        if anchor not in text:
            raise RuntimeError("task_close function anchor missing")
        text = text.replace(anchor, block + anchor, 1)

    decision = "    owner_receipt_decision = owner_receipt_closeout_consumer(report_dir)\n"
    if decision not in text:
        anchor = (
            "    convergence_decision = "
            "validate_closeout_projection(review_convergence)\n"
        )
        if anchor not in text:
            raise RuntimeError("task_close decision anchor missing")
        text = text.replace(anchor, anchor + decision, 1)

    owner_check = (
        '        "owner_receipts_consumer": '
        'owner_receipt_decision.get("ready") is True,\n'
    )
    if owner_check not in text:
        anchor = (
            '        "completion_coverage_consumer": '
            'completion_decision.get("ready") is True,\n'
        )
        if anchor not in text:
            raise RuntimeError("task_close check anchor missing")
        text = text.replace(anchor, anchor + owner_check, 1)

    print_marker = '        "OWNER_RECEIPTS_CONSUMER="'
    if print_marker not in text:
        start = source.index('    print(\n        "OWNER_RECEIPTS_CONSUMER="')
        anchor = '    print(\n        "CAPACITY_LIFECYCLE_CLOSEOUT="'
        end = source.index(anchor, start)
        if anchor not in text:
            raise RuntimeError("task_close print anchor missing")
        text = text.replace(anchor, source[start:end] + anchor, 1)
    write(path, text)


def assert_integrated_contracts() -> None:
    required = {
        "agents/COMMUNICATION_PROTOCOL.md": (
            "agent-canon.communication-capability-handshake.v1",
            "agent-canon.coordination-receipt.v1",
            "### Parent Orchestration-Only Contract",
            "## Owner and invalidation packets",
        ),
        "agents/skills/agent-orchestration.md": (
            "## Distributed owner correspondence",
            "The integration executor performs",
            "the integration executor owns edit/revert/rollback integration",
        ),
        "agents/task_catalog.yaml": (
            "owner-local receipts establish correspondence",
            "without approval or merge authority",
            "integration_executor owns merge/conflict resolution",
            "ship_reviewer owns final approval",
        ),
        "tools/agent_tools/task_close.py": (
            "VERIFIER_RECEIPT_SCHEMA",
            "PARENT_MUTATION_EVIDENCE_SCHEMA",
            "def owner_receipt_closeout_consumer(",
            '"verifier_child_provenance"',
            '"parent_nonmutation_evidence"',
            '"owner_receipts_consumer"',
        ),
    }
    for path, markers in required.items():
        text = read(path)
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise RuntimeError(f"{path}: missing integrated markers: {missing}")


def main() -> None:
    merge_protocol()
    merge_orchestration()
    merge_catalog()
    merge_closeout()
    assert_integrated_contracts()


if __name__ == "__main__":
    main()
