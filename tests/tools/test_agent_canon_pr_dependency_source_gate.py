"""Integration tests for the PR dependency source gate."""

# @dependency-start
# contract test
# responsibility Verifies PR dependency validation runs without graph runtime state.
# upstream implementation ../../tools/ci/run_pr_dependency_source_gate.sh owns source review routing
# upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh owns source validation
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh consumes the gate status
# @dependency-end

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_GATE = PROJECT_ROOT / "tools" / "ci" / "run_pr_dependency_source_gate.sh"


def write_executable(path: Path, content: str) -> None:
    """Write one executable fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class AgentCanonPrDependencySourceGateTest(unittest.TestCase):
    """Exercise required and skipped source-review routes."""

    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        """Create source-review stubs without a graph executable."""
        tools = root / "canon-tools"
        report = root / "reports" / "dependency"
        packet = root / "changed-paths.json"
        packet.write_text("{}\n", encoding="utf-8")
        log = root / "calls.log"
        write_executable(
            tools / "agent_tools" / "run_repo_dependency_review.sh",
            f"""
            #!/usr/bin/env bash
            printf 'review:%s\\n' "$*" >> {log!s}
            args=("$@")
            for ((index = 0; index < $#; index++)); do
              if [[ "${{args[$index]}}" == "--report-dir" ]]; then
                mkdir -p "${{args[$((index + 1))]}}"
              fi
            done
            """,
        )
        write_executable(
            tools / "agent_tools" / "tool_drift.py",
            f"""
            #!/usr/bin/env python3
            from pathlib import Path
            Path({str(log)!r}).open('a', encoding='utf-8').write('tool-drift\\n')
            """,
        )
        write_executable(
            tools / "agent_tools" / "render_dependency_manifest_graph.py",
            f"""
            #!/usr/bin/env python3
            import sys
            from pathlib import Path
            args = sys.argv[1:]
            Path({str(log)!r}).open('a', encoding='utf-8').write('render\\n')
            for option in ('--markdown-out', '--dot-out'):
                output = Path(args[args.index(option) + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text('source projection\\n', encoding='utf-8')
            """,
        )
        return tools, report, packet

    def run_gate(
        self,
        root: Path,
        tools: Path,
        report: Path,
        packet: Path,
        *,
        required: int,
        base: str = "a" * 40,
    ) -> subprocess.CompletedProcess[str]:
        """Run the production source-gate shell against fixture tools."""
        environment = dict(os.environ)
        environment.pop("AGENT_CANON_PARENT_ROOT", None)
        return subprocess.run(
            [
                "bash",
                str(SOURCE_GATE),
                "--root",
                str(root),
                "--tools-root",
                str(tools),
                "--report-dir",
                str(report),
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                base,
                "--source-review-required",
                str(required),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_required_standalone_route_runs_source_checks_without_graph(self) -> None:
        """Required review runs drift, source graph, and rendering without runtime."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tools, report, packet = self.fixture(root)

            result = self.run_gate(
                root,
                tools,
                report,
                packet,
                required=1,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_CANON_PR_DEPENDENCY_SOURCE=source", result.stdout)
            calls = (root / "calls.log").read_text(encoding="utf-8")
            self.assertIn("tool-drift", calls)
            self.assertIn("--cycle-report-only", calls)
            self.assertIn("render", calls)
            self.assertFalse((tools / "bin" / "agent-canon").exists())
            self.assertFalse((root / ".agent-canon").exists())

    def test_skipped_parent_route_runs_only_trusted_header_scan(self) -> None:
        """Out-of-surface changes retain trusted header scan without full review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tools, report, packet = self.fixture(root)

            result = self.run_gate(
                root,
                tools,
                report,
                packet,
                required=0,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_CANON_PR_DEPENDENCY_SOURCE=skipped", result.stdout)
            calls = (root / "calls.log").read_text(encoding="utf-8")
            self.assertIn("--header-scan-only", calls)
            self.assertNotIn("tool-drift", calls)
            self.assertNotIn("render", calls)

    def test_invalid_trusted_base_fails_before_any_source_tool(self) -> None:
        """The changed-path packet remains bound to a commit-shaped base identity."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tools, report, packet = self.fixture(root)

            result = self.run_gate(
                root,
                tools,
                report,
                packet,
                required=1,
                base="not-a-commit",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("trusted_base_invalid", result.stdout)
            self.assertFalse((root / "calls.log").exists())


if __name__ == "__main__":
    unittest.main()
