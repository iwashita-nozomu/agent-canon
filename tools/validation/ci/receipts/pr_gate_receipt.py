#!/usr/bin/env python3
"""Read and write the source-owned PR dependency gate receipt.

The receipt is a small process-bound handoff between the PR source gate and
the follow-up CI consumer.  This module is the only owner of its keys and
status enum; shell callers must consume the validated ``status=...`` result
instead of parsing receipt text themselves.
"""

# @dependency-start
# contract tool
# responsibility Owns the source/skipped PR dependency gate receipt schema and binding validation.
# upstream design ../../../../documents/design/source-owned-dependency-validation.md source-owned PR receipt contract
# downstream implementation ../checks/check_agent_canon_pr.sh writes the validated receipt
# downstream implementation ../runners/run_all_checks.sh consumes the validated receipt
# downstream implementation ../../../../tests/tools/test_pr_gate_receipt.py exercises schema and binding rejection
# downstream implementation ../../../../tests/tools/test_pr_gate_receipt_round_trip.py exercises writer/parser/consumer round trips
# @dependency-end

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PrGateDependencyStatus(str, Enum):  # noqa: UP042
    """The two source-owned states carried by a PR gate receipt."""

    SOURCE = "source"
    SKIPPED = "skipped"


_OWNER = "check_agent_canon_pr.sh"
_FIELDS = (
    "owner",
    "root_identity",
    "parent_pid",
    "strict_dependency",
    "graph",
    "selector_reason",
    "selector_evidence",
)
_FIELD_SET: frozenset[str] = frozenset(_FIELDS)
_PID_RE = re.compile(r"[1-9][0-9]*\Z")


class ReceiptError(ValueError):
    """Raised when receipt bytes do not satisfy the source-owned contract."""


@dataclass(frozen=True)
class PrGateReceipt:
    """Canonical, already-validated receipt values."""

    owner: str
    root_identity: str
    parent_pid: int
    status: PrGateDependencyStatus
    selector_reason: str
    selector_evidence: str


def _single_line(name: str, value: str) -> str:
    if not value or "\n" in value or "\r" in value:
        raise ReceiptError(f"{name} must be a non-empty single-line value")
    return value


def _parse_fields(text: str) -> dict[str, str]:
    if not text or not text.endswith("\n"):
        raise ReceiptError("receipt must be newline-terminated")
    fields: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line or "=" not in line:
            raise ReceiptError(f"malformed receipt line {line_number}")
        key, value = line.split("=", 1)
        if key not in _FIELD_SET:
            raise ReceiptError(f"unknown receipt key: {key}")
        if key in fields:
            raise ReceiptError(f"duplicate receipt key: {key}")
        fields[key] = value
    missing_keys = [key for key in _FIELDS if key not in fields]
    if missing_keys:
        missing = ",".join(missing_keys)
        raise ReceiptError(f"missing receipt keys: {missing}")
    return fields


def parse_receipt(text: str) -> PrGateReceipt:
    """Parse and validate receipt bytes without external identity binding."""
    fields = _parse_fields(text)
    if fields["owner"] != _OWNER:
        raise ReceiptError("receipt owner mismatch")
    root_identity = _single_line("root_identity", fields["root_identity"])
    if not os.path.isabs(root_identity) or os.path.normpath(root_identity) != root_identity:
        raise ReceiptError("root_identity must be a normalized absolute path")
    parent_pid_text = _single_line("parent_pid", fields["parent_pid"])
    if not _PID_RE.fullmatch(parent_pid_text):
        raise ReceiptError("parent_pid must be a positive decimal PID")
    status_text = _single_line("strict_dependency", fields["strict_dependency"])
    graph_status = _single_line("graph", fields["graph"])
    try:
        status = PrGateDependencyStatus(status_text)
    except ValueError as exc:
        raise ReceiptError(f"unsupported receipt status: {status_text}") from exc
    if graph_status != status.value:
        raise ReceiptError("strict_dependency and graph statuses differ")
    selector_reason = _single_line("selector_reason", fields["selector_reason"])
    selector_evidence = _single_line("selector_evidence", fields["selector_evidence"])
    return PrGateReceipt(
        owner=_OWNER,
        root_identity=root_identity,
        parent_pid=int(parent_pid_text),
        status=status,
        selector_reason=selector_reason,
        selector_evidence=selector_evidence,
    )


def validate_receipt(
    text: str,
    *,
    expected_root: str | None = None,
    expected_parent_pid: int | None = None,
) -> PrGateReceipt:
    """Validate receipt bytes and optional caller-owned identity bindings."""
    receipt = parse_receipt(text)
    if expected_root is not None:
        root = Path(expected_root).resolve(strict=True)
        if receipt.root_identity != os.path.normpath(str(root)):
            raise ReceiptError("receipt root identity mismatch")
    if expected_parent_pid is not None and receipt.parent_pid != expected_parent_pid:
        raise ReceiptError("receipt parent PID mismatch")
    return receipt


def serialize_receipt(
    *,
    root: str,
    parent_pid: int,
    status: str,
    selector_reason: str,
    selector_evidence: str,
) -> str:
    """Build canonical receipt bytes after validating all supplied values."""
    root_identity = os.path.normpath(str(Path(root).resolve(strict=True)))
    if not _PID_RE.fullmatch(str(parent_pid)):
        raise ReceiptError("parent_pid must be a positive decimal PID")
    try:
        canonical_status = PrGateDependencyStatus(status)
    except ValueError as exc:
        raise ReceiptError(f"unsupported receipt status: {status}") from exc
    reason = _single_line("selector_reason", selector_reason)
    evidence = _single_line("selector_evidence", selector_evidence)
    text = (
        f"owner={_OWNER}\n"
        f"root_identity={root_identity}\n"
        f"parent_pid={parent_pid}\n"
        f"strict_dependency={canonical_status.value}\n"
        f"graph={canonical_status.value}\n"
        f"selector_reason={reason}\n"
        f"selector_evidence={evidence}\n"
    )
    validate_receipt(text, expected_root=root_identity, expected_parent_pid=int(parent_pid))
    return text


def _read_receipt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReceiptError(f"unable to read receipt: {path}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    write = subparsers.add_parser("write", help="write canonical receipt bytes")
    write.add_argument("--root", required=True)
    write.add_argument("--parent-pid", required=True, type=int)
    write.add_argument("--status", required=True)
    write.add_argument("--selector-reason", required=True)
    write.add_argument("--selector-evidence", required=True)

    validate = subparsers.add_parser("validate", help="validate and print one status")
    validate.add_argument("--receipt", required=True, type=Path)
    validate.add_argument("--root")
    validate.add_argument("--parent-pid", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the receipt writer or validator command."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "write":
            sys.stdout.write(
                serialize_receipt(
                    root=args.root,
                    parent_pid=args.parent_pid,
                    status=args.status,
                    selector_reason=args.selector_reason,
                    selector_evidence=args.selector_evidence,
                )
            )
        else:
            receipt = validate_receipt(
                _read_receipt(args.receipt),
                expected_root=args.root,
                expected_parent_pid=args.parent_pid,
            )
            print(f"status={receipt.status.value}")
    except (OSError, ReceiptError) as exc:
        print(f"PR_GATE_RECEIPT=invalid reason={exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
