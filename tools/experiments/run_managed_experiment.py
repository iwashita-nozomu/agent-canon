#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides run managed experiment experiment workflow tooling.
# upstream design ../README.md shared automation index
# @dependency-end

"""Run one experiment while recording canonical server-side run metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

DEFAULT_REQUIRED_EVAL_ARTIFACTS = ("summary.json", "cases.jsonl", "config.json")
CONFIG_SOURCE_SNAPSHOT_NAME = "config_source.yaml"
COMMAND_MANIFEST_NAME = "command.json"
ENVIRONMENT_MANIFEST_NAME = "environment.json"
SOURCE_SNAPSHOT_NAME = "source_snapshot.json"
ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"
STARTUP_LOG_NAME = "startup.jsonl"
STDOUT_LOG_NAME = "stdout.log"
STDERR_LOG_NAME = "stderr.log"
MANAGED_RUN_ARTIFACTS = frozenset(
    {
        "run_manifest.json",
        "eval_manifest.json",
        "run.log",
        CONFIG_SOURCE_SNAPSHOT_NAME,
        COMMAND_MANIFEST_NAME,
        ENVIRONMENT_MANIFEST_NAME,
        SOURCE_SNAPSHOT_NAME,
        ARTIFACT_MANIFEST_NAME,
        f"logs/{STARTUP_LOG_NAME}",
        f"logs/{STDOUT_LOG_NAME}",
        f"logs/{STDERR_LOG_NAME}",
    }
)
FILE_READ_CHUNK_BYTES = 1024 * 1024
STREAM_TERMINATION_TIMEOUT_SECONDS = 10
INTERRUPTED_EXIT_CODE = 130
COMMAND_START_FAILURE_EXIT_CODE = 127
PREFLIGHT_FAILURE_EXIT_CODE = 2
DURATION_ROUND_DIGITS = 3
REGISTERED_COMMAND_KINDS = ("default", "formal")
LEGACY_REGISTERED_COMMAND_ALIASES = {"smoke": "default"}
SENSITIVE_ENV_KEY_PARTS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
EXCLUDED_SOURCE_SNAPSHOT_DIRS = frozenset(
    {
        ".git",
        "result",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


@dataclass(frozen=True)
class RegistryContext:
    """Loaded experiment registry data for one topic."""

    path: Path
    entry: dict[str, object]
    defaults: dict[str, object]
    available: bool


@dataclass(frozen=True)
class RunIdentity:
    """Stable identifiers for one managed experiment run."""

    topic: str
    run_name: str
    variant: str


@dataclass(frozen=True)
class RunPaths:
    """Filesystem paths owned by one managed run."""

    result_dir: Path
    log_dir: Path
    report_path: Path
    manifest_path: Path
    eval_manifest_path: Path
    artifact_manifest_path: Path
    command_manifest_path: Path
    environment_manifest_path: Path
    source_snapshot_path: Path
    config_source_path: Path
    config_path: Path
    log_path: Path
    startup_log_path: Path
    stdout_log_path: Path
    stderr_log_path: Path


@dataclass(frozen=True)
class CommandSelection:
    """Selected inner command and its provenance."""

    command: list[str]
    source: str
    registered_match: str | None


@dataclass(frozen=True)
class GitSnapshot:
    """Git state captured for one run manifest."""

    branch: str | None
    commit: str | None
    status_short: list[str]


@dataclass(frozen=True)
class EvalArtifactPatterns:
    """Validated eval artifact patterns for one run."""

    required: list[str]
    optional: list[str]


@dataclass(frozen=True)
class RunContext:
    """Complete immutable setup context for one managed run."""

    repo_root: Path
    identity: RunIdentity
    topic_dir: Path
    paths: RunPaths
    registry: RegistryContext
    command: CommandSelection
    created_at: str
    git: GitSnapshot


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[2]


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_timestamp() -> str:
    """Return the compact timestamp used for run names."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create one managed experiment run directory with manifests, "
            "source/config snapshots, split logs, and an optional report stub."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_from_script()),
        help="Repository root. Defaults to the path inferred from this script.",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Experiment topic name under experiments/.",
    )
    parser.add_argument(
        "--run-name",
        help="Explicit run name. Defaults to <topic>_<variant>_<timestamp>.",
    )
    parser.add_argument(
        "--variant",
        default="formal",
        help="Variant label used when --run-name is omitted.",
    )
    parser.add_argument(
        "--registry",
        help=(
            "Optional registry path. Defaults to <repo-root>/experiments/registry.toml "
            "when present."
        ),
    )
    parser.add_argument(
        "--use-registered-command",
        help="Execute a registered inner command from experiments/registry.toml for this topic.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional report path. Defaults to experiments/report/<run_name>.md.",
    )
    parser.add_argument(
        "--skip-report-init",
        action="store_true",
        help="Do not create a report stub when the report file is absent.",
    )
    parser.add_argument(
        "--config-json",
        help=(
            "Optional JSON object file to merge into result/<run_name>/config.json. "
            "The file must decode to a dictionary."
        ),
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help=(
            "Add one JSON-encoded config value to result/<run_name>/config.json. "
            "Example: --config seed=0 --config enabled=true."
        ),
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=(
            "Command to run. Tokens may use {run_dir}, {run_name}, {report_path}, "
            "{manifest_path}, {eval_manifest_path}, {config_path}, "
            "{config_source_path}, {startup_log_path}, {stdout_log_path}, "
            "or {stderr_log_path}."
        ),
    )
    return parser.parse_args()


def load_registry(path: Path) -> dict[str, object]:
    """Load one experiment registry TOML file."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("experiment registry TOML root must be a table")
    return data


def string_list(raw_value: object, key: str) -> list[str]:
    """Return one normalized non-empty string list."""
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise ValueError(f"{key} must be an array of strings")
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key}[{index}] must be a non-empty string")
    return [item.strip() for item in raw_value]


def find_registry_topic(
    registry: dict[str, object], topic_name: str
) -> dict[str, object] | None:
    """Return one topic entry from the registry."""
    raw_topics = registry.get("topics", [])
    if not isinstance(raw_topics, list):
        raise ValueError("experiment registry must contain [[topics]]")
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            continue
        name = raw_topic.get("name")
        if name == topic_name:
            return raw_topic
    return None


def resolve_registry_path(repo_root: Path, registry_arg: str) -> Path:
    """Resolve the registry path requested by the CLI."""
    if registry_arg:
        return Path(registry_arg).resolve()
    return repo_root / "experiments" / "registry.toml"


def load_registry_context(registry_path: Path, topic_name: str) -> RegistryContext:
    """Load one topic registry context when the registry exists."""
    if not registry_path.is_file():
        return RegistryContext(
            path=registry_path,
            entry={},
            defaults={},
            available=False,
        )
    registry = load_registry(registry_path)
    entry = find_registry_topic(registry, topic_name)
    if entry is None:
        raise ValueError(f"topic {topic_name!r} is missing from {registry_path}")
    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("experiment registry defaults must be a table")
    return RegistryContext(
        path=registry_path,
        entry=entry,
        defaults=defaults,
        available=True,
    )


def load_command_version(name: str) -> str | None:
    """Return one-line version text for a command when available."""
    if shutil.which(name) is None:
        return None
    result = subprocess.run(
        [name, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if not output:
        return None
    return output.splitlines()[0]


def load_config_json(path: Path) -> dict[str, object]:
    """Load one experiment config JSON object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"--config-json must decode to a JSON object: {path}")
    config: dict[str, object] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"--config-json contains an invalid key: {key!r}")
        config[key] = value
    return config


def parse_config_pairs(pairs: list[str]) -> dict[str, object]:
    """Parse repeated KEY=JSON config arguments."""
    config: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--config must use KEY=JSON form: {pair}")
        key, raw_value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--config has an empty key: {pair}")
        try:
            config[key] = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"--config value for {key!r} is not valid JSON: {exc}"
            ) from exc
    return config


def build_registry_config_snapshot(registry: RegistryContext) -> dict[str, object]:
    """Build the registry fragment embedded in run config."""
    if not registry.available:
        return {}
    return {
        "name": registry.entry.get("name"),
        "canonical_entrypoint": registry.entry.get("canonical_entrypoint"),
        "default_variant": registry.entry.get("default_variant"),
        "default_inner_command": registry.entry.get("default_inner_command")
        or registry.entry.get("smoke_inner_command"),
        "formal_inner_command": registry.entry.get("formal_inner_command"),
    }


def build_run_config(
    context: RunContext, explicit_config: dict[str, object]
) -> dict[str, object]:
    """Build one JSON-serializable experiment run configuration dictionary."""
    run_config: dict[str, object] = {
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "variant": context.identity.variant,
        "paths": {
            "result_dir": str(context.paths.result_dir),
            "log_dir": str(context.paths.log_dir),
            "report_path": str(context.paths.report_path),
            "run_manifest": str(context.paths.manifest_path),
            "eval_manifest": str(context.paths.eval_manifest_path),
            "artifact_manifest": str(context.paths.artifact_manifest_path),
            "command_manifest": str(context.paths.command_manifest_path),
            "environment_manifest": str(context.paths.environment_manifest_path),
            "source_snapshot": str(context.paths.source_snapshot_path),
            "source_config": str(context.paths.config_source_path),
            "config": str(context.paths.config_path),
            "startup_log": str(context.paths.startup_log_path),
            "stdout_log": str(context.paths.stdout_log_path),
            "stderr_log": str(context.paths.stderr_log_path),
        },
        "command": context.command.command,
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "config": explicit_config,
    }
    registry_config = build_registry_config_snapshot(context.registry)
    if registry_config:
        run_config["registry"] = registry_config
    return run_config


def git_value(repo_root: Path, *args: str) -> str | None:
    """Return one git value or None when unavailable."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def load_git_snapshot(repo_root: Path) -> GitSnapshot:
    """Load the git state recorded in run artifacts."""
    git_dirty = git_value(repo_root, "status", "--short")
    return GitSnapshot(
        branch=git_value(repo_root, "branch", "--show-current"),
        commit=git_value(repo_root, "rev-parse", "HEAD"),
        status_short=git_dirty.splitlines() if git_dirty else [],
    )


def registry_path_text(registry: RegistryContext) -> str:
    """Return the display registry path for reports."""
    if registry.available:
        return str(registry.path)
    return "(none)"


def render_report_stub(context: RunContext) -> str:
    """Render one initial run report."""
    command_text = (
        shlex.join(context.command.command)
        if context.command.command
        else "(no command)"
    )
    branch_text = context.git.branch or "(unknown)"
    commit_text = context.git.commit or "(unknown)"
    return f"""# {context.identity.run_name}

- Topic: {context.identity.topic}
- Created At (UTC): {context.created_at}
- Result Dir: {context.paths.result_dir}
- Log Dir: {context.paths.log_dir}
- Run Manifest: {context.paths.manifest_path}
- Eval Manifest: {context.paths.eval_manifest_path}
- Artifact Manifest: {context.paths.artifact_manifest_path}
- Config: {context.paths.config_path}
- Source Config Snapshot: {context.paths.config_source_path}
- Registry: {registry_path_text(context.registry)}
- Branch: {branch_text}
- Commit: {commit_text}

## Question

<!-- What empirical question does this run answer? -->

## Comparison Target

<!-- main, baseline, previous run, or external reference. -->

## Protocol

- Command: `{command_text}`
- Report Path: `{context.paths.report_path}`

## Results

<!-- Fill in summary.json, cases.jsonl, and the main observations after the run. -->

## Reproducibility Record

- `run_manifest.json`
- `config.json`
- `config_source.yaml`
- `eval_manifest.json`
- `artifact_manifest.json`
- `command.json`
- `environment.json`
- `source_snapshot.json`
- `run.log`
- `logs/`
- `logs/startup.jsonl`
- `logs/stdout.log`
- `logs/stderr.log`
- `summary.json`
- `cases.jsonl`

## Critical Review Notes

<!-- What this run still does not justify. -->
"""


def build_manifest(context: RunContext, status: str) -> dict[str, object]:
    """Build one manifest dictionary."""
    manifest: dict[str, object] = {
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "status": status,
        "created_at_utc": context.created_at,
        "repo_root": str(context.repo_root),
        "topic_dir": str(context.topic_dir),
        "result_dir": str(context.paths.result_dir),
        "log_dir": str(context.paths.log_dir),
        "report_path": str(context.paths.report_path),
        "manifest_path": str(context.paths.manifest_path),
        "eval_manifest_path": str(context.paths.eval_manifest_path),
        "artifact_manifest_path": str(context.paths.artifact_manifest_path),
        "command_manifest_path": str(context.paths.command_manifest_path),
        "environment_manifest_path": str(context.paths.environment_manifest_path),
        "source_snapshot_path": str(context.paths.source_snapshot_path),
        "config_source_path": str(context.paths.config_source_path),
        "startup_log_path": str(context.paths.startup_log_path),
        "stdout_log_path": str(context.paths.stdout_log_path),
        "stderr_log_path": str(context.paths.stderr_log_path),
        "command": context.command.command,
        "server_context": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME") or "(unknown)",
        },
        "tool_versions": {
            "python": platform.python_version(),
            "codex": load_command_version("codex"),
            "docker": load_command_version("docker"),
        },
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "git": {
            "branch": context.git.branch,
            "commit": context.git.commit,
            "dirty": bool(context.git.status_short),
            "status_short": context.git.status_short,
        },
    }
    if context.registry.available:
        registry_snapshot = dict(context.registry.entry)
        registry_snapshot["registry_path"] = str(context.registry.path)
        manifest["registry"] = registry_snapshot
    return manifest


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write one JSON object with canonical formatting."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Write one manifest JSON file."""
    write_json(path, manifest)


def env_key_is_sensitive(key: str) -> bool:
    """Return whether an environment variable name likely contains a secret."""
    key_upper = key.upper()
    return any(part in key_upper for part in SENSITIVE_ENV_KEY_PARTS)


def captured_environment(env: dict[str, str]) -> dict[str, object]:
    """Return a redacted environment snapshot for reproducibility."""
    values: dict[str, object] = {}
    redacted_keys: list[str] = []
    for key in sorted(env):
        if env_key_is_sensitive(key):
            values[key] = {"present": True, "redacted": True}
            redacted_keys.append(key)
        else:
            values[key] = env[key]
    return {
        "captured_at_utc": utc_now(),
        "policy": "full_environment_with_key_secret_redaction",
        "key_count": len(values),
        "redacted_keys": redacted_keys,
        "values": values,
    }


def file_record(path: Path, base: Path) -> dict[str, object]:
    """Return stable metadata for one file."""
    relative_path = str(path.relative_to(base))
    return {
        "relative_path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
    }


def path_is_relative_to(path: Path, base: Path) -> bool:
    """Return whether path is inside base."""
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def external_file_record(path: Path) -> dict[str, object]:
    """Return stable metadata for one source file outside the repo root."""
    return {
        "absolute_path": str(path),
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
    }


def source_snapshot_candidate_files(path: Path) -> list[Path]:
    """Return source snapshot files under one path."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    files: list[Path] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        relative_parts = child.relative_to(path).parts
        if any(part in EXCLUDED_SOURCE_SNAPSHOT_DIRS for part in relative_parts):
            continue
        files.append(child)
    return files


def git_status_path_text(status_line: str) -> str:
    """Return the path portion from one git status --short line."""
    raw_path = status_line[3:].strip()
    if " -> " in raw_path:
        raw_path = raw_path.rsplit(" -> ", 1)[1]
    return raw_path.strip('"')


def dirty_source_files(repo_root: Path, status_short: list[str]) -> tuple[list[Path], list[str]]:
    """Return existing dirty files plus dirty entries without a readable file."""
    files: list[Path] = []
    missing_paths: list[str] = []
    for status_line in status_short:
        path_text = git_status_path_text(status_line)
        if not path_text:
            continue
        candidate = repo_root / path_text
        candidate_files = source_snapshot_candidate_files(candidate)
        if candidate_files:
            files.extend(candidate_files)
        else:
            missing_paths.append(path_text)
    return files, missing_paths


def command_source_files(command: list[str], repo_root: Path) -> list[Path]:
    """Return local source files referenced directly by a command."""
    files: list[Path] = []
    for token in command:
        candidate = Path(token)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.is_file():
            files.append(candidate.resolve())
    return files


def unique_paths(paths: list[Path]) -> list[Path]:
    """Return stable unique paths."""
    return sorted(dict.fromkeys(path.resolve() for path in paths), key=lambda path: str(path))


def build_source_snapshot(context: RunContext) -> dict[str, object]:
    """Build the source-file digest snapshot for one managed run."""
    files = source_snapshot_candidate_files(context.topic_dir)
    if context.registry.available and context.registry.path.is_file():
        files.append(context.registry.path)
    files.extend(command_source_files(context.command.command, context.repo_root))
    dirty_files, missing_dirty_paths = dirty_source_files(
        context.repo_root,
        context.git.status_short,
    )
    files.extend(dirty_files)
    runner_path = Path(__file__).resolve()
    if path_is_relative_to(runner_path, context.repo_root):
        files.append(runner_path)
        external_files: list[Path] = []
    else:
        external_files = [runner_path]
    unique_files = unique_paths(files)
    repo_files = [
        path for path in unique_files if path_is_relative_to(path, context.repo_root)
    ]
    external_records = [
        external_file_record(path) for path in unique_paths(external_files)
    ]
    return {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "base_dir": str(context.repo_root),
        "excluded_topic_dirs": sorted(EXCLUDED_SOURCE_SNAPSHOT_DIRS),
        "git": {
            "branch": context.git.branch,
            "commit": context.git.commit,
            "dirty": bool(context.git.status_short),
            "status_short": context.git.status_short,
            "missing_dirty_paths": missing_dirty_paths,
        },
        "command_source_files": [
            str(path.relative_to(context.repo_root))
            for path in command_source_files(context.command.command, context.repo_root)
            if path_is_relative_to(path, context.repo_root)
        ],
        "dirty_file_count": len(dirty_files),
        "file_count": len(repo_files),
        "external_file_count": len(external_records),
        "files": [file_record(path, context.repo_root) for path in repo_files],
        "external_files": external_records,
    }


def copy_source_config_snapshot(context: RunContext) -> dict[str, object]:
    """Copy the checked-in topic config into the run directory."""
    source_config = context.topic_dir / "config.yaml"
    if not source_config.is_file():
        return {
            "status": "missing",
            "source_path": str(source_config),
            "snapshot_path": str(context.paths.config_source_path),
        }
    shutil.copy2(source_config, context.paths.config_source_path)
    return {
        "status": "copied",
        "source_path": str(source_config),
        "snapshot_path": str(context.paths.config_source_path),
        "sha256": load_file_sha256(context.paths.config_source_path),
        "bytes": context.paths.config_source_path.stat().st_size,
    }


def build_command_manifest(context: RunContext) -> dict[str, object]:
    """Build the resolved-command manifest for one run."""
    return {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "command": context.command.command,
        "command_text": shlex.join(context.command.command),
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "cwd": str(context.repo_root),
        "paths": {
            "result_dir": str(context.paths.result_dir),
            "log_dir": str(context.paths.log_dir),
            "run_log": str(context.paths.log_path),
            "stdout_log": str(context.paths.stdout_log_path),
            "stderr_log": str(context.paths.stderr_log_path),
            "startup_log": str(context.paths.startup_log_path),
        },
    }


def append_startup_event(
    context: RunContext,
    event: str,
    payload: dict[str, object],
) -> None:
    """Append one startup chronology event."""
    context.paths.startup_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry: dict[str, object] = {
        "timestamp_utc": utc_now(),
        "event": event,
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
    }
    entry.update(payload)
    with context.paths.startup_log_path.open("a", encoding="utf-8") as handle:
        json.dump(entry, handle, sort_keys=True, ensure_ascii=True)
        handle.write("\n")


def build_artifact_manifest(context: RunContext) -> dict[str, object]:
    """Build a digest inventory for all current run artifacts."""
    files = [
        path
        for path in sorted(context.paths.result_dir.rglob("*"))
        if path.is_file() and path != context.paths.artifact_manifest_path
    ]
    return {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "result_dir": str(context.paths.result_dir),
        "self_excluded": str(context.paths.artifact_manifest_path),
        "artifact_count": len(files),
        "artifacts": [file_record(path, context.paths.result_dir) for path in files],
    }


def merge_unique_strings(*groups: list[str]) -> list[str]:
    """Return one deduplicated list preserving first appearance order."""
    return list(dict.fromkeys(value for group in groups for value in group))


def validate_eval_artifact_patterns(patterns: list[str], key: str) -> list[str]:
    """Validate one eval artifact pattern list."""
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            raise ValueError(
                f"{key} must stay relative to result/<run_name>: {pattern}"
            )
        if ".." in pattern_path.parts:
            raise ValueError(f"{key} must not escape result/<run_name>: {pattern}")
    return patterns


def resolve_eval_artifact_patterns(
    registry_defaults: dict[str, object],
    registry_entry: dict[str, object],
) -> EvalArtifactPatterns:
    """Return required and optional eval artifact patterns for one run."""
    default_required = string_list(
        registry_defaults.get("required_eval_artifacts"),
        "defaults.required_eval_artifacts",
    )
    default_optional = string_list(
        registry_defaults.get("optional_eval_artifacts"),
        "defaults.optional_eval_artifacts",
    )
    entry_required = string_list(
        registry_entry.get("required_eval_artifacts"),
        "topics.required_eval_artifacts",
    )
    entry_optional = string_list(
        registry_entry.get("optional_eval_artifacts"),
        "topics.optional_eval_artifacts",
    )
    required = merge_unique_strings(
        list(DEFAULT_REQUIRED_EVAL_ARTIFACTS),
        default_required,
        entry_required,
    )
    optional = merge_unique_strings(default_optional, entry_optional)
    optional = [pattern for pattern in optional if pattern not in required]
    return EvalArtifactPatterns(
        required=validate_eval_artifact_patterns(required, "required_eval_artifacts"),
        optional=validate_eval_artifact_patterns(optional, "optional_eval_artifacts"),
    )


def load_file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def artifact_kind(path: Path) -> str:
    """Infer one artifact kind from the file suffix."""
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".log", ".md"}:
        return "text"
    if suffix in {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".html"}:
        return "rendered"
    return "file"


def load_line_count(path: Path) -> int:
    """Return the number of lines in one file without assuming UTF-8 text."""
    count = 0
    saw_bytes = False
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_READ_CHUNK_BYTES)
            if not chunk:
                break
            saw_bytes = True
            last_byte = chunk[-1:]
            count += chunk.count(b"\n")
    if saw_bytes and last_byte != b"\n":
        count += 1
    return count


def is_managed_run_artifact(path: Path, result_dir: Path) -> bool:
    """Return whether one path is a reserved managed artifact."""
    return str(path.relative_to(result_dir)) in MANAGED_RUN_ARTIFACTS


def load_eval_artifact(
    path: Path, result_dir: Path, patterns: list[str]
) -> dict[str, object]:
    """Load eval artifact metadata for one collected file."""
    artifact: dict[str, object] = {
        "relative_path": str(path.relative_to(result_dir)),
        "kind": artifact_kind(path),
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
        "matched_patterns": patterns,
    }
    if artifact["kind"] in {"jsonl", "text", "csv"}:
        artifact["line_count"] = load_line_count(path)
    return artifact


def load_eval_artifacts(
    result_dir: Path,
    *,
    topic: str,
    run_name: str,
    patterns: EvalArtifactPatterns,
) -> dict[str, object]:
    """Collect eval artifact metadata from one result directory."""
    matched_patterns_by_path: dict[Path, list[str]] = {}
    missing_required_patterns: list[str] = []

    for pattern in patterns.required:
        matches = sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        )
        if not matches:
            missing_required_patterns.append(pattern)
            continue
        for match in matches:
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    for pattern in patterns.optional:
        for match in sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        ):
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    artifacts: list[dict[str, object]] = []
    for path in sorted(
        matched_patterns_by_path,
        key=lambda item: str(item.relative_to(result_dir)),
    ):
        artifacts.append(
            load_eval_artifact(path, result_dir, matched_patterns_by_path[path])
        )

    return {
        "topic": topic,
        "run_name": run_name,
        "result_dir": str(result_dir),
        "collected_at_utc": utc_now(),
        "required_patterns": patterns.required,
        "optional_patterns": patterns.optional,
        "missing_required_patterns": missing_required_patterns,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def format_command(command: list[str], placeholders: dict[str, str]) -> list[str]:
    """Format command tokens with run placeholders."""
    if command and command[0] == "--":
        command = command[1:]
    return [token.format(**placeholders) for token in command]


def normalize_registered_command_kind(command_kind: str) -> str:
    """Return the canonical registered command kind."""
    normalized = LEGACY_REGISTERED_COMMAND_ALIASES.get(command_kind, command_kind)
    if normalized not in REGISTERED_COMMAND_KINDS:
        allowed = ", ".join(REGISTERED_COMMAND_KINDS)
        raise ValueError(f"unsupported registered command {command_kind!r}; expected {allowed}")
    return normalized


def registered_command_keys(command_kind: str) -> tuple[str, ...]:
    """Return preferred registry keys for one command kind."""
    normalized = normalize_registered_command_kind(command_kind)
    keys = [f"{normalized}_inner_command"]
    if normalized == "default":
        keys.append("smoke_inner_command")
    return tuple(keys)


def command_from_registry(
    registry_entry: dict[str, object],
    command_kind: str,
    placeholders: dict[str, str],
) -> list[str]:
    """Return one formatted command from the registry."""
    checked_keys = registered_command_keys(command_kind)
    raw_command: str | None = None
    for command_key in checked_keys:
        raw_value = registry_entry.get(command_key)
        if isinstance(raw_value, str) and raw_value.strip():
            raw_command = raw_value
            break
    else:
        raise ValueError(f"registry entry is missing one of {', '.join(checked_keys)}")
    assert raw_command is not None
    return [token.format(**placeholders) for token in shlex.split(raw_command)]


def resolve_registered_command_match(
    registry: RegistryContext, command: list[str], placeholders: dict[str, str]
) -> str | None:
    """Return the matching registered command kind when one exists."""
    if not registry.available:
        return None
    for command_kind in REGISTERED_COMMAND_KINDS:
        try:
            registered_command = command_from_registry(
                registry.entry, command_kind, placeholders
            )
        except ValueError:
            continue
        if registered_command == command:
            return command_kind
    return None


def mirror_stream(
    stream: TextIO,
    *,
    console: TextIO,
    side_log: TextIO,
    combined_log: TextIO,
    combined_lock: threading.Lock,
    label: str,
) -> None:
    """Copy one child-process stream to console and log files."""
    for line in stream:
        console.write(line)
        console.flush()
        side_log.write(line)
        side_log.flush()
        with combined_lock:
            combined_log.write(f"[{label}] {line}")
            combined_log.flush()


def run_streamed_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> int:
    """Run one command, teeing stdout and stderr to durable log files."""
    with (
        log_path.open("w", encoding="utf-8") as log_handle,
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        command_line = "$ " + shlex.join(command) + "\n"
        log_handle.write(command_line)
        stdout_handle.write(command_line)
        stderr_handle.write(command_line)
        log_handle.flush()
        stdout_handle.flush()
        stderr_handle.flush()

        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            message = f"command_start_error={type(exc).__name__}: {exc}\n"
            sys.stderr.write(message)
            log_handle.write("[stderr] " + message)
            stderr_handle.write(message)
            return COMMAND_START_FAILURE_EXIT_CODE

        assert process.stdout is not None
        assert process.stderr is not None
        combined_lock = threading.Lock()
        stdout_thread = threading.Thread(
            target=mirror_stream,
            kwargs={
                "stream": process.stdout,
                "console": sys.stdout,
                "side_log": stdout_handle,
                "combined_log": log_handle,
                "combined_lock": combined_lock,
                "label": "stdout",
            },
        )
        stderr_thread = threading.Thread(
            target=mirror_stream,
            kwargs={
                "stream": process.stderr,
                "console": sys.stderr,
                "side_log": stderr_handle,
                "combined_log": log_handle,
                "combined_lock": combined_lock,
                "label": "stderr",
            },
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            exit_code = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                exit_code = process.wait(timeout=STREAM_TERMINATION_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                exit_code = INTERRUPTED_EXIT_CODE
        stdout_thread.join(timeout=STREAM_TERMINATION_TIMEOUT_SECONDS)
        stderr_thread.join(timeout=STREAM_TERMINATION_TIMEOUT_SECONDS)
        return exit_code


def resolve_topic_dir(
    repo_root: Path, identity: RunIdentity, registry: RegistryContext
) -> Path:
    """Resolve the experiment topic directory."""
    if registry.available:
        topic_dir_raw = registry.entry.get("topic_dir")
        if not isinstance(topic_dir_raw, str):
            raise ValueError(
                f"registry entry for {identity.topic!r} is missing topic_dir"
            )
        return repo_root / topic_dir_raw
    return repo_root / "experiments" / identity.topic


def resolve_report_path(
    repo_root: Path, registry: RegistryContext, run_name: str, report_arg: str
) -> Path:
    """Resolve the report path for one run."""
    if report_arg:
        return Path(report_arg).resolve()
    if registry.available:
        registry_report_root = registry.entry.get(
            "report_root"
        ) or registry.defaults.get("report_root")
        if isinstance(registry_report_root, str):
            return (repo_root / registry_report_root / f"{run_name}.md").resolve()
    return (repo_root / "experiments" / "report" / f"{run_name}.md").resolve()


def build_run_paths(topic_dir: Path, run_name: str, report_path: Path) -> RunPaths:
    """Build filesystem paths owned by one run."""
    result_dir = topic_dir / "result" / run_name
    log_dir = result_dir / "logs"
    return RunPaths(
        result_dir=result_dir,
        log_dir=log_dir,
        report_path=report_path,
        manifest_path=result_dir / "run_manifest.json",
        eval_manifest_path=result_dir / "eval_manifest.json",
        artifact_manifest_path=result_dir / ARTIFACT_MANIFEST_NAME,
        command_manifest_path=result_dir / COMMAND_MANIFEST_NAME,
        environment_manifest_path=result_dir / ENVIRONMENT_MANIFEST_NAME,
        source_snapshot_path=result_dir / SOURCE_SNAPSHOT_NAME,
        config_source_path=result_dir / CONFIG_SOURCE_SNAPSHOT_NAME,
        config_path=result_dir / "config.json",
        log_path=result_dir / "run.log",
        startup_log_path=log_dir / STARTUP_LOG_NAME,
        stdout_log_path=log_dir / STDOUT_LOG_NAME,
        stderr_log_path=log_dir / STDERR_LOG_NAME,
    )


def build_placeholders(
    repo_root: Path, identity: RunIdentity, topic_dir: Path, paths: RunPaths
) -> dict[str, str]:
    """Build command placeholder values for one run."""
    return {
        "repo_root": str(repo_root),
        "topic_dir": str(topic_dir),
        "run_name": identity.run_name,
        "run_dir": str(paths.result_dir),
        "log_dir": str(paths.log_dir),
        "report_path": str(paths.report_path),
        "manifest_path": str(paths.manifest_path),
        "eval_manifest_path": str(paths.eval_manifest_path),
        "artifact_manifest_path": str(paths.artifact_manifest_path),
        "command_manifest_path": str(paths.command_manifest_path),
        "environment_manifest_path": str(paths.environment_manifest_path),
        "source_snapshot_path": str(paths.source_snapshot_path),
        "config_source_path": str(paths.config_source_path),
        "config_path": str(paths.config_path),
        "log_path": str(paths.log_path),
        "startup_log_path": str(paths.startup_log_path),
        "stdout_log_path": str(paths.stdout_log_path),
        "stderr_log_path": str(paths.stderr_log_path),
    }


def load_explicit_config(
    config_json_path: str, config_pairs: list[str]
) -> dict[str, object]:
    """Load explicit CLI config values."""
    explicit_config: dict[str, object] = {}
    if config_json_path:
        explicit_config.update(load_config_json(Path(config_json_path).resolve()))
    explicit_config.update(parse_config_pairs(config_pairs))
    return explicit_config


def select_command(
    use_registered_command: str,
    manual_command: list[str],
    registry: RegistryContext,
    placeholders: dict[str, str],
) -> CommandSelection:
    """Select the inner command for one managed run."""
    if use_registered_command and manual_command:
        raise ValueError(
            "do not pass both a manual command and --use-registered-command"
        )
    if use_registered_command:
        if not registry.available:
            raise ValueError(
                "--use-registered-command requires experiments/registry.toml"
            )
        registered_kind = normalize_registered_command_kind(use_registered_command)
        command = command_from_registry(
            registry.entry, registered_kind, placeholders
        )
        return CommandSelection(
            command=command,
            source=f"registered:{registered_kind}",
            registered_match=registered_kind,
        )
    command = format_command(manual_command, placeholders)
    return CommandSelection(
        command=command,
        source="manual",
        registered_match=resolve_registered_command_match(
            registry, command, placeholders
        ),
    )


def build_run_context(args: argparse.Namespace) -> RunContext:
    """Build setup context for one managed run."""
    repo_root = Path(args.repo_root).resolve()
    identity = RunIdentity(
        topic=args.topic,
        run_name=args.run_name or f"{args.topic}_{args.variant}_{compact_timestamp()}",
        variant=args.variant,
    )
    registry = load_registry_context(
        resolve_registry_path(repo_root, args.registry or ""),
        identity.topic,
    )
    topic_dir = resolve_topic_dir(repo_root, identity, registry)
    if not topic_dir.is_dir():
        raise ValueError(f"topic directory does not exist: {topic_dir}")
    report_path = resolve_report_path(
        repo_root,
        registry,
        identity.run_name,
        args.report_path or "",
    )
    paths = build_run_paths(topic_dir, identity.run_name, report_path)
    placeholders = build_placeholders(repo_root, identity, topic_dir, paths)
    command = select_command(
        args.use_registered_command or "",
        args.command,
        registry,
        placeholders,
    )
    return RunContext(
        repo_root=repo_root,
        identity=identity,
        topic_dir=topic_dir,
        paths=paths,
        registry=registry,
        command=command,
        created_at=utc_now(),
        git=load_git_snapshot(repo_root),
    )


def write_initial_artifacts(
    context: RunContext,
    manifest: dict[str, object],
    run_config: dict[str, object],
    skip_report_init: bool,
) -> dict[str, object]:
    """Write run directories, initial JSON files, and optional report stub."""
    context.paths.result_dir.mkdir(parents=True, exist_ok=True)
    context.paths.log_dir.mkdir(parents=True, exist_ok=True)
    context.paths.report_path.parent.mkdir(parents=True, exist_ok=True)
    source_config = copy_source_config_snapshot(context)
    run_config["source_config"] = source_config
    manifest["source_config"] = source_config
    write_json(context.paths.config_path, run_config)
    write_json(context.paths.command_manifest_path, build_command_manifest(context))
    write_json(
        context.paths.environment_manifest_path,
        captured_environment(build_run_environment(context)),
    )
    write_json(context.paths.source_snapshot_path, build_source_snapshot(context))
    write_manifest(context.paths.manifest_path, manifest)
    append_startup_event(
        context,
        "initialized",
        {
            "result_dir": str(context.paths.result_dir),
            "command_manifest": str(context.paths.command_manifest_path),
            "environment_manifest": str(context.paths.environment_manifest_path),
            "source_snapshot": str(context.paths.source_snapshot_path),
        },
    )

    if not skip_report_init and not context.paths.report_path.exists():
        context.paths.report_path.write_text(
            render_report_stub(context),
            encoding="utf-8",
        )
    return source_config


def source_config_error(source_config: dict[str, object]) -> str | None:
    """Return a preflight error when the checked-in config snapshot is missing."""
    if source_config.get("status") == "copied":
        return None
    return (
        "missing required source config.yaml: "
        f"{source_config.get('source_path')}; create the checked-in topic config "
        "before running a managed experiment"
    )


def build_run_environment(context: RunContext) -> dict[str, str]:
    """Build the environment for the inner experiment command."""
    env = dict(os.environ)
    env.update(
        {
            "EXPERIMENT_RUN_NAME": context.identity.run_name,
            "EXPERIMENT_TOPIC": context.identity.topic,
            "EXPERIMENT_RUN_DIR": str(context.paths.result_dir),
            "EXPERIMENT_LOG_DIR": str(context.paths.log_dir),
            "EXPERIMENT_REPORT_PATH": str(context.paths.report_path),
            "EXPERIMENT_RUN_MANIFEST": str(context.paths.manifest_path),
            "EXPERIMENT_EVAL_MANIFEST": str(context.paths.eval_manifest_path),
            "EXPERIMENT_ARTIFACT_MANIFEST": str(context.paths.artifact_manifest_path),
            "EXPERIMENT_COMMAND_MANIFEST": str(context.paths.command_manifest_path),
            "EXPERIMENT_CONFIG_PATH": str(context.paths.config_path),
            "EXPERIMENT_SOURCE_CONFIG_PATH": str(context.paths.config_source_path),
            "EXPERIMENT_SOURCE_SNAPSHOT": str(context.paths.source_snapshot_path),
            "EXPERIMENT_RUN_LOG": str(context.paths.log_path),
            "EXPERIMENT_STARTUP_LOG": str(context.paths.startup_log_path),
            "EXPERIMENT_STDOUT_LOG": str(context.paths.stdout_log_path),
            "EXPERIMENT_STDERR_LOG": str(context.paths.stderr_log_path),
        }
    )
    return env


def finalize_run_manifest(
    context: RunContext,
    manifest: dict[str, object],
    start_monotonic: float,
    exit_code: int,
    patterns: EvalArtifactPatterns,
) -> None:
    """Collect eval artifacts and write the final run manifest."""
    eval_collection = load_eval_artifacts(
        context.paths.result_dir,
        topic=context.identity.topic,
        run_name=context.identity.run_name,
        patterns=patterns,
    )
    write_json(context.paths.eval_manifest_path, eval_collection)
    manifest["finished_at_utc"] = utc_now()
    manifest["duration_seconds"] = round(
        time.monotonic() - start_monotonic, DURATION_ROUND_DIGITS
    )
    manifest["exit_code"] = exit_code
    manifest["status"] = "completed" if exit_code == 0 else "failed"
    manifest["eval_artifacts"] = {
        "eval_manifest_path": str(context.paths.eval_manifest_path),
        "required_patterns": patterns.required,
        "optional_patterns": patterns.optional,
        "collected_artifact_count": eval_collection["artifact_count"],
        "missing_required_patterns": eval_collection["missing_required_patterns"],
    }
    manifest["artifact_manifest"] = {
        "artifact_manifest_path": str(context.paths.artifact_manifest_path),
        "self_excluded": True,
    }
    write_manifest(context.paths.manifest_path, manifest)
    write_json(context.paths.artifact_manifest_path, build_artifact_manifest(context))


def run_cli(args: argparse.Namespace) -> int:
    """Run one managed experiment from parsed CLI args."""
    context = build_run_context(args)
    patterns = resolve_eval_artifact_patterns(
        context.registry.defaults,
        context.registry.entry,
    )
    explicit_config = load_explicit_config(args.config_json or "", args.config)

    if not context.command.command:
        raise ValueError("a command is required")

    manifest = build_manifest(context, "running")
    run_config = build_run_config(context, explicit_config)
    manifest["config_path"] = str(context.paths.config_path)
    manifest["config"] = run_config
    start_monotonic = time.monotonic()
    source_config = write_initial_artifacts(
        context,
        manifest,
        run_config,
        args.skip_report_init,
    )
    preflight_error = source_config_error(source_config)
    if preflight_error:
        print(preflight_error, file=sys.stderr)
        manifest["preflight_error"] = {
            "kind": "missing_source_config",
            "message": preflight_error,
        }
        append_startup_event(
            context,
            "preflight_failed",
            {
                "exit_code": PREFLIGHT_FAILURE_EXIT_CODE,
                "message": preflight_error,
            },
        )
        finalize_run_manifest(
            context,
            manifest,
            start_monotonic,
            PREFLIGHT_FAILURE_EXIT_CODE,
            patterns,
        )
        return PREFLIGHT_FAILURE_EXIT_CODE

    append_startup_event(
        context,
        "command_start",
        {
            "command": context.command.command,
            "command_source": context.command.source,
        },
    )
    exit_code = run_streamed_command(
        context.command.command,
        cwd=context.repo_root,
        env=build_run_environment(context),
        log_path=context.paths.log_path,
        stdout_path=context.paths.stdout_log_path,
        stderr_path=context.paths.stderr_log_path,
    )
    append_startup_event(context, "command_exit", {"exit_code": exit_code})
    finalize_run_manifest(context, manifest, start_monotonic, exit_code, patterns)
    return exit_code


def main() -> int:
    """Run the CLI."""
    try:
        return run_cli(parse_args())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
