#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Compares observed repository trees with the AgentCanon structure contract.
# upstream design ../../documents/repo-structure-contract.toml expected repository structure profiles
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared root surface policy
# upstream design ../../documents/tools/README.md tool entrypoint policy
# downstream implementation ../../tests/agent_tools/test_repo_structure_contract.py tests tree and contract comparison
# @dependency-end
"""Compare a repository tree with the AgentCanon structure contract."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast
import tomllib

DEFAULT_CONTRACT = "documents/repo-structure-contract.toml"
ERROR = "error"
WARN = "warn"
TREE_KIND_MAP = {
    "directory": "dir",
    "file": "file",
    "link": "link",
}


@dataclass(frozen=True)
class Finding:
    """One structure contract finding."""

    severity: str
    category: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"REPO_STRUCTURE_FINDING={self.severity}:{self.category}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class ExpectedPath:
    """One expected repository path from the contract."""

    path: str
    kind: str
    category: str


@dataclass(frozen=True)
class Profile:
    """One repository structure profile."""

    profile_id: str
    summary: str
    detect_all: tuple[str, ...]
    allowed_top_level: tuple[str, ...]
    extra_top_level_severity: str
    required: tuple[ExpectedPath, ...]
    optional: tuple[ExpectedPath, ...]


@dataclass(frozen=True)
class IgnoreRules:
    """Ignored path rules from the contract defaults."""

    names: tuple[str, ...]
    globs: tuple[str, ...]


@dataclass(frozen=True)
class PathRecord:
    """One observed path and path kind."""

    path: str
    kind: str


@dataclass(frozen=True)
class StructureReport:
    """Structure comparison result."""

    status: str
    profile: str
    tree_source: str
    checked_paths: int
    findings: tuple[Finding, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--contract",
        default=DEFAULT_CONTRACT,
        help="Structure contract path relative to root, or an absolute path.",
    )
    parser.add_argument(
        "--profile",
        default="auto",
        help="Profile id to check. Defaults to auto detection from the contract.",
    )
    parser.add_argument(
        "--tree-json",
        help="JSON produced by `tree -a -J` from the repository root. Defaults to running tree.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--strict-extra-top-level",
        action="store_true",
        help="Treat top-level paths outside the profile contract as errors.",
    )
    return parser


def string_list(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from a TOML value."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def as_mapping(value: object) -> Mapping[str, object]:
    """Return a string-keyed mapping or an empty mapping."""
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return {}
    return cast(Mapping[str, object], mapping)


def normalize_path(path: str) -> str:
    """Normalize a repo-relative path for contract comparison."""
    normalized = path.replace("\\", "/").strip("/")
    if normalized in {"", "."}:
        return ""
    return normalized


def resolve_path(root: Path, path: str) -> Path:
    """Resolve a path relative to the root unless it is already absolute."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def expected_path(raw: object) -> ExpectedPath | None:
    """Parse one expected path entry from TOML."""
    mapping = as_mapping(raw)
    path = mapping.get("path")
    if not isinstance(path, str) or not path:
        return None
    kind = mapping.get("kind")
    category = mapping.get("category")
    return ExpectedPath(
        path=normalize_path(path),
        kind=kind if isinstance(kind, str) else "any",
        category=category if isinstance(category, str) else "contract",
    )


def expected_paths(raw: object) -> tuple[ExpectedPath, ...]:
    """Parse expected path entries from a TOML list."""
    if not isinstance(raw, list):
        return ()
    parsed = [expected_path(item) for item in raw]
    return tuple(item for item in parsed if item is not None)


def load_contract(root: Path, contract_path: str) -> tuple[IgnoreRules, tuple[Profile, ...]]:
    """Load structure contract defaults and profiles."""
    path = resolve_path(root, contract_path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("catalog_kind") != "agent_canon_repo_structure_contract":
        raise ValueError(f"invalid structure contract kind: {path}")
    defaults = as_mapping(raw.get("defaults"))
    profiles_raw = raw.get("profile")
    if not isinstance(profiles_raw, list):
        raise ValueError(f"missing profile list in structure contract: {path}")
    ignore_rules = IgnoreRules(
        names=string_list(defaults.get("ignore_names")),
        globs=string_list(defaults.get("ignore_globs")),
    )
    profiles: list[Profile] = []
    for raw_profile in profiles_raw:
        mapping = as_mapping(raw_profile)
        profile_id = mapping.get("id")
        if not isinstance(profile_id, str) or not profile_id:
            continue
        summary = mapping.get("summary")
        severity = mapping.get("extra_top_level_severity")
        profiles.append(
            Profile(
                profile_id=profile_id,
                summary=summary if isinstance(summary, str) else "",
                detect_all=string_list(mapping.get("detect_all")),
                allowed_top_level=string_list(mapping.get("allowed_top_level")),
                extra_top_level_severity=severity if severity in {ERROR, WARN} else WARN,
                required=expected_paths(mapping.get("required")),
                optional=expected_paths(mapping.get("optional")),
            )
        )
    if not profiles:
        raise ValueError(f"no valid profiles in structure contract: {path}")
    return ignore_rules, tuple(profiles)


def is_ignored(path: str, rules: IgnoreRules) -> bool:
    """Return whether a repo-relative path is ignored by contract defaults."""
    normalized = normalize_path(path)
    if not normalized:
        return False
    parts = normalized.split("/")
    if any(part in rules.names for part in parts):
        return True
    return any(
        fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(parts[-1], pattern)
        for pattern in rules.globs
    )


def records_from_tree_node(
    node: Mapping[str, object],
    parent: str,
    rules: IgnoreRules,
) -> list[PathRecord]:
    """Recursively convert one tree JSON node into path records."""
    name = node.get("name")
    if not isinstance(name, str):
        return []
    path = normalize_path(f"{parent}/{name}" if parent else name)
    if is_ignored(path, rules):
        return []
    raw_type = node.get("type")
    kind = TREE_KIND_MAP.get(raw_type, raw_type) if isinstance(raw_type, str) else "other"
    records = [PathRecord(path, kind if isinstance(kind, str) else "other")]
    contents = node.get("contents")
    if isinstance(contents, list):
        for child in contents:
            child_mapping = as_mapping(child)
            if child_mapping:
                records.extend(records_from_tree_node(child_mapping, path, rules))
    return records


def load_tree_json(path: Path, rules: IgnoreRules) -> tuple[PathRecord, ...]:
    """Load records from `tree -J` JSON output."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return records_from_tree_json(raw, rules)


def records_from_tree_json(raw: object, rules: IgnoreRules) -> tuple[PathRecord, ...]:
    """Convert parsed `tree -J` JSON output to path records."""
    roots = raw if isinstance(raw, list) else [raw]
    records: list[PathRecord] = []
    for root_node in roots:
        mapping = as_mapping(root_node)
        if not mapping:
            continue
        contents = mapping.get("contents")
        if isinstance(contents, list):
            for child in contents:
                child_mapping = as_mapping(child)
                if child_mapping:
                    records.extend(records_from_tree_node(child_mapping, "", rules))
        else:
            records.extend(records_from_tree_node(mapping, "", rules))
    return tuple(records)


def tree_ignore_pattern(rules: IgnoreRules) -> str:
    """Return the tree -I pattern derived from contract ignore names."""
    names = set(rules.names)
    for pattern in rules.globs:
        tail = pattern.rstrip("/").split("/")[-1]
        if tail and tail != "**":
            names.add(tail)
    return "|".join(sorted(names))


def run_tree(root: Path, rules: IgnoreRules) -> tuple[PathRecord, ...]:
    """Run tree and return observed path records."""
    command = ["tree", "-a", "-J", "--noreport"]
    ignore_pattern = tree_ignore_pattern(rules)
    if ignore_pattern:
        command.extend(["-I", ignore_pattern])
    command.append(str(root))
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    raw = json.loads(result.stdout)
    return records_from_tree_json(raw, rules)


def profile_detects(profile: Profile, observed: Mapping[str, str]) -> bool:
    """Return whether a profile matches the observed path set."""
    return all(path in observed for path in profile.detect_all)


def select_profile(requested: str, profiles: Sequence[Profile], observed: Mapping[str, str]) -> Profile:
    """Select a profile by id or by contract detection rules."""
    if requested != "auto":
        for profile in profiles:
            if profile.profile_id == requested:
                return profile
        raise ValueError(f"unknown repo structure profile: {requested}")
    for profile in profiles:
        if profile_detects(profile, observed):
            return profile
    raise ValueError("could not auto-detect repo structure profile")


def kind_matches(expected: str, actual: str | None) -> bool:
    """Return whether an observed kind satisfies the expected kind."""
    if actual is None:
        return False
    if expected == "any":
        return True
    return expected == actual


def top_level(path: str) -> str:
    """Return the first path component."""
    return normalize_path(path).split("/", 1)[0]


def compare_structure(
    profile: Profile,
    observed: Mapping[str, str],
    strict_extra_top_level: bool,
) -> tuple[Finding, ...]:
    """Compare observed paths against the selected profile."""
    findings: list[Finding] = []
    for expected in profile.required:
        actual_kind = observed.get(expected.path)
        if actual_kind is None:
            findings.append(Finding(ERROR, expected.category, expected.path, f"missing-{expected.kind}"))
        elif not kind_matches(expected.kind, actual_kind):
            findings.append(
                Finding(
                    ERROR,
                    expected.category,
                    expected.path,
                    f"kind-mismatch:{actual_kind}!={expected.kind}",
                )
            )
    for expected in profile.optional:
        actual_kind = observed.get(expected.path)
        if actual_kind is not None and not kind_matches(expected.kind, actual_kind):
            findings.append(
                Finding(
                    WARN,
                    expected.category,
                    expected.path,
                    f"optional-kind-mismatch:{actual_kind}!={expected.kind}",
                )
            )
    allowed = set(profile.allowed_top_level)
    allowed.update(top_level(item.path) for item in (*profile.required, *profile.optional))
    extra_severity = ERROR if strict_extra_top_level else profile.extra_top_level_severity
    observed_top_level = sorted({top_level(path) for path in observed if "/" not in path})
    for item in observed_top_level:
        if item not in allowed:
            findings.append(
                Finding(extra_severity, "unexpected_top_level", item, "not-in-profile-contract")
            )
    return tuple(sorted(findings, key=lambda item: (item.severity, item.category, item.path, item.detail)))


def run_check(
    root: Path,
    contract_path: str,
    profile_id: str,
    tree_json: str | None,
    strict_extra_top_level: bool,
) -> StructureReport:
    """Run the structure contract check."""
    root = root.resolve()
    ignore_rules, profiles = load_contract(root, contract_path)
    if tree_json:
        tree_path = resolve_path(root, tree_json)
        records = load_tree_json(tree_path, ignore_rules)
        tree_source = f"tree-json:{tree_path}"
    else:
        records = run_tree(root, ignore_rules)
        tree_source = f"tree-command:{root}"
    observed = {record.path: record.kind for record in records}
    profile = select_profile(profile_id, profiles, observed)
    findings = compare_structure(profile, observed, strict_extra_top_level)
    status = "fail" if any(finding.severity == ERROR for finding in findings) else "pass"
    return StructureReport(
        status=status,
        profile=profile.profile_id,
        tree_source=tree_source,
        checked_paths=len(observed),
        findings=findings,
    )


def render_json(report: StructureReport) -> str:
    """Render JSON output."""
    return json.dumps(asdict(report), indent=2, sort_keys=True)


def render_text(report: StructureReport) -> None:
    """Render text output."""
    for finding in report.findings:
        print(finding.render())
    errors = sum(1 for finding in report.findings if finding.severity == ERROR)
    warnings = sum(1 for finding in report.findings if finding.severity == WARN)
    print(f"REPO_STRUCTURE_PROFILE={report.profile}")
    print(f"REPO_STRUCTURE_TREE_SOURCE={report.tree_source}")
    print(f"REPO_STRUCTURE_CHECKED_PATHS={report.checked_paths}")
    print(f"REPO_STRUCTURE_ERRORS={errors}")
    print(f"REPO_STRUCTURE_WARNINGS={warnings}")
    print(f"REPO_STRUCTURE={report.status}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    try:
        report = run_check(
            root=Path(args.root),
            contract_path=args.contract,
            profile_id=args.profile,
            tree_json=args.tree_json,
            strict_extra_top_level=args.strict_extra_top_level,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"REPO_STRUCTURE_ERROR={exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(render_json(report))
    else:
        render_text(report)
    return 1 if report.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
