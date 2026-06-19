#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates and materializes vendored third-party skill adapters.
# upstream design ../../vendor/README.md AgentCanon internal vendor ownership policy
# upstream design ../../vendor/skills/README.md third-party skill vendor contract
# upstream implementation ../../vendor/skills/manifest.toml third-party skill adapter manifest
# downstream implementation ./check_agent_runtime_alignment.py runs adapter validation
# downstream implementation ../../tests/agent_tools/test_vendor_skill_adapters.py verifies adapter behavior
# @dependency-end
"""Validate and materialize AgentCanon vendored third-party skill adapters."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
import tomllib

import yaml

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path("vendor/skills/manifest.toml")
SKILL_ROOT = Path(".agents/skills")
VENDOR_SKILL_ROOT = Path("vendor/skills")
PROMPT_EVAL_MANIFEST = Path("evidence/agent-evals/skill_workflow_prompt_eval.toml")
RUNTIME_SKILL_TARGET_GLOB = ".agents/skills/*/SKILL.md"
FRONTMATTER_SCAN_LINES = 24
SKILL_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROVIDER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$")
GITHUB_HTTPS_UPSTREAM_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s?#]+?)(?:\.git)?(?:[/?#].*)?$"
)
GITHUB_SSH_UPSTREAM_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/)(?P<owner>[^/\s]+)/(?P<repo>[^/\s?#]+?)(?:\.git)?(?:[/?#].*)?$"
)


@dataclass(frozen=True)
class Finding:
    """One vendor skill adapter validation finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding line."""
        return f"VENDOR_SKILL_ADAPTER_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class SkillFrontmatter:
    """The runtime-visible frontmatter fields required for one skill."""

    name: str
    description: str


@dataclass(frozen=True)
class VendorSkill:
    """One vendored third-party skill entry."""

    skill_id: str
    provider: str
    source: Path
    adapter: Path
    enabled: bool
    license_id: str
    upstream: str
    revision: str

    @property
    def source_skill(self) -> Path:
        """Return the vendored SKILL.md source."""
        return self.source / "SKILL.md"

    @property
    def adapter_skill(self) -> Path:
        """Return the runtime adapter SKILL.md path."""
        return self.adapter / "SKILL.md"


@dataclass(frozen=True)
class VendorSkillManifest:
    """Parsed third-party skill manifest."""

    path: Path
    entries: tuple[VendorSkill, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class ManifestOwnershipPolicy:
    """Validate manifest fields that attach external repositories under vendor."""

    index: int
    skill_id: str
    provider: str
    source_text: str
    upstream: str

    def validate(self) -> list[Finding]:
        """Return ownership findings for one external skill import."""
        findings: list[Finding] = []
        if self.provider and not PROVIDER_RE.fullmatch(self.provider):
            findings.append(
                Finding("manifest", f"skills[{self.index}].provider", "invalid-github-owner-provider")
            )
        if self.source_text and self.provider and self.skill_id:
            expected_source = VENDOR_SKILL_ROOT / self.provider / self.skill_id
            if Path(self.source_text) != expected_source:
                findings.append(
                    Finding(
                        "manifest",
                        self.source_text,
                        f"source-must-match-provider-skill:{expected_source.as_posix()}",
                    )
                )
        if self.upstream and self.provider:
            owner = github_upstream_owner(self.upstream)
            if owner is not None and owner != self.provider:
                findings.append(
                    Finding(
                        "manifest",
                        f"skills[{self.index}].upstream",
                        f"github-owner-must-match-provider:{owner}!={self.provider}",
                    )
                )
        return findings


@dataclass(frozen=True)
class SyncAction:
    """One filesystem action used to expose a vendored skill."""

    action: str
    path: Path

    def render(self, root: Path) -> str:
        """Render one stable sync action line."""
        return f"VENDOR_SKILL_ADAPTER_ACTION={self.action}:{relative_to_root(self.path, root)}"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="AgentCanon source root. Defaults to this script's repository root.",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Manifest path relative to root. Defaults to vendor/skills/manifest.toml.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Create missing enabled adapter symlinks, then validate.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def as_mapping(value: object) -> Mapping[str, object] | None:
    """Return a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(Mapping[str, object], mapping)


def as_sequence(value: object) -> Sequence[object] | None:
    """Return a sequence, excluding strings."""
    if isinstance(value, str):
        return None
    if isinstance(value, Sequence):
        return cast(Sequence[object], value)
    return None


def string_field(mapping: Mapping[str, object], field: str, index: int) -> tuple[str, list[Finding]]:
    """Read one required string field."""
    value = mapping.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip(), []
    return "", [Finding("manifest", f"skills[{index}].{field}", "missing-string")]


def bool_field(mapping: Mapping[str, object], field: str, index: int) -> tuple[bool, list[Finding]]:
    """Read one required boolean field."""
    value = mapping.get(field)
    if isinstance(value, bool):
        return value, []
    return False, [Finding("manifest", f"skills[{index}].{field}", "missing-boolean")]


def relative_to_root(path: Path, root: Path) -> str:
    """Render a path relative to root when possible."""
    root_path = root.resolve()
    absolute_path = path if path.is_absolute() else root_path / path
    try:
        return absolute_path.absolute().relative_to(root_path).as_posix()
    except ValueError:
        return path.as_posix()


def is_relative_path(path_text: str) -> bool:
    """Return whether one manifest path is relative and does not traverse upward."""
    path = Path(path_text)
    return not path.is_absolute() and ".." not in path.parts


def validate_contained_path(root: Path, path: Path, container: Path, label: str) -> list[Finding]:
    """Return findings if path is outside its expected container."""
    findings: list[Finding] = []
    root_path = root.resolve()
    absolute_path = path if path.is_absolute() else root_path / path
    try:
        absolute_path.absolute().relative_to((root_path / container).absolute())
    except ValueError:
        findings.append(
            Finding("manifest", relative_to_root(path, root), f"{label}-outside-{container}")
        )
    return findings


def github_upstream_owner(upstream: str) -> str | None:
    """Return the GitHub owner or organization when upstream is a GitHub URL."""
    for pattern in (GITHUB_HTTPS_UPSTREAM_RE, GITHUB_SSH_UPSTREAM_RE):
        match = pattern.fullmatch(upstream)
        if match is not None:
            return match.group("owner").lower()
    return None


def parse_frontmatter(skill_path: Path) -> tuple[SkillFrontmatter | None, list[Finding]]:
    """Parse the required frontmatter fields from one SKILL.md file."""
    if not skill_path.is_file():
        return None, [Finding("skill", skill_path.as_posix(), "missing-skill-md")]
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None, [Finding("skill", skill_path.as_posix(), "missing-frontmatter")]

    closing_index = None
    for index, line in enumerate(lines[1:FRONTMATTER_SCAN_LINES], start=1):
        if line.strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        return None, [Finding("skill", skill_path.as_posix(), "missing-frontmatter-close")]

    fields: dict[str, str] = {}
    for line in lines[1:closing_index]:
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    name = fields.get("name", "")
    description = fields.get("description", "")
    findings: list[Finding] = []
    if not name:
        findings.append(Finding("skill", skill_path.as_posix(), "missing-name"))
    if not description:
        findings.append(Finding("skill", skill_path.as_posix(), "missing-description"))
    if findings:
        return None, findings
    return SkillFrontmatter(name=name, description=description), []


def load_canonical_skill_ids(root: Path) -> set[str]:
    """Return public AgentCanon skill ids reserved by the canonical catalog."""
    catalog_path = root / "agents" / "skills" / "catalog.yaml"
    if not catalog_path.is_file():
        return set()
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    data = as_mapping(raw)
    if data is None:
        return set()
    entries = as_sequence(data.get("skill_families")) or ()
    result: set[str] = set()
    for entry in entries:
        mapping = as_mapping(entry)
        if mapping is None:
            continue
        skill_id = mapping.get("id")
        if isinstance(skill_id, str):
            result.add(skill_id)
    return result


def parse_entry(root: Path, raw_entry: object, index: int) -> tuple[VendorSkill | None, list[Finding]]:
    """Parse one manifest entry."""
    mapping = as_mapping(raw_entry)
    if mapping is None:
        return None, [Finding("manifest", f"skills[{index}]", "entry-not-mapping")]

    skill_id, findings = string_field(mapping, "id", index)
    provider, provider_findings = string_field(mapping, "provider", index)
    source_text, source_findings = string_field(mapping, "source", index)
    enabled, enabled_findings = bool_field(mapping, "enabled", index)
    license_id, license_findings = string_field(mapping, "license", index)
    upstream, upstream_findings = string_field(mapping, "upstream", index)
    revision, revision_findings = string_field(mapping, "revision", index)
    findings.extend(provider_findings)
    findings.extend(source_findings)
    findings.extend(enabled_findings)
    findings.extend(license_findings)
    findings.extend(upstream_findings)
    findings.extend(revision_findings)

    adapter_value = mapping.get("adapter")
    adapter_text = str(adapter_value).strip() if isinstance(adapter_value, str) else ""
    if not adapter_text and skill_id:
        adapter_text = f".agents/skills/{skill_id}"

    if skill_id and not SKILL_ID_RE.fullmatch(skill_id):
        findings.append(Finding("manifest", f"skills[{index}].id", "invalid-skill-id"))
    if source_text and not is_relative_path(source_text):
        findings.append(Finding("manifest", f"skills[{index}].source", "must-be-relative-contained-path"))
    if adapter_text and not is_relative_path(adapter_text):
        findings.append(Finding("manifest", f"skills[{index}].adapter", "must-be-relative-contained-path"))
    findings.extend(
        ManifestOwnershipPolicy(
            index=index,
            skill_id=skill_id,
            provider=provider,
            source_text=source_text,
            upstream=upstream,
        ).validate()
    )

    source = root / source_text
    adapter = root / adapter_text
    if source_text:
        findings.extend(validate_contained_path(root, source, VENDOR_SKILL_ROOT, "source"))
    if adapter_text:
        findings.extend(validate_contained_path(root, adapter, SKILL_ROOT, "adapter"))
    if skill_id and adapter_text and adapter != root / SKILL_ROOT / skill_id:
        findings.append(Finding("manifest", adapter_text, "adapter-must-match-id"))

    if findings:
        return None, findings
    return (
        VendorSkill(
            skill_id=skill_id,
            provider=provider,
            source=source,
            adapter=adapter,
            enabled=enabled,
            license_id=license_id,
            upstream=upstream,
            revision=revision,
        ),
        [],
    )


def load_manifest(root: Path, manifest_path: Path) -> VendorSkillManifest:
    """Load and parse the third-party skill manifest."""
    findings: list[Finding] = []
    if not manifest_path.is_file():
        return VendorSkillManifest(
            path=manifest_path,
            entries=(),
            findings=(Finding("manifest", relative_to_root(manifest_path, root), "missing-file"),),
        )
    raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    data = as_mapping(raw)
    if data is None:
        return VendorSkillManifest(
            path=manifest_path,
            entries=(),
            findings=(Finding("manifest", relative_to_root(manifest_path, root), "must-be-mapping"),),
        )
    if data.get("version") != 1:
        findings.append(Finding("manifest", relative_to_root(manifest_path, root), "unsupported-version"))
    entries_raw = as_sequence(data.get("skills")) if "skills" in data else ()
    if entries_raw is None:
        findings.append(Finding("manifest", "skills", "must-be-list"))
        entries_raw = ()

    entries: list[VendorSkill] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(entries_raw, start=1):
        entry, entry_findings = parse_entry(root, raw_entry, index)
        findings.extend(entry_findings)
        if entry is None:
            continue
        if entry.skill_id in seen:
            findings.append(Finding("manifest", entry.skill_id, "duplicate-id"))
            continue
        seen.add(entry.skill_id)
        entries.append(entry)
    return VendorSkillManifest(manifest_path, tuple(entries), tuple(findings))


class VendorSkillValidator:
    """Validate and sync the AgentCanon third-party skill adapter surface."""

    def __init__(self, root: Path, manifest: Path = DEFAULT_MANIFEST) -> None:
        """Store repository paths."""
        self.root = root.resolve()
        self.manifest = manifest if manifest.is_absolute() else self.root / manifest

    def validate(self, require_adapters: bool = True) -> list[Finding]:
        """Return validation findings for the manifest and runtime adapters."""
        parsed = load_manifest(self.root, self.manifest)
        findings = list(parsed.findings)
        canonical_ids = load_canonical_skill_ids(self.root)

        for entry in parsed.entries:
            findings.extend(self.validate_entry(entry, canonical_ids, require_adapters))
        if require_adapters:
            findings.extend(self.validate_prompt_eval_coverage())
        return sorted(findings, key=lambda finding: (finding.check, finding.path, finding.detail))

    def validate_entry(
        self,
        entry: VendorSkill,
        canonical_ids: set[str],
        require_adapters: bool,
    ) -> list[Finding]:
        """Return findings for one vendored skill entry."""
        findings: list[Finding] = []
        if entry.skill_id in canonical_ids:
            findings.append(Finding("manifest", entry.skill_id, "conflicts-with-canonical-skill"))
        if not entry.source.is_dir():
            findings.append(Finding("source", relative_to_root(entry.source, self.root), "missing-source-dir"))
            return findings

        frontmatter, source_findings = parse_frontmatter(entry.source_skill)
        findings.extend(
            Finding(finding.check, relative_to_root(Path(finding.path), self.root), finding.detail)
            for finding in source_findings
        )
        if frontmatter is not None and frontmatter.name != entry.skill_id:
            findings.append(
                Finding(
                    "source",
                    relative_to_root(entry.source_skill, self.root),
                    f"frontmatter-name-mismatch:{frontmatter.name}",
                )
            )

        if entry.enabled:
            findings.extend(self.validate_enabled_adapter(entry, require_adapters))
        elif entry.adapter.exists():
            findings.append(
                Finding(
                    "adapter",
                    relative_to_root(entry.adapter, self.root),
                    "disabled-entry-adapter-present",
                )
            )
        return findings

    def validate_enabled_adapter(self, entry: VendorSkill, require_adapters: bool) -> list[Finding]:
        """Return findings for an enabled runtime adapter."""
        if not require_adapters and not entry.adapter.exists():
            return []
        if not entry.adapter.exists():
            return [Finding("adapter", relative_to_root(entry.adapter, self.root), "missing-adapter")]
        if entry.adapter.resolve() != entry.source.resolve():
            return [
                Finding(
                    "adapter",
                    relative_to_root(entry.adapter, self.root),
                    "adapter-must-symlink-to-source",
                )
            ]
        if not entry.adapter_skill.is_file():
            return [Finding("adapter", relative_to_root(entry.adapter_skill, self.root), "missing-skill-md")]
        return []

    def sync(self) -> tuple[list[Finding], list[SyncAction]]:
        """Create missing adapter symlinks for enabled entries."""
        preflight_findings = self.validate(require_adapters=False)
        if preflight_findings:
            return preflight_findings, []

        parsed = load_manifest(self.root, self.manifest)
        actions: list[SyncAction] = []
        for entry in parsed.entries:
            if not entry.enabled:
                continue
            if entry.adapter.exists() and entry.adapter.resolve() == entry.source.resolve():
                continue
            if entry.adapter.exists():
                return [
                    Finding(
                        "adapter",
                        relative_to_root(entry.adapter, self.root),
                        "adapter-exists-and-is-not-managed-symlink",
                    )
                ], actions
            entry.adapter.parent.mkdir(parents=True, exist_ok=True)
            target = os.path.relpath(entry.source, entry.adapter.parent)
            entry.adapter.symlink_to(target, target_is_directory=True)
            actions.append(SyncAction("create-symlink", entry.adapter))
        return self.validate(require_adapters=True), actions

    def validate_prompt_eval_coverage(self) -> list[Finding]:
        """Return findings when runtime skill eval coverage drifts."""
        manifest_path = self.root / PROMPT_EVAL_MANIFEST
        if not manifest_path.is_file():
            return []
        raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        data = as_mapping(raw)
        if data is None:
            return [Finding("eval", PROMPT_EVAL_MANIFEST.as_posix(), "must-be-mapping")]
        eval_entries = as_sequence(data.get("evals")) or ()
        for raw_entry in eval_entries:
            entry = as_mapping(raw_entry)
            if entry is None or entry.get("target_glob") != RUNTIME_SKILL_TARGET_GLOB:
                continue
            expected = entry.get("expected_count")
            actual = len(
                [
                    path
                    for path in self.root.glob(RUNTIME_SKILL_TARGET_GLOB)
                    if path.is_file()
                ]
            )
            if expected == actual:
                return []
            return [
                Finding(
                    "eval",
                    PROMPT_EVAL_MANIFEST.as_posix(),
                    f"prompt-eval-expected-count-mismatch:{RUNTIME_SKILL_TARGET_GLOB}:expected={expected} actual={actual}",
                )
            ]
        return [
            Finding(
                "eval",
                PROMPT_EVAL_MANIFEST.as_posix(),
                f"missing-runtime-skill-target-glob:{RUNTIME_SKILL_TARGET_GLOB}",
            )
        ]


def render_json(findings: Sequence[Finding], actions: Sequence[SyncAction], root: Path) -> str:
    """Render command output as JSON."""
    payload = {
        "status": "pass" if not findings else "fail",
        "findings": [
            {"check": finding.check, "path": finding.path, "detail": finding.detail}
            for finding in findings
        ],
        "actions": [
            {"action": action.action, "path": relative_to_root(action.path, root)}
            for action in actions
        ],
    }
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run adapter validation or synchronization."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    manifest = Path(args.manifest)
    validator = VendorSkillValidator(root=root, manifest=manifest)
    if args.sync:
        findings, actions = validator.sync()
    else:
        findings = validator.validate(require_adapters=True)
        actions = []

    if args.format == "json":
        print(render_json(findings, actions, root))
    else:
        for action in actions:
            print(action.render(root))
        for finding in findings:
            print(finding.render())
        print(f"VENDOR_SKILL_ADAPTER_FINDINGS={len(findings)}")
        print(f"VENDOR_SKILL_ADAPTERS={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
