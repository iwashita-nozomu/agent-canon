#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks experiment registry CI readiness.
# upstream design ../README.md shared automation index
# upstream design ../../documents/experiments/experiment-registry.md defines registry schema
# downstream implementation ../../tests/tools/test_run_managed_experiment.py tests
# @dependency-end

"""Validate the canonical experiment registry."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass
from pathlib import Path
from typing import cast

if __package__:
    from tools.experiments.experiment_identity import validate_segment
else:
    _IDENTITY_PATH = (
        Path(__file__).resolve().parents[1] / "experiments" / "experiment_identity.py"
    )
    _IDENTITY_SPEC = importlib.util.spec_from_file_location(
        "agentcanon_experiment_identity", _IDENTITY_PATH
    )
    if _IDENTITY_SPEC is None or _IDENTITY_SPEC.loader is None:
        raise ImportError(
            f"experiment identity source is unavailable: {_IDENTITY_PATH}"
        )
    _IDENTITY_MODULE = importlib.util.module_from_spec(_IDENTITY_SPEC)
    sys.modules[_IDENTITY_SPEC.name] = _IDENTITY_MODULE
    _IDENTITY_SPEC.loader.exec_module(_IDENTITY_MODULE)
    validate_segment = _IDENTITY_MODULE.validate_segment

MANAGED_RUN_ARTIFACTS = frozenset(
    {
        "run_manifest.json",
        "eval_manifest.json",
        "run.log",
        "artifact_manifest.json",
        "command.json",
        "config_source.yaml",
        "environment.json",
        "source_snapshot.json",
        "logs/startup.jsonl",
        "logs/stdout.log",
        "logs/stderr.log",
    }
)


@dataclass(frozen=True)
class Finding:
    """One registry finding."""

    level: str
    message: str


def run_git_root_lookup() -> subprocess.CompletedProcess[str]:
    """Run the git root lookup used by the CLI default."""
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
    )


def extract_git_root(result: subprocess.CompletedProcess[str]) -> Path | None:
    """Extract a repository root from one completed git lookup."""
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return None


def resolve_repo_root() -> Path:
    """Return the repository root from the checkout or script path."""
    discovered_root = extract_git_root(run_git_root_lookup())
    if discovered_root is not None:
        return discovered_root
    return Path(__file__).absolute().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Validate experiments/registry.toml.")
    parser.add_argument(
        "--repo-root",
        default=str(resolve_repo_root()),
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


def git_ref_exists(repo_root: Path, ref_name: str) -> bool:
    """Return whether one local or remote ref exists."""
    candidates = [
        ref_name,
        f"refs/heads/{ref_name}",
        f"refs/remotes/{ref_name}",
    ]
    for candidate in candidates:
        result = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", candidate],
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0:
            return True
    return False


def git_commit_exists(repo_root: Path, commit: str) -> bool:
    """Return whether one commit-ish exists."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


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


def normalize_optional_topics(
    raw_topics: object, table_name: str
) -> list[dict[str, object]]:
    """Return an optional topic table list."""
    if raw_topics is None:
        return []
    if not isinstance(raw_topics, list):
        raise ValueError(f"registry {table_name} must be an array of tables")
    topics: list[dict[str, object]] = []
    for index, raw_topic in enumerate(raw_topics):
        if not isinstance(raw_topic, dict):
            raise ValueError(f"{table_name}[{index}] must be a table")
        topics.append(raw_topic)
    return topics


def require_string(entry: dict[str, object], key: str) -> str | None:
    """Return one required non-empty string field."""
    raw_value = entry.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    return raw_value


def required_field_finding(topic_name: str, key: str) -> Finding:
    """Build the finding for one missing required string field."""
    return Finding("error", f"{topic_name}: missing required string field: {key}")


def append_missing_required_field_findings(
    findings: list[Finding], topic_name: str, values: dict[str, str | None]
) -> None:
    """Append findings for missing required string fields in declaration order."""
    for key, value in values.items():
        if value is None:
            findings.append(required_field_finding(topic_name, key))


def required_topic_values(topic: dict[str, object]) -> dict[str, str | None]:
    """Extract the required ordinary topic fields."""
    keys = (
        "status",
        "topic_dir",
        "topic_readme",
        "canonical_entrypoint",
        "result_root",
        "report_root",
        "default_variant",
    )
    return {key: require_string(topic, key) for key in keys}


def complete_required_values(values: dict[str, str | None]) -> dict[str, str] | None:
    """Return required values only when every field was present."""
    if any(value is None for value in values.values()):
        return None
    return {key: value for key, value in values.items() if value is not None}


def maybe_string(entry: dict[str, object], key: str) -> str | None:
    """Return one optional non-empty string field."""
    raw_value = entry.get(key)
    if not isinstance(raw_value, str):
        return None
    stripped = raw_value.strip()
    return stripped or None


def registered_command_value(entry: dict[str, object], command_kind: str) -> str | None:
    """Return one registered command, including legacy default aliases."""
    keys = [f"{command_kind}_inner_command"]
    if command_kind == "default":
        keys.append("smoke_inner_command")
    for key in keys:
        value = maybe_string(entry, key)
        if value is not None:
            return value
    return None


def registered_command_finding(topic_name: str, command_kind: str) -> Finding:
    """Build the finding for one missing registered command."""
    return Finding(
        "error",
        f"{topic_name}: missing registered command field for {command_kind}",
    )


def optional_string_list_value(entry: dict[str, object], key: str) -> object:
    """Extract one optional string-list value without recording findings."""
    return entry.get(key)


def normalize_optional_string_list(raw_value: object) -> list[str]:
    """Normalize valid non-empty strings from one optional list value."""
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        return []
    items = cast(list[object], raw_value)
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def optional_string_list_findings(
    scope_name: str, key: str, raw_value: object
) -> list[Finding]:
    """Build validation findings for one optional string-list value."""
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        return [Finding("error", f"{scope_name}: {key} must be an array of strings")]
    items = cast(list[object], raw_value)
    return [
        Finding("error", f"{scope_name}: {key}[{index}] must be a non-empty string")
        for index, item in enumerate(items)
        if not isinstance(item, str) or not item.strip()
    ]


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
                Finding(
                    "error",
                    f"{scope_name}: {key} must stay relative to result/<run_name>: {pattern}",
                )
            )
        if ".." in pattern_path.parts:
            findings.append(
                Finding(
                    "error",
                    f"{scope_name}: {key} must not escape result/<run_name>: {pattern}",
                )
            )
        if pattern in MANAGED_RUN_ARTIFACTS:
            findings.append(
                Finding(
                    "error",
                    f"{scope_name}: {key} must not target reserved managed "
                    f"artifacts: {pattern}",
                )
            )


def validate_topic_layout(
    repo_root: Path,
    defaults: dict[str, object],
    topic_name: str,
    fields: dict[str, str],
    findings: list[Finding],
) -> None:
    """Validate one topic's paths, status, and required files."""
    status = fields["status"]
    topic_dir_raw = fields["topic_dir"]
    readme_raw = fields["topic_readme"]
    entrypoint_raw = fields["canonical_entrypoint"]
    result_root_raw = fields["result_root"]
    report_root_raw = fields["report_root"]
    for field, value in (
        ("topic", topic_name),
        ("default_variant", fields["default_variant"]),
    ):
        try:
            validate_segment(value, field)
        except ValueError as exc:
            findings.append(Finding("error", f"{topic_name}: {exc}"))
    allowed_status = {"template", "draft", "active", "paused", "archived"}
    if status not in allowed_status:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: unsupported status {status!r}; "
                f"expected one of {sorted(allowed_status)}",
            )
        )

    topic_dir = repo_root / topic_dir_raw
    topic_readme = repo_root / readme_raw
    result_root = repo_root / result_root_raw
    report_root = repo_root / report_root_raw
    topic_template_dir = defaults.get("topic_template_dir")
    if topic_name == "_template" and isinstance(topic_template_dir, str):
        expected_topic_dir_raw = topic_template_dir
    else:
        expected_topic_dir_raw = f"experiments/{topic_name}"
    expected_topic_dir = repo_root / expected_topic_dir_raw
    expected_entrypoint_raw = f"{expected_topic_dir_raw}/run.py"
    expected_config_raw = f"{expected_topic_dir_raw}/config.yaml"
    expected_result_root_raw = f"{expected_topic_dir_raw}/result"
    expected_report_root_raw = f"{expected_topic_dir_raw}/report"
    expected_entrypoint = repo_root / expected_entrypoint_raw
    expected_config = repo_root / expected_config_raw

    if topic_dir != expected_topic_dir:
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: topic_dir is {topic_dir_raw}, "
                f"expected {expected_topic_dir_raw} for the default layout",
            )
        )
    if entrypoint_raw != expected_entrypoint_raw:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: canonical_entrypoint must be the topic-local run.py "
                f"({expected_entrypoint_raw}), got {entrypoint_raw}",
            )
        )
    if result_root_raw != expected_result_root_raw:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: result_root must be {expected_result_root_raw} "
                f"(run names are appended by the lifecycle owner; variant is metadata), got {result_root_raw}",
            )
        )
    if report_root_raw != expected_report_root_raw:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: report_root must be {expected_report_root_raw} "
                f"(the run name is appended directly), got {report_root_raw}",
            )
        )
    if not topic_dir.is_dir():
        findings.append(
            Finding("error", f"{topic_name}: topic_dir is missing: {topic_dir}")
        )
    if not topic_readme.is_file():
        findings.append(
            Finding("error", f"{topic_name}: topic_readme is missing: {topic_readme}")
        )
    if not expected_entrypoint.is_file():
        findings.append(
            Finding(
                "error",
                f"{topic_name}: canonical_entrypoint is missing: {expected_entrypoint}",
            )
        )
    if not expected_config.is_file():
        findings.append(
            Finding(
                "error",
                f"{topic_name}: topic config is missing: {expected_config_raw}",
            )
        )
    if not result_root.is_dir():
        findings.append(
            Finding("error", f"{topic_name}: result_root is missing: {result_root}")
        )
    if not report_root.is_dir():
        findings.append(
            Finding("error", f"{topic_name}: report_root is missing: {report_root}")
        )


def validate_topic_commands(
    defaults: dict[str, object],
    topic_name: str,
    topic: dict[str, object],
    entrypoint_raw: str,
    default_command: str,
    findings: list[Finding],
) -> None:
    """Validate registered topic commands against the canonical entrypoint."""
    managed_runner = defaults.get("managed_runner")
    registered_commands = [("default", default_command)]
    formal_command = maybe_string(topic, "formal_inner_command")
    if formal_command is not None:
        registered_commands.append(("formal", formal_command))
    for command_kind, command_text in registered_commands:
        if entrypoint_raw not in command_text:
            findings.append(
                Finding(
                    "error",
                    f"{topic_name}: {command_kind}_inner_command must mention "
                    f"canonical_entrypoint {entrypoint_raw}",
                )
            )
        if "{config_path}" not in command_text:
            findings.append(
                Finding(
                    "error",
                    f"{topic_name}: {command_kind}_inner_command must include "
                    "{config_path} so managed runs consume the saved config snapshot",
                )
            )
        managed_runner_module = None
        if isinstance(managed_runner, str) and managed_runner.endswith(".py"):
            managed_runner_module = managed_runner[:-3].replace("/", ".")
        if isinstance(managed_runner, str) and (
            managed_runner in command_text
            or (
                managed_runner_module is not None
                and managed_runner_module in command_text
            )
        ):
            findings.append(
                Finding(
                    "error",
                    f"{topic_name}: {command_kind}_inner_command must not call the "
                    "managed runner recursively",
                )
            )


def validate_topic_variant(
    topic_name: str,
    topic: dict[str, object],
    default_variant: str,
    findings: list[Finding],
) -> None:
    """Validate the selected topic command variant."""
    formal_command = maybe_string(topic, "formal_inner_command")
    try:
        validate_segment(default_variant, "default_variant")
    except ValueError as exc:
        findings.append(Finding("error", f"{topic_name}: {exc}"))
    if default_variant == "formal" and formal_command is None:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: default_variant is formal but formal_inner_command is missing",
            )
        )


def validate_topic_references(
    repo_root: Path,
    topic_name: str,
    topic: dict[str, object],
    findings: list[Finding],
) -> None:
    """Validate optional branch and note references for one topic."""
    active_branch = maybe_string(topic, "active_branch")
    if active_branch is not None and not git_branch_exists(repo_root, active_branch):
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: active_branch does not exist in the current repo: {active_branch}",
            )
        )

    for optional_path_key in (
        "active_worktree",
        "scope_file",
        "branch_note",
        "primary_note",
    ):
        optional_path = maybe_string(topic, optional_path_key)
        if optional_path is None:
            continue
        resolved = repo_root / optional_path
        if not resolved.exists():
            findings.append(
                Finding(
                    "warning",
                    f"{topic_name}: {optional_path_key} is set but missing: {resolved}",
                )
            )


def validate_topic_eval_artifacts(
    topic_name: str,
    topic: dict[str, object],
    findings: list[Finding],
) -> None:
    """Validate required and optional topic evaluation artifact patterns."""
    required_raw = optional_string_list_value(topic, "required_eval_artifacts")
    findings.extend(
        optional_string_list_findings(
            topic_name, "required_eval_artifacts", required_raw
        )
    )
    required_eval_artifacts = normalize_optional_string_list(required_raw)
    optional_raw = optional_string_list_value(topic, "optional_eval_artifacts")
    findings.extend(
        optional_string_list_findings(
            topic_name, "optional_eval_artifacts", optional_raw
        )
    )
    optional_eval_artifacts = normalize_optional_string_list(optional_raw)
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


def validate_topic(
    repo_root: Path,
    defaults: dict[str, object],
    topic: dict[str, object],
    findings: list[Finding],
) -> None:
    """Validate one topic entry through focused responsibility stages."""
    topic_name = require_string(topic, "name")
    if topic_name is None:
        findings.append(required_field_finding("<unknown>", "name"))
        return

    required_values = required_topic_values(topic)
    append_missing_required_field_findings(findings, topic_name, required_values)
    default_command = registered_command_value(topic, "default")
    if default_command is None:
        findings.append(registered_command_finding(topic_name, "default"))
    complete_values = complete_required_values(required_values)
    if complete_values is None or default_command is None:
        return

    validate_topic_layout(repo_root, defaults, topic_name, complete_values, findings)
    validate_topic_commands(
        defaults,
        topic_name,
        topic,
        complete_values["canonical_entrypoint"],
        default_command,
        findings,
    )
    validate_topic_variant(
        topic_name, topic, complete_values["default_variant"], findings
    )
    validate_topic_references(repo_root, topic_name, topic, findings)
    validate_topic_eval_artifacts(topic_name, topic, findings)


def validate_branch_topic(
    repo_root: Path,
    topic: dict[str, object],
    findings: list[Finding],
) -> None:
    """Validate one branch-only topic entry."""
    topic_name = require_string(topic, "name")
    if topic_name is None:
        findings.append(required_field_finding("<unknown>", "name"))
        return

    required_values = {
        key: require_string(topic, key)
        for key in ("status", "remote_branch", "primary_note")
    }
    append_missing_required_field_findings(findings, topic_name, required_values)
    complete_values = complete_required_values(required_values)
    if complete_values is None:
        return
    status = complete_values["status"]
    remote_branch = complete_values["remote_branch"]
    primary_note = complete_values["primary_note"]

    allowed_status = {"active", "paused", "archived"}
    if status not in allowed_status:
        findings.append(
            Finding(
                "error",
                f"{topic_name}: unsupported branch topic status {status!r}; "
                f"expected one of {sorted(allowed_status)}",
            )
        )

    if not git_ref_exists(repo_root, remote_branch):
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: remote_branch does not exist in the current repo: {remote_branch}",
            )
        )

    primary_note_path = repo_root / primary_note
    if not primary_note_path.is_file():
        findings.append(
            Finding(
                "error", f"{topic_name}: primary_note is missing: {primary_note_path}"
            )
        )

    branch_note = maybe_string(topic, "branch_note")
    if branch_note is not None and not (repo_root / branch_note).is_file():
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: branch_note is set but missing: {repo_root / branch_note}",
            )
        )

    source_commit = maybe_string(topic, "source_commit")
    if source_commit is not None and not git_commit_exists(repo_root, source_commit):
        findings.append(
            Finding(
                "warning",
                f"{topic_name}: source_commit does not exist in the current repo: {source_commit}",
            )
        )


def collect_findings(repo_root: Path, registry_path: Path) -> list[Finding]:
    """Validate one registry file."""
    findings: list[Finding] = []
    if not registry_path.is_file():
        return [Finding("error", f"registry file is missing: {registry_path}")]

    registry = load_registry(registry_path)
    schema_version = registry.get("schema_version")
    if schema_version != 1:
        findings.append(
            Finding("error", f"schema_version must be 1, got {schema_version!r}")
        )

    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        findings.append(Finding("error", "defaults must be a table"))
        defaults = {}

    managed_runner = defaults.get("managed_runner")
    if isinstance(managed_runner, str):
        managed_runner_path = repo_root / managed_runner
        if not managed_runner_path.is_file():
            findings.append(
                Finding(
                    "error",
                    f"defaults.managed_runner is missing: {managed_runner_path}",
                )
            )
    else:
        findings.append(Finding("error", "defaults.managed_runner must be a string"))

    topic_template_dir = defaults.get("topic_template_dir")
    if isinstance(topic_template_dir, str):
        resolved_template_dir = repo_root / topic_template_dir
        if not resolved_template_dir.is_dir():
            findings.append(
                Finding(
                    "error",
                    f"defaults.topic_template_dir is missing: {resolved_template_dir}",
                )
            )

    required_raw = optional_string_list_value(defaults, "required_eval_artifacts")
    findings.extend(
        optional_string_list_findings(
            "defaults", "required_eval_artifacts", required_raw
        )
    )
    required_eval_artifacts = normalize_optional_string_list(required_raw)
    optional_raw = optional_string_list_value(defaults, "optional_eval_artifacts")
    findings.extend(
        optional_string_list_findings(
            "defaults", "optional_eval_artifacts", optional_raw
        )
    )
    optional_eval_artifacts = normalize_optional_string_list(optional_raw)
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
    branch_topics = normalize_optional_topics(
        registry.get("branch_topics"), "branch_topics"
    )
    seen_names: set[str] = set()
    for topic in topics:
        topic_name = topic.get("name")
        if isinstance(topic_name, str):
            if topic_name in seen_names:
                findings.append(Finding("error", f"duplicate topic name: {topic_name}"))
            seen_names.add(topic_name)
        validate_topic(repo_root, defaults, topic, findings)

    for topic in branch_topics:
        topic_name = topic.get("name")
        if isinstance(topic_name, str):
            if topic_name in seen_names:
                findings.append(Finding("error", f"duplicate topic name: {topic_name}"))
            seen_names.add(topic_name)
        validate_branch_topic(repo_root, topic, findings)

    return findings


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else repo_root / "experiments" / "registry.toml"
    )
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
