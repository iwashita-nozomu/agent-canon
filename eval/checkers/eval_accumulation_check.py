#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates append-only AgentCanon eval and hook result accumulation.
# upstream design ../../evidence/agent-evals/README.md eval usage contract
# upstream design ../../evidence/agent-evals/eval_result_families.toml eval family artifact registry
# upstream design ../../documents/runtime/runtime-log-archive.md eval and hook result archive contract
# upstream design ../../documents/runtime/runtime-log-archive-migration.md legacy in-tree result migration contract
# upstream implementation ./runtime_log_paths.py resolves mounted archive result paths
# upstream implementation ./runtime_artifacts.py owns the external artifact boundary
# upstream implementation ./prompt_capture.py owns prompt secret redaction patterns
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# downstream implementation ../../tools/ci/run_all_checks.sh runs eval accumulation checks
# downstream implementation ../../tests/agent_tools/test_eval_accumulation_check.py tests result validation
# @dependency-end
"""Check accumulated AgentCanon eval and hook results."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval.checkers.eval_manifest_paths import eval_manifest_path, resolve_eval_manifest  # noqa: E402
from tools.agent.orchestration.prompt_capture import redact_sensitive_text  # noqa: E402
from tools.runtime.archive.runtime_log_paths import (  # noqa: E402
    eval_result_search_dirs,
    hook_result_search_dirs,
    mounted_log_archive_root,
)
from tools.runtime.artifacts.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactError,
    runtime_artifact_boundary,
)

HOOK_REQUIRED_FIELDS = (
    "hook_run_id",
    "timestamp",
    "status",
    "payload_fingerprint",
)
BEHAVIOR_EVENT_SCHEMA = "agent-canon.behavior-event.v1"
BEHAVIOR_EVENT_KIND = "behavior_snapshot"
BEHAVIOR_HOOK_EVENTS = frozenset({"UserPromptSubmit", "PreToolUse", "PostToolUse"})
WORKFLOW_ATTRIBUTION_KINDS = frozenset({"owner", "context", "missing"})
PROMPT_CAPTURE_STATUSES = frozenset({"present", "missing"})
PROMPT_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{16}$")


PROMPT_CAPTURE_CAUSE_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
BEHAVIOR_HINT_FIELDS = frozenset(
    {
        "event_kind",
        "workflow_attribution_kind",
        "selected_workflow",
        "selected_workflows",
        "workflow",
        "workflow_family",
        "workflow_selection_kind",
        "workflow_owner",
        "workflow_owner_workflows",
        "workflow_context_kind",
        "workflow_context_source",
        "workflow_context_workflows",
        "workflow_context_timestamp",
        "workflow_context_source_event",
        "selected_workflow_count",
        "candidate_workflows",
        "prompt_capture_status",
        "prompt_excerpt_redacted",
        "prompt_fingerprint",
        "prompt_char_count",
    }
)
SKILL_REPORT_RE = re.compile(
    r"^skill-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail)-[a-z0-9-]+(?:-[a-z0-9-]+)*\.md$"
)
WORKFLOW_SELECTION_REPORT_RE = re.compile(
    r"^workflow-selection-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail)\.md$"
)
REPORT_QUALITY_REPORT_RE = re.compile(
    r"^report-quality-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail)\.md$"
)
DEFAULT_FAMILY_REGISTRY = Path(eval_manifest_path("eval_result_families.toml"))
COMPACT_FINDING_SAMPLE_LIMIT = 25


@dataclass(frozen=True)
class Finding:
    """One eval accumulation finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one machine-readable finding."""
        return f"EVAL_ACCUMULATION_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class EvalFamilyContract:
    """One accumulated eval family artifact contract."""

    family_id: str
    check_id: str
    count_label: str
    summary: str
    producer: str
    filename_regex: str
    run_id_regex: str
    missing_reports_detail: str
    missing_run_id_detail: str
    duplicate_run_id_detail: str


@dataclass(frozen=True)
class EvalAccumulationReport:
    """Eval accumulation report."""

    hook_files: int
    hook_entries: int
    hook_legacy_missing_namespace: int
    eval_report_counts: dict[str, int]
    findings: tuple[Finding, ...]


def is_mounted_archive_path(path_label: str) -> bool:
    """Return whether a finding path points at the mounted external archive."""
    return "archive/agent-canon-log/" in Path(path_label).as_posix()


def is_warning_finding(finding: Finding) -> bool:
    """Return whether a finding is nonblocking archive evidence debt."""
    if finding.check == "hook_jsonl" and is_mounted_archive_path(finding.path):
        return True
    return (
        finding.detail == "missing-eval-run-id"
        and "archive/agent-canon-log/eval-results/legacy-import/"
        in Path(finding.path).as_posix()
    ) or (
        finding.check == "behavior_event"
        and finding.detail == "legacy-behavior-schema"
    )


def blocking_findings(report: EvalAccumulationReport) -> tuple[Finding, ...]:
    """Return findings that should fail the checker."""
    return tuple(finding for finding in report.findings if not is_warning_finding(finding))


def warning_findings(report: EvalAccumulationReport) -> tuple[Finding, ...]:
    """Return findings that should be reported without blocking the checker."""
    return tuple(finding for finding in report.findings if is_warning_finding(finding))


def report_status(report: EvalAccumulationReport) -> str:
    """Return pass/fail status from blocking findings only."""
    return "pass" if not blocking_findings(report) else "fail"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="Explicit external runtime root containing eval and hook archives.",
    )
    parser.add_argument(
        "--family-registry",
        default=DEFAULT_FAMILY_REGISTRY.as_posix(),
        help="TOML registry that declares accumulated eval result families.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--compact-out",
        type=Path,
        help="Optional JSON summary path. When set, stdout omits full finding detail.",
    )
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return the explicitly selected AgentCanon source checkout."""
    return root.resolve()


def relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def git_check_ignored(root: Path, path: Path) -> bool:
    """Return whether git ignore rules ignore a path."""
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", "--", relative(root, path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ignored_path_findings(root: Path, paths: Sequence[Path]) -> list[Finding]:
    """Return findings for result files ignored by git."""
    return [
        Finding("gitignore", relative(root, path), "ignored-result-path")
        for path in paths
        if not intentionally_ignored_archive_path(path) and git_check_ignored(root, path)
    ]


def intentionally_ignored_archive_path(path: Path) -> bool:
    """Return whether the path is inside the mounted external log archive."""
    parts = path.parts
    return "archive" in parts and "agent-canon-log" in parts


def _nonnegative_int(value: object) -> bool:
    """Return whether a value is an integer counter (not a boolean)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _string_list(value: object) -> bool:
    """Return whether a value is a JSON list of strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _behavior_envelope_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate canonical behavior-event identity and transport fields."""
    findings: list[Finding] = []
    required_nonempty = (
        "event_id",
        "hook_invocation_id",
        "hook_event_name",
        "event_kind",
        "timestamp",
        "source",
        "workflow_attribution_kind",
        "prompt_capture_status",
    )
    for field in required_nonempty:
        value = entry.get(field)
        valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            findings.append(Finding("behavior_event", label, f"missing-field:{field}"))

    for field, value, valid in (
        ("prompt_excerpt_redacted", entry.get("prompt_excerpt_redacted"), isinstance(entry.get("prompt_excerpt_redacted"), str)),
        ("prompt_fingerprint", entry.get("prompt_fingerprint"), isinstance(entry.get("prompt_fingerprint"), str)),
        ("prompt_char_count", entry.get("prompt_char_count"), _nonnegative_int(entry.get("prompt_char_count"))),
        ("prompt_excerpt_truncated", entry.get("prompt_excerpt_truncated"), isinstance(entry.get("prompt_excerpt_truncated"), bool)),
    ):
        if not valid:
            findings.append(Finding("behavior_event", label, f"missing-field:{field}"))

    event_id = entry.get("event_id")
    if isinstance(event_id, str) and not re.fullmatch(r"[0-9a-f]{64}", event_id):
        findings.append(Finding("behavior_event", label, "invalid-event-id"))
    if entry.get("hook_event_name") not in BEHAVIOR_HOOK_EVENTS:
        findings.append(Finding("behavior_event", label, "invalid-hook-event-name"))
    if entry.get("event_kind") != BEHAVIOR_EVENT_KIND:
        findings.append(Finding("behavior_event", label, "invalid-event-kind"))

    return findings


def _behavior_workflow_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate owner/context/missing workflow attribution coherence."""
    selected = entry.get("selected_workflows", [])
    owner_workflows = entry.get("workflow_owner_workflows", [])
    context_workflows = entry.get("workflow_context_workflows", [])
    findings = _workflow_list_findings(label, selected, owner_workflows, context_workflows)
    findings.extend(_workflow_kind_findings(label, entry))
    return findings


def _workflow_list_findings(
    label: str,
    selected: object,
    owner_workflows: object,
    context_workflows: object,
) -> list[Finding]:
    """Validate the three workflow list fields."""
    findings: list[Finding] = []
    for field, value in (
        ("selected_workflows", selected),
        ("workflow_owner_workflows", owner_workflows),
        ("workflow_context_workflows", context_workflows),
    ):
        if not _string_list(value):
            findings.append(Finding("behavior_event", label, f"invalid-list:{field}"))
    return findings


def _workflow_kind_findings(
    label: str,
    entry: dict[str, object],
) -> list[Finding]:
    """Validate fields conditioned on the selected attribution kind."""
    findings: list[Finding] = []
    attribution = entry.get("workflow_attribution_kind")
    if attribution not in WORKFLOW_ATTRIBUTION_KINDS:
        findings.append(Finding("behavior_event", label, "invalid-workflow-attribution-kind"))
    if attribution == "owner":
        findings.extend(_workflow_owner_findings(label, entry))
    elif attribution == "context":
        findings.extend(_workflow_context_findings(label, entry))
    elif attribution == "missing":
        findings.extend(_workflow_missing_findings(label, entry))

    return findings


def _workflow_owner_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate direct owner attribution fields."""
    owner = entry.get("workflow_owner", "")
    selected = entry.get("selected_workflows", [])
    owner_workflows = entry.get("workflow_owner_workflows", [])
    if (
        isinstance(owner, str)
        and owner.strip()
        and isinstance(selected, list)
        and selected
        and isinstance(owner_workflows, list)
        and owner_workflows
    ):
        if owner != selected[0] or owner_workflows != selected:
            return [Finding("behavior_event", label, "workflow-owner-fields-incoherent")]
        if _workflow_owner_optional_mismatch(entry, owner, selected):
            return [Finding("behavior_event", label, "workflow-owner-fields-incoherent")]
        if any(
            _workflow_value_present(entry.get(field, default))
            for field, default in (
                ("workflow_context_kind", ""),
                ("workflow_context_source", ""),
                ("workflow_context_workflows", []),
                ("workflow_context_timestamp", ""),
                ("workflow_context_source_event", ""),
            )
        ):
            return [Finding("behavior_event", label, "workflow-owner-fields-incoherent")]
        return []
    return [Finding("behavior_event", label, "workflow-owner-fields-incoherent")]


def _workflow_owner_optional_mismatch(
    entry: dict[str, object],
    owner: str,
    selected: list[object],
) -> bool:
    """Return whether optional owner carriers disagree with selected workflows."""
    expected_count = len(selected)
    mismatches = (
        "selected_workflow" in entry and entry["selected_workflow"] != owner,
        "workflow" in entry and entry["workflow"] != selected,
        "workflow_family" in entry and entry["workflow_family"] != owner,
        "workflow_selection_kind" in entry
        and entry["workflow_selection_kind"] != "declared_workflow",
        "selected_workflow_count" in entry
        and entry["selected_workflow_count"] != expected_count,
    )
    return any(mismatches)


def _workflow_context_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate inherited context attribution fields."""
    workflows = entry.get("workflow_context_workflows", [])
    kind = entry.get("workflow_context_kind", "")
    source = entry.get("workflow_context_source", "")
    timestamp = entry.get("workflow_context_timestamp", "")
    source_event = entry.get("workflow_context_source_event", "")
    owner_carriers = (
        ("selected_workflow", entry.get("selected_workflow", "")),
        ("selected_workflows", entry.get("selected_workflows", [])),
        ("workflow", entry.get("workflow", [])),
        ("workflow_family", entry.get("workflow_family", "")),
        ("workflow_owner", entry.get("workflow_owner", "")),
        ("workflow_owner_workflows", entry.get("workflow_owner_workflows", [])),
        ("selected_workflow_count", entry.get("selected_workflow_count", 0)),
    )
    selection_kind = entry.get("workflow_selection_kind", "")
    coherent_context = (
        isinstance(workflows, list)
        and bool(workflows)
        and isinstance(kind, str)
        and bool(kind.strip())
        and isinstance(source, str)
        and bool(source.strip())
        and isinstance(timestamp, str)
        and bool(timestamp.strip())
        and isinstance(source_event, str)
        and bool(source_event.strip())
        and selection_kind == "context_workflow"
    )
    if coherent_context and not any(_workflow_value_present(value) for _field, value in owner_carriers):
        return []
    return [Finding("behavior_event", label, "workflow-context-fields-incoherent")]


def _workflow_missing_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate explicit empty sentinels for missing attribution."""
    fields = (
        ("selected_workflow", entry.get("selected_workflow", "")),
        ("selected_workflows", entry.get("selected_workflows", [])),
        ("workflow", entry.get("workflow", [])),
        ("workflow_family", entry.get("workflow_family", "")),
        ("workflow_selection_kind", entry.get("workflow_selection_kind", "")),
        ("workflow_owner", entry.get("workflow_owner", "")),
        ("workflow_owner_workflows", entry.get("workflow_owner_workflows", [])),
        ("workflow_context_kind", entry.get("workflow_context_kind", "")),
        ("workflow_context_source", entry.get("workflow_context_source", "")),
        ("workflow_context_workflows", entry.get("workflow_context_workflows", [])),
        ("workflow_context_timestamp", entry.get("workflow_context_timestamp", "")),
        ("workflow_context_source_event", entry.get("workflow_context_source_event", "")),
        ("selected_workflow_count", entry.get("selected_workflow_count", 0)),
    )
    return [] if all(not _workflow_value_present(value) for _field, value in fields) else [
        Finding("behavior_event", label, "workflow-missing-fields-incoherent")
    ]


def _workflow_value_present(value: object) -> bool:
    """Return whether an attribution carrier contains a nonempty value."""
    if value is None or value is False or value == "" or value == [] or value == 0:
        return False
    return True


def _behavior_prompt_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate redacted prompt evidence and typed missing sentinels."""
    findings: list[Finding] = []
    prompt_status = entry.get("prompt_capture_status")
    excerpt = entry.get("prompt_excerpt_redacted")
    fingerprint = entry.get("prompt_fingerprint")
    char_count = entry.get("prompt_char_count")
    truncated = entry.get("prompt_excerpt_truncated")
    if prompt_status not in PROMPT_CAPTURE_STATUSES:
        findings.append(Finding("behavior_event", label, "invalid-prompt-capture-status"))
    if not isinstance(excerpt, str) or len(excerpt) > 600:
        findings.append(Finding("behavior_event", label, "invalid-prompt-excerpt"))
    if not isinstance(fingerprint, str):
        findings.append(Finding("behavior_event", label, "invalid-prompt-fingerprint"))
    if not _nonnegative_int(char_count):
        findings.append(Finding("behavior_event", label, "invalid-prompt-char-count"))
    if not isinstance(truncated, bool):
        findings.append(Finding("behavior_event", label, "invalid-prompt-truncated"))
    if prompt_status == "present":
        findings.extend(_prompt_present_findings(label, excerpt, fingerprint, char_count))
    elif prompt_status == "missing":
        if (excerpt, fingerprint, char_count, truncated) != ("", "", 0, False):
            findings.append(Finding("behavior_event", label, "prompt-missing-fields-incoherent"))
    cause = entry.get("prompt_capture_reason")
    if cause is not None and (not isinstance(cause, str) or not PROMPT_CAPTURE_CAUSE_RE.fullmatch(cause)):
        findings.append(Finding("behavior_event", label, "invalid-prompt-capture-reason"))
    return findings


def _prompt_present_findings(
    label: str,
    excerpt: object,
    fingerprint: object,
    char_count: object,
) -> list[Finding]:
    """Validate present-prompt identity fields and conservative redaction."""
    findings: list[Finding] = []
    if (
        not isinstance(fingerprint, str)
        or PROMPT_FINGERPRINT_RE.fullmatch(fingerprint) is None
        or not isinstance(char_count, int)
        or char_count <= 0
    ):
        findings.append(Finding("behavior_event", label, "prompt-present-fields-incoherent"))
    if isinstance(excerpt, str) and redact_sensitive_text(excerpt) != excerpt:
        findings.append(Finding("behavior_event", label, "prompt-excerpt-secret-material"))
    return findings


def behavior_event_findings(label: str, entry: dict[str, object]) -> list[Finding]:
    """Validate the bounded attribution and prompt fields of a new behavior event."""
    if entry.get("schema") != BEHAVIOR_EVENT_SCHEMA:
        if BEHAVIOR_HINT_FIELDS.intersection(entry):
            return [Finding("behavior_event", label, "legacy-behavior-schema")]
        return []
    return [
        *_behavior_envelope_findings(label, entry),
        *_behavior_workflow_findings(label, entry),
        *_behavior_prompt_findings(label, entry),
    ]


def parse_hook_line(root: Path, path: Path, line_no: int, raw_line: str) -> tuple[str, int, list[Finding]]:
    """Parse one hook JSONL line and return its run id plus findings."""
    label = f"{relative(root, path)}:{line_no}"
    try:
        loaded = json.loads(raw_line)
    except json.JSONDecodeError:
        return "", 0, [Finding("hook_jsonl", label, "invalid-json")]
    if not isinstance(loaded, dict):
        return "", 0, [Finding("hook_jsonl", label, "entry-not-object")]
    entry = cast(dict[str, object], loaded)
    namespaced = path.parent.name not in ("hook-runs", "legacy-import")
    required_fields = HOOK_REQUIRED_FIELDS if namespaced else (
        "hook_run_id",
        "timestamp",
        "payload_fingerprint",
    )
    findings = [
        Finding("hook_jsonl", label, f"missing-field:{field}")
        for field in required_fields
        if not isinstance(entry.get(field), str) or not str(entry.get(field)).strip()
    ]
    legacy_missing_namespace = 0
    if namespaced and not isinstance(entry.get("hook_log_namespace"), str):
        legacy_missing_namespace = 1
    findings.extend(behavior_event_findings(label, entry))
    run_id = entry.get("hook_run_id")
    return (run_id if isinstance(run_id, str) else ""), legacy_missing_namespace, findings


def hook_result_findings(root: Path, hook_dirs: Sequence[Path]) -> tuple[int, int, int, list[Finding]]:
    """Validate hook JSONL files."""
    findings: list[Finding] = []
    seen_run_ids: dict[str, str] = {}
    files = sorted(
        {
            path
            for hook_dir in hook_dirs
            if hook_dir.is_dir()
            for path in hook_dir.rglob("*.jsonl")
        }
    )
    entries = 0
    legacy_missing_namespace = 0
    for path in files:
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            entries += 1
            run_id, line_legacy_missing_namespace, line_findings = parse_hook_line(
                root, path, line_no, raw_line
            )
            legacy_missing_namespace += line_legacy_missing_namespace
            findings.extend(line_findings)
            if not run_id:
                continue
            previous = seen_run_ids.get(run_id)
            label = f"{relative(root, path)}:{line_no}"
            if previous is not None:
                findings.append(Finding("hook_run_id", label, f"duplicate:{previous}"))
            seen_run_ids[run_id] = label
    if files and entries == 0:
        labels = ",".join(relative(root, hook_dir) for hook_dir in hook_dirs)
        findings.append(Finding("hook_jsonl", labels, "no-hook-entries"))
    findings.extend(ignored_path_findings(root, files))
    return len(files), entries, legacy_missing_namespace, findings


def markdown_reports(results_dirs: Sequence[Path]) -> tuple[Path, ...]:
    """Return unique Markdown reports from multiple result directories."""
    return tuple(
        sorted(
            {
                path
                for results_dir in results_dirs
                if results_dir.is_dir()
                for path in results_dir.glob("*.md")
                if path.name != "README.md"
            }
        )
    )


def missing_reports_label(root: Path, results_dirs: Sequence[Path]) -> str:
    """Return a bounded path label for a missing report family."""
    return ",".join(relative(root, path) for path in results_dirs)


def reports_required(results_dirs: Sequence[Path], *, archive_mounted: bool) -> bool:
    """Return whether absence of a report family is a validation failure."""
    return archive_mounted or any(results_dir.is_dir() for results_dir in results_dirs)


def resolve_family_registry(canon_root: Path, registry_value: str) -> Path:
    """Resolve the eval family registry path."""
    return resolve_eval_manifest(canon_root, registry_value)


def load_family_contracts(registry_path: Path) -> tuple[EvalFamilyContract, ...]:
    """Load accumulated eval family contracts from TOML."""
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    families = data.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("eval family registry must define at least one [[families]] entry")
    contracts: list[EvalFamilyContract] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for raw_family in cast(list[object], families):
        if not isinstance(raw_family, dict):
            raise ValueError("eval family registry entries must be TOML tables")
        family = cast(dict[str, object], raw_family)
        values: dict[str, str] = {}
        for field in (
            "id",
            "check_id",
            "count_label",
            "summary",
            "producer",
            "filename_regex",
            "run_id_regex",
            "missing_reports_detail",
            "missing_run_id_detail",
            "duplicate_run_id_detail",
        ):
            value = family.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"eval family registry entry missing string field: {field}")
            values[field] = value.strip()
        if values["id"] in seen_ids:
            raise ValueError(f"duplicate eval family id: {values['id']}")
        if values["count_label"] in seen_labels:
            raise ValueError(f"duplicate eval family count label: {values['count_label']}")
        re.compile(values["filename_regex"])
        re.compile(values["run_id_regex"])
        seen_ids.add(values["id"])
        seen_labels.add(values["count_label"])
        contracts.append(
            EvalFamilyContract(
                family_id=values["id"],
                check_id=values["check_id"],
                count_label=values["count_label"],
                summary=values["summary"],
                producer=values["producer"],
                filename_regex=values["filename_regex"],
                run_id_regex=values["run_id_regex"],
                missing_reports_detail=values["missing_reports_detail"],
                missing_run_id_detail=values["missing_run_id_detail"],
                duplicate_run_id_detail=values["duplicate_run_id_detail"],
            )
        )
    return tuple(contracts)


def eval_family_findings(
    root: Path,
    contract: EvalFamilyContract,
    results_dirs: Sequence[Path],
    *,
    require_reports: bool,
) -> tuple[int, list[Finding]]:
    """Validate one accumulated eval report family declared by the registry."""
    findings: list[Finding] = []
    reports = markdown_reports(results_dirs)
    seen_run_ids: dict[str, str] = {}
    filename_pattern = re.compile(contract.filename_regex)
    run_id_pattern = re.compile(contract.run_id_regex)
    if not reports and require_reports:
        findings.append(
            Finding(
                contract.check_id,
                missing_reports_label(root, results_dirs),
                contract.missing_reports_detail,
            )
        )
    for path in reports:
        rel_path = relative(root, path)
        if not filename_pattern.fullmatch(path.name):
            findings.append(Finding(contract.check_id, rel_path, "invalid-report-name"))
        text = path.read_text(encoding="utf-8")
        run_id_match = run_id_pattern.search(text)
        if run_id_match is None:
            findings.append(Finding(contract.check_id, rel_path, contract.missing_run_id_detail))
            continue
        run_id = run_id_match.group(1)
        previous = seen_run_ids.get(run_id)
        if previous is not None:
            findings.append(
                Finding(contract.check_id, rel_path, f"{contract.duplicate_run_id_detail}:{previous}")
            )
        seen_run_ids[run_id] = rel_path
    findings.extend(ignored_path_findings(root, reports))
    return len(reports), findings


def validate(
    root: Path,
    family_registry: str = DEFAULT_FAMILY_REGISTRY.as_posix(),
    runtime_root: Path | str | None = None,
) -> EvalAccumulationReport:
    """Validate accumulated eval results."""
    requested_root = root.resolve()
    canon_root = agent_canon_root(requested_root)
    contracts = load_family_contracts(resolve_family_registry(canon_root, family_registry))
    findings: list[Finding] = []
    hook_files, hook_entries, hook_legacy_missing_namespace, hook_findings = hook_result_findings(
        canon_root,
        hook_result_search_dirs(requested_root, canon_root, runtime_root),
    )
    archive_mounted = mounted_log_archive_root(canon_root, runtime_root).is_dir()
    eval_report_counts: dict[str, int] = {}
    findings.extend(hook_findings)
    for contract in contracts:
        results_dirs = eval_result_search_dirs(canon_root, contract.family_id, runtime_root)
        report_count, family_findings = eval_family_findings(
            canon_root,
            contract,
            results_dirs,
            require_reports=reports_required(results_dirs, archive_mounted=archive_mounted),
        )
        eval_report_counts[contract.family_id] = report_count
        findings.extend(family_findings)
    return EvalAccumulationReport(
        hook_files=hook_files,
        hook_entries=hook_entries,
        hook_legacy_missing_namespace=hook_legacy_missing_namespace,
        eval_report_counts=eval_report_counts,
        findings=tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
    )


def render_json(report: EvalAccumulationReport) -> str:
    """Render JSON output."""
    blocking = blocking_findings(report)
    warnings = warning_findings(report)
    return json.dumps(
        {
            "status": report_status(report),
            "hook_files": report.hook_files,
            "hook_entries": report.hook_entries,
            "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
            "hook_namespace_debt": report.hook_legacy_missing_namespace,
            "eval_report_counts": report.eval_report_counts,
            "skill_reports": eval_report_count(report, "skill-workflow-prompt"),
            "workflow_selection_reports": eval_report_count(report, "workflow-selection"),
            "report_quality_reports": eval_report_count(report, "report-quality"),
            "codex_agent_role_reports": eval_report_count(report, "codex-agent-role"),
            "blocking_finding_count": len(blocking),
            "warning_count": len(warnings),
            "findings": [asdict(item) for item in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def eval_report_count(report: EvalAccumulationReport, family_id: str) -> int:
    """Return a report count for one family id."""
    return report.eval_report_counts.get(family_id, 0)


def eval_family_count_lines(report: EvalAccumulationReport) -> list[str]:
    """Return generic per-family count lines without dynamic field names."""
    return [
        f"EVAL_ACCUMULATION_FAMILY_REPORTS={family_id}:{count}"
        for family_id, count in sorted(report.eval_report_counts.items())
    ]


def compact_summary(report: EvalAccumulationReport) -> dict[str, object]:
    """Return a bounded JSON-friendly accumulation summary."""
    finding_counts: dict[str, int] = {}
    for finding in report.findings:
        finding_counts[finding.check] = finding_counts.get(finding.check, 0) + 1
    blocking = blocking_findings(report)
    warnings = warning_findings(report)
    return {
        "status": report_status(report),
        "finding_count": len(report.findings),
        "blocking_finding_count": len(blocking),
        "warning_count": len(warnings),
        "finding_counts": dict(sorted(finding_counts.items())),
        "hook_files": report.hook_files,
        "hook_entries": report.hook_entries,
        "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
        "hook_namespace_debt": report.hook_legacy_missing_namespace,
        "eval_report_counts": report.eval_report_counts,
        "skill_reports": eval_report_count(report, "skill-workflow-prompt"),
        "workflow_selection_reports": eval_report_count(report, "workflow-selection"),
        "report_quality_reports": eval_report_count(report, "report-quality"),
        "codex_agent_role_reports": eval_report_count(report, "codex-agent-role"),
        "blocking_finding_samples": [
            asdict(finding) for finding in blocking[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
        "warning_samples": [
            asdict(finding) for finding in warnings[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
        "finding_samples": [
            asdict(finding) for finding in report.findings[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
    }


def write_compact_summary(
    source_root: Path,
    path: Path,
    report: EvalAccumulationReport,
    runtime_root: Path | str | None = None,
) -> Path:
    """Write a bounded JSON summary for agent consumption."""
    boundary = runtime_artifact_boundary(source_root, runtime_root)
    return boundary.atomic_write_text(
        path,
        json.dumps(compact_summary(report), indent=2, sort_keys=True) + "\n",
    )


def render_text(
    report: EvalAccumulationReport,
    *,
    include_details: bool = True,
    compact_out: Path | None = None,
) -> str:
    """Render machine-readable text output."""
    blocking = blocking_findings(report)
    warnings = warning_findings(report)
    lines: list[str] = []
    if include_details:
        lines.extend(finding.render() for finding in report.findings)
    lines.extend(
        [
            f"EVAL_ACCUMULATION_HOOK_FILES={report.hook_files}",
            f"EVAL_ACCUMULATION_HOOK_ENTRIES={report.hook_entries}",
            "EVAL_ACCUMULATION_HOOK_LEGACY_MISSING_NAMESPACE="
            f"{report.hook_legacy_missing_namespace}",
            f"EVAL_ACCUMULATION_HOOK_NAMESPACE_DEBT={report.hook_legacy_missing_namespace}",
            f"EVAL_ACCUMULATION_SKILL_REPORTS={eval_report_count(report, 'skill-workflow-prompt')}",
            "EVAL_ACCUMULATION_WORKFLOW_SELECTION_REPORTS="
            f"{eval_report_count(report, 'workflow-selection')}",
            f"EVAL_ACCUMULATION_REPORT_QUALITY_REPORTS={eval_report_count(report, 'report-quality')}",
            f"EVAL_ACCUMULATION_CODEX_AGENT_ROLE_REPORTS={eval_report_count(report, 'codex-agent-role')}",
            *eval_family_count_lines(report),
            f"EVAL_ACCUMULATION_FINDINGS={len(report.findings)}",
            f"EVAL_ACCUMULATION_BLOCKING_FINDINGS={len(blocking)}",
            f"EVAL_ACCUMULATION_WARNINGS={len(warnings)}",
            f"EVAL_ACCUMULATION={report_status(report)}",
        ]
    )
    if compact_out is not None:
        lines.append(f"EVAL_ACCUMULATION_COMPACT_OUT={compact_out.as_posix()}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the eval accumulation checker."""
    args = build_parser().parse_args(argv)
    try:
        report = validate(args.root, str(args.family_registry), args.runtime_root)
    except RuntimeError as error:
        if "AgentCanon log archive root is required" not in str(error) and not isinstance(
            error, RuntimeArtifactError
        ):
            raise
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_code": "log_archive_required",
                        "message": str(error),
                        "next_action": "pass --runtime-root or set AGENT_CANON_RUNTIME_ROOT",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("EVAL_ACCUMULATION=error")
            print("EVAL_ACCUMULATION_ERROR_CODE=log_archive_required")
            print(f"EVAL_ACCUMULATION_ERROR={error}")
            print("NEXT_ACTION=pass_--runtime-root_or_set_AGENT_CANON_RUNTIME_ROOT")
        return 1
    if args.compact_out is not None:
        write_compact_summary(args.root, args.compact_out, report, args.runtime_root)
    if args.format == "json":
        print(render_json(report))
    else:
        print(
            render_text(
                report,
                include_details=args.compact_out is None,
                compact_out=args.compact_out,
            ),
            end="",
        )
    return 1 if blocking_findings(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
