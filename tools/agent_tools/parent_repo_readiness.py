#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks whether a parent repository satisfies AgentCanon runtime expectations.
# upstream design ../../documents/shared-runtime-surfaces.toml root surface ownership manifest
# upstream design ../../documents/agent-canon-parent-repo-latest-checklist.md parent update checklist
# upstream implementation ./surface_manifest.py parses shared runtime surface manifests
# upstream implementation ../ci/container_config.py validates parent Docker/devcontainer surfaces
# downstream implementation ../../tests/agent_tools/test_parent_repo_readiness.py tests checker behavior
# @dependency-end
"""Check parent repository readiness for an AgentCanon submodule pin."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

from surface_manifest import SurfaceEntry, load_manifest, target_for_entry

DEFAULT_PREFIX = "vendor/agent-canon"
DEFAULT_MANIFEST = "documents/shared-runtime-surfaces.toml"
DEFAULT_TREE_DEPTH = 3
DEFAULT_TREE_IGNORE = ".git|__pycache__|.venv|node_modules|target|reports"
ERROR = "error"
WARN = "warn"


@dataclass(frozen=True)
class Finding:
    """One parent repository readiness finding."""

    severity: str
    category: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return (
            "PARENT_REPO_READINESS_FINDING="
            f"{self.severity}:{self.category}:{self.path}:{self.detail}"
        )


@dataclass(frozen=True)
class ExpectedPath:
    """One expected parent repository path."""

    path: str
    category: str
    kind: str
    severity: str = ERROR
    executable: bool = False


@dataclass(frozen=True)
class ContentMarker:
    """One required marker in a parent repository file."""

    path: str
    marker: str
    category: str
    severity: str = ERROR


@dataclass(frozen=True)
class ReadinessReport:
    """Readiness check result."""

    status: str
    findings: tuple[Finding, ...]
    checked: tuple[str, ...]
    tree_command: str


class ContainerFinding(Protocol):
    """Protocol for container_config finding values."""

    kind: str
    path: str
    detail: str


class ContainerValidationReport(Protocol):
    """Protocol for container_config validation reports."""

    findings: Sequence[ContainerFinding]
    checked: Sequence[str]


PARENT_CONTRACT_PATHS = (
    ExpectedPath("README.md", "parent_document", "file"),
    ExpectedPath("QUICK_START.md", "parent_document", "file"),
    ExpectedPath("Makefile", "parent_automation", "file"),
    ExpectedPath(".gitmodules", "agent_canon_submodule", "file"),
    ExpectedPath("goal.md", "parent_state", "file"),
    ExpectedPath("responsibility-scope.toml", "responsibility_scope", "file"),
    ExpectedPath(".agent-canon/update-state.toml", "agent_canon_update_state", "file", WARN),
    ExpectedPath("scripts/README.md", "parent_automation", "file"),
)

ENVIRONMENT_PATHS = (
    ExpectedPath(".dockerignore", "container_environment", "file"),
    ExpectedPath("docker/README.md", "container_environment", "file"),
    ExpectedPath("docker/Dockerfile", "container_environment", "file"),
    ExpectedPath("docker/requirements.txt", "container_environment", "file"),
    ExpectedPath("docker/install_python_dependencies.sh", "container_environment", "file", executable=True),
    ExpectedPath("docker/register_safe_directories.sh", "container_environment", "file", executable=True),
    ExpectedPath("docker/packs", "container_environment", "dir"),
    ExpectedPath("docker/packs/default.toml", "container_environment", "file"),
    ExpectedPath("docker/packs/default-host-docker.toml", "container_environment", "file"),
    ExpectedPath(".devcontainer/devcontainer.json", "devcontainer_environment", "file"),
    ExpectedPath(".devcontainer/post-create.sh", "devcontainer_environment", "file", executable=True),
    ExpectedPath(
        ".devcontainer/generate-runtime-compose.sh",
        "devcontainer_environment",
        "file",
        executable=True,
    ),
    ExpectedPath(".github/workflows/ci.yml", "github_environment", "file"),
    ExpectedPath(".github/workflows/docker-build.yml", "github_environment", "file"),
    ExpectedPath(".github/scripts/checkout_agent_canon_submodule.sh", "github_environment", "file", executable=True),
)

CONTENT_MARKERS = (
    ContentMarker(".gitmodules", "vendor/agent-canon", "agent_canon_submodule"),
    ContentMarker(".gitmodules", "agent-canon", "agent_canon_submodule"),
    ContentMarker("responsibility-scope.toml", "catalog_kind = \"agent_canon_responsibility_scope\"", "responsibility_scope"),
    ContentMarker(".agent-canon/update-state.toml", "tasks_applied_through", "agent_canon_update_state", WARN),
)


class ExpectedPathChecker:
    """Checks required parent-owned files and directories."""

    def __init__(self, root: Path, expectations: Iterable[ExpectedPath]) -> None:
        """Store the parent root and path expectations."""
        self.root = root
        self.expectations = tuple(expectations)

    def run(self) -> tuple[Finding, ...]:
        """Return findings for missing or malformed expected paths."""
        findings: list[Finding] = []
        for expected in self.expectations:
            path = self.root / expected.path
            if not self.path_matches_kind(path, expected.kind):
                findings.append(
                    Finding(expected.severity, expected.category, expected.path, f"missing-{expected.kind}")
                )
                continue
            if expected.executable and not os.access(path, os.X_OK):
                findings.append(
                    Finding(expected.severity, expected.category, expected.path, "not-executable")
                )
        return tuple(findings)

    @staticmethod
    def path_matches_kind(path: Path, kind: str) -> bool:
        """Return whether a path matches the expected kind."""
        if kind == "file":
            return path.is_file()
        if kind == "dir":
            return path.is_dir()
        return path.exists()


class ContentMarkerChecker:
    """Checks required parent file markers."""

    def __init__(self, root: Path, markers: Iterable[ContentMarker]) -> None:
        """Store the parent root and marker expectations."""
        self.root = root
        self.markers = tuple(markers)

    def run(self) -> tuple[Finding, ...]:
        """Return findings for files that miss required markers."""
        findings: list[Finding] = []
        for marker in self.markers:
            path = self.root / marker.path
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            if marker.marker not in text:
                findings.append(
                    Finding(marker.severity, marker.category, marker.path, f"missing-marker:{marker.marker}")
                )
        return tuple(findings)


class SubmoduleShapeChecker:
    """Checks the expected AgentCanon submodule shape."""

    def __init__(self, root: Path, prefix: str, skip_git_marker: bool) -> None:
        """Store submodule shape inputs."""
        self.root = root
        self.prefix = prefix
        self.skip_git_marker = skip_git_marker

    def run(self) -> tuple[Finding, ...]:
        """Return findings for an invalid submodule checkout shape."""
        findings: list[Finding] = []
        source_root = self.root / self.prefix
        manifest_path = source_root / DEFAULT_MANIFEST
        if not source_root.is_dir():
            findings.append(Finding(ERROR, "agent_canon_submodule", self.prefix, "missing-directory"))
        if not manifest_path.is_file():
            findings.append(
                Finding(ERROR, "agent_canon_submodule", f"{self.prefix}/{DEFAULT_MANIFEST}", "missing-manifest")
            )
        if not self.skip_git_marker:
            findings.extend(self.check_git_marker(source_root))
        return tuple(findings)

    def check_git_marker(self, source_root: Path) -> tuple[Finding, ...]:
        """Return findings for a missing or non-submodule .git marker."""
        git_marker = source_root / ".git"
        if not git_marker.exists():
            return (Finding(ERROR, "agent_canon_submodule", f"{self.prefix}/.git", "missing-git-marker"),)
        if git_marker.is_dir():
            return (Finding(ERROR, "agent_canon_submodule", f"{self.prefix}/.git", "expected-submodule-gitfile"),)
        return ()


class SurfaceReadinessChecker:
    """Checks AgentCanon shared root view readiness from the manifest."""

    def __init__(self, root: Path, prefix: str, entries: Iterable[SurfaceEntry]) -> None:
        """Store manifest entries and path context."""
        self.root = root
        self.prefix = prefix
        self.entries = tuple(entries)

    def run(self) -> tuple[Finding, ...]:
        """Return findings for root surface drift."""
        findings: list[Finding] = []
        for entry in self.entries:
            findings.extend(self.check_entry(entry))
        return tuple(findings)

    def check_entry(self, entry: SurfaceEntry) -> tuple[Finding, ...]:
        """Check one manifest entry."""
        if entry.mode == "standalone_only":
            return self.check_root_absent(entry)
        if entry.mode == "regular":
            return self.check_regular(entry)
        if entry.mode == "symlink":
            return self.check_symlink(entry)
        if entry.mode == "copy":
            return self.check_copy(entry)
        return ()

    def check_root_absent(self, entry: SurfaceEntry) -> tuple[Finding, ...]:
        """Return a finding when a standalone-only path leaked into the parent root."""
        path = self.root / entry.path
        if os.path.lexists(path):
            return (Finding(ERROR, "standalone_only_leak", entry.path, "must-not-exist-in-parent-root"),)
        return ()

    def check_regular(self, entry: SurfaceEntry) -> tuple[Finding, ...]:
        """Return findings for a parent-owned regular file."""
        path = self.root / entry.path
        if entry.optional and not path.exists():
            return ()
        if entry.surface_class == "project_content":
            if not path.is_dir():
                return (Finding(ERROR, "project_content", entry.path, "missing-directory"),)
            if path.is_symlink():
                return (Finding(ERROR, "project_content", entry.path, "must-be-parent-owned-directory"),)
            return ()
        if not path.is_file():
            return (Finding(ERROR, "active_contract", entry.path, "missing-regular-file"),)
        if path.is_symlink():
            return (Finding(ERROR, "active_contract", entry.path, "must-be-parent-owned-regular-file"),)
        return ()

    def check_symlink(self, entry: SurfaceEntry) -> tuple[Finding, ...]:
        """Return findings for one AgentCanon-owned symlink view."""
        path = self.root / entry.path
        source = self.root / self.prefix / entry.source_or_default()
        findings: list[Finding] = []
        if not source.exists():
            findings.append(Finding(ERROR, "shared_surface_source", entry.path, "missing-source"))
        if not os.path.lexists(path):
            findings.append(Finding(ERROR, "shared_surface", entry.path, "missing-symlink"))
            return tuple(findings)
        if not path.is_symlink():
            findings.append(Finding(ERROR, "shared_surface", entry.path, "must-be-symlink"))
            return tuple(findings)
        expected_target = target_for_entry(self.root, self.prefix, entry)
        actual_target = os.readlink(path)
        if actual_target != expected_target:
            findings.append(
                Finding(
                    ERROR,
                    "shared_surface",
                    entry.path,
                    f"symlink-target-mismatch:{actual_target}!={expected_target}",
                )
            )
        return tuple(findings)

    def check_copy(self, entry: SurfaceEntry) -> tuple[Finding, ...]:
        """Return findings for one GitHub path constraint copy."""
        path = self.root / entry.path
        source = self.root / self.prefix / entry.source_or_default()
        if not source.is_file():
            return (Finding(ERROR, "github_copy_source", entry.path, "missing-source"),)
        if not path.is_file():
            return (Finding(ERROR, "github_copy", entry.path, "missing-copy"),)
        if path.read_bytes() != source.read_bytes():
            return (Finding(ERROR, "github_copy", entry.path, "copy-differs-from-agent-canon-source"),)
        return ()


class ContainerConfigChecker:
    """Runs the shared container configuration checker against the parent root."""

    def __init__(self, root: Path, prefix: str, skip: bool) -> None:
        """Store container checker inputs."""
        self.root = root
        self.prefix = prefix
        self.skip = skip

    def run(self) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
        """Return container findings and checked surface names."""
        if self.skip:
            return (), ("container_config:skipped",)
        module_path = self.root / self.prefix / "tools" / "ci" / "container_config.py"
        if not module_path.is_file():
            finding = Finding(
                ERROR,
                "container_environment",
                f"{self.prefix}/tools/ci/container_config.py",
                "missing-validator",
            )
            return (finding,), ("container_config:missing",)
        module = self.load_module(module_path)
        validate_object: object = getattr(module, "validate", None)
        if not callable(validate_object):
            finding = Finding(ERROR, "container_environment", str(module_path), "validate-not-callable")
            return (finding,), ("container_config:invalid",)
        validate = cast(Callable[[Path], ContainerValidationReport], validate_object)
        report = validate(self.root)
        raw_findings = report.findings
        checked = tuple(str(item) for item in report.checked)
        findings = tuple(
            Finding(
                ERROR,
                "container_environment",
                str(item.path),
                f"{item.kind}:{item.detail}",
            )
            for item in raw_findings
        )
        return findings, tuple(f"container_config:{item}" for item in checked)

    @staticmethod
    def load_module(module_path: Path) -> ModuleType:
        """Load the container validator module from the AgentCanon source path."""
        spec = importlib.util.spec_from_file_location("_agent_canon_container_config", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


class TreeDisplayChecker:
    """Checks availability of the canonical parent structure display command."""

    def __init__(self, root: Path, depth: int, skip: bool) -> None:
        """Store tree display inputs."""
        self.root = root
        self.depth = depth
        self.skip = skip

    def run(self) -> tuple[tuple[Finding, ...], tuple[str, ...], str]:
        """Return tree display findings, checked tokens, and the stable command."""
        command = self.render_command()
        if self.skip:
            return (), ("tree_display:skipped",), command
        if shutil.which("tree") is None:
            finding = Finding(WARN, "tree_display", "tree", "missing-command")
            return (finding,), ("tree_display:missing",), command
        return (), (f"tree_display:available:depth={self.depth}",), command

    def render_command(self) -> str:
        """Render the canonical human-facing structure inspection command."""
        parts = (
            "tree",
            "-a",
            "-L",
            str(self.depth),
            "-I",
            DEFAULT_TREE_IGNORE,
            str(self.root),
        )
        return " ".join(shlex.quote(part) for part in parts)


class ParentRepoReadinessChecker:
    """Coordinates all parent repository readiness checks."""

    def __init__(
        self,
        root: Path,
        prefix: str,
        manifest_path: str,
        skip_container_config: bool,
        skip_submodule_check: bool,
        tree_depth: int,
        skip_tree: bool,
    ) -> None:
        """Store parent readiness check inputs."""
        self.root = root
        self.prefix = prefix
        self.manifest_path = manifest_path
        self.skip_container_config = skip_container_config
        self.skip_submodule_check = skip_submodule_check
        self.tree_depth = tree_depth
        self.skip_tree = skip_tree

    def run(self) -> ReadinessReport:
        """Run parent readiness checks."""
        findings: list[Finding] = []
        checked: list[str] = []
        tree_findings, tree_checked, tree_command = TreeDisplayChecker(
            self.root,
            self.tree_depth,
            self.skip_tree,
        ).run()
        findings.extend(tree_findings)
        checked.extend(tree_checked)
        findings.extend(SubmoduleShapeChecker(self.root, self.prefix, self.skip_submodule_check).run())
        try:
            manifest = load_manifest(self.root, self.prefix, self.manifest_path)
            findings.extend(SurfaceReadinessChecker(self.root, self.prefix, manifest.entries).run())
            checked.append(f"surface_manifest:{len(manifest.entries)}")
        except (OSError, ValueError) as exc:
            findings.append(
                Finding(ERROR, "shared_surface_manifest", self.manifest_path, f"load-failed:{exc}")
            )
        expected_paths = (*PARENT_CONTRACT_PATHS, *ENVIRONMENT_PATHS)
        findings.extend(ExpectedPathChecker(self.root, expected_paths).run())
        findings.extend(ContentMarkerChecker(self.root, CONTENT_MARKERS).run())
        container_findings, container_checked = ContainerConfigChecker(
            self.root,
            self.prefix,
            self.skip_container_config,
        ).run()
        findings.extend(container_findings)
        checked.extend(container_checked)
        sorted_findings = tuple(
            sorted(findings, key=lambda item: (item.severity, item.category, item.path, item.detail))
        )
        status = "fail" if any(finding.severity == ERROR for finding in sorted_findings) else "pass"
        return ReadinessReport(status, sorted_findings, tuple(checked), tree_command)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Parent repository root. Defaults to cwd.")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="AgentCanon prefix relative to root.")
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="Shared runtime surface manifest relative to AgentCanon prefix.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--skip-container-config",
        action="store_true",
        help="Skip deep Docker/devcontainer validation; path existence is still checked.",
    )
    parser.add_argument(
        "--skip-submodule-check",
        action="store_true",
        help="Skip the .git-file submodule shape check for synthetic fixtures.",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Treat warning findings as failures.",
    )
    parser.add_argument(
        "--tree-depth",
        type=int,
        default=DEFAULT_TREE_DEPTH,
        help="Depth for the canonical tree structure inspection command.",
    )
    parser.add_argument(
        "--skip-tree",
        action="store_true",
        help="Skip tree command availability checking.",
    )
    return parser


def render_json(report: ReadinessReport) -> str:
    """Render a JSON report."""
    return json.dumps(
        {
            "status": report.status,
            "checked": list(report.checked),
            "tree_command": report.tree_command,
            "findings": [asdict(finding) for finding in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def render_text(report: ReadinessReport) -> None:
    """Render a text report."""
    for finding in report.findings:
        print(finding.render())
    errors = sum(1 for finding in report.findings if finding.severity == ERROR)
    warnings = sum(1 for finding in report.findings if finding.severity == WARN)
    print(f"PARENT_REPO_READINESS_CHECKED={','.join(report.checked) if report.checked else 'none'}")
    print(f"PARENT_REPO_READINESS_TREE_COMMAND={report.tree_command}")
    print(f"PARENT_REPO_READINESS_ERRORS={errors}")
    print(f"PARENT_REPO_READINESS_WARNINGS={warnings}")
    print(f"PARENT_REPO_READINESS={report.status}")


def exit_status(report: ReadinessReport, strict_warnings: bool) -> int:
    """Return the command exit status for one report."""
    if report.status == "fail":
        return 1
    if strict_warnings and report.findings:
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the parent repository readiness checker."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    checker = ParentRepoReadinessChecker(
        root=root,
        prefix=args.prefix,
        manifest_path=args.manifest,
        skip_container_config=args.skip_container_config,
        skip_submodule_check=args.skip_submodule_check,
        tree_depth=args.tree_depth,
        skip_tree=args.skip_tree,
    )
    report = checker.run()
    if args.format == "json":
        print(render_json(report))
    else:
        render_text(report)
    return exit_status(report, args.strict_warnings)


if __name__ == "__main__":
    raise SystemExit(main())
