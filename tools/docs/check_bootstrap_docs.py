#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Validate bootstrap-facing docs stay portable after template initialization."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(".").resolve()
BOOTSTRAP_DOCS = (
    Path("README.md"),
    Path("QUICK_START.md"),
    Path("docker/README.md"),
    Path("scripts/README.md"),
    Path("documents/template-bootstrap.md"),
    Path("documents/linux-wsl-host-requirements.md"),
)
ABSOLUTE_WORKSPACE_LINK = re.compile(r"\]\(/mnt/l/workspace/[^)]+\)")
DERIVED_REPO_STALE_STRINGS = (
    "Project Template",
    "project-template",
    "/mnt/git/template.git",
    "/mnt/l/workspace/project_template/",
)


def current_project_name() -> str | None:
    """Return the configured project name from ``pyproject.toml`` when available."""
    pyproject_path = ROOT / "pyproject.toml"
    if not pyproject_path.is_file():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def iter_findings() -> list[str]:
    """Collect validation findings for bootstrap-facing docs."""
    findings: list[str] = []
    project_name = current_project_name()
    check_derived_stale_strings = project_name not in (None, "project-template")

    for relative_path in BOOTSTRAP_DOCS:
        path = ROOT / relative_path
        if not path.is_file():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if ABSOLUTE_WORKSPACE_LINK.search(line):
                findings.append(
                    f"{relative_path}:{line_no}: replace workspace-absolute markdown links with relative links"
                )
            if not check_derived_stale_strings:
                continue
            for stale_string in DERIVED_REPO_STALE_STRINGS:
                if stale_string in line:
                    findings.append(
                        f"{relative_path}:{line_no}: stale template bootstrap text remains: {stale_string}"
                    )
    return findings


def main() -> int:
    """Run the bootstrap-doc validation."""
    findings = iter_findings()
    if not findings:
        print("Bootstrap docs check passed")
        return 0

    print("Bootstrap docs check failed:")
    for finding in findings:
        print(f"- {finding}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
