#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Validate the canonical experiment registry."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

MANAGED_RUN_ARTIFACTS = frozenset({"run_manifest.json", "eval_manifest.json", "run.log"})


@dataclass(frozen=True)
class Finding:
    """One registry finding."""

    level: str
    message: str


def repo_root_from_script() -> Path:
    """Return the repository root from the script path."""
    return Path(__file__).absolute().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Validate experiments/registry.toml.")
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_from_script()),
        help="Repository root. Defaults to the path inferred from this script.",
    )
    parser.add_argument(
        "--registry",
        help="Optional registry path. Defaults to <repo-root>/experiments/registry.toml.",
    )
    return parser


def load_registry(path: Path) -> dict[str, object]:
    """Load one TOML registry."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("registry TOML root must be a table")
    return data


def git_branch_exists(repo_root: Path, branch_name: str) -> bool:
    """Return whether one local branch exists."""
    result = subprocess.run(
        ["git", "branch", "--list", branch_name],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def normalize_topics(raw_topics: object) -> list[dict[str, object]]:
    """Return the topic table list."""
    if not isinstance(raw_topics, list):
        raise ValueError("registry must contain [[topics]]")
    topics: list[dict[str, object]] = []
    for index, raw_topic in enumerate(raw_topics):
        if not isinstance(raw_topic, dict):
            raise ValueError(f"topics[{index}] must be a table")
        topics.append(raw_topic)
    return topics


def require_string(
    findings: list[Finding], topic_name: str, entry: dict[str, object], key: str
) -> str | None:
    """Return one required non-empty string field."""
    raw_value = entry.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        findings.append(Finding("error", f"{topic_name}: missing required string field: {key}"))
        return None
    return raw_value


def maybe_string(entry: dict[str, object], key: str) -> str | None:
    """Return one optional non-empty string field."""
    raw_value = entry.get(key)
    if not isinstance(raw_value, str):
        return None
    stripped = raw_value.strip()
    return stripped or None


def maybe_string_list(
    findings: list[Finding],
    scope_name: str,
    entry: dict[str, object],
    key: str,
) -> list[str]:
    """Return one optional string list, recording validation findings."""
    raw_value = entry.get(key)
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        findings.append(Finding("error", f"{scope_name}: {key} must be an array of strings"))
        return []
    values: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            findings.append(
                Finding("error", f"{scope_name}: {key}[{index}] must be a non-empty string")
            )
            continue
        values.append(item.strip())
    return values


def validate_eval_patterns(
    findings: list[Finding],
    scope_name: str,
    key: str,
    patterns: list[str],
) -> None:
    """Validate one eval artifact pattern list."""
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            findings.append(
                Finding("error", f"{scope_name}: {key} must stay relative to result/<run_name>: {pattern}")
            )
        if ".." in pattern_path.parts:
            findings.append(
                Finding("error", f"{scope_name}: {key} must not escape result/<run_name>: {pattern}")
            )
        if pattern in MANAGED_RUN_ARTIFACTS:
            findings.append(
                Finding(
                    "error",
                    f"{scope_name}: {key} must not target reserved top-level managed artifacts: {pattern}",
                )
            )


def validate_topic(
    repo_root: Path,
    defaults: dict[str, object],
    topic: dict[str, object],
    findings: list[Finding],
) -> None:
    """Validate one topic entry."""
    topic_name = require_string(findings, "<unknown>", topic, "name")
    if topic_name is None:
        return

    status = require_string(findings, topic_name, topic, "status")
    topic_dir_raw = require_string(findings, topic_name, topic, "topic_dir")
    readme_raw = require_string(findings, topic_name, topic, "topic_readme")
    entrypoint_raw = require_string(findings, topic_name, topic, "canonical_entrypoint")
    result_root_raw = require_string(findings, topic_name, topic, "result_root")
    report_root_raw = require_string(findings, topic_name, topic, "report_root")
    default_variant = require_string(findings, topic_name, topic, "default_variant")
    smoke_command = require_string(findings, topic_name, topic, "smoke_inner_command")
    formal_command = require_string(findings, topic_name, topic, "formal_inner_command")
    if any(
        value is None
        for value in (
            status,
            topic_dir_raw,
            readme_raw,
            entrypoint_raw,
            result_root_raw,
            report_root_raw,
            default_variant,
            smoke_command,
            formal_command,
        )
    ):
        return

    allowed_status = {"template", "draft", "active", "paused", "archived"}
    if status not in allowed_status:
        findings.append(
            Finding("error", f"{topic_name}: unsupported status {status!r}; expected one of {sorted(allowed_status)}")
        )

    topic_dir = repo_root / topic_dir_raw
    topic_readme = repo_root / readme_raw
    canonical_entrypoint = repo_root / entrypoint_raw
    result_root = repo_root / result_root_raw
    report_root = repo_root / report_root_raw
    expected_topic_dir = repo_root / "experiments" / topic_name

    if topic_dir != expected_topic_dir:
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: topic_dir is {topic_dir_raw}, expected experiments/{topic_name} for the default layout",
            )
        )
    if not topic_dir.is_dir():
        findings.append(Finding("error", f"{topic_name}: topic_dir is missing: {topic_dir}"))
    if not topic_readme.is_file():
        findings.append(Finding("error", f"{topic_name}: topic_readme is missing: {topic_readme}"))
    if not canonical_entrypoint.is_file():
        findings.append(Finding("error", f"{topic_name}: canonical_entrypoint is missing: {canonical_entrypoint}"))
    if not result_root.is_dir():
        findings.append(Finding("error", f"{topic_name}: result_root is missing: {result_root}"))
    if not report_root.is_dir():
        findings.append(Finding("error", f"{topic_name}: report_root is missing: {report_root}"))

    managed_runner = defaults.get("managed_runner")
    for command_kind, command_text in (("smoke", smoke_command), ("formal", formal_command)):
        if "{run_dir}" not in command_text:
            findings.append(
                Finding("error", f"{topic_name}: {command_kind}_inner_command must contain {{run_dir}}")
            )
        if entrypoint_raw not in command_text:
            findings.append(
                Finding(
                    "error",
                    f"{topic_name}: {command_kind}_inner_command must mention canonical_entrypoint {entrypoint_raw}",
                )
            )
        if managed_runner is not None and isinstance(managed_runner, str) and managed_runner in command_text:
            findings.append(
                Finding(
                    "error",
                    f"{topic_name}: {command_kind}_inner_command must not call the managed runner recursively",
                )
            )

    if default_variant not in {"smoke", "formal", "manual"}:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: default_variant must be smoke, formal, or manual; got {default_variant!r}",
            )
        )

    active_branch = maybe_string(topic, "active_branch")
    if active_branch is not None and not git_branch_exists(repo_root, active_branch):
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: active_branch does not exist in the current repo: {active_branch}",
            )
        )

    for optional_path_key in ("active_worktree", "scope_file", "branch_note", "primary_note"):
        optional_path = maybe_string(topic, optional_path_key)
        if optional_path is None:
            continue
        resolved = repo_root / optional_path
        if not resolved.exists():
            findings.append(
                Finding("warning", f"{topic_name}: {optional_path_key} is set but missing: {resolved}")
            )

    required_eval_artifacts = maybe_string_list(
        findings,
        topic_name,
        topic,
        "required_eval_artifacts",
    )
    optional_eval_artifacts = maybe_string_list(
        findings,
        topic_name,
        topic,
        "optional_eval_artifacts",
    )
    validate_eval_patterns(
        findings,
        topic_name,
        "required_eval_artifacts",
        required_eval_artifacts,
    )
    validate_eval_patterns(
        findings,
        topic_name,
        "optional_eval_artifacts",
        optional_eval_artifacts,
    )


def collect_findings(repo_root: Path, registry_path: Path) -> list[Finding]:
    """Validate one registry file."""
    findings: list[Finding] = []
    if not registry_path.is_file():
        return [Finding("error", f"registry file is missing: {registry_path}")]

    registry = load_registry(registry_path)
    schema_version = registry.get("schema_version")
    if schema_version != 1:
        findings.append(Finding("error", f"schema_version must be 1, got {schema_version!r}"))

    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        findings.append(Finding("error", "defaults must be a table"))
        defaults = {}

    managed_runner = defaults.get("managed_runner")
    if isinstance(managed_runner, str):
        managed_runner_path = repo_root / managed_runner
        if not managed_runner_path.is_file():
            findings.append(Finding("error", f"defaults.managed_runner is missing: {managed_runner_path}"))
    else:
        findings.append(Finding("error", "defaults.managed_runner must be a string"))

    topic_template_dir = defaults.get("topic_template_dir")
    if isinstance(topic_template_dir, str):
        resolved_template_dir = repo_root / topic_template_dir
        if not resolved_template_dir.is_dir():
            findings.append(
                Finding("error", f"defaults.topic_template_dir is missing: {resolved_template_dir}")
            )

    required_eval_artifacts = maybe_string_list(
        findings,
        "defaults",
        defaults,
        "required_eval_artifacts",
    )
    optional_eval_artifacts = maybe_string_list(
        findings,
        "defaults",
        defaults,
        "optional_eval_artifacts",
    )
    validate_eval_patterns(
        findings,
        "defaults",
        "required_eval_artifacts",
        required_eval_artifacts,
    )
    validate_eval_patterns(
        findings,
        "defaults",
        "optional_eval_artifacts",
        optional_eval_artifacts,
    )

    topics = normalize_topics(registry.get("topics", []))
    seen_names: set[str] = set()
    for topic in topics:
        topic_name = topic.get("name")
        if isinstance(topic_name, str):
            if topic_name in seen_names:
                findings.append(Finding("error", f"duplicate topic name: {topic_name}"))
            seen_names.add(topic_name)
        validate_topic(repo_root, defaults, topic, findings)

    return findings


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else repo_root / "experiments" / "registry.toml"
    try:
        findings = collect_findings(repo_root, registry_path)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"repo_root={repo_root}")
    print(f"registry_path={registry_path}")
    for finding in findings:
        print(f"{finding.level.upper()}: {finding.message}")

    if any(finding.level == "error" for finding in findings):
        return 1
    print("OK: experiment registry is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
