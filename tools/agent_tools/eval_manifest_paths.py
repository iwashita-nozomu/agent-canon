#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves canonical and legacy eval manifest source paths.
# upstream design ../../evidence/README.md evidence directory ownership
# upstream design ../../evidence/agent-evals/README.md canonical eval manifest source
# downstream implementation ./evaluate_skill_workflow_prompts.py resolves prompt eval manifests
# downstream implementation ./evaluate_agent_run.py resolves behavior eval manifests
# downstream implementation ./evaluate_workflow_selection.py resolves workflow selection manifests
# downstream implementation ./evaluate_report_quality.py resolves report quality manifests
# downstream implementation ./local_llm_eval.py resolves local LLM eval manifests
# downstream implementation ./eval_accumulation_check.py resolves eval family registries
# downstream implementation ./run_accumulated_agent_evals.py resolves producer manifests
# @dependency-end
"""Resolve eval manifest source paths after the evidence directory split."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

CANONICAL_EVAL_MANIFEST_ROOT = Path("evidence") / "agent-evals"
LEGACY_EVAL_MANIFEST_ROOT = Path("agents") / "evals"
LEGACY_EVAL_RESULT_ROOT = LEGACY_EVAL_MANIFEST_ROOT / "results"


def eval_manifest_path(filename: str) -> str:
    """Return the canonical relative path for one eval manifest filename."""
    return (CANONICAL_EVAL_MANIFEST_ROOT / filename).as_posix()


def is_legacy_manifest_path(path: Path) -> bool:
    """Return whether a path uses the old manifest source directory."""
    normalized = Path(path.as_posix())
    if normalized.is_absolute():
        return False
    try:
        normalized.relative_to(LEGACY_EVAL_RESULT_ROOT)
        return False
    except ValueError:
        pass
    try:
        normalized.relative_to(LEGACY_EVAL_MANIFEST_ROOT)
        return True
    except ValueError:
        return False


def legacy_to_canonical_manifest(path: Path) -> Path:
    """Map an old eval manifest source path to the canonical evidence path."""
    return CANONICAL_EVAL_MANIFEST_ROOT / path.relative_to(LEGACY_EVAL_MANIFEST_ROOT)


def caller_chain(limit: int = 6) -> str:
    """Return a compact caller chain for migration warnings."""
    frames = inspect.stack()[2 : 2 + limit]
    entries = []
    for frame in frames:
        entries.append(f"{Path(frame.filename).name}:{frame.function}:{frame.lineno}")
    return " -> ".join(entries)


def warn_legacy_manifest_path(old_path: Path, new_path: Path) -> None:
    """Emit a fix-now warning for an old eval manifest source path."""
    print(
        "EVAL_MANIFEST_FORWARDER=deprecated "
        "EVAL_MANIFEST_FORWARDER_SEVERITY=fix-now "
        f"old={old_path.as_posix()} "
        f"new={new_path.as_posix()} "
        f"caller_chain={caller_chain()}",
        file=sys.stderr,
    )


def resolve_eval_manifest(root: Path, value: str | Path) -> Path:
    """Resolve canonical eval manifests and old-path compatibility aliases."""
    raw = Path(value)
    if raw.is_absolute():
        try:
            relative = raw.relative_to(root)
        except ValueError:
            return raw
        if is_legacy_manifest_path(relative):
            canonical = legacy_to_canonical_manifest(relative)
            warn_legacy_manifest_path(relative, canonical)
            return root / canonical
        return raw
    if is_legacy_manifest_path(raw):
        canonical = legacy_to_canonical_manifest(raw)
        warn_legacy_manifest_path(raw, canonical)
        return root / canonical
    return root / raw


def relative_manifest_path(root: Path, path: Path) -> Path:
    """Return a relative path for reporting when possible."""
    try:
        return path.relative_to(root)
    except ValueError:
        return path
