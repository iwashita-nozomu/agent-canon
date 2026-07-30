#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Manages the ignored Git clone used for AgentCanon runtime log and report archives.
# upstream design ../../documents/runtime/runtime-log-archive.md runtime log archive ownership and branch policy
# upstream implementation ./runtime_log_paths.py resolves archive paths and source repo keys
# downstream design ../../documents/runtime/runtime-log-archive.md documents this tool as the normal Git workflow
# downstream implementation ../../tests/agent_tools/test_runtime_log_archive_git.py validates clone, branch, status, and push behavior
# @dependency-end
"""Manage the external AgentCanon runtime log archive Git repository."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from stat import S_IMODE, S_ISDIR, S_ISREG
from typing import BinaryIO, cast

UTC = timezone.utc

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from log_repository_identity import source_repository_id_for_write  # noqa: E402
from report_artifact_checks import (  # noqa: E402
    MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS,
    check_final_review_artifact,
    final_review_decision_lines,
    parse_review_identity,
)
from runtime_log_paths import (  # noqa: E402
    LOG_ARCHIVE_REMOTE,
    agent_canon_git_commit_key,
    agent_report_archive_dir,
    codex_trace_key,
    hook_event_spool_root,
    log_environment_key,
    mounted_log_archive_root,
    repo_log_key,
    runtime_event_publication_outcome_spool_root,
    source_git_head,
)
from task_authority import ACTIVE_RUN_POINTER  # noqa: E402

DEFAULT_COMMIT_NAME = "AgentCanon Log Archive"
DEFAULT_COMMIT_EMAIL = "agent-canon-log@example.invalid"
AGENT_REPORT_ARCHIVE_SCHEMA = "agent-report-snapshot.v1"
DEFAULT_AGENT_REPORT_ROOT = Path("reports") / "agents"
DEFAULT_AGENT_REPORT_DESTINATION = Path("agent-reports")
AGENT_REPORT_EXCLUDED_DIRS = frozenset(
    {".cache", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
)
AGENT_REPORT_EXCLUDED_FILES = frozenset({".active_run", ".mcp_inventory_cache.json"})
DEFAULT_AGENT_REPORT_MAX_FILE_BYTES = 10 * 1024 * 1024
GIT_PORCELAIN_STATUS_PATH_START = 3
GIT_PORCELAIN_STATUS_MIN_LINE_LENGTH = GIT_PORCELAIN_STATUS_PATH_START
REPORT_SNAPSHOT_DIGEST_CHARS = 64
PUBLICATION_RETRY_LIMIT = 3
REPO_KEYED_ARCHIVE_FAMILIES = frozenset({"agent-reports", "codex-runtime", "hook-runs"})
MANAGED_GLOBAL_ARCHIVE_FAMILIES = frozenset({"eval-results", "legacy-import"})
BRANCH_SWITCH_COMMIT_MESSAGE = "Preserve managed runtime logs before branch switch"
GIT_INDEX_LOCK_MESSAGE = "index.lock"
GIT_INDEX_LOCK_RETRIES = 5
GIT_INDEX_LOCK_RETRY_SECONDS = 1.0
RUNTIME_EVENT_SCHEMA = "agent_canon.runtime_event.v1"
RUNTIME_EVENT_MATERIALIZATION_SCHEMA = "agent_canon.runtime_event.materialization.v1"
RUNTIME_EVENT_PUBLICATION_ATTEMPT_SCHEMA = (
    "agent_canon.runtime_event.publication_attempt.v1"
)
RUNTIME_EVENT_PUBLICATION_INTENT_SCHEMA = (
    "agent_canon.runtime_event.publication_intent.v1"
)
RUNTIME_EVENT_OBSERVATION_SCHEMA = (
    "agent_canon.runtime_event.publication_outcome_observation.v1"
)
RUNTIME_EVENT_RECEIPT_SCHEMA = (
    "agent_canon.runtime_event.publication_outcome_receipt.v1"
)
RUNTIME_EVENT_CONTEXT_SCHEMA = "codex.context_discovery.v1"
CONTEXT_DISCOVERY_CERTIFICATE_SCHEMA = (
    "agent_canon.context_discovery_certificate.v1"
)
CONTEXT_DISCOVERY_CERTIFICATE_PREFIX = (
    CONTEXT_DISCOVERY_CERTIFICATE_SCHEMA + "\0"
).encode("ascii")
CONTEXT_DISCOVERY_CERTIFICATE_NAME = re.compile(
    r"^context_discovery\.(?P<certificate_id>[0-9a-f]{64})\.json$"
)
RUNTIME_EVENT_FAMILY_NAMES = ("requirements", "design", "review", "validation", "lifecycle")
RUNTIME_EVENT_GATE_RESULTS = (
    "APPROVE", "REVISE", "ESCALATE", "PASS", "FAIL", "BLOCKED", "READY", "INCOMPLETE"
)
RUNTIME_EVENT_DECISIONS = ("APPROVE", "REVISE", "ESCALATE", "NONE")
RUNTIME_EVENT_HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUNTIME_EVENT_OID40 = re.compile(r"^[0-9a-f]{40}$")
RUNTIME_EVENT_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
RUNTIME_EVENT_GENERATED_NAME = re.compile(
    r"^runtime_event(?:_archive_manifest)?\..+\.json$"
)
RUNTIME_EVENT_ROLLOUT_NAME = re.compile(
    r"^rollout-(?P<timestamp>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:+.\-]+Z?)-"
    r"(?P<context>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)
RUNTIME_EVENT_TARGET_NAME = re.compile(
    r"^reports/agents/(?P<run>[^/\\]+)/runtime_event\.(?P<unit>[0-9a-f]{16})\.json$"
)
RUNTIME_EVENT_RECEIPT_NAME = re.compile(
    r"^runtime_event\.(?P<unit>[0-9a-f]{16})\.outcome\."
    r"(?P<attempt>[0-9a-f]{64})\.(?P<sequence>[0-9]{6})\.json$"
)
RUNTIME_EVENT_OBSERVATION_NAME = re.compile(
    r"^(?P<sequence>[0-9]{6})-(?P<sha256>[0-9a-f]{64})\.json$"
)
RUNTIME_EVENT_PUBLICATION_OUTCOMES = ("committed", "uncertain")
RUNTIME_EVENT_FSYNC_PURPOSES = (
    "artifact-parent",
    "observation-parent",
    "receipt-parent",
    "receipt-confirm-parent",
)
RUNTIME_EVENT_YEAR = re.compile(r"^[0-9]{4}$")
RUNTIME_EVENT_MONTH_DAY = re.compile(r"^[0-9]{2}$")
RUNTIME_EVENT_GENERATED_ROOTS = frozenset(
    {
        "reports/agent-eval-runs", "reports/agent-improvement-guide",
        "reports/agent-runtime-dashboard", "reports/dependency-review",
        "reports/hooks", "reports/.cache",
    }
)
RUNTIME_EVENT_RESULT_FILES = {
    "requirements": ("requirements_review.md", "requirements-review", "ReviewArtifactV1"),
    "design": ("design_review.md", "design-review", "ReviewArtifactV1"),
    "review": ("change_review.md", "change-review", "ReviewArtifactV1"),
    "validation": ("validation_result.json", "validation", "agent_canon.runtime_result_input.v1"),
    "lifecycle": ("closeout_gate.md", "closeout", "CloseoutGateV1"),
}
HOOK_SPOOL_INDEX_SCHEMA = "agent_canon.hook_spool_index.v1"
HOOK_SPOOL_CURSOR_SCHEMA = "agent_canon.hook_spool_cursor.v1"
HOOK_SPOOL_CURSOR_SCHEMA_VERSION = 1
HOOK_SPOOL_INDEX_NAME = ".spool-index.jsonl"
HOOK_SPOOL_CURSOR_NAME = ".spool-cursor.json"
HOOK_SPOOL_LOCK_RELATIVE = Path(".agent-canon") / "runtime-event-spool" / ".archive-transaction.lock"
HOOK_SPOOL_ZERO_SHA256 = "0" * 64
HOOK_HOT_PATH_ROOTS = (
    "HookLogContext.append",
    "canonical_hook_event_bytes",
    "publish_hook_event_noreplace",
)
HOOK_HOT_PATH_RUNTIME_PATH_HELPERS = frozenset(
    {"codex_trace_key", "hook_event_spool_root", "repo_log_key"}
)
HOOK_HOT_PATH_FORBIDDEN_CALLS = frozenset(
    {
        "subprocess",
        "system",
        "source_git_head",
        "hook_results_dir",
        "mounted_log_archive_root",
        "ensure_archive_branch",
        "runtime_log_archive_git",
        "rglob",
        "glob",
        "walk",
        "graph",
        "git",
        "fetch",
        "status",
        "commit",
        "push",
    }
)
_ACTIVE_ARCHIVE_LOCKS: set[Path] = set()
AT_FDCWD = -100
RENAME_NOREPLACE = 1


@dataclass(frozen=True)
class ArchiveContext:
    """Resolved archive operation context."""

    source_root: Path
    canon_root: Path
    archive_root: Path
    repo_key: str
    env_key: str
    branch_key: str
    branch: str
    remote: str


@dataclass(frozen=True)
class ArchiveStatusSummary:
    """Structured dirty-state summary for the archive clone."""

    current_branch: str
    dirty: bool
    branch_matches: bool
    dirty_keys: tuple[str, ...]
    current_key_dirty: bool
    foreign_dirty_keys: tuple[str, ...]
    tree_keys: tuple[str, ...]
    foreign_tree_keys: tuple[str, ...]
    global_dirty: bool


class ArchiveGitError(RuntimeError):
    """Raised when the archive Git operation cannot proceed safely."""


@dataclass(frozen=True)
class HookSpoolEvent:
    """Immutable size/hash snapshot for one local hook event file."""

    path: Path
    size: int
    bytes_sha256: str


@dataclass(frozen=True)
class HookSpoolCursorV1:
    """Committed hook-spool watermark and dedup-index certificate."""

    schema: str
    schema_version: int
    repo_key: str
    generation: int
    prior_cursor_sha256: str
    transaction_id: str
    source_event_count: int
    accepted_event_count: int
    duplicate_event_count: int
    failed_event_count: int
    source_set_sha256: str
    dedup_index_sha256: str
    archive_commit_oid: str
    cursor_body_sha256: str

    def as_dict(self) -> dict[str, object]:
        """Return fields in explicit canonical lexical order."""
        values: dict[str, object] = {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "repo_key": self.repo_key,
            "generation": self.generation,
            "prior_cursor_sha256": self.prior_cursor_sha256,
            "transaction_id": self.transaction_id,
            "source_event_count": self.source_event_count,
            "accepted_event_count": self.accepted_event_count,
            "duplicate_event_count": self.duplicate_event_count,
            "failed_event_count": self.failed_event_count,
            "source_set_sha256": self.source_set_sha256,
            "dedup_index_sha256": self.dedup_index_sha256,
            "archive_commit_oid": self.archive_commit_oid,
            "cursor_body_sha256": self.cursor_body_sha256,
        }
        return {key: values[key] for key in sorted(values)}


@dataclass(frozen=True)
class HookSpoolIngestResult:
    """Prepared archive changes and source files covered by one ingest."""

    transaction_id: str
    spool_snapshot: tuple[HookSpoolEvent, ...]
    accepted_events: tuple[HookSpoolEvent, ...]
    duplicate_events: tuple[HookSpoolEvent, ...]
    failed_event_count: int
    source_set_sha256: str
    dedup_index_path: Path
    dedup_index_sha256: str
    cursor_path: Path
    cursor_sha256: str


@dataclass(frozen=True)
class ArchivePublicationReceipt:
    """Consumer-visible publication and exact archive readback certificate."""

    status: str
    commit_created: bool
    pushed: bool
    archive_commit_oid: str
    archive_tree_oid: str
    dedup_index_sha256: str
    cursor_sha256: str
    push_status: str = ""


@dataclass
class PreparedArchiveTransaction:
    """One non-reentrant archive-index mutation boundary."""

    context: ArchiveContext
    lock_path: Path
    lock_handle: BinaryIO
    archive_head_before: str
    ensured_branch: str

    def __enter__(self) -> PreparedArchiveTransaction:
        """Return the already prepared, lock-owning transaction."""
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        """Release the nonblocking transaction lock exactly once."""
        try:
            fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.lock_handle.close()
            _ACTIVE_ARCHIVE_LOCKS.discard(self.lock_path.resolve())


@dataclass(frozen=True)
class LegacyImportRecord:
    """One source/destination digest record in a legacy import plan."""

    source: Path
    source_relative: str
    destination: str | None
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class LegacyImportPlan:
    """Copy and deletion plan held until archive publication readback succeeds."""

    family: str
    legacy_root: Path
    index_path: Path
    inventory_sha256: str
    records: tuple[LegacyImportRecord, ...]
    delete_source: bool


@dataclass(frozen=True)
class RuntimeEventSelector:
    """Fixed selector for one source-bound runtime event."""

    codex_thread_id: str
    agent_context_id: str
    turn_id: str
    result_family: str
    run_id: str
    gate_id: str
    base_ref: str
    unit_id: str | None


@dataclass(frozen=True)
class SourceEventIdentity:
    """Certified rollout identity and exact source-byte provenance."""

    agent_id: str
    agent_context_id: str
    codex_thread_id: str
    parent_id: str
    turn_id: str
    role: str
    rollout_path: str
    rollout_path_bytes_b64: str
    rollout_path_sha256: str
    rollout_file_sha256: str
    record_line: int
    record_byte_offset: int
    record_byte_length: int
    record_bytes_b64: str
    record_sha256: str
    stable_record_id: str


@dataclass(frozen=True)
class ResultFamilySpec:
    """One closed result-artifact family contract."""

    result_family: str
    gate_id: str
    artifact_name: str
    schema: str


@dataclass(frozen=True)
class RuntimeEventRecord:
    """Validated canonical runtime-event object."""

    value: dict[str, object]

    def __getitem__(self, key: str) -> object:
        """Return one validated record field."""
        return self.value[key]


@dataclass(frozen=True)
class PublicationAttemptLock:
    """Validated nonblocking lock held for one publication attempt."""

    attempt_id: str
    attempt_directory: Path
    lock_path: Path
    fd: int


@dataclass(frozen=True)
class DurablePublicationOutcomeReceipt:
    """Receipt accepted only after file and parent durability confirmation."""

    path: Path
    value: dict[str, object]
    bytes_: bytes


class RuntimeEventMaterializationError(ArchiveGitError):
    """Raised for a typed source-bound runtime-event transaction failure."""

    def __init__(self, code: str, detail: str):
        """Store the stable error code and diagnostic detail."""
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


RESULT_FAMILY_SPECS = tuple(
    ResultFamilySpec(family, gate_id, artifact_name, schema)
    for family, (artifact_name, gate_id, schema) in RUNTIME_EVENT_RESULT_FILES.items()
)


def fixed_result_family_spec(result_family: str, gate_id: str | None = None) -> ResultFamilySpec:
    """Return the sole fixed specification for one result family and gate."""
    spec = next((item for item in RESULT_FAMILY_SPECS if item.result_family == result_family), None)
    if spec is None or (gate_id is not None and spec.gate_id != gate_id):
        raise RuntimeEventMaterializationError(
            "result_authority_mismatch", "result family and gate id do not match"
        )
    return spec


def _ast_call_name(call: ast.Call) -> str:
    """Return one dotted call target when syntax fixes it statically."""
    return _ast_expression_name(call.func)


def _ast_expression_name(node: ast.expr) -> str:
    """Return a dotted expression name without evaluating source code."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _resolve_ast_alias(name: str, aliases: dict[str, str]) -> str:
    """Resolve imported and local name aliases to a stable dotted target."""
    resolved = name
    visited: set[str] = set()
    while resolved:
        first, separator, remainder = resolved.partition(".")
        replacement = aliases.get(first)
        if replacement is None or first in visited:
            break
        visited.add(first)
        resolved = replacement + (f".{remainder}" if separator else "")
    return resolved


def _module_ast_aliases(tree: ast.Module) -> dict[str, str]:
    """Index statically named import and module-level assignment aliases."""
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name != "*":
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None:
                continue
            target_name = next(
                (target.id for target in targets if isinstance(target, ast.Name)),
                None,
            )
            value_name = _ast_expression_name(value)
            if target_name and value_name:
                aliases[target_name] = _resolve_ast_alias(value_name, aliases)
    return aliases


def _definition_ast_aliases(
    definition: ast.FunctionDef | ast.AsyncFunctionDef,
    module_aliases: dict[str, str],
) -> dict[str, str]:
    """Extend module aliases with statically named aliases in one function."""
    aliases = dict(module_aliases)
    for node in ast.walk(definition):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and node is not definition:
            continue
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if value is None:
            continue
        value_name = _ast_expression_name(value)
        if not value_name:
            continue
        resolved = _resolve_ast_alias(value_name, aliases)
        for target in targets:
            if isinstance(target, ast.Name):
                aliases[target.id] = resolved
    return aliases


def _hot_path_definitions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Index module functions and HookLogContext methods for call-graph traversal."""
    definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions[node.name] = node
        if isinstance(node, ast.ClassDef) and node.name == "HookLogContext":
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions[f"HookLogContext.{child.name}"] = child
    return definitions


def _runtime_path_definitions(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Index runtime_log_paths functions under an unambiguous module prefix."""
    return {
        f"runtime_log_paths.{node.name}": node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _runtime_path_imports(tree: ast.Module) -> dict[str, str]:
    """Return approved runtime_log_paths helper bindings imported by the hook."""
    bindings: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module != "runtime_log_paths":
            continue
        for alias in node.names:
            if alias.name in HOOK_HOT_PATH_RUNTIME_PATH_HELPERS:
                bindings[alias.asname or alias.name] = f"runtime_log_paths.{alias.name}"
    return bindings


def check_hook_hot_path(path: Path) -> tuple[str, ...]:
    """Return static forbidden-operation findings reachable from hook append."""
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return ("hook_source_unreadable",)

    definitions = _hot_path_definitions(tree)
    module_aliases = _module_ast_aliases(tree)
    runtime_imports = _runtime_path_imports(tree)
    findings: set[str] = set()
    if runtime_imports:
        runtime_path = path.resolve().parents[2] / "tools" / "agent_tools" / "runtime_log_paths.py"
        try:
            runtime_text = runtime_path.read_text(encoding="utf-8")
            runtime_tree = ast.parse(runtime_text, filename=str(runtime_path))
        except (OSError, SyntaxError, UnicodeError):
            findings.add("runtime_log_paths_source_unreadable")
        else:
            definitions.update(_runtime_path_definitions(runtime_tree))
            module_aliases.update(_module_ast_aliases(runtime_tree))
            for target in runtime_imports.values():
                if target not in definitions:
                    findings.add(f"missing:{target}")
    append_node = definitions.get("HookLogContext.append")
    if append_node is None:
        findings.add("missing:HookLogContext.append")
    else:
        annotation = append_node.returns
        if not isinstance(annotation, ast.Name) or annotation.id != "HookAppendResult":
            findings.add("return_annotation:HookLogContext.append")

    pending = list(HOOK_HOT_PATH_ROOTS)
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        definition = definitions.get(name)
        if definition is None:
            findings.add(f"missing:{name}")
            continue
        aliases = _definition_ast_aliases(definition, module_aliases)
        for node in ast.walk(definition):
            if not isinstance(node, ast.Call):
                continue
            call_name = _ast_call_name(node)
            resolved_call = _resolve_ast_alias(call_name, aliases)
            call_parts = tuple(
                part.casefold() for part in resolved_call.split(".") if part
            )
            forbidden = next(
                (part for part in call_parts if part in HOOK_HOT_PATH_FORBIDDEN_CALLS),
                None,
            )
            if forbidden is not None:
                findings.add(f"forbidden:{resolved_call}")
            if resolved_call in {
                "print",
                "builtins.print",
                "sys.stdout.write",
                "sys.stderr.write",
            }:
                findings.add(f"output:{resolved_call}")

            local_name = ""
            if name.startswith("runtime_log_paths.") and "." not in resolved_call:
                candidate = f"runtime_log_paths.{resolved_call}"
                if candidate in definitions:
                    local_name = candidate
            elif resolved_call.startswith("self."):
                local_name = f"HookLogContext.{resolved_call.removeprefix('self.')}"
            elif resolved_call.startswith("runtime_log_paths."):
                local_name = resolved_call
            elif "." not in resolved_call and resolved_call in definitions:
                local_name = resolved_call
            if local_name in definitions and local_name not in visited:
                pending.append(local_name)
    return tuple(sorted(findings))


def command_check_hook_hot_path(path: Path) -> int:
    """Print the stable, context-free hook hot-path checker result."""
    findings = check_hook_hot_path(path)
    print(f"RUNTIME_LOG_HOT_PATH_PATH={path}")
    print(f"RUNTIME_LOG_HOT_PATH_FORBIDDEN_COUNT={len(findings)}")
    print(f"RUNTIME_LOG_HOT_PATH={'pass' if not findings else 'fail'}")
    return 0 if not findings else 1


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Repository whose runtime logs are being written. Defaults to the superproject when AgentCanon is vendored.",
    )
    parser.add_argument(
        "--canon-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="AgentCanon root that owns .agent-canon/log-archive.",
    )
    parser.add_argument(
        "--remote",
        default=LOG_ARCHIVE_REMOTE,
        help="Log archive Git remote. Defaults to the shared agent-canon-log SSH URL.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        help="Override the archive clone path. Defaults to <canon-root>/.agent-canon/log-archive.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_hot_path = subparsers.add_parser(
        "check-hook-hot-path",
        help="Statically reject blocking or output-producing hook append operations.",
    )
    check_hot_path.add_argument("--path", type=Path, default=None)

    context_discovery = subparsers.add_parser(
        "append-context-discovery",
        help="Publish one immutable native ContextDiscoveryV1 certificate.",
    )
    context_discovery.add_argument("--run-id", required=True, help="Active reports/agents run id.")
    context_discovery.add_argument(
        "--agent-context-id", required=True, help="Native Codex session context UUID."
    )
    context_discovery.add_argument(
        "--turn-id", required=True, help="Native task-completion turn UUID."
    )

    materialize = subparsers.add_parser(
        "materialize-runtime-event",
        help="Materialize one source-bound runtime event into the active run bundle.",
    )
    materialize.add_argument(
        "--result-family", choices=RUNTIME_EVENT_FAMILY_NAMES, required=True,
        help="Fixed result-artifact family to verify.",
    )
    materialize.add_argument("--run-id", required=True, help="Active reports/agents run id.")
    materialize.add_argument("--gate-id", required=True, help="Fixed gate id for the result family.")
    materialize.add_argument("--base-ref", required=True, help="Git ref used for target/base verification.")
    materialize.add_argument(
        "--unit-id", help="Optional first sixteen hexadecimal characters of the source record hash."
    )

    subparsers.add_parser("repo-key", help="Print the source repository key and log branch.")

    ensure = subparsers.add_parser(
        "ensure",
        help="Clone/fetch the archive and select logs/<stable-source-repository-id>.",
    )
    ensure.add_argument("--no-fetch", action="store_true", help="Do not fetch origin before selecting the branch.")

    status = subparsers.add_parser("status", help="Print archive clone, branch, and dirty state.")
    status.add_argument("--porcelain", action="store_true", help="Include git status --porcelain output.")

    check_clean = subparsers.add_parser(
        "check-clean",
        help="Fail unless the archive clone is on the expected branch and has no uncommitted log artifacts.",
    )
    check_clean.add_argument(
        "--porcelain",
        action="store_true",
        help="Include git status --porcelain output on failure.",
    )

    agent_reports = subparsers.add_parser(
        "archive-agent-reports",
        help="Snapshot reports/agents run bundles into the current runtime archive branch.",
    )
    agent_reports.add_argument(
        "--report-root",
        type=Path,
        help="Agent report root. Defaults to <source-root>/reports/agents.",
    )
    agent_reports.add_argument(
        "--destination-prefix",
        default=DEFAULT_AGENT_REPORT_DESTINATION.as_posix(),
        help="Archive-relative destination prefix for copied agent reports.",
    )
    agent_reports.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_AGENT_REPORT_MAX_FILE_BYTES,
        help="Skip individual report files larger than this many bytes.",
    )

    legacy = subparsers.add_parser(
        "import-legacy",
        help="Copy old AgentCanon in-tree hook JSONL into legacy-import/hook-runs.",
    )
    legacy.add_argument(
        "--legacy-root",
        type=Path,
        help="Legacy hook JSONL root. Defaults to <canon-root>/agents/evals/results/hook-runs.",
    )
    legacy.add_argument(
        "--destination-prefix",
        default="legacy-import/hook-runs",
        help="Archive-relative destination prefix for legacy JSONL.",
    )
    legacy.add_argument(
        "--delete-source",
        action="store_true",
        help="Delete imported source JSONL after copying. Tracked files are removed with git rm.",
    )

    eval_results = subparsers.add_parser(
        "import-eval-results",
        help="Copy old AgentCanon in-tree eval Markdown reports into legacy-import/eval-results.",
    )
    eval_results.add_argument(
        "--legacy-root",
        type=Path,
        help="Legacy eval results root. Defaults to <canon-root>/agents/evals/results.",
    )
    eval_results.add_argument(
        "--destination-prefix",
        default="legacy-import/eval-results",
        help="Archive-relative destination prefix for legacy eval reports.",
    )
    eval_results.add_argument(
        "--delete-source",
        action="store_true",
        help=(
            "Delete imported source eval result files after copying. AgentCanon source "
            "keeps runtime-log policy in documents/runtime/runtime-log-archive.md, not under agents/evals/results."
        ),
    )

    agent_report = subparsers.add_parser(
        "archive-agent-report",
        help="Snapshot a reports/agents/<run-id> bundle into the external log archive.",
    )
    agent_report.add_argument(
        "--report-dir",
        type=Path,
        required=True,
        help="Run bundle directory to archive, normally reports/agents/<run-id>.",
    )

    push = subparsers.add_parser("push", help="Commit and push append-only logs for this source repository.")
    push.add_argument("--message", help="Commit message. Defaults to 'Append <stable-source-repository-id> runtime logs'.")
    push.add_argument("--no-pull", action="store_true", help="Do not pull --rebase before pushing.")

    sync = subparsers.add_parser(
        "sync",
        help="Ensure the archive, snapshot current agent reports, commit, and push log artifacts.",
    )
    sync.add_argument("--message", help="Commit message. Defaults to 'Append <stable-source-repository-id> runtime logs'.")
    sync.add_argument("--no-pull", action="store_true", help="Do not pull --rebase before pushing.")
    sync.add_argument("--no-push", action="store_true", help="Copy artifacts into the archive without pushing.")
    sync.add_argument("--no-agent-reports", action="store_true", help="Do not copy reports/agents artifacts.")
    sync.add_argument(
        "--report-root",
        type=Path,
        help="Agent report root. Defaults to <source-root>/reports/agents.",
    )
    sync.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_AGENT_REPORT_MAX_FILE_BYTES,
        help="Skip individual report files larger than this many bytes.",
    )
    return parser


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one command and return the completed process."""
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        detail = result.stderr.strip() or result.stdout.strip()
        raise ArchiveGitError(f"{command} failed: {detail}")
    return result


def git(
    archive_root: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run git inside the archive clone."""
    command = ["git", "-C", str(archive_root), *args]
    for attempt in range(GIT_INDEX_LOCK_RETRIES + 1):
        result = run(command, check=False)
        if result.returncode == 0 or not git_index_locked(result) or attempt == GIT_INDEX_LOCK_RETRIES:
            if check and result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise ArchiveGitError(f"{' '.join(command)} failed: {detail}")
            return result
        time.sleep(GIT_INDEX_LOCK_RETRY_SECONDS)
    raise ArchiveGitError(f"{' '.join(command)} failed after index lock retries")


def git_index_locked(result: subprocess.CompletedProcess[str]) -> bool:
    """Return whether a git failure is caused by a transient index lock."""
    detail = f"{result.stderr}\n{result.stdout}"
    return GIT_INDEX_LOCK_MESSAGE in detail


def git_root(path: Path) -> Path | None:
    """Return the Git toplevel for one path, if available."""
    result = run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def superproject_root(path: Path) -> Path | None:
    """Return the superproject root when AgentCanon is checked out as a submodule."""
    result = run(
        ["git", "-C", str(path), "rev-parse", "--show-superproject-working-tree"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def default_source_root(canon_root: Path) -> Path:
    """Return the default source repo for branch naming."""
    cwd_git_root = git_root(Path.cwd())
    canon_git_root = git_root(canon_root)
    if cwd_git_root is not None and canon_git_root is not None and cwd_git_root == canon_git_root:
        return cwd_git_root
    return superproject_root(canon_root) or cwd_git_root or Path.cwd().resolve()


def build_context(args: argparse.Namespace) -> ArchiveContext:
    """Resolve source/canon/archive paths and branch names."""
    canon_root = args.canon_root.resolve()
    source_root = (args.source_root.resolve() if args.source_root else default_source_root(canon_root))
    archive_root = (
        args.archive_root.resolve()
        if args.archive_root
        else mounted_log_archive_root(canon_root).resolve()
    )
    try:
        key = source_repository_id_for_write(source_root)
        branch_key = key
    except ValueError as exc:
        raise ArchiveGitError(f"source_identity_preflight_failed:{exc}") from exc
    env_key = log_environment_key(canon_root)
    return ArchiveContext(
        source_root=source_root,
        canon_root=canon_root,
        archive_root=archive_root,
        repo_key=key,
        env_key=env_key,
        branch_key=branch_key,
        branch=f"logs/{branch_key}",
        remote=args.remote,
    )


def _runtime_session_roots() -> tuple[Path, ...]:
    """Return the finite, deduplicated Codex session roots."""
    candidates: list[Path] = []
    configured = os.environ.get("AGENT_CANON_CODEX_SESSION_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured))
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        candidates.append(Path(codex_home) / "sessions")
    home = os.environ.get("HOME", "").strip()
    if home:
        candidates.append(Path(home) / ".codex" / "sessions")
    roots = {candidate.resolve() for candidate in candidates if candidate.is_dir()}
    return tuple(sorted(roots, key=lambda path: path.as_posix().encode("utf-8")))


def _rollout_name_identity(path: Path) -> tuple[str, str] | None:
    """Return timestamp/context only for a canonical Codex rollout basename."""
    match = RUNTIME_EVENT_ROLLOUT_NAME.fullmatch(path.name)
    if match is None:
        return None
    timestamp = match.group("timestamp")
    normalized = timestamp.removesuffix("Z")
    date, separator, clock = normalized.partition("T")
    if not separator:
        return None
    clock_parts = clock.split("-", 2)
    if ":" not in clock and len(clock_parts) == 3:
        normalized = f"{date}T{clock_parts[0]}:{clock_parts[1]}:{clock_parts[2]}"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.date().isoformat(), match.group("context")


def _rollout_files(agent_context_id: str) -> tuple[Path, ...]:
    """Enumerate only date-scoped rollout files for one context suffix."""
    files: set[Path] = set()
    for root in _runtime_session_roots():
        try:
            years = sorted(
                (
                    path
                    for path in root.iterdir()
                    if not path.is_symlink()
                    and path.is_dir()
                    and RUNTIME_EVENT_YEAR.fullmatch(path.name)
                ),
                key=lambda path: path.name.encode("utf-8"),
            )
            for year in years:
                months = sorted(
                    (
                        path
                        for path in year.iterdir()
                        if not path.is_symlink()
                        and path.is_dir()
                        and RUNTIME_EVENT_MONTH_DAY.fullmatch(path.name)
                    ),
                    key=lambda path: path.name.encode("utf-8"),
                )
                for month in months:
                    days = sorted(
                        (
                            path
                            for path in month.iterdir()
                            if not path.is_symlink()
                            and path.is_dir()
                            and RUNTIME_EVENT_MONTH_DAY.fullmatch(path.name)
                        ),
                        key=lambda path: path.name.encode("utf-8"),
                    )
                    for day in days:
                        for path in sorted(
                            (
                                item
                                for item in day.iterdir()
                                if not item.is_symlink() and item.is_file()
                            ),
                            key=lambda item: item.name.encode("utf-8"),
                        ):
                            identity = _rollout_name_identity(path)
                            if identity is None or identity[1] != agent_context_id:
                                continue
                            if identity[0] == f"{year.name}-{month.name}-{day.name}":
                                resolved = path.resolve(strict=True)
                                if resolved.is_relative_to(root):
                                    files.add(resolved)
        except OSError as exc:
            raise RuntimeEventMaterializationError("source_unavailable", str(exc)) from exc
    return tuple(sorted(files, key=lambda path: path.as_posix().encode("utf-8")))


def _native_session_meta(value: dict[str, object]) -> dict[str, object] | None:
    """Read one native session metadata record or reject its malformed shape."""
    if value.get("type") != "session_meta":
        return None
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "session_meta payload is not an object"
        )
    identity = payload.get("id")
    parent_id = payload.get("parent_thread_id")
    role = payload.get("agent_role")
    cwd = payload.get("cwd")
    source = payload.get("source")
    if (
        not isinstance(identity, str)
        or not RUNTIME_EVENT_UUID.fullmatch(identity)
        or not isinstance(parent_id, str)
        or not RUNTIME_EVENT_UUID.fullmatch(parent_id)
        or not isinstance(role, str)
        or not role
        or not isinstance(cwd, str)
        or not cwd
        or not isinstance(source, dict)
    ):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "session_meta native identity is invalid"
        )
    subagent = source.get("subagent")
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    if not isinstance(spawn, dict):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "session_meta thread_spawn is absent"
        )
    spawn_parent = spawn.get("parent_thread_id")
    spawn_role = spawn.get("agent_role")
    if (
        not isinstance(spawn_parent, str)
        or not RUNTIME_EVENT_UUID.fullmatch(spawn_parent)
        or not isinstance(spawn_role, str)
        or not spawn_role
        or spawn_parent != parent_id
        or spawn_role != role
    ):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "session_meta structural joins do not match"
        )
    return {
        "identity": identity,
        "parent_id": parent_id,
        "role": role,
        "cwd": cwd,
    }


def _native_task_complete(
    value: dict[str, object], turn_id: str
) -> dict[str, object] | None:
    """Read one native task-completion record for the selected turn."""
    if value.get("type") != "event_msg":
        return None
    payload = value.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "task_complete":
        return None
    native_turn_id = payload.get("turn_id")
    if not isinstance(native_turn_id, str) or not RUNTIME_EVENT_UUID.fullmatch(native_turn_id):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "task_complete turn id is invalid"
        )
    if native_turn_id != turn_id:
        return None
    return {"turn_id": native_turn_id}


def discover_rollout_context(agent_context_id: str, turn_id: str) -> dict[str, object]:
    """Certify native session metadata, rollout identity, and task joins."""
    if not RUNTIME_EVENT_UUID.fullmatch(agent_context_id) or not RUNTIME_EVENT_UUID.fullmatch(turn_id):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "context or turn selector is not a UUID"
        )
    if not _runtime_session_roots():
        raise RuntimeEventMaterializationError(
            "context_source_absent", "no Codex session root exists"
        )
    files = _rollout_files(agent_context_id)
    if not files:
        raise RuntimeEventMaterializationError(
            "context_source_absent", "no rollout file matches the context selector"
        )
    if len(files) != 1:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous", "rollout path is not unique for the context selector"
        )
    snapshots: dict[Path, bytes] = {}
    sessions: list[tuple[Path, dict[str, object], dict[str, object]]] = []
    completions: list[tuple[Path, dict[str, object], dict[str, object]]] = []
    for path in files:
        try:
            snapshot = path.read_bytes()
        except OSError as exc:
            raise RuntimeEventMaterializationError("source_unavailable", str(exc)) from exc
        snapshots[path] = snapshot
        for record in _iter_source_snapshot_records(snapshot):
            value = cast(dict[str, object], record["value"])
            session = _native_session_meta(value)
            if session is not None:
                if cast(str, session["identity"]) != agent_context_id:
                    raise RuntimeEventMaterializationError(
                        "source_identity_mismatch", "session_meta id does not match selector"
                    )
                sessions.append((path, record, session))
            completion = _native_task_complete(value, turn_id)
            if completion is not None:
                completions.append((path, record, completion))
    if not sessions:
        raise RuntimeEventMaterializationError(
            "context_source_absent", "native session_meta record is absent"
        )
    if len(sessions) != 1:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous", "native session_meta record is not unique"
        )
    if not completions:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "selected task_complete record is absent"
        )
    if len(completions) != 1:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous", "selected task_complete record is not unique"
        )
    session_path, session_record, session = sessions[0]
    task_path, task_record, _task = completions[0]
    if session_path != task_path:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "session_meta and task_complete use different rollouts"
        )
    name_identity = _rollout_name_identity(session_path)
    if name_identity is None or name_identity[1] != agent_context_id:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "rollout filename does not match context selector"
        )
    file_bytes = snapshots[session_path]
    path_bytes = session_path.as_posix().encode("utf-8")
    task_raw = cast(bytes, task_record["raw"])
    session_raw = cast(bytes, session_record["raw"])
    task_sha = hashlib.sha256(task_raw).hexdigest()
    return {
        "agent_id": agent_context_id,
        "agent_context_id": agent_context_id,
        "codex_thread_id": agent_context_id,
        "parent_id": cast(str, session["parent_id"]),
        "turn_id": turn_id,
        "role": cast(str, session["role"]),
        "rollout_path": session_path.as_posix(),
        "rollout_path_bytes_b64": base64.b64encode(path_bytes).decode("ascii"),
        "rollout_path_sha256": hashlib.sha256(path_bytes).hexdigest(),
        "rollout_file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "session_cwd": cast(str, session["cwd"]),
        "session_meta": {
            "line": cast(int, session_record["line"]),
            "byte_offset": cast(int, session_record["offset"]),
            "byte_length": len(session_raw),
            "record_sha256": hashlib.sha256(session_raw).hexdigest(),
        },
        "task_complete": {
            "line": cast(int, task_record["line"]),
            "byte_offset": cast(int, task_record["offset"]),
            "byte_length": len(task_raw),
            "record_sha256": task_sha,
        },
        "record_bytes_b64": base64.b64encode(task_raw).decode("ascii"),
        "record_sha256": task_sha,
        "stable_record_id": task_sha,
    }


def _rollout_files_from_root(root: Path) -> tuple[Path, ...]:
    """Enumerate eligible rollout files for the context-discovery scan."""
    files: set[Path] = set()
    try:
        for year in (
            path
            for path in root.iterdir()
            if path.is_dir() and RUNTIME_EVENT_YEAR.fullmatch(path.name)
        ):
            for month in (
                path
                for path in year.iterdir()
                if path.is_dir() and RUNTIME_EVENT_MONTH_DAY.fullmatch(path.name)
            ):
                for day in (
                    path
                    for path in month.iterdir()
                    if path.is_dir()
                    and RUNTIME_EVENT_MONTH_DAY.fullmatch(path.name)
                ):
                    for path in day.iterdir():
                        if not path.is_file():
                            continue
                        identity = _rollout_name_identity(path)
                        if identity is None:
                            continue
                        if identity[0] == f"{year.name}-{month.name}-{day.name}":
                            files.add(path.resolve())
    except OSError as exc:
        raise RuntimeEventMaterializationError("source_unavailable", str(exc)) from exc
    return tuple(sorted(files, key=lambda path: path.as_posix().encode("utf-8")))


def discover_rollout_path(selector: RuntimeEventSelector) -> Path:
    """Return the exact rollout path certified by ContextDiscoveryV1."""
    context = discover_rollout_context(selector.agent_context_id, selector.turn_id)
    return Path(cast(str, context["rollout_path"]))


def _iter_source_snapshot_records(source: bytes) -> Iterator[dict[str, object]]:
    """Yield structural JSONL records from one immutable byte snapshot."""
    offset = 0
    for line_number, raw in enumerate(source.splitlines(keepends=True), start=1):
        length = len(raw)
        if raw.endswith(b"\n"):
            try:
                value = json.loads(raw[:-1].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                value = None
            if isinstance(value, dict):
                yield {"line": line_number, "offset": offset, "length": length, "raw": raw, "value": value}
        offset += length


def iter_source_records(path: Path) -> Iterator[dict[str, object]]:
    """Yield finite structural JSONL records with exact byte provenance."""
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError("source_unavailable", str(exc)) from exc
    yield from _iter_source_snapshot_records(source)


def is_source_snapshot_path(relative: Path) -> bool:
    """Return whether a path belongs to the finite owner-approved source universe."""
    parts = relative.parts
    excluded = {".git", ".agent-canon", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    if not parts or any(part in excluded for part in parts):
        return False
    if len(parts) >= 3 and parts[0] == "experiments" and parts[2] in {"result", "report"}:
        return False
    normalized = relative.as_posix()
    if any(normalized == root or normalized.startswith(f"{root}/") for root in RUNTIME_EVENT_GENERATED_ROOTS):
        return False
    if RUNTIME_EVENT_GENERATED_NAME.fullmatch(relative.name):
        return False
    for pattern in MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS:
        if hasattr(pattern, "match") and pattern.match(normalized):
            return False
        if isinstance(pattern, str) and re.fullmatch(pattern, normalized):
            return False
    return True


def _path_has_traversal(value: str) -> bool:
    """Return whether a serialized path contains a traversal or non-POSIX seam."""
    if not value or "\0" in value or "\\" in value:
        return True
    parts = value.split("/")
    return any(part in {".", ".."} for part in parts)


def _context_certificate_path(value: object, field: str) -> str:
    """Validate one absolute, normalized POSIX certificate path."""
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or _path_has_traversal(value)
        or Path(value).as_posix() != value
    ):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", f"{field} is not a canonical absolute path"
        )
    return value


def _context_certificate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate keys while parsing a context certificate."""
    if len({key for key, _value in pairs}) != len(pairs):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate has duplicate keys"
        )
    return dict(pairs)


def _context_certificate_bytes(value: dict[str, object]) -> bytes:
    """Render one context certificate as compact canonical JSONL bytes."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _context_certificate_id(value: dict[str, object]) -> str:
    """Calculate the certificate id from its zeroed-id canonical preimage."""
    preimage = dict(value)
    preimage["certificate_id"] = "0" * 64
    return hashlib.sha256(
        CONTEXT_DISCOVERY_CERTIFICATE_PREFIX + _context_certificate_bytes(preimage)
    ).hexdigest()


def validate_context_discovery_certificate(raw: bytes) -> None:
    """Validate exact ContextDiscoveryV1 certificate shape, bytes, and hashes."""
    if not raw.endswith(b"\n") or b"\n" in raw[:-1] or not raw[:-1]:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate must be one JSON line"
        )
    try:
        value = json.loads(
            raw[:-1].decode("utf-8"), object_pairs_hook=_context_certificate_pairs
        )
    except RuntimeEventMaterializationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate JSON is invalid"
        ) from exc
    def matches(pattern: re.Pattern[str], item: object) -> bool:
        return isinstance(item, str) and pattern.fullmatch(item) is not None

    if not isinstance(value, dict):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate is not an object"
        )
    if list(value) != ["schema", "certificate_id", "context", "repository", "rollout"]:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate top-level keys are not canonical"
        )
    if value["schema"] != CONTEXT_DISCOVERY_CERTIFICATE_SCHEMA or not matches(RUNTIME_EVENT_HEX64, value["certificate_id"]):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate schema or id is invalid"
        )
    context = value["context"]
    repository = value["repository"]
    rollout = value["rollout"]
    if not isinstance(context, dict) or list(context) != [
        "schema", "agent_id", "agent_context_id", "codex_thread_id",
        "parent_id", "turn_id", "role",
    ]:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate context shape is invalid"
        )
    if context["schema"] != RUNTIME_EVENT_CONTEXT_SCHEMA:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate context schema is invalid"
        )
    for field in ("agent_id", "agent_context_id", "codex_thread_id", "parent_id", "turn_id"):
        if not isinstance(context[field], str) or not RUNTIME_EVENT_UUID.fullmatch(context[field]):
            raise RuntimeEventMaterializationError(
                "context_schema_invalid", f"context certificate {field} is invalid"
            )
    if (
        not isinstance(context["role"], str)
        or not context["role"]
        or context["agent_id"] != context["agent_context_id"]
        or context["agent_context_id"] != context["codex_thread_id"]
    ):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate identity joins are invalid"
        )
    if not isinstance(repository, dict) or list(repository) != [
        "root", "root_path_sha256", "head_oid", "tree_oid",
    ]:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate repository shape is invalid"
        )
    _context_certificate_path(repository["root"], "repository.root")
    if (
        not matches(RUNTIME_EVENT_HEX64, repository["root_path_sha256"])
        or not matches(RUNTIME_EVENT_OID40, repository["head_oid"])
        or not matches(RUNTIME_EVENT_OID40, repository["tree_oid"])
    ):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate repository identity is invalid"
        )
    if not isinstance(rollout, dict) or list(rollout) != [
        "path", "path_sha256", "file_sha256", "session_cwd", "session_meta", "task_complete",
    ]:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate rollout shape is invalid"
        )
    rollout_path = _context_certificate_path(rollout["path"], "rollout.path")
    if (
        not matches(RUNTIME_EVENT_HEX64, rollout["path_sha256"])
        or not matches(RUNTIME_EVENT_HEX64, rollout["file_sha256"])
        or not isinstance(rollout["session_cwd"], str)
        or not rollout["session_cwd"]
    ):
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate rollout identity is invalid"
        )
    for field in ("session_meta", "task_complete"):
        descriptor = rollout[field]
        if not isinstance(descriptor, dict) or list(descriptor) != [
            "line", "byte_offset", "byte_length", "record_sha256",
        ]:
            raise RuntimeEventMaterializationError(
                "context_schema_invalid", f"context certificate {field} shape is invalid"
            )
        if (
            type(descriptor["line"]) is not int
            or descriptor["line"] <= 0
            or type(descriptor["byte_offset"]) is not int
            or descriptor["byte_offset"] < 0
            or type(descriptor["byte_length"]) is not int
            or descriptor["byte_length"] <= 0
            or not matches(RUNTIME_EVENT_HEX64, descriptor["record_sha256"])
        ):
            raise RuntimeEventMaterializationError(
                "context_schema_invalid", f"context certificate {field} range is invalid"
            )
    if _context_certificate_id(value) != value["certificate_id"]:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate id does not cover canonical bytes"
        )
    if _context_certificate_bytes(value) != raw:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context certificate is not canonical"
        )
    if not rollout_path:
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "rollout path is empty"
        )


def _source_git_identity(root: Path) -> tuple[str, str]:
    """Read the current source repository HEAD and tree identities."""
    head = run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"], check=False)
    tree = run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{tree}"], check=False)
    head_oid = head.stdout.strip()
    tree_oid = tree.stdout.strip()
    if (
        head.returncode != 0
        or tree.returncode != 0
        or not RUNTIME_EVENT_OID40.fullmatch(head_oid)
        or not RUNTIME_EVENT_OID40.fullmatch(tree_oid)
    ):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "source Git HEAD/tree identity is unavailable"
        )
    return head_oid, tree_oid


def _build_context_discovery_certificate(
    context: ArchiveContext, run_id: str, agent_context_id: str, turn_id: str
) -> tuple[dict[str, object], dict[str, object]]:
    """Build one certificate from the selected native rollout snapshot."""
    source = discover_rollout_context(agent_context_id, turn_id)
    root = context.source_root.resolve()
    root_bytes = root.as_posix().encode("utf-8")
    head_oid, tree_oid = _source_git_identity(root)
    value: dict[str, object] = {
        "schema": CONTEXT_DISCOVERY_CERTIFICATE_SCHEMA,
        "certificate_id": "0" * 64,
        "context": {
            "schema": RUNTIME_EVENT_CONTEXT_SCHEMA,
            "agent_id": source["agent_id"],
            "agent_context_id": source["agent_context_id"],
            "codex_thread_id": source["codex_thread_id"],
            "parent_id": source["parent_id"],
            "turn_id": source["turn_id"],
            "role": source["role"],
        },
        "repository": {
            "root": root.as_posix(),
            "root_path_sha256": hashlib.sha256(root_bytes).hexdigest(),
            "head_oid": head_oid,
            "tree_oid": tree_oid,
        },
        "rollout": {
            "path": source["rollout_path"],
            "path_sha256": source["rollout_path_sha256"],
            "file_sha256": source["rollout_file_sha256"],
            "session_cwd": source["session_cwd"],
            "session_meta": source["session_meta"],
            "task_complete": source["task_complete"],
        },
    }
    value["certificate_id"] = _context_certificate_id(value)
    raw = _context_certificate_bytes(value)
    validate_context_discovery_certificate(raw)
    return value, source


def _active_run_directory(context: ArchiveContext, run_id: str) -> Path:
    """Resolve and verify the selected run against the active-run pointer."""
    safe_id = safe_run_id(run_id)
    pointer = context.source_root / ACTIVE_RUN_POINTER
    if not pointer.is_file():
        raise RuntimeEventMaterializationError(
            "source_unavailable", "active run pointer is absent"
        )
    active_value = pointer.read_text(encoding="utf-8").strip()
    if not active_value:
        raise RuntimeEventMaterializationError(
            "source_unavailable", "active run pointer is empty"
        )
    active_run = Path(active_value)
    if not active_run.is_absolute():
        active_run = pointer.parent / active_run
    active_run = active_run.resolve()
    expected_run = (context.source_root / DEFAULT_AGENT_REPORT_ROOT / safe_id).resolve()
    if active_run != expected_run:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "run id does not match the active run pointer"
        )
    if not active_run.is_dir():
        raise RuntimeEventMaterializationError(
            "source_unavailable", "active run directory is absent"
        )
    return active_run
def _require_relative_schema_path(value: object, field: str) -> str:
    """Validate one canonical repository-relative schema path."""
    if (
        not isinstance(value, str)
        or Path(value).is_absolute()
        or _path_has_traversal(value)
    ):
        raise RuntimeEventMaterializationError("schema_invalid", f"{field} is unsafe")
    return value


def _porcelain_source_paths(path: str) -> tuple[str, ...]:
    """Return each repository path encoded by one porcelain-v1 path field."""
    return tuple(part.strip().strip('"') for part in path.split(" -> "))


def parse_porcelain_v1_line(line: str) -> dict[str, str]:
    """Parse one porcelain-v1 line without collapsing either status column."""
    if (
        len(line) < GIT_PORCELAIN_STATUS_MIN_LINE_LENGTH
        or line[2] != " "
        or "\0" in line
        or "\n" in line
        or "\r" in line
    ):
        raise RuntimeEventMaterializationError("source_snapshot_invalid", "porcelain-v1 line is too short")
    return {"raw": line, "status_x": line[0], "status_y": line[1], "separator": line[2], "path": line[3:]}


def capture_porcelain_v1(root: Path) -> tuple[dict[str, str], ...]:
    """Capture ordered raw porcelain-v1 status lines and validate their shape."""
    result = run(["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"], check=False)
    if result.returncode != 0:
        raise RuntimeEventMaterializationError("source_snapshot_invalid", result.stderr.strip())
    statuses: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parsed = parse_porcelain_v1_line(line)
        if not parsed["path"]:
            raise RuntimeEventMaterializationError("source_snapshot_invalid", "porcelain-v1 path is empty")
        source_paths = _porcelain_source_paths(parsed["path"])
        if any(_path_has_traversal(path) for path in source_paths):
            raise RuntimeEventMaterializationError(
                "source_snapshot_invalid", "porcelain-v1 path is unsafe"
            )
        if not all(is_source_snapshot_path(Path(path)) for path in source_paths):
            continue
        statuses.append(parsed)
    return tuple(statuses)


def validate_markdown_review_result(text: str, expected_gate_id: str) -> dict[str, object]:
    """Validate one fixed Markdown review artifact through W2 review checks."""
    identity = parse_review_identity(text)
    decisions = final_review_decision_lines(text)
    if len(decisions) != 1 or decisions[0].upper() not in {"APPROVE", "REVISE", "ESCALATE"}:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "review decision is not exactly one supported value")
    decision = decisions[0].upper()
    if identity.decision_approved != (decision == "APPROVE"):
        raise RuntimeEventMaterializationError(
            "result_authority_mismatch",
            "review decision disagrees with canonical identity authority",
        )
    if identity.design_artifact_path is None or identity.review_target_sha256 is None:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "review identity fields are incomplete")
    if check_final_review_artifact(text) and decision == "APPROVE":
        raise RuntimeEventMaterializationError("result_authority_mismatch", "; ".join(check_final_review_artifact(text)))
    return {
        "schema": "ReviewArtifactV1",
        "path": identity.design_artifact_path,
        "target_paths": [identity.design_artifact_path],
        "gate_id": expected_gate_id,
        "gate_result": decision,
        "decision": decision,
        "review_target_sha256": identity.review_target_sha256,
    }


def _validation_json_object(
    items: list[tuple[str, object]],
) -> dict[str, object]:
    """Build one validation JSON object only when every key is unique."""
    if len({key for key, _value in items}) != len(items):
        raise RuntimeEventMaterializationError(
            "result_authority_mismatch", "validation result has duplicate keys"
        )
    return dict(items)


def parse_validation_result(raw: bytes, expected_gate_id: str) -> dict[str, object]:
    """Parse the exact generic validation result input schema."""
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_validation_json_object
        )
    except RuntimeEventMaterializationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation result is not UTF-8 JSON") from exc
    expected = ["schema", "result", "gate_id", "target_paths", "base_ref", "observations"]
    if not isinstance(value, dict) or list(value) != expected or value.get("schema") != "agent_canon.runtime_result_input.v1":
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation result keys or schema mismatch")
    if value.get("gate_id") != expected_gate_id or value.get("result") not in {"PASS", "FAIL", "BLOCKED"}:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation result gate mismatch")
    target_paths = value.get("target_paths")
    if not isinstance(target_paths, list) or not target_paths or len(set(target_paths)) != len(target_paths):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation target_paths are invalid")
    if any(
        not isinstance(path, str)
        or Path(path).is_absolute()
        or _path_has_traversal(path)
        for path in cast(list[object], target_paths)
    ):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation target_paths are invalid")
    if not isinstance(value.get("base_ref"), str) or not value["base_ref"] or not isinstance(value.get("observations"), dict):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation identity fields are incomplete")
    result = cast(dict[str, object], value)
    result["gate_result"] = result["result"]
    result["decision"] = "NONE"
    return result


def parse_lifecycle_result(text: str, expected_gate_id: str) -> dict[str, object]:
    """Parse fixed closeout gate fields without treating prose as authority."""
    owned_fields = (
        "status",
        "closeout_gate_id",
        "target_paths",
        "base_ref",
        "evidence_path",
        "evidence_sha256",
    )
    lines = text.splitlines()
    section_starts = [
        index
        for index, line in enumerate(lines)
        if line.strip() == "## Completion Readiness"
    ]
    if len(section_starts) != 1:
        raise RuntimeEventMaterializationError(
            "result_authority_mismatch",
            "closeout readiness section is not exactly one",
        )
    section_start = section_starts[0]
    section_end = len(lines)
    for index in range(section_start + 1, len(lines)):
        if re.match(r"^#{1,2}(?:\s|$)", lines[index].strip()):
            section_end = index
            break

    fields: dict[str, str] = {}
    for index, line in enumerate(lines):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key not in owned_fields:
            continue
        if not section_start < index < section_end:
            raise RuntimeEventMaterializationError(
                "result_authority_mismatch",
                "closeout field appears outside readiness section",
            )
        if key in fields:
            raise RuntimeEventMaterializationError(
                "result_authority_mismatch", "closeout field is duplicated"
            )
        fields[key] = value.strip()
    if set(fields) != set(owned_fields):
        raise RuntimeEventMaterializationError(
            "result_authority_mismatch", "closeout readiness fields are incomplete"
        )
    if fields.get("closeout_gate_id") != expected_gate_id:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "closeout gate id mismatch")
    status = fields.get("status")
    if status not in {"READY", "BLOCKED", "INCOMPLETE"}:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "closeout status is unsupported")
    target_paths = [item.strip() for item in fields.get("target_paths", "").split(",") if item.strip()]
    evidence_path = fields.get("evidence_path", "")
    if not target_paths or any(
        Path(item).is_absolute() or _path_has_traversal(item)
        for item in target_paths
    ):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "closeout target_paths are invalid")
    if (
        not evidence_path
        or Path(evidence_path).is_absolute()
        or _path_has_traversal(evidence_path)
    ):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "closeout evidence_path is invalid")
    if not fields.get("base_ref") or not RUNTIME_EVENT_HEX64.fullmatch(fields.get("evidence_sha256", "")):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "closeout identity fields are incomplete")
    return {
        "schema": "CloseoutGateV1", "path": "closeout_gate.md", "target_paths": target_paths,
        "evidence_path": evidence_path, "base_ref": fields["base_ref"], "gate_id": expected_gate_id,
        "gate_result": status, "decision": "NONE", "evidence_sha256": fields["evidence_sha256"],
    }


def validate_validation_result(result: dict[str, object]) -> None:
    """Validate the fixed validation-result observation shape."""
    observations = result.get("observations")
    if not isinstance(observations, dict):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "validation observations are missing")
    for field in ("head_oid", "base_oid"):
        if not isinstance(observations.get(field), str) or not RUNTIME_EVENT_OID40.fullmatch(cast(str, observations[field])):
            raise RuntimeEventMaterializationError("result_authority_mismatch", f"validation {field} is invalid")


def validate_lifecycle_result(result: dict[str, object]) -> None:
    """Validate lifecycle evidence fields before source identity verification."""
    if result.get("gate_result") not in {"READY", "BLOCKED", "INCOMPLETE"}:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "lifecycle gate result is invalid")
    evidence_path = result.get("evidence_path")
    target_paths = result.get("target_paths")
    if not isinstance(evidence_path, str) or not evidence_path or not is_source_snapshot_path(Path(evidence_path)):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "lifecycle evidence_path is outside source scope")
    if not isinstance(target_paths, list) or evidence_path not in target_paths:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "lifecycle evidence_path is not a target path")


def derive_gate_result(result: dict[str, object]) -> str:
    """Return the one verifier-owned gate result."""
    value = result.get("gate_result")
    if not isinstance(value, str) or value not in RUNTIME_EVENT_GATE_RESULTS:
        raise RuntimeEventMaterializationError("result_authority_mismatch", "gate result is unsupported")
    return value


def _git_bytes(root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one Git command while retaining exact binary output."""
    return subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)


def verify_target_identities(root: Path, result: dict[str, object], base_ref: str) -> tuple[dict[str, object], ...]:
    """Verify exact target content/blob and base identities for one artifact."""
    base = run(["git", "-C", str(root), "rev-parse", "--verify", base_ref], check=False)
    head = run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"], check=False)
    if base.returncode != 0 or head.returncode != 0:
        raise RuntimeEventMaterializationError("target_identity_mismatch", "Git base/head identity is unavailable")
    base_oid, head_oid = base.stdout.strip(), head.stdout.strip()
    if not RUNTIME_EVENT_OID40.fullmatch(base_oid) or not RUNTIME_EVENT_OID40.fullmatch(head_oid):
        raise RuntimeEventMaterializationError("target_identity_mismatch", "Git base/head identity is invalid")
    target_paths = result.get("target_paths")
    if not isinstance(target_paths, list) or not target_paths:
        raise RuntimeEventMaterializationError("target_identity_mismatch", "target path set is empty")
    expected_sha = result.get("review_target_sha256")
    observations = result.get("observations")
    observed_targets = observations.get("targets") if isinstance(observations, dict) else None
    if observed_targets is not None and not isinstance(observed_targets, dict):
        raise RuntimeEventMaterializationError("target_identity_mismatch", "target observations are invalid")
    identities: list[dict[str, object]] = []
    ordered_paths = sorted(cast(list[str], target_paths), key=lambda value: value.encode("utf-8"))
    if len(set(ordered_paths)) != len(ordered_paths):
        raise RuntimeEventMaterializationError("target_identity_mismatch", "target paths are duplicated")
    for path_value in ordered_paths:
        relative = Path(path_value)
        if (
            relative.is_absolute()
            or _path_has_traversal(path_value)
            or not is_source_snapshot_path(relative)
        ):
            raise RuntimeEventMaterializationError("target_identity_mismatch", f"target path is outside source scope: {path_value}")
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
            target_bytes = target.read_bytes()
        except (OSError, ValueError) as exc:
            raise RuntimeEventMaterializationError("target_identity_mismatch", f"target cannot be read: {path_value}") from exc
        content_sha = hashlib.sha256(target_bytes).hexdigest()
        blob = run(["git", "-C", str(root), "hash-object", "--", path_value], check=False)
        blob_oid = blob.stdout.strip()
        if blob.returncode != 0 or not RUNTIME_EVENT_OID40.fullmatch(blob_oid):
            raise RuntimeEventMaterializationError("target_identity_mismatch", f"target blob is unavailable: {path_value}")
        if isinstance(expected_sha, str) and content_sha != expected_sha:
            raise RuntimeEventMaterializationError("target_identity_mismatch", f"target sha mismatch: {path_value}")
        if isinstance(observed_targets, dict) and isinstance(observed_targets.get(path_value), dict):
            observed = cast(dict[str, object], observed_targets[path_value])
            if observed.get("content_sha256") != content_sha or observed.get("git_blob_oid") != blob_oid:
                raise RuntimeEventMaterializationError("target_identity_mismatch", f"recorded target mismatch: {path_value}")
        present = run(["git", "-C", str(root), "cat-file", "-e", f"{base_oid}:{path_value}"], check=False).returncode == 0
        base_sha: str | None = None
        base_blob: str | None = None
        if present:
            base_content = _git_bytes(root, ["show", f"{base_oid}:{path_value}"])
            base_object = run(["git", "-C", str(root), "rev-parse", "--verify", f"{base_oid}:{path_value}"], check=False)
            if base_content.returncode != 0 or base_object.returncode != 0:
                raise RuntimeEventMaterializationError("target_identity_mismatch", f"base target cannot be read: {path_value}")
            base_sha = hashlib.sha256(base_content.stdout).hexdigest()
            base_blob = base_object.stdout.strip()
        identities.append({
            "path": path_value, "content_sha256": content_sha, "git_blob_oid": blob_oid,
            "base_present": present, "base_content_sha256": base_sha, "base_git_blob_oid": base_blob,
        })
    return tuple(identities)


def canonical_preimage_bytes(record: RuntimeEventRecord) -> bytes:
    """Render the exact materialization preimage in its fixed nested order."""
    value = record.value
    source_event = cast(dict[str, object], value["source_event"])
    gate = cast(dict[str, object], value["gate"])
    result_artifact = cast(dict[str, object], value["result_artifact"])
    source_snapshot = cast(dict[str, object], value["source_snapshot"])
    preimage = {
        "schema": RUNTIME_EVENT_MATERIALIZATION_SCHEMA,
        "result_family": value["result_family"],
        "gate": {"id": gate["id"], "result": gate["result"]},
        "source_event": {
            "stable_record_id": source_event["stable_record_id"],
            "rollout_path_sha256": source_event["rollout_path_sha256"],
            "rollout_file_sha256": source_event["rollout_file_sha256"],
            "record_line": source_event["record_line"],
            "record_byte_offset": source_event["record_byte_offset"],
            "record_byte_length": source_event["record_byte_length"],
        },
        "result_artifact": {
            "artifact_sha256": result_artifact["artifact_sha256"],
            "artifact_blob_oid": result_artifact["artifact_blob_oid"],
            "gate_id": result_artifact["gate_id"],
        },
        "target_identities": value["target_identities"],
        "source_snapshot": {
            "head_oid": source_snapshot["head_oid"],
            "base_ref": source_snapshot["base_ref"],
            "base_oid": source_snapshot["base_oid"],
        },
    }
    return (json.dumps(preimage, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def derive_publication_attempt_id(materialization_id: str, target_path: str) -> str:
    """Derive the sole deterministic publication-attempt identity."""
    if not RUNTIME_EVENT_HEX64.fullmatch(materialization_id):
        raise RuntimeEventMaterializationError(
            "schema_invalid", "materialization id is not canonical"
        )
    normalized_target = _require_relative_schema_path(
        target_path, "publication_intent.target_path"
    )
    preimage = (
        RUNTIME_EVENT_PUBLICATION_ATTEMPT_SCHEMA.encode("ascii")
        + b"\0"
        + materialization_id.encode("ascii")
        + b"\0"
        + normalized_target.encode("utf-8")
    )
    return hashlib.sha256(preimage).hexdigest()


def _canonical_runtime_event_bytes(record: RuntimeEventRecord) -> bytes:
    """Render canonical event bytes while calculating its sole self-hash."""
    value = dict(record.value)
    zeroed = dict(value)
    zeroed["artifact_sha256"] = "0" * 64
    preimage = (json.dumps(zeroed, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    value["artifact_sha256"] = hashlib.sha256(preimage).hexdigest()
    record.value.clear()
    record.value.update(value)
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def validate_runtime_event_schema(raw: bytes) -> None:
    """Validate exact runtime-event structure, canonical bytes, and hashes."""
    if not raw.endswith(b"\n") or b"\n" in raw[:-1] or not raw[:-1]:
        raise RuntimeEventMaterializationError("schema_invalid", "runtime event must be one JSON line with one terminal LF")

    def pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        if len({key for key, _value in pairs}) != len(pairs):
            raise RuntimeEventMaterializationError("schema_invalid", "duplicate JSON key")
        return dict(pairs)

    def matches(pattern: re.Pattern[str], value: object) -> bool:
        """Return whether one typed text value matches a schema pattern."""
        return isinstance(value, str) and pattern.fullmatch(value) is not None

    try:
        value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=pairs)
    except RuntimeEventMaterializationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeEventMaterializationError("schema_invalid", "runtime event JSON is invalid") from exc
    if not isinstance(value, dict):
        raise RuntimeEventMaterializationError("schema_invalid", "runtime event must be an object")
    top = ["schema", "materialization_id", "result_family", "gate", "source_event", "result_artifact", "target_identities", "source_snapshot", "publication_intent", "artifact_sha256"]
    if list(value) != top or value.get("schema") != RUNTIME_EVENT_SCHEMA:
        raise RuntimeEventMaterializationError("schema_invalid", "runtime event top-level keys are not canonical")
    if value.get("result_family") not in RUNTIME_EVENT_FAMILY_NAMES or not matches(RUNTIME_EVENT_HEX64, value.get("materialization_id")):
        raise RuntimeEventMaterializationError("schema_invalid", "runtime event schema or materialization id is invalid")
    expected_nested = {
        "gate": ["id", "result"],
        "source_event": ["agent_id", "agent_context_id", "codex_thread_id", "parent_id", "turn_id", "role", "decision", "applicable_gate_result", "rollout_path", "rollout_path_bytes_b64", "rollout_path_sha256", "rollout_file_sha256", "record_line", "record_byte_offset", "record_byte_length", "record_bytes_b64", "record_sha256", "stable_record_id"],
        "result_artifact": ["path", "schema", "artifact_sha256", "artifact_blob_oid", "gate_id", "gate_result", "target_paths", "base_ref", "base_oid"],
        "source_snapshot": ["head_oid", "base_ref", "base_oid", "porcelain_v1"],
        "publication_intent": ["schema", "attempt_id", "target_path", "prepared_state"],
    }
    objects: dict[str, dict[str, object]] = {}
    for name, keys in expected_nested.items():
        item = value.get(name)
        if not isinstance(item, dict) or list(item) != keys:
            raise RuntimeEventMaterializationError("schema_invalid", f"{name} keys are not canonical")
        objects[name] = cast(dict[str, object], item)
    gate = objects["gate"]
    if not isinstance(gate["id"], str) or gate["result"] not in RUNTIME_EVENT_GATE_RESULTS:
        raise RuntimeEventMaterializationError("schema_invalid", "gate is invalid")
    fixed_result_family_spec(cast(str, value["result_family"]), cast(str, gate["id"]))
    source = objects["source_event"]
    for field in ("agent_id", "agent_context_id", "codex_thread_id", "parent_id", "turn_id"):
        if not isinstance(source[field], str) or not RUNTIME_EVENT_UUID.fullmatch(cast(str, source[field])):
            raise RuntimeEventMaterializationError("schema_invalid", f"source event {field} is invalid")
    if not isinstance(source["role"], str) or not source["role"] or source["decision"] not in RUNTIME_EVENT_DECISIONS or source["applicable_gate_result"] != gate["result"]:
        raise RuntimeEventMaterializationError("schema_invalid", "source event role, decision, or gate is invalid")
    if (
        not isinstance(source["rollout_path"], str)
        or not Path(cast(str, source["rollout_path"])).is_absolute()
        or _path_has_traversal(cast(str, source["rollout_path"]))
    ):
        raise RuntimeEventMaterializationError("schema_invalid", "rollout path is invalid")
    if type(source["record_line"]) is not int or source["record_line"] <= 0 or type(source["record_byte_offset"]) is not int or source["record_byte_offset"] < 0 or type(source["record_byte_length"]) is not int or source["record_byte_length"] <= 0:
        raise RuntimeEventMaterializationError("schema_invalid", "record range is invalid")
    for field in ("rollout_path_sha256", "rollout_file_sha256", "record_sha256", "stable_record_id"):
        if not matches(RUNTIME_EVENT_HEX64, source[field]):
            raise RuntimeEventMaterializationError("schema_invalid", f"source event {field} is invalid")
    if source["stable_record_id"] != source["record_sha256"]:
        raise RuntimeEventMaterializationError("schema_invalid", "stable record id mismatch")
    try:
        path_bytes = base64.b64decode(cast(str, source["rollout_path_bytes_b64"]), validate=True)
        record_bytes = base64.b64decode(cast(str, source["record_bytes_b64"]), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeEventMaterializationError("schema_invalid", "source event base64 is invalid") from exc
    if path_bytes != cast(str, source["rollout_path"]).encode("utf-8") or hashlib.sha256(path_bytes).hexdigest() != source["rollout_path_sha256"] or len(record_bytes) != source["record_byte_length"] or hashlib.sha256(record_bytes).hexdigest() != source["record_sha256"]:
        raise RuntimeEventMaterializationError("schema_invalid", "source byte identity mismatch")
    artifact = objects["result_artifact"]
    spec = fixed_result_family_spec(cast(str, value["result_family"]), cast(str, artifact["gate_id"]))
    artifact_path = _require_relative_schema_path(
        artifact["path"], "result_artifact.path"
    )
    if artifact["schema"] != spec.schema or artifact["gate_result"] != gate["result"]:
        raise RuntimeEventMaterializationError("schema_invalid", "result artifact identity is invalid")
    if not matches(RUNTIME_EVENT_HEX64, artifact["artifact_sha256"]) or not matches(RUNTIME_EVENT_OID40, artifact["artifact_blob_oid"]) or not matches(RUNTIME_EVENT_OID40, artifact["base_oid"]):
        raise RuntimeEventMaterializationError("schema_invalid", "result artifact hashes are invalid")
    targets = artifact["target_paths"]
    if not isinstance(targets, list) or not targets:
        raise RuntimeEventMaterializationError("schema_invalid", "result artifact target paths are invalid")
    target_paths = [
        _require_relative_schema_path(item, "result_artifact.target_paths")
        for item in targets
    ]
    if (
        len(set(target_paths)) != len(target_paths)
        or target_paths != sorted(target_paths, key=lambda item: item.encode("utf-8"))
    ):
        raise RuntimeEventMaterializationError("schema_invalid", "result artifact target paths are invalid")
    snapshot = objects["source_snapshot"]
    if not RUNTIME_EVENT_OID40.fullmatch(cast(str, snapshot["head_oid"])) or snapshot["base_oid"] != artifact["base_oid"] or snapshot["base_ref"] != artifact["base_ref"]:
        raise RuntimeEventMaterializationError("schema_invalid", "source snapshot base identity is invalid")
    if not isinstance(snapshot["porcelain_v1"], list) or any(not isinstance(line, str) for line in cast(list[object], snapshot["porcelain_v1"])):
        raise RuntimeEventMaterializationError("schema_invalid", "source snapshot porcelain is invalid")
    for line in cast(list[str], snapshot["porcelain_v1"]):
        try:
            parsed = parse_porcelain_v1_line(line)
        except RuntimeEventMaterializationError as exc:
            raise RuntimeEventMaterializationError(
                "schema_invalid", "source snapshot porcelain is invalid"
            ) from exc
        porcelain_paths = _porcelain_source_paths(parsed["path"])
        if any(_path_has_traversal(path) for path in porcelain_paths) or not all(
            is_source_snapshot_path(Path(path)) for path in porcelain_paths
        ):
            raise RuntimeEventMaterializationError(
                "schema_invalid", "source snapshot contains an unsafe or generated path"
            )
    identity_list = value["target_identities"]
    if not isinstance(identity_list, list) or not identity_list:
        raise RuntimeEventMaterializationError("schema_invalid", "target identities are empty")
    identity_paths: list[str] = []
    for identity in cast(list[object], identity_list):
        if not isinstance(identity, dict) or list(identity) != ["path", "content_sha256", "git_blob_oid", "base_present", "base_content_sha256", "base_git_blob_oid"]:
            raise RuntimeEventMaterializationError("schema_invalid", "target identity shape is invalid")
        identity_path = _require_relative_schema_path(
            identity["path"], "target_identities.path"
        )
        identity_paths.append(identity_path)
        if not matches(RUNTIME_EVENT_HEX64, identity["content_sha256"]) or not matches(RUNTIME_EVENT_OID40, identity["git_blob_oid"]) or not isinstance(identity["base_present"], bool):
            raise RuntimeEventMaterializationError("schema_invalid", "target identity value is invalid")
        if identity["base_present"]:
            if not matches(RUNTIME_EVENT_HEX64, identity["base_content_sha256"]) or not matches(RUNTIME_EVENT_OID40, identity["base_git_blob_oid"]):
                raise RuntimeEventMaterializationError("schema_invalid", "present target base identity is invalid")
        elif identity["base_content_sha256"] is not None or identity["base_git_blob_oid"] is not None:
            raise RuntimeEventMaterializationError("schema_invalid", "absent target base identity must be null")
    if identity_paths != target_paths or identity_paths != sorted(
        identity_paths, key=lambda item: item.encode("utf-8")
    ):
        raise RuntimeEventMaterializationError(
            "schema_invalid", "target path identities do not match target_paths"
        )
    publication = objects["publication_intent"]
    publication_path = _require_relative_schema_path(
        publication["target_path"], "publication_intent.target_path"
    )
    target_match = RUNTIME_EVENT_TARGET_NAME.fullmatch(publication_path)
    if (
        target_match is None
        or target_match.group("run") in {".", ".."}
        or target_match.group("unit") != cast(str, source["record_sha256"])[:16]
        or artifact_path
        != f"reports/agents/{target_match.group('run')}/{spec.artifact_name}"
        or publication["schema"] != RUNTIME_EVENT_PUBLICATION_INTENT_SCHEMA
        or publication["prepared_state"] != "prepared"
        or not matches(RUNTIME_EVENT_HEX64, publication["attempt_id"])
    ):
        raise RuntimeEventMaterializationError("schema_invalid", "publication intent is invalid")
    if not matches(RUNTIME_EVENT_HEX64, value["artifact_sha256"]):
        raise RuntimeEventMaterializationError("schema_invalid", "artifact hash is invalid")
    record = RuntimeEventRecord(cast(dict[str, object], value))
    expected_id = hashlib.sha256(RUNTIME_EVENT_MATERIALIZATION_SCHEMA.encode("utf-8") + b"\0" + canonical_preimage_bytes(record)).hexdigest()
    if value["materialization_id"] != expected_id:
        raise RuntimeEventMaterializationError("schema_invalid", "materialization id mismatch")
    if publication["attempt_id"] != derive_publication_attempt_id(
        cast(str, value["materialization_id"]), publication_path
    ):
        raise RuntimeEventMaterializationError(
            "schema_invalid", "publication attempt id mismatch"
        )
    zeroed = dict(value)
    zeroed["artifact_sha256"] = "0" * 64
    expected_artifact = hashlib.sha256((json.dumps(zeroed, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")).hexdigest()
    if value["artifact_sha256"] != expected_artifact:
        raise RuntimeEventMaterializationError("schema_invalid", "artifact hash coverage mismatch")
    canonical = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if canonical != raw:
        raise RuntimeEventMaterializationError("schema_invalid", "runtime event is not canonical")


def _readback_runtime_event(target: Path) -> RuntimeEventRecord:
    """Read and validate one committed runtime-event record."""
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_uncertain", "artifact readback failed"
        ) from exc
    validate_runtime_event_schema(raw)
    return RuntimeEventRecord(cast(dict[str, object], json.loads(raw[:-1].decode("utf-8"))))


def _renameat2_noreplace(source: Path, target: Path) -> None:
    """Atomically rename one identity-owned temp without replacing a target."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOSYS, "renameat2(RENAME_NOREPLACE) is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(target),
        RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), target)
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
        raise OSError(error_number, os.strerror(error_number), target)
    raise OSError(error_number, os.strerror(error_number), target)


def _owner_mutation_exclusive_mode(mode: int, required_owner_bits: int) -> bool:
    """Require owner mutation bits without group or other write access."""
    permissions = S_IMODE(mode)
    return (
        permissions & required_owner_bits == required_owner_bits
        and permissions & 0o022 == 0
    )


def _validate_publication_attempt_directories(attempt_directory: Path) -> Path:
    """Validate every fixed 0700 directory in one publication attempt path."""
    spool_root = attempt_directory.parent
    runtime_spool = spool_root.parent
    agent_canon_directory = runtime_spool.parent
    source_root = agent_canon_directory.parent
    if (
        spool_root.name != "publication-outcome"
        or runtime_spool.name != "runtime-event-spool"
        or agent_canon_directory.name != ".agent-canon"
    ):
        raise ValueError("publication spool path mismatch")
    resolved_source = source_root.resolve(strict=True)
    for directory in (
        agent_canon_directory,
        runtime_spool,
        spool_root,
        attempt_directory,
    ):
        metadata = directory.lstat()
        resolved = directory.resolve(strict=True)
        resolved.relative_to(resolved_source)
        if (
            resolved != directory
            or directory.is_symlink()
            or not S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or not _owner_mutation_exclusive_mode(metadata.st_mode, 0o700)
        ):
            raise ValueError("attempt directory metadata mismatch")
    return spool_root


def validate_publication_attempt_lock(attempt_lock: PublicationAttemptLock) -> None:
    """Validate the exact attempt directory, lock path, and open lock FD."""
    if not RUNTIME_EVENT_HEX64.fullmatch(attempt_lock.attempt_id):
        raise RuntimeEventMaterializationError(
            "publication_attempt_lock_invalid", "attempt id is invalid"
        )
    spool_root = attempt_lock.attempt_directory.parent
    expected_directory = spool_root / attempt_lock.attempt_id
    expected_lock = expected_directory / ".attempt.lock"
    try:
        validated_root = _validate_publication_attempt_directories(
            attempt_lock.attempt_directory
        )
        resolved_root = validated_root.resolve(strict=True)
        resolved_directory = attempt_lock.attempt_directory.resolve(strict=True)
        resolved_directory.relative_to(resolved_root)
        if (
            validated_root != spool_root
            or resolved_directory != expected_directory
            or attempt_lock.lock_path != expected_lock
            or attempt_lock.lock_path.parent != attempt_lock.attempt_directory
        ):
            raise ValueError("attempt path mismatch")
        path_metadata = attempt_lock.lock_path.lstat()
        fd_metadata = os.fstat(attempt_lock.fd)
        if (
            attempt_lock.lock_path.is_symlink()
            or not S_ISREG(path_metadata.st_mode)
            or not S_ISREG(fd_metadata.st_mode)
            or path_metadata.st_uid != os.geteuid()
            or fd_metadata.st_uid != os.geteuid()
            or path_metadata.st_nlink != 1
            or fd_metadata.st_nlink != 1
            or not _owner_mutation_exclusive_mode(path_metadata.st_mode, 0o600)
            or not _owner_mutation_exclusive_mode(fd_metadata.st_mode, 0o600)
            or (path_metadata.st_dev, path_metadata.st_ino)
            != (fd_metadata.st_dev, fd_metadata.st_ino)
        ):
            raise ValueError("attempt lock metadata mismatch")
    except (OSError, ValueError) as exc:
        raise RuntimeEventMaterializationError(
            "publication_attempt_lock_invalid", "attempt lock validation failed"
        ) from exc


@contextmanager
def acquire_publication_attempt_lock(
    source_root: Path, attempt_id: str
) -> Iterator[PublicationAttemptLock]:
    """Acquire and always release the sole nonblocking same-attempt lock."""
    if not RUNTIME_EVENT_HEX64.fullmatch(attempt_id):
        raise RuntimeEventMaterializationError(
            "publication_attempt_lock_invalid", "attempt id is invalid"
        )
    spool_root = runtime_event_publication_outcome_spool_root(source_root)
    attempt_directory = spool_root / attempt_id
    lock_path = attempt_directory / ".attempt.lock"
    fd = -1
    locked = False
    body_error: BaseException | None = None
    try:
        source_root = source_root.resolve(strict=True)
        relative_spool = spool_root.relative_to(source_root)
        if relative_spool.parts != (
            ".agent-canon",
            "runtime-event-spool",
            "publication-outcome",
        ):
            raise RuntimeEventMaterializationError(
                "publication_attempt_lock_invalid",
                "publication spool root is not canonical",
            )
        directory = source_root
        for component in (*relative_spool.parts, attempt_id):
            directory /= component
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                pass
            metadata = directory.lstat()
            if (
                directory.is_symlink()
                or not S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or not _owner_mutation_exclusive_mode(metadata.st_mode, 0o700)
            ):
                raise RuntimeEventMaterializationError(
                    "publication_attempt_lock_invalid",
                    "attempt directory validation failed",
                )
        try:
            _validate_publication_attempt_directories(attempt_directory)
        except (OSError, ValueError) as exc:
            raise RuntimeEventMaterializationError(
                "publication_attempt_lock_invalid", "attempt directory escapes spool root"
            ) from exc
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if not nofollow:
            raise RuntimeEventMaterializationError(
                "publication_attempt_lock_invalid", "O_NOFOLLOW is unavailable"
            )
        created = False
        try:
            fd = os.open(
                lock_path,
                flags | nofollow | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            created = True
        except FileExistsError:
            fd = os.open(lock_path, flags | nofollow)
        if created:
            os.fchmod(fd, 0o600)
        attempt_lock = PublicationAttemptLock(
            attempt_id=attempt_id,
            attempt_directory=attempt_directory,
            lock_path=lock_path,
            fd=fd,
        )
        validate_publication_attempt_lock(attempt_lock)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeEventMaterializationError(
                "publication_attempt_busy", "publication attempt is busy"
            ) from exc
        locked = True
        try:
            yield attempt_lock
        except BaseException as exc:
            body_error = exc
            raise
    except RuntimeEventMaterializationError:
        raise
    except (OSError, ValueError) as exc:
        raise RuntimeEventMaterializationError(
            "publication_attempt_lock_invalid", "attempt lock acquisition failed"
        ) from exc
    finally:
        release_error: OSError | None = None
        if fd >= 0:
            if locked:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError as exc:
                    release_error = exc
            try:
                os.close(fd)
            except OSError as exc:
                if release_error is None:
                    release_error = exc
            fd = -1
        if release_error is not None:
            error = RuntimeEventMaterializationError(
                "publication_attempt_lock_release_failed",
                "publication attempt lock release failed",
            )
            if body_error is not None:
                raise error from body_error
            raise error from release_error


def _publish_context_discovery_noreplace(target: Path, bytes_: bytes) -> None:
    """Publish one immutable context certificate with exact readback."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeEventMaterializationError(
                "context_record_collision", "certificate target is not a regular file"
            )
        if target.is_file():
            existing = target.read_bytes()
            if existing != bytes_:
                raise RuntimeEventMaterializationError(
                    "context_record_collision", "certificate target has different bytes"
                )
            validate_context_discovery_certificate(existing)
            return
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "context_publication_failure", "certificate target preparation failed"
        ) from exc

    fd = -1
    temporary: Path | None = None
    identity: tuple[int, int] | None = None
    published = False
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(fd, 0o600)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if not nofollow:
            raise RuntimeEventMaterializationError(
                "context_publication_failure", "O_NOFOLLOW is unavailable"
            )
        os.close(fd)
        fd = os.open(temporary, os.O_RDWR | nofollow)
        metadata = os.fstat(fd)
        identity = (metadata.st_dev, metadata.st_ino)
        if (
            not S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or not _owner_mutation_exclusive_mode(metadata.st_mode, 0o600)
        ):
            raise RuntimeEventMaterializationError(
                "context_publication_failure", "identity-owned temp metadata is invalid"
            )
        view = memoryview(bytes_)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise RuntimeEventMaterializationError(
                    "context_publication_failure", "certificate write made no progress"
                )
            view = view[written:]
        os.fsync(fd)
        if os.pread(fd, len(bytes_) + 1, 0) != bytes_:
            raise RuntimeEventMaterializationError(
                "context_publication_failure", "certificate temporary readback differs"
            )
        os.close(fd)
        fd = -1
        latest = temporary.lstat()
        if (
            not S_ISREG(latest.st_mode)
            or latest.st_uid != os.geteuid()
            or identity != (latest.st_dev, latest.st_ino)
            or latest.st_nlink != 1
            or not _owner_mutation_exclusive_mode(latest.st_mode, 0o600)
        ):
            raise RuntimeEventMaterializationError(
                "context_publication_failure", "identity-owned temp verification failed"
            )
        try:
            _renameat2_noreplace(temporary, target)
        except FileExistsError:
            if target.is_symlink() or not target.is_file():
                raise RuntimeEventMaterializationError(
                    "context_record_collision", "certificate target collision"
                )
            existing = target.read_bytes()
            if existing != bytes_:
                raise RuntimeEventMaterializationError(
                    "context_record_collision", "certificate target collision"
                )
            validate_context_discovery_certificate(existing)
            return
        published = True
        temporary = None
        _fsync_directory(target.parent, "artifact-parent")
        committed = target.read_bytes()
        if committed != bytes_:
            raise RuntimeEventMaterializationError(
                "context_publication_failure", "certificate target readback differs"
            )
        validate_context_discovery_certificate(committed)
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "context_publication_failure", "certificate publication failed"
        ) from exc
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "context_publication_failure", "certificate temporary close failed"
                ) from exc
        if temporary is not None:
            try:
                current = temporary.stat()
                if not published and identity == (current.st_dev, current.st_ino):
                    temporary.unlink()
            except OSError:
                pass


def _certificate_record(
    records: tuple[dict[str, object], ...],
    descriptor: dict[str, object],
    field: str,
) -> dict[str, object]:
    """Return the one rollout record covered by a certificate descriptor."""
    matches = tuple(
        record
        for record in records
        if record["line"] == descriptor["line"]
        and record["offset"] == descriptor["byte_offset"]
        and record["length"] == descriptor["byte_length"]
        and hashlib.sha256(cast(bytes, record["raw"])).hexdigest()
        == descriptor["record_sha256"]
    )
    if len(matches) != 1:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", f"{field} certificate range is not unique"
        )
    return matches[0]


def _verify_context_discovery_certificate(
    context: ArchiveContext, value: dict[str, object]
) -> dict[str, object]:
    """Revalidate a certificate against the current repository and rollout."""
    certificate_context = cast(dict[str, object], value["context"])
    repository = cast(dict[str, object], value["repository"])
    rollout = cast(dict[str, object], value["rollout"])
    root = context.source_root.resolve()
    root_bytes = root.as_posix().encode("utf-8")
    if (
        repository["root"] != root.as_posix()
        or repository["root_path_sha256"] != hashlib.sha256(root_bytes).hexdigest()
    ):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate repository path identity differs"
        )
    head_oid, tree_oid = _source_git_identity(root)
    if repository["head_oid"] != head_oid or repository["tree_oid"] != tree_oid:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate repository Git identity differs"
        )
    rollout_path = Path(cast(str, rollout["path"]))
    try:
        resolved_rollout_path = rollout_path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "source_unavailable", "certificate rollout path is unavailable"
        ) from exc
    session_roots = _runtime_session_roots()
    if (
        rollout_path.is_symlink()
        or resolved_rollout_path.as_posix() != rollout["path"]
        or not any(
            resolved_rollout_path.is_relative_to(root) for root in session_roots
        )
        or _rollout_name_identity(rollout_path) is None
        or cast(tuple[str, str], _rollout_name_identity(rollout_path))[1]
        != certificate_context["agent_context_id"]
    ):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate rollout path identity differs"
        )
    rollout_path = resolved_rollout_path
    eligible = _rollout_files(cast(str, certificate_context["agent_context_id"]))
    if len(eligible) != 1 or eligible[0] != rollout_path:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous" if len(eligible) > 1 else "source_identity_mismatch",
            "certificate rollout is absent or not unique",
        )
    try:
        file_bytes = rollout_path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "source_unavailable", "certificate rollout cannot be read"
        ) from exc
    path_bytes = rollout_path.as_posix().encode("utf-8")
    if (
        hashlib.sha256(path_bytes).hexdigest() != rollout["path_sha256"]
        or hashlib.sha256(file_bytes).hexdigest() != rollout["file_sha256"]
    ):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate rollout bytes differ"
        )
    records = tuple(_iter_source_snapshot_records(file_bytes))
    session_descriptor = cast(dict[str, object], rollout["session_meta"])
    task_descriptor = cast(dict[str, object], rollout["task_complete"])
    session_record = _certificate_record(records, session_descriptor, "session_meta")
    task_record = _certificate_record(records, task_descriptor, "task_complete")
    session = _native_session_meta(cast(dict[str, object], session_record["value"]))
    task = _native_task_complete(
        cast(dict[str, object], task_record["value"]),
        cast(str, certificate_context["turn_id"]),
    )
    if session is None or task is None:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate native record shape differs"
        )
    if (
        session["identity"] != certificate_context["agent_context_id"]
        or session["parent_id"] != certificate_context["parent_id"]
        or session["role"] != certificate_context["role"]
        or session["cwd"] != rollout["session_cwd"]
        or task["turn_id"] != certificate_context["turn_id"]
    ):
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate native joins differ"
        )
    if sum(
        _native_session_meta(cast(dict[str, object], record["value"])) is not None
        for record in records
    ) != 1:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous", "session_meta record is no longer unique"
        )
    selected_tasks = tuple(
        record
        for record in records
        if _native_task_complete(
            cast(dict[str, object], record["value"]),
            cast(str, certificate_context["turn_id"]),
        )
        is not None
    )
    if len(selected_tasks) != 1 or selected_tasks[0] != task_record:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous" if len(selected_tasks) > 1 else "source_identity_mismatch",
            "selected task_complete record is no longer unique",
        )
    task_raw = cast(bytes, task_record["raw"])
    return {
        "agent_id": certificate_context["agent_id"],
        "agent_context_id": certificate_context["agent_context_id"],
        "codex_thread_id": certificate_context["codex_thread_id"],
        "parent_id": certificate_context["parent_id"],
        "turn_id": certificate_context["turn_id"],
        "role": certificate_context["role"],
        "rollout_path": rollout["path"],
        "rollout_path_bytes_b64": base64.b64encode(path_bytes).decode("ascii"),
        "rollout_path_sha256": rollout["path_sha256"],
        "rollout_file_sha256": rollout["file_sha256"],
        "record_line": task_descriptor["line"],
        "record_byte_offset": task_descriptor["byte_offset"],
        "record_byte_length": task_descriptor["byte_length"],
        "record_bytes_b64": base64.b64encode(task_raw).decode("ascii"),
        "record_sha256": task_descriptor["record_sha256"],
        "stable_record_id": task_descriptor["record_sha256"],
    }


def _load_context_discovery_certificate(
    context: ArchiveContext, active_run: Path
) -> dict[str, object]:
    """Load exactly one active-run certificate and return its certified source event."""
    try:
        candidates = tuple(
            sorted(
                (
                    path
                    for path in active_run.iterdir()
                    if CONTEXT_DISCOVERY_CERTIFICATE_NAME.fullmatch(path.name)
                ),
                key=lambda path: path.name.encode("utf-8"),
            )
        )
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "source_unavailable", "active run certificate directory cannot be read"
        ) from exc
    if not candidates:
        raise RuntimeEventMaterializationError(
            "context_source_absent", "context discovery certificate is absent"
        )
    if len(candidates) != 1:
        raise RuntimeEventMaterializationError(
            "context_source_ambiguous", "context discovery certificate is not unique"
        )
    certificate_path = candidates[0]
    if certificate_path.is_symlink() or not certificate_path.is_file():
        raise RuntimeEventMaterializationError(
            "context_schema_invalid", "context discovery certificate is not a regular file"
        )
    try:
        raw = certificate_path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "source_unavailable", "context discovery certificate cannot be read"
        ) from exc
    validate_context_discovery_certificate(raw)
    value = cast(
        dict[str, object],
        json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=_context_certificate_pairs),
    )
    certificate_id = cast(str, value["certificate_id"])
    filename_id = cast(re.Match[str], CONTEXT_DISCOVERY_CERTIFICATE_NAME.fullmatch(certificate_path.name)).group("certificate_id")
    if certificate_id != filename_id:
        raise RuntimeEventMaterializationError(
            "source_identity_mismatch", "certificate filename id differs"
        )
    return _verify_context_discovery_certificate(context, value)


def command_append_context_discovery(
    context: ArchiveContext, args: argparse.Namespace
) -> int:
    """Produce and publish one native ContextDiscoveryV1 certificate."""
    active_run = _active_run_directory(context, args.run_id)
    value, source = _build_context_discovery_certificate(
        context, args.run_id, args.agent_context_id, args.turn_id
    )
    certificate_id = cast(str, value["certificate_id"])
    target = active_run / f"context_discovery.{certificate_id}.json"
    _publish_context_discovery_noreplace(target, _context_certificate_bytes(value))
    print(f"CONTEXT_DISCOVERY_PATH={target.relative_to(context.source_root).as_posix()}")
    print(f"CONTEXT_DISCOVERY_CERTIFICATE_ID={certificate_id}")
    print(f"CONTEXT_DISCOVERY_RECORD_SHA256={source['record_sha256']}")
    print("CONTEXT_DISCOVERY_APPEND=pass")
    return 0


def _publish_runtime_event_noreplace(target: Path, bytes_: bytes) -> dict[str, object]:
    """Publish prepared artifact bytes and return only observed target evidence."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeEventMaterializationError(
                "record_collision", "publication target is not a regular file"
            )
        if target.is_file():
            try:
                existing = target.read_bytes()
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_uncertain", "publication target readback failed"
                ) from exc
            if existing != bytes_:
                try:
                    candidate = json.loads(existing[:-1].decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, IndexError):
                    candidate = None
                if (
                    isinstance(candidate, dict)
                    and candidate.get("schema") == RUNTIME_EVENT_SCHEMA
                ):
                    try:
                        validate_runtime_event_schema(existing)
                    except RuntimeEventMaterializationError as exc:
                        raise RuntimeEventMaterializationError(
                            "schema_invalid", "existing artifact schema is invalid"
                        ) from exc
                raise RuntimeEventMaterializationError(
                    "record_collision", "publication target has different bytes"
                )
            validate_runtime_event_schema(existing)
            recovered_record = RuntimeEventRecord(
                cast(
                    dict[str, object],
                    json.loads(existing[:-1].decode("utf-8")),
                )
            )
            return {
                "source": "recovery",
                "causal_gap": True,
                "target_presence": "present",
                "rename_status": "recovered_present",
                "target_directory_fsync_status": "unknown",
                "readback_status": "verified",
                "readback_sha256": cast(
                    str, recovered_record["artifact_sha256"]
                ),
            }
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_failure", "artifact target preparation failed"
        ) from exc

    fd = -1
    temporary: Path | None = None
    identity: tuple[int, int] | None = None
    published = False
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        os.fchmod(fd, 0o600)
        flags = getattr(os, "O_NOFOLLOW", 0)
        if not flags:
            raise RuntimeEventMaterializationError(
                "publication_failure", "O_NOFOLLOW is unavailable"
            )
        os.close(fd)
        fd = os.open(temporary, os.O_RDWR | flags)
        metadata = os.fstat(fd)
        identity = (metadata.st_dev, metadata.st_ino)
        if (
            not S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or not _owner_mutation_exclusive_mode(metadata.st_mode, 0o600)
        ):
            raise RuntimeEventMaterializationError("publication_failure", "identity-owned temp metadata is invalid")
        view = memoryview(bytes_)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise RuntimeEventMaterializationError("publication_failure", "runtime event write made no progress")
            view = view[written:]
        os.fsync(fd)
        if os.pread(fd, len(bytes_) + 1, 0) != bytes_:
            raise RuntimeEventMaterializationError("publication_failure", "temporary readback differs from canonical bytes")
        os.close(fd)
        fd = -1
        latest = temporary.lstat()
        if (
            not S_ISREG(latest.st_mode)
            or latest.st_uid != os.geteuid()
            or identity != (latest.st_dev, latest.st_ino)
            or latest.st_nlink != 1
            or not _owner_mutation_exclusive_mode(latest.st_mode, 0o600)
        ):
            raise RuntimeEventMaterializationError("publication_failure", "identity-owned temp verification failed")
        try:
            _renameat2_noreplace(temporary, target)
        except FileExistsError:
            if target.is_symlink() or not target.is_file():
                raise RuntimeEventMaterializationError("record_collision", "publication target collision")
            try:
                existing = target.read_bytes()
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_uncertain", "publication target readback failed"
                ) from exc
            if existing != bytes_:
                try:
                    candidate = json.loads(existing[:-1].decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, IndexError):
                    candidate = None
                if (
                    isinstance(candidate, dict)
                    and candidate.get("schema") == RUNTIME_EVENT_SCHEMA
                ):
                    try:
                        validate_runtime_event_schema(existing)
                    except RuntimeEventMaterializationError as exc:
                        raise RuntimeEventMaterializationError(
                            "schema_invalid", "existing artifact schema is invalid"
                        ) from exc
                raise RuntimeEventMaterializationError("record_collision", "publication target collision")
            validate_runtime_event_schema(existing)
            recovered_record = RuntimeEventRecord(
                cast(
                    dict[str, object],
                    json.loads(existing[:-1].decode("utf-8")),
                )
            )
            return {
                "source": "recovery",
                "causal_gap": True,
                "target_presence": "present",
                "rename_status": "recovered_present",
                "target_directory_fsync_status": "unknown",
                "readback_status": "verified",
                "readback_sha256": cast(
                    str, recovered_record["artifact_sha256"]
                ),
            }
        published = True
        temporary = None
        try:
            _fsync_directory(target.parent, "artifact-parent")
            fsync_status = "succeeded"
        except OSError:
            fsync_status = "failed"
        try:
            committed = target.read_bytes()
        except OSError:
            readback_status = "failed"
            readback_sha256 = None
        else:
            if committed != bytes_:
                raise RuntimeEventMaterializationError(
                    "publication_observation_invalid",
                    "artifact target readback differs after publication",
                )
            try:
                validate_runtime_event_schema(committed)
                committed_value = json.loads(committed[:-1].decode("utf-8"))
            except RuntimeEventMaterializationError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_observation_invalid",
                    "artifact target readback is malformed after publication",
                ) from exc
            readback_status = "verified"
            readback_sha256 = cast(str, committed_value["artifact_sha256"])
        return {
            "source": "publish",
            "causal_gap": False,
            "target_presence": "present",
            "rename_status": "completed",
            "target_directory_fsync_status": fsync_status,
            "readback_status": readback_status,
            "readback_sha256": readback_sha256,
        }
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError("publication_failure", str(exc)) from exc
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_failure", "artifact temporary close failed"
                ) from exc
        if temporary is not None:
            try:
                current = temporary.stat()
                if not published and identity == (current.st_dev, current.st_ino):
                    temporary.unlink()
            except OSError:
                pass


def classify_publication_outcome(
    *,
    attempt_id: str,
    artifact_path: str,
    artifact_sha256: str,
    materialization_id: str,
    sequence: int,
    prior_observation_sha256: str | None,
    evidence: dict[str, object],
) -> dict[str, object]:
    """Classify post-target evidence and emit one immutable observation."""
    readback_status = evidence.get("readback_status")
    readback_sha256 = evidence.get("readback_sha256")
    if readback_status == "mismatch" or (
        readback_status == "verified" and readback_sha256 != artifact_sha256
    ):
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid",
            "artifact readback proves an invalid publication observation",
        )
    committed = (
        evidence.get("causal_gap") is False
        and evidence.get("target_directory_fsync_status") == "succeeded"
        and readback_status == "verified"
        and readback_sha256 == artifact_sha256
    )
    value: dict[str, object] = {
        "schema": RUNTIME_EVENT_OBSERVATION_SCHEMA,
        "attempt_id": attempt_id,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "materialization_id": materialization_id,
        "sequence": sequence,
        "prior_observation_sha256": prior_observation_sha256,
        "outcome": "committed" if committed else "uncertain",
        "evidence": {
            "source": evidence.get("source"),
            "causal_gap": evidence.get("causal_gap"),
            "target_presence": evidence.get("target_presence"),
            "rename_status": evidence.get("rename_status"),
            "target_directory_fsync_status": evidence.get(
                "target_directory_fsync_status"
            ),
            "readback_status": evidence.get("readback_status"),
            "readback_sha256": evidence.get("readback_sha256"),
        },
        "observation_sha256": "0" * 64,
    }
    zeroed = (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    value["observation_sha256"] = hashlib.sha256(zeroed).hexdigest()
    raw = (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return validate_publication_outcome_observation(raw)


def validate_publication_outcome_observation(raw: bytes) -> dict[str, object]:
    """Validate exact observation schema, evidence classification, and hash."""
    if not raw.endswith(b"\n") or b"\n" in raw[:-1] or not raw[:-1]:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation is not one JSON line"
        )

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        if len({key for key, _value in items}) != len(items):
            raise RuntimeEventMaterializationError(
                "publication_observation_invalid", "observation has duplicate keys"
            )
        return dict(items)

    try:
        value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=pairs)
    except RuntimeEventMaterializationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation JSON is invalid"
        ) from exc
    top = [
        "schema",
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
        "prior_observation_sha256",
        "outcome",
        "evidence",
        "observation_sha256",
    ]
    if not isinstance(value, dict) or list(value) != top:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation keys are not canonical"
        )
    observation = cast(dict[str, object], value)
    evidence = observation.get("evidence")
    evidence_keys = [
        "source",
        "causal_gap",
        "target_presence",
        "rename_status",
        "target_directory_fsync_status",
        "readback_status",
        "readback_sha256",
    ]
    if not isinstance(evidence, dict) or list(evidence) != evidence_keys:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation evidence is not canonical"
        )
    evidence = cast(dict[str, object], evidence)
    sequence = observation.get("sequence")
    prior = observation.get("prior_observation_sha256")
    readback_status = evidence.get("readback_status")
    readback_sha256 = evidence.get("readback_sha256")
    if (
        observation.get("schema") != RUNTIME_EVENT_OBSERVATION_SCHEMA
        or not isinstance(observation.get("attempt_id"), str)
        or not RUNTIME_EVENT_HEX64.fullmatch(cast(str, observation["attempt_id"]))
        or not isinstance(observation.get("artifact_path"), str)
        or Path(cast(str, observation["artifact_path"])).is_absolute()
        or _path_has_traversal(cast(str, observation["artifact_path"]))
        or not isinstance(observation.get("artifact_sha256"), str)
        or not RUNTIME_EVENT_HEX64.fullmatch(cast(str, observation["artifact_sha256"]))
        or not isinstance(observation.get("materialization_id"), str)
        or not RUNTIME_EVENT_HEX64.fullmatch(cast(str, observation["materialization_id"]))
        or type(sequence) is not int
        or sequence not in (1, 2)
        or (sequence == 1 and prior is not None)
        or (
            sequence == 2
            and (
                not isinstance(prior, str)
                or RUNTIME_EVENT_HEX64.fullmatch(prior) is None
            )
        )
        or observation.get("outcome") not in RUNTIME_EVENT_PUBLICATION_OUTCOMES
        or not isinstance(observation.get("observation_sha256"), str)
        or not RUNTIME_EVENT_HEX64.fullmatch(
            cast(str, observation["observation_sha256"])
        )
        or evidence.get("source") not in ("publish", "recovery")
        or type(evidence.get("causal_gap")) is not bool
        or evidence.get("target_presence") != "present"
        or evidence.get("rename_status") not in ("completed", "recovered_present")
        or evidence.get("target_directory_fsync_status")
        not in ("succeeded", "failed", "unknown")
        or readback_status not in ("verified", "failed", "mismatch")
        or readback_status == "mismatch"
        or (
            readback_status == "failed"
            and readback_sha256 is not None
        )
        or (
            readback_status != "failed"
            and (
                not isinstance(readback_sha256, str)
                or RUNTIME_EVENT_HEX64.fullmatch(readback_sha256) is None
            )
        )
        or (
            readback_status == "verified"
            and readback_sha256 != observation.get("artifact_sha256")
        )
        or (
            evidence.get("source") == "publish"
            and (
                evidence.get("rename_status") != "completed"
                or evidence.get("causal_gap") is not False
            )
        )
        or (
            evidence.get("source") == "recovery"
            and evidence.get("rename_status") != "recovered_present"
        )
        or (
            evidence.get("causal_gap") is True
            and (sequence != 1 or evidence.get("source") != "recovery")
        )
    ):
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation values are invalid"
        )
    committed = (
        evidence["causal_gap"] is False
        and evidence["target_directory_fsync_status"] == "succeeded"
        and evidence["readback_status"] == "verified"
        and evidence["readback_sha256"] == observation["artifact_sha256"]
    )
    if observation["outcome"] != ("committed" if committed else "uncertain"):
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation outcome is forged"
        )
    zeroed = dict(observation)
    zeroed["observation_sha256"] = "0" * 64
    preimage = (
        json.dumps(
            zeroed,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if observation["observation_sha256"] != hashlib.sha256(preimage).hexdigest():
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation hash is invalid"
        )
    canonical = (
        json.dumps(
            observation,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if canonical != raw:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation bytes are not canonical"
        )
    return observation


def confirm_publication_outcome_observation(
    attempt_lock: PublicationAttemptLock,
    path: Path,
    expected_bytes: bytes | None = None,
) -> dict[str, object]:
    """Confirm one observation file, parent fsync, and exact readback."""
    validate_publication_attempt_lock(attempt_lock)
    if path.parent != attempt_lock.attempt_directory:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation path escapes attempt"
        )
    match = RUNTIME_EVENT_OBSERVATION_NAME.fullmatch(path.name)
    try:
        metadata = path.lstat()
        if path.is_symlink() or not S_ISREG(metadata.st_mode):
            raise RuntimeEventMaterializationError(
                "publication_observation_invalid", "observation is not a regular file"
            )
        first = path.read_bytes()
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_observation_uncertain", "observation readback failed"
        ) from exc
    value = validate_publication_outcome_observation(first)
    if (
        match is None
        or int(match.group("sequence")) != value["sequence"]
        or match.group("sha256") != value["observation_sha256"]
        or value["attempt_id"] != attempt_lock.attempt_id
    ):
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation path identity mismatch"
        )
    if expected_bytes is not None and first != expected_bytes:
        raise RuntimeEventMaterializationError(
            "publication_observation_collision", "observation bytes differ"
        )
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        os.fsync(descriptor)
        _fsync_directory(path.parent, "observation-parent")
        second = path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_observation_uncertain", "observation confirmation failed"
        ) from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_observation_uncertain",
                    "observation descriptor close failed",
                ) from exc
    if first != second:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation readback changed"
        )
    return value


def spool_publication_outcome(
    attempt_lock: PublicationAttemptLock, observation: dict[str, object]
) -> tuple[Path, dict[str, object]]:
    """Atomically append and confirm one publication outcome observation."""
    raw = (
        json.dumps(
            observation,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    validated = validate_publication_outcome_observation(raw)
    if validated["attempt_id"] != attempt_lock.attempt_id:
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation attempt mismatch"
        )
    path = attempt_lock.attempt_directory / (
        f"{cast(int, validated['sequence']):06d}-"
        f"{validated['observation_sha256']}.json"
    )
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise RuntimeEventMaterializationError(
                "publication_observation_invalid", "observation target is invalid"
            )
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RuntimeEventMaterializationError(
                "publication_observation_uncertain",
                "observation target readback failed",
            ) from exc
        if existing != raw:
            raise RuntimeEventMaterializationError(
                "publication_observation_collision", "observation target differs"
            )
        return path, confirm_publication_outcome_observation(
            attempt_lock, path, raw
        )
    fd = -1
    temporary: Path | None = None
    identity: tuple[int, int] | None = None
    candidate_exists = False
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(fd, 0o600)
        metadata = os.fstat(fd)
        identity = (metadata.st_dev, metadata.st_ino)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "observation write made no progress")
            view = view[written:]
        os.fsync(fd)
        if os.pread(fd, len(raw) + 1, 0) != raw:
            raise OSError(errno.EIO, "observation temporary readback mismatch")
        os.close(fd)
        fd = -1
        _renameat2_noreplace(temporary, path)
        candidate_exists = True
        temporary = None
    except FileExistsError:
        if path.is_symlink() or not path.is_file():
            raise RuntimeEventMaterializationError(
                "publication_observation_collision", "observation target collision"
            )
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RuntimeEventMaterializationError(
                "publication_observation_uncertain",
                "observation target readback failed",
            ) from exc
        if existing != raw:
            raise RuntimeEventMaterializationError(
                "publication_observation_collision", "observation target collision"
            )
        candidate_exists = True
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_observation_failed", "observation publication failed"
        ) from exc
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_observation_failed",
                    "observation temporary close failed",
                ) from exc
        if temporary is not None:
            try:
                current = temporary.stat()
                if not candidate_exists and identity == (current.st_dev, current.st_ino):
                    temporary.unlink()
            except OSError:
                pass
    try:
        _fsync_directory(path.parent, "observation-parent")
        if path.read_bytes() != raw:
            raise RuntimeEventMaterializationError(
                "publication_observation_invalid", "observation readback differs"
            )
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_observation_uncertain", "observation durability is uncertain"
        ) from exc
    return path, confirm_publication_outcome_observation(attempt_lock, path, raw)


def _canonical_publication_outcome_receipt_bytes(
    receipt: dict[str, object],
) -> bytes:
    """Render exact receipt bytes while deriving the receipt self-hash."""
    value = dict(receipt)
    value["receipt_sha256"] = "0" * 64
    preimage = (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    receipt["receipt_sha256"] = hashlib.sha256(preimage).hexdigest()
    return (
        json.dumps(
            receipt,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def validate_publication_outcome_receipt(raw: bytes) -> dict[str, object]:
    """Validate exact receipt bytes, nested observation, repetitions, and hash."""
    if not raw.endswith(b"\n") or b"\n" in raw[:-1] or not raw[:-1]:
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt is not one JSON line"
        )

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        if len({key for key, _value in items}) != len(items):
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt has duplicate keys"
            )
        return dict(items)

    try:
        value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=pairs)
    except RuntimeEventMaterializationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt JSON is invalid"
        ) from exc
    keys = [
        "schema",
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
        "prior_receipt_sha256",
        "observation",
        "receipt_sha256",
    ]
    if not isinstance(value, dict) or list(value) != keys:
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt keys are not canonical"
        )
    receipt = cast(dict[str, object], value)
    observation = receipt.get("observation")
    if not isinstance(observation, dict):
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt observation is absent"
        )
    observation_raw = (
        json.dumps(
            observation,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        validated_observation = validate_publication_outcome_observation(
            observation_raw
        )
    except RuntimeEventMaterializationError as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt observation is invalid"
        ) from exc
    sequence = receipt.get("sequence")
    prior = receipt.get("prior_receipt_sha256")
    if (
        receipt.get("schema") != RUNTIME_EVENT_RECEIPT_SCHEMA
        or not isinstance(receipt.get("attempt_id"), str)
        or RUNTIME_EVENT_HEX64.fullmatch(cast(str, receipt["attempt_id"])) is None
        or not isinstance(receipt.get("artifact_path"), str)
        or Path(cast(str, receipt["artifact_path"])).is_absolute()
        or _path_has_traversal(cast(str, receipt["artifact_path"]))
        or not isinstance(receipt.get("artifact_sha256"), str)
        or RUNTIME_EVENT_HEX64.fullmatch(cast(str, receipt["artifact_sha256"])) is None
        or not isinstance(receipt.get("materialization_id"), str)
        or RUNTIME_EVENT_HEX64.fullmatch(cast(str, receipt["materialization_id"])) is None
        or type(sequence) is not int
        or sequence not in (1, 2)
        or (sequence == 1 and prior is not None)
        or (
            sequence == 2
            and (
                not isinstance(prior, str)
                or RUNTIME_EVENT_HEX64.fullmatch(prior) is None
            )
        )
        or not isinstance(receipt.get("receipt_sha256"), str)
        or RUNTIME_EVENT_HEX64.fullmatch(cast(str, receipt["receipt_sha256"])) is None
    ):
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt values are invalid"
        )
    for field in (
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
    ):
        if receipt[field] != validated_observation[field]:
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt observation identity mismatch"
            )
    zeroed = dict(receipt)
    zeroed["receipt_sha256"] = "0" * 64
    preimage = (
        json.dumps(
            zeroed,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if receipt["receipt_sha256"] != hashlib.sha256(preimage).hexdigest():
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt hash is invalid"
        )
    canonical = (
        json.dumps(
            receipt,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if canonical != raw:
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt bytes are not canonical"
        )
    return receipt


def validate_publication_receipt_chain(
    record: RuntimeEventRecord,
    observations: list[dict[str, object]],
    receipts: list[dict[str, object]],
) -> dict[str, object] | None:
    """Validate the sole monotone observation/receipt chain for one attempt."""
    intent = cast(dict[str, object], record["publication_intent"])
    expected = {
        "attempt_id": intent["attempt_id"],
        "artifact_path": intent["target_path"],
        "artifact_sha256": record["artifact_sha256"],
        "materialization_id": record["materialization_id"],
    }
    ordered_observations = sorted(
        observations, key=lambda item: cast(int, item["sequence"])
    )
    ordered_receipts = sorted(receipts, key=lambda item: cast(int, item["sequence"]))
    if len(ordered_observations) > 2 or len(ordered_receipts) > 2:
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "publication chain exceeds two sequences"
        )
    for index, observation in enumerate(ordered_observations, start=1):
        if observation["sequence"] != index or any(
            observation[field] != value for field, value in expected.items()
        ):
            raise RuntimeEventMaterializationError(
                "publication_observation_invalid", "observation chain identity mismatch"
            )
        expected_prior = (
            None
            if index == 1
            else ordered_observations[index - 2]["observation_sha256"]
        )
        if observation["prior_observation_sha256"] != expected_prior:
            raise RuntimeEventMaterializationError(
                "publication_observation_invalid", "observation prior link is invalid"
            )
    if len(ordered_observations) == 2 and (
        ordered_observations[0]["outcome"] != "uncertain"
        or ordered_observations[1]["outcome"] != "committed"
    ):
        raise RuntimeEventMaterializationError(
            "publication_observation_invalid", "observation transition is not monotone"
        )
    observation_by_sequence = {
        cast(int, item["sequence"]): item for item in ordered_observations
    }
    for index, receipt in enumerate(ordered_receipts, start=1):
        if receipt["sequence"] != index or any(
            receipt[field] != value for field, value in expected.items()
        ):
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt chain identity mismatch"
            )
        observation = observation_by_sequence.get(index)
        if observation is None or receipt["observation"] != observation:
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt lacks matching observation"
            )
        expected_prior = (
            None if index == 1 else ordered_receipts[index - 2]["receipt_sha256"]
        )
        if receipt["prior_receipt_sha256"] != expected_prior:
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt prior link is invalid"
            )
    if len(ordered_receipts) == 2 and (
        cast(dict[str, object], ordered_receipts[0]["observation"])["outcome"]
        != "uncertain"
        or cast(dict[str, object], ordered_receipts[1]["observation"])["outcome"]
        != "committed"
    ):
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt transition is not monotone"
        )
    return ordered_receipts[-1] if ordered_receipts else None


def _readback_publication_outcome_receipt(
    path: Path,
) -> tuple[dict[str, object], bytes]:
    """Read and validate one candidate receipt without accepting durability."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_uncertain", "receipt readback failed"
        ) from exc
    return validate_publication_outcome_receipt(raw), raw


def confirm_publication_outcome_receipt(
    attempt_lock: PublicationAttemptLock,
    path: Path,
    expected_bytes: bytes,
    record: RuntimeEventRecord,
    observations: list[dict[str, object]],
    prior_receipts: list[dict[str, object]],
) -> DurablePublicationOutcomeReceipt:
    """Confirm candidate receipt file and parent durability before acceptance."""
    validate_publication_attempt_lock(attempt_lock)
    try:
        metadata = path.lstat()
        if path.is_symlink() or not S_ISREG(metadata.st_mode):
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt is not a regular file"
            )
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_uncertain", "receipt metadata readback failed"
        ) from exc
    receipt, first = _readback_publication_outcome_receipt(path)
    if first != expected_bytes:
        raise RuntimeEventMaterializationError(
            "publication_receipt_collision", "receipt candidate bytes differ"
        )
    intent = cast(dict[str, object], record["publication_intent"])
    artifact_match = RUNTIME_EVENT_TARGET_NAME.fullmatch(cast(str, intent["target_path"]))
    name_match = RUNTIME_EVENT_RECEIPT_NAME.fullmatch(path.name)
    if (
        artifact_match is None
        or name_match is None
        or name_match.group("unit") != artifact_match.group("unit")
        or name_match.group("attempt") != attempt_lock.attempt_id
        or int(name_match.group("sequence")) != receipt["sequence"]
        or path.parent.name != artifact_match.group("run")
    ):
        raise RuntimeEventMaterializationError(
            "publication_receipt_invalid", "receipt path identity mismatch"
        )
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        os.fsync(descriptor)
        _fsync_directory(path.parent, "receipt-confirm-parent")
        second = path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_uncertain", "receipt confirmation failed"
        ) from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_receipt_uncertain",
                    "receipt descriptor close failed",
                ) from exc
    if first != second:
        raise RuntimeEventMaterializationError(
            "publication_receipt_uncertain", "receipt changed during confirmation"
        )
    validate_publication_receipt_chain(
        record, observations, [*prior_receipts, receipt]
    )
    return DurablePublicationOutcomeReceipt(path=path, value=receipt, bytes_=first)


def _publish_publication_outcome_receipt_noreplace(
    attempt_lock: PublicationAttemptLock,
    artifact_target: Path,
    receipt: dict[str, object],
    record: RuntimeEventRecord,
    observations: list[dict[str, object]],
    prior_receipts: list[dict[str, object]],
) -> DurablePublicationOutcomeReceipt:
    """Publish and confirm one immutable outcome receipt without replacement."""
    raw = _canonical_publication_outcome_receipt_bytes(receipt)
    validated = validate_publication_outcome_receipt(raw)
    path = artifact_target.with_name(
        f"{artifact_target.stem}.outcome.{validated['attempt_id']}."
        f"{cast(int, validated['sequence']):06d}.json"
    )
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt target is invalid"
            )
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RuntimeEventMaterializationError(
                "publication_receipt_uncertain", "receipt target readback failed"
            ) from exc
        if existing != raw:
            raise RuntimeEventMaterializationError(
                "publication_receipt_collision", "receipt target differs"
            )
        return confirm_publication_outcome_receipt(
            attempt_lock,
            path,
            raw,
            record,
            observations,
            prior_receipts,
        )
    fd = -1
    temporary: Path | None = None
    identity: tuple[int, int] | None = None
    candidate_exists = False
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(fd, 0o600)
        metadata = os.fstat(fd)
        identity = (metadata.st_dev, metadata.st_ino)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "receipt write made no progress")
            view = view[written:]
        os.fsync(fd)
        if os.pread(fd, len(raw) + 1, 0) != raw:
            raise OSError(errno.EIO, "receipt temporary readback mismatch")
        os.close(fd)
        fd = -1
        _renameat2_noreplace(temporary, path)
        candidate_exists = True
        temporary = None
    except FileExistsError:
        if path.is_symlink() or not path.is_file():
            raise RuntimeEventMaterializationError(
                "publication_receipt_collision", "receipt target collision"
            )
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RuntimeEventMaterializationError(
                "publication_receipt_uncertain", "receipt target readback failed"
            ) from exc
        if existing != raw:
            raise RuntimeEventMaterializationError(
                "publication_receipt_collision", "receipt target collision"
            )
        candidate_exists = True
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_failed", "receipt publication failed"
        ) from exc
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "publication_receipt_failed", "receipt temporary close failed"
                ) from exc
        if temporary is not None:
            try:
                current = temporary.stat()
                if not candidate_exists and identity == (current.st_dev, current.st_ino):
                    temporary.unlink()
            except OSError:
                pass
    try:
        _fsync_directory(path.parent, "receipt-parent")
        if path.read_bytes() != raw:
            raise RuntimeEventMaterializationError(
                "publication_receipt_collision", "receipt readback differs"
            )
    except RuntimeEventMaterializationError:
        raise
    except OSError as exc:
        raise RuntimeEventMaterializationError(
            "publication_receipt_uncertain", "receipt durability is uncertain"
        ) from exc
    return confirm_publication_outcome_receipt(
        attempt_lock,
        path,
        raw,
        record,
        observations,
        prior_receipts,
    )


def reconcile_runtime_event_publication(
    source_root: Path,
    target: Path,
    record: RuntimeEventRecord,
    artifact_bytes: bytes,
) -> DurablePublicationOutcomeReceipt:
    """Reconcile one prepared artifact and its append-only outcome chain."""
    validate_runtime_event_schema(artifact_bytes)
    intent = cast(dict[str, object], record["publication_intent"])
    attempt_id = cast(str, intent["attempt_id"])
    artifact_path = cast(str, intent["target_path"])
    artifact_sha256 = cast(str, record["artifact_sha256"])
    materialization_id = cast(str, record["materialization_id"])
    if (
        target != source_root / artifact_path
        or cast(
            str,
            json.loads(artifact_bytes[:-1].decode("utf-8"))["artifact_sha256"],
        )
        != artifact_sha256
    ):
        raise RuntimeEventMaterializationError(
            "schema_invalid", "prepared artifact target or hash mismatch"
        )

    with acquire_publication_attempt_lock(source_root, attempt_id) as attempt_lock:
        observations: list[dict[str, object]] = []
        observation_paths: dict[int, Path] = {}
        for path in sorted(
            attempt_lock.attempt_directory.iterdir(), key=lambda item: os.fsencode(item.name)
        ):
            if path == attempt_lock.lock_path:
                continue
            match = RUNTIME_EVENT_OBSERVATION_NAME.fullmatch(path.name)
            if match is None or path.is_dir():
                raise RuntimeEventMaterializationError(
                    "publication_attempt_collision",
                    "unexpected attempt-local semantic file",
                )
            sequence = int(match.group("sequence"))
            if sequence not in (1, 2):
                raise RuntimeEventMaterializationError(
                    "publication_observation_invalid", "observation sequence is invalid"
                )
            if sequence in observation_paths:
                raise RuntimeEventMaterializationError(
                    "publication_attempt_collision", "duplicate observation sequence"
                )
            observation = confirm_publication_outcome_observation(
                attempt_lock, path
            )
            if (
                observation["artifact_path"] != artifact_path
                or observation["artifact_sha256"] != artifact_sha256
                or observation["materialization_id"] != materialization_id
            ):
                raise RuntimeEventMaterializationError(
                    "publication_observation_invalid",
                    "observation artifact identity mismatch",
                )
            observation_paths[sequence] = path
            observations.append(observation)
        observations.sort(key=lambda item: cast(int, item["sequence"]))

        artifact_match = RUNTIME_EVENT_TARGET_NAME.fullmatch(artifact_path)
        if artifact_match is None:
            raise RuntimeEventMaterializationError(
                "schema_invalid", "artifact publication path is invalid"
            )
        receipt_prefix = f"{target.stem}.outcome."
        receipt_paths: dict[int, Path] = {}
        for path in sorted(target.parent.iterdir(), key=lambda item: os.fsencode(item.name)):
            if not path.name.startswith(receipt_prefix):
                continue
            match = RUNTIME_EVENT_RECEIPT_NAME.fullmatch(path.name)
            if match is None:
                raise RuntimeEventMaterializationError(
                    "publication_receipt_invalid", "receipt basename is invalid"
                )
            if match.group("attempt") != attempt_id:
                raise RuntimeEventMaterializationError(
                    "publication_attempt_collision", "receipt belongs to another attempt"
                )
            sequence = int(match.group("sequence"))
            if sequence not in (1, 2):
                raise RuntimeEventMaterializationError(
                    "publication_receipt_invalid", "receipt sequence is invalid"
                )
            if sequence in receipt_paths:
                raise RuntimeEventMaterializationError(
                    "publication_attempt_collision", "duplicate receipt sequence"
                )
            receipt_paths[sequence] = path

        if sorted(receipt_paths) != list(range(1, len(receipt_paths) + 1)):
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt chain skips a sequence"
            )
        if any(sequence not in observation_paths for sequence in receipt_paths):
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt exists without observation"
            )

        target_present = target.exists() or target.is_symlink()
        if not target_present and (observations or receipt_paths):
            code = (
                "publication_receipt_invalid"
                if receipt_paths
                else "publication_observation_invalid"
            )
            raise RuntimeEventMaterializationError(
                code, "publication records exist without artifact target"
            )
        if target_present:
            if target.is_symlink() or not target.is_file():
                raise RuntimeEventMaterializationError(
                    "record_collision", "artifact target is not a regular file"
                )
            try:
                existing = target.read_bytes()
            except OSError as exc:
                raise RuntimeEventMaterializationError(
                    "record_collision", "artifact target cannot be read"
                ) from exc
            if existing != artifact_bytes:
                try:
                    candidate = json.loads(existing[:-1].decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, IndexError):
                    candidate = None
                if isinstance(candidate, dict) and candidate.get("schema") == RUNTIME_EVENT_SCHEMA:
                    try:
                        validate_runtime_event_schema(existing)
                    except RuntimeEventMaterializationError as exc:
                        raise RuntimeEventMaterializationError(
                            "schema_invalid", "existing artifact schema is invalid"
                        ) from exc
                raise RuntimeEventMaterializationError(
                    "record_collision", "artifact target bytes differ"
                )
            existing_record = _readback_runtime_event(target)
            existing_intent = cast(
                dict[str, object], existing_record["publication_intent"]
            )
            if (
                existing_record["artifact_sha256"] != artifact_sha256
                or existing_record["materialization_id"] != materialization_id
                or existing_intent != intent
            ):
                raise RuntimeEventMaterializationError(
                    "schema_invalid", "existing artifact identity is malformed"
                )

        validate_publication_receipt_chain(record, observations, [])
        receipts: list[dict[str, object]] = []
        durable_by_sequence: dict[int, DurablePublicationOutcomeReceipt] = {}
        for observation in observations:
            sequence = cast(int, observation["sequence"])
            path = receipt_paths.get(sequence)
            if path is None:
                continue
            receipt_value: dict[str, object] = {
                "schema": RUNTIME_EVENT_RECEIPT_SCHEMA,
                "attempt_id": attempt_id,
                "artifact_path": artifact_path,
                "artifact_sha256": artifact_sha256,
                "materialization_id": materialization_id,
                "sequence": sequence,
                "prior_receipt_sha256": (
                    None if sequence == 1 else receipts[-1]["receipt_sha256"]
                ),
                "observation": observation,
                "receipt_sha256": "0" * 64,
            }
            expected_bytes = _canonical_publication_outcome_receipt_bytes(receipt_value)
            try:
                existing_receipt, existing_bytes = _readback_publication_outcome_receipt(
                    path
                )
            except RuntimeEventMaterializationError as exc:
                if exc.code == "publication_receipt_uncertain":
                    raise
                raise RuntimeEventMaterializationError(
                    "publication_receipt_invalid", "existing receipt is invalid"
                ) from exc
            if existing_bytes != expected_bytes:
                if existing_receipt["receipt_sha256"] == receipt_value["receipt_sha256"]:
                    raise RuntimeEventMaterializationError(
                        "publication_receipt_invalid",
                        "existing receipt canonical bytes are inconsistent",
                    )
                raise RuntimeEventMaterializationError(
                    "publication_receipt_collision", "existing receipt differs"
                )
            durable = confirm_publication_outcome_receipt(
                attempt_lock,
                path,
                expected_bytes,
                record,
                observations,
                receipts,
            )
            receipts.append(durable.value)
            durable_by_sequence[sequence] = durable
        if receipts and [cast(int, item["sequence"]) for item in receipts] != list(
            range(1, len(receipts) + 1)
        ):
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "receipt chain skips a sequence"
            )
        validate_publication_receipt_chain(record, observations, receipts)

        def publish_receipt(
            observation: dict[str, object],
        ) -> DurablePublicationOutcomeReceipt:
            sequence = cast(int, observation["sequence"])
            receipt_value: dict[str, object] = {
                "schema": RUNTIME_EVENT_RECEIPT_SCHEMA,
                "attempt_id": attempt_id,
                "artifact_path": artifact_path,
                "artifact_sha256": artifact_sha256,
                "materialization_id": materialization_id,
                "sequence": sequence,
                "prior_receipt_sha256": (
                    None if sequence == 1 else receipts[-1]["receipt_sha256"]
                ),
                "observation": observation,
                "receipt_sha256": "0" * 64,
            }
            durable = _publish_publication_outcome_receipt_noreplace(
                attempt_lock,
                target,
                receipt_value,
                record,
                observations,
                receipts,
            )
            receipts.append(durable.value)
            durable_by_sequence[sequence] = durable
            validate_publication_receipt_chain(record, observations, receipts)
            return durable

        for observation in observations:
            sequence = cast(int, observation["sequence"])
            if sequence not in durable_by_sequence:
                publish_receipt(observation)
        latest = validate_publication_receipt_chain(record, observations, receipts)
        if latest is not None:
            latest_outcome = cast(dict[str, object], latest["observation"])["outcome"]
            if latest_outcome == "committed":
                return durable_by_sequence[cast(int, latest["sequence"])]

        direct_uncertain = False
        if not target_present:
            publication_evidence = _publish_runtime_event_noreplace(
                target, artifact_bytes
            )
            target_present = True
            sequence = 1
            observation = classify_publication_outcome(
                attempt_id=attempt_id,
                artifact_path=artifact_path,
                artifact_sha256=artifact_sha256,
                materialization_id=materialization_id,
                sequence=sequence,
                prior_observation_sha256=None,
                evidence=publication_evidence,
            )
            _path, confirmed = spool_publication_outcome(attempt_lock, observation)
            observations.append(confirmed)
            observations.sort(key=lambda item: cast(int, item["sequence"]))
            durable = publish_receipt(confirmed)
            if confirmed["outcome"] == "committed":
                return durable
            direct_uncertain = publication_evidence["source"] == "publish"

        if not observations:
            try:
                _fsync_directory(target.parent, "artifact-parent")
                fsync_status = "succeeded"
            except OSError:
                fsync_status = "failed"
            try:
                readback = target.read_bytes()
            except OSError:
                readback_status = "failed"
                readback_sha256: str | None = None
            else:
                if readback != artifact_bytes:
                    raise RuntimeEventMaterializationError(
                        "publication_observation_invalid",
                        "artifact recovery readback differs",
                    )
                readback_status = "verified"
                readback_sha256 = artifact_sha256
            orphan = classify_publication_outcome(
                attempt_id=attempt_id,
                artifact_path=artifact_path,
                artifact_sha256=artifact_sha256,
                materialization_id=materialization_id,
                sequence=1,
                prior_observation_sha256=None,
                evidence={
                    "source": "recovery",
                    "causal_gap": True,
                    "target_presence": "present",
                    "rename_status": "recovered_present",
                    "target_directory_fsync_status": fsync_status,
                    "readback_status": readback_status,
                    "readback_sha256": readback_sha256,
                },
            )
            _path, confirmed = spool_publication_outcome(attempt_lock, orphan)
            observations.append(confirmed)
            publish_receipt(confirmed)

        latest = validate_publication_receipt_chain(record, observations, receipts)
        if latest is None:
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "publication receipt is absent"
            )
        if cast(dict[str, object], latest["observation"])["outcome"] == "committed":
            return durable_by_sequence[cast(int, latest["sequence"])]
        if direct_uncertain:
            raise RuntimeEventMaterializationError(
                "publication_uncertain", "latest confirmed outcome is uncertain"
            )
        if len(observations) != 1 or len(receipts) != 1:
            raise RuntimeEventMaterializationError(
                "publication_receipt_invalid", "uncertain chain cannot advance"
            )
        try:
            _fsync_directory(target.parent, "artifact-parent")
            recovery_fsync = "succeeded"
        except OSError:
            recovery_fsync = "failed"
        try:
            recovery_bytes = target.read_bytes()
        except OSError:
            recovery_readback = "failed"
            recovery_sha256: str | None = None
        else:
            if recovery_bytes != artifact_bytes:
                raise RuntimeEventMaterializationError(
                    "publication_observation_invalid",
                    "artifact recovery readback differs",
                )
            recovery_readback = "verified"
            recovery_sha256 = artifact_sha256
        recovery_evidence: dict[str, object] = {
            "source": "recovery",
            "causal_gap": False,
            "target_presence": "present",
            "rename_status": "recovered_present",
            "target_directory_fsync_status": recovery_fsync,
            "readback_status": recovery_readback,
            "readback_sha256": recovery_sha256,
        }
        committed = (
            recovery_fsync == "succeeded"
            and recovery_readback == "verified"
            and recovery_sha256 == artifact_sha256
        )
        if not committed:
            raise RuntimeEventMaterializationError(
                "publication_uncertain", "recovery did not prove committed outcome"
            )
        second = classify_publication_outcome(
            attempt_id=attempt_id,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha256,
            materialization_id=materialization_id,
            sequence=2,
            prior_observation_sha256=cast(str, observations[0]["observation_sha256"]),
            evidence=recovery_evidence,
        )
        _path, confirmed_second = spool_publication_outcome(attempt_lock, second)
        observations.append(confirmed_second)
        durable = publish_receipt(confirmed_second)
        return durable


def command_materialize_runtime_event(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Materialize one fixed result-family event into the active run bundle."""
    spec = fixed_result_family_spec(args.result_family, args.gate_id)
    run_id = safe_run_id(args.run_id)
    active_run = _active_run_directory(context, run_id)
    source_event = _load_context_discovery_certificate(context, active_run)
    result_path = active_run / spec.artifact_name
    try:
        result_bytes = result_path.read_bytes()
    except OSError as exc:
        raise RuntimeEventMaterializationError("result_authority_mismatch", f"fixed result artifact is absent: {result_path}") from exc
    if spec.result_family in {"requirements", "design", "review"}:
        result = validate_markdown_review_result(result_bytes.decode("utf-8"), spec.gate_id)
    elif spec.result_family == "validation":
        result = parse_validation_result(result_bytes, spec.gate_id)
        validate_validation_result(result)
        observations = cast(dict[str, object], result["observations"])
        head = run(["git", "-C", str(context.source_root), "rev-parse", "--verify", "HEAD"], check=False).stdout.strip()
        base = run(["git", "-C", str(context.source_root), "rev-parse", "--verify", cast(str, result["base_ref"])], check=False).stdout.strip()
        if observations.get("head_oid") != head or observations.get("base_oid") != base:
            raise RuntimeEventMaterializationError("target_identity_mismatch", "validation observations do not match Git identities")
    else:
        result = parse_lifecycle_result(result_bytes.decode("utf-8"), spec.gate_id)
        validate_lifecycle_result(result)
        evidence_path = context.source_root / cast(str, result["evidence_path"])
        if hashlib.sha256(evidence_path.read_bytes()).hexdigest() != result["evidence_sha256"]:
            raise RuntimeEventMaterializationError("result_authority_mismatch", "lifecycle evidence hash does not match bytes")
    if result.get("base_ref") not in {None, args.base_ref}:
        raise RuntimeEventMaterializationError("target_identity_mismatch", "result base_ref differs from selected base ref")
    artifact_sha = hashlib.sha256(result_bytes).hexdigest()
    artifact_relative = result_path.relative_to(context.source_root).as_posix()
    artifact_blob = run(["git", "-C", str(context.source_root), "hash-object", "--", artifact_relative], check=False)
    if artifact_blob.returncode != 0 or not RUNTIME_EVENT_OID40.fullmatch(artifact_blob.stdout.strip()):
        raise RuntimeEventMaterializationError("result_authority_mismatch", "result artifact Git blob is unavailable")
    targets = verify_target_identities(context.source_root, result, args.base_ref)
    head = run(["git", "-C", str(context.source_root), "rev-parse", "--verify", "HEAD"], check=False)
    base = run(["git", "-C", str(context.source_root), "rev-parse", "--verify", args.base_ref], check=False)
    if head.returncode != 0 or base.returncode != 0 or not RUNTIME_EVENT_OID40.fullmatch(head.stdout.strip()) or not RUNTIME_EVENT_OID40.fullmatch(base.stdout.strip()):
        raise RuntimeEventMaterializationError("target_identity_mismatch", "source snapshot identities are unavailable")
    gate_result = derive_gate_result(result)
    record_sha = cast(str, source_event["record_sha256"])
    unit_id = args.unit_id or record_sha[:16]
    if not re.fullmatch(r"[0-9a-f]{16}", unit_id) or unit_id != record_sha[:16]:
        raise RuntimeEventMaterializationError("source_identity_mismatch", "unit id does not match source record hash")
    target = active_run / f"runtime_event.{unit_id}.json"
    source_event["decision"] = cast(str, result.get("decision", "NONE"))
    source_event["applicable_gate_result"] = gate_result
    value: dict[str, object] = {
        "schema": RUNTIME_EVENT_SCHEMA, "materialization_id": "0" * 64, "result_family": spec.result_family,
        "gate": {"id": spec.gate_id, "result": gate_result}, "source_event": {
            "agent_id": source_event["agent_id"], "agent_context_id": source_event["agent_context_id"],
            "codex_thread_id": source_event["codex_thread_id"], "parent_id": source_event["parent_id"],
            "turn_id": source_event["turn_id"], "role": source_event["role"], "decision": source_event["decision"],
            "applicable_gate_result": source_event["applicable_gate_result"], "rollout_path": source_event["rollout_path"],
            "rollout_path_bytes_b64": source_event["rollout_path_bytes_b64"], "rollout_path_sha256": source_event["rollout_path_sha256"],
            "rollout_file_sha256": source_event["rollout_file_sha256"], "record_line": source_event["record_line"],
            "record_byte_offset": source_event["record_byte_offset"], "record_byte_length": source_event["record_byte_length"],
            "record_bytes_b64": source_event["record_bytes_b64"], "record_sha256": source_event["record_sha256"],
            "stable_record_id": source_event["stable_record_id"],
        }, "result_artifact": {
            "path": artifact_relative, "schema": spec.schema, "artifact_sha256": artifact_sha,
            "artifact_blob_oid": artifact_blob.stdout.strip(), "gate_id": spec.gate_id, "gate_result": gate_result,
            "target_paths": [cast(dict[str, object], item)["path"] for item in targets], "base_ref": args.base_ref, "base_oid": base.stdout.strip(),
        }, "target_identities": list(targets), "source_snapshot": {
            "head_oid": head.stdout.strip(), "base_ref": args.base_ref, "base_oid": base.stdout.strip(),
            "porcelain_v1": [item["raw"] for item in capture_porcelain_v1(context.source_root)],
        }, "publication_intent": {
            "schema": RUNTIME_EVENT_PUBLICATION_INTENT_SCHEMA,
            "attempt_id": "0" * 64,
            "target_path": target.relative_to(context.source_root).as_posix(),
            "prepared_state": "prepared",
        }, "artifact_sha256": "0" * 64,
    }
    record = RuntimeEventRecord(value)
    value["materialization_id"] = hashlib.sha256(RUNTIME_EVENT_MATERIALIZATION_SCHEMA.encode("utf-8") + b"\0" + canonical_preimage_bytes(record)).hexdigest()
    publication_intent = cast(dict[str, object], value["publication_intent"])
    publication_intent["attempt_id"] = derive_publication_attempt_id(
        cast(str, value["materialization_id"]),
        cast(str, publication_intent["target_path"]),
    )
    event_bytes = _canonical_runtime_event_bytes(record)
    validate_runtime_event_schema(event_bytes)
    receipt = reconcile_runtime_event_publication(
        context.source_root.resolve(), target.resolve(), record, event_bytes
    )
    observation = cast(dict[str, object], receipt.value["observation"])
    if observation["outcome"] != "committed":
        raise RuntimeEventMaterializationError(
            "publication_uncertain", "latest confirmed outcome is uncertain"
        )
    print(f"RUNTIME_EVENT_PATH={target.relative_to(context.source_root).as_posix()}")
    print(f"RUNTIME_EVENT_UNIT_ID={unit_id}")
    print(f"RUNTIME_EVENT_RECORD_SHA256={record_sha}")
    print(f"RUNTIME_EVENT_MATERIALIZATION_ID={value['materialization_id']}")
    print(f"RUNTIME_EVENT_ATTEMPT_ID={publication_intent['attempt_id']}")
    print(
        "RUNTIME_EVENT_RECEIPT_PATH="
        f"{receipt.path.relative_to(context.source_root).as_posix()}"
    )
    print(f"RUNTIME_EVENT_RECEIPT_SHA256={receipt.value['receipt_sha256']}")
    print("RUNTIME_EVENT_OUTCOME=committed")
    print("RUNTIME_EVENT_MATERIALIZE=pass")
    return 0


def remote_branch_exists(context: ArchiveContext, branch: str) -> bool:
    """Return whether origin/<branch> exists locally after fetch."""
    result = git(context.archive_root, ["rev-parse", "--verify", f"origin/{branch}"], check=False)
    return result.returncode == 0


def local_branch_exists(context: ArchiveContext, branch: str) -> bool:
    """Return whether one local branch exists."""
    result = git(context.archive_root, ["rev-parse", "--verify", branch], check=False)
    return result.returncode == 0


def current_branch(context: ArchiveContext) -> str:
    """Return the current branch name for the archive clone."""
    result = git(context.archive_root, ["branch", "--show-current"])
    return result.stdout.strip()


def porcelain_status(context: ArchiveContext) -> str:
    """Return porcelain status output for the archive clone."""
    return git(
        context.archive_root,
        ["status", "--porcelain", "--untracked-files=all"],
        check=False,
    ).stdout


def porcelain_paths(context: ArchiveContext) -> tuple[str, ...]:
    """Return dirty archive-relative paths from porcelain status."""
    paths = []
    for line in porcelain_status(context).splitlines():
        path = porcelain_path(line)
        if path:
            paths.append(path)
    return tuple(paths)


def porcelain_path(line: str) -> str:
    """Extract a path from one non-z porcelain status line."""
    if len(line) < GIT_PORCELAIN_STATUS_MIN_LINE_LENGTH:
        return ""
    path = line[GIT_PORCELAIN_STATUS_PATH_START:]
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[-1]
    return path.strip()


def managed_runtime_archive_path(path: str) -> bool:
    """Return whether a dirty archive path is a managed runtime artifact."""
    parts = Path(path).parts
    if not parts:
        return False
    if parts[0] in REPO_KEYED_ARCHIVE_FAMILIES and len(parts) >= 2:
        return True
    return parts[0] in MANAGED_GLOBAL_ARCHIVE_FAMILIES


def dirty_key_for_path(path: str) -> tuple[str, bool]:
    """Return (repo_key, global_dirty) for one archive-relative dirty path."""
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] in REPO_KEYED_ARCHIVE_FAMILIES:
        if parts[1] != "legacy-import":
            return parts[1], False
    if parts and parts[0] in {
        ".gitattributes",
        "README.md",
        "eval-results",
        "legacy-import",
        "reports",
        "tools",
    }:
        return "", True
    return "", False


def archive_tree_keys(context: ArchiveContext) -> tuple[str, ...]:
    """Return repo-key directory names already present in keyed archive families."""
    keys: set[str] = set()
    for family in sorted(REPO_KEYED_ARCHIVE_FAMILIES):
        family_root = context.archive_root / family
        try:
            children = tuple(family_root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and child.name != "legacy-import":
                keys.add(child.name)
    return tuple(sorted(keys))


def associated_repo_keys(context: ArchiveContext) -> tuple[str, ...]:
    """Return repo keys allowed to coexist on the same chat archive branch."""
    keys = {context.repo_key, repo_log_key(context.canon_root)}
    parent = superproject_root(context.canon_root)
    if parent is not None:
        keys.add(repo_log_key(parent))
    return tuple(sorted(keys))


def archive_status_summary(context: ArchiveContext) -> ArchiveStatusSummary:
    """Return structured archive dirty-state information."""
    current = current_branch(context)
    status = porcelain_status(context)
    tree_keys = archive_tree_keys(context)
    associated_keys = set(associated_repo_keys(context))
    dirty_keys: set[str] = set()
    global_dirty = False
    for line in status.splitlines():
        key, is_global = dirty_key_for_path(porcelain_path(line))
        if key:
            dirty_keys.add(key)
        if is_global:
            global_dirty = True
    foreign_keys = tuple(sorted(key for key in dirty_keys if key not in associated_keys))
    foreign_tree_keys = tuple(sorted(key for key in tree_keys if key not in associated_keys))
    return ArchiveStatusSummary(
        current_branch=current,
        dirty=bool(status.strip()),
        branch_matches=current == context.branch,
        dirty_keys=tuple(sorted(dirty_keys)),
        current_key_dirty=context.repo_key in dirty_keys,
        foreign_dirty_keys=foreign_keys,
        tree_keys=tree_keys,
        foreign_tree_keys=foreign_tree_keys,
        global_dirty=global_dirty,
    )


def print_status_summary(context: ArchiveContext, summary: ArchiveStatusSummary) -> None:
    """Print stable structured archive status lines."""
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={summary.current_branch}")
    print(f"RUNTIME_LOG_ARCHIVE_EXPECTED_BRANCH={context.branch}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH_MATCH={'yes' if summary.branch_matches else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_DIRTY={'yes' if summary.dirty else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={','.join(summary.dirty_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY={'yes' if summary.current_key_dirty else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS={','.join(summary.foreign_dirty_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY={'yes' if summary.foreign_dirty_keys else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_TREE_KEYS={','.join(summary.tree_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS={','.join(summary.foreign_tree_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE={'yes' if summary.foreign_tree_keys else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_GLOBAL_DIRTY={'yes' if summary.global_dirty else 'no'}")


def archive_next_action(context: ArchiveContext, summary: ArchiveStatusSummary) -> str:
    """Return the next operation for a non-clean archive state."""
    if not summary.branch_matches:
        return f"run runtime_log_archive_git.py ensure for archive branch {context.branch}"
    if summary.foreign_dirty_keys:
        return (
            "commit or migrate foreign repo-key log paths before closeout: "
            + ",".join(summary.foreign_dirty_keys)
        )
    if summary.global_dirty:
        return "commit or revert archive-level dirty paths before closeout"
    if summary.dirty:
        return "run runtime_log_archive_git.py sync, then check-clean"
    return "none"


def safe_archive_relative_path(value: str) -> Path:
    """Return an archive-relative path or fail for unsafe input."""
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ArchiveGitError(f"archive path must be relative and cannot contain '..': {value}")
    return path


def safe_run_id(value: str) -> str:
    """Return a filesystem-safe run id for the archive tree."""
    if not value or value in {".", ".."}:
        raise ArchiveGitError(f"invalid run id: {value!r}")
    if "/" in value or "\\" in value:
        raise ArchiveGitError(f"run id must be one path segment: {value!r}")
    return value


def ensure_commit_identity(context: ArchiveContext) -> None:
    """Ensure the archive clone has a local identity for automated commits."""
    name = git(context.archive_root, ["config", "--get", "user.name"], check=False)
    email = git(context.archive_root, ["config", "--get", "user.email"], check=False)
    if name.returncode != 0 or not name.stdout.strip():
        git(context.archive_root, ["config", "user.name", DEFAULT_COMMIT_NAME])
    if email.returncode != 0 or not email.stdout.strip():
        git(context.archive_root, ["config", "user.email", DEFAULT_COMMIT_EMAIL])


def preserve_managed_dirty_paths(context: ArchiveContext, current: str) -> None:
    """Commit managed runtime artifacts before switching archive branches."""
    paths = porcelain_paths(context)
    unmanaged = [path for path in paths if not managed_runtime_archive_path(path)]
    if unmanaged:
        raise ArchiveGitError(
            "archive has non-runtime local changes on "
            f"{current}: {', '.join(unmanaged)}"
        )
    if not paths:
        return
    ensure_commit_identity(context)
    git(context.archive_root, ["add", "--", *paths])
    staged = git(context.archive_root, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode != 0:
        git(
            context.archive_root,
            ["commit", "-m", f"{BRANCH_SWITCH_COMMIT_MESSAGE}: {current}"],
        )


def source_is_tracked(canon_root: Path, path: Path) -> bool:
    """Return whether one source path is tracked by the canon Git repo."""
    try:
        relative = path.resolve().relative_to(canon_root.resolve())
    except ValueError:
        return False
    result = run(
        ["git", "-C", str(canon_root), "ls-files", "--error-unmatch", "--", relative.as_posix()],
        check=False,
    )
    return result.returncode == 0


def delete_source_file(context: ArchiveContext, source: Path) -> None:
    """Delete one imported source file, using git rm when possible."""
    try:
        relative = source.resolve().relative_to(context.canon_root.resolve())
    except ValueError:
        source.unlink()
        return
    if source_is_tracked(context.canon_root, source):
        run(["git", "-C", str(context.canon_root), "rm", "--", relative.as_posix()])
        return
    source.unlink()


def is_archive_clone(path: Path) -> bool:
    """Return whether path is an existing Git worktree."""
    return (path / ".git").exists()


def ensure_origin(context: ArchiveContext) -> None:
    """Ensure origin points at the configured remote."""
    result = git(context.archive_root, ["remote", "get-url", "origin"], check=False)
    if result.returncode != 0:
        git(context.archive_root, ["remote", "add", "origin", context.remote])
        return
    if result.stdout.strip() != context.remote:
        git(context.archive_root, ["remote", "set-url", "origin", context.remote])


def switch_to_archive_branch(context: ArchiveContext, branch: str) -> None:
    """Switch the archive clone to one local or remote branch."""
    if local_branch_exists(context, branch):
        git(context.archive_root, ["switch", branch])
        return
    if remote_branch_exists(context, branch):
        git(context.archive_root, ["switch", "--track", "-c", branch, f"origin/{branch}"])
        return
    if remote_branch_exists(context, "main"):
        git(context.archive_root, ["switch", "-c", branch, "origin/main"])
        return
    git(context.archive_root, ["switch", "-c", branch])


def ensure_archive(
    context: ArchiveContext,
    *,
    fetch: bool = True,
    allow_branch_switch: bool = True,
) -> None:
    """Ensure the ignored clone exists and is on the runtime log branch."""
    created = False
    if not context.archive_root.exists():
        context.archive_root.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", context.remote, str(context.archive_root)])
        created = True
    if not is_archive_clone(context.archive_root):
        raise ArchiveGitError(f"archive path is not a Git clone: {context.archive_root}")

    ensure_origin(context)
    if fetch:
        git(context.archive_root, ["fetch", "origin"], check=False)

    branch = context.branch
    current = current_branch(context)
    if current == branch:
        return
    if created and not allow_branch_switch:
        switch_to_archive_branch(context, branch)
        return
    if not allow_branch_switch:
        raise ArchiveGitError(
            f"archive_branch_mismatch:current={current}:expected={branch}"
        )
    summary = archive_status_summary(context)
    if summary.dirty:
        preserve_managed_dirty_paths(context, current)
        summary = archive_status_summary(context)
        if summary.dirty:
            raise ArchiveGitError(
                f"archive has local changes on {current}; run sync or push for that branch before switching to {branch}"
            )
    switch_to_archive_branch(context, branch)


def _archive_oid(context: ArchiveContext, revision: str) -> str:
    """Return one archive object id, or the empty string for an unborn branch."""
    result = git(context.archive_root, ["rev-parse", "--verify", revision], check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _require_prepared(transaction: PreparedArchiveTransaction) -> ArchiveContext:
    """Return context only while the transaction owns its live lock."""
    if transaction.lock_handle.closed:
        raise ArchiveGitError("archive_transaction_closed")
    return transaction.context


def prepare_archive_transaction(
    context: ArchiveContext,
    fetch: bool,
    *,
    allow_branch_switch: bool = False,
) -> PreparedArchiveTransaction:
    """Acquire the source lock, ensure once, and return one prepared boundary."""
    lock_path = (context.source_root / HOOK_SPOOL_LOCK_RELATIVE).resolve()
    if lock_path in _ACTIVE_ARCHIVE_LOCKS:
        raise ArchiveGitError("archive_transaction_busy")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+b")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_handle.close()
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            raise ArchiveGitError("archive_transaction_busy") from exc
        raise
    _ACTIVE_ARCHIVE_LOCKS.add(lock_path)
    try:
        ensure_archive(
            context,
            fetch=fetch,
            allow_branch_switch=allow_branch_switch,
        )
        ensured_branch = current_branch(context)
        if ensured_branch != context.branch:
            raise ArchiveGitError(
                f"archive_transaction_branch_mismatch:{ensured_branch}:{context.branch}"
            )
        return PreparedArchiveTransaction(
            context=context,
            lock_path=lock_path,
            lock_handle=lock_handle,
            archive_head_before=_archive_oid(context, "HEAD"),
            ensured_branch=ensured_branch,
        )
    except Exception:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
            _ACTIVE_ARCHIVE_LOCKS.discard(lock_path)
        raise


def _canonical_compact_json(value: object) -> bytes:
    """Return canonical compact ASCII JSON without a trailing newline."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fsync_directory(path: Path, purpose: str) -> None:
    """Fsync one runtime-event directory for an exact classified purpose."""
    if purpose not in RUNTIME_EVENT_FSYNC_PURPOSES:
        raise ValueError(f"invalid runtime-event fsync purpose: {purpose}")
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_archive_directory(path: Path) -> None:
    """Fsync one archive-checkpoint directory outside runtime publication."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_bytes_fsync(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_archive_directory(path.parent)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_archive_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _restore_atomic_file(path: Path, prior: bytes | None) -> None:
    """Restore one managed file to its exact pre-transaction state."""
    if prior is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        _fsync_archive_directory(path.parent)
        return
    _atomic_write_bytes(path, prior)


def _spool_root(transaction: PreparedArchiveTransaction) -> Path:
    context = _require_prepared(transaction)
    return hook_event_spool_root(context.source_root).resolve()


def snapshot_hook_spool_events(
    transaction: PreparedArchiveTransaction,
) -> tuple[HookSpoolEvent, ...]:
    """Capture a fixed-depth sorted size/hash snapshot after preparation."""
    root = _spool_root(transaction)
    if not root.is_dir():
        return ()
    paths: list[Path] = []
    for runtime_directory in sorted(root.iterdir(), key=lambda path: path.name.encode("utf-8")):
        if not runtime_directory.is_dir() or runtime_directory.is_symlink():
            continue
        for hook_directory in sorted(
            runtime_directory.iterdir(), key=lambda path: path.name.encode("utf-8")
        ):
            if not hook_directory.is_dir() or hook_directory.is_symlink():
                continue
            for path in sorted(hook_directory.iterdir(), key=lambda item: item.name.encode("utf-8")):
                if path.suffix != ".json" or not path.is_file() or path.is_symlink():
                    continue
                paths.append(path.resolve())

    snapshot: list[HookSpoolEvent] = []
    for path in sorted(
        paths,
        key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
    ):
        before = path.stat().st_size
        payload = path.read_bytes()
        after = path.stat().st_size
        if before != after or len(payload) != before:
            raise ArchiveGitError(f"spool_snapshot_changed:{path}")
        snapshot.append(HookSpoolEvent(path=path, size=before, bytes_sha256=_hash_bytes(payload)))
    return tuple(snapshot)


def _hook_archive_metadata_paths(context: ArchiveContext) -> tuple[Path, Path]:
    root = context.archive_root / "hook-runs" / context.repo_key
    return root / HOOK_SPOOL_INDEX_NAME, root / HOOK_SPOOL_CURSOR_NAME


def _cursor_body_sha256(payload: dict[str, object]) -> str:
    body = dict(payload)
    body.pop("cursor_body_sha256", None)
    return _hash_bytes(_canonical_compact_json(body))


def load_hook_spool_cursor(
    transaction: PreparedArchiveTransaction,
) -> HookSpoolCursorV1 | None:
    """Load and validate the sole cursor from the prepared archive work tree."""
    context = _require_prepared(transaction)
    _index_path, cursor_path = _hook_archive_metadata_paths(context)
    if not cursor_path.exists():
        return None
    try:
        cursor_bytes = cursor_path.read_bytes()
        payload = cast(object, json.loads(cursor_bytes.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveGitError(f"hook_spool_cursor_invalid:{cursor_path}") from exc
    expected_keys = sorted([
        "schema",
        "schema_version",
        "repo_key",
        "generation",
        "prior_cursor_sha256",
        "transaction_id",
        "source_event_count",
        "accepted_event_count",
        "duplicate_event_count",
        "failed_event_count",
        "source_set_sha256",
        "dedup_index_sha256",
        "archive_commit_oid",
        "cursor_body_sha256",
    ])
    if not isinstance(payload, dict) or list(payload) != expected_keys:
        raise ArchiveGitError("hook_spool_cursor_invalid:field_order")
    value = cast(dict[str, object], payload)
    integer_fields = (
        "schema_version",
        "generation",
        "source_event_count",
        "accepted_event_count",
        "duplicate_event_count",
        "failed_event_count",
    )
    if any(not isinstance(value.get(key), int) for key in integer_fields):
        raise ArchiveGitError("hook_spool_cursor_invalid:integer_field")
    string_fields = tuple(key for key in expected_keys if key not in integer_fields)
    if any(not isinstance(value.get(key), str) for key in string_fields):
        raise ArchiveGitError("hook_spool_cursor_invalid:string_field")
    if cursor_bytes != _canonical_compact_json(value) + b"\n":
        raise ArchiveGitError("hook_spool_cursor_invalid:canonical")
    sha_fields = (
        "prior_cursor_sha256",
        "transaction_id",
        "source_set_sha256",
        "dedup_index_sha256",
        "cursor_body_sha256",
    )
    if any(not RUNTIME_EVENT_HEX64.fullmatch(cast(str, value[key])) for key in sha_fields):
        raise ArchiveGitError("hook_spool_cursor_invalid:hash")
    archive_commit_oid = cast(str, value["archive_commit_oid"])
    if archive_commit_oid and not RUNTIME_EVENT_OID40.fullmatch(archive_commit_oid):
        raise ArchiveGitError("hook_spool_cursor_invalid:archive_commit_oid")
    counts = tuple(cast(int, value[key]) for key in integer_fields)
    if any(item < 0 for item in counts):
        raise ArchiveGitError("hook_spool_cursor_invalid:negative_count")
    if cast(int, value["source_event_count"]) != sum(
        cast(int, value[key])
        for key in (
            "accepted_event_count",
            "duplicate_event_count",
            "failed_event_count",
        )
    ):
        raise ArchiveGitError("hook_spool_cursor_invalid:event_count")
    if (
        value["schema"] != HOOK_SPOOL_CURSOR_SCHEMA
        or value["schema_version"] != HOOK_SPOOL_CURSOR_SCHEMA_VERSION
        or value["repo_key"] != context.repo_key
        or value["cursor_body_sha256"] != _cursor_body_sha256(value)
    ):
        raise ArchiveGitError("hook_spool_cursor_invalid:certificate")
    try:
        return HookSpoolCursorV1(**value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ArchiveGitError("hook_spool_cursor_invalid:types") from exc


def _parse_spool_index_bytes(
    payload: bytes,
) -> dict[str, tuple[str, str, str, str]]:
    """Return event id to SHA/namespace/hook/projection from the canonical index."""
    entries: dict[str, tuple[str, str, str, str]] = {}
    expected_keys = sorted([
        "schema",
        "event_id",
        "event_sha256",
        "runtime_namespace",
        "hook_name",
        "projection_path",
        "transaction_id",
    ])
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchiveGitError("hook_spool_index_invalid:utf8") from exc
    if payload and not payload.endswith(b"\n"):
        raise ArchiveGitError("hook_spool_index_invalid:partial_row")
    for line in text.splitlines():
        if not line:
            raise ArchiveGitError("hook_spool_index_invalid:empty_row")
        try:
            value = cast(object, json.loads(line))
        except json.JSONDecodeError as exc:
            raise ArchiveGitError("hook_spool_index_invalid:json") from exc
        if not isinstance(value, dict) or list(value) != expected_keys:
            raise ArchiveGitError("hook_spool_index_invalid:field_order")
        row = cast(dict[str, object], value)
        if line.encode("utf-8") != _canonical_compact_json(row):
            raise ArchiveGitError("hook_spool_index_invalid:canonical")
        index_string_fields = tuple(key for key in expected_keys if key != "schema")
        if row.get("schema") != HOOK_SPOOL_INDEX_SCHEMA or any(
            not isinstance(row.get(key), str) or not cast(str, row[key])
            for key in index_string_fields
        ):
            raise ArchiveGitError("hook_spool_index_invalid:field")
        event_id = cast(str, row["event_id"])
        event_sha256 = cast(str, row["event_sha256"])
        if event_id in entries or not RUNTIME_EVENT_HEX64.fullmatch(event_sha256):
            raise ArchiveGitError("hook_spool_index_invalid:identity")
        entries[event_id] = (
            event_sha256,
            cast(str, row["runtime_namespace"]),
            cast(str, row["hook_name"]),
            cast(str, row["projection_path"]),
        )
    return entries


def _validate_spool_checkpoint_state(
    transaction: PreparedArchiveTransaction,
    index_present: bool,
    index_bytes: bytes,
    index_entries: dict[str, tuple[str, str, str, str]],
    cursor: HookSpoolCursorV1 | None,
) -> None:
    """Fail closed unless index, cursor, and projections form one certificate."""
    context = _require_prepared(transaction)
    if index_present != (cursor is not None):
        raise ArchiveGitError("hook_spool_checkpoint_inconsistent:index_cursor")
    if cursor is None:
        return
    if _hash_bytes(index_bytes) != cursor.dedup_index_sha256:
        raise ArchiveGitError("hook_spool_checkpoint_inconsistent:index_hash")
    projection_root = Path("hook-runs") / context.repo_key
    projection_cache: dict[Path, dict[str, str]] = {}
    for event_id, (event_sha256, _namespace, _hook_name, serialized_path) in index_entries.items():
        projection_relative = Path(serialized_path)
        try:
            projection_relative.relative_to(projection_root)
        except ValueError as exc:
            raise ArchiveGitError(
                "hook_spool_checkpoint_inconsistent:projection_path"
            ) from exc
        if (
            projection_relative.is_absolute()
            or ".." in projection_relative.parts
            or projection_relative.suffix != ".jsonl"
        ):
            raise ArchiveGitError(
                "hook_spool_checkpoint_inconsistent:projection_path"
            )
        projection_path = context.archive_root / projection_relative
        if not projection_path.is_file() or projection_path.is_symlink():
            raise ArchiveGitError(
                "hook_spool_checkpoint_inconsistent:projection_missing"
            )
        projection_entries = projection_cache.get(projection_path)
        if projection_entries is None:
            projection_entries = _projection_event_hashes(projection_path.read_bytes())
            projection_cache[projection_path] = projection_entries
        if projection_entries.get(event_id) != event_sha256:
            raise ArchiveGitError(
                "hook_spool_checkpoint_inconsistent:projection_mismatch"
            )


def _canonical_spool_event(payload: bytes) -> tuple[dict[str, object], bytes]:
    """Validate and canonicalize one exact hook-event source file."""
    try:
        value = cast(object, json.loads(payload.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveGitError("hook_spool_event_invalid:json") from exc
    if not isinstance(value, dict):
        raise ArchiveGitError("hook_spool_event_invalid:schema")
    event = cast(dict[str, object], value)
    for key in (
        "hook_run_id",
        "timestamp",
        "payload_fingerprint",
        "status",
        "source_repo_key",
        "hook_log_namespace",
    ):
        if not isinstance(event.get(key), str) or not cast(str, event[key]).strip():
            raise ArchiveGitError(f"hook_spool_event_invalid:{key}")
    try:
        canonical = _canonical_compact_json(event) + b"\n"
    except (TypeError, ValueError) as exc:
        raise ArchiveGitError("hook_spool_event_invalid:canonical") from exc
    if canonical != payload:
        raise ArchiveGitError("hook_spool_event_invalid:noncanonical")
    return event, canonical


def _projection_event_hashes(payload: bytes) -> dict[str, str]:
    """Return event identities from one canonical JSONL projection."""
    entries: dict[str, str] = {}
    for line in payload.splitlines(keepends=True):
        if not line.strip():
            continue
        event, canonical = _canonical_spool_event(line)
        event_id = cast(str, event["hook_run_id"])
        event_sha256 = _hash_bytes(canonical)
        previous = entries.get(event_id)
        if previous is not None and previous != event_sha256:
            raise ArchiveGitError("spool_conflict")
        entries[event_id] = event_sha256
    return entries


def _dedup_key(event_id: str, event_sha256: str) -> str:
    return _hash_bytes(
        _canonical_compact_json({"event_id": event_id, "event_sha256": event_sha256})
    )


def ingest_hook_event_spool(
    transaction: PreparedArchiveTransaction,
    spool_snapshot: tuple[HookSpoolEvent, ...],
) -> HookSpoolIngestResult:
    """Validate a fixed snapshot and materialize projection/index/cursor changes."""
    context = _require_prepared(transaction)
    spool_root = _spool_root(transaction)
    index_path, cursor_path = _hook_archive_metadata_paths(context)
    index_present = index_path.exists()
    index_bytes_before = index_path.read_bytes() if index_present else b""
    index_entries = _parse_spool_index_bytes(index_bytes_before)
    cursor_before = cursor_path.read_bytes() if cursor_path.exists() else b""
    cursor = load_hook_spool_cursor(transaction)
    _validate_spool_checkpoint_state(
        transaction,
        index_present,
        index_bytes_before,
        index_entries,
        cursor,
    )

    source_rows: list[list[object]] = []
    accepted: list[tuple[HookSpoolEvent, str, str, str, bytes, Path]] = []
    duplicates: list[HookSpoolEvent] = []
    projection_cache: dict[Path, dict[str, str]] = {}
    projection_bytes: dict[Path, bytes] = {}
    projection_original_bytes: dict[Path, bytes | None] = {}
    pending_identities: dict[str, tuple[str, str, str]] = {}
    agent_canon_head = agent_canon_git_commit_key(context.canon_root)

    for snapshot_event in spool_snapshot:
        try:
            relative = snapshot_event.path.relative_to(spool_root)
        except ValueError as exc:
            raise ArchiveGitError("hook_spool_event_invalid:outside_root") from exc
        if len(relative.parts) != 3 or relative.suffix != ".json":
            raise ArchiveGitError("hook_spool_event_invalid:path_shape")
        runtime_namespace, hook_name, file_name = relative.parts
        payload = snapshot_event.path.read_bytes()
        if len(payload) != snapshot_event.size or _hash_bytes(payload) != snapshot_event.bytes_sha256:
            raise ArchiveGitError(f"spool_snapshot_changed:{snapshot_event.path}")
        event, canonical = _canonical_spool_event(payload)
        event_id = cast(str, event["hook_run_id"])
        event_sha256 = _hash_bytes(canonical)
        _dedup_key(event_id, event_sha256)
        if file_name != f"{event_id}.json" or event_sha256 != snapshot_event.bytes_sha256:
            raise ArchiveGitError("hook_spool_event_invalid:identity")
        if event["source_repo_key"] != context.repo_key:
            raise ArchiveGitError("hook_spool_event_invalid:repo_key")
        if event["hook_log_namespace"] != runtime_namespace:
            raise ArchiveGitError("hook_spool_event_invalid:namespace")
        source_rows.append([relative.as_posix(), event_sha256])

        indexed = index_entries.get(event_id)
        if indexed is not None:
            if indexed[:3] != (event_sha256, runtime_namespace, hook_name):
                raise ArchiveGitError("spool_conflict")
            duplicates.append(snapshot_event)
            continue
        pending = pending_identities.get(event_id)
        if pending is not None:
            if pending != (event_sha256, runtime_namespace, hook_name):
                raise ArchiveGitError("spool_conflict")
            duplicates.append(snapshot_event)
            continue

        projection_relative = (
            Path("hook-runs")
            / context.repo_key
            / runtime_namespace
            / f"{hook_name}-{agent_canon_head}.jsonl"
        )
        projection_path = context.archive_root / projection_relative
        projection_entries = projection_cache.get(projection_path)
        if projection_entries is None:
            projection_exists = projection_path.exists()
            existing = projection_path.read_bytes() if projection_exists else b""
            projection_entries = _projection_event_hashes(existing)
            projection_cache[projection_path] = projection_entries
            projection_bytes[projection_path] = existing
            projection_original_bytes[projection_path] = existing if projection_exists else None
        projected_sha = projection_entries.get(event_id)
        if projected_sha is not None:
            if projected_sha != event_sha256:
                raise ArchiveGitError("spool_conflict")
        else:
            projection_bytes[projection_path] += canonical
        accepted.append(
            (
                snapshot_event,
                event_id,
                runtime_namespace,
                hook_name,
                canonical,
                projection_relative,
            )
        )
        pending_identities[event_id] = (event_sha256, runtime_namespace, hook_name)
        projection_entries[event_id] = event_sha256

    source_set_sha256 = _hash_bytes(_canonical_compact_json(source_rows))
    prior_cursor_sha256 = _hash_bytes(cursor_before) if cursor_before else HOOK_SPOOL_ZERO_SHA256
    transaction_id = _hash_bytes(
        _canonical_compact_json(
            {
                "archive_head_before": transaction.archive_head_before,
                "prior_cursor_sha256": prior_cursor_sha256,
                "repo_key": context.repo_key,
                "source_set_sha256": source_set_sha256,
            }
        )
    )

    projection_updates: dict[Path, bytes] = {
        context.archive_root / projection_relative: projection_bytes[
            context.archive_root / projection_relative
        ]
        for *_, projection_relative in accepted
    }
    index_bytes_after = index_bytes_before
    for snapshot_event, event_id, runtime_namespace, hook_name, _canonical, projection_relative in accepted:
        index_row = {
            "schema": HOOK_SPOOL_INDEX_SCHEMA,
            "event_id": event_id,
            "event_sha256": snapshot_event.bytes_sha256,
            "runtime_namespace": runtime_namespace,
            "hook_name": hook_name,
            "projection_path": projection_relative.as_posix(),
            "transaction_id": transaction_id,
        }
        index_bytes_after += _canonical_compact_json(index_row) + b"\n"

    dedup_index_sha256 = _hash_bytes(index_bytes_after)
    cursor_bytes_after = cursor_before
    if accepted:
        cursor_body: dict[str, object] = {
            "schema": HOOK_SPOOL_CURSOR_SCHEMA,
            "schema_version": HOOK_SPOOL_CURSOR_SCHEMA_VERSION,
            "repo_key": context.repo_key,
            "generation": (cursor.generation if cursor else 0) + 1,
            "prior_cursor_sha256": prior_cursor_sha256,
            "transaction_id": transaction_id,
            "source_event_count": len(spool_snapshot),
            "accepted_event_count": len(accepted),
            "duplicate_event_count": len(duplicates),
            "failed_event_count": 0,
            "source_set_sha256": source_set_sha256,
            "dedup_index_sha256": dedup_index_sha256,
            "archive_commit_oid": transaction.archive_head_before,
        }
        cursor_body["cursor_body_sha256"] = _cursor_body_sha256(cursor_body)
        cursor_bytes_after = _canonical_compact_json(cursor_body) + b"\n"

        prior_files: dict[Path, bytes | None] = {
            path: projection_original_bytes[path] for path in projection_updates
        }
        prior_files[index_path] = index_bytes_before if index_present else None
        prior_files[cursor_path] = cursor_before if cursor_path.exists() else None
        touched: list[Path] = []
        try:
            for projection_path in sorted(
                projection_updates, key=lambda path: path.as_posix().encode("utf-8")
            ):
                touched.append(projection_path)
                _atomic_write_bytes(projection_path, projection_updates[projection_path])
            touched.append(index_path)
            _atomic_write_bytes(index_path, index_bytes_after)
            touched.append(cursor_path)
            _atomic_write_bytes(cursor_path, cursor_bytes_after)
        except (ArchiveGitError, OSError) as exc:
            try:
                for path in reversed(touched):
                    _restore_atomic_file(path, prior_files[path])
            except OSError as recovery_error:
                raise ArchiveGitError(
                    f"hook_spool_recovery_failed:{recovery_error}"
                ) from exc
            raise ArchiveGitError(f"hook_spool_ingest_failed:{exc}") from exc

    observed_index = index_path.read_bytes() if index_path.exists() else b""
    observed_cursor = cursor_path.read_bytes() if cursor_path.exists() else b""
    if observed_index != index_bytes_after or observed_cursor != cursor_bytes_after:
        raise ArchiveGitError("hook_spool_checkpoint_inconsistent:write_readback")
    return HookSpoolIngestResult(
        transaction_id=transaction_id,
        spool_snapshot=spool_snapshot,
        accepted_events=tuple(item[0] for item in accepted),
        duplicate_events=tuple(duplicates),
        failed_event_count=0,
        source_set_sha256=source_set_sha256,
        dedup_index_path=index_path,
        dedup_index_sha256=dedup_index_sha256,
        cursor_path=cursor_path,
        cursor_sha256=_hash_bytes(observed_cursor),
    )


def _archive_blob_at(context: ArchiveContext, commit_oid: str, relative_path: Path) -> bytes:
    if not commit_oid:
        return b""
    result = git(
        context.archive_root,
        ["show", f"{commit_oid}:{relative_path.as_posix()}"],
        check=False,
    )
    return result.stdout.encode("utf-8") if result.returncode == 0 else b""


def _worktree_hash(path: Path) -> str:
    return _hash_bytes(path.read_bytes() if path.exists() else b"")


def finalize_hook_spool_readback(
    transaction: PreparedArchiveTransaction,
    receipt: ArchivePublicationReceipt,
    ingest_result: HookSpoolIngestResult,
) -> int:
    """Delete only source files certified by exact committed-tree readback."""
    context = _require_prepared(transaction)
    if receipt.status != "committed" or not receipt.pushed:
        return 0
    covered = ingest_result.accepted_events + ingest_result.duplicate_events
    if not covered:
        return 0
    if not receipt.archive_commit_oid or not receipt.archive_tree_oid:
        raise ArchiveGitError("archive_readback_mismatch:missing_oid")
    if (
        receipt.dedup_index_sha256 != ingest_result.dedup_index_sha256
        or receipt.cursor_sha256 != ingest_result.cursor_sha256
    ):
        raise ArchiveGitError("archive_readback_mismatch:metadata")

    index_relative = ingest_result.dedup_index_path.relative_to(context.archive_root)
    committed_index = _archive_blob_at(context, receipt.archive_commit_oid, index_relative)
    index_entries = _parse_spool_index_bytes(committed_index)
    projection_cache: dict[Path, dict[str, str]] = {}
    for event in covered:
        event_id = event.path.stem
        indexed = index_entries.get(event_id)
        if indexed is None or indexed[0] != event.bytes_sha256:
            raise ArchiveGitError("archive_readback_mismatch:index")
        projection_path = Path(indexed[3])
        projection_entries = projection_cache.get(projection_path)
        if projection_entries is None:
            projection = _archive_blob_at(context, receipt.archive_commit_oid, projection_path)
            projection_entries = _projection_event_hashes(projection)
            projection_cache[projection_path] = projection_entries
        if projection_entries.get(event_id) != event.bytes_sha256:
            raise ArchiveGitError("archive_readback_mismatch:projection")

    removed = 0
    fsync_directories: set[Path] = set()
    for event in covered:
        try:
            payload = event.path.read_bytes()
        except FileNotFoundError:
            continue
        if len(payload) != event.size or _hash_bytes(payload) != event.bytes_sha256:
            continue
        event.path.unlink()
        removed += 1
        fsync_directories.add(event.path.parent)
    for directory in sorted(fsync_directories, key=lambda path: path.as_posix()):
        _fsync_archive_directory(directory)
    return removed


def print_context(context: ArchiveContext) -> None:
    """Print stable context lines."""
    run_local_agent_reports = context.source_root / DEFAULT_AGENT_REPORT_ROOT
    archive_agent_reports = (
        context.archive_root / DEFAULT_AGENT_REPORT_DESTINATION / context.repo_key
    )
    print(f"RUNTIME_LOG_ARCHIVE_SOURCE_ROOT={context.source_root}")
    print(f"RUNTIME_LOG_ARCHIVE_CANON_ROOT={context.canon_root}")
    print(f"RUNTIME_LOG_ARCHIVE_ROOT={context.archive_root}")
    print(f"RUNTIME_LOG_ARCHIVE_ENV_KEY={context.env_key}")
    print(f"RUNTIME_LOG_ARCHIVE_REMOTE={context.remote}")
    print(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={context.repo_key}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH_KEY={context.branch_key}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH={context.branch}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL={run_local_agent_reports}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH={context.branch}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={archive_agent_reports}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{context.repo_key}")


def command_repo_key(context: ArchiveContext) -> int:
    """Print repo-key context."""
    print_context(context)
    return 0


def command_ensure(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Ensure archive clone and branch."""
    with prepare_archive_transaction(
        context,
        fetch=not args.no_fetch,
        allow_branch_switch=True,
    ) as transaction:
        print_context(transaction.context)
        print(f"RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={transaction.ensured_branch}")
        print("RUNTIME_LOG_ARCHIVE_ENSURE=pass")
    return 0


def command_status(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Print archive status."""
    print_context(context)
    if not context.archive_root.exists():
        print("RUNTIME_LOG_ARCHIVE_STATUS=missing")
        return 0
    if not is_archive_clone(context.archive_root):
        print("RUNTIME_LOG_ARCHIVE_STATUS=invalid")
        return 1
    status = porcelain_status(context)
    summary = archive_status_summary(context)
    print_status_summary(context, summary)
    print(f"RUNTIME_LOG_ARCHIVE_NEXT_ACTION={archive_next_action(context, summary)}")
    if args.porcelain:
        for line in status.splitlines():
            print(f"RUNTIME_LOG_ARCHIVE_PORCELAIN={line}")
    if not summary.branch_matches:
        print("RUNTIME_LOG_ARCHIVE_ERROR_CODE=archive_branch_mismatch")
        print("RUNTIME_LOG_ARCHIVE_STATUS=branch_mismatch")
        return 1
    print("RUNTIME_LOG_ARCHIVE_STATUS=pass")
    return 0


def command_check_clean(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Fail unless the archive clone is on the expected branch and clean."""
    print_context(context)
    if not context.archive_root.exists():
        print("RUNTIME_LOG_ARCHIVE_CLEAN=no")
        print("RUNTIME_LOG_ARCHIVE_STATUS=missing")
        return 1
    if not is_archive_clone(context.archive_root):
        print("RUNTIME_LOG_ARCHIVE_CLEAN=no")
        print("RUNTIME_LOG_ARCHIVE_STATUS=invalid")
        return 1
    status = porcelain_status(context)
    summary = archive_status_summary(context)
    print_status_summary(context, summary)
    clean = summary.branch_matches and not summary.dirty and not summary.foreign_tree_keys
    print(f"RUNTIME_LOG_ARCHIVE_NEXT_ACTION={archive_next_action(context, summary)}")
    if args.porcelain:
        for line in status.splitlines():
            print(f"RUNTIME_LOG_ARCHIVE_PORCELAIN={line}")
    print(f"RUNTIME_LOG_ARCHIVE_CLEAN={'yes' if clean else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass" if clean else "RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail")
    return 0 if clean else 1


def _legacy_import_index_path(context: ArchiveContext) -> Path:
    """Return the append-only index that certifies each legacy import plan."""
    return context.archive_root / "legacy-import" / "import-index.jsonl"


def _legacy_import_plan(
    transaction: PreparedArchiveTransaction,
    *,
    family: str,
    legacy_root: Path,
    destination_prefix: Path,
    sources: list[tuple[Path, str, bool]],
    delete_source: bool,
) -> LegacyImportPlan:
    """Copy and inventory legacy sources without authorizing source deletion."""
    context = _require_prepared(transaction)
    records: list[LegacyImportRecord] = []
    imported = 0
    existing = 0
    for source, relative, should_copy in sources:
        if not source.is_file():
            continue
        payload = source.read_bytes()
        destination = (
            (destination_prefix / Path(relative)).as_posix()
            if should_copy
            else None
        )
        target = context.archive_root / destination if destination else None
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != payload:
                    raise ArchiveGitError(
                        f"archive destination already exists with different content: {target}"
                    )
                existing += 1
            else:
                shutil.copy2(source, target)
                imported += 1
        records.append(
            LegacyImportRecord(
                source=source,
                source_relative=relative,
                destination=destination,
                byte_count=len(payload),
                sha256=_hash_bytes(payload),
            )
        )

    for record in records:
        try:
            observed = record.source.read_bytes()
        except FileNotFoundError as exc:
            raise ArchiveGitError("legacy_source_changed_before_inventory") from exc
        if len(observed) != record.byte_count or _hash_bytes(observed) != record.sha256:
            raise ArchiveGitError("legacy_source_changed_before_inventory")

    inventory_records = [
        {
            "bytes": record.byte_count,
            "destination": record.destination,
            "sha256": record.sha256,
            "source": record.source_relative,
        }
        for record in records
    ]
    inventory = {
        "family": family,
        "files": inventory_records,
        "schema": "agent_canon.legacy_import.v1",
    }
    inventory_sha256 = _hash_bytes(_canonical_compact_json(inventory))
    index_entry = {
        "family": family,
        "file_count": len(records),
        "files": inventory_records,
        "inventory_sha256": inventory_sha256,
        "schema": "agent_canon.legacy_import.v1",
    }
    index_path = _legacy_import_index_path(context)
    if records:
        write_jsonl_once(index_path, index_entry, inventory_sha256)
        git(context.archive_root, ["add", "--", "legacy-import"])
    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_FAMILY={family}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_ROOT={legacy_root}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_FILES={sum(1 for record in records if record.destination)}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_NEW_FILES={imported}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EXISTING_FILES={existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_DELETIONS={len(records)}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_INVENTORY_SHA256={inventory_sha256}")
    copied_count = sum(1 for record in records if record.destination)
    if family == "hook-runs":
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_LEGACY_ROOT={legacy_root}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_DESTINATION={destination_prefix.as_posix()}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_FILES={copied_count}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_NEW_FILES={imported}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EXISTING_FILES={existing}")
    else:
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_ROOT={legacy_root}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DESTINATION={destination_prefix.as_posix()}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_FILES={copied_count}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_NEW_FILES={imported}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_EXISTING_FILES={existing}")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS={len(records)}")
    return LegacyImportPlan(
        family=family,
        legacy_root=legacy_root,
        index_path=index_path,
        inventory_sha256=inventory_sha256,
        records=tuple(records),
        delete_source=delete_source,
    )


def _finalize_legacy_import(
    transaction: PreparedArchiveTransaction,
    plan: LegacyImportPlan,
    args: argparse.Namespace,
) -> int:
    """Publish first, then delete only the already-read-back legacy sources."""
    if not plan.delete_source:
        print("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no")
        if plan.family == "eval-results":
            print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no")
        print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
        return 0
    if not plan.records:
        print("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no")
        if plan.family == "eval-results":
            print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no")
        print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
        return 0
    receipt = publish_prepared_archive(transaction, args)
    if receipt.status != "committed" or not receipt.pushed:
        print("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no")
        if plan.family == "eval-results":
            print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no")
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT=publication_{receipt.status}")
        return 1
    required_paths = tuple(
        path
        for path in (plan.index_path, *(transaction.context.archive_root / record.destination
                                        for record in plan.records if record.destination))
    )
    _verify_remote_archive_readback(transaction.context, receipt, required_paths)
    for record in plan.records:
        try:
            payload = record.source.read_bytes()
        except FileNotFoundError as exc:
            raise ArchiveGitError("legacy_source_changed_before_finalize") from exc
        if len(payload) != record.byte_count or _hash_bytes(payload) != record.sha256:
            raise ArchiveGitError("legacy_source_changed_before_finalize")
    for record in plan.records:
        delete_source_file(transaction.context, record.source)
    print("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=yes")
    if plan.family == "eval-results":
        print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=yes")
    print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
    return 0


def _import_legacy_prepared(
    transaction: PreparedArchiveTransaction,
    args: argparse.Namespace,
) -> LegacyImportPlan:
    """Prepare old in-tree hook JSONL without deleting any source."""
    context = _require_prepared(transaction)
    legacy_root = (
        args.legacy_root.resolve()
        if args.legacy_root
        else context.canon_root / "agents" / "evals" / "results" / "hook-runs"
    )
    destination_prefix = safe_archive_relative_path(args.destination_prefix)
    if context.archive_root.resolve() == legacy_root or context.archive_root.resolve() in legacy_root.parents:
        raise ArchiveGitError("legacy root cannot be inside the archive clone")
    sources = (
        [(source, source.relative_to(legacy_root).as_posix(), True)
         for source in sorted(legacy_root.rglob("*.jsonl")) if source.is_file()]
        if legacy_root.exists()
        else []
    )
    return _legacy_import_plan(
        transaction,
        family="hook-runs",
        legacy_root=legacy_root,
        destination_prefix=destination_prefix,
        sources=sources,
        delete_source=args.delete_source,
    )


def command_import_legacy(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Import legacy hook logs and finalize deletion only after readback."""
    with prepare_archive_transaction(context, fetch=True) as transaction:
        plan = _import_legacy_prepared(transaction, args)
        return _finalize_legacy_import(transaction, plan, args)


def should_import_eval_result(relative: Path) -> bool:
    """Return whether one legacy eval result file should move to eval-results."""
    if relative.parts and relative.parts[0] == "hook-runs":
        return False
    return True


def _import_eval_results_prepared(
    transaction: PreparedArchiveTransaction,
    args: argparse.Namespace,
) -> LegacyImportPlan:
    """Prepare old in-tree eval reports without deleting any source."""
    context = _require_prepared(transaction)
    legacy_root = (
        args.legacy_root.resolve()
        if args.legacy_root
        else context.canon_root / "agents" / "evals" / "results"
    )
    destination_prefix = safe_archive_relative_path(args.destination_prefix)
    if context.archive_root.resolve() == legacy_root or context.archive_root.resolve() in legacy_root.parents:
        raise ArchiveGitError("legacy root cannot be inside the archive clone")
    sources: list[tuple[Path, str, bool]] = []
    if legacy_root.exists():
        for source in sorted(path for path in legacy_root.rglob("*") if path.is_file()):
            relative = source.relative_to(legacy_root)
            if should_import_eval_result(relative):
                sources.append((source, relative.as_posix(), True))
        hook_notice = legacy_root / "hook-runs" / "README.md"
        if hook_notice.exists():
            sources.append((hook_notice, "hook-runs/README.md", False))
    return _legacy_import_plan(
        transaction,
        family="eval-results",
        legacy_root=legacy_root,
        destination_prefix=destination_prefix,
        sources=sources,
        delete_source=args.delete_source,
    )


def command_import_eval_results(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Import legacy eval results and finalize deletion only after readback."""
    with prepare_archive_transaction(context, fetch=True) as transaction:
        plan = _import_eval_results_prepared(transaction, args)
        return _finalize_legacy_import(transaction, plan, args)


def iter_report_files(report_dir: Path) -> list[Path]:
    """Return deterministic report bundle files to snapshot."""
    files: list[Path] = []
    for path in sorted(report_dir.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def report_snapshot_digest(report_dir: Path, files: list[Path]) -> str:
    """Return a stable digest for one report snapshot."""
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(report_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()[:REPORT_SNAPSHOT_DIGEST_CHARS]


def write_jsonl_once(path: Path, payload: dict[str, object], key: str) -> bool:
    """Append a JSON object unless a line with the same key already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = cast(object, json.loads(line))
            except json.JSONDecodeError:
                continue
            if isinstance(existing, dict):
                existing_payload = cast(dict[str, object], existing)
                if existing_payload.get("archive_id") == key:
                    return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return True


def _archive_agent_report_prepared(
    transaction: PreparedArchiveTransaction,
    args: argparse.Namespace,
) -> int:
    """Snapshot one run bundle into the archive clone."""
    context = _require_prepared(transaction)
    report_dir = args.report_dir.resolve()
    if not report_dir.is_dir():
        raise ArchiveGitError(f"report directory does not exist: {report_dir}")
    try:
        report_dir.relative_to(context.source_root.resolve())
    except ValueError as exc:
        raise ArchiveGitError(
            f"report directory must be under source root {context.source_root}: {report_dir}"
        ) from exc

    run_id = safe_run_id(report_dir.name)
    files = iter_report_files(report_dir)
    max_file_bytes = getattr(args, "max_file_bytes", None)
    if max_file_bytes is not None:
        files = [
            path
            for path in files
            if not should_skip_agent_report(
                path.relative_to(report_dir), path, max_file_bytes
            )
        ]
    if not files:
        raise ArchiveGitError(f"report directory has no files to archive: {report_dir}")
    snapshot_id = report_snapshot_digest(report_dir, files)
    archive_id = f"{run_id}-{snapshot_id}"
    destination = agent_report_archive_dir(context.source_root, context.canon_root) / run_id / snapshot_id
    destination.mkdir(parents=True, exist_ok=True)

    file_entries: list[dict[str, object]] = []
    copied = 0
    existing = 0
    for source in files:
        relative = source.relative_to(report_dir)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source_bytes = source.read_bytes()
        if target.exists():
            if target.read_bytes() != source_bytes:
                raise ArchiveGitError(f"archive destination has conflicting content: {target}")
            existing += 1
        else:
            shutil.copy2(source, target)
            copied += 1
        file_entries.append(
            {
                "path": relative.as_posix(),
                "bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        )

    manifest = {
        "schema": AGENT_REPORT_ARCHIVE_SCHEMA,
        "archive_id": archive_id,
        "archived_at": datetime.now(UTC).isoformat(),
        "codex_trace_key": codex_trace_key(),
        "agent_canon_git_head": source_git_head(context.canon_root),
        "source_git_head": source_git_head(context.source_root),
        "source_root": str(context.source_root),
        "canon_root": str(context.canon_root),
        "repo_key": context.repo_key,
        "branch": context.branch,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "report_dir": str(report_dir),
        "destination": str(destination.relative_to(context.archive_root)),
        "file_count": len(file_entries),
        "files": file_entries,
    }
    manifest_path = destination / "archive_manifest.json"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists():
        try:
            existing_manifest = cast(object, json.loads(manifest_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ArchiveGitError(f"archive manifest is not valid JSON: {manifest_path}") from exc
        existing_manifest_payload = (
            cast(dict[str, object], existing_manifest) if isinstance(existing_manifest, dict) else {}
        )
        if existing_manifest_payload.get("archive_id") != archive_id:
            raise ArchiveGitError(f"archive manifest conflict: {manifest_path}")
    else:
        manifest_path.write_text(manifest_text, encoding="utf-8")

    index_path = agent_report_archive_dir(context.source_root, context.canon_root) / "index.jsonl"
    index_appended = write_jsonl_once(
        index_path,
        {
            "schema": AGENT_REPORT_ARCHIVE_SCHEMA,
            "archive_id": archive_id,
            "archived_at": manifest["archived_at"],
            "repo_key": context.repo_key,
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "destination": manifest["destination"],
            "file_count": len(file_entries),
        },
        archive_id,
    )
    git(context.archive_root, ["add", "--", Path("agent-reports").as_posix()])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_RUN_ID={run_id}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT={snapshot_id}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={manifest['destination']}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={len(file_entries)}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_NEW_FILES={copied}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING_FILES={existing}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED={'yes' if index_appended else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass")
    return 0


def command_archive_agent_report(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Archive one run bundle under the sole archive transaction lock."""
    with prepare_archive_transaction(context, fetch=True) as transaction:
        return _archive_agent_report_prepared(transaction, args)


@dataclass(frozen=True)
class AgentReportArchiveSummary:
    """Counts from copying run-local agent reports into the archive."""

    report_root: Path
    destination: Path
    files: int
    copied: int
    updated: int
    existing: int
    skipped: int


def report_root_for_context(context: ArchiveContext, report_root: Path | None) -> Path:
    """Return the source report root for agent run artifacts."""
    return (report_root.resolve() if report_root else context.source_root / DEFAULT_AGENT_REPORT_ROOT)


def should_skip_agent_report(relative: Path, source: Path, max_file_bytes: int) -> bool:
    """Return whether one report artifact should stay out of the log archive."""
    if any(part in AGENT_REPORT_EXCLUDED_DIRS for part in relative.parts):
        return True
    if relative.name in AGENT_REPORT_EXCLUDED_FILES:
        return True
    try:
        return source.stat().st_size > max(0, max_file_bytes)
    except OSError:
        return True


def copy_agent_reports_prepared(
    transaction: PreparedArchiveTransaction,
    *,
    report_root: Path | None,
    destination_prefix: Path,
    max_file_bytes: int,
) -> AgentReportArchiveSummary:
    """Snapshot each run bundle; never overwrite a mutable full-tree projection."""
    context = _require_prepared(transaction)
    if destination_prefix != DEFAULT_AGENT_REPORT_DESTINATION:
        raise ArchiveGitError(
            "agent report destination is policy-owned: "
            f"expected {DEFAULT_AGENT_REPORT_DESTINATION}"
        )
    root = report_root_for_context(context, report_root)
    default_destination = agent_report_archive_dir(context.source_root, context.canon_root)
    if context.archive_root.resolve() == root or context.archive_root.resolve() in root.parents:
        raise ArchiveGitError("agent report root cannot be inside the archive clone")
    if not root.exists():
        return AgentReportArchiveSummary(root, default_destination, 0, 0, 0, 0, 0)

    files = copied = existing = skipped = 0
    run_directories = sorted(path for path in root.iterdir() if path.is_dir())
    for run_dir in run_directories:
        run_files = iter_report_files(run_dir)
        eligible = [
            path
            for path in run_files
            if not should_skip_agent_report(path.relative_to(run_dir), path, max_file_bytes)
        ]
        skipped += len(run_files) - len(eligible)
        if not eligible:
            continue
        run_id = safe_run_id(run_dir.name)
        snapshot_id = report_snapshot_digest(run_dir, eligible)
        destination = default_destination / run_id / snapshot_id
        before = {
            source.relative_to(run_dir).as_posix(): (destination / source.relative_to(run_dir)).read_bytes()
            for source in eligible
            if (destination / source.relative_to(run_dir)).is_file()
        }
        _archive_agent_report_prepared(
            transaction,
            argparse.Namespace(report_dir=run_dir, max_file_bytes=max_file_bytes),
        )
        files += len(eligible)
        existing += len(before)
        copied += len(eligible) - len(before)

    return AgentReportArchiveSummary(root, default_destination, files, copied, 0, existing, skipped)


def print_agent_report_archive_summary(summary: AgentReportArchiveSummary) -> None:
    """Print stable status lines for agent report archiving."""
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_ROOT={summary.report_root}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={summary.destination}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={summary.files}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COPIED={summary.copied}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_UPDATED={summary.updated}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING={summary.existing}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SKIPPED={summary.skipped}")


def command_archive_agent_reports(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Archive current reports/agents artifacts."""
    with prepare_archive_transaction(context, fetch=True) as transaction:
        destination_prefix = safe_archive_relative_path(args.destination_prefix)
        summary = copy_agent_reports_prepared(
            transaction,
            report_root=args.report_root,
            destination_prefix=destination_prefix,
            max_file_bytes=args.max_file_bytes,
        )
        stage_archive_paths(transaction)
        print_context(context)
        print_agent_report_archive_summary(summary)
        print("RUNTIME_LOG_ARCHIVE_AGENT_REPORTS=pass")
    return 0


def stage_archive_paths(transaction: PreparedArchiveTransaction) -> None:
    """Stage all AgentCanon-managed log archive families that exist."""
    context = _require_prepared(transaction)
    log_paths = [
        Path("hook-runs") / context.repo_key,
        Path("codex-runtime") / context.repo_key,
        DEFAULT_AGENT_REPORT_DESTINATION / context.repo_key,
        Path("eval-results"),
        Path("legacy-import"),
    ]
    existing = [path.as_posix() for path in log_paths if (context.archive_root / path).exists()]
    if existing:
        git(context.archive_root, ["add", "--", *existing])


def _publication_metadata_hashes(
    context: ArchiveContext,
    commit_oid: str,
    *,
    committed_tree: bool,
) -> tuple[str, str]:
    index_path, cursor_path = _hook_archive_metadata_paths(context)
    if not committed_tree:
        return _worktree_hash(index_path), _worktree_hash(cursor_path)
    index_relative = index_path.relative_to(context.archive_root)
    cursor_relative = cursor_path.relative_to(context.archive_root)
    return (
        _hash_bytes(_archive_blob_at(context, commit_oid, index_relative)),
        _hash_bytes(_archive_blob_at(context, commit_oid, cursor_relative)),
    )


def _remote_ref_oid(context: ArchiveContext) -> str:
    """Read the exact remote branch head without trusting a stale tracking ref."""
    result = git(
        context.archive_root,
        ["ls-remote", "origin", f"refs/heads/{context.branch}"],
        check=False,
    )
    if result.returncode != 0:
        return ""
    line = result.stdout.strip().splitlines()
    return line[0].split("\t", 1)[0] if line else ""


def _verify_remote_archive_readback(
    context: ArchiveContext,
    receipt: ArchivePublicationReceipt,
    required_paths: tuple[Path, ...],
) -> None:
    """Verify remote ref, commit tree, and required archive index/blob bytes."""
    if receipt.status != "committed" or not receipt.pushed:
        raise ArchiveGitError("archive_readback_mismatch:publication_not_committed")
    remote_commit = _remote_ref_oid(context)
    if not remote_commit or remote_commit != receipt.archive_commit_oid:
        raise ArchiveGitError("archive_readback_mismatch:remote_ref")
    remote_tree = _archive_oid(context, f"{remote_commit}^{{tree}}")
    if not remote_tree or remote_tree != receipt.archive_tree_oid:
        raise ArchiveGitError("archive_readback_mismatch:tree")
    for path in required_paths:
        try:
            relative = path.resolve().relative_to(context.archive_root.resolve())
        except ValueError as exc:
            raise ArchiveGitError("archive_readback_mismatch:path") from exc
        if not path.is_file():
            raise ArchiveGitError("archive_readback_mismatch:missing_local_blob")
        local = path.read_bytes()
        remote = _archive_blob_at(context, remote_commit, relative)
        if local != remote:
            raise ArchiveGitError(
                f"archive_readback_mismatch:blob:{relative.as_posix()}"
            )


def _rebase_to_remote(context: ArchiveContext) -> tuple[bool, str]:
    """Rebase local append-only commits onto the fetched remote head."""
    fetched = git(
        context.archive_root,
        ["fetch", "origin", context.branch],
        check=False,
    )
    if fetched.returncode != 0 and _remote_ref_oid(context):
        return False, "fetch_failed"
    remote = _archive_oid(context, f"origin/{context.branch}")
    local = _archive_oid(context, "HEAD")
    if not remote or remote == local:
        return True, "no_rebase_needed"
    rebased = git(
        context.archive_root,
        ["rebase", f"origin/{context.branch}"],
        check=False,
    )
    if rebased.returncode == 0:
        return True, "rebased"
    conflicted = git(
        context.archive_root,
        ["diff", "--name-only", "--diff-filter=U"],
        check=False,
    ).stdout.splitlines()
    if conflicted and all(path.endswith(".jsonl") for path in conflicted):
        for path in conflicted:
            ours = git(context.archive_root, ["show", f":2:{path}"]).stdout
            theirs = git(context.archive_root, ["show", f":3:{path}"]).stdout
            merged = ours.splitlines(keepends=True)
            seen = set(merged)
            for line in theirs.splitlines(keepends=True):
                if line not in seen:
                    merged.append(line)
                    seen.add(line)
            Path(context.archive_root / path).write_text("".join(merged), encoding="utf-8")
            git(context.archive_root, ["add", "--", path])
        continued = run(
            [
                "env",
                "GIT_EDITOR=true",
                "git",
                "-C",
                str(context.archive_root),
                "rebase",
                "--continue",
            ],
            check=False,
        )
        if continued.returncode == 0:
            return True, "rebased_jsonl_union"
    git(context.archive_root, ["rebase", "--abort"], check=False)
    detail = rebased.stderr.strip() or rebased.stdout.strip() or "rebase_failed"
    return False, detail.replace("\n", " ")[:240]


def _compare_and_push(
    transaction: PreparedArchiveTransaction,
    *,
    no_pull: bool,
) -> tuple[bool, bool, str]:
    """Push without force, retrying only after expected-head comparison and rebase."""
    context = _require_prepared(transaction)
    expected = transaction.archive_head_before
    for attempt in range(PUBLICATION_RETRY_LIMIT):
        if attempt:
            rebased, detail = _rebase_to_remote(context)
            if not rebased:
                return False, False, f"conflict:{detail}"
            expected = _remote_ref_oid(context)
        else:
            fetched = git(context.archive_root, ["fetch", "origin", context.branch], check=False)
            if fetched.returncode != 0 and _remote_ref_oid(context):
                return False, False, "fetch_failed"
            observed = _remote_ref_oid(context)
            if observed != expected:
                if no_pull:
                    return False, False, "expected_remote_head_changed"
                rebased, detail = _rebase_to_remote(context)
                if not rebased:
                    return False, False, f"conflict:{detail}"
                expected = _remote_ref_oid(context)
        local = _archive_oid(context, "HEAD")
        if not local:
            return False, False, "local_head_missing"
        pushed = git(
            context.archive_root,
            ["push", "-u", "origin", f"HEAD:refs/heads/{context.branch}"],
            check=False,
        )
        if pushed.returncode == 0:
            readback = _remote_ref_oid(context)
            if readback == local:
                return True, True, "committed"
            return False, False, "remote_readback_mismatch"
        if attempt + 1 < PUBLICATION_RETRY_LIMIT and not no_pull:
            continue
        return False, False, "compare_and_push_conflict"
    return False, False, "retry_limit"


def publish_prepared_archive(
    transaction: PreparedArchiveTransaction,
    args: argparse.Namespace,
) -> ArchivePublicationReceipt:
    """Stage, commit, optionally pull/push, and read back one prepared archive."""
    context = _require_prepared(transaction)
    message = getattr(args, "message", None) or f"Append {context.repo_key} runtime logs"
    no_pull = bool(getattr(args, "no_pull", False))
    no_push = bool(getattr(args, "no_push", False))

    try:
        stage_archive_paths(transaction)
        staged = git(context.archive_root, ["diff", "--cached", "--quiet"], check=False)
    except ArchiveGitError:
        commit_oid = _archive_oid(context, "HEAD")
        tree_oid = _archive_oid(context, f"{commit_oid}^{{tree}}") if commit_oid else ""
        index_sha256, cursor_sha256 = _publication_metadata_hashes(
            context,
            commit_oid,
            committed_tree=False,
        )
        return ArchivePublicationReceipt(
            status="failed",
            commit_created=False,
            pushed=False,
            archive_commit_oid=commit_oid,
            archive_tree_oid=tree_oid,
            dedup_index_sha256=index_sha256,
            cursor_sha256=cursor_sha256,
        )
    if no_push:
        commit_oid = _archive_oid(context, "HEAD")
        tree_oid = _archive_oid(context, f"{commit_oid}^{{tree}}") if commit_oid else ""
        index_sha256, cursor_sha256 = _publication_metadata_hashes(
            context,
            commit_oid,
            committed_tree=False,
        )
        return ArchivePublicationReceipt(
            status="partial_retained",
            commit_created=False,
            pushed=False,
            archive_commit_oid=commit_oid,
            archive_tree_oid=tree_oid,
            dedup_index_sha256=index_sha256,
            cursor_sha256=cursor_sha256,
        )

    commit_created = staged.returncode != 0
    try:
        if commit_created:
            ensure_commit_identity(context)
            git(context.archive_root, ["commit", "-m", message])
    except ArchiveGitError:
        commit_oid = _archive_oid(context, "HEAD")
        tree_oid = _archive_oid(context, f"{commit_oid}^{{tree}}") if commit_oid else ""
        index_sha256, cursor_sha256 = _publication_metadata_hashes(
            context,
            commit_oid,
            committed_tree=True,
        )
        return ArchivePublicationReceipt(
            status="failed",
            commit_created=commit_created,
            pushed=False,
            archive_commit_oid=commit_oid,
            archive_tree_oid=tree_oid,
            dedup_index_sha256=index_sha256,
            cursor_sha256=cursor_sha256,
        )

    commit_oid = _archive_oid(context, "HEAD")
    tree_oid = _archive_oid(context, f"{commit_oid}^{{tree}}") if commit_oid else ""
    index_sha256, cursor_sha256 = _publication_metadata_hashes(
        context,
        commit_oid,
        committed_tree=True,
    )
    pushed, push_succeeded, _push_status = _compare_and_push(
        transaction,
        no_pull=no_pull,
    )
    status = "committed" if pushed and push_succeeded else "uncertain"
    commit_oid = _archive_oid(context, "HEAD")
    tree_oid = _archive_oid(context, f"{commit_oid}^{{tree}}") if commit_oid else ""
    if status == "committed" and (not commit_oid or not tree_oid):
        status = "uncertain"
    return ArchivePublicationReceipt(
        status=status,
        commit_created=commit_created,
        pushed=push_succeeded,
        archive_commit_oid=_archive_oid(context, "HEAD"),
        archive_tree_oid=tree_oid,
        dedup_index_sha256=index_sha256,
        cursor_sha256=cursor_sha256,
        push_status=_push_status,
    )


def command_push(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Commit and push source repo runtime logs."""
    with prepare_archive_transaction(context, fetch=True) as transaction:
        receipt = publish_prepared_archive(transaction, args)
        print_context(context)
        print(f"RUNTIME_LOG_ARCHIVE_COMMITTED={'yes' if receipt.commit_created else 'no'}")
        print(f"RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS={receipt.status}")
        print(f"RUNTIME_LOG_ARCHIVE_PUSH_STATUS={receipt.push_status}")
        print(
            "RUNTIME_LOG_ARCHIVE_PUSH=pass"
            if receipt.status == "committed"
            else f"RUNTIME_LOG_ARCHIVE_PUSH={receipt.status}"
        )
        return 0 if receipt.status == "committed" else 1


def command_sync(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Run the normal unattended archive sync flow."""
    with prepare_archive_transaction(context, fetch=True) as transaction:
        spool_snapshot = snapshot_hook_spool_events(transaction)
        ingest_result = ingest_hook_event_spool(transaction, spool_snapshot)
        print_context(context)
        print(f"RUNTIME_LOG_ARCHIVE_SPOOL_SOURCE_EVENTS={len(spool_snapshot)}")
        print(f"RUNTIME_LOG_ARCHIVE_SPOOL_ACCEPTED={len(ingest_result.accepted_events)}")
        print(f"RUNTIME_LOG_ARCHIVE_SPOOL_DUPLICATES={len(ingest_result.duplicate_events)}")
        if not args.no_agent_reports:
            summary = copy_agent_reports_prepared(
                transaction,
                report_root=args.report_root,
                destination_prefix=DEFAULT_AGENT_REPORT_DESTINATION,
                max_file_bytes=args.max_file_bytes,
            )
            print_agent_report_archive_summary(summary)
        receipt = publish_prepared_archive(transaction, args)
        removed = finalize_hook_spool_readback(transaction, receipt, ingest_result)
        print(f"RUNTIME_LOG_ARCHIVE_SPOOL_FINALIZED={removed}")
        print(f"RUNTIME_LOG_ARCHIVE_COMMITTED={'yes' if receipt.commit_created else 'no'}")
        print(f"RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS={receipt.status}")
        print(f"RUNTIME_LOG_ARCHIVE_PUSH_STATUS={receipt.push_status}")
        if receipt.status == "partial_retained":
            print("RUNTIME_LOG_ARCHIVE_SYNC_PUSH=skipped")
            print("RUNTIME_LOG_ARCHIVE_SYNC=partial_retained")
            return 0
        if receipt.status == "uncertain":
            print("RUNTIME_LOG_ARCHIVE_SYNC=uncertain")
            return 1
        if receipt.status == "failed":
            print("RUNTIME_LOG_ARCHIVE_SYNC=failed")
            return 1
        print("RUNTIME_LOG_ARCHIVE_SYNC=pass")
        return 0


def main(argv: list[str] | None = None) -> int:
    """Run the runtime log archive Git helper."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check-hook-hot-path":
        path = args.path or (args.canon_root / ".codex/hooks/hook_event_log.py")
        return command_check_hook_hot_path(path.resolve())
    try:
        context = build_context(args)
        if args.command == "append-context-discovery":
            return command_append_context_discovery(context, args)
        if args.command == "materialize-runtime-event":
            return command_materialize_runtime_event(context, args)
        if args.command == "repo-key":
            return command_repo_key(context)
        if args.command == "ensure":
            return command_ensure(context, args)
        if args.command == "status":
            return command_status(context, args)
        if args.command == "check-clean":
            return command_check_clean(context, args)
        if args.command == "import-legacy":
            return command_import_legacy(context, args)
        if args.command == "import-eval-results":
            return command_import_eval_results(context, args)
        if args.command == "archive-agent-report":
            return command_archive_agent_report(context, args)
        if args.command == "archive-agent-reports":
            return command_archive_agent_reports(context, args)
        if args.command == "push":
            return command_push(context, args)
        if args.command == "sync":
            return command_sync(context, args)
    except RuntimeEventMaterializationError as exc:
        if args.command == "append-context-discovery":
            print(f"CONTEXT_DISCOVERY_ERROR_CODE={exc.code}")
            print("CONTEXT_DISCOVERY_APPEND=fail")
            return 1
        print(f"RUNTIME_EVENT_ERROR_CODE={exc.code}")
        print("RUNTIME_EVENT_MATERIALIZE=fail")
        return 1
    except ArchiveGitError as exc:
        if args.command == "append-context-discovery":
            print("CONTEXT_DISCOVERY_ERROR_CODE=source_unavailable")
            print("CONTEXT_DISCOVERY_APPEND=fail")
            return 1
        message = str(exc)
        if message.startswith("source_identity_preflight_failed:"):
            print(f"RUNTIME_LOG_ARCHIVE_ERROR_CODE={message.split(':', 1)[1]}")
        print(f"RUNTIME_LOG_ARCHIVE_ERROR={exc}")
        print("RUNTIME_LOG_ARCHIVE=fail")
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
