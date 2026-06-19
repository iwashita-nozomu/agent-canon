# @dependency-start
# contract test
# responsibility Tests test update agent canon behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the derived-repo agent-canon update wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


def resolve_repo_root() -> Path:
    """Return the repository root for both vendored and mirrored test paths."""
    git_root = None
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            git_root = candidate
            if (candidate / "vendor" / "agent-canon").exists():
                return candidate
    if git_root is not None:
        raise unittest.SkipTest("derived-repo agent-canon wrapper tests require vendor/agent-canon")
    raise RuntimeError("git repository root not found")


REPO_ROOT = resolve_repo_root()
AGENT_CANON_IS_SUBMODULE = bool(
    subprocess.run(
        [
            "git",
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.vendor/agent-canon.path",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
OVERLAY_EXCLUDED_NAMES = {".git", ".pytest_cache", ".ruff_cache", "reports"}
SUBMODULE_GITFILE = Path("vendor") / "agent-canon" / ".git"


@unittest.skipIf(
    AGENT_CANON_IS_SUBMODULE,
    "subtree snapshot wrapper tests do not apply when vendor/agent-canon is a submodule",
)
class UpdateAgentCanonTest(unittest.TestCase):
    """Exercise the wrapper through a cloned repository."""

    def overlay_working_tree(self, target: Path) -> None:
        """Mirror the current working tree into one clone without external tools."""
        for child in target.iterdir():
            if child.name in OVERLAY_EXCLUDED_NAMES:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in REPO_ROOT.iterdir():
            if child.name in OVERLAY_EXCLUDED_NAMES:
                continue
            destination = target / child.name
            subprocess.run(
                ["cp", "-a", str(child), str(destination)],
                check=True,
                capture_output=True,
                text=True,
            )
        submodule_gitfile = target / SUBMODULE_GITFILE
        if submodule_gitfile.is_file():
            submodule_gitfile.unlink()

    def clone_repo(self, target: Path) -> None:
        """Clone the current repository into one temporary target."""
        subprocess.run(
            ["git", "clone", "--no-local", str(REPO_ROOT), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.overlay_working_tree(target)
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if status:
            subprocess.run(
                ["git", "config", "user.name", "Update Agent Canon Test"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "update-agent-canon@example.invalid"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "test: overlay current working tree"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )

    def split_agent_canon_snapshot(self, repo: Path) -> str:
        """Return a split commit for fresh clones that may not have subtree join objects."""
        plain = subprocess.run(
            ["git", "subtree", "split", "--prefix=vendor/agent-canon", "HEAD"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        if plain.returncode == 0 and plain.stdout.strip():
            return plain.stdout.strip()

        ignore_joins = subprocess.run(
            ["git", "subtree", "split", "--ignore-joins", "--prefix=vendor/agent-canon", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return ignore_joins.stdout.strip()

    def replace_tree(self, source: Path, target: Path) -> None:
        """Replace target contents without depending on rsync in minimal containers."""
        for child in target.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in source.iterdir():
            if child.name == ".git":
                continue
            destination = target / child.name
            if child.is_symlink():
                os.symlink(os.readlink(child), destination)
            elif child.is_dir():
                shutil.copytree(child, destination, symlinks=True)
            else:
                shutil.copy2(child, destination, follow_symlinks=False)

    def test_link_root_converts_shared_goal_symlink_to_repo_local_file(self) -> None:
        """goal.md is repo-local state and must not be a shared canon symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            self.clone_repo(clone_dir)
            goal_path = clone_dir / "goal.md"
            if goal_path.exists() or goal_path.is_symlink():
                goal_path.unlink()
            os.symlink("vendor/agent-canon/goal.md", goal_path)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(goal_path.is_symlink())
            self.assertIn("repo-local goal", goal_path.read_text(encoding="utf-8"))
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_plan_reports_snapshot_import_without_subtree_binary(self) -> None:
        """Plan should report the no-subtree route when git-subtree is unavailable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            missing_exec = root / "missing-git-exec"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = work_dir / ".plan-no-subtree-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: advance agent canon",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            missing_exec.mkdir(parents=True, exist_ok=True)
            git_binary = shutil.which("git")
            self.assertIsNotNone(git_binary)
            git_wrapper = missing_exec / "git"
            git_wrapper.write_text(
                "#!/usr/bin/env bash\n"
                "for arg in \"$@\"; do\n"
                "  if [[ \"$arg\" == \"subtree\" ]]; then\n"
                "    echo 'git: subtree unavailable in test' >&2\n"
                "    exit 1\n"
                "  fi\n"
                "done\n"
                f"exec {git_binary} \"$@\"\n",
                encoding="utf-8",
            )
            git_wrapper.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{missing_exec}{os.pathsep}{env['PATH']}"

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertRegex(
                plan.stdout,
                r"agent_canon_plan_route=(snapshot_import_tree_match|snapshot_import_no_subtree)",
            )

    def test_plan_prefers_subtree_pull_when_local_split_is_remote_ancestor(self) -> None:
        """Plan should prefer subtree_pull over tree-match snapshot route when subtree metadata exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = work_dir / ".subtree-pull-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: advance agent canon with subtree metadata available",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=subtree_pull", plan.stdout)

    def test_apply_succeeds_when_local_history_diverged_but_tree_matches_remote_history(
        self,
    ) -> None:
        """Apply should recover when local split diverged but the current tree exists upstream."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "remove", "agent-canon"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            remote_marker_a = work_dir / ".remote-tree-match-marker"
            remote_marker_a.write_text("remote-a\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker_a.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: remote tree match base",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            local_diverged_marker = clone_dir / "vendor" / "agent-canon" / ".diverged-local-marker"
            local_diverged_marker.write_text("diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(local_diverged_marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge local shared canon",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            self.replace_tree(work_dir, clone_dir / "vendor" / "agent-canon")
            subprocess.run(
                ["git", "add", "-A"], cwd=clone_dir, check=True, capture_output=True, text=True
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: realign local tree to remote history",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            remote_marker_b = work_dir / ".remote-after-tree-match-marker"
            remote_marker_b.write_text("remote-b\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker_b.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: remote advance after tree match",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=snapshot_import_tree_match", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn(
                "agent_canon_snapshot_import=tree_match_in_remote_history", combined_output
            )
            self.assertIn(
                "agent_canon_update_method=snapshot_import_after_subtree_pull_failure",
                combined_output,
            )

    def test_apply_fails_closed_when_local_shared_canon_history_diverges(self) -> None:
        """Apply should stop before mutating the worktree when local vendor history diverges."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            remote_marker = work_dir / ".remote-diverged-marker"
            remote_marker.write_text("remote-diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge remote shared canon",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            diverged_marker = clone_dir / "vendor" / "agent-canon" / ".diverged-local-marker"
            diverged_marker.write_text("diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(diverged_marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge local shared canon",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=diverged_local_history", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(apply.returncode, 0)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn("agent_canon_snapshot_import=diverged_history", combined_output)
            self.assertIn("diverged", combined_output)

            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(status, "")

@unittest.skipUnless(
    AGENT_CANON_IS_SUBMODULE,
    "submodule wrapper tests only apply when vendor/agent-canon is a submodule",
)
class SubmoduleUpdateAgentCanonTest(unittest.TestCase):
    """Exercise submodule-specific update routes."""

    def make_agent_canon_remote(self, root: Path) -> tuple[Path, Path]:
        """Create one bare AgentCanon remote and working clone."""
        root.mkdir(parents=True, exist_ok=True)
        bare_repo = root / "agent-canon.git"
        work_dir = root / "agent-canon-work"
        subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True)
        subprocess.run(["git", "clone", str(bare_repo), str(work_dir)], check=True)
        subprocess.run(["git", "switch", "-c", "main"], cwd=work_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=work_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "submodule-test@example.invalid"],
            cwd=work_dir,
            check=True,
        )
        (work_dir / "README.md").write_text("# AgentCanon\n", encoding="utf-8")
        (work_dir / "ROOT_AGENTS.md").write_text("# Root agents\n", encoding="utf-8")
        (work_dir / "tools" / "agent_tools").mkdir(parents=True)
        shutil.copy2(
            REPO_ROOT / "tools" / "agent_tools" / "surface_manifest.py",
            work_dir / "tools" / "agent_tools" / "surface_manifest.py",
        )
        (work_dir / "documents").mkdir()
        (work_dir / "documents" / "shared-runtime-surfaces.toml").write_text(
            "\n".join(
                [
                    'version = 1',
                    'prefix = "vendor/agent-canon"',
                    '',
                    '[[surface]]',
                    'path = "AGENTS.md"',
                    'mode = "symlink"',
                    'source = "ROOT_AGENTS.md"',
                    'owner = "agent-canon"',
                    'class = "runtime_surface"',
                    '',
                    '[[group]]',
                    'mode = "symlink"',
                    'owner = "agent-canon"',
                    'class = "runtime_surface"',
                    'paths = [',
                    '  ".vscode",',
                    '  ".github/AGENTS.md",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "copy"',
                    'owner = "github-path-constraint"',
                    'class = "github_copy"',
                    'local_override_allowed = false',
                    'paths = [',
                    '  ".github/workflows/agent-coordination.yml",',
                    '  ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "regular"',
                    'owner = "template-or-derived-repo"',
                    'class = "active_contract"',
                    'local_override_allowed = true',
                    'source_prefix = ""',
                    'paths = [',
                    '  "documents/README.md",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "standalone_only"',
                    'owner = "agent-canon-standalone"',
                    'class = "standalone_only"',
                    'local_override_allowed = false',
                    'paths = [',
                    '  "documents/SHARED_RUNTIME_SURFACES.md",',
                    ']',
                    '',
                    '[[surface]]',
                    'path = "goal.md"',
                    'mode = "repo_state"',
                    'owner = "project"',
                    'class = "durable_state"',
                    'local_override_allowed = true',
                    '',
                ]
            ),
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows").mkdir(parents=True)
        (work_dir / ".github" / "PULL_REQUEST_TEMPLATE").mkdir(parents=True)
        (work_dir / ".vscode").mkdir()
        (work_dir / ".vscode" / "settings.json").write_text(
            '{"agentCanonTest": true}\n',
            encoding="utf-8",
        )
        (work_dir / "documents" / "README.md").write_text(
            "# Derived Documents Seed\n",
            encoding="utf-8",
        )
        (work_dir / "documents" / "SHARED_RUNTIME_SURFACES.md").write_text(
            "\n".join(
                [
                    "# Standalone Surface Policy",
                    "",
                    "documents/shared-runtime-surfaces.toml",
                    ".codex/hooks.json",
                    ".codex/hooks",
                    ".devcontainer/",
                    "documents/README.md",
                    "documents/template-bootstrap.md",
                    "documents/github-first-module-and-devcontainer-policy.md",
                    "memory/USER_PREFERENCES.md",
                    "tests/agent_tools/",
                    "Root `tools/` is a symlink view",
                    "vendor/agent-canon/tools/",
                    "Project-local automation must stay in project-owned paths",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (work_dir / ".github" / "AGENTS.md").write_text(
            "# GitHub agents\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows" / "agent-coordination.yml").write_text(
            "name: agent coordination\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md").write_text(
            "# AgentCanon PR\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "git",
                "add",
                "README.md",
                "ROOT_AGENTS.md",
                ".github",
                ".vscode",
                "documents",
                "tools",
            ],
            cwd=work_dir,
            check=True,
        )
        subprocess.run(["git", "commit", "-m", "initial agent canon"], cwd=work_dir, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
        subprocess.run(
            ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
        )
        return bare_repo, work_dir

    def make_superproject(self, root: Path, bare_repo: Path) -> Path:
        """Create one derived repo with AgentCanon as a submodule."""
        repo = root / "derived"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "submodule-test@example.invalid"],
            cwd=repo,
            check=True,
        )
        (repo / "tools").mkdir()
        shutil.copy2(REPO_ROOT / "tools" / "sync_agent_canon.sh", repo / "tools")
        shutil.copy2(REPO_ROOT / "tools" / "update_agent_canon.sh", repo / "tools")
        shutil.copy2(REPO_ROOT / "tools" / "rebuild_agent_tools.sh", repo / "tools")
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "-b",
                "main",
                str(bare_repo),
                "vendor/agent-canon",
            ],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "add", ".gitmodules", "tools", "vendor/agent-canon"],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "commit", "-m", "add submodule"], cwd=repo, check=True)
        return repo

    def test_ensure_latest_reports_already_current_submodule(self) -> None:
        """Ensure-latest should no-op when the parent pin already matches remote main."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest_submodule_local_state_checked=yes", result.stdout)
            self.assertIn("agent_canon_latest=already_current_submodule", result.stdout)

    def test_latest_aligns_clean_submodule_with_tree_equivalent_remote_main_after_squash(self) -> None:
        """Ensure-latest should align a clean PR-branch checkout when trees are identical."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"

            subprocess.run(
                ["git", "switch", "-c", "canon-pr/tree-equivalent"],
                cwd=submodule,
                check=True,
            )
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "squash-match local branch marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "canon-pr/tree-equivalent"],
                cwd=submodule,
                check=True,
            )

            subprocess.run(
                ["git", "config", "user.name", "Submodule Test"],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "submodule-test@example.invalid"],
                cwd=work_dir,
                check=True,
            )
            (work_dir / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "squash-match remote main marker",
                ],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            pinned_sha = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=local_tree_matches_remote", plan.stdout)
            self.assertEqual(latest.returncode, 0, latest.stderr)
            self.assertIn("agent_canon_latest=local_tree_matches_remote", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=updated", latest.stdout)
            self.assertNotIn("AGENT_CANON_LATEST_TOOL_RESULT=agent_workflow_required", latest.stdout)
            self.assertEqual(pinned_sha, remote_sha)

    def test_pull_redirects_to_ensure_latest_for_submodules(self) -> None:
        """The legacy pull command should use submodule ensure-latest semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "pull"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())

    def test_status_reports_submodule_mode_and_pin(self) -> None:
        """Status output should expose submodule mode, URL, and pin evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "status"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("prefix_mode_name=submodule", result.stdout)
            self.assertIn(f"submodule_url={bare_repo}", result.stdout)
            self.assertRegex(result.stdout, r"submodule_pin=[0-9a-f]{40}")

    def test_snapshot_alias_reports_deprecation(self) -> None:
        """The legacy snapshot alias should advertise link-root as the replacement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "snapshot"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_snapshot_alias=deprecated_use_link_root", result.stdout)

    def test_link_root_keeps_goal_local_and_syncs_copy_surfaces(self) -> None:
        """Link-root should restore root views without copying standalone-only PR templates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            goal_path = repo / "goal.md"
            os.symlink("vendor/agent-canon/goal.md", goal_path)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(goal_path.is_symlink())
            self.assertIn("repo-local goal", goal_path.read_text(encoding="utf-8"))
            self.assertEqual(
                (repo / ".github" / "workflows" / "agent-coordination.yml").read_text(
                    encoding="utf-8"
                ),
                (
                    repo
                    / "vendor"
                    / "agent-canon"
                    / ".github"
                    / "workflows"
                    / "agent-coordination.yml"
                ).read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (repo / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md").read_text(
                    encoding="utf-8"
                ),
                (
                    repo
                    / "vendor"
                    / "agent-canon"
                    / ".github"
                    / "PULL_REQUEST_TEMPLATE"
                    / "agent_canon.md"
                ).read_text(encoding="utf-8"),
            )
            self.assertFalse((repo / ".github" / "PULL_REQUEST_TEMPLATE.md").exists())

    def test_link_root_replaces_legacy_vscode_directory_with_shared_symlink(self) -> None:
        """Link-root should migrate VS Code workspace defaults to AgentCanon ownership."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            vscode_dir = repo / ".vscode"
            vscode_dir.mkdir()
            (vscode_dir / "settings.json").write_text(
                '{"legacyRepoLocalSetting": true}\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", ".vscode/settings.json"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add legacy vscode settings"],
                cwd=repo,
                check=True,
            )

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(vscode_dir.is_symlink())
            self.assertEqual(os.readlink(vscode_dir), "vendor/agent-canon/.vscode")
            self.assertEqual(check.returncode, 0, check.stderr)
            subprocess.run(["git", "add", "-A", ".vscode"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "sync vscode shared surface"],
                cwd=repo,
                check=True,
            )
            status = subprocess.run(
                ["git", "status", "--short", "--", ".vscode"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout.strip(), "")

    def test_link_root_materializes_missing_and_legacy_regular_active_contracts(self) -> None:
        """Link-root should seed active-contract docs without keeping legacy symlinks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            readme_path = documents_dir / "README.md"

            result_missing = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result_missing.returncode, 0, result_missing.stderr)
            self.assertFalse(readme_path.is_symlink())
            self.assertIn(
                "Derived Documents Seed",
                readme_path.read_text(encoding="utf-8"),
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            readme_path = documents_dir / "README.md"
            os.symlink("../vendor/agent-canon/documents/README.md", readme_path)
            result_symlink = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result_symlink.returncode, 0, result_symlink.stderr)
            self.assertFalse(readme_path.is_symlink())
            self.assertIn(
                "Derived Documents Seed",
                readme_path.read_text(encoding="utf-8"),
            )

    def test_link_root_removes_standalone_only_root_views(self) -> None:
        """Link-root and check should keep standalone-only docs out of parent roots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            policy_path = documents_dir / "SHARED_RUNTIME_SURFACES.md"
            os.symlink(
                "../vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md",
                policy_path,
            )

            check_before = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(check_before.returncode, 0)
            self.assertIn(
                "absent[documents/SHARED_RUNTIME_SURFACES.md]=present",
                check_before.stderr,
            )

            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            self.assertFalse(policy_path.exists())
            self.assertFalse(policy_path.is_symlink())

    def test_check_rejects_broken_tracked_root_view_symlink(self) -> None:
        """Check should catch retired tracked symlink views into AgentCanon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            retired = repo / "tests" / "tools" / "test_retired_mirror.py"
            retired.parent.mkdir(parents=True)
            os.symlink(
                "../../vendor/agent-canon/tests/tools/test_retired_mirror.py",
                retired,
            )
            subprocess.run(["git", "add", "tests/tools/test_retired_mirror.py"], cwd=repo, check=True)

            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(check.returncode, 0)
            self.assertIn(
                "root-symlink[tests/tools/test_retired_mirror.py]=broken",
                check.stderr,
            )

    def test_plan_reports_submodule_update_without_root_commit_lookup_errors(self) -> None:
        """Plan should compare submodule commits inside the submodule repo."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertNotIn("Not a valid commit name", plan.stderr)
            self.assertIn("agent_canon_plan_prefix_mode=submodule", plan.stdout)
            self.assertIn("agent_canon_plan_route=submodule_update", plan.stdout)

    def test_latest_updates_clean_submodule_and_reports_tool_completion(self) -> None:
        """The high-level latest command should apply safe submodule updates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("agent_canon_plan_route=submodule_update", latest.stdout)
            self.assertIn("agent_canon_latest=updating_submodule", latest.stdout)
            self.assertIn("shared surface is in sync", latest.stdout)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_rust_manifest", latest.stdout)
            self.assertIn("AGENT_CANON_TOOL_REBUILD=pass", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TODOS=skipped_missing_tool", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=updated", latest.stdout)
            self.assertIn("NEXT_ACTION=run_validation_then_push_parent_repo", latest.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())

    def test_rebuild_tools_installs_rust_cli_from_current_submodule(self) -> None:
        """Rebuild-tools should install a Rust CLI matching the current AgentCanon source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            rust_root = submodule / "rust" / "agent-canon"
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            rust_root.mkdir(parents=True)
            (rust_root / "Cargo.toml").write_text("[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\nedition = \"2021\"\n", encoding="utf-8")
            fake_bin.mkdir()
            cargo = fake_bin / "cargo"
            cargo.write_text(
                "#!/usr/bin/env bash\n"
                "manifest=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = '--manifest-path' ]; then manifest=\"$2\"; shift 2; else shift; fi\n"
                "done\n"
                "crate_dir=\"$(dirname \"$manifest\")\"\n"
                "mkdir -p \"$crate_dir/target/release\"\n"
                "cat >\"$crate_dir/target/release/agent-canon\" <<'SH'\n"
                "#!/usr/bin/env bash\n"
                "echo 'agent-canon test 0.1.0'\n"
                "SH\n"
                "chmod +x \"$crate_dir/target/release/agent-canon\"\n",
                encoding="utf-8",
            )
            cargo.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["AGENT_CANON_TOOLS_HOME"] = str(tools_home)
            env["AGENT_CANON_SKIP_USR_LOCAL_LINK"] = "1"

            first = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            time.sleep(1.1)
            (rust_root / "Cargo.toml").write_text(
                "[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\nedition = \"2021\"\n# dirty source\n",
                encoding="utf-8",
            )
            third = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=rebuilt", first.stdout)
            self.assertIn("AGENT_CANON_TOOL_REBUILD=pass", first.stdout)
            self.assertTrue((tools_home / "bin" / "agent-canon").is_symlink())
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=already_current", second.stdout)
            self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=rebuilt", third.stdout)

    def test_latest_preserves_dirty_submodule_and_merges_remote_main(self) -> None:
        """Latest should preserve dirty shared canon work while merging remote main."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "dirty-marker.txt").write_text("dirty\n", encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            stash_list = subprocess.run(
                ["git", "stash", "list"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("agent_canon_plan_route=submodule_update", latest.stdout)
            self.assertIn("agent_canon_plan_submodule_worktree_status=dirty", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_DIRTY_PRESERVE=started", latest.stdout)
            self.assertIn("agent_canon_merge_dirty_preserve_result=started", latest.stdout)
            self.assertIn("agent_canon_merge_dirty_restore=applied", latest.stdout)
            self.assertIn("agent_canon_merge_dirty_stash_dropped=yes", latest.stdout)
            self.assertIn("agent_canon_merge_remote_main_in_post_head=yes", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_DIRTY_PRESERVE=pass", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROOT_VIEW_REPAIR=pass", latest.stdout)
            self.assertIn("shared surface is in sync", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_SHARED_SURFACE_CHECK=pass", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=agent_workflow_preserved_dirty", latest.stdout)
            self.assertIn("NEXT_ACTION=continue_agentcanon_branch_PR_flow_with_restored_dirty_state", latest.stdout)
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertTrue((submodule / "dirty-marker.txt").is_file())
            self.assertIn("?? dirty-marker.txt", status)
            self.assertNotIn("preserve dirty AgentCanon work", stash_list)
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", remote_sha, "HEAD"],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )

    def test_latest_parks_eval_logs_before_submodule_update(self) -> None:
        """Latest should park accumulated eval logs before applying a safe main update."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            log_path = (
                submodule
                / "agents"
                / "evals"
                / "results"
                / "hook-runs"
                / "derived-devcontainer"
                / "skill_usage.jsonl"
            )
            log_path.parent.mkdir(parents=True)
            log_path.write_text('{"hook_run_id":"local-log","status":"pass"}\n', encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            parked_log = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(bare_repo),
                    "show",
                    "refs/heads/agent-logs/derived:agents/evals/results/hook-runs/derived-devcontainer/skill_usage.jsonl",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("AGENT_CANON_EVAL_LOG_PARK=committed", latest.stdout)
            self.assertIn("AGENT_CANON_EVAL_LOG_PARK_BRANCH=agent-logs/derived", latest.stdout)
            self.assertIn("agent_canon_latest=updating_submodule", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=updated", latest.stdout)
            self.assertIn('"hook_run_id":"local-log"', parked_log.stdout)
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertFalse(log_path.exists())

    def test_plan_ignores_removed_source_repo_override_for_submodule_remote(self) -> None:
        """Submodule plan should keep GitHub-first submodule remote semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            removed_source_repo = root / "new" / "agent-canon-work"
            repo = self.make_superproject(root, old_bare_repo)

            env = {
                **os.environ,
                "AGENT_CANON_SOURCE_REPO": str(removed_source_repo),
                "AGENT_CANON_REMOTE_URL": str(old_bare_repo),
            }
            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertNotIn("agent_canon_plan_effective_remote_url=", plan.stdout)
            self.assertIn("agent_canon_plan_remote_source=submodule", plan.stdout)
            self.assertIn(f"agent_canon_plan_remote_url={old_bare_repo}", plan.stdout)
            self.assertIn("agent_canon_plan_route=already_current_submodule", plan.stdout)

    def test_latest_check_reports_clean_submodule_worktree_at_remote_with_stale_parent_pin(
        self,
    ) -> None:
        """Latest gate should report a stale parent gitlink without mutating the index."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                REPO_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "fetch", "origin", "main"], cwd=submodule, check=True)
            subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=submodule, check=True)
            (repo / "UNRELATED_ROOT_FILE").write_text("dirty parent\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_LATEST=pass", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=submodule_update", result.stdout)
            self.assertIn(
                "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_REMOTE_MATCH=yes",
                result.stdout,
            )
            self.assertIn("AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes", result.stdout)
            self.assertIn(
                "AGENT_CANON_LATEST_AUTO_REPAIR=skipped_read_only_check",
                result.stdout,
            )
            self.assertIn(
                "AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin",
                result.stdout,
            )
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--", "vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(staged.stdout.strip(), "")

    def test_latest_check_fails_local_ahead_submodule_pin_as_pr_required(self) -> None:
        """A parent pin ahead of shared canon main is AgentCanon PR work, not latest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                REPO_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin local proposal"], cwd=repo, check=True)

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST=fail", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=local_contains_remote", result.stdout)
            self.assertIn(
                "AGENT_CANON_LATEST_MERGE_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty",
                result.stdout,
            )
            self.assertIn("AgentCanon branch and PR", result.stderr)

    def test_latest_defers_clean_pushed_agentcanon_branch_pin(self) -> None:
        """A clean pushed AgentCanon branch head is deferred to the AgentCanon PR."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                REPO_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            branch_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "checkout", "--detach", branch_head],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin pushed proposal"], cwd=repo, check=True)
            subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "add", "AGENTS.md", ".github", ".vscode", "documents/README.md", "goal.md"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "sync root views"], cwd=repo, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            ensure_latest = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest_check = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=deferred_branch_pr", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_local_state_checked=yes", plan.stdout)
            self.assertIn(
                "agent_canon_plan_submodule_deferred_branch=canon-pr/local-work",
                plan.stdout,
            )
            self.assertIn(
                "agent_canon_plan_submodule_deferred_remote_branch=origin/canon-pr/local-work",
                plan.stdout,
            )
            self.assertEqual(ensure_latest.returncode, 0, ensure_latest.stderr)
            self.assertIn(
                "agent_canon_latest_submodule_local_state_checked=yes",
                ensure_latest.stdout,
            )
            self.assertIn("agent_canon_latest=deferred_branch_pr", ensure_latest.stdout)
            self.assertIn("agent_canon_latest_branch=canon-pr/local-work", ensure_latest.stdout)
            self.assertIn(
                "agent_canon_latest_remote_branch=origin/canon-pr/local-work",
                ensure_latest.stdout,
            )
            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr", latest.stdout)
            self.assertIn(
                "NEXT_ACTION=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest",
                latest.stdout,
            )
            self.assertEqual(latest_check.returncode, 0, latest_check.stdout + latest_check.stderr)
            self.assertIn("AGENT_CANON_LATEST=pass", latest_check.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=deferred_branch_pr", latest_check.stdout)

    def test_latest_defers_clean_pushed_agentcanon_branch_when_parent_pin_is_stale(self) -> None:
        """A clean pushed AgentCanon branch checkout should not block on a stale parent gitlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                REPO_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            initial_parent_pin = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/worktree-only"],
                cwd=submodule,
                check=True,
            )
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "canon-pr/worktree-only"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "add", "AGENTS.md", ".github", ".vscode", "documents/README.md", "goal.md"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "sync root views"], cwd=repo, check=True)
            subprocess.run(
                [
                    "git",
                    "update-index",
                    "--cacheinfo",
                    f"160000,{initial_parent_pin},vendor/agent-canon",
                ],
                cwd=repo,
                check=True,
            )
            if subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", "vendor/agent-canon"],
                cwd=repo,
                check=False,
            ).returncode != 0:
                subprocess.run(
                    ["git", "commit", "-m", "keep stale agent canon parent pin"],
                    cwd=repo,
                    check=True,
                )

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            ensure_latest = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest_check = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=deferred_branch_pr", plan.stdout)
            self.assertIn(
                "agent_canon_plan_submodule_deferred_branch=canon-pr/worktree-only",
                plan.stdout,
            )
            self.assertEqual(ensure_latest.returncode, 0, ensure_latest.stderr)
            self.assertIn("agent_canon_latest=deferred_branch_pr", ensure_latest.stdout)
            self.assertIn("agent_canon_latest_branch=canon-pr/worktree-only", ensure_latest.stdout)
            self.assertIn("agent_canon_latest_parent_pin_status=stale", ensure_latest.stdout)
            self.assertNotIn("local_submodule_worktree_differs_from_parent_pin", ensure_latest.stdout)
            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr", latest.stdout)
            self.assertEqual(latest_check.returncode, 0, latest_check.stdout + latest_check.stderr)
            self.assertIn("AGENT_CANON_LATEST=pass", latest_check.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=deferred_branch_pr", latest_check.stdout)

    def test_apply_updates_submodule_pin_with_untracked_root_file(self) -> None:
        """Apply should update the gitlink without requiring unrelated root cleanup."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            (repo / "UNTRACKED_ROOT_FILE").write_text("root dirty\n", encoding="utf-8")

            apply = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "apply"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", apply.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("?? UNTRACKED_ROOT_FILE", status)

    def test_ensure_latest_does_not_commit_dirty_regular_active_contract(self) -> None:
        """Submodule updates should not sweep template-owned active contracts into sync commits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add generated root views"],
                cwd=repo,
                check=True,
            )
            (repo / "documents" / "README.md").write_text(
                "# Locally Edited Documents\n",
                encoding="utf-8",
            )
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--", "documents/README.md"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            committed_paths = subprocess.run(
                ["git", "show", "--name-only", "--format=", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertEqual(status, " M documents/README.md\n")
            self.assertNotIn("documents/README.md", committed_paths)

    def test_ensure_latest_refuses_unpinned_local_submodule_commits(self) -> None:
        """Ensure-latest should not overwrite local submodule commits silently."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "local-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "local marker",
                ],
                cwd=submodule,
                check=True,
            )
            local_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            after_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "agent_canon_latest=local_submodule_worktree_differs_from_parent_pin",
                result.stdout,
            )
            self.assertIn("worktree HEAD differs from parent gitlink", result.stderr)
            self.assertEqual(after_head, local_head)

    def test_ensure_latest_uses_gitmodules_url_when_origin_differs(self) -> None:
        """Ensure-latest should follow .gitmodules instead of stale submodule origin."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            new_bare_repo, new_work_dir = self.make_agent_canon_remote(root / "new")
            repo = self.make_superproject(root, old_bare_repo)
            subprocess.run(
                [
                    "git",
                    "config",
                    "-f",
                    ".gitmodules",
                    "submodule.vendor/agent-canon.url",
                    str(new_bare_repo),
                ],
                cwd=repo,
                check=True,
            )
            (new_work_dir / "new-remote-marker.txt").write_text("new remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "new-remote-marker.txt"], cwd=new_work_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "advance new remote"],
                cwd=new_work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=new_work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "new-remote-marker.txt").is_file())

    def test_merge_main_into_current_merges_remote_main_into_local_branch(self) -> None:
        """Merge-main should merge GitHub main into the current AgentCanon branch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "config", "user.email", "submodule-test@example.invalid"],
                cwd=submodule,
                check=True,
            )
            (submodule / "local-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-marker.txt"], cwd=submodule, check=True)
            subprocess.run(["git", "commit", "-m", "local branch work"], cwd=submodule, check=True)
            local_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            post_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(merge.returncode, 0, merge.stderr)
            self.assertIn("agent_canon_merge_result=merged", merge.stdout)
            self.assertIn("agent_canon_merge_source_sha=", merge.stdout)
            self.assertIn("agent_canon_merge_remote_main_in_post_head=yes", merge.stdout)
            self.assertIn("agent_canon_merge_remote_main_verified=yes", merge.stdout)
            self.assertIn("agent_canon_parent_pin_pending=yes", merge.stdout)
            self.assertIn("NEXT_ACTION=run_validation_then_push_current_agentcanon_branch", merge.stdout)
            self.assertTrue((submodule / "local-marker.txt").is_file())
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", local_sha, post_sha],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", remote_sha, post_sha],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )

    def test_merge_main_into_current_blocks_dirty_submodule(self) -> None:
        """Merge-main should not merge over uncommitted AgentCanon work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            (submodule / "dirty-marker.txt").write_text("dirty\n", encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            before_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            after_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_result=blocked_dirty", merge.stdout)
            self.assertIn("NEXT_ACTION=commit_agentcanon_artifacts", merge.stdout)
            self.assertEqual(after_head, before_head)

    def test_merge_main_preserve_dirty_restores_dirty_submodule_work(self) -> None:
        """Explicit preserve-dirty merge should stash, merge main, and restore dirt."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "config", "user.email", "submodule-test@example.invalid"],
                cwd=submodule,
                check=True,
            )
            (submodule / "local-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-marker.txt"], cwd=submodule, check=True)
            subprocess.run(["git", "commit", "-m", "local branch work"], cwd=submodule, check=True)
            (submodule / "dirty-marker.txt").write_text("dirty\n", encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            merge = subprocess.run(
                [
                    "bash",
                    "tools/update_agent_canon.sh",
                    "merge-main-into-current-preserve-dirty",
                ],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            stash_list = subprocess.run(
                ["git", "stash", "list"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            self.assertEqual(merge.returncode, 0, merge.stderr)
            self.assertIn("agent_canon_merge_dirty_preserve_result=started", merge.stdout)
            self.assertIn("agent_canon_merge_dirty_restore=applied", merge.stdout)
            self.assertIn("agent_canon_merge_dirty_stash_dropped=yes", merge.stdout)
            self.assertIn("agent_canon_merge_remote_main_in_post_head=yes", merge.stdout)
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertTrue((submodule / "dirty-marker.txt").is_file())
            self.assertIn("?? dirty-marker.txt", status)
            self.assertNotIn("preserve dirty AgentCanon work", stash_list)
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", remote_sha, "HEAD"],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )

    def test_merge_main_into_current_blocks_detached_submodule(self) -> None:
        """Merge-main should require a named AgentCanon branch for PR flow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "checkout", "--detach"], cwd=submodule, check=True)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_result=blocked_detached_head", merge.stdout)
            self.assertIn("NEXT_ACTION=create_agentcanon_branch", merge.stdout)

    def test_removed_proposal_command_is_not_user_facing(self) -> None:
        """The GitHub-first wrapper should reject removed proposal commands."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            push = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "push-proposal", "canon-proposal/test"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(push.returncode, 0)
            self.assertIn("unknown subcommand 'push-proposal'", push.stderr)

    def test_sync_push_refuses_default_branch_for_submodule(self) -> None:
        """Low-level sync push should not directly update AgentCanon main by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            push = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "push", "main"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(push.returncode, 0)
            self.assertIn("submodule push to 'main' is forbidden", push.stderr)

    def test_apply_updates_submodule_pin_after_main_contains_branch_work(self) -> None:
        """Apply should update the pin after GitHub main contains the branch work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "merge proposal marker"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            apply = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "apply"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            pinned_sha = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", apply.stdout)
            self.assertEqual(pinned_sha, remote_sha)


if __name__ == "__main__":
    unittest.main()
