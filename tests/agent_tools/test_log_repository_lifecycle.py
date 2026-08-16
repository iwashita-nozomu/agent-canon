"""Synthetic tests for stable runtime log repository lifecycle behavior."""

# @dependency-start
# contract test
# responsibility Verifies stable identity, root resolution, and runtime archive lifecycle behavior.
# upstream design ../../documents/runtime/runtime-log-archive.md runtime log archive contract
# upstream implementation ../../tools/agent_tools/log_repository_identity.py resolves stable source identity
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py resolves source and canon roots
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py derives runtime archive paths
# upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py publishes archive snapshots and refs
# @dependency-end

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.agent_tools.agent_canon_source_root import resolve_agent_canon_source_root
from tools.agent_tools.log_repository_identity import (
    SourceRepositoryIdentityError,
    normalize_remote,
    source_repository_id_for_write,
    stable_log_branch,
    stable_source_id_from_runtime_env,
    stable_source_repository_id,
)
from tools.agent_tools.runtime_log_paths import repo_log_key

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "agent_tools" / "runtime_log_archive_git.py"
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))
import runtime_log_archive_git as archive  # noqa: E402


def git(cwd: Path, *args: str, check: bool = True) -> str:
    """Run one Git command in a synthetic checkout and return stdout."""
    result = subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)
    return result.stdout.strip()


def materialize_exact_fixture_root(root: Path) -> None:
    """Materialize a nested Git root and canonical discovery sentinel."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    sentinel = root / ".agent-canon" / "fixture-sentinel"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(f"{root.resolve()}\n", encoding="utf-8")


class LogRepositoryLifecycleTest(unittest.TestCase):
    """Exercise stable identity, root resolution, snapshots, and publication."""

    def setUp(self) -> None:
        """Prepare stable source identity environment for each test."""
        self.env = os.environ.copy()
        self.env["GIT_CONFIG_GLOBAL"] = os.devnull
        self.env["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"] = "https://github.com/owner/source.git"
        for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID"):
            self.env.pop(name, None)

    def make_remote(self, root: Path) -> Path:
        """Create a bare archive remote with one main seed commit."""
        seed = root / "seed"
        seed.mkdir()
        git(seed, "init", "-q")
        git(seed, "config", "user.email", "test@example.invalid")
        git(seed, "config", "user.name", "Test")
        (seed / "README.md").write_text("archive\n", encoding="utf-8")
        git(seed, "add", "README.md")
        git(seed, "commit", "-qm", "seed")
        git(seed, "branch", "-M", "main")
        remote = root / "archive.git"
        subprocess.run(["git", "clone", "--bare", str(seed), str(remote)], check=True, capture_output=True)
        return remote

    def source(self, root: Path, name: str) -> Path:
        """Create a synthetic source checkout with the test remote configured."""
        source = root / name
        source.mkdir()
        git(source, "init", "-q")
        git(source, "remote", "add", "origin", self.env["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"])
        return source

    def run_tool(
        self,
        source: Path,
        canon: Path,
        remote: Path,
        *args: str,
        archive_root: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Invoke the archive tool against one synthetic source and remote."""
        global_args = [] if archive_root is None else ["--archive-root", str(archive_root)]
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [
                os.environ.get("PYTHON", "python3"),
                str(SCRIPT),
                "--source-root", str(source),
                "--canon-root", str(canon),
                "--remote", str(remote),
                *global_args,
                *args,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_same_remote_different_paths_share_stable_branch(self) -> None:
        """Different checkouts of one remote resolve to one stable branch."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "checkout-a"
            second = root / "checkout-b"
            first.mkdir()
            second.mkdir()
            for path in (first, second):
                git(path, "init", "-q")
                git(path, "remote", "add", "origin", "git@GITHUB.com:Owner/Source.git")
            self.assertEqual(stable_log_branch(first), stable_log_branch(second))
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": "",
                    "AGENT_CANON_SOURCE_REPOSITORY_ID": "",
                },
            ):
                self.assertEqual(repo_log_key(first), repo_log_key(second))

    def test_distinct_sources_do_not_collide(self) -> None:
        """Distinct normalized repository identities produce different branches."""
        self.assertNotEqual(
            stable_source_repository_id("https://github.com/owner/a.git"),
            stable_source_repository_id("https://github.com/owner/b.git"),
        )

    def test_matching_id_override_requires_remote_provenance(self) -> None:
        """A matching explicit id is accepted only with its normalized remote."""
        expected = stable_source_repository_id(self.env["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"])
        with patch.dict(
            os.environ,
            {
                "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": self.env["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"],
                "AGENT_CANON_SOURCE_REPOSITORY_ID": expected,
            },
        ):
            self.assertEqual(source_repository_id_for_write(Path("/tmp/source")), expected)

    def test_mismatched_or_unavailable_identity_is_typed_before_write(self) -> None:
        """Mismatch and missing remote fail before the archive clone can be created."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root, "source")
            canon = root / "canon"
            canon.mkdir()
            remote = self.make_remote(root)
            mismatch = self.run_tool(
                source,
                canon,
                remote,
                "ensure",
                archive_root=canon / ".agent-canon" / "log-archive",
                extra_env={"AGENT_CANON_SOURCE_REPOSITORY_ID": "a" * 24},
            )
            self.assertEqual(mismatch.returncode, 1)
            self.assertIn("source_repository_id_mismatch", mismatch.stdout)
            self.assertFalse((canon / ".agent-canon" / "log-archive").exists())
            unavailable_source = root / "unavailable-source"
            unavailable_source.mkdir()
            git(unavailable_source, "init", "-q")
            unavailable_canon = root / "unavailable-canon"
            unavailable_canon.mkdir()
            unavailable = self.run_tool(
                unavailable_source,
                unavailable_canon,
                remote,
                "push",
                extra_env={
                    "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": "",
                    "AGENT_CANON_SOURCE_REPOSITORY_ID": "b" * 24,
                },
            )
            self.assertEqual(unavailable.returncode, 1)
            self.assertIn("source_remote_required", unavailable.stdout)
            self.assertFalse((unavailable_canon / ".agent-canon" / "log-archive").exists())

        with patch.dict(
            os.environ,
            {
                "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": self.env["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"],
                "AGENT_CANON_SOURCE_REPOSITORY_ID": "not-the-derived-id",
            },
        ):
            with self.assertRaises(SourceRepositoryIdentityError) as raised:
                source_repository_id_for_write(Path("/tmp/source"))
            self.assertEqual(str(raised.exception), "source_repository_id_mismatch")
        with patch.dict(
            os.environ,
            {
                "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": "",
                "AGENT_CANON_SOURCE_REPOSITORY_ID": "a" * 24,
            },
        ):
            with self.assertRaises(SourceRepositoryIdentityError) as raised:
                source_repository_id_for_write(Path("/tmp/source"))
            self.assertEqual(str(raised.exception), "source_remote_required")
        with patch.dict(
            os.environ,
            {
                "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": "",
                "AGENT_CANON_SOURCE_REPOSITORY_ID": "a" * 24,
            },
        ):
            self.assertEqual(stable_source_id_from_runtime_env(), "unidentified-source")

    def test_remote_matrix_strips_case_insensitive_git_suffix(self) -> None:
        """SSH and HTTPS forms strip a case-insensitive .git suffix equally."""
        forms = (
            "git@GITHUB.com:OWNER/SOURCE.GIT",
            "ssh://git@github.com/owner/source.git",
            "https://github.com/OWNER/SOURCE.GiT",
        )
        self.assertEqual({normalize_remote(form) for form in forms}, {"github.com/owner/source"})

    def test_branch_mismatch_is_typed_and_write_does_not_mutate_archive(self) -> None:
        """A mismatched archive fails status and writes before mutation."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = self.make_remote(root)
            source = self.source(root, "source")
            canon = root / "canon"
            canon.mkdir()
            archive_clone = canon / ".agent-canon" / "log-archive"
            archive_clone.parent.mkdir(parents=True)
            subprocess.run(["git", "clone", str(remote), str(archive_clone)], check=True, capture_output=True)
            before = git(archive_clone, "rev-parse", "HEAD")
            status = self.run_tool(source, canon, remote, "status", archive_root=archive_clone)
            self.assertEqual(status.returncode, 1)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ERROR_CODE=archive_branch_mismatch", status.stdout)
            report = source / "reports" / "agents" / "run-1"
            report.mkdir(parents=True)
            (report / "result.md").write_text("one\n", encoding="utf-8")
            write = self.run_tool(source, canon, remote, "archive-agent-report", "--report-dir", str(report), archive_root=archive_clone)
            self.assertEqual(write.returncode, 1)
            self.assertIn("archive_branch_mismatch", write.stdout)
            self.assertEqual(git(archive_clone, "rev-parse", "HEAD"), before)
            self.assertFalse((archive_clone / "agent-reports").exists())

    def test_snapshots_are_content_addressed_idempotent_and_collision_safe(self) -> None:
        """Identical reports deduplicate while changed content gets a new snapshot."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = self.make_remote(root)
            source = self.source(root, "source")
            canon = root / "canon"
            canon.mkdir()
            self.assertEqual(self.run_tool(source, canon, remote, "ensure").returncode, 0)
            report = source / "reports" / "agents" / "run-1"
            report.mkdir(parents=True)
            path = report / "result.md"
            path.write_text("one\n", encoding="utf-8")
            first = self.run_tool(source, canon, remote, "archive-agent-report", "--report-dir", str(report))
            second = self.run_tool(source, canon, remote, "archive-agent-report", "--report-dir", str(report))
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            branch = stable_source_repository_id(self.env["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"])
            snapshots = list((canon / ".agent-canon" / "log-archive" / "agent-reports" / branch / "run-1").iterdir())
            self.assertEqual(len(snapshots), 1)
            index = snapshots[0].parent.parent / "index.jsonl"
            self.assertEqual(len(index.read_text(encoding="utf-8").splitlines()), 1)
            path.write_text("two\n", encoding="utf-8")
            collision = self.run_tool(source, canon, remote, "archive-agent-report", "--report-dir", str(report))
            self.assertEqual(collision.returncode, 0, collision.stdout + collision.stderr)
            self.assertEqual(len(list(snapshots[0].parent.iterdir())), 2)

    def test_two_writers_retry_without_force_and_read_back_remote_ref(self) -> None:
        """Concurrent writers retry append-only publication and verify readback."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = self.make_remote(root)
            first_source = self.source(root, "source-a")
            second_source = self.source(root, "source-b")
            first_canon = root / "canon-a"
            second_canon = root / "canon-b"
            first_canon.mkdir()
            second_canon.mkdir()
            self.assertEqual(self.run_tool(first_source, first_canon, remote, "ensure").returncode, 0)
            self.assertEqual(self.run_tool(second_source, second_canon, remote, "ensure").returncode, 0)
            for source, run_id, content in (
                (first_source, "run-a", "a\n"),
                (second_source, "run-b", "b\n"),
            ):
                report = source / "reports" / "agents" / run_id
                report.mkdir(parents=True)
                (report / "result.md").write_text(content, encoding="utf-8")
                staged = self.run_tool(source, first_canon if source == first_source else second_canon, remote, "archive-agent-report", "--report-dir", str(report))
                self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)
            pushed = self.run_tool(first_source, first_canon, remote, "push")
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            retried = self.run_tool(second_source, second_canon, remote, "push")
            self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
            remote_head = subprocess.run(
                ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{stable_log_branch(first_source)}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(remote_head, git(second_canon / ".agent-canon" / "log-archive", "rev-parse", "HEAD"))

    def test_root_resolution_standalone_vendored_and_override(self) -> None:
        """Standalone, vendored, and mismatched explicit roots remain independently visible."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            standalone = root / "standalone"
            (standalone / "agents" / "skills").mkdir(parents=True)
            (standalone / "agents" / "skills" / "catalog.yaml").write_text("version: 1\n", encoding="utf-8")
            materialize_exact_fixture_root(standalone)
            clean_identity = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("AGENT_CANON_")
            }
            with patch.dict(os.environ, clean_identity, clear=True):
                standalone_resolution = resolve_agent_canon_source_root(standalone)
            self.assertEqual(standalone_resolution.layout, "standalone")
            self.assertEqual(standalone_resolution.source_root, standalone.resolve())
            self.assertEqual(standalone_resolution.canon_root, standalone.resolve())
            parent = root / "parent"
            (parent / "vendor" / "agent-canon" / "agents" / "skills").mkdir(parents=True)
            (parent / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").write_text("version: 1\n", encoding="utf-8")
            materialize_exact_fixture_root(parent)
            with patch.dict(os.environ, clean_identity, clear=True):
                vendored_resolution = resolve_agent_canon_source_root(parent)
            vendor = parent / "vendor" / "agent-canon"
            self.assertEqual(vendored_resolution.layout, "vendored")
            self.assertEqual(vendored_resolution.source_root, vendor.resolve())
            self.assertEqual(vendored_resolution.canon_root, vendor.resolve())
            source_override = root / "source-override"
            (source_override / "agents" / "skills").mkdir(parents=True)
            (source_override / "agents" / "skills" / "catalog.yaml").write_text("version: 1\n", encoding="utf-8")
            canon_override = root / "canon-override"
            (canon_override / "agents" / "skills").mkdir(parents=True)
            (canon_override / "agents" / "skills" / "catalog.yaml").write_text("version: 1\n", encoding="utf-8")
            resolution = resolve_agent_canon_source_root(root, source_root=source_override, canon_root=canon_override)
            self.assertEqual(resolution.layout, "override")
            self.assertEqual(resolution.source_root, source_override.resolve())
            self.assertEqual(resolution.canon_root, canon_override.resolve())
            self.assertNotEqual(resolution.source_root, resolution.canon_root)
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_SOURCE_ROOT": str(source_override),
                    "AGENT_CANON_ROOT": str(canon_override),
                },
            ):
                env_resolution = resolve_agent_canon_source_root(root)
            self.assertEqual(env_resolution.source_root, source_override.resolve())
            self.assertEqual(env_resolution.canon_root, canon_override.resolve())

    def test_sync_has_no_deletion_or_force_route(self) -> None:
        """The normal sync route contains no branch deletion or force push."""
        source = inspect.getsource(archive.command_sync)
        push = inspect.getsource(archive._compare_and_push)
        self.assertNotIn("push --delete", source)
        self.assertNotIn("git clean", source)
        self.assertNotIn("--force", push)


if __name__ == "__main__":
    unittest.main()
