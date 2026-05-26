#!/usr/bin/env python3
# @dependency-start
# responsibility Renders the runtime profile and check matrix doc from a machine-readable inventory.
# upstream design ../../documents/runtime-profiles-and-check-matrix.json runtime profile inventory source of truth
# downstream implementation ../../tools/agent_tools/check_runtime_profile_inventory.py drift checker compares rendered doc
# downstream implementation ../../documents/runtime-profiles-and-check-matrix.md rendered documentation
# @dependency-end
"""Render `documents/runtime-profiles-and-check-matrix.md` from JSON inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_INVENTORY = Path("documents/runtime-profiles-and-check-matrix.json")
DEFAULT_DOC = Path("documents/runtime-profiles-and-check-matrix.md")


DEPENDENCY_HEADER = """<!--
@dependency-start
responsibility Defines AgentCanon runtime profiles and risk-based validation routing.
upstream design ../ROOT_AGENTS.md root runtime entrypoint and closeout model
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
downstream design ../README.md AgentCanon repository overview
downstream design ../agents/canonical/CODEX_WORKFLOW.md Codex execution workflow
downstream design ./agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream implementation ../tools/ci/run_all_checks.sh repo check runner
downstream implementation ../tools/catalog.yaml structured tool catalog
@dependency-end
-->
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render runtime profile inventory markdown from JSON source of truth."
        )
    )
    parser.add_argument(
        "--inventory",
        default=str(DEFAULT_INVENTORY),
        help="Path to runtime profile inventory JSON.",
    )
    parser.add_argument(
        "--doc",
        default=str(DEFAULT_DOC),
        help="Path to generated markdown doc.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the rendered doc differs from the on-disk markdown.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the rendered markdown to --doc instead of printing to stdout.",
    )
    return parser


def load_inventory(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("inventory JSON must be an object")
    return raw


def render_paragraph(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_rows = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_row, separator_row, *body_rows]).rstrip() + "\n"


def render_doc(inventory: dict[str, object], inventory_rel_link: str) -> str:
    title = inventory.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("inventory.title must be a non-empty string")

    summary = inventory.get("summary")
    if not isinstance(summary, list) or not all(isinstance(s, str) for s in summary):
        raise ValueError("inventory.summary must be a list of strings")

    profile_classes = inventory.get("profile_classes")
    if not isinstance(profile_classes, list):
        raise ValueError("inventory.profile_classes must be a list")

    risk_classes = inventory.get("risk_classes")
    if not isinstance(risk_classes, list):
        raise ValueError("inventory.risk_classes must be a list")

    check_matrix = inventory.get("check_matrix")
    if not isinstance(check_matrix, list):
        raise ValueError("inventory.check_matrix must be a list")

    compatibility_note = inventory.get("compatibility_note")
    if not isinstance(compatibility_note, list) or not all(
        isinstance(s, str) for s in compatibility_note
    ):
        raise ValueError("inventory.compatibility_note must be a list of strings")

    risk_note = inventory.get("risk_note")
    if not isinstance(risk_note, list) or not all(isinstance(s, str) for s in risk_note):
        raise ValueError("inventory.risk_note must be a list of strings")

    closeout_rule = inventory.get("closeout_rule")
    if not isinstance(closeout_rule, list) or not all(
        isinstance(s, str) for s in closeout_rule
    ):
        raise ValueError("inventory.closeout_rule must be a list of strings")

    output = []
    output.append(DEPENDENCY_HEADER.rstrip() + "\n\n")
    output.append(f"# {title}\n\n")
    output.append(
        f"Source of truth: [{DEFAULT_INVENTORY.name}]({inventory_rel_link}).\n\n"
    )
    output.append(render_paragraph([str(s) for s in summary]) + "\n")

    output.append("## Profile Classes\n\n")
    profile_rows: list[list[str]] = []
    for item in profile_classes:
        if not isinstance(item, dict):
            raise ValueError("inventory.profile_classes entries must be objects")
        profile = item.get("profile")
        activates = item.get("activates")
        required_when = item.get("required_when")
        if not isinstance(profile, str) or not profile.strip():
            raise ValueError("profile_classes.profile must be a non-empty string")
        if not isinstance(activates, list) or not all(isinstance(s, str) for s in activates):
            raise ValueError("profile_classes.activates must be a list of strings")
        if not isinstance(required_when, str) or not required_when.strip():
            raise ValueError("profile_classes.required_when must be a non-empty string")
        profile_rows.append([profile, ", ".join(activates), required_when])
    output.append(render_table(["Profile", "Activates", "Required when"], profile_rows) + "\n")

    output.append(render_paragraph([str(s) for s in compatibility_note]) + "\n\n")

    output.append("## Risk Classes\n\n")
    risk_rows: list[list[str]] = []
    for item in risk_classes:
        if not isinstance(item, dict):
            raise ValueError("inventory.risk_classes entries must be objects")
        risk = item.get("risk")
        examples = item.get("examples")
        minimum_validation = item.get("minimum_validation")
        if not isinstance(risk, str) or not risk.strip():
            raise ValueError("risk_classes.risk must be a non-empty string")
        if not isinstance(examples, str) or not examples.strip():
            raise ValueError("risk_classes.examples must be a non-empty string")
        if not isinstance(minimum_validation, str) or not minimum_validation.strip():
            raise ValueError("risk_classes.minimum_validation must be a non-empty string")
        risk_rows.append([risk, examples, minimum_validation])
    output.append(render_table(["Risk", "Examples", "Minimum validation"], risk_rows) + "\n")

    output.append(render_paragraph([str(s) for s in risk_note]) + "\n\n")

    output.append("## Check Matrix\n\n")
    check_rows: list[list[str]] = []
    for item in check_matrix:
        if not isinstance(item, dict):
            raise ValueError("inventory.check_matrix entries must be objects")
        changed_surface = item.get("changed_surface")
        required_check = item.get("required_check")
        if not isinstance(changed_surface, str) or not changed_surface.strip():
            raise ValueError("check_matrix.changed_surface must be a non-empty string")
        if not isinstance(required_check, list) or not all(
            isinstance(s, str) for s in required_check
        ):
            raise ValueError("check_matrix.required_check must be a list of strings")
        check_rows.append([changed_surface, "; ".join(required_check)])
    output.append(render_table(["Changed surface", "Required check"], check_rows) + "\n")

    output.append("## Closeout Rule\n\n")
    output.append(render_paragraph([str(s) for s in closeout_rule]))

    return "".join(output).rstrip() + "\n"


def main() -> int:
    args = build_parser().parse_args()
    inventory_path = Path(args.inventory)
    doc_path = Path(args.doc)

    inventory = load_inventory(inventory_path)
    inventory_rel_link = Path(inventory_path.name).as_posix()
    rendered = render_doc(inventory, inventory_rel_link)

    if args.check:
        if not doc_path.exists():
            raise SystemExit(f"doc file missing: {doc_path}")
        current = doc_path.read_text(encoding="utf-8")
        if current != rendered:
            print("RUNTIME_PROFILE_INVENTORY_DOC=drift")
            print(f"Rendered doc differs from {doc_path}.")
            print(
                f"Run: python3 {Path(__file__).as_posix()} --write --doc {doc_path}"
            )
            return 1
        print("RUNTIME_PROFILE_INVENTORY_DOC=pass")
        return 0

    if args.write:
        doc_path.write_text(rendered, encoding="utf-8")
        return 0

    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

