#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Forwards the legacy non-canonical document inventory CLI to the Rust structured-analysis implementation.
# upstream design ../../agents/skills/document-canon-cleanup.md document cleanup workflow
# upstream design ../../documents/dependency-manifest-design.md dependency manifest model
# upstream implementation ../../rust/agent-canon/src/structured_analysis.rs canonical document inventory implementation
# downstream implementation ../../tests/agent_tools/test_noncanonical_document_inventory.py tests legacy CLI compatibility
# @dependency-end
"""Legacy entrypoint for document-canon inventory.

The implementation lives in `agent-canon structured-analysis document-inventory`.
This wrapper preserves the historical `NONCANONICAL_DOCUMENT_*` stdout contract
for older workflow calls.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PREFIX_MAP: tuple[tuple[str, str], ...] = (
    (
        "STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=",
        "NONCANONICAL_DOCUMENT_INVENTORY=",
    ),
    ("STRUCTURED_ANALYSIS_DOCUMENTS=", "NONCANONICAL_DOCUMENTS="),
    (
        "STRUCTURED_ANALYSIS_DOCUMENT_FINDINGS=",
        "NONCANONICAL_DOCUMENT_FINDINGS=",
    ),
    (
        "STRUCTURED_ANALYSIS_DOCUMENT_FINDING=",
        "NONCANONICAL_DOCUMENT_FINDING=",
    ),
    ("STRUCTURED_ANALYSIS_FINDING=", "NONCANONICAL_DOCUMENT_ERROR="),
)
LEGACY_FORWARDER_WARNING_REQUIRED = True
output_lines = [
    "NONCANONICAL_DOCUMENT_INVENTORY=<status>",
    "NONCANONICAL_DOCUMENTS=<count>",
    "NONCANONICAL_DOCUMENT_FINDINGS=<count>",
    "NONCANONICAL_DOCUMENT_FINDING=<kind:path:canonical:action>",
    "NONCANONICAL_DOCUMENT_FORWARDER=deprecated",
    "NONCANONICAL_DOCUMENT_FORWARDER_SEVERITY=fix-now",
    "NONCANONICAL_DOCUMENT_FORWARDER_PATH=<path>",
    "NONCANONICAL_DOCUMENT_FORWARDER_CALLER=<caller-chain>",
    "NONCANONICAL_DOCUMENT_FORWARDER_ACTION=<canonical-command>",
    "NONCANONICAL_DOCUMENT_FORWARDER_PROMPT=<migration-prompt>",
    "NONCANONICAL_DOCUMENT_ERROR=<error>",
]


def agent_canon_entrypoint() -> Path:
    """Return the stable Rust CLI wrapper path."""
    return Path(__file__).resolve().parents[1] / "bin" / "agent-canon"


def process_cmdline(pid: int) -> str:
    """Return a compact command line for a process id when /proc is available."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return "<unknown>"
    parts = [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]
    return " ".join(" ".join(parts).split()) if parts else "<unknown>"


def parent_pid(pid: int) -> int:
    """Return the parent pid for a process id when /proc is available."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def caller_process_chain(max_depth: int = 4) -> str:
    """Return the process chain that invoked this legacy wrapper."""
    chain: list[str] = []
    pid = os.getppid()
    depth = 0
    while pid > 1 and depth < max_depth:
        chain.append(f"pid={pid} cmd={process_cmdline(pid)}")
        pid = parent_pid(pid)
        depth += 1
    return " | ".join(chain) if chain else "<unknown>"


def warn_forwarder_call() -> None:
    """Warn that a caller still uses the legacy wrapper."""
    print("NONCANONICAL_DOCUMENT_FORWARDER=deprecated", file=sys.stderr)
    print("NONCANONICAL_DOCUMENT_FORWARDER_SEVERITY=fix-now", file=sys.stderr)
    print(f"NONCANONICAL_DOCUMENT_FORWARDER_PATH={Path(__file__).resolve()}", file=sys.stderr)
    print(
        f"NONCANONICAL_DOCUMENT_FORWARDER_CALLER={caller_process_chain()}",
        file=sys.stderr,
    )
    print(
        "NONCANONICAL_DOCUMENT_FORWARDER_ACTION=update caller to `agent-canon structured-analysis document-inventory`",
        file=sys.stderr,
    )
    print(
        "NONCANONICAL_DOCUMENT_FORWARDER_PROMPT=Legacy forwarder warning appeared; migrate the caller before continuing the original task.",
        file=sys.stderr,
    )
    sys.stderr.flush()


def translate_output(text: str) -> str:
    """Translate Rust structured-analysis summary prefixes to legacy names."""
    translated_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        translated = line
        for source, target in PREFIX_MAP:
            if translated.startswith(source):
                translated = target + translated.removeprefix(source)
                break
        translated_lines.append(translated)
    return "".join(translated_lines)


def main(argv: list[str] | None = None) -> int:
    """Run the Rust implementation and preserve the legacy CLI surface."""
    warn_forwarder_call()
    command = [
        str(agent_canon_entrypoint()),
        "structured-analysis",
        "document-inventory",
        *(sys.argv[1:] if argv is None else argv),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print("NONCANONICAL_DOCUMENT_INVENTORY=fail", file=sys.stderr)
        print(f"NONCANONICAL_DOCUMENT_ERROR=rust-entrypoint:{error}", file=sys.stderr)
        return 1

    sys.stdout.write(translate_output(result.stdout))
    sys.stderr.write(translate_output(result.stderr))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
