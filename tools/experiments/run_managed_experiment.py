#!/usr/bin/env python3
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
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path

DEFAULT_REQUIRED_EVAL_ARTIFACTS = ("summary.json", "cases.jsonl")
MANAGED_RUN_ARTIFACTS = frozenset({"run_manifest.json", "eval_manifest.json", "run.log"})

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[2]


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_timestamp() -> str:
    """Return the compact timestamp used for run names."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Create one managed experiment run directory, manifest, and optional report stub."
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
        default="manual",
        help="Variant label used when --run-name is omitted.",
    )
    parser.add_argument(
        "--registry",
        help="Optional registry path. Defaults to <repo-root>/experiments/registry.toml when present.",
    )
    parser.add_argument(
        "--use-registered-command",
        choices=("smoke", "formal"),
        help="Execute the canonical inner command from experiments/registry.toml for this topic.",
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
        "--dry-run",
        action="store_true",
        help="Resolve run paths and command metadata but do not write files or execute the command.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=(
            "Command to run. Tokens may use {run_dir}, {run_name}, {report_path}, "
            "{manifest_path}, {eval_manifest_path}."
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
    values: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key}[{index}] must be a non-empty string")
        values.append(item.strip())
    return values


def find_registry_topic(registry: dict[str, object], topic_name: str) -> dict[str, object] | None:
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


def load_registry_entry(
    repo_root: Path, registry_path: Path | None, topic_name: str
) -> tuple[Path | None, dict[str, object] | None, dict[str, object]]:
    """Load one topic entry from the registry when available."""
    resolved_registry = registry_path or (repo_root / "experiments" / "registry.toml")
    if not resolved_registry.is_file():
        return None, None, {}
    registry = load_registry(resolved_registry)
    entry = find_registry_topic(registry, topic_name)
    if entry is None:
        raise ValueError(f"topic {topic_name!r} is missing from {resolved_registry}")
    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("experiment registry defaults must be a table")
    return resolved_registry, entry, defaults


def command_version(name: str) -> str | None:
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
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if not output:
        return None
    return output.splitlines()[0]


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


def render_report_stub(
    *,
    topic: str,
    run_name: str,
    report_path: Path,
    result_dir: Path,
    manifest_path: Path,
    eval_manifest_path: Path,
    command: list[str],
    created_at: str,
    branch: str | None,
    commit: str | None,
    registry_path: Path | None,
) -> str:
    """Render one initial run report."""
    command_text = shlex.join(command) if command else "(dry-run)"
    branch_text = branch or "(unknown)"
    commit_text = commit or "(unknown)"
    registry_text = str(registry_path) if registry_path is not None else "(none)"
    return f"""# {run_name}

- Topic: {topic}
- Created At (UTC): {created_at}
- Result Dir: {result_dir}
- Run Manifest: {manifest_path}
- Eval Manifest: {eval_manifest_path}
- Registry: {registry_text}
- Branch: {branch_text}
- Commit: {commit_text}

## Question

<!-- What empirical question does this run answer? -->

## Comparison Target

<!-- main, baseline, previous run, or external reference. -->

## Protocol

- Command: `{command_text}`
- Report Path: `{report_path}`

## Results

<!-- Fill in summary.json, cases.jsonl, and the main observations after the run. -->

## Reproducibility Record

- `run_manifest.json`
- `eval_manifest.json`
- `run.log`
- `summary.json`
- `cases.jsonl`

## Critical Review Notes

<!-- What this run still does not justify. -->
"""


def build_manifest(
    *,
    repo_root: Path,
    topic: str,
    run_name: str,
    topic_dir: Path,
    result_dir: Path,
    report_path: Path,
    manifest_path: Path,
    command: list[str],
    created_at: str,
    status: str,
    registry_path: Path | None,
    registry_entry: dict[str, object] | None,
    command_source: str,
    registered_command_match: str | None,
) -> dict[str, object]:
    """Build one manifest dictionary."""
    branch = git_value(repo_root, "branch", "--show-current")
    commit = git_value(repo_root, "rev-parse", "HEAD")
    git_dirty = git_value(repo_root, "status", "--short")
    manifest: dict[str, object] = {
        "topic": topic,
        "run_name": run_name,
        "status": status,
        "created_at_utc": created_at,
        "repo_root": str(repo_root),
        "topic_dir": str(topic_dir),
        "result_dir": str(result_dir),
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "command": command,
        "server_context": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME") or "(unknown)",
        },
        "tool_versions": {
            "python": platform.python_version(),
            "codex": command_version("codex"),
            "docker": command_version("docker"),
        },
        "command_source": command_source,
        "registered_command_match": registered_command_match,
        "git": {
            "branch": branch,
            "commit": commit,
            "dirty": bool(git_dirty),
            "status_short": git_dirty.splitlines() if git_dirty else [],
        },
    }
    if registry_path is not None and registry_entry is not None:
        registry_snapshot = dict(registry_entry)
        registry_snapshot["registry_path"] = str(registry_path)
        manifest["registry"] = registry_snapshot
    return manifest


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write one JSON object with canonical formatting."""
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Write one manifest JSON file."""
    write_json(path, manifest)


def merge_unique_strings(*groups: list[str]) -> list[str]:
    """Return one deduplicated list preserving first appearance order."""
    merged: list[str] = []
    for group in groups:
        for value in group:
            if value not in merged:
                merged.append(value)
    return merged


def validate_eval_artifact_patterns(patterns: list[str], key: str) -> list[str]:
    """Validate one eval artifact pattern list."""
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            raise ValueError(f"{key} must stay relative to result/<run_name>: {pattern}")
        if ".." in pattern_path.parts:
            raise ValueError(f"{key} must not escape result/<run_name>: {pattern}")
    return patterns


def resolve_eval_artifact_patterns(
    registry_defaults: dict[str, object],
    registry_entry: dict[str, object] | None,
) -> tuple[list[str], list[str]]:
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
        registry_entry.get("required_eval_artifacts") if registry_entry is not None else None,
        "topics.required_eval_artifacts",
    )
    entry_optional = string_list(
        registry_entry.get("optional_eval_artifacts") if registry_entry is not None else None,
        "topics.optional_eval_artifacts",
    )
    required = merge_unique_strings(
        list(DEFAULT_REQUIRED_EVAL_ARTIFACTS),
        default_required,
        entry_required,
    )
    optional = merge_unique_strings(default_optional, entry_optional)
    optional = [pattern for pattern in optional if pattern not in required]
    return (
        validate_eval_artifact_patterns(required, "required_eval_artifacts"),
        validate_eval_artifact_patterns(optional, "optional_eval_artifacts"),
    )


def file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
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


def line_count(path: Path) -> int:
    """Return the number of lines in one file without assuming UTF-8 text."""
    count = 0
    saw_bytes = False
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            saw_bytes = True
            last_byte = chunk[-1:]
            count += chunk.count(b"\n")
    if saw_bytes and last_byte != b"\n":
        count += 1
    return count


def is_managed_run_artifact(path: Path, result_dir: Path) -> bool:
    """Return whether one path is a reserved top-level managed artifact."""
    return str(path.relative_to(result_dir)) in MANAGED_RUN_ARTIFACTS


def collect_eval_artifacts(
    result_dir: Path,
    *,
    topic: str,
    run_name: str,
    required_patterns: list[str],
    optional_patterns: list[str],
) -> dict[str, object]:
    """Collect eval artifact metadata from one result directory."""
    matched_patterns_by_path: dict[Path, list[str]] = {}
    missing_required_patterns: list[str] = []

    for pattern in required_patterns:
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

    for pattern in optional_patterns:
        for match in sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        ):
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    artifacts: list[dict[str, object]] = []
    for path in sorted(matched_patterns_by_path, key=lambda item: str(item.relative_to(result_dir))):
        artifact: dict[str, object] = {
            "relative_path": str(path.relative_to(result_dir)),
            "kind": artifact_kind(path),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            "matched_patterns": matched_patterns_by_path[path],
        }
        if artifact["kind"] in {"jsonl", "text", "csv"}:
            artifact["line_count"] = line_count(path)
        artifacts.append(artifact)

    return {
        "topic": topic,
        "run_name": run_name,
        "result_dir": str(result_dir),
        "collected_at_utc": utc_now(),
        "required_patterns": required_patterns,
        "optional_patterns": optional_patterns,
        "missing_required_patterns": missing_required_patterns,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def format_command(command: list[str], placeholders: dict[str, str]) -> list[str]:
    """Format command tokens with run placeholders."""
    if command and command[0] == "--":
        command = command[1:]
    return [token.format(**placeholders) for token in command]


def command_from_registry(
    registry_entry: dict[str, object],
    command_kind: str,
    placeholders: dict[str, str],
) -> list[str]:
    """Return one formatted command from the registry."""
    command_key = f"{command_kind}_inner_command"
    raw_command = registry_entry.get(command_key)
    if not isinstance(raw_command, str) or not raw_command.strip():
        raise ValueError(f"registry entry is missing {command_key}")
    return [token.format(**placeholders) for token in shlex.split(raw_command)]


def matched_registered_command(
    registry_entry: dict[str, object] | None,
    command: list[str],
    placeholders: dict[str, str],
) -> str | None:
    """Return the matching registered command kind when one exists."""
    if registry_entry is None:
        return None
    for command_kind in ("smoke", "formal"):
        try:
            registered_command = command_from_registry(registry_entry, command_kind, placeholders)
        except ValueError:
            continue
        if registered_command == command:
            return command_kind
    return None


def stream_command(command: list[str], *, cwd: Path, env: dict[str, str], log_path: Path) -> int:
    """Run one command, teeing output to stdout and the log file."""
    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write("$ " + shlex.join(command) + "\n")
        log_handle.flush()

        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                log_handle.write(line)
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                return process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return 130


def main() -> int:
    """Run the CLI."""
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    registry_arg = Path(args.registry).resolve() if args.registry else None
    try:
        registry_path, registry_entry, registry_defaults = load_registry_entry(
            repo_root, registry_arg, args.topic
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if registry_entry is not None:
        topic_dir_raw = registry_entry.get("topic_dir")
        if not isinstance(topic_dir_raw, str):
            print(f"registry entry for {args.topic!r} is missing topic_dir", file=sys.stderr)
            return 2
        topic_dir = repo_root / topic_dir_raw
    else:
        topic_dir = repo_root / "experiments" / args.topic
    if not topic_dir.is_dir():
        print(f"topic directory does not exist: {topic_dir}", file=sys.stderr)
        return 2

    run_name = args.run_name or f"{args.topic}_{args.variant}_{compact_timestamp()}"
    result_dir = topic_dir / "result" / run_name
    if args.report_path:
        report_path = Path(args.report_path).resolve()
    elif registry_entry is not None:
        registry_report_root = registry_entry.get("report_root") or registry_defaults.get("report_root")
        if isinstance(registry_report_root, str):
            report_path = (repo_root / registry_report_root / f"{run_name}.md").resolve()
        else:
            report_path = (repo_root / "experiments" / "report" / f"{run_name}.md").resolve()
    else:
        report_path = (repo_root / "experiments" / "report" / f"{run_name}.md").resolve()
    manifest_path = result_dir / "run_manifest.json"
    eval_manifest_path = result_dir / "eval_manifest.json"
    log_path = result_dir / "run.log"
    try:
        required_eval_patterns, optional_eval_patterns = resolve_eval_artifact_patterns(
            registry_defaults,
            registry_entry,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    created_at = utc_now()
    placeholders = {
        "repo_root": str(repo_root),
        "topic_dir": str(topic_dir),
        "run_name": run_name,
        "run_dir": str(result_dir),
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "eval_manifest_path": str(eval_manifest_path),
        "log_path": str(log_path),
    }

    if args.use_registered_command and args.command:
        print("do not pass both a manual command and --use-registered-command", file=sys.stderr)
        return 2
    if args.use_registered_command:
        if registry_entry is None:
            print("--use-registered-command requires experiments/registry.toml", file=sys.stderr)
            return 2
        try:
            command = command_from_registry(registry_entry, args.use_registered_command, placeholders)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        command_source = f"registered:{args.use_registered_command}"
    else:
        command = format_command(args.command, placeholders)
        command_source = "manual"
    registered_match = matched_registered_command(registry_entry, command, placeholders)

    manifest = build_manifest(
        repo_root=repo_root,
        topic=args.topic,
        run_name=run_name,
        topic_dir=topic_dir,
        result_dir=result_dir,
        report_path=report_path,
        manifest_path=manifest_path,
        command=command,
        created_at=created_at,
        status="initialized" if args.dry_run else "running",
        registry_path=registry_path,
        registry_entry=registry_entry,
        command_source=command_source,
        registered_command_match=registered_match,
    )

    if args.dry_run:
        print(f"run_name={run_name}")
        print(f"result_dir={result_dir}")
        print(f"report_path={report_path}")
        print(f"manifest_path={manifest_path}")
        print(f"eval_manifest_path={eval_manifest_path}")
        print(f"command_source={command_source}")
        print("required_eval_patterns=" + ",".join(required_eval_patterns))
        print("optional_eval_patterns=" + ",".join(optional_eval_patterns))
        if command:
            print("command=" + shlex.join(command))
        return 0

    if not command:
        print("a command is required unless --dry-run is used", file=sys.stderr)
        return 2

    result_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_manifest(manifest_path, manifest)

    if not args.skip_report_init and not report_path.exists():
        git_info = manifest["git"]
        if not isinstance(git_info, dict):
            raise TypeError("git manifest entry must be a dictionary")
        report_path.write_text(
            render_report_stub(
                topic=args.topic,
                run_name=run_name,
                report_path=report_path,
                result_dir=result_dir,
                manifest_path=manifest_path,
                eval_manifest_path=eval_manifest_path,
                command=command,
                created_at=created_at,
                branch=git_info.get("branch") if isinstance(git_info.get("branch"), str) else None,
                commit=git_info.get("commit") if isinstance(git_info.get("commit"), str) else None,
                registry_path=registry_path,
            ),
            encoding="utf-8",
        )

    env = dict(os.environ)
    env.update(
        {
            "EXPERIMENT_RUN_NAME": run_name,
            "EXPERIMENT_TOPIC": args.topic,
            "EXPERIMENT_RUN_DIR": str(result_dir),
            "EXPERIMENT_REPORT_PATH": str(report_path),
            "EXPERIMENT_RUN_MANIFEST": str(manifest_path),
            "EXPERIMENT_RUN_LOG": str(log_path),
        }
    )

    start_monotonic = time.monotonic()
    exit_code = stream_command(command, cwd=repo_root, env=env, log_path=log_path)
    finished_at = utc_now()
    eval_collection = collect_eval_artifacts(
        result_dir,
        topic=args.topic,
        run_name=run_name,
        required_patterns=required_eval_patterns,
        optional_patterns=optional_eval_patterns,
    )
    write_json(eval_manifest_path, eval_collection)
    manifest["finished_at_utc"] = finished_at
    manifest["duration_seconds"] = round(time.monotonic() - start_monotonic, 3)
    manifest["exit_code"] = exit_code
    manifest["status"] = "completed" if exit_code == 0 else "failed"
    manifest["eval_artifacts"] = {
        "eval_manifest_path": str(eval_manifest_path),
        "required_patterns": required_eval_patterns,
        "optional_patterns": optional_eval_patterns,
        "collected_artifact_count": eval_collection["artifact_count"],
        "missing_required_patterns": eval_collection["missing_required_patterns"],
    }
    write_manifest(manifest_path, manifest)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
