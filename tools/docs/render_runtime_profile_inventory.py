#!/usr/bin/env python3
# @dependency-start
# contract tool
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
contract reference
responsibility Defines AgentCanon runtime profiles and risk-based validation routing.
upstream design ../ROOT_AGENTS.md root runtime entrypoint and closeout model
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
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


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def require_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return list(value)


def require_object_list(value: object, field: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    objects: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field} entries must be objects")
        objects.append(item)
    return objects


def collect_profile_class_rows(items: list[dict[str, object]]) -> list[list[str]]:
    profile_rows: list[list[str]] = []
    for item in items:
        profile = require_string(item.get("profile"), "profile_classes.profile")
        activates = require_string_list(
            item.get("activates"),
            "profile_classes.activates",
        )
        required_when = require_string(
            item.get("required_when"),
            "profile_classes.required_when",
        )
        profile_rows.append([profile, ", ".join(activates), required_when])
    return profile_rows


def collect_risk_class_rows(items: list[dict[str, object]]) -> list[list[str]]:
    risk_rows: list[list[str]] = []
    for item in items:
        risk = require_string(item.get("risk"), "risk_classes.risk")
        examples = require_string(item.get("examples"), "risk_classes.examples")
        required_validation = require_string(
            item.get("required_validation"),
            "risk_classes.required_validation",
        )
        risk_rows.append([risk, examples, required_validation])
    return risk_rows


def collect_check_matrix_rows(items: list[dict[str, object]]) -> list[list[str]]:
    check_rows: list[list[str]] = []
    for item in items:
        changed_surface = require_string(
            item.get("changed_surface"),
            "check_matrix.changed_surface",
        )
        required_check = require_string_list(
            item.get("required_check"),
            "check_matrix.required_check",
        )
        check_rows.append([changed_surface, "; ".join(required_check)])
    return check_rows


def bridge_inventory_to_markdown(inventory: dict[str, object], inventory_rel_link: str) -> str:
    title = require_string(inventory.get("title"), "inventory.title")
    summary = require_string_list(inventory.get("summary"), "inventory.summary")
    profile_classes = require_object_list(
        inventory.get("profile_classes"),
        "inventory.profile_classes",
    )
    risk_classes = require_object_list(
        inventory.get("risk_classes"),
        "inventory.risk_classes",
    )
    check_matrix = require_object_list(
        inventory.get("check_matrix"),
        "inventory.check_matrix",
    )
    compatibility_note = require_string_list(
        inventory.get("compatibility_note"),
        "inventory.compatibility_note",
    )
    risk_note = require_string_list(inventory.get("risk_note"), "inventory.risk_note")
    closeout_rule = require_string_list(
        inventory.get("closeout_rule"),
        "inventory.closeout_rule",
    )

    output = []
    output.append(DEPENDENCY_HEADER.rstrip() + "\n\n")
    output.append(f"# {title}\n\n")
    output.append(
        f"Source of truth: [{DEFAULT_INVENTORY.name}]({inventory_rel_link}).\n\n"
    )
    output.append(render_paragraph(summary) + "\n")

    output.append("## Profile Classes\n\n")
    profile_rows = collect_profile_class_rows(profile_classes)
    output.append(render_table(["Profile", "Activates", "Required when"], profile_rows) + "\n")

    output.append(render_paragraph(compatibility_note) + "\n\n")

    output.append("## Risk Classes\n\n")
    risk_rows = collect_risk_class_rows(risk_classes)
    output.append(render_table(["Risk", "Examples", "Required validation"], risk_rows) + "\n")

    output.append(render_paragraph(risk_note) + "\n\n")

    output.append("## Check Matrix\n\n")
    check_rows = collect_check_matrix_rows(check_matrix)
    output.append(render_table(["Changed surface", "Required check"], check_rows) + "\n")

    output.append("## Closeout Rule\n\n")
    output.append(render_paragraph(closeout_rule))

    return "".join(output).rstrip() + "\n"


def main() -> int:
    args = build_parser().parse_args()
    inventory_path = Path(args.inventory)
    doc_path = Path(args.doc)

    inventory = load_inventory(inventory_path)
    inventory_rel_link = Path(inventory_path.name).as_posix()
    rendered = bridge_inventory_to_markdown(inventory, inventory_rel_link)

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
