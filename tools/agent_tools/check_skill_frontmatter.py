#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates runtime skill frontmatter for Codex skill loading.
# upstream design ../../agents/canonical/skills.md skill runtime registry contract
# upstream design ../../agents/skills/README.md human-facing skill index
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml runs this check in GitHub Actions
# downstream implementation ../../tools/ci/run_all_checks.sh runs this check in repository CI
# downstream implementation ../../tests/agent_tools/test_check_skill_frontmatter.py verifies this check
# @dependency-end
"""Validate YAML frontmatter for runtime Codex skill shims."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

SKILL_GLOB = ".agents/skills/*/SKILL.md"
FRONTMATTER_DELIMITER = "---"
REQUIRED_STRING_FIELDS = ("name", "description")
SKILL_NAME_RE = re.compile(r"_?[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class Finding:
    """One runtime skill frontmatter finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding."""
        return f"SKILL_FRONTMATTER_FINDING={self.check}:{self.path}:{self.detail}"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def relative_path(path: Path, root: Path) -> str:
    """Render a path relative to the repository root."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def skill_paths(root: Path) -> list[Path]:
    """Return runtime skill shim paths in stable order."""
    return sorted(path for path in root.glob(SKILL_GLOB) if path.is_file())


def frontmatter_block(path: Path) -> tuple[str | None, str | None]:
    """Return frontmatter text and an optional structural error detail."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, "missing-frontmatter-open"
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            return "\n".join(lines[1:index]), None
    return None, "missing-frontmatter-close"


def as_string_mapping(value: object) -> Mapping[str, object] | None:
    """Return a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(Mapping[str, object], mapping)


def parse_frontmatter(path: Path) -> tuple[Mapping[str, object] | None, str | None]:
    """Parse one YAML frontmatter block."""
    block, structural_error = frontmatter_block(path)
    if structural_error is not None:
        return None, structural_error
    assert block is not None
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        return None, f"invalid-yaml:{type(exc).__name__}:{str(exc).splitlines()[0]}"
    mapping = as_string_mapping(loaded)
    if mapping is None:
        return None, "frontmatter-must-be-mapping"
    return mapping, None


def validate_skill(path: Path, root: Path) -> list[Finding]:
    """Return findings for one runtime skill shim."""
    rel_path = relative_path(path, root)
    frontmatter, parse_error = parse_frontmatter(path)
    if parse_error is not None:
        return [Finding("yaml", rel_path, parse_error)]
    assert frontmatter is not None

    findings: list[Finding] = []
    for field in REQUIRED_STRING_FIELDS:
        value = frontmatter.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(Finding("field", rel_path, f"missing-{field}"))
    name = frontmatter.get("name")
    if isinstance(name, str) and not SKILL_NAME_RE.fullmatch(name.strip()):
        findings.append(Finding("field", rel_path, f"invalid-name:{name}"))
    if isinstance(name, str) and name.strip() != path.parent.name:
        findings.append(
            Finding("field", rel_path, f"name-must-match-directory:{name}!={path.parent.name}")
        )
    return findings


def validate_root(root: Path) -> tuple[list[Finding], int]:
    """Return frontmatter findings and the number of checked skills."""
    paths = skill_paths(root)
    findings: list[Finding] = []
    for path in paths:
        findings.extend(validate_skill(path, root))
    return sorted(findings, key=lambda finding: (finding.path, finding.check, finding.detail)), len(paths)


def render_json(findings: Sequence[Finding], checked: int) -> str:
    """Render JSON output."""
    payload = {
        "status": "pass" if not findings else "fail",
        "checked": checked,
        "findings": [asdict(finding) for finding in findings],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the frontmatter validator."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    findings, checked = validate_root(root)
    if args.format == "json":
        print(render_json(findings, checked))
    else:
        for finding in findings:
            print(finding.render())
        print(f"SKILL_FRONTMATTER_CHECKED={checked}")
        print(f"SKILL_FRONTMATTER={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
