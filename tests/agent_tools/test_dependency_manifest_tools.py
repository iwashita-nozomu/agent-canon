"""Tests for dependency manifest shell tools."""

# @dependency-start
# responsibility Tests dependency manifest shell tool behavior.
# upstream design ../../documents/dependency-manifest-design.md manifest design
# upstream implementation ../../tools/agent_tools/scan_dependency_headers.sh scans
# upstream implementation ../../tools/agent_tools/check_dependency_header_format.sh format checks
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh graph checks
# upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh wraps
# upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh scans code
# @dependency-end

from __future__ import annotations

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
WORKFLOW_MONITOR = PROJECT_ROOT / "tools" / "agent_tools" / "workflow_monitor.py"
AGENT_TEAM = PROJECT_ROOT / "tools" / "agent_tools" / "agent_team.py"


def run_tool(*args: str, root: Path) -> subprocess.CompletedProcess[str]:
    """Run a dependency manifest shell tool."""
    return subprocess.run(
        ["bash", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class DependencyManifestToolTest(unittest.TestCase):
    """Exercise the dependency manifest shell tools."""

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
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
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
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "CODE_DEPENDENCY\tc-family\tinclude\tmain.cpp\tinclude/api.hpp\tinclude/api.hpp",
                result.stdout,
            )

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
                        "# responsibility Exercises TOML manifest parsing.",
                        "# upstream design target.md target context",
                        "# @dependency-end",
                        "[tool.demo]",
                        'enabled = true',
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
            submodule = root / "vendor" / "agent-canon" / "shared.md"
            root_view.parent.mkdir(parents=True)
            submodule.parent.mkdir(parents=True)
            product.write_text("# Product\n\nBody.\n", encoding="utf-8")
            root_view.write_text("name: Agent Coordination\n", encoding="utf-8")
            submodule.write_text("# Shared\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--explain-missing",
                str(product),
                str(root_view),
                str(submodule),
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
                "MISSING_DEPENDENCY_MANIFEST=vendor/agent-canon/shared.md owner=submodule_source",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_MISSING_BY_OWNER product_file=1 root_view=1 "
                "symlink=0 submodule_source=1 other=0",
                result.stdout,
            )
            self.assertIn("MISSING_DEPENDENCY_EXPLANATION_BEGIN=product.md", result.stdout)
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

    def test_root_copy_headers_resolve_in_agentcanon_source_context(self) -> None:
        """Root-copy GitHub headers should keep valid AgentCanon-source paths."""
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
            issue_readme = root / "vendor" / "agent-canon" / "issues" / "README.md"
            root_copy.parent.mkdir(parents=True)
            source_copy.parent.mkdir(parents=True)
            issue_readme.parent.mkdir(parents=True)
            issue_readme.write_text("# Issues\n", encoding="utf-8")
            content = "\n".join(
                [
                    "<!--",
                    "@dependency-start",
                    "responsibility Defines a template AgentCanon PR checklist copy.",
                    "upstream design ../../issues/README.md durable issue storage",
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
                "vendor/agent-canon/issues/README.md",
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
            graph_tsv = root / "reports" / "dependency_graph.tsv"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
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
            report_dir = root / "reports" / "dependency-review"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
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
            self.assertIn("direction\tkind\tsource\ttarget", (report_dir / "dependency_graph.tsv").read_text(encoding="utf-8"))
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
            ".claude/skills/adaptive-improvement-loop/SKILL.md",
            ".claude/skills/codex-task-workflow/SKILL.md",
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
            "documents/BRANCH_SCOPE.md",
            "documents/algorithm-implementation-boundary.md",
            "documents/codex-configuration-reference.md",
            "documents/coding-conventions-project.md",
            "documents/coding-conventions-reviews.md",
            "documents/conventions/python/20_benchmark_policy.md",
            "documents/experiment-critical-review.md",
            "documents/tools/README.md",
            "documents/worktree-lifecycle.md",
            "memory/AGENT_PHILOSOPHY.md",
            "memory/USER_PREFERENCES.md",
            "notes/README.md",
            "notes/guardrails/engineering_avoidances.md",
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
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            artifact = root / "reports" / "dependency-review" / "run" / "search_hits.txt"
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
            self.assertNotIn("reports/dependency-review/run/search_hits.txt", result.stdout)

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
            report_dir = root / "reports" / "agents" / "run-3"

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
