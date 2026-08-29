#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the paired workflow context JSON load/store boundary.
# upstream design ../../../documents/design/agentcanon-hook-simplification-wave3.md owns context-path and fail-open semantics.
# downstream implementation ../../runtime/archive/behavior_event_assembly.py uses workflow context readback.
# downstream implementation ./subagent_selection.py consumes loaded context.
# @dependency-end
"""Atomic workflow context store/load with fail-open empty-state semantics."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class WorkflowContext:
    workflows: tuple[str, ...] = ()
    timestamp: str = ""
    source_event: str = ""

    def has_workflow(self) -> bool:
        return bool(self.workflows)


@dataclass(frozen=True)
class StoreResult:
    status: str
    path: Path
    error: str = ""


def _empty() -> WorkflowContext:
    return WorkflowContext()


def load_workflow_context(path: Path) -> WorkflowContext:
    """Read only the paired context file; every malformed read fails open."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _empty()
        workflows = raw.get("workflows")
        if not isinstance(workflows, list) or not all(isinstance(item, str) for item in workflows):
            return _empty()
        timestamp = raw.get("timestamp", "")
        source_event = raw.get("source_event", "")
        if not isinstance(timestamp, str) or not isinstance(source_event, str):
            return _empty()
        return WorkflowContext(tuple(workflows), timestamp, source_event)
    except (OSError, ValueError, TypeError):
        return _empty()


def store_workflow_context(path: Path, context: WorkflowContext) -> StoreResult:
    """Atomically replace the context JSON and never create a behavior event."""
    payload = {
        "schema": "agent-canon.workflow-context.v1",
        "workflows": list(context.workflows),
        "timestamp": context.timestamp,
        "source_event": context.source_event,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return StoreResult("stored", path)
    except (OSError, TypeError, ValueError) as exc:
        return StoreResult("skipped", path, type(exc).__name__)


def context_from_workflows(workflows: tuple[str, ...], source_event: str) -> WorkflowContext:
    return WorkflowContext(workflows, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), source_event)
