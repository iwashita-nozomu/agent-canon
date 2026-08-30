"""Executable writer/parser/consumer checks for the PR gate receipt."""

# @dependency-start
# contract test
# responsibility Verifies the live source receipt writer and consumer handoff.
# upstream implementation ../../tools/validation/ci/checks/check_agent_canon_pr.sh owns receipt production
# upstream implementation ../../tools/validation/ci/receipts/pr_gate_receipt.py owns receipt serialization and parsing
# downstream implementation ../../tools/validation/ci/runners/run_all_checks.sh consumes one validated status
# downstream design ../../documents/design/source-owned-dependency-validation.md owns source/runtime separation
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_TOOL = PROJECT_ROOT / "tools" / "validation" / "ci" / "receipts" / "pr_gate_receipt.py"
PR_CHECK = PROJECT_ROOT / "tools" / "validation" / "ci" / "checks" / "check_agent_canon_pr.sh"
RUN_ALL_CHECKS = PROJECT_ROOT / "tools" / "validation" / "ci" / "runners" / "run_all_checks.sh"


class LiveReceiptFixture:
    """Build a minimal standalone checkout for the production shell scripts."""

    COPIED_FILES = (
        "tools/validation/ci/checks/check_agent_canon_pr.sh",
        "tools/validation/ci/receipts/pr_gate_receipt.py",
        "tools/validation/ci/runners/run_all_checks.sh",
        "tools/validation/ci/checks/run_python_quality_checks.sh",
        "tools/repository/support/repo_paths.sh",
        "tools/repository/workspace/parent_root_side_effects.py",
        "tools/runtime/artifacts/runtime_artifacts.py",
        "tools/agent/orchestration/review_dispatch.py",
        "tools/runtime/artifacts/artifact_identity.py",
        "tools/runtime/artifacts/external_artifact_binding.py",
        "tools/repository/github/publication_integrator.py",
        "tools/runtime/artifacts/report_artifact_checks.py",
        "tools/runtime/archive/work_log.py",
        "tools/runtime/artifacts/generated_artifact_guard.py",
        "tests/agent_tools/test_artifact_identity.py",
        "tests/agent_tools/test_codex_hooks.py",
        "tests/agent_tools/test_external_artifact_binding.py",
        "tests/agent_tools/test_publication_integrator.py",
        "tests/agent_tools/test_review_dispatch.py",
        "tests/agent_tools/test_work_log.py",
    )

    def __init__(self, root: Path, status: str) -> None:
        """Bind the fixture root and source-gate status used by one case."""
        self.temp_root = root
        self.control_root = root / "control"
        self.root = self.control_root / "workspace" / "agent-canon"
        self.runtime_root = self.control_root / "workspace" / "agent-canon-runtime" / "pr-gate"
        self.status = status
        self.log = root / "calls.log"
        self.bin = root / "bin"

    def copy_file(self, relative: str) -> None:
        """Copy one production file while preserving its executable mode."""
        source = PROJECT_ROOT / relative
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def write_executable(self, relative: str, content: str) -> None:
        """Write one fixture command with an executable mode."""
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(0o755)

    def write_external_executable(self, name: str, content: str) -> None:
        """Write a fake tool outside the source checkout."""
        target = self.bin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(0o755)

    def prepare(self) -> None:
        """Install production scripts and unrelated-check stubs."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.control_root.mkdir(parents=True, exist_ok=True)
        (self.control_root / ".gitignore").write_text("/workspace/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.control_root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "control@example.invalid"],
            cwd=self.control_root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Control Fixture"],
            cwd=self.control_root,
            check=True,
        )
        subprocess.run(["git", "add", ".gitignore"], cwd=self.control_root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "control fixture"],
            cwd=self.control_root,
            check=True,
        )
        for relative in self.COPIED_FILES:
            self.copy_file(relative)
        self.write_executable(
            "tools/validation/ci/checks/run_pr_dependency_source_gate.sh",
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            "printf 'source_gate=%s\\n' \"${SOURCE_STATUS:?}\" >> \"${CALL_LOG:?}\"\n"
            "printf 'AGENT_CANON_PR_DEPENDENCY_SOURCE=%s\\n' \"${SOURCE_STATUS}\"\n",
        )
        self.write_executable(
            "tools/validation/ci/runners/run_standalone_static_gate_unit.sh",
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            "printf 'static_gate_unit=%s\\n' \"$1\" >> \"${CALL_LOG:?}\"\n",
        )
        self.write_executable(
            "tools/validation/ci/checks/check_github_workflows.py",
            "#!/usr/bin/env python3\n",
        )
        self.write_executable(
            "tools/runtime/artifacts/generated_artifact_guard.py",
            "#!/usr/bin/env python3\n"
            "from __future__ import annotations\n",
        )
        self.write_executable(
            "tools/bin/agent-canon",
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            "printf 'agent-canon=%s\\n' \"$*\" >> \"${CALL_LOG:?}\"\n",
        )
        self.write_executable(
            "tools/validation/ci/checks/agent_canon_pr_graph_selector.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--changed-path-packet', type=Path)\n"
            "parser.add_argument('--root')\n"
            "parser.add_argument('--source-root')\n"
            "parser.add_argument('--trusted-base-sha')\n"
            "args, _ = parser.parse_known_args()\n"
            "if args.changed_path_packet is not None:\n"
            "    args.changed_path_packet.parent.mkdir(parents=True, exist_ok=True)\n"
            "    args.changed_path_packet.write_text('{}\\n', encoding='utf-8')\n"
            "print('AGENT_CANON_PR_DEPENDENCY_GRAPH=required')\n"
            "print('AGENT_CANON_PR_DEPENDENCY_GRAPH_REASON=fixture_source_review')\n"
            "print('AGENT_CANON_PR_DEPENDENCY_GRAPH_EVIDENCE=base=' + 'a' * 40)\n",
        )
        self.bin.mkdir(parents=True, exist_ok=True)
        self.write_external_executable(
            "quality-python",
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            "printf 'quality-python=%s\\n' \"$*\" >> \"${CALL_LOG:?}\"\n",
        )
        self.write_external_executable(
            "cargo",
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            "printf 'cargo=%s\\n' \"$*\" >> \"${CALL_LOG:?}\"\n",
        )
        self.write_external_executable(
            "gh",
            "#!/usr/bin/env bash\n"
            "exit 1\n",
        )
        self.log.write_text("", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=self.root, check=True)

    def environment(self) -> dict[str, str]:
        """Return the isolated command environment for the fixture checkout."""
        return {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "PYTHON_BIN": str(self.bin / "quality-python"),
            "CALL_LOG": str(self.log),
            "SOURCE_STATUS": self.status,
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(self.control_root),
            "AGENT_CANON_RUNTIME_ROOT": str(self.runtime_root),
        }

    def run_pr_check(self) -> subprocess.CompletedProcess[str]:
        """Run the actual producer, nested consumer, and cleanup lifecycle."""
        return subprocess.run(
            ["bash", str(self.root / "tools/validation/ci/checks/check_agent_canon_pr.sh")],
            cwd=self.root,
            env=self.environment(),
            check=False,
            capture_output=True,
            text=True,
        )


class PrGateReceiptRoundTripTest(unittest.TestCase):
    """Keep the producer/parser/consumer boundary executable and one-way."""

    def run_writer(self, root: Path, status: str) -> subprocess.CompletedProcess[str]:
        """Execute the production receipt writer CLI."""
        return subprocess.run(
            [
                sys.executable,
                str(RECEIPT_TOOL),
                "write",
                "--root",
                str(root),
                "--parent-pid",
                str(os.getpid()),
                "--status",
                status,
                "--selector-reason",
                "tracked_source_validated",
                "--selector-evidence",
                "base=" + "a" * 40,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_production_shell_round_trip_owns_live_receipt_for_each_status(self) -> None:
        """Run producer and consumer shells before producer cleanup for both statuses."""
        for status in ("source", "skipped"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                fixture = LiveReceiptFixture(Path(temporary), status)
                fixture.prepare()
                result = fixture.run_pr_check()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("AGENT_CANON_PR_GATE_RECEIPT_HANDOFF=consumed", result.stdout)
                self.assertIn(
                    f"PR_GATE_RECEIPT=accepted dependency_source={status}",
                    result.stdout,
                )
                receipt_lines = [
                    line
                    for line in result.stdout.splitlines()
                    if line.startswith("AGENT_CANON_PR_GATE_RECEIPT=")
                ]
                self.assertEqual(len(receipt_lines), 1)
                receipt_path = Path(receipt_lines[0].split("=", 1)[1])
                self.assertFalse(receipt_path.exists())
                calls = fixture.log.read_text(encoding="utf-8").splitlines()
                self.assertEqual(
                    sum(line.startswith("source_gate=") for line in calls), 1
                )
                self.assertFalse(any(line.startswith("check_dependency_header_format") for line in calls))
                self.assertFalse(any("graph build" in line for line in calls))
                self.assertFalse(any("graph status" in line for line in calls))
                self.assertFalse(any("graph query" in line for line in calls))
                self.assertFalse(any("graph context" in line for line in calls))

    def test_retired_states_fail_at_writer_and_shell_consumer_boundaries(self) -> None:
        """Reject retired states through both the writer and run-all shell consumer."""
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LiveReceiptFixture(Path(temporary), "source")
            fixture.prepare()
            valid = self.run_writer(Path(temporary), "source")
            self.assertEqual(valid.returncode, 0, valid.stderr)
            receipt = Path(temporary) / "retired.receipt"
            for status in ("prepared", "scoped"):
                with self.subTest(status=status):
                    written = self.run_writer(Path(temporary), status)
                    self.assertNotEqual(written.returncode, 0)
                    receipt.write_text(
                        valid.stdout.replace(
                            "strict_dependency=source", f"strict_dependency={status}"
                        ).replace("graph=source", f"graph={status}"),
                        encoding="utf-8",
                    )
                    consumed = subprocess.run(
                        [
                            "bash",
                            str(fixture.root / "tools/validation/ci/runners/run_all_checks.sh"),
                            "--pr-gate-receipt",
                            str(receipt),
                            "--pr-gate-parent-pid",
                            str(os.getpid()),
                        ],
                        cwd=fixture.root,
                        env=fixture.environment(),
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(consumed.returncode, 0)
                    self.assertNotIn("PR_GATE_RECEIPT=accepted", consumed.stdout)

    def test_shell_writer_and_consumer_delegate_to_one_parser(self) -> None:
        """Keep shell producer and consumer delegated to one parser."""
        producer = PR_CHECK.read_text(encoding="utf-8")
        consumer = RUN_ALL_CHECKS.read_text(encoding="utf-8")
        self.assertIn('pr_gate_receipt.py" write', producer)
        self.assertIn('pr_gate_receipt.py" validate', consumer)
        self.assertIn("--pr-gate-parent-pid", producer)
        self.assertIn("--pr-gate-parent-pid", consumer)
        self.assertNotIn('strict_dependency_status="$(awk', consumer)
        self.assertNotIn('graph_status="$(awk', consumer)
        self.assertIn("validated_source_receipt_consumed", consumer)
        self.assertNotIn('PR_GATE_DEPENDENCY_GRAPH_STATUS="', consumer)


if __name__ == "__main__":
    unittest.main()
