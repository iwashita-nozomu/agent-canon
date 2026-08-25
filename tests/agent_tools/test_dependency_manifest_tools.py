"""Tests for dependency manifest shell tools."""

# @dependency-start
# contract test
# responsibility Tests dependency manifest shell tool behavior.
# upstream design ../../documents/design/dependency-contract-kinds.toml registered dependency header contract kinds
# upstream design ../../documents/design/dependency-manifest-design.md manifest design
# upstream implementation ../../tools/agent_tools/scan_dependency_headers.sh scans
# upstream implementation ../../tools/agent_tools/check_dependency_header_format.sh format checks
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh graph checks
# upstream implementation ../../tools/agent_tools/visualization_contract.py owns complete projection/readback coverage after graph extraction
# upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh wraps
# upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh scans code
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "scan_dependency_headers.sh"
FORMAT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_header_format.sh"
GRAPH = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_graph.sh"
REPO_REVIEW = PROJECT_ROOT / "tools" / "agent_tools" / "run_repo_dependency_review.sh"
CODE_SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "scan_code_dependencies.sh"
DESIGN_CLAIMS = PROJECT_ROOT / "tools" / "agent_tools" / "check_design_doc_claims.py"
WORKFLOW_MONITOR = PROJECT_ROOT / "tools" / "agent_tools" / "workflow_monitor.py"
AGENT_TEAM = PROJECT_ROOT / "tools" / "agent_tools" / "agent_team.py"
DOCKER_VALIDATOR = PROJECT_ROOT / "tools" / "docker_dependency_validator.sh"


def runtime_root_for(root: Path) -> Path:
    """Return the per-fixture runtime root outside the fixture checkout."""
    inherited_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
    runtime_parent = Path(inherited_runtime) if inherited_runtime else root.parent
    identity = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    runtime = runtime_parent / "dependency-manifest-tests" / identity
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def tool_environment(root: Path) -> dict[str, str]:
    """Provide the explicit external runtime/control roots required by tools."""
    environment = os.environ.copy()
    environment.update(
        {
            "AGENT_CANON_RUNTIME_ROOT": str(runtime_root_for(root)),
            "AGENT_CANON_CONTROL_PARENT_ROOT": environment.get(
                "AGENT_CANON_CONTROL_PARENT_ROOT", str(root.parent.resolve())
            ),
        }
    )
    return environment


def run_tool(*args: str, root: Path) -> subprocess.CompletedProcess[str]:
    """Run a dependency manifest shell tool."""
    return subprocess.run(
        ["bash", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=tool_environment(root),
    )


class DependencyManifestToolTest(unittest.TestCase):
    """Exercise the dependency manifest shell tools."""

    @staticmethod
    def git_output(root: Path, *args: str) -> str:
        """Run one successful Git fixture command."""
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def changed_header_fixture(
        self,
        root: Path,
        base_files: dict[str, str],
        head_files: dict[str, str],
    ) -> tuple[str, str]:
        """Create a two-commit fixture for trusted changed-path scans."""
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.git_output(root, "config", "user.email", "headers@example.invalid")
        self.git_output(root, "config", "user.name", "Header Fixture")
        for relative, content in base_files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.git_output(root, "add", "-A")
        self.git_output(root, "commit", "-m", "base")
        base = self.git_output(root, "rev-parse", "HEAD")
        for relative in set(base_files) - set(head_files):
            (root / relative).unlink()
        for relative, content in head_files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.git_output(root, "add", "-A")
        self.git_output(root, "commit", "-m", "head")
        return base, self.git_output(root, "rev-parse", "HEAD")

    def write_changed_path_packet(
        self,
        root: Path,
        base: str,
        packet_path: Path,
        changed_paths: list[str] | None = None,
        root_value: str | None = None,
    ) -> None:
        """Write selector-compatible trusted path evidence for a fixture."""
        head = self.git_output(root, "rev-parse", "HEAD")
        actual_paths = self.git_output(
            root, "diff", "--name-only", f"{base}...{head}", "--"
        ).splitlines()
        paths = actual_paths if changed_paths is None else changed_paths
        packet = {
            "schema": "agent-canon.pr-changed-paths.v1",
            "root": str(root.resolve()) if root_value is None else root_value,
            "base_sha": base,
            "base_source": "fixture",
            "base_tree": self.git_output(root, "rev-parse", f"{base}^{{tree}}"),
            "head_sha": head,
            "head_tree": self.git_output(root, "rev-parse", f"{head}^{{tree}}"),
            "merge_base": self.git_output(root, "merge-base", base, head),
            "changed_paths": paths,
            "changed_paths_sha256": hashlib.sha256(
                "\0".join(paths).encode("utf-8")
            ).hexdigest(),
        }
        packet_path.write_text(
            json.dumps(packet, sort_keys=True) + "\n", encoding="utf-8"
        )

    @staticmethod
    def valid_header(label: str) -> str:
        """Return one minimal registered dependency manifest."""
        return (
            "<!--\n"
            "@dependency-start\n"
            "contract test\n"
            f"responsibility Defines {label}.\n"
            "@dependency-end\n"
        )

    def test_scan_reports_missing_manifest(self) -> None:
        """The scan tool reports missing markers and can fail on request."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            doc.write_text("# Doc\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(doc),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=doc.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)

    def test_scan_reports_display_path_and_real_source_path(self) -> None:
        """Missing-header findings should include review path and real source path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            doc.write_text("# Doc\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                str(doc),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=doc.md", result.stdout)
            self.assertIn("realpath=doc.md", result.stdout)
            self.assertIn("owner=product_file", result.stdout)

    def test_code_scan_can_write_lexical_lsp_report(self) -> None:
        """Compatibility scanner can persist the canonical lexical report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            root = workspace / "source"
            runtime = workspace / "runtime"
            root.mkdir()
            runtime.mkdir()
            source = root / "main.py"
            source.write_text("import package\n", encoding="utf-8")
            analysis = runtime / "analysis.json"
            result = subprocess.run(
                [
                    "bash",
                    str(CODE_SCAN),
                    "--root",
                    str(root),
                    "--lexical-only",
                    "--runtime-root",
                    str(runtime),
                    "--analysis-json",
                    str(analysis),
                    "main.py",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CODE_DEPENDENCY_SCAN=pass", result.stdout)
            payload = json.loads(analysis.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "agent-canon.lsp-code-analysis.v1")
            self.assertEqual(payload["lifecycle"]["state"], "lexical-only")

    def test_code_scan_default_uses_lsp_and_fails_closed(self) -> None:
        """The normal scanner route does not silently downgrade to lexical facts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "main.py"
            source.write_text("import package\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["AGENT_CANON_DEPENDENCY_MANIFEST"] = str(
                root / "missing-dependencies.toml"
            )
            result = subprocess.run(
                ["bash", str(CODE_SCAN), "--root", str(root), "main.py"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("CODE_DEPENDENCY_SCAN=pass", result.stdout)

    def test_code_scan_lexical_wrapper_rejects_symlink_ancestor(self) -> None:
        """The lexical wrapper delegates explicit path validation to LSP."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            real = root / "real"
            real.mkdir()
            (real / "main.py").write_text("import package\n", encoding="utf-8")
            (root / "linked").symlink_to(real, target_is_directory=True)
            result = subprocess.run(
                [
                    "bash",
                    str(CODE_SCAN),
                    "--root",
                    str(root),
                    "--lexical-only",
                    "linked/main.py",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("CODE_DEPENDENCY_SCAN=pass", result.stdout)
            self.assertIn("path-escape", result.stderr)

            paths_file = root / "paths.txt"
            paths_file.write_text("linked/main.py\n", encoding="utf-8")
            paths_result = subprocess.run(
                [
                    "bash",
                    str(CODE_SCAN),
                    "--root",
                    str(root),
                    "--lexical-only",
                    "--paths-file",
                    str(paths_file),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(paths_result.returncode, 0)
            self.assertIn("path-escape", paths_result.stderr)

    def test_code_scan_no_selector_delegates_bounded_discovery(self) -> None:
        """No-selector wrapper calls LSP without pre-expanding repository paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for relative in (
                "python/main.py",
                "workspace/leak.py",
                "vendor/leak.py",
                "reports/leak.py",
                "build/leak.py",
                ".venv/leak.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x = 1\n", encoding="utf-8")
            (root / "linked.py").symlink_to(root / "python" / "main.py")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            args_file = root / "lsp-args.txt"
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$SCAN_ARGS_FILE\"\n",
                encoding="utf-8",
            )
            os.chmod(fake_python, 0o755)
            environment = dict(os.environ)
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            environment["SCAN_ARGS_FILE"] = str(args_file)

            result = subprocess.run(
                ["bash", str(CODE_SCAN), "--root", str(root), "--lexical-only"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            forwarded = args_file.read_text(encoding="utf-8").splitlines()
            self.assertIn("--lexical-only", forwarded)
            self.assertNotIn("--files", forwarded)
            self.assertNotIn("workspace/leak.py", forwarded)
            self.assertNotIn("vendor/leak.py", forwarded)
            self.assertNotIn("reports/leak.py", forwarded)
            self.assertNotIn("build/leak.py", forwarded)
            self.assertNotIn(".venv/leak.py", forwarded)
            self.assertNotIn("linked.py", forwarded)

    def test_code_scan_rust_is_sidecar_only(self) -> None:
        """Rust lexical facts stay in the sidecar without fabricated TSV rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            root = workspace / "source"
            runtime = workspace / "runtime"
            root.mkdir()
            runtime.mkdir()
            source = root / "main.rs"
            source.write_text("mod helper;\nuse crate::helper;\n", encoding="utf-8")
            analysis = runtime / "analysis.json"
            result = subprocess.run(
                [
                    "bash",
                    str(CODE_SCAN),
                    "--root",
                    str(root),
                    "--lexical-only",
                    "--runtime-root",
                    str(runtime),
                    "--analysis-json",
                    str(analysis),
                    "main.rs",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "CODE_DEPENDENCY_SCAN=pass files=1")
            legacy_rows = [
                line for line in result.stdout.splitlines() if line.startswith("CODE_DEPENDENCY\t")
            ]
            self.assertFalse(legacy_rows)
            self.assertTrue(all(len(line.split("\t")) == 7 for line in legacy_rows))
            payload = json.loads(analysis.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["files"], ["main.rs"])
            self.assertTrue(payload["lexical_candidates"])
            self.assertTrue(any(item["token"] == "helper" for item in payload["lexical_candidates"]))

    def test_trusted_packet_reports_unchanged_missing_as_baseline(self) -> None:
        """Unchanged missing headers are evidence and do not fail the PR scan."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, _ = self.changed_header_fixture(
                root,
                {
                    "README.md": self.valid_header("stable readme"),
                    "unchanged.md": "# Existing missing header\n",
                },
                {
                    "README.md": self.valid_header("stable readme"),
                    "unchanged.md": "# Existing missing header\n",
                    "changed.md": self.valid_header("changed source"),
                },
            )
            packet = root / "changed-paths.json"
            self.write_changed_path_packet(root, base, packet)

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_BASELINE=1", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_BLOCKING=0", result.stdout)
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_BASELINE_MISSING_PATH=unchanged.md",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)

    def test_trusted_packet_blocks_changed_missing_header(self) -> None:
        """A changed product file without a manifest remains a blocking failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, _ = self.changed_header_fixture(
                root,
                {"changed.md": self.valid_header("base source")},
                {"changed.md": "# Header removed in the PR\n"},
            )
            packet = root / "changed-paths.json"
            self.write_changed_path_packet(root, base, packet)

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADER_SCAN_BLOCKING=1", result.stdout)
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_CHANGED_MISSING_PATH=changed.md",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)

    def test_trusted_packet_blocks_new_missing_header(self) -> None:
        """A newly added product file without a manifest is blocking."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, _ = self.changed_header_fixture(
                root,
                {"README.md": self.valid_header("stable readme")},
                {
                    "README.md": self.valid_header("stable readme"),
                    "new.md": "# New source without a manifest\n",
                },
            )
            packet = root / "changed-paths.json"
            self.write_changed_path_packet(root, base, packet)

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_CHANGED_MISSING_PATH=new.md",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)

    def test_trusted_packet_changed_valid_header_passes(self) -> None:
        """A changed product file with a valid manifest passes the strict scan."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, _ = self.changed_header_fixture(
                root,
                {"changed.md": "# Base source\n"},
                {"changed.md": self.valid_header("changed source")},
            )
            packet = root / "changed-paths.json"
            self.write_changed_path_packet(root, base, packet)

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_BLOCKING=0", result.stdout)

    def test_trusted_packet_deleted_file_is_skipped(self) -> None:
        """A deleted path from the trusted diff is not scanned as a head file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, _ = self.changed_header_fixture(
                root,
                {
                    "README.md": self.valid_header("stable readme"),
                    "deleted.md": "# Deleted source was missing\n",
                },
                {"README.md": self.valid_header("stable readme")},
            )
            packet = root / "changed-paths.json"
            self.write_changed_path_packet(root, base, packet)

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", result.stdout)

    def test_trusted_packet_missing_or_wrong_fails_closed(self) -> None:
        """Missing and mismatched trusted path packets cannot widen the scan."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, head = self.changed_header_fixture(
                root,
                {"changed.md": self.valid_header("base source")},
                {"changed.md": self.valid_header("changed source")},
            )
            missing = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(root / "missing.json"),
                "--trusted-base-sha",
                base,
                root=root,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_REASON=changed_path_packet_missing_or_wrong_type",
                missing.stdout,
            )

            wrong = root / "wrong.json"
            self.write_changed_path_packet(root, base, wrong, changed_paths=[])
            mismatched = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(wrong),
                "--trusted-base-sha",
                base,
                root=root,
            )
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_REASON=changed_path_packet_paths_mismatch",
                mismatched.stdout,
            )

            packet = root / "packet.json"
            self.write_changed_path_packet(root, base, packet)
            substituted = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                head,
                root=root,
            )
            self.assertNotEqual(substituted.returncode, 0)
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_REASON=changed_path_packet_trusted_base_mismatch",
                substituted.stdout,
            )

    def test_repo_review_header_scan_only_runs_without_graph_executable(self) -> None:
        """The trusted header gate is independent from graph-selection readiness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base, _ = self.changed_header_fixture(
                root,
                {"changed.md": self.valid_header("base source")},
                {"changed.md": self.valid_header("changed source")},
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "run_repo_dependency_review.sh").symlink_to(REPO_REVIEW)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            packet = root / "changed-paths.json"
            self.write_changed_path_packet(root, base, packet)

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--header-scan-only",
                "--fail-missing",
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_scan_accepts_large_file_with_manifest_markers_near_top(self) -> None:
        """Early marker matches in large files must not trip pipefail/SIGPIPE."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "large.md"
            doc.write_text(
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises large-file dependency header scanning.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                        *("x" * 4096 for _ in range(120)),
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(doc),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)

    def test_repo_review_output_is_stable_across_repeated_runs(self) -> None:
        """Strict repo dependency review should be stable across repeated runs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target fixture for stable review.",
                        "downstream design source.md source consumes target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source fixture for stable review.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            first = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )
            second = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", first.stdout)

    def test_repo_review_default_root_uses_current_worktree(self) -> None:
        """Default root should be cwd, not the symlinked tool source repository."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.parent.mkdir(parents=True)
            tool_dir.symlink_to(PROJECT_ROOT / "tools" / "agent_tools")
            target = root / "target.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines cwd-root dependency fixture.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "\n".join(
                    [
                        "# Readme",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines readme fixture.",
                        "downstream design target.md target fixture",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "README.md", "target.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                ["bash", str(REPO_REVIEW), "--fail-missing"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                env=tool_environment(root),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_can_run_design_claim_checker_for_explicit_path(self) -> None:
        """The dependency review wrapper can invoke design claim evidence checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "check_design_doc_claims.py").symlink_to(DESIGN_CLAIMS)
            design = root / "documents" / "design" / "feature.md"
            implementation = root / "tools" / "feature_runner.py"
            design.parent.mkdir(parents=True)
            implementation.parent.mkdir(parents=True, exist_ok=True)
            design.write_text(
                "\n".join(
                    [
                        "# Feature",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Documents feature fixture.",
                        "downstream implementation ../../tools/feature_runner.py runner",
                        "@dependency-end",
                        "-->",
                        "",
                        "## Evidence And Assumption Ledger",
                        "",
                        "- Evidence sources: `tools/feature_runner.py`.",
                        "- Assumptions: direct implementation evidence.",
                        "",
                        "## Claims",
                        "",
                        "- The design must use `run_feature`.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            implementation.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Implements feature fixture.",
                        "# upstream design ../documents/design/feature.md feature design",
                        "# @dependency-end",
                        "",
                        "def run_feature() -> None:",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "git",
                    "add",
                    "documents/design/feature.md",
                    "tools/feature_runner.py",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--check-design-doc-claims",
                "--design-doc-claim-path",
                "documents/design/feature.md",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_design_claim_checker_defaults_to_changed_design_docs(
        self,
    ) -> None:
        """Wrapper claim checks stay migration-safe for legacy design backlog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "check_design_doc_claims.py").symlink_to(DESIGN_CLAIMS)
            readme = root / "README.md"
            legacy = root / "documents" / "design" / "legacy.md"
            legacy.parent.mkdir(parents=True)
            readme.write_text(
                "\n".join(
                    [
                        "# Readme",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines fixture readme.",
                        "downstream design documents/design/legacy.md legacy design",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            legacy.write_text(
                "\n".join(
                    [
                        "# Legacy",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Documents legacy design fixture.",
                        "upstream design ../../README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                        "## Claims",
                        "",
                        "- The legacy design must preserve behavior.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "README.md", "documents/design/legacy.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=test@example.com",
                    "-c",
                    "user.name=Test User",
                    "commit",
                    "-m",
                    "baseline",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            design = root / "documents" / "design" / "feature.md"
            implementation = root / "tools" / "feature_runner.py"
            design.write_text(
                "\n".join(
                    [
                        "# Feature",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Documents feature fixture.",
                        "downstream implementation ../../tools/feature_runner.py runner",
                        "@dependency-end",
                        "-->",
                        "",
                        "## Evidence And Assumption Ledger",
                        "",
                        "- Evidence sources: `tools/feature_runner.py`.",
                        "- Assumptions: direct implementation evidence.",
                        "",
                        "## Claims",
                        "",
                        "- The design must use `run_feature`.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            implementation.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Implements feature fixture.",
                        "# upstream design ../documents/design/feature.md feature design",
                        "# @dependency-end",
                        "",
                        "def run_feature() -> None:",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "git",
                    "add",
                    "documents/design/feature.md",
                    "tools/feature_runner.py",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--check-design-doc-claims",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=1", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_code_scan_extracts_python_import_edges(self) -> None:
        """The code dependency scanner resolves local Python imports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            source = package / "consumer.py"
            source.write_text("from . import module\n", encoding="utf-8")

            result = run_tool(
                str(CODE_SCAN),
                "--root",
                str(root),
                "--lexical-only",
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "CODE_DEPENDENCY\tpython\tfrom-import-symbol\tpkg/consumer.py\tpkg/module.py\t.module",
                result.stdout,
            )
            self.assertIn("CODE_DEPENDENCY_SCAN=pass files=1", result.stdout)

    def test_code_scan_extracts_c_family_local_includes(self) -> None:
        """The code dependency scanner resolves local C/C++ includes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            include = root / "include"
            include.mkdir()
            header = include / "api.hpp"
            source = root / "main.cpp"
            header.write_text("#pragma once\n", encoding="utf-8")
            source.write_text('#include "include/api.hpp"\n', encoding="utf-8")

            result = run_tool(
                str(CODE_SCAN),
                "--root",
                str(root),
                "--lexical-only",
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "CODE_DEPENDENCY\tc-family\tinclude\tmain.cpp\tinclude/api.hpp\tinclude/api.hpp",
                result.stdout,
            )

    def test_docker_validator_accepts_project_extras_in_parent_layout(self) -> None:
        """The standalone bootstrap manifest validates without legacy Dev Container state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "python").mkdir()
            (root / "docker").mkdir()
            agent_tools = root / "tools" / "agent_tools"
            agent_tools.mkdir(parents=True)
            (agent_tools / "devcontainer_dependencies.py").symlink_to(
                PROJECT_ROOT / "tools" / "agent_tools" / "devcontainer_dependencies.py"
            )
            (agent_tools / "dependency_plan.py").symlink_to(
                PROJECT_ROOT / "tools" / "agent_tools" / "dependency_plan.py"
            )
            manifest = root / "bootstrap" / "container" / "dependencies.toml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                "\n".join(
                    [
                        'schema = "agent-canon.tool-dependencies"',
                        "schema_version = 2",
                        "",
                        "[[records]]",
                        'id = "fixture"',
                        'package = "fixture"',
                        'method = "apt-package"',
                        'version = "1.0"',
                        'source = "fixture"',
                        'verification = { kind = "apt-package" }',
                        "deps = []",
                        'provides = ["fixture"]',
                        'failure_policy = "fail"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                "[project]\ndependencies = []\n[project.optional-dependencies]\ndev = []\n",
                encoding="utf-8",
            )
            (root / "docker" / "Dockerfile").write_text(
                "FROM ubuntu:22.04\n",
                encoding="utf-8",
            )
            (root / ".dockerignore").write_text(
                ".git\n.state\n",
                encoding="utf-8",
            )
            (root / ".gitignore").write_text(".venv/\nvenv/\n", encoding="utf-8")
            (root / "README.md").write_text(
                "PYTHONPATH=/workspace/python\nUse docker run for execution.\n",
                encoding="utf-8",
            )
            (root / "docker" / "README.md").write_text(
                "Parent product image dependencies.\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", str(DOCKER_VALIDATOR)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_CANON_TOOL_DEPENDENCY=pass", result.stdout)
            self.assertIn("AGENT_CANON_TOOL_DEPENDENCY_ORDER=fixture", result.stdout)
            self.assertNotIn("missing-file", result.stdout)
            self.assertNotIn("unsupported requirement syntax", result.stdout)

    def test_format_accepts_line_comment_manifest(self) -> None:
        """Line-comment manifests are valid for Python-like files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.py"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises a valid line-comment manifest.",
                        "# upstream implementation target.py target contract",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_preserves_missing_targets_in_issue_mirrors(self) -> None:
        """Durable issue mirrors may retain dependency paths from their recorded state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "documents" / "design").mkdir(parents=True)
            (
                root / "documents" / "design" / "dependency-contract-kinds.toml"
            ).write_text(
                'allowed_kinds = [\n  "test"\n]\n',
                encoding="utf-8",
            )
            issue = root / "issues" / "closed" / "AC-1.md"
            issue.parent.mkdir(parents=True)
            issue.write_text(
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Preserves a durable issue mirror.",
                        "upstream design ../../documents/removed-document.md historical reference",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(issue), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_rejects_dependency_path_escaping_root(self) -> None:
        """Dependency targets that resolve above ROOT_DIR are rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow = root / ".github" / "workflows" / "agent-improvement-guide.yml"
            outside = root / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Rejects root-escaping dependency paths.",
                        "# upstream design ../../../outside.md escapes root",
                        "# @dependency-end",
                        "name: Agent Improvement Guide",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(workflow), root=root)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("dependency target escapes repository root", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_format_accepts_markdown_h1_before_manifest(self) -> None:
        """Markdown H1 titles may precede the dependency manifest near the top."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text("# Target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source Title",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises H1 before manifest parsing.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_accepts_coverage_rule_manifest_lines(self) -> None:
        """Coverage-rule manifest lines are valid non-edge dependency metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises coverage-rule metadata in dependency manifests.",
                        "upstream design README.md readme context",
                        "coverage graph_trace requires node record|edge record",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_accepts_registered_contract_kind(self) -> None:
        """Format validation accepts registry-backed manifest metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract design",
                        "responsibility Exercises registered contract kind metadata.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_rejects_missing_contract_kind(self) -> None:
        """Format validation rejects manifests without contract metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "responsibility Exercises missing contract kind metadata.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one contract line", result.stdout)
            self.assertIn("fix: add 'contract <registered-kind>'", result.stdout)
            self.assertIn(
                "documents/design/dependency-contract-kinds.toml", result.stdout
            )
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_format_rejects_unregistered_contract_kind(self) -> None:
        """Format validation keeps contract kinds in the registry."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract invented-kind",
                        "responsibility Exercises unregistered contract kind metadata.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unregistered contract kind", result.stdout)
            self.assertIn("fix: use an existing allowed_kinds entry", result.stdout)
            self.assertIn(
                "documents/design/dependency-contract-kinds.toml", result.stdout
            )
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_format_accepts_skill_frontmatter_before_html_manifest(self) -> None:
        """YAML frontmatter may precede an HTML-comment dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "SKILL.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo",
                        "description: Demo skill.",
                        "---",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises skill frontmatter manifest parsing.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_scan_and_format_accept_shell_and_toml_line_comments(self) -> None:
        """Shell and TOML files can use line-comment dependency manifests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.md"
            shell = root / "script.sh"
            toml = root / "config.toml"
            target.write_text("# Target\n", encoding="utf-8")
            shell.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises shell manifest parsing.",
                        "# upstream design target.md target context",
                        "# @dependency-end",
                        "set -euo pipefail",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            toml.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises TOML manifest parsing.",
                        "# upstream design target.md target context",
                        "# @dependency-end",
                        "[tool.demo]",
                        "enabled = true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(shell),
                str(toml),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(shell),
                str(toml),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)

    def test_allow_frontmatter_flag_is_accepted_by_manifest_tools(self) -> None:
        """Manifest tools accept an explicit frontmatter policy flag."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "SKILL.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo",
                        "description: Demo skill.",
                        "---",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises explicit frontmatter allowance.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--allow-frontmatter",
                str(source),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                "--allow-frontmatter",
                str(source),
                root=root,
            )
            graph = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--allow-frontmatter",
                str(source),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertEqual(graph.returncode, 0, graph.stdout + graph.stderr)

    def test_scan_groups_missing_manifests_by_owner_and_explains(self) -> None:
        """Missing manifest output includes owner grouping and first-lines evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            product = root / "product.md"
            root_view = root / ".github" / "workflows" / "agent-coordination.yml"
            root_view.parent.mkdir(parents=True)
            product.write_text("# Product\n\nBody.\n", encoding="utf-8")
            root_view.write_text("name: Agent Coordination\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--explain-missing",
                str(product),
                str(root_view),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "MISSING_DEPENDENCY_MANIFEST=product.md owner=product_file",
                result.stdout,
            )
            self.assertIn(
                "MISSING_DEPENDENCY_MANIFEST=.github/workflows/"
                "agent-coordination.yml owner=root_view",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_MISSING_BY_OWNER product_file=1 root_view=1 "
                "symlink=0 submodule_source=0 other=0",
                result.stdout,
            )
            self.assertIn(
                "MISSING_DEPENDENCY_EXPLANATION_BEGIN=product.md", result.stdout
            )
            self.assertIn(
                "missing_start_and_end_markers_in_first_80_lines",
                result.stdout,
            )

    def test_graph_distinguishes_root_symlink_from_vendor_source(self) -> None:
        """Graph extraction should report the real vendor source, not the root symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vendor = root / "vendor" / "agent-canon"
            vendor.mkdir(parents=True)
            source = vendor / "ROOT_AGENTS.md"
            target = vendor / "README.md"
            target.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Root Agents",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines the vendor source for root agent instructions.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            os.symlink("vendor/agent-canon/ROOT_AGENTS.md", root / "AGENTS.md")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--print-edges",
                str(root / "AGENTS.md"),
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "upstream\tdesign\tvendor/agent-canon/ROOT_AGENTS.md\tvendor/agent-canon/README.md",
                result.stdout,
            )
            self.assertNotIn("upstream\tdesign\tAGENTS.md\t", result.stdout)

    def test_generated_root_copy_headers_resolve_in_projection_context(self) -> None:
        """Generated root-copy GitHub headers should resolve in projection context."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            root_copy = root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md"
            source_copy = (
                root
                / "vendor"
                / "agent-canon"
                / ".github"
                / "PULL_REQUEST_TEMPLATE"
                / "agent_canon.md"
            )
            issue_readme = root / "vendor" / "agent-canon" / "documents" / "runtime" / "private-feedback-knowledge.md"
            root_copy.parent.mkdir(parents=True)
            source_copy.parent.mkdir(parents=True)
            issue_readme.parent.mkdir(parents=True)
            issue_readme.write_text("# Issues\n", encoding="utf-8")
            content = "\n".join(
                [
                    "<!--",
                    "@dependency-start",
                    "contract test",
                    "responsibility Defines a template AgentCanon PR checklist copy.",
                    "upstream design ../../vendor/agent-canon/documents/runtime/private-feedback-knowledge.md private Issue packet storage",
                    "@dependency-end",
                    "-->",
                    "",
                ]
            )
            root_copy.write_text(content, encoding="utf-8")
            source_copy.write_text(content, encoding="utf-8")

            format_result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(root_copy),
                root=root,
            )
            graph_result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--print-edges",
                str(root_copy),
                root=root,
            )

            self.assertEqual(
                format_result.returncode,
                0,
                format_result.stdout + format_result.stderr,
            )
            self.assertEqual(
                graph_result.returncode,
                0,
                graph_result.stdout + graph_result.stderr,
            )
            self.assertIn(
                "upstream\tdesign\t.github/PULL_REQUEST_TEMPLATE/agent_canon.md\t"
                "vendor/agent-canon/documents/runtime/private-feedback-knowledge.md",
                graph_result.stdout,
            )
            self.assertNotIn("\tissues/README.md", graph_result.stdout)

    def test_graph_lists_related_dependency_surfaces_for_focus_path(self) -> None:
        """Focused graph output should list declared and incoming dependency edges."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            dependent = root / "tests" / "test_source.py"
            design = root / "design.md"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises focused dependency graph listing.",
                        "# upstream design design.md source design",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dependent.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Tests focused dependency graph listing.",
                        "# upstream implementation ../source.py source behavior",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--list-related",
                "--focus",
                "source.py",
                "source.py",
                "tests/test_source.py",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_RELATED_SURFACE=source.py", result.stdout)
            self.assertIn(
                "DEPENDENCY_RELATED_EDGE role=declared_upstream "
                "kind=design source=source.py target=design.md",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_RELATED_EDGE role=incoming_upstream "
                "kind=implementation source=tests/test_source.py target=source.py",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_RELATED_SURFACES=1", result.stdout)

    def test_graph_writes_machine_readable_tsv_artifact(self) -> None:
        """Graph checks can emit a stable TSV artifact for issue and PR evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            dependent = root / "tests" / "test_source.py"
            design = root / "design.md"
            graph_tsv = runtime_root_for(root) / "reports" / "dependency_graph.tsv"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises TSV dependency graph output.",
                        "# upstream design design.md source design",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dependent.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Tests TSV dependency graph output.",
                        "# upstream implementation ../source.py source behavior",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--graph-tsv",
                str(graph_tsv),
                "source.py",
                "tests/test_source.py",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"DEPENDENCY_GRAPH_TSV={graph_tsv}", result.stdout)
            self.assertEqual(
                graph_tsv.read_text(encoding="utf-8").splitlines(),
                [
                    "direction\tkind\tsource\ttarget",
                    "upstream\tdesign\tsource.py\tdesign.md",
                    "upstream\timplementation\ttests/test_source.py\tsource.py",
                ],
            )

    def test_graph_tsv_preserves_large_dependency_set_without_cap(self) -> None:
        """Graph extraction emits every declared edge for downstream coverage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "sources"
            source_dir.mkdir()
            (root / "design.md").write_text("# Design\n", encoding="utf-8")
            edge_count = 1205
            source_paths: list[str] = []
            expected_edges: set[str] = set()
            for index in range(edge_count):
                relative_source = f"sources/source-{index}.py"
                (root / relative_source).write_text(
                    "\n".join(
                        [
                            "# @dependency-start",
                            "# contract test",
                            "# responsibility Exercises uncapped dependency graph output.",
                            "# upstream design ../design.md complete edge",
                            "# @dependency-end",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                source_paths.append(relative_source)
                expected_edges.add(f"upstream\tdesign\t{relative_source}\tdesign.md")
            graph_tsv = runtime_root_for(root) / "reports" / "dependency_graph.tsv"

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--graph-tsv",
                str(graph_tsv),
                *source_paths,
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows = graph_tsv.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), edge_count + 1)
            self.assertEqual(rows[0], "direction\tkind\tsource\ttarget")
            self.assertEqual(set(rows[1:]), expected_edges)

    def test_graph_expands_search_hits_to_edit_scope(self) -> None:
        """Search hit files should expand to declared and incoming dependency scope."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            dependent = root / "tests" / "test_source.py"
            design = root / "design.md"
            hits = root / "search_hits.txt"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises search edit-scope expansion.",
                        "# upstream design design.md source design",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dependent.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Tests search edit-scope expansion.",
                        "# upstream implementation ../source.py source behavior",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            hits.write_text("source.py:1:needle\n", encoding="utf-8")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--search-hits-file",
                str(hits),
                "source.py",
                "tests/test_source.py",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=source.py",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=declared_upstream "
                "kind=design path=design.md source=source.py target=design.md",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=incoming_upstream "
                "kind=implementation path=tests/test_source.py "
                "source=tests/test_source.py target=source.py",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_EDIT_SCOPE_PATHS=3", result.stdout)

    def test_repo_review_report_dir_generates_graph_and_edit_scope(self) -> None:
        """Repo dependency review should persist graph and edit-scope artifacts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            target = root / "target.md"
            source = root / "source.md"
            hits = root / "search_hits.txt"
            report_dir = runtime_root_for(root) / "reports" / "dependency-review"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target fixture for report artifacts.",
                        "downstream design source.md source consumes target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source fixture for report artifacts.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            hits.write_text("source.md:1:Source\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--report-dir",
                str(report_dir),
                "--search-hits-file",
                str(hits),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((report_dir / "dependency_graph.tsv").is_file())
            self.assertTrue((report_dir / "dependency_edit_scope.txt").is_file())
            self.assertIn(
                "direction\tkind\tsource\ttarget",
                (report_dir / "dependency_graph.tsv").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=source.md",
                (report_dir / "dependency_edit_scope.txt").read_text(encoding="utf-8"),
            )

    def test_repo_review_report_dir_without_search_hits_records_changed_scope(
        self,
    ) -> None:
        """Report-dir dependency review persists changed-file edit scope by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            target = root / "target.md"
            source = root / "source.md"
            report_dir = runtime_root_for(root) / "reports" / "dependency-review"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target fixture for changed scope.",
                        "downstream design source.md source consumes target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source fixture for changed scope.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=test@example.invalid",
                    "-c",
                    "user.name=Test User",
                    "commit",
                    "-m",
                    "seed dependency fixture",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            source.write_text(
                source.read_text(encoding="utf-8") + "changed\n",
                encoding="utf-8",
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--report-dir",
                str(report_dir),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((report_dir / "dependency_edit_scope.txt").is_file())
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=source.md",
                (report_dir / "dependency_edit_scope.txt").read_text(encoding="utf-8"),
            )

    def test_symlink_root_views_are_skipped_without_breaking_scan(self) -> None:
        """Root symlink views are owned by link-root and do not fail header scans."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vendor = root / "vendor" / "agent-canon"
            vendor.mkdir(parents=True)
            (vendor / "README.md").write_text(
                "\n".join(
                    [
                        "# Vendor",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines a vendor source fixture.",
                        "upstream design README.md self fixture",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            os.symlink("vendor/agent-canon/README.md", root / "README.md")

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(root / "README.md"),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(root / "README.md"),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)

    def test_legal_license_files_are_skipped_without_dependency_headers(self) -> None:
        """Canonical legal license files keep standard legal text without repo headers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            license_file = root / "LICENSE"
            license_file.write_text("Apache License\nVersion 2.0\n", encoding="utf-8")

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(license_file),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(license_file),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)

    def test_agent_runtime_surfaces_pass_manifest_scan_and_format(self) -> None:
        """Agent runtime docs and skill surfaces stay compatible with manifest tools."""
        paths = [
            ".agents/skills/codex-task-workflow/SKILL.md",
            ".codex/README.md",
            "ROOT_AGENTS.md",
            "agents/TASK_WORKFLOWS.md",
            "agents/USER_GUIDE_JA.md",
            "agents/skills/catalog.yaml",
            "agents/skills/worktree-start.md",
            "agents/task_catalog.yaml",
            "agents/workflows/adaptive-improvement-workflow.md",
            "agents/workflows/agent-canon-pr-workflow.md",
            "agents/workflows/agent-learning-workflow.md",
            "agents/workflows/experiment-workflow.md",
            "agents/workflows/implementation-waterfall-workflow.md",
            "documents/operations/BRANCH_SCOPE.md",
            "documents/design/algorithm-implementation-boundary.md",
            "documents/codex/codex-configuration-reference.md",
            "documents/conventions/coding-conventions-project.md",
            "documents/conventions/coding-conventions-reviews.md",
            "documents/conventions/python/20_benchmark_policy.md",
            "documents/experiments/experiment-critical-review.md",
            "documents/tools/README.md",
            "documents/operations/worktree-lifecycle.md",
            "documents/notes/knowledge/README.md",
            "documents/notes/knowledge",
            "documents/notes/README.md",
            "documents/notes/guardrails/engineering_avoidances.md",
        ]

        scan = run_tool(
            str(SCAN),
            "--root",
            str(PROJECT_ROOT),
            "--fail-missing",
            *paths,
            root=PROJECT_ROOT,
        )
        fmt = run_tool(
            str(FORMAT),
            "--root",
            str(PROJECT_ROOT),
            "--require-header",
            *paths,
            root=PROJECT_ROOT,
        )

        self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
        self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
        self.assertIn("DEPENDENCY_HEADER_SCAN=pass", scan.stdout)
        self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)
        self.assertTrue((PROJECT_ROOT / "ROOT_AGENTS.md").is_file())
        template_root = PROJECT_ROOT.parent.parent
        embedded_vendor = template_root / "vendor" / "agent-canon"
        if embedded_vendor.exists() and embedded_vendor.resolve() == PROJECT_ROOT:
            self.assertFalse((template_root / "ROOT_AGENTS.md").exists())
            self.assertTrue((template_root / "AGENTS.md").is_symlink())
            self.assertEqual(
                (template_root / "AGENTS.md").readlink().as_posix(),
                "vendor/agent-canon/ROOT_AGENTS.md",
            )

    def test_format_accepts_json_string_manifest(self) -> None:
        """JSON files can keep valid syntax by storing manifest lines as strings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.json"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "{",
                        '  "_dependency_manifest": [',
                        '    "@dependency-start",',
                        '    "contract test",',
                        '    "responsibility Exercises a JSON string manifest.",',
                        '    "upstream implementation target.py target contract",',
                        '    "@dependency-end"',
                        "  ],",
                        '  "ok": true',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_scan_skips_strict_json_without_manifest(self) -> None:
        """Strict JSON is commentless and is not part of required header coverage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)

    def test_require_header_skips_strict_json_without_manifest(self) -> None:
        """Strict JSON without manifest markers remains valid under require-header."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_require_header_skips_agent_run_artifacts(self) -> None:
        """Run-bundle artifacts are workflow evidence, not product manifest surface."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report = root / "reports" / "agents" / "run-1" / "verification.txt"
            report.parent.mkdir(parents=True)
            report.write_text("status=pass\n", encoding="utf-8")

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(report),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_rejects_invalid_direction(self) -> None:
        """The format checker rejects unknown directions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.py"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises invalid direction validation.",
                        "# sideways implementation target.py invalid direction",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid direction", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_graph_accepts_bidirectional_edges(self) -> None:
        """Matching upstream/downstream reverse edges pass graph validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines source a for graph validation.",
                        "# downstream implementation b.py b consumes a",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines source b for graph validation.",
                        "# upstream implementation a.py a is consumed by b",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                str(a),
                str(b),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH=pass", result.stdout)

    def test_graph_rejects_isolated_manifest(self) -> None:
        """The graph checker rejects manifests that do not connect to any edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises isolated manifest validation.",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(GRAPH), "--root", str(root), str(source), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("isolated dependency manifest", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_rejects_missing_reverse_edge(self) -> None:
        """Strict bidirectional mode requires the matching reverse edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines source a for reverse validation.",
                        "# downstream implementation b.py b consumes a",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text("# no manifest\n", encoding="utf-8")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--check-bidirectional",
                str(a),
                str(b),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing reverse upstream implementation edge", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_rejects_upstream_cycles(self) -> None:
        """The graph checker detects cycles in the upstream graph."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# upstream implementation b.py b is prerequisite",
                        "# downstream implementation b.py b also affected",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# upstream implementation a.py a is prerequisite",
                        "# downstream implementation a.py a also affected",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                str(a),
                str(b),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cycle includes", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_can_report_cycles_without_failing(self) -> None:
        """Cycle report-only mode keeps known graph debt visible without blocking."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines a fixture with a known cycle.",
                        "# upstream implementation b.py b is prerequisite",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines b fixture with a known cycle.",
                        "# upstream implementation a.py a is prerequisite",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--cycle-report-only",
                str(a),
                str(b),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("cycle includes", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH_UPSTREAM_CYCLES=report_only", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=pass", result.stdout)

    def test_repo_review_runs_all_dependency_tools(self) -> None:
        """The wrapper applies dependency tools to tracked checkable files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target test fixture context.",
                        "downstream design source.md source reads target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(str(REPO_REVIEW), "--root", str(root), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_can_report_cycles_without_failing(self) -> None:
        """The wrapper supports report-only cycles when a durable graph artifact is used."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            (tool_dir / "agent_team.py").symlink_to(AGENT_TEAM)
            a = root / "a.md"
            b = root / "b.md"
            a.write_text(
                "\n".join(
                    [
                        "# A",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines a cycle-report-only fixture.",
                        "upstream design b.md b is prerequisite",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# B",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines b cycle-report-only fixture.",
                        "upstream design a.md a is prerequisite",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "a.md", "b.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--cycle-report-only",
                "--report-dir",
                str(runtime_root_for(root) / "reports" / "dependency-review" / "run"),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH_UPSTREAM_CYCLES=report_only", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_skips_dependency_review_artifacts(self) -> None:
        """Generated dependency-review outputs are not repo source inputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target test fixture context.",
                        "downstream design source.md source reads target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            artifact = (
                root / "reports" / "dependency-review" / "run" / "search_hits.txt"
            )
            artifact.parent.mkdir(parents=True)
            artifact.write_text("source.md\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "add",
                    "target.md",
                    "source.md",
                    "reports/dependency-review/run/search_hits.txt",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
            self.assertNotIn(
                "reports/dependency-review/run/search_hits.txt", result.stdout
            )

    def test_repo_review_records_monitoring_when_report_dir_is_given(self) -> None:
        """The review wrapper records monitoring evidence when directed to a run."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            (tool_dir / "agent_team.py").symlink_to(AGENT_TEAM)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target test fixture context.",
                        "downstream design source.md source reads target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            report_dir = runtime_root_for(root) / "reports" / "agents" / "run-3"

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--report-dir",
                str(report_dir),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn("repo_dependency_review=pass", text)
            self.assertIn(
                "run_repo_dependency_review.sh recorded dependency review pass",
                text,
            )

    def graph_ensure_fixture(
        self,
        root: Path,
        statuses: list[tuple[str, int, object, object]],
        build_exit: int = 0,
    ) -> tuple[Path, Path]:
        """Create a source-root fixture with scripted status/build readback."""
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.git_output(root, "config", "user.email", "graph@example.invalid")
        self.git_output(root, "config", "user.name", "Graph Fixture")
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git_output(root, "add", "README.md")
        self.git_output(root, "commit", "-m", "graph fixture")
        tools_dir = root / "tools"
        (tools_dir / "bin").mkdir(parents=True)
        (tools_dir / "agent_tools").mkdir()
        script = (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
            "root = Path(sys.argv[sys.argv.index('--root') + 1])\n"
            "calls = root / '.graph-calls'\n"
            "call = ' '.join(sys.argv[1:3])\n"
            "calls.write_text(calls.read_text() + call + '\\n' if calls.exists() else call + '\\n')\n"
            "if sys.argv[1:3] == ['graph', 'build']:\n"
            f"    print(json.dumps({{'exit_code': {build_exit}}}))\n"
            f"    raise SystemExit({build_exit})\n"
            "if sys.argv[1:3] == ['graph', 'status']:\n"
            "    sequence = json.loads(os.environ['GRAPH_STATUS_SEQUENCE'])\n"
            "    index = sum(1 for line in calls.read_text().splitlines() if line == 'graph status') - 1\n"
            "    status, exit_code, reason, probe_reason = sequence[min(index, len(sequence) - 1)]\n"
            "    payload = json.loads(os.environ['GRAPH_STATUS_JSON'])\n"
            "    payload['status'] = status\n"
            "    payload['exit_code'] = exit_code\n"
            "    payload['reason'] = reason\n"
            "    payload['probe_reason'] = probe_reason\n"
            "    print(json.dumps(payload))\n"
            "    raise SystemExit(exit_code)\n"
            "raise SystemExit(2)\n"
        )
        executable = tools_dir / "bin" / "agent-canon"
        executable.write_text(script, encoding="utf-8")
        executable.chmod(0o755)
        return executable, root / ".graph-calls"

    def run_graph_ensure_fixture(
        self,
        root: Path,
        statuses: list[tuple[str, int, object, object]],
        build_exit: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        """Run the existing dependency-review graph ensure route."""
        executable, calls = self.graph_ensure_fixture(root, statuses, build_exit)
        environment = os.environ.copy()
        environment.update(
            {
                "AGENT_CANON_RUNTIME_ROOT": str(runtime_root_for(root)),
                "AGENT_CANON_CONTROL_PARENT_ROOT": str(root.parent.resolve()),
                "AGENT_CANON_GRAPH_CLI": str(executable),
                "GRAPH_STATUS_SEQUENCE": json.dumps(statuses),
                "GRAPH_STATUS_JSON": json.dumps(
                    {
                        "schema": "agent-canon.graph.status.v1",
                        "command": "status",
                        "status": "fresh",
                        "exit_code": 0,
                        "reason": None,
                        "probe_reason": None,
                    }
                ),
            }
        )
        result = subprocess.run(
            [
                "bash",
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--ensure-graph",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        result.calls_path = calls  # type: ignore[attr-defined]
        return result

    def test_graph_ensure_fresh_does_not_build(self) -> None:
        """Fresh status is accepted without invoking the producer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.run_graph_ensure_fixture(
                Path(tmp_dir), [("fresh", 0, None, None)]
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GRAPH_ENSURE=pass status=fresh", result.stdout)
            self.assertIn("GRAPH_REBUILD=not_needed", result.stdout)
            self.assertEqual(
                result.calls_path.read_text(encoding="utf-8").splitlines(),
                ["graph status"],
            )

    def test_graph_ensure_source_changed_builds_once_and_reads_fresh(self) -> None:
        """Only a typed source-change status performs one build."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.run_graph_ensure_fixture(
                Path(tmp_dir),
                [
                    ("stale", 2, "source_changed", "source_changed"),
                    ("fresh", 0, None, None),
                ],
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GRAPH_REBUILD=performed", result.stdout)
            self.assertEqual(
                result.calls_path.read_text(encoding="utf-8").splitlines(),
                ["graph status", "graph build", "graph status"],
            )

    def test_graph_ensure_non_source_status_fails_without_build(self) -> None:
        """Corruption, unknown, and non-source statuses never admit rebuilding."""
        cases = (
            (
                "stale",
                2,
                "persisted_readback_mismatch",
                "persisted_readback_mismatch",
            ),
            ("stale", 2, "unknown_reason", "unknown_reason"),
            ("stale", 2, "runtime_evidence_changed", "runtime_evidence_changed"),
            ("stale", 2, "producer_identity_changed", "producer_identity_changed"),
            ("stale", 2, "source_changed", None),
            ("stale", 2, 1, "source_changed"),
            ("unavailable", 1, "graph_unavailable", None),
            ("incomplete", 2, "source_completeness_incomplete", None),
            ("invalid", 1, None, None),
        )
        for status in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp_dir:
                result = self.run_graph_ensure_fixture(Path(tmp_dir), [status])

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("REPO_DEPENDENCY_REVIEW=fail", result.stdout)
                self.assertEqual(
                    result.calls_path.read_text(encoding="utf-8").splitlines(),
                    ["graph status"],
                )

    def test_graph_ensure_fails_closed_for_build_or_readback_failure(self) -> None:
        """Build failure and non-fresh readback stay closed."""
        cases = (
            ([
                ("stale", 2, "source_changed", "source_changed"),
            ], 3, "GRAPH_REBUILD=failed rc=3", True),
            ([
                ("stale", 2, "source_changed", "source_changed"),
                ("stale", 2, "source_changed", "source_changed"),
            ], 0, "REPO_DEPENDENCY_REVIEW=fail", True),
            ([
                ("stale", 2, "source_changed", "source_changed"),
                (
                    "stale",
                    2,
                    "persisted_readback_mismatch",
                    "persisted_readback_mismatch",
                ),
            ], 0, "REPO_DEPENDENCY_REVIEW=fail", True),
        )
        for statuses, build_exit, expected, build_expected in cases:
            with self.subTest(statuses=statuses, build_exit=build_exit), tempfile.TemporaryDirectory() as tmp_dir:
                result = self.run_graph_ensure_fixture(
                    Path(tmp_dir), statuses, build_exit
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)
                calls = result.calls_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual("graph build" in calls, build_expected)

    def test_repo_review_reports_missing_manifests_by_default(self) -> None:
        """The repo-wide wrapper keeps missing headers report-only during migration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            source = root / "source.md"
            source.write_text("# Source\n\nBody.\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(str(REPO_REVIEW), "--root", str(root), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=source.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_can_require_missing_manifests(self) -> None:
        """Strict mode fails when tracked checkable files lack manifests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            source = root / "source.md"
            source.write_text("# Source\n\nBody.\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=source.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)


if __name__ == "__main__":
    unittest.main()
