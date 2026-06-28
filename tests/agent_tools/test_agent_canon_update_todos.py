# @dependency-start
# contract test
# responsibility Tests AgentCanon update TODO state routing for parent repositories.
# upstream design ../../documents/agent-canon-parent-repo-latest-checklist.md parent update TODO workflow
# upstream design ../../documents/agent-canon-update-tasks.toml shared update TODO manifest
# upstream implementation ../../tools/agent_tools/agent_canon_update_todos.py manages parent update state
# @dependency-end

"""Tests for parent-repository AgentCanon update TODO routing."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "agent_canon_update_todos.py"
TASK_ID = "ACUT-test-parent-state"


def run_git(repo: Path, *args: str) -> str:
    """Run git in a fixture repository."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    """Commit all fixture changes and return HEAD."""
    run_git(repo, "add", ".")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=AgentCanon Update Todo Test",
            "-c",
            "user.email=agentcanon-update-todo@example.invalid",
            "commit",
            "-m",
            message,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return run_git(repo, "rev-parse", "HEAD")


def write_manifest(canon_root: Path, boundary: str) -> None:
    """Write a minimal update TODO manifest."""
    manifest = canon_root / "documents" / "agent-canon-update-tasks.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        "\n".join(
            [
                'manifest_kind = "agent_canon_update_tasks"',
                "version = 1",
                "",
                "[[task]]",
                f'id = "{TASK_ID}"',
                'title = "Fixture parent state task"',
                f'introduced_after = "{boundary}"',
                'severity = "S1"',
                'applies_to = ["parent_repo"]',
                'summary = "Fixture task."',
                'actions = ["Apply fixture task."]',
                'acceptance = ["Fixture state is recorded."]',
                'paths = [".agent-canon/update-state.toml"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def create_canon_repo(root: Path) -> tuple[Path, str, str]:
    """Create a tiny vendored AgentCanon git repo with one update task."""
    canon_root = root / "vendor" / "agent-canon"
    canon_root.mkdir(parents=True, exist_ok=True)
    run_git(canon_root, "init")
    (canon_root / "README.md").write_text("fixture canon\n", encoding="utf-8")
    boundary = commit_all(canon_root, "seed canon")
    write_manifest(canon_root, boundary)
    target = commit_all(canon_root, "add update task")
    return canon_root, boundary, target


class AgentCanonUpdateTodosTest(unittest.TestCase):
    """Verify update TODOs route parent-repo agents before normal work."""

    def run_tool(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the update TODO tool in a fixture root."""
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_init_creates_parent_state_and_ignored_generated_surface(self) -> None:
        """Initialization records a parent-local boundary and scoped ignore file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, _, target = create_canon_repo(root)

            result = self.run_tool(root, "--target-commit", target, "init")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_INIT=created", result.stdout)
            state_path = root / ".agent-canon" / "update-state.toml"
            state_text = state_path.read_text(encoding="utf-8")
            self.assertIn("# contract data", state_text)
            self.assertIn(target, state_text)
            self.assertIn(
                "../vendor/agent-canon/documents/agent-canon-update-tasks.toml",
                state_text,
            )
            self.assertEqual(
                "*\n!.gitignore\n!update-state.toml\n",
                (root / ".agent-canon" / ".gitignore").read_text(encoding="utf-8"),
            )

    def test_plan_complete_and_acknowledge_update_task(self) -> None:
        """Pending update TODOs become ready_to_ack only after local resolution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, boundary, target = create_canon_repo(root)
            self.assertEqual(
                self.run_tool(root, "--target-commit", boundary, "init").returncode,
                0,
            )

            plan = self.run_tool(root, "--target-commit", target, "plan", "--write")

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_STATUS=pending", plan.stdout)
            self.assertIn(f"AGENT_CANON_UPDATE_TODO_TASKS={TASK_ID}", plan.stdout)
            self.assertIn(f"AGENT_CANON_UPDATE_TODO_FIRST_TASK={TASK_ID}", plan.stdout)
            self.assertIn(
                "AGENT_CANON_UPDATE_TODO_FIRST_ACTION=Apply fixture task.",
                plan.stdout,
            )
            self.assertIn(
                "AGENT_CANON_UPDATE_TODO_PENDING_JSON=.agent-canon/update-todos.pending.json",
                plan.stdout,
            )
            generated = root / ".agent-canon" / "update-todos.generated.md"
            self.assertIn(TASK_ID, generated.read_text(encoding="utf-8"))
            pending_json = json.loads(
                (root / ".agent-canon" / "update-todos.pending.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(pending_json["pending_tasks"], [TASK_ID])
            self.assertEqual(
                pending_json["pending_task_details"][0]["actions"],
                ["Apply fixture task."],
            )
            self.assertIn("not_applicable_command", pending_json["operator_protocol"])

            complete = self.run_tool(
                root,
                "--target-commit",
                target,
                "complete",
                TASK_ID,
                "--note",
                "fixture applied",
            )
            self.assertEqual(complete.returncode, 0, complete.stderr)

            ready = self.run_tool(root, "--target-commit", target, "status")
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_STATUS=ready_to_ack", ready.stdout)

            ack = self.run_tool(root, "--target-commit", target, "acknowledge")
            self.assertEqual(ack.returncode, 0, ack.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_ACKNOWLEDGED=yes", ack.stdout)

            final = self.run_tool(root, "--target-commit", target, "status")
            self.assertEqual(final.returncode, 0, final.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_STATUS=pass", final.stdout)

    def test_not_applicable_resolves_update_task_before_acknowledge(self) -> None:
        """Parent repos can resolve TODOs that do not apply without using defer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, boundary, target = create_canon_repo(root)
            self.assertEqual(
                self.run_tool(root, "--target-commit", boundary, "init").returncode,
                0,
            )

            not_applicable = self.run_tool(
                root,
                "--target-commit",
                target,
                "not-applicable",
                TASK_ID,
                "--reason",
                "fixture not applicable",
                "--owner",
                "repo-owner",
            )
            self.assertEqual(not_applicable.returncode, 0, not_applicable.stderr)
            self.assertIn(
                "AGENT_CANON_UPDATE_TODO_MARKED_STATUS=not_applicable",
                not_applicable.stdout,
            )

            ready = self.run_tool(root, "--target-commit", target, "status")
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_STATUS=ready_to_ack", ready.stdout)

            state_text = (root / ".agent-canon" / "update-state.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn('status = "not_applicable"', state_text)

    def test_missing_state_routes_to_initialization_without_failure(self) -> None:
        """Missing parent state is a route, not a hard status failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, _, target = create_canon_repo(root)

            result = self.run_tool(root, "--target-commit", target, "status")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_UPDATE_TODO_STATUS=state_missing", result.stdout)
            self.assertIn(
                "AGENT_CANON_UPDATE_TODO_NEXT=initialize_agent_canon_update_state",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
