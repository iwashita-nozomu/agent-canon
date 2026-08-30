"""Tests for runtime log archive Git helper."""

# @dependency-start
# contract test
# responsibility Tests runtime log archive Git clone, branch, status, push, and report provenance behavior.
# upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py manages the ignored log archive clone
# upstream implementation ../../tools/runtime/archive/runtime_log_paths.py defines repo keys and archive mount paths
# upstream design ../../documents/runtime/runtime-log-archive.md documents archive branch and push policy
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md source-bound runtime-event communication and checkpoint contract
# @dependency-end

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import inspect
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from unittest.mock import patch

# Resolve the implementation checkout before importing namespace-package
# modules.  When this test is run from a parent template checkout, pytest can
# otherwise cache the parent's ``tools`` package and its top-level helpers.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT_ROOT)]


def _module_belongs_to_current_checkout(module_name: str) -> bool:
    """Return whether a cached module resolves inside this AgentCanon clone."""
    module = sys.modules.get(module_name)
    if module is None:
        return True
    locations: list[str] = []
    module_file = getattr(module, "__file__", None)
    if module_file:
        locations.append(str(module_file))
    locations.extend(str(location) for location in getattr(module, "__path__", ()))
    if not locations:
        return True
    root = PROJECT_ROOT.resolve()
    for location in locations:
        try:
            Path(location).resolve().relative_to(root)
        except ValueError:
            continue
        else:
            return True
    return False


for _module_name in (
    "tools",
    "tools.analysis.dependencies.graph_client",
    "tools.repository.github.github_publish",
    "tools.runtime.archive.log_repository_identity",
    "tools.runtime.archive.runtime_log_paths",
    "tools.runtime.archive.runtime_log_archive_git",
    "tools.runtime.artifacts.report_artifact_checks",
    "tools.runtime.authority.task_authority",
):
    if not _module_belongs_to_current_checkout(_module_name):
        sys.modules.pop(_module_name, None)

from tools.analysis.dependencies.graph_client import GraphClient
from tools.repository.github import github_publish
from tools.runtime.archive.log_repository_identity import stable_source_repository_id
from tools.runtime.archive.runtime_log_paths import (
    mounted_log_archive_root,
    repo_log_key,
    runtime_event_publication_outcome_spool_root,
)

SCRIPT = PROJECT_ROOT / "tools" / "runtime" / "archive" / "runtime_log_archive_git.py"
LIFECYCLE_REVERSE_COVERAGE = {
    "bootstrap/container/image/Dockerfile": {"RL-002", "RL-004", "RL-013"},
    "agent-canon-environment.toml": {"RL-002", "RL-004"},
    "agents/skills/agent-log-analysis.md": {"RL-013"},
    "documents/design/runtime-log-repository-lifecycle-correspondence.json": {"RL-014"},
    "documents/runtime/runtime-log-archive.md": {"RL-013"},
    "documents/tools/README.md": {"RL-013"},
    "tests/agent_tools/test_runtime_log_archive_git.py": {"RL-004", "RL-005", "RL-006", "RL-007", "RL-008", "RL-011", "RL-013", "RL-014", "RL-015"},
    "tests/tools/test_bootstrap_container_contract.py": {"RL-002", "RL-004"},
    "tests/bootstrap/test_bootstrap_runtime.py": {"RL-002", "RL-004"},
    "tools/runtime/archive/runtime_log_archive_git.py": {"RL-004", "RL-005", "RL-006", "RL-007", "RL-008", "RL-011", "RL-013", "RL-015"},
    "tools/runtime/container/bootstrap_runtime.py": {"RL-002", "RL-004"},
}
from tools.runtime.archive import runtime_log_archive_git  # noqa: E402


@dataclass(frozen=True)
class RuntimeMaterializationFixture:
    """One complete source/result/Git fixture for public materialization tests."""

    source: Path
    context: runtime_log_archive_git.ArchiveContext
    args: argparse.Namespace
    thread_id: str
    context_id: str
    turn_id: str
    session_root: Path
    rollout: Path
    raw_record: bytes
    target: Path
    old_state: Path
    base_oid: str
    head_oid: str
    target_relative: str
    result_path: Path


class RuntimeLogArchiveGitTest(unittest.TestCase):
    """Validate the runtime log archive Git workflow."""

    def setUp(self) -> None:
        """Set the stable source remote used by archive command fixtures."""
        self._old_source_remote = os.environ.get("AGENT_CANON_SOURCE_REPOSITORY_REMOTE")
        self._old_parent_root = os.environ.get("AGENT_CANON_PARENT_ROOT")
        self._old_hook_archive_dir = os.environ.get("AGENT_CANON_HOOK_ARCHIVE_DIR")
        self._old_hook_event_spool_dir = os.environ.get(
            "AGENT_CANON_HOOK_EVENT_SPOOL_DIR"
        )
        self._old_git_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"] = "https://github.com/test/source.git"
        # Every archive fixture owns its temporary tree.  The ceiling prevents
        # Git from walking through the managed checkout when a fixture is
        # intentionally an empty/non-Git source or canon root.
        os.environ["GIT_CEILING_DIRECTORIES"] = tempfile.gettempdir()
        for env_name in (
            "AGENT_CANON_PARENT_ROOT",
            "AGENT_CANON_HOOK_ARCHIVE_DIR",
            "AGENT_CANON_HOOK_EVENT_SPOOL_DIR",
        ):
            os.environ.pop(env_name, None)

    def tearDown(self) -> None:
        """Restore the caller's source remote environment."""
        if self._old_source_remote is None:
            os.environ.pop("AGENT_CANON_SOURCE_REPOSITORY_REMOTE", None)
        else:
            os.environ["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"] = self._old_source_remote
        for env_name, old_value in (
            ("AGENT_CANON_PARENT_ROOT", self._old_parent_root),
            ("AGENT_CANON_HOOK_ARCHIVE_DIR", self._old_hook_archive_dir),
            ("AGENT_CANON_HOOK_EVENT_SPOOL_DIR", self._old_hook_event_spool_dir),
            ("GIT_CEILING_DIRECTORIES", self._old_git_ceiling),
        ):
            if old_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = old_value

    def test_git_index_locked_detects_transient_lock_failure(self) -> None:
        """Index lock errors should be classified for bounded retry."""
        result = subprocess.CompletedProcess(
            ["git", "commit"],
            128,
            "",
            "fatal: Unable to create '.git/index.lock': File exists.",
        )

        self.assertTrue(runtime_log_archive_git.git_index_locked(result))

    def test_owner_mutation_exclusive_mode_is_access_only_and_shared(self) -> None:
        """Projected mode is an access check, not file-identity evidence."""
        cases = (
            (0o600, 0o600, True),
            (0o700, 0o600, True),
            (0o755, 0o600, True),
            (0o700, 0o700, True),
            (0o755, 0o700, True),
            (0o555, 0o600, False),
            (0o655, 0o700, False),
            (0o660, 0o600, False),
            (0o775, 0o600, False),
            (0o775, 0o700, False),
            (0o777, 0o600, False),
            (0o777, 0o700, False),
        )
        for mode, required_owner_bits, accepted in cases:
            with self.subTest(
                mode=oct(mode), required_owner_bits=oct(required_owner_bits)
            ):
                self.assertEqual(
                    runtime_log_archive_git._owner_mutation_exclusive_mode(
                        mode, required_owner_bits
                    ),
                    accepted,
                )

        predicate_source = inspect.getsource(
            runtime_log_archive_git._owner_mutation_exclusive_mode
        )
        for identity_field in ("st_uid", "st_nlink", "st_dev", "st_ino"):
            self.assertNotIn(identity_field, predicate_source)
        call_sites = (
            (runtime_log_archive_git._validate_publication_attempt_directories, 1),
            (runtime_log_archive_git.validate_publication_attempt_lock, 2),
            (runtime_log_archive_git.acquire_publication_attempt_lock, 1),
            (runtime_log_archive_git._secure_publish_noreplace, 2),
        )
        for function, expected_calls in call_sites:
            with self.subTest(function=function.__name__):
                source = inspect.getsource(function)
                self.assertEqual(
                    source.count("_owner_mutation_exclusive_mode("),
                    expected_calls,
                )
        source = inspect.getsource(runtime_log_archive_git._secure_publish_noreplace)
        for retained_oracle in (
            "os.fchmod",
            "O_NOFOLLOW",
            "st_uid",
            "st_nlink",
            "st_dev",
            "st_ino",
            "_renameat2_noreplace",
            "os.fsync",
            "os.pread",
        ):
            self.assertIn(retained_oracle, source)
        for function in (
            runtime_log_archive_git._publish_context_discovery_noreplace,
            runtime_log_archive_git._publish_runtime_event_noreplace,
            runtime_log_archive_git.spool_publication_outcome,
            runtime_log_archive_git._publish_publication_outcome_receipt_noreplace,
        ):
            self.assertIn("_secure_publish_noreplace(", inspect.getsource(function))

    def test_publication_paths_accept_0755_projection_without_identity_drift(
        self,
    ) -> None:
        """A fixed read/execute projection does not replace freshness or identity."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            original_fstat = os.fstat
            original_lstat = Path.lstat

            def project_mode(metadata: os.stat_result) -> os.stat_result:
                values = list(metadata)
                values[stat.ST_MODE] = stat.S_IFMT(metadata.st_mode) | 0o755
                projected = os.stat_result(values)
                self.assertEqual(
                    stat.S_IFMT(projected.st_mode), stat.S_IFMT(metadata.st_mode)
                )
                for identity_field in (
                    "st_uid",
                    "st_nlink",
                    "st_dev",
                    "st_ino",
                    "st_size",
                ):
                    self.assertEqual(
                        getattr(projected, identity_field),
                        getattr(metadata, identity_field),
                    )
                return projected

            def projected_fstat(fd: int) -> os.stat_result:
                return project_mode(original_fstat(fd))

            def projected_lstat(path: Path) -> os.stat_result:
                return project_mode(original_lstat(path))

            context_bytes = b"{}\n"
            runtime_bytes = (
                json.dumps(
                    {"artifact_sha256": "a" * 64}, separators=(",", ":")
                )
                + "\n"
            ).encode("utf-8")
            context_target = root / "context" / "certificate.json"
            runtime_target = root / "runtime" / "runtime-event.json"
            with (
                patch.dict(
                    os.environ,
                    {"AGENT_CANON_PARENT_ROOT": str(root)},
                    clear=False,
                ),
                patch.object(os, "fstat", new=projected_fstat),
                patch.object(Path, "lstat", new=projected_lstat),
                patch.object(
                    runtime_log_archive_git,
                    "validate_context_discovery_certificate",
                ),
                patch.object(
                    runtime_log_archive_git,
                    "validate_runtime_event_schema",
                ),
            ):
                with runtime_log_archive_git.acquire_publication_attempt_lock(
                    source, "a" * 64, root / "runtime"
                ) as attempt_lock:
                    path_metadata = original_lstat(attempt_lock.lock_path)
                    fd_metadata = original_fstat(attempt_lock.fd)
                    self.assertEqual(
                        (path_metadata.st_dev, path_metadata.st_ino),
                        (fd_metadata.st_dev, fd_metadata.st_ino),
                    )
                runtime_log_archive_git._publish_context_discovery_noreplace(
                    context_target, context_bytes
                )
                evidence = runtime_log_archive_git._publish_runtime_event_noreplace(
                    runtime_target, runtime_bytes
                )

            self.assertEqual(context_target.read_bytes(), context_bytes)
            self.assertEqual(runtime_target.read_bytes(), runtime_bytes)
            self.assertEqual(evidence["readback_status"], "verified")
            self.assertEqual(evidence["readback_sha256"], "a" * 64)

    def test_publication_paths_reject_group_or_other_writable_projection(
        self,
    ) -> None:
        """Writable projections fail closed without weakening identity checks."""
        for scenario in ("attempt_directory", "attempt_lock"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp_dir:
                source = Path(tmp_dir) / "source"
                source.mkdir()
                original_fstat = os.fstat
                original_lstat = Path.lstat

                def projected_fstat(fd: int) -> os.stat_result:
                    metadata = original_fstat(fd)
                    mode = 0o775 if scenario == "attempt_lock" else 0o755
                    values = list(metadata)
                    values[stat.ST_MODE] = stat.S_IFMT(metadata.st_mode) | mode
                    return os.stat_result(values)

                def projected_lstat(path: Path) -> os.stat_result:
                    metadata = original_lstat(path)
                    writable = scenario == "attempt_directory" or (
                        scenario == "attempt_lock" and path.name == ".attempt.lock"
                    )
                    values = list(metadata)
                    values[stat.ST_MODE] = stat.S_IFMT(metadata.st_mode) | (
                        0o775 if writable else 0o755
                    )
                    return os.stat_result(values)

                with (
                    patch.object(os, "fstat", new=projected_fstat),
                    patch.object(Path, "lstat", new=projected_lstat),
                    self.assertRaises(
                        runtime_log_archive_git.RuntimeEventMaterializationError
                    ) as raised,
                ):
                    with runtime_log_archive_git.acquire_publication_attempt_lock(
                        source, "b" * 64, source.parent / "runtime"
                    ):
                        self.fail("writable attempt metadata was accepted")
                self.assertEqual(
                    raised.exception.code, "publication_attempt_lock_invalid"
                )

        publishers = (
            (
                "context",
                runtime_log_archive_git._publish_context_discovery_noreplace,
                b"{}\n",
                "context_publication_failure",
            ),
            (
                "runtime_event",
                runtime_log_archive_git._publish_runtime_event_noreplace,
                b"{}\n",
                "publication_failure",
            ),
        )
        for label, publisher, bytes_, expected_code in publishers:
            for phase in ("initial", "final"):
                with (
                    self.subTest(label=label, phase=phase),
                    tempfile.TemporaryDirectory() as tmp_dir,
                ):
                    subprocess.run(["git", "init", "-q", tmp_dir], check=True)
                    target = Path(tmp_dir) / label / "artifact.json"
                    original_fstat = os.fstat
                    original_lstat = Path.lstat

                    def projected_fstat(fd: int) -> os.stat_result:
                        metadata = original_fstat(fd)
                        values = list(metadata)
                        values[stat.ST_MODE] = stat.S_IFMT(metadata.st_mode) | (
                            0o775 if phase == "initial" else 0o755
                        )
                        return os.stat_result(values)

                    def projected_lstat(path: Path) -> os.stat_result:
                        metadata = original_lstat(path)
                        values = list(metadata)
                        values[stat.ST_MODE] = stat.S_IFMT(metadata.st_mode) | (
                            0o775 if phase == "final" else 0o755
                        )
                        return os.stat_result(values)

                    with (
                        patch.dict(
                            os.environ,
                            {"AGENT_CANON_PARENT_ROOT": tmp_dir},
                            clear=False,
                        ),
                        patch.object(os, "fstat", new=projected_fstat),
                        patch.object(Path, "lstat", new=projected_lstat),
                        self.assertRaises(
                            runtime_log_archive_git.RuntimeEventMaterializationError
                        ) as raised,
                    ):
                        publisher(target, bytes_)
                    self.assertEqual(raised.exception.code, expected_code)
                    self.assertFalse(target.exists())

    def test_secure_publication_rejects_intermediate_parent_replacement(self) -> None:
        """A parent component replacement fails before rename or residue escape."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            target = fixture.source / "tools" / "race-artifact.json"
            original_verify = runtime_log_archive_git._verify_secure_publication_parent
            verify_calls = 0
            moved_parent = target.parent.with_name("tools-moved")

            def replace_before_rename(context: object) -> None:
                nonlocal verify_calls
                verify_calls += 1
                if verify_calls == 2:
                    target.parent.rename(moved_parent)
                    target.parent.mkdir()
                original_verify(context)

            with patch.object(
                runtime_log_archive_git,
                "_verify_secure_publication_parent",
                side_effect=replace_before_rename,
            ):
                with self.assertRaises(
                    runtime_log_archive_git.RuntimeEventMaterializationError
                ) as raised:
                    with patch.object(
                        runtime_log_archive_git,
                        "validate_context_discovery_certificate",
                    ):
                        runtime_log_archive_git._publish_context_discovery_noreplace(
                            target, b"{}\n"
                        )
            self.assertEqual(raised.exception.code, "parent_boundary_race")
            self.assertFalse(target.exists())
            self.assertEqual(tuple(target.parent.glob(".*.tmp")), ())
            self.assertEqual(tuple(moved_parent.glob(".*.tmp")), ())
            self.assertFalse((moved_parent / target.name).exists())

    def test_writer_without_parent_root_fails_before_external_file_creation(self) -> None:
        """A representative adapter cannot fall back to an unbounded writer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "external-summary.json"
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AGENT_CANON_PARENT_ROOT", None)
                with self.assertRaises(github_publish.ParentRootSideEffectError) as raised:
                    github_publish._write_publication_summary(target, b"{}\n")
            self.assertEqual(
                raised.exception.reject,
                github_publish.ParentRootReject.HANDOFF_INVALID,
            )
            self.assertFalse(target.exists())
            self.assertEqual(tuple(root.iterdir()), ())

    def test_secure_publication_reports_cleanup_failure_without_suppression(self) -> None:
        """A failed temp cleanup is typed and never silently discarded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            target = fixture.source / "tools" / "cleanup-artifact.json"
            original_unlink = os.unlink

            def fail_temp_cleanup(
                path: str | bytes,
                *,
                dir_fd: int | None = None,
            ) -> None:
                if dir_fd is not None and str(path).startswith(".cleanup-artifact."):
                    raise OSError(5, "injected temporary cleanup failure")
                original_unlink(path, dir_fd=dir_fd)

            with (
                patch.object(
                    runtime_log_archive_git,
                    "validate_context_discovery_certificate",
                ),
                patch.object(
                    runtime_log_archive_git,
                    "_renameat2_noreplace_at",
                    side_effect=OSError(5, "injected publication failure"),
                ),
                patch.object(os, "unlink", side_effect=fail_temp_cleanup),
            ):
                with self.assertRaises(
                    runtime_log_archive_git.RuntimeEventMaterializationError
                ) as raised:
                    runtime_log_archive_git._publish_context_discovery_noreplace(
                        target, b"{}\n"
                    )
            self.assertEqual(raised.exception.code, "publication_cleanup_failed")
            self.assertFalse(target.exists())
            self.assertTrue(tuple(target.parent.glob(".cleanup-artifact.*.tmp")))

    def run_tool(
        self,
        *args: str,
        source_root: Path,
        canon_root: Path,
        remote: Path,
        runtime_root: Path | None = None,
        archive_root: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the archive helper with explicit temp paths."""
        # Runtime artifacts must be outside both the source checkout and the
        # AgentCanon checkout.  Keep the command-line boundary explicit so a
        # test cannot accidentally exercise the removed source-local fallback.
        runtime_root = runtime_root or source_root.parent / "runtime"
        env = os.environ.copy()
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["AGENT_CANON_LOG_ENV"] = "test-env"
        for env_name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID"):
            env.pop(env_name, None)
        if extra_env:
            env.update(extra_env)
        command = [
            sys.executable,
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--canon-root",
            str(canon_root),
            "--remote",
            str(remote),
        ]
        if archive_root is not None:
            command.extend(("--archive-root", str(archive_root)))
        command.extend(("--runtime-root", str(runtime_root), *args))
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )

    def expected_branch(self, source: Path, chat_key: str | None = None) -> str:
        """Return the stable source branch expected by run_tool."""
        return f"logs/{stable_source_repository_id(os.environ['AGENT_CANON_SOURCE_REPOSITORY_REMOTE'])}"

    def make_remote(self, root: Path) -> Path:
        """Create a temporary Git remote with a main branch."""
        seed = root / "seed"
        remote = root / "agent-canon-log.git"
        seed.mkdir()
        subprocess.run(["git", "init"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=seed, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=seed, check=True)
        (seed / "README.md").write_text("# Runtime Log Archive\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "InitialCommit"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "clone", "--bare", str(seed), str(remote)], check=True, capture_output=True)
        return remote

    def runtime_root(self, root: Path) -> Path:
        """Return the fixture's external runtime boundary."""
        return root / "runtime"

    def source_snapshot(self, source: Path) -> tuple[tuple[str, str, str], ...]:
        """Capture source bytes and entry kinds without including external runtime state."""
        entries: list[tuple[str, str, str]] = []
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            relative = path.relative_to(source).as_posix()
            if path.is_dir():
                entries.append((relative, "dir", ""))
            elif path.is_file():
                entries.append((relative, "file", hashlib.sha256(path.read_bytes()).hexdigest()))
            else:
                entries.append((relative, "other", ""))
        return tuple(entries)

    def make_valid_materialization_fixture(
        self,
        root: Path,
        *,
        run_id: str = "run-materializer",
    ) -> RuntimeMaterializationFixture:
        """Create one active-run, rollout, result, and target/base identity fixture."""
        canon = root / "agent-canon"
        source = root / "source"
        source.mkdir(parents=True)
        # The external runtime boundary still needs an authenticated parent
        # root for secure publication.  Keep that parent Git root outside the
        # source checkout so the fixture can assert source-tree cleanliness.
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "Test User"],
            check=True,
        )
        target_relative = "tools/materialized_target.py"
        target_path = source / target_relative
        target_path.parent.mkdir(parents=True)
        target_path.write_bytes(b"base target\n")
        subprocess.run(["git", "-C", str(source), "add", target_relative], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-qm", "base target"],
            check=True,
        )
        base_oid = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        target_path.write_bytes(b"current target\n")
        subprocess.run(["git", "-C", str(source), "add", target_relative], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-qm", "current target"],
            check=True,
        )
        head_oid = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        run_dir = source / "reports" / "agents" / run_id
        run_dir.mkdir(parents=True)
        (source / "reports" / "agents" / ".active_run").write_text(
            f"{run_id}\n", encoding="utf-8"
        )
        result_path = run_dir / "validation_result.json"
        result_path.write_text(
            json.dumps(
                {
                    "schema": "agent_canon.runtime_result_input.v1",
                    "result": "PASS",
                    "gate_id": "validation",
                    "target_paths": [target_relative],
                    "base_ref": base_oid,
                    "observations": {"head_oid": head_oid, "base_oid": base_oid},
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        thread_id = "11111111-1111-4111-8111-111111111111"
        context_id = "22222222-2222-4222-8222-222222222222"
        parent_id = "44444444-4444-4444-8444-444444444444"
        turn_id = "55555555-5555-4555-8555-555555555555"
        session_root = root / "sessions"
        session_day = session_root / "2026" / "07" / "17"
        session_day.mkdir(parents=True)
        rollout = session_day / (
            f"rollout-2026-07-17T12-00-00.123Z-{context_id}.jsonl"
        )
        session_meta = {
            "type": "session_meta",
            "payload": {
                "id": context_id,
                "parent_thread_id": parent_id,
                "agent_role": "worker",
                "cwd": str(source),
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": parent_id,
                            "agent_role": "worker",
                        }
                    }
                }
            }
        }
        records = [
            json.dumps({"type": "noop", "index": index}, separators=(",", ":"))
            + "\n"
            for index in range(870)
        ]
        records.extend(
            [
                json.dumps(session_meta, separators=(",", ":")) + "\n",
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {"type": "task_complete", "turn_id": turn_id},
                    },
                    separators=(",", ":"),
                )
                + "\n",
            ]
        )
        rollout.write_text("".join(records), encoding="utf-8")
        raw_record = rollout.read_bytes().splitlines(keepends=True)[871]
        unit_id = hashlib.sha256(raw_record).hexdigest()[:16]
        target = run_dir / f"runtime_event.{unit_id}.json"
        old_state = run_dir / "runtime_event.0000000000000000.json"
        runtime_root = root / "runtime"
        runtime_root.mkdir(mode=0o700)
        canon.mkdir()
        context = runtime_log_archive_git.ArchiveContext(
            source_root=source,
            canon_root=canon,
            archive_root=root / "archive",
            repo_key="fixture",
            env_key="fixture",
            branch_key="fixture",
            branch="logs/fixture",
            remote=str(root / "remote.git"),
            runtime_root=runtime_root,
        )
        args = argparse.Namespace(
            result_family="validation",
            run_id=run_id,
            gate_id="validation",
            base_ref=base_oid,
            unit_id=None,
        )
        producer_stdout = io.StringIO()
        producer_stderr = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {"AGENT_CANON_CODEX_SESSION_ROOT": str(session_root)},
                clear=False,
            ),
            contextlib.redirect_stdout(producer_stdout),
            contextlib.redirect_stderr(producer_stderr),
        ):
            self.assertEqual(
                runtime_log_archive_git.main(
                    [
                        "--source-root",
                        str(source),
                        "--canon-root",
                        str(source),
                        "--archive-root",
                        str(context.archive_root),
                        "--runtime-root",
                        str(context.runtime_root),
                        "append-context-discovery",
                        "--run-id",
                        run_id,
                        "--agent-context-id",
                        context_id,
                        "--turn-id",
                        turn_id,
                    ]
                ),
                0,
            )
        self.assertEqual(producer_stderr.getvalue(), "")
        self.assertIn("CONTEXT_DISCOVERY_APPEND=pass\n", producer_stdout.getvalue())
        return RuntimeMaterializationFixture(
            source=source,
            context=context,
            args=args,
            thread_id=thread_id,
            context_id=context_id,
            turn_id=turn_id,
            session_root=session_root,
            rollout=rollout,
            raw_record=raw_record,
            target=target,
            old_state=old_state,
            base_oid=base_oid,
            head_oid=head_oid,
            target_relative=target_relative,
            result_path=result_path,
        )

    def producer_argv(self, fixture: RuntimeMaterializationFixture) -> list[str]:
        """Return the exact public argv for one context producer invocation."""
        return [
            "--source-root",
            str(fixture.source),
            "--canon-root",
            str(fixture.source),
            "--archive-root",
            str(fixture.context.archive_root),
            "--runtime-root",
            str(fixture.context.runtime_root),
            "append-context-discovery",
            "--run-id",
            fixture.args.run_id,
            "--agent-context-id",
            fixture.context_id,
            "--turn-id",
            fixture.turn_id,
        ]

    def invoke_producer(
        self, fixture: RuntimeMaterializationFixture
    ) -> tuple[int, str, str]:
        """Invoke the public context producer and capture its exact streams."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {"AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root)},
                clear=False,
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = runtime_log_archive_git.main(self.producer_argv(fixture))
        return result, stdout.getvalue(), stderr.getvalue()

    def assert_producer_failure(
        self,
        fixture: RuntimeMaterializationFixture,
        code: str,
    ) -> None:
        """Require one exact typed public context-producer failure."""
        result, stdout, stderr = self.invoke_producer(fixture)
        self.assertEqual(result, 1)
        self.assertEqual(
            stdout,
            f"CONTEXT_DISCOVERY_ERROR_CODE={code}\n"
            "CONTEXT_DISCOVERY_APPEND=fail\n",
        )
        self.assertEqual(stderr, "")

    def materializer_argv(self, fixture: RuntimeMaterializationFixture) -> list[str]:
        """Return the exact public argv for one fixture materialization."""
        return [
            "--source-root",
            str(fixture.source),
            "--canon-root",
            str(fixture.source),
            "--archive-root",
            str(fixture.context.archive_root),
            "--runtime-root",
            str(fixture.context.runtime_root),
            "materialize-runtime-event",
            "--result-family",
            fixture.args.result_family,
            "--run-id",
            fixture.args.run_id,
            "--gate-id",
            fixture.args.gate_id,
            "--base-ref",
            fixture.args.base_ref,
        ]

    def invoke_materializer(
        self, fixture: RuntimeMaterializationFixture
    ) -> tuple[int, str, str]:
        """Invoke the public command and capture its exact process streams."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root),
                },
                clear=False,
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = runtime_log_archive_git.main(self.materializer_argv(fixture))
        return result, stdout.getvalue(), stderr.getvalue()

    def assert_materializer_failure(
        self,
        fixture: RuntimeMaterializationFixture,
        code: str,
    ) -> None:
        """Require one exact typed public materialization failure."""
        result, stdout, stderr = self.invoke_materializer(fixture)
        self.assertEqual(result, 1)
        self.assertEqual(
            stdout,
            f"RUNTIME_EVENT_ERROR_CODE={code}\nRUNTIME_EVENT_MATERIALIZE=fail\n",
        )
        self.assertEqual(stderr, "")

    def observation_directory(
        self, fixture: RuntimeMaterializationFixture, attempt_id: str
    ) -> Path:
        """Return the exact attempt-local observation directory."""
        return runtime_event_publication_outcome_spool_root(
            fixture.source, fixture.context.runtime_root
        ) / attempt_id

    def archive_branch(self, archive: Path) -> str:
        """Return the currently checked out archive branch."""
        return subprocess.run(
            ["git", "-C", str(archive), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_repo_key_prints_branch_context(self) -> None:
        """repo-key should show the source-remote-derived stable branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            chat_key = "Chat UUID 1"

            result = self.run_tool(
                "repo-key",
                source_root=source,
                canon_root=canon,
                remote=remote,
                extra_env={"CODEX_THREAD_ID": chat_key},
            )

        key = repo_log_key(source)
        expected_branch = self.expected_branch(source, chat_key)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={key}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_BRANCH_KEY={stable_source_repository_id(os.environ['AGENT_CANON_SOURCE_REPOSITORY_REMOTE'])}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_BRANCH={expected_branch}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL={source / 'reports' / 'agents'}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH={expected_branch}", result.stdout)
        self.assertIn(
            f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={mounted_log_archive_root(canon, self.runtime_root(root)) / 'agent-reports' / key}",
            result.stdout,
        )
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{key}", result.stdout)

    def test_repo_key_defaults_to_canon_root_when_run_inside_canon_checkout(self) -> None:
        """Running from AgentCanon itself should key logs to the AgentCanon checkout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canon = root / "agent-canon"
            canon.mkdir()
            remote = self.make_remote(root)
            subprocess.run(["git", "init"], cwd=canon, check=True, capture_output=True)
            env = os.environ.copy()
            env["GIT_CONFIG_GLOBAL"] = os.devnull
            env["AGENT_CANON_LOG_ENV"] = "test-env"
            for env_name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID"):
                env.pop(env_name, None)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--canon-root",
                    str(canon),
                    "--remote",
                    str(remote),
                    "--runtime-root",
                    str(root / "runtime"),
                    "repo-key",
                ],
                check=False,
                capture_output=True,
                cwd=canon,
                env=env,
                text=True,
            )

        key = repo_log_key(canon)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_SOURCE_ROOT={canon}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={key}", result.stdout)

    def test_ensure_status_and_push_logs_branch(self) -> None:
        """Ensure should create the clone, and push should commit source repo logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)

            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            self.assertTrue((archive / ".git").exists())
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(archive), "branch", "--show-current"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                self.expected_branch(source),
            )

            log_path = archive / "hook-runs" / key / "test" / "skill_usage-no-git-head.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-1",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "payload_fingerprint": "abc",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=yes", status.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)

            dirty_clean_check = self.run_tool(
                "check-clean",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(dirty_clean_check.returncode, 0, dirty_clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", dirty_clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", dirty_clean_check.stdout)

            push = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(push.returncode, 0, push.stdout + push.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", push.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_PUSH=pass", push.stdout)

            clean_check = self.run_tool(
                "check-clean",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(clean_check.returncode, 0, clean_check.stdout + clean_check.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass", clean_check.stdout)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(archive), "config", "--get", "user.email"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "agent-canon-log@example.invalid",
            )

            remote_ref = subprocess.run(
                ["git", "--git-dir", str(remote), "show-ref", "--verify", f"refs/heads/{self.expected_branch(source)}"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remote_ref.returncode, 0, remote_ref.stderr)

    def test_ensure_preserves_keyed_dirty_logs_before_branch_switch(self) -> None:
        """Ensure should commit managed dirty logs before switching branches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            self.assertEqual(self.archive_branch(archive), self.expected_branch(other_source))

            log_path = archive / "hook-runs" / key / "runtime" / "skill_usage.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-current-key",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(source))
            self.assertTrue(log_path.exists())

    def test_ensure_preserves_foreign_dirty_logs_before_branch_switch(self) -> None:
        """Ensure should preserve managed logs even when target repo key differs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            other_key = repo_log_key(other_source)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "skill_usage.jsonl"
            foreign_log.parent.mkdir(parents=True)
            foreign_log.write_text('{"hook_run_id": "foreign-dirty"}\n', encoding="utf-8")

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(source))
            self.assertTrue(foreign_log.exists())

    def test_ensure_rejects_archive_level_dirty_paths_before_branch_switch(self) -> None:
        """Ensure should not auto-preserve archive-level policy/tool dirt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            tool_path = archive / "tools" / "runtime_log_dashboard.py"
            tool_path.parent.mkdir(parents=True)
            tool_path.write_text("# dashboard change\n", encoding="utf-8")

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(other_source))
            self.assertTrue(tool_path.exists())

    def test_status_reports_foreign_repo_key_dirty_paths(self) -> None:
        """status/check-clean should expose dirty paths for another repo key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            other_key = repo_log_key(other_source)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "module_boundary_guard-no-git-head.jsonl"
            foreign_log.parent.mkdir(parents=True)
            foreign_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-foreign",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": other_key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={other_key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS=", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={key}", status.stdout)

            clean_check = self.run_tool(
                "check-clean",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(clean_check.returncode, 0, clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", clean_check.stdout)

    def test_check_clean_rejects_committed_foreign_repo_key_tree(self) -> None:
        """check-clean should reject committed trees for other repo keys on a chat branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            other_key = stable_source_repository_id("https://github.com/test/other.git")

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "skill_usage-no-git-head.jsonl"
            foreign_log.parent.mkdir(parents=True)
            foreign_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-committed-foreign",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": other_key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(archive), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(archive), "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", str(archive), "add", "hook-runs"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(archive), "commit", "-m", "Commit foreign tree"],
                check=True,
                capture_output=True,
            )

            clean_check = self.run_tool(
                "check-clean",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(clean_check.returncode, 0, clean_check.stdout + clean_check.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", clean_check.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS={other_key}", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", clean_check.stdout)

    def test_check_clean_allows_source_and_canon_repo_key_trees(self) -> None:
        """A chat branch may contain source and AgentCanon repo-key trees."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            canon_key = repo_log_key(canon)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            canon_log = archive / "hook-runs" / canon_key / "runtime" / "skill_usage-no-git-head.jsonl"
            canon_log.parent.mkdir(parents=True)
            canon_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-associated-canon",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": canon_key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(archive), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(archive), "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", str(archive), "add", "hook-runs"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(archive), "commit", "-m", "Commit associated canon tree"],
                check=True,
                capture_output=True,
            )

            clean_check = self.run_tool(
                "check-clean",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(clean_check.returncode, 0, clean_check.stdout + clean_check.stderr)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_TREE_KEYS={canon_key}", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS=", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass", clean_check.stdout)

    def test_status_allows_associated_repo_key_dirty_paths(self) -> None:
        """Dirty logs from source or AgentCanon repo keys are associated chat evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            canon_key = repo_log_key(canon)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            canon_log = archive / "hook-runs" / canon_key / "runtime" / "skill_usage.jsonl"
            canon_log.parent.mkdir(parents=True)
            canon_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-associated-dirty",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": canon_key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={canon_key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS=", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)

    def test_status_reports_archive_level_dirty_paths(self) -> None:
        """Status should separate archive-level tool or policy dirt from repo-key logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            tool_path = archive / "tools" / "runtime_log_dashboard.py"
            tool_path.parent.mkdir(parents=True)
            tool_path.write_text("# dashboard tool update\n", encoding="utf-8")

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY_KEYS=", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=no", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_GLOBAL_DIRTY=yes", status.stdout)
            self.assertIn("commit or revert archive-level dirty paths", status.stdout)

    def test_archive_agent_reports_copies_run_bundles(self) -> None:
        """archive-agent-reports should copy reports/agents into the log branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            run_dir = source / "reports" / "agents" / "run-1"
            run_dir.mkdir(parents=True)
            (source / "reports" / "agents" / ".active_run").write_text("run-1\n", encoding="utf-8")
            (run_dir / "summary.md").write_text("# Summary\n", encoding="utf-8")
            (run_dir / "state.json").write_text('{"ok": true}\n', encoding="utf-8")

            ensured = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensured.returncode, 0, ensured.stdout + ensured.stderr)

            archived = self.run_tool(
                "archive-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(archived.returncode, 0, archived.stdout + archived.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES=2", archived.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COPIED=2", archived.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SKIPPED=0", archived.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{key}", archived.stdout)

            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            snapshot_line = next(line for line in archived.stdout.splitlines() if line.startswith("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT="))
            snapshot = snapshot_line.split("=", 1)[1]
            self.assertTrue((archive / "agent-reports" / key / "run-1" / snapshot / "summary.md").exists())
            self.assertTrue((archive / "agent-reports" / key / "run-1" / snapshot / "state.json").exists())
            self.assertFalse((archive / "agent-reports" / key / ".active_run").exists())

            pushed = self.run_tool(
                "push",
                "--message",
                "Archive agent reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", pushed.stdout)

    def test_sync_pushes_codex_runtime_and_agent_reports(self) -> None:
        """Sync should be the unattended path for runtime summaries and agent reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            ensured = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensured.returncode, 0, ensured.stdout + ensured.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            runtime_summary = archive / "codex-runtime" / key / "chats" / "thread-1" / "summary-no-git-head.jsonl"
            runtime_summary.parent.mkdir(parents=True)
            runtime_summary.write_text('{"conversation_id": "thread-1", "thread_id": "thread-1"}\n', encoding="utf-8")
            runtime_index = archive / "codex-runtime" / key / "index.jsonl"
            runtime_index.write_text(
                '{"conversation_id": "thread-1", "summary_path": "chats/thread-1/summary-no-git-head.jsonl"}\n',
                encoding="utf-8",
            )
            run_dir = source / "reports" / "agents" / "run-2"
            run_dir.mkdir(parents=True)
            (run_dir / "closeout_gate.md").write_text("closeout=yes\n", encoding="utf-8")

            synced = self.run_tool("sync", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", synced.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", synced.stdout)

            clone = root / "verification"
            subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(clone), "switch", self.expected_branch(source)], check=True, capture_output=True)
            self.assertTrue((clone / "codex-runtime" / key / "chats" / "thread-1" / "summary-no-git-head.jsonl").exists())
            self.assertTrue((clone / "codex-runtime" / key / "index.jsonl").exists())
            snapshots = list((clone / "agent-reports" / key / "run-2").iterdir())
            self.assertEqual(len(snapshots), 1)
            self.assertTrue((snapshots[0] / "closeout_gate.md").exists())

    def test_sync_with_explicit_archive_root_keeps_reports_in_archive_clone(self) -> None:
        """Explicit private archive roots must not create a runtime archive clone."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            runtime = root / ".runtime"
            archive = root / "agent-canon-log"
            source.mkdir()
            canon.mkdir()
            runtime.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            run_dir = source / "reports" / "agents" / "run-explicit-archive"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.md").write_text("# Summary\n", encoding="utf-8")

            synced = self.run_tool(
                "sync",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime,
                archive_root=archive,
            )

            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", synced.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_PUSH_STATUS=committed", synced.stdout)
            self.assertIn(
                f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={archive / 'agent-reports' / key}",
                synced.stdout,
            )
            self.assertTrue(archive.is_dir())
            self.assertFalse((runtime / "archive").exists())
            clean = self.run_tool(
                "check-clean",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime,
                archive_root=archive,
            )
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=yes", clean.stdout)

    def test_sync_with_canonical_source_runtime_uses_spool_only(self) -> None:
        """The install-root runtime handles locks/spool while reports stay external."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            runtime = source / ".runtime"
            archive = root / "agent-canon-log"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            run_dir = source / "reports" / "agents" / "run-source-runtime"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.md").write_text("# Summary\n", encoding="utf-8")

            synced = self.run_tool(
                "sync",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime,
                archive_root=archive,
            )

            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", synced.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", synced.stdout)
            self.assertTrue((archive / "agent-reports" / key).is_dir())
            self.assertFalse((runtime / "archive").exists())

            rerun = self.run_tool(
                "sync",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime,
                archive_root=archive,
            )
            self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", rerun.stdout)
            self.assertFalse((runtime / "archive").exists())

    def test_external_runtime_bare_remote_readback_duplicate_noop_and_conflict(self) -> None:
        """The external runtime flow proves remote objects, replay no-op, and conflict retention."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            runtime_root = self.runtime_root(root)
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            source_before = self.source_snapshot(source)
            event_id = "hook-20260822-external-e2e"
            event = {
                "hook_log_namespace": "test-runtime",
                "hook_run_id": event_id,
                "payload_fingerprint": "external-e2e",
                "source_repo_key": key,
                "status": "pass",
                "timestamp": "2026-08-22T00:00:00Z",
            }
            event_bytes = runtime_log_archive_git._canonical_compact_json(event) + b"\n"
            spool_path = (
                runtime_root
                / "spool"
                / "hook-events"
                / key
                / "test-runtime"
                / "posttooluse"
                / f"{event_id}.json"
            )
            spool_path.parent.mkdir(parents=True)
            spool_path.write_bytes(event_bytes)

            ensured = self.run_tool(
                "ensure",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime_root,
            )
            self.assertEqual(ensured.returncode, 0, ensured.stdout + ensured.stderr)
            synced = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime_root,
            )
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SPOOL_SOURCE_EVENTS=1", synced.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", synced.stdout)
            self.assertFalse(spool_path.exists())
            self.assertEqual(self.source_snapshot(source), source_before)

            branch = self.expected_branch(source)
            remote_head = subprocess.run(
                ["git", "--git-dir", str(remote), "rev-parse", branch],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            clone = root / "readback-clone"
            subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(clone), "switch", branch], check=True, capture_output=True)
            projection = clone / "hook-runs" / key / "test-runtime" / "posttooluse-no-git-head.jsonl"
            self.assertEqual(projection.read_bytes(), event_bytes)
            self.assertEqual(
                subprocess.run(
                    ["git", "--git-dir", str(remote), "show-ref", "--verify", f"refs/heads/{branch}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.split()[0],
                remote_head,
            )
            tree_paths = subprocess.run(
                ["git", "-C", str(clone), "ls-tree", "-r", "--name-only", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertIn(projection.relative_to(clone).as_posix(), tree_paths)
            blob_oid = subprocess.run(
                ["git", "-C", str(clone), "rev-parse", f"HEAD:{projection.relative_to(clone).as_posix()}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(clone), "cat-file", "blob", blob_oid],
                    check=True,
                    capture_output=True,
                ).stdout,
                event_bytes,
            )

            duplicate = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime_root,
            )
            self.assertEqual(duplicate.returncode, 0, duplicate.stdout + duplicate.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SPOOL_SOURCE_EVENTS=0", duplicate.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=no", duplicate.stdout)
            self.assertEqual(
                subprocess.run(
                    ["git", "--git-dir", str(remote), "rev-parse", branch],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                remote_head,
            )

            diverged = root / "diverged"
            subprocess.run(["git", "clone", str(remote), str(diverged)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(diverged), "switch", branch], check=True, capture_output=True)
            diverged_cursor = diverged / "hook-runs" / key / ".spool-cursor.json"
            self.assertTrue(diverged_cursor.is_file())
            diverged_cursor.write_text('{"remote_conflict":true}\n', encoding="utf-8")
            subprocess.run(["git", "-C", str(diverged), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(diverged), "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", str(diverged), "add", str(diverged_cursor.relative_to(diverged))], check=True)
            subprocess.run(["git", "-C", str(diverged), "commit", "-m", "remote conflict"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(diverged), "push", "origin", f"HEAD:{branch}"], check=True, capture_output=True)

            second_id = "hook-20260822-external-conflict"
            second_path = spool_path.with_name(f"{second_id}.json")
            second_event = dict(event, hook_run_id=second_id, payload_fingerprint="external-conflict")
            second_path.write_bytes(runtime_log_archive_git._canonical_compact_json(second_event) + b"\n")
            conflict = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
                runtime_root=runtime_root,
            )
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn("RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS=uncertain", conflict.stdout)
            self.assertIn("conflict:", conflict.stdout)
            self.assertTrue(second_path.exists())
            self.assertEqual(self.source_snapshot(source), source_before)

    def test_archive_eval_switches_repository_branch_inside_shared_transaction(self) -> None:
        """Sequential eval publication selects each source branch under one lease."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canon = root / "agent-canon"
            canon.mkdir()
            runtime_root = self.runtime_root(root)
            remote = self.make_remote(root)

            sources = (root / "source-a", root / "source-b")
            remotes = (
                "https://github.com/test/source-a.git",
                "https://github.com/test/source-b.git",
            )
            branches: list[str] = []
            for index, (source, source_remote) in enumerate(
                zip(sources, remotes, strict=True),
                start=1,
            ):
                source.mkdir()
                run_id = f"eval-source-{index}"
                spool = runtime_root / "spool" / run_id
                results = spool / "eval-results" / "fixture"
                logs = spool / "producer-logs"
                results.mkdir(parents=True)
                logs.mkdir(parents=True)
                (results / "result.md").write_text(
                    f"source={index}\n",
                    encoding="utf-8",
                )
                (logs / "producer.stdout.txt").write_text(
                    f"producer={index}\n",
                    encoding="utf-8",
                )
                (spool / "collection.json").write_text(
                    json.dumps(
                        {
                            "schema": "agent_canon.eval_collection.v1",
                            "run_id": run_id,
                        },
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )

                published = self.run_tool(
                    "archive-eval",
                    "--spool-root",
                    str(spool),
                    "--run-id",
                    run_id,
                    source_root=source,
                    canon_root=canon,
                    remote=remote,
                    runtime_root=runtime_root,
                    extra_env={
                        "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": source_remote,
                    },
                )
                self.assertEqual(
                    published.returncode,
                    0,
                    published.stdout + published.stderr,
                )
                branch = f"logs/{stable_source_repository_id(source_remote)}"
                branches.append(branch)
                self.assertIn(
                    f"RUNTIME_LOG_ARCHIVE_EVAL_REMOTE_REF=refs/heads/{branch}",
                    published.stdout,
                )

            duplicate = self.run_tool(
                "archive-eval",
                "--spool-root",
                str(runtime_root / "spool" / "eval-source-2"),
                "--run-id",
                "eval-source-2",
                source_root=sources[1],
                canon_root=canon,
                remote=remote,
                runtime_root=runtime_root,
                extra_env={
                    "AGENT_CANON_SOURCE_REPOSITORY_REMOTE": remotes[1],
                },
            )
            self.assertEqual(
                duplicate.returncode,
                0,
                duplicate.stdout + duplicate.stderr,
            )
            self.assertIn(
                "RUNTIME_LOG_ARCHIVE_EVAL_STATUS=duplicate_noop",
                duplicate.stdout,
            )
            for branch in branches:
                subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        str(remote),
                        "show-ref",
                        "--verify",
                        f"refs/heads/{branch}",
                    ],
                    check=True,
                    capture_output=True,
                )

    def test_import_legacy_copies_and_deletes_old_jsonl(self) -> None:
        """import-legacy should move old in-tree hook JSONL to the archive."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            legacy = canon / "agents" / "evals" / "results" / "hook-runs" / "old-runtime"
            legacy.mkdir(parents=True)
            source_log = legacy / "skill_usage.jsonl"
            source_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "legacy-hook",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            imported = self.run_tool(
                "import-legacy",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_FILES=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=yes", imported.stdout)
            self.assertFalse(source_log.exists())

            archive_log = (
                mounted_log_archive_root(canon, self.runtime_root(root))
                / "legacy-import"
                / "hook-runs"
                / "old-runtime"
                / "skill_usage.jsonl"
            )
            self.assertTrue(archive_log.exists())

            pushed = self.run_tool(
                "push",
                "--message",
                "Import legacy logs",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=no", pushed.stdout)

    def test_import_eval_results_preserves_destinationless_hook_notice(self) -> None:
        """Only concrete imported records may be deleted after readback proof."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            results = canon / "agents" / "evals" / "results"
            skill_dir = results / "skill-workflow-prompt"
            hook_dir = results / "hook-runs"
            skill_dir.mkdir(parents=True)
            hook_dir.mkdir(parents=True)
            root_notice = results / "README.md"
            hook_notice = hook_dir / "README.md"
            family_notice = skill_dir / "README.md"
            report = skill_dir / "skill-eval-20260517T010203040506Z-1234567890-pass-agent-orchestration.md"
            root_notice.write_text("source notice\n", encoding="utf-8")
            hook_notice.write_text("hook notice\n", encoding="utf-8")
            family_notice.write_text("family notice\n", encoding="utf-8")
            report.write_text("EVAL_RUN_ID=skill-eval-20260517T010203040506Z-1234567890\n", encoding="utf-8")

            imported = self.run_tool(
                "import-eval-results",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_FILES=3", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS=3", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_PRESERVED=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_NOT_IMPORTED=1", imported.stdout)
            self.assertFalse(root_notice.exists())
            self.assertTrue(hook_notice.exists())
            self.assertFalse(family_notice.exists())
            self.assertFalse(report.exists())

            archive = mounted_log_archive_root(canon, self.runtime_root(root)) / "legacy-import" / "eval-results"
            self.assertTrue((archive / "README.md").exists())
            self.assertTrue((archive / "skill-workflow-prompt" / family_notice.name).exists())
            self.assertTrue((archive / "skill-workflow-prompt" / report.name).exists())
            self.assertFalse((archive / "hook-runs" / hook_notice.name).exists())

            pushed = self.run_tool(
                "push",
                "--message",
                "Import legacy eval results",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=no", pushed.stdout)

    def test_import_eval_results_reports_no_deletion_when_all_records_are_preserved(self) -> None:
        """All destinationless records report no deletion after successful readback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            hook_notice = canon / "agents" / "evals" / "results" / "hook-runs" / "README.md"
            hook_notice.parent.mkdir(parents=True)
            hook_notice.write_text("hook notice\n", encoding="utf-8")

            imported = self.run_tool(
                "import-eval-results",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_DELETIONS=0", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_PRESERVED=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_NOT_IMPORTED=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS=0", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_PRESERVED=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_NOT_IMPORTED=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no", imported.stdout)
            self.assertTrue(hook_notice.exists())

    def test_correspondence_reverse_map_and_root_commands_read_back(self) -> None:
        """The declared reverse map and validation commands are executable readback."""
        manifest_path = (
            PROJECT_ROOT
            / "documents"
            / "design"
            / "runtime-log-repository-lifecycle-correspondence.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        targets = {item["path"] for item in manifest["implementation_targets"]}
        for target in targets:
            self.assertTrue((PROJECT_ROOT / target).exists(), target)
        self.assertNotIn("tools/runtime/archive/runtime_log_paths.py", targets)
        reverse_coverage = LIFECYCLE_REVERSE_COVERAGE
        self.assertEqual(set(reverse_coverage), targets)
        clause_ids = set(manifest["clause_ids"])
        for path, clauses in reverse_coverage.items():
            self.assertTrue(clauses, path)
            self.assertTrue(set(clauses) <= clause_ids, path)

        for route in manifest["validation_route"]:
            self.assertEqual(route["cwd"], ".")
            argv = route["argv"]
            self.assertIsInstance(argv, list)
            self.assertTrue(argv)
            self.assertTrue(all(isinstance(token, str) and token for token in argv))
            for token in argv:
                path = Path(token)
                if path.is_absolute() or "/" not in token:
                    continue
                if path.suffix not in {".py", ".sh"}:
                    continue
                self.assertTrue((PROJECT_ROOT / path).is_file(), token)

    def test_legacy_delete_waits_for_remote_readback_and_retains_on_failure(self) -> None:
        """Legacy source remains when archive push fails, then deletes after retry readback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            legacy = canon / "agents" / "evals" / "results" / "hook-runs" / "old-runtime"
            legacy.mkdir(parents=True)
            source_log = legacy / "skill_usage.jsonl"
            source_log.write_text("{\"hook_run_id\":\"retained\"}\n", encoding="utf-8")
            reject_hook = remote / "hooks" / "pre-receive"
            reject_hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            reject_hook.chmod(reject_hook.stat().st_mode | stat.S_IXUSR)

            failed = self.run_tool(
                "import-legacy",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertTrue(source_log.exists())
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no", failed.stdout)
            reject_hook.unlink()

            recovered = self.run_tool(
                "import-legacy",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertFalse(source_log.exists())
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=yes", recovered.stdout)

    def test_normal_sync_and_push_have_no_source_delete_authority(self) -> None:
        """Normal runtime publication cannot delete a legacy source file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            legacy = canon / "agents" / "evals" / "results" / "hook-runs"
            legacy.mkdir(parents=True)
            source_log = legacy / "normal-sync.jsonl"
            source_log.write_text("retained\n", encoding="utf-8")
            synced = self.run_tool(
                "sync",
                "--no-agent-reports",
                "--no-push",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            pushed = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertTrue(source_log.exists())

    def test_preflight_and_internal_transaction_order_is_explicit(self) -> None:
        """The public sync entry and publication helper preserve the design state order."""
        sync_source = inspect.getsource(runtime_log_archive_git.command_sync)
        publish_source = inspect.getsource(runtime_log_archive_git.publish_prepared_archive)
        self.assertLess(sync_source.index("prepare_archive_transaction"), sync_source.index("snapshot_hook_spool_events"))
        for earlier, later in (
            ("stage_archive_paths", "ensure_commit_identity"),
            ("ensure_commit_identity", "_compare_and_push"),
        ):
            self.assertLess(publish_source.index(earlier), publish_source.index(later))
        for function in (
            runtime_log_archive_git.command_sync,
            runtime_log_archive_git.command_push,
            runtime_log_archive_git.publish_prepared_archive,
        ):
            self.assertNotIn("delete_source_file", inspect.getsource(function))
        compare_source = inspect.getsource(runtime_log_archive_git._compare_and_push)
        self.assertNotIn("--force", compare_source)
        self.assertNotIn('"merge"', compare_source)

    def test_archive_agent_report_snapshots_run_bundle_and_pushes(self) -> None:
        """archive-agent-report should copy a run bundle into agent-reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            report_dir = source / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "verification.txt").write_text("status=pass\n", encoding="utf-8")
            (report_dir / "work_log.md").write_text("# Work Log\n\n- done\n", encoding="utf-8")

            ensured = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensured.returncode, 0, ensured.stdout + ensured.stderr)

            archived = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(report_dir),
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(archived.returncode, 0, archived.stdout + archived.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass", archived.stdout)
            snapshot_line = next(
                line
                for line in archived.stdout.splitlines()
                if line.startswith("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT=")
            )
            snapshot = snapshot_line.split("=", 1)[1]
            archive = mounted_log_archive_root(canon, self.runtime_root(root)) / "agent-reports" / key / "run-1" / snapshot
            self.assertTrue((archive / "verification.txt").exists())
            self.assertTrue((archive / "archive_manifest.json").exists())
            manifest = json.loads((archive / "archive_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("codex_trace_key", manifest)
            self.assertIn("source_git_head", manifest)
            index_path = mounted_log_archive_root(canon, self.runtime_root(root)) / "agent-reports" / key / "index.jsonl"
            first_index = index_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(first_index), 1)

            archived_again = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(report_dir),
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(archived_again.returncode, 0, archived_again.stdout + archived_again.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED=no", archived_again.stdout)
            self.assertEqual(index_path.read_text(encoding="utf-8").splitlines(), first_index)

            pushed = self.run_tool(
                "push",
                "--message",
                "Archive agent report",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", pushed.stdout)
            remote_tree = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(remote),
                    "ls-tree",
                    "-r",
                    "--name-only",
                    self.expected_branch(source),
                    "--",
                    "agent-reports",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("agent-reports", remote_tree.stdout)

    def test_prepared_sanitized_report_publishes_provenance_and_supersession(self) -> None:
        """Prepared v1 provenance is read back without rewriting the old snapshot."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            subprocess.run(["git", "init", "-b", "main", str(source)], check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/test/source.git"],
                cwd=source,
                check=True,
            )
            report = source / "reports" / "agents" / "run-1"
            report.mkdir(parents=True)
            original = report / "summary.md"
            original.write_text("summary\n", encoding="utf-8")
            subprocess.run(["git", "add", "reports"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-m", "source"], cwd=source, check=True, capture_output=True)

            ensured = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensured.returncode, 0, ensured.stdout + ensured.stderr)
            old_archive = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(report),
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(old_archive.returncode, 0, old_archive.stdout + old_archive.stderr)
            old_snapshot = next(
                line.split("=", 1)[1]
                for line in old_archive.stdout.splitlines()
                if line.startswith("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT=")
            )
            pushed_old = self.run_tool(
                "push",
                "--message",
                "Archive unsafe report",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed_old.returncode, 0, pushed_old.stdout + pushed_old.stderr)
            archive = mounted_log_archive_root(canon, self.runtime_root(root))
            old_commit = subprocess.check_output(["git", "-C", str(archive), "rev-parse", "HEAD"], text=True).strip()
            old_tree = subprocess.check_output(["git", "-C", str(archive), "rev-parse", "HEAD^{tree}"], text=True).strip()
            key = repo_log_key(source)
            index_rel = f"agent-reports/{key}/index.jsonl"
            old_index_blob = subprocess.check_output(
                ["git", "-C", str(archive), "rev-parse", f"HEAD:{index_rel}"], text=True
            ).strip()
            old_index = json.loads((archive / index_rel).read_text(encoding="utf-8").splitlines()[0])

            prepared = root / "prepared" / "run-1"
            prepared.mkdir(parents=True)
            sanitized = prepared / "summary.md"
            sanitized.write_text("summary\n", encoding="utf-8")
            source_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            source_prefix = "reports/agents/run-1"
            tree_listing = subprocess.check_output(
                ["git", "-C", str(source), "ls-tree", "-r", "-z", source_commit, "--", source_prefix]
            )
            source_tree = hashlib.sha256(tree_listing).hexdigest()
            source_sha = hashlib.sha256(original.read_bytes()).hexdigest()
            archive_sha = hashlib.sha256(sanitized.read_bytes()).hexdigest()
            supersession = {
                "status": "superseded",
                "quarantine_status": "quarantined",
                "superseded_snapshot_id": old_snapshot,
                "superseded_archive_ref": f"refs/heads/{self.expected_branch(source)}",
                "superseded_archive_commit": old_commit,
                "superseded_archive_tree": old_tree,
                "superseded_index_blob": old_index_blob,
                "superseded_destination_prefix": old_index["destination"],
                "reason": "prepared sanitization replaces an unsafe historical snapshot",
            }
            snapshot_payload = {
                "source_commit": source_commit,
                "source_tree_digest_sha256": source_tree,
                "files": [{"archive_sha256": archive_sha, "relative_path": "summary.md", "size": len(sanitized.read_bytes())}],
                "redaction_count": 0,
            }
            provenance = {
                "archive_schema": "agent-report-snapshot.v1",
                "files": [{
                    "archive_sha256": archive_sha,
                    "redactions": [],
                    "redaction_count": 0,
                    "redaction_rule_ids": [],
                    "redaction_rule_counts": {},
                    "relative_path": "summary.md",
                    "size": len(sanitized.read_bytes()),
                    "source_path": f"{source_prefix}/summary.md",
                    "source_sha256": source_sha,
                }],
                "redaction_count": 0,
                "redaction_policy": {
                    "credential_shaped_values": "replace with REDACTED_SECRET_SHA256_<sha256>",
                    "direct_local_paths": "replace with REDACTED_PATH_SHA256_<sha256>",
                    "source_value_retention": "never",
                },
                "redaction_rule_counts": {},
                "run_id": "run-1",
                "schema": "agent-canon-log-report-provenance.v1",
                "snapshot_id": hashlib.sha256(json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "source_branch": "main",
                "source_commit": source_commit,
                "source_file_count": 1,
                "source_normalized_remote": "github.com/test/source",
                "source_prefix": source_prefix,
                "source_remote": "https://github.com/test/source.git",
                "source_stable_id": key,
                "source_tree_digest_sha256": source_tree,
                "supersession": supersession,
            }
            provenance_path = root / "prepared" / "provenance.json"
            provenance_path.write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")
            published = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(prepared),
                "--provenance",
                str(provenance_path),
                "--publish",
                "--message",
                "Archive sanitized report",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(published.returncode, 0, published.stdout + published.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_PROVENANCE=pass", published.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass", published.stdout)
            index_lines = (archive / index_rel).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(index_lines), 2)
            successor = json.loads(index_lines[-1])
            self.assertEqual(successor["schema"], "agent-canon-log-report-provenance.v1")
            self.assertEqual(successor["snapshot_schema"], "agent-report-snapshot.v1")
            self.assertEqual(successor["supersession"]["quarantine_status"], "quarantined")
            self.assertEqual(successor["supersedes"], successor["supersession"])
            self.assertEqual(successor["quarantines"], successor["supersession"])
            self.assertEqual(successor["files"][0]["archive_sha256"], archive_sha)
            replay = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(prepared),
                "--provenance",
                str(provenance_path),
                "--publish",
                "--message",
                "Replay sanitized report",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED=no", replay.stdout)
            self.assertEqual(len((archive / index_rel).read_text(encoding="utf-8").splitlines()), 2)

    def test_materialize_runtime_event_cli_rejects_decision_and_raw_path_inputs(self) -> None:
        """The public parser exposes only fixed family and source selectors."""
        parser = runtime_log_archive_git.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "materialize-runtime-event",
                    "--result-family",
                    "review",
                    "--run-id",
                    "run-1",
                    "--gate-id",
                    "change-review",
                    "--base-ref",
                    "main",
                    "--decision",
                    "APPROVE",
                    "--raw-path",
                    "rollout.jsonl",
                ]
            )

    def test_materialize_runtime_event_binds_rollout_path_bytes_offsets_and_ids(self) -> None:
        """Context discovery returns exact path, byte range, and structural joins."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root),
                },
                clear=False,
            ):
                identity = runtime_log_archive_git.discover_rollout_context(
                    fixture.context_id,
                    fixture.turn_id,
                )
                self.assertEqual(
                    runtime_log_archive_git.command_materialize_runtime_event(
                        fixture.context, fixture.args
                    ),
                    0,
                )
            record = runtime_log_archive_git._readback_runtime_event(fixture.target)
            source_event = record["source_event"]
            self.assertIsInstance(source_event, dict)
            source_event = source_event
            self.assertEqual(identity["rollout_path"], fixture.rollout.resolve().as_posix())
            task_complete = cast(dict[str, object], identity["task_complete"])
            self.assertEqual(task_complete["line"], 872)
            self.assertEqual(task_complete["byte_length"], len(fixture.raw_record))
            self.assertEqual(
                task_complete["byte_offset"],
                sum(
                    len(item)
                    for item in fixture.rollout.read_bytes().splitlines(keepends=True)[:871]
                ),
            )
            self.assertEqual(
                task_complete["record_sha256"], hashlib.sha256(fixture.raw_record).hexdigest()
            )
            self.assertEqual(source_event["record_bytes_b64"], identity["record_bytes_b64"])
            self.assertEqual(source_event["record_byte_offset"], task_complete["byte_offset"])
            self.assertEqual(source_event["agent_id"], fixture.context_id)
            self.assertEqual(source_event["parent_id"], "44444444-4444-4444-8444-444444444444")

    def test_context_discovery_certificate_is_canonical_and_idempotent(self) -> None:
        """The native producer publishes one hash-bound certificate and retries safely."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            certificate = next(fixture.result_path.parent.glob("context_discovery.*.json"))
            first_bytes = certificate.read_bytes()
            value = json.loads(first_bytes)
            self.assertEqual(
                certificate.name,
                f"context_discovery.{value['certificate_id']}.json",
            )
            runtime_log_archive_git.validate_context_discovery_certificate(first_bytes)
            self.assertEqual(value["rollout"]["task_complete"]["line"], 872)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {"AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root)},
                    clear=False,
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(
                    runtime_log_archive_git.main(
                        [
                            "--source-root",
                            str(fixture.source),
                            "--canon-root",
                            str(fixture.source),
                            "--archive-root",
                            str(fixture.context.archive_root),
                            "--runtime-root",
                            str(fixture.context.runtime_root),
                            "append-context-discovery",
                            "--run-id",
                            fixture.args.run_id,
                            "--agent-context-id",
                            fixture.context_id,
                            "--turn-id",
                            fixture.turn_id,
                        ]
                    ),
                    0,
                )
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(certificate.read_bytes(), first_bytes)

    def test_context_discovery_producer_rejects_symlinked_rollout_outside_session_root(
        self,
    ) -> None:
        """An outside-root JSONL reached through a symlink cannot be certified."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            certificate = next(
                fixture.result_path.parent.glob("context_discovery.*.json")
            )
            certificate.unlink()
            outside = Path(tmp_dir) / "outside" / fixture.rollout.name
            outside.parent.mkdir()
            outside.write_bytes(fixture.rollout.read_bytes())
            fixture.rollout.unlink()
            fixture.rollout.symlink_to(outside)

            self.assert_producer_failure(fixture, "context_source_absent")
            self.assertEqual(
                tuple(fixture.result_path.parent.glob("context_discovery.*.json")),
                (),
            )

    def test_context_discovery_does_not_use_host_codex_session_fallback(self) -> None:
        """Host Codex state cannot satisfy an omitted runtime-owner root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            host_home = Path(tmp_dir) / "host-home"
            host_session_root = host_home / ".codex" / "sessions"
            host_session_root.mkdir(parents=True)
            (host_session_root / fixture.rollout.name).write_bytes(
                fixture.rollout.read_bytes()
            )
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_CODEX_SESSION_ROOT": "",
                    "CODEX_HOME": str(host_home / ".codex"),
                    "HOME": str(host_home),
                },
                clear=False,
            ):
                with self.assertRaises(
                    runtime_log_archive_git.RuntimeEventMaterializationError
                ) as raised:
                    runtime_log_archive_git.discover_rollout_context(
                        fixture.context_id, fixture.turn_id
                    )
            self.assertEqual(raised.exception.code, "context_source_absent")

    def test_context_discovery_producer_rejects_invalid_native_evidence_cardinality(
        self,
    ) -> None:
        """C-04 rejects absent, duplicate, and malformed native evidence."""
        cases = (
            ("rollout_absent", "context_source_absent"),
            ("rollout_ambiguous", "context_source_ambiguous"),
            ("session_meta_absent", "context_source_absent"),
            ("session_meta_duplicate", "context_source_ambiguous"),
            ("task_complete_absent", "source_identity_mismatch"),
            ("task_complete_duplicate", "context_source_ambiguous"),
            ("malformed_structural_join", "source_identity_mismatch"),
        )
        for case, expected_code in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp_dir:
                fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
                certificate = next(
                    fixture.result_path.parent.glob("context_discovery.*.json")
                )
                certificate.unlink()
                if case == "rollout_absent":
                    fixture.rollout.unlink()
                elif case == "rollout_ambiguous":
                    duplicate = fixture.rollout.with_name(
                        "rollout-2026-07-17T12-00-01.123Z-"
                        f"{fixture.context_id}.jsonl"
                    )
                    duplicate.write_bytes(fixture.rollout.read_bytes())
                else:
                    lines = fixture.rollout.read_bytes().splitlines(keepends=True)
                    if case == "session_meta_absent":
                        del lines[870]
                    elif case == "session_meta_duplicate":
                        lines.insert(871, lines[870])
                    elif case == "task_complete_absent":
                        del lines[871]
                    elif case == "task_complete_duplicate":
                        lines.append(lines[871])
                    else:
                        session_meta = json.loads(lines[870])
                        session_meta["payload"]["source"]["subagent"]["thread_spawn"][
                            "parent_thread_id"
                        ] = "33333333-3333-4333-8333-333333333333"
                        lines[870] = (
                            json.dumps(session_meta, separators=(",", ":")) + "\n"
                        ).encode("utf-8")
                    fixture.rollout.write_bytes(b"".join(lines))

                self.assert_producer_failure(fixture, expected_code)
                self.assertEqual(
                    tuple(fixture.result_path.parent.glob("context_discovery.*.json")),
                    (),
                )

    def test_context_discovery_producer_no_replace_collision_and_failure(
        self,
    ) -> None:
        """C-03 preserves existing bytes and fails before a replacement is visible."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            collision = self.make_valid_materialization_fixture(
                Path(tmp_dir) / "collision"
            )
            collision_target = next(
                collision.result_path.parent.glob("context_discovery.*.json")
            )
            conflicting_bytes = b"existing collision bytes\n"
            collision_target.write_bytes(conflicting_bytes)

            self.assert_producer_failure(collision, "context_record_collision")
            self.assertEqual(collision_target.read_bytes(), conflicting_bytes)

            publication_failure = self.make_valid_materialization_fixture(
                Path(tmp_dir) / "publication-failure"
            )
            publication_target = next(
                publication_failure.result_path.parent.glob(
                    "context_discovery.*.json"
                )
            )
            publication_target.unlink()
            with patch.object(
                runtime_log_archive_git,
                "_renameat2_noreplace_at",
                side_effect=OSError("forced publication failure"),
            ):
                self.assert_producer_failure(
                    publication_failure, "context_publication_failure"
                )
            self.assertFalse(publication_target.exists())
            self.assertEqual(
                tuple(
                    publication_failure.result_path.parent.glob(
                        f".{publication_target.name}.*.tmp"
                    )
                ),
                (),
            )

    def test_materialize_runtime_event_requires_exactly_one_context_certificate(self) -> None:
        """The materializer rejects absent and ambiguous certificate handoffs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            absent = self.make_valid_materialization_fixture(Path(tmp_dir) / "absent")
            certificate = next(absent.result_path.parent.glob("context_discovery.*.json"))
            certificate.unlink()
            self.assert_materializer_failure(absent, "context_source_absent")

            ambiguous = self.make_valid_materialization_fixture(Path(tmp_dir) / "ambiguous")
            certificate = next(ambiguous.result_path.parent.glob("context_discovery.*.json"))
            duplicate = certificate.with_name(
                "context_discovery." + "f" * 64 + ".json"
            )
            duplicate.write_bytes(certificate.read_bytes())
            self.assert_materializer_failure(ambiguous, "context_source_ambiguous")

    def test_materialize_runtime_event_uses_one_immutable_rollout_snapshot(self) -> None:
        """V-02 binds discovery, selected bytes, offsets, and hashes to one read."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            original_read_bytes = Path.read_bytes
            original_snapshot = original_read_bytes(fixture.rollout)
            mutated_lines = original_snapshot.splitlines(keepends=True)
            mutated_lines[871] = (
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "turn_id": "66666666-6666-4666-8666-666666666666"
                        },
                    },
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            mutated_snapshot = b"".join(mutated_lines)
            mutation_applied = False

            def mutate_after_rollout_snapshot(path: Path) -> bytes:
                """Mutate the live rollout only after returning its first snapshot."""
                nonlocal mutation_applied
                snapshot = original_read_bytes(path)
                if path == fixture.rollout and not mutation_applied:
                    mutation_applied = True
                    fixture.rollout.write_bytes(mutated_snapshot)
                return snapshot

            with (
                patch.dict(
                    os.environ,
                    {
                        "AGENT_CANON_CODEX_SESSION_ROOT": str(
                            fixture.session_root
                        )
                    },
                    clear=False,
                ),
                patch.object(
                    Path,
                    "read_bytes",
                    new=mutate_after_rollout_snapshot,
                ),
            ):
                identity = runtime_log_archive_git.discover_rollout_context(
                    fixture.context_id,
                    fixture.turn_id,
                )

            self.assertTrue(mutation_applied)
            self.assertEqual(fixture.rollout.read_bytes(), mutated_snapshot)
            self.assertEqual(
                identity["rollout_file_sha256"],
                hashlib.sha256(original_snapshot).hexdigest(),
            )
            self.assertEqual(
                identity["rollout_path_sha256"],
                hashlib.sha256(
                    fixture.rollout.resolve().as_posix().encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(
                base64.b64decode(cast(str, identity["record_bytes_b64"])),
                fixture.raw_record,
            )
            self.assertEqual(
                cast(dict[str, object], identity["task_complete"])["byte_offset"],
                sum(
                    len(line)
                    for line in original_snapshot.splitlines(keepends=True)[:871]
                ),
            )

    def test_materialize_runtime_event_uses_fixed_result_family_specs(self) -> None:
        """All five result families have one fixed artifact and gate schema."""
        expected = {
            "requirements": ("requirements_review.md", "requirements-review", "ReviewArtifactV1"),
            "design": ("design_review.md", "design-review", "ReviewArtifactV1"),
            "review": ("change_review.md", "change-review", "ReviewArtifactV1"),
            "validation": ("validation_result.json", "validation", "agent_canon.runtime_result_input.v1"),
            "lifecycle": ("closeout_gate.md", "closeout", "CloseoutGateV1"),
        }
        self.assertEqual(tuple(item.result_family for item in runtime_log_archive_git.RESULT_FAMILY_SPECS), tuple(expected))
        for family, (artifact, gate, schema) in expected.items():
            spec = runtime_log_archive_git.fixed_result_family_spec(family, gate)
            self.assertEqual((spec.artifact_name, spec.gate_id, spec.schema), (artifact, gate, schema))
        with self.assertRaises(runtime_log_archive_git.RuntimeEventMaterializationError):
            runtime_log_archive_git.fixed_result_family_spec("review", "requirements-review")

    def test_materialize_runtime_event_rejects_nested_validation_duplicate_keys(self) -> None:
        """V-03 rejects duplicate keys at nested validation-object depth."""
        raw = (
            b'{"schema":"agent_canon.runtime_result_input.v1",'
            b'"result":"PASS","gate_id":"validation",'
            b'"target_paths":["tools/target.py"],"base_ref":"main",'
            b'"observations":{"head_oid":"1111111111111111111111111111111111111111",'
            b'"head_oid":"2222222222222222222222222222222222222222",'
            b'"base_oid":"3333333333333333333333333333333333333333"}}\n'
        )
        with self.assertRaises(
            runtime_log_archive_git.RuntimeEventMaterializationError
        ) as raised:
            runtime_log_archive_git.parse_validation_result(raw, "validation")
        self.assertEqual(raised.exception.code, "result_authority_mismatch")

    def test_materialize_runtime_event_lifecycle_fields_are_section_bounded(self) -> None:
        """V-03 accepts one readiness section and rejects every authority impostor."""
        valid = (
            "# Closeout\n\n"
            "## Completion Readiness\n"
            "status: READY\n"
            "closeout_gate_id: closeout\n"
            "target_paths: tools/target.py, reports/evidence.json\n"
            "base_ref: main\n"
            "evidence_path: reports/evidence.json\n"
            f"evidence_sha256: {'a' * 64}\n\n"
            "## References\n"
            "terminal prose\n"
        )
        parsed = runtime_log_archive_git.parse_lifecycle_result(valid, "closeout")
        self.assertEqual(parsed["gate_result"], "READY")

        invalid_documents = (
            valid + "\n## Completion Readiness\n",
            valid.replace("status: READY\n", "status: READY\nstatus: BLOCKED\n"),
            "status: BLOCKED\n" + valid,
            valid.replace("base_ref: main\n", ""),
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(
                    runtime_log_archive_git.RuntimeEventMaterializationError
                ) as raised:
                    runtime_log_archive_git.parse_lifecycle_result(
                        document, "closeout"
                    )
                self.assertEqual(
                    raised.exception.code, "result_authority_mismatch"
                )

    def test_materialize_runtime_event_derives_target_blob_and_base_identities(self) -> None:
        """Target identity verification is bound to external Git object identities."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root),
                },
                clear=False,
            ):
                runtime_log_archive_git.command_materialize_runtime_event(
                    fixture.context, fixture.args
                )
            value = json.loads(fixture.target.read_text(encoding="utf-8"))
            identity = value["target_identities"][0]
            current_blob = subprocess.run(
                ["git", "-C", str(fixture.source), "hash-object", "--", fixture.target_relative],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            base_blob = subprocess.run(
                ["git", "-C", str(fixture.source), "rev-parse", f"{fixture.base_oid}:{fixture.target_relative}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            artifact_blob = subprocess.run(
                [
                    "git",
                    "-C",
                    str(fixture.source),
                    "hash-object",
                    "--",
                    fixture.result_path.relative_to(fixture.source).as_posix(),
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(identity["path"], fixture.target_relative)
            self.assertEqual(identity["content_sha256"], hashlib.sha256((fixture.source / fixture.target_relative).read_bytes()).hexdigest())
            self.assertEqual(identity["git_blob_oid"], current_blob)
            self.assertTrue(identity["base_present"])
            self.assertEqual(identity["base_content_sha256"], hashlib.sha256(b"base target\n").hexdigest())
            self.assertEqual(identity["base_git_blob_oid"], base_blob)
            self.assertEqual(value["result_artifact"]["artifact_blob_oid"], artifact_blob)
            self.assertEqual(value["result_artifact"]["base_oid"], fixture.base_oid)
            self.assertEqual(value["source_snapshot"]["head_oid"], fixture.head_oid)
            self.assertEqual(value["source_snapshot"]["base_oid"], fixture.base_oid)
            self.assertEqual(value["result_artifact"]["target_paths"], [fixture.target_relative])

    def test_materialize_runtime_event_preserves_porcelain_columns_and_exclusions(self) -> None:
        """Status capture preserves X/Y and excludes generated source roots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "tracked.txt").write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "-qm", "init"], check=True)
            (root / "tracked.txt").write_text("new\n", encoding="utf-8")
            (root / "reports" / "agent-runtime-dashboard").mkdir(parents=True)
            (root / "reports" / "agent-runtime-dashboard" / "generated.md").write_text("generated\n", encoding="utf-8")
            statuses = runtime_log_archive_git.capture_porcelain_v1(root)
            self.assertTrue(any(item["status_x"] == " " and item["status_y"] == "M" for item in statuses))
            self.assertEqual(runtime_log_archive_git.parse_porcelain_v1_line("AM tracked.txt")["status_x"], "A")
            self.assertFalse(runtime_log_archive_git.is_source_snapshot_path(Path("reports/agent-runtime-dashboard/generated.md")))

    def test_materialize_runtime_event_noreplace_collision_and_identical_readback(self) -> None:
        """V-08 binds canonical collisions, lock exclusion, and exact retry."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            def successful_bytes(
                fixture: RuntimeMaterializationFixture,
            ) -> dict[Path, bytes]:
                """Return every immutable publication byte string for a fixture."""
                attempt_id = cast(
                    str,
                    json.loads(fixture.target.read_text(encoding="utf-8"))[
                        "publication_intent"
                    ]["attempt_id"],
                )
                paths = [fixture.target]
                paths.extend(
                    sorted(
                        path
                        for path in self.observation_directory(
                            fixture, attempt_id
                        ).iterdir()
                        if path.name != ".attempt.lock"
                    )
                )
                paths.extend(sorted(fixture.target.parent.glob(f"{fixture.target.stem}.outcome.*")))
                return {path: path.read_bytes() for path in paths}

            def assert_success(fixture: RuntimeMaterializationFixture) -> str:
                """Run one successful public materialization and return its attempt."""
                result, stdout, stderr = self.invoke_materializer(fixture)
                self.assertEqual(result, 0, stdout + stderr)
                self.assertEqual(stderr, "")
                self.assertEqual(stdout.splitlines()[-2:], [
                    "RUNTIME_EVENT_OUTCOME=committed",
                    "RUNTIME_EVENT_MATERIALIZE=pass",
                ])
                value = json.loads(fixture.target.read_text(encoding="utf-8"))
                return cast(str, value["publication_intent"]["attempt_id"])

            def fail_artifact_rename(
                fixture: RuntimeMaterializationFixture,
            ) -> object:
                """Return an OS-boundary replacement that fails only artifact rename."""
                original = runtime_log_archive_git._renameat2_noreplace_at

                def injected(source: str, target: str, directory_fd: int) -> None:
                    if target == fixture.target.name:
                        raise OSError(5, "injected artifact rename failure")
                    original(source, target, directory_fd)

                return patch.object(
                    runtime_log_archive_git,
                    "_renameat2_noreplace_at",
                    side_effect=injected,
                )

            internal_failure = self.make_valid_materialization_fixture(
                root / "internal-failure"
            )
            with fail_artifact_rename(internal_failure):
                self.assert_materializer_failure(
                    internal_failure, "publication_failure"
                )
            self.assertFalse(internal_failure.target.exists())
            assert_success(internal_failure)
            replay_before = successful_bytes(internal_failure)
            assert_success(internal_failure)
            self.assertEqual(successful_bytes(internal_failure), replay_before)

            collision = self.make_valid_materialization_fixture(root / "collision")
            collision.target.write_bytes(b"different bytes\n")
            self.assert_materializer_failure(collision, "record_collision")
            self.assertEqual(collision.target.read_bytes(), b"different bytes\n")

            malformed_artifact = self.make_valid_materialization_fixture(
                root / "malformed-artifact"
            )
            assert_success(malformed_artifact)
            malformed_value = json.loads(
                malformed_artifact.target.read_text(encoding="utf-8")
            )
            malformed_value["publication_intent"]["prepared_state"] = "published"
            malformed_artifact.target.write_text(
                json.dumps(malformed_value, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.assert_materializer_failure(malformed_artifact, "schema_invalid")

            mismatched_readback = self.make_valid_materialization_fixture(
                root / "mismatched-readback"
            )
            original_secure_readback = runtime_log_archive_git._read_secure_publication_target
            mismatch_injected = False

            def mismatch_after_artifact_rename(
                context: object, target_name: str
            ) -> bytes | None:
                """Return proven wrong bytes for the first committed-target readback."""
                nonlocal mismatch_injected
                value = original_secure_readback(context, target_name)
                if (
                    target_name == mismatched_readback.target.name
                    and value is not None
                    and not mismatch_injected
                ):
                    mismatch_injected = True
                    return b"{}\n"
                return value

            with patch.object(
                runtime_log_archive_git,
                "_read_secure_publication_target",
                new=mismatch_after_artifact_rename,
            ):
                self.assert_materializer_failure(
                    mismatched_readback, "publication_observation_invalid"
                )
            self.assertTrue(mismatch_injected)
            self.assertTrue(mismatched_readback.target.is_file())
            mismatched_attempt = cast(
                str,
                json.loads(mismatched_readback.target.read_text(encoding="utf-8"))[
                    "publication_intent"
                ]["attempt_id"],
            )
            self.assertEqual(
                [
                    path
                    for path in self.observation_directory(
                        mismatched_readback, mismatched_attempt
                    ).iterdir()
                    if path.name != ".attempt.lock"
                ],
                [],
            )
            self.assertEqual(
                list(
                    mismatched_readback.target.parent.glob(
                        f"{mismatched_readback.target.stem}.outcome.*"
                    )
                ),
                [],
            )

            observation_failure = self.make_valid_materialization_fixture(
                root / "observation-failure"
            )
            original_open = os.open

            def fail_observation_temp(
                path: str | bytes,
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                directory = (
                    Path(os.readlink(f"/proc/self/fd/{dir_fd}"))
                    if dir_fd is not None
                    else Path()
                )
                if (
                    dir_fd is not None
                    and flags & os.O_CREAT
                    and directory.parent.name == "publication-outcome"
                ):
                    raise OSError(5, "injected observation temp failure")
                return original_open(path, flags, mode, dir_fd=dir_fd)

            with patch.object(
                os,
                "open",
                side_effect=fail_observation_temp,
            ):
                self.assert_materializer_failure(
                    observation_failure, "publication_observation_failed"
                )
            self.assertTrue(observation_failure.target.is_file())
            observation_attempt = cast(
                str,
                json.loads(observation_failure.target.read_text(encoding="utf-8"))[
                    "publication_intent"
                ]["attempt_id"],
            )
            self.assertEqual(
                [
                    path
                    for path in self.observation_directory(
                        observation_failure, observation_attempt
                    ).iterdir()
                    if path.name != ".attempt.lock"
                ],
                [],
            )
            assert_success(observation_failure)
            recovered_observations = sorted(
                path
                for path in self.observation_directory(
                    observation_failure, observation_attempt
                ).iterdir()
                if path.name != ".attempt.lock"
            )
            self.assertEqual(len(recovered_observations), 2)
            self.assertTrue(
                json.loads(recovered_observations[0].read_text(encoding="utf-8"))[
                    "evidence"
                ]["causal_gap"]
            )

            observation_uncertain = self.make_valid_materialization_fixture(
                root / "observation-uncertain"
            )
            original_fsync = runtime_log_archive_git._fsync_directory

            def fail_observation_parent(path: Path, purpose: str) -> None:
                if purpose == "observation-parent":
                    raise OSError(5, "injected observation parent fsync failure")
                original_fsync(path, purpose)

            with patch.object(
                runtime_log_archive_git,
                "_fsync_directory",
                side_effect=fail_observation_parent,
            ):
                self.assert_materializer_failure(
                    observation_uncertain, "publication_observation_uncertain"
                )
            uncertain_attempt = cast(
                str,
                json.loads(observation_uncertain.target.read_text(encoding="utf-8"))[
                    "publication_intent"
                ]["attempt_id"],
            )
            uncertain_candidates = [
                path
                for path in self.observation_directory(
                    observation_uncertain, uncertain_attempt
                ).iterdir()
                if path.name != ".attempt.lock"
            ]
            self.assertEqual(len(uncertain_candidates), 1)
            uncertain_bytes = uncertain_candidates[0].read_bytes()
            self.assertEqual(
                list(observation_uncertain.target.parent.glob(f"{observation_uncertain.target.stem}.outcome.*")),
                [],
            )
            assert_success(observation_uncertain)
            self.assertEqual(uncertain_candidates[0].read_bytes(), uncertain_bytes)

            observation_collision = self.make_valid_materialization_fixture(
                root / "observation-collision"
            )
            original_rename = runtime_log_archive_git._renameat2_noreplace_at

            def collide_observation(source: str, target: str, directory_fd: int) -> None:
                if runtime_log_archive_git.RUNTIME_EVENT_OBSERVATION_NAME.fullmatch(
                    target
                ):
                    descriptor = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                        0o600,
                        dir_fd=directory_fd,
                    )
                    try:
                        os.write(descriptor, b"different observation bytes\n")
                    finally:
                        os.close(descriptor)
                original_rename(source, target, directory_fd)

            with patch.object(
                runtime_log_archive_git,
                "_renameat2_noreplace_at",
                side_effect=collide_observation,
            ):
                self.assert_materializer_failure(
                    observation_collision, "publication_observation_collision"
                )

            malformed_observation = self.make_valid_materialization_fixture(
                root / "malformed-observation"
            )
            with patch.object(
                runtime_log_archive_git,
                "_fsync_directory",
                side_effect=fail_observation_parent,
            ):
                self.assert_materializer_failure(
                    malformed_observation, "publication_observation_uncertain"
                )
            malformed_observation_attempt = cast(
                str,
                json.loads(
                    malformed_observation.target.read_text(encoding="utf-8")
                )["publication_intent"]["attempt_id"],
            )
            malformed_observation_paths = [
                path
                for path in self.observation_directory(
                    malformed_observation, malformed_observation_attempt
                ).iterdir()
                if path.name != ".attempt.lock"
            ]
            self.assertEqual(len(malformed_observation_paths), 1)
            self.assertEqual(
                list(
                    malformed_observation.target.parent.glob(
                        f"{malformed_observation.target.stem}.outcome.*"
                    )
                ),
                [],
            )
            malformed_observation_path = malformed_observation_paths[0]
            malformed_observation_path.write_bytes(b"{}\n")
            self.assert_materializer_failure(
                malformed_observation, "publication_observation_invalid"
            )
            self.assertEqual(
                list(
                    malformed_observation.target.parent.glob(
                        f"{malformed_observation.target.stem}.outcome.*"
                    )
                ),
                [],
            )

            receipt_collision = self.make_valid_materialization_fixture(
                root / "receipt-collision"
            )

            def collide_receipt(source: str, target: str, directory_fd: int) -> None:
                if runtime_log_archive_git.RUNTIME_EVENT_RECEIPT_NAME.fullmatch(
                    target
                ):
                    descriptor = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                        0o600,
                        dir_fd=directory_fd,
                    )
                    try:
                        os.write(descriptor, b"different receipt bytes\n")
                    finally:
                        os.close(descriptor)
                original_rename(source, target, directory_fd)

            with patch.object(
                runtime_log_archive_git,
                "_renameat2_noreplace_at",
                side_effect=collide_receipt,
            ):
                self.assert_materializer_failure(
                    receipt_collision, "publication_receipt_collision"
                )

            receipt_without_observation = self.make_valid_materialization_fixture(
                root / "receipt-without-observation"
            )
            receipt_without_attempt = assert_success(receipt_without_observation)
            for path in self.observation_directory(
                receipt_without_observation, receipt_without_attempt
            ).iterdir():
                if path.name != ".attempt.lock":
                    path.unlink()
            self.assert_materializer_failure(
                receipt_without_observation, "publication_receipt_invalid"
            )

            forged_receipt = self.make_valid_materialization_fixture(
                root / "forged-receipt"
            )
            assert_success(forged_receipt)
            forged_path = next(
                forged_receipt.target.parent.glob(
                    f"{forged_receipt.target.stem}.outcome.*.000001.json"
                )
            )
            forged = json.loads(forged_path.read_text(encoding="utf-8"))
            forged_observation = forged["observation"]
            forged_observation["evidence"][
                "target_directory_fsync_status"
            ] = "failed"
            forged_observation["outcome"] = "committed"
            forged_observation["observation_sha256"] = "0" * 64
            forged_observation["observation_sha256"] = hashlib.sha256(
                (
                    json.dumps(forged_observation, separators=(",", ":"))
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            forged["receipt_sha256"] = "0" * 64
            forged["receipt_sha256"] = hashlib.sha256(
                (json.dumps(forged, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            ).hexdigest()
            forged_path.write_text(
                json.dumps(forged, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.assert_materializer_failure(
                forged_receipt, "publication_receipt_invalid"
            )

            skipped_receipt = self.make_valid_materialization_fixture(
                root / "skipped-receipt"
            )
            skipped_attempt = assert_success(skipped_receipt)
            first_receipt = next(
                skipped_receipt.target.parent.glob(
                    f"{skipped_receipt.target.stem}.outcome.{skipped_attempt}.000001.json"
                )
            )
            skipped_receipt.target.with_name(
                f"{skipped_receipt.target.stem}.outcome.{skipped_attempt}.000003.json"
            ).write_bytes(first_receipt.read_bytes())
            self.assert_materializer_failure(
                skipped_receipt, "publication_receipt_invalid"
            )

            duplicate_observation = self.make_valid_materialization_fixture(
                root / "duplicate-observation"
            )
            duplicate_attempt = assert_success(duplicate_observation)
            first_observation_path = next(
                path
                for path in self.observation_directory(
                    duplicate_observation, duplicate_attempt
                ).iterdir()
                if path.name != ".attempt.lock"
            )
            duplicate_value = json.loads(
                first_observation_path.read_text(encoding="utf-8")
            )
            duplicate_value["outcome"] = "uncertain"
            duplicate_value["evidence"][
                "target_directory_fsync_status"
            ] = "failed"
            duplicate_value["observation_sha256"] = "0" * 64
            duplicate_value["observation_sha256"] = hashlib.sha256(
                (
                    json.dumps(duplicate_value, separators=(",", ":"))
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            duplicate_path = first_observation_path.with_name(
                f"000001-{duplicate_value['observation_sha256']}.json"
            )
            duplicate_path.write_text(
                json.dumps(duplicate_value, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.assert_materializer_failure(
                duplicate_observation, "publication_attempt_collision"
            )

            busy = self.make_valid_materialization_fixture(root / "busy")
            with fail_artifact_rename(busy):
                self.assert_materializer_failure(busy, "publication_failure")
            publication_root = runtime_event_publication_outcome_spool_root(
                busy.source, busy.context.runtime_root
            )
            busy_attempt_directory = next(
                path for path in publication_root.iterdir() if path.is_dir()
            )
            busy_lock = busy_attempt_directory / ".attempt.lock"
            descriptor = os.open(busy_lock, os.O_RDWR)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assert_materializer_failure(busy, "publication_attempt_busy")
                self.assertFalse(busy.target.exists())
                self.assertEqual(
                    [
                        path
                        for path in busy_attempt_directory.iterdir()
                        if path.name != ".attempt.lock"
                    ],
                    [],
                )
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
            assert_success(busy)

            invalid_lock = self.make_valid_materialization_fixture(
                root / "invalid-lock"
            )
            with fail_artifact_rename(invalid_lock):
                self.assert_materializer_failure(
                    invalid_lock, "publication_failure"
                )
            invalid_root = runtime_event_publication_outcome_spool_root(
                invalid_lock.source, invalid_lock.context.runtime_root
            )
            invalid_attempt_directory = next(
                path for path in invalid_root.iterdir() if path.is_dir()
            )
            # Read-only group/other access is valid; make the fixture
            # invalid by granting group write access instead.
            os.chmod(invalid_attempt_directory / ".attempt.lock", 0o664)
            self.assert_materializer_failure(
                invalid_lock, "publication_attempt_lock_invalid"
            )
            self.assertFalse(invalid_lock.target.exists())

    def test_materialize_runtime_event_pre_rename_failure_preserves_old_state(self) -> None:
        """A source failure before publication leaves no new record."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            fixture.old_state.write_bytes(b"old-state\n")
            with (
                patch.dict(
                    os.environ,
                    {
                        "AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root),
                    },
                    clear=False,
                ),
                patch.object(
                    runtime_log_archive_git,
                    "_renameat2_noreplace_at",
                    side_effect=OSError(5, "injected pre-rename failure"),
                ),
            ):
                with self.assertRaises(runtime_log_archive_git.RuntimeEventMaterializationError) as raised:
                    runtime_log_archive_git.command_materialize_runtime_event(
                        fixture.context, fixture.args
                    )
            self.assertEqual(raised.exception.code, "publication_failure")
            self.assertFalse(fixture.target.exists())
            self.assertEqual(fixture.old_state.read_bytes(), b"old-state\n")

    def test_materialize_runtime_event_post_rename_fsync_is_uncertain_not_success(self) -> None:
        """V-07 appends uncertainty, then recovers without rewriting history."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = self.make_valid_materialization_fixture(Path(tmp_dir))
            original_fsync = runtime_log_archive_git._fsync_directory
            original_rename = runtime_log_archive_git._renameat2_noreplace_at

            def fail_artifact_parent(path: Path, purpose: str) -> None:
                if purpose == "artifact-parent":
                    raise OSError(5, "injected artifact parent fsync failure")
                original_fsync(path, purpose)

            def fail_sequence_one_receipt(source: str, target: str, directory_fd: int) -> None:
                match = runtime_log_archive_git.RUNTIME_EVENT_RECEIPT_NAME.fullmatch(
                    target
                )
                if match is not None and match.group("sequence") == "000001":
                    raise OSError(5, "injected sequence-one receipt rename failure")
                original_rename(source, target, directory_fd)

            first_stdout = io.StringIO()
            first_stderr = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {
                        "AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root),
                    },
                    clear=False,
                ),
                patch.object(
                    runtime_log_archive_git,
                    "_fsync_directory",
                    side_effect=fail_artifact_parent,
                ),
                patch.object(
                    runtime_log_archive_git,
                    "_renameat2_noreplace_at",
                    side_effect=fail_sequence_one_receipt,
                ),
                contextlib.redirect_stdout(first_stdout),
                contextlib.redirect_stderr(first_stderr),
            ):
                with self.assertRaises(runtime_log_archive_git.RuntimeEventMaterializationError) as raised:
                    runtime_log_archive_git.command_materialize_runtime_event(
                        fixture.context, fixture.args
                    )
            self.assertEqual(raised.exception.code, "publication_receipt_failed")
            self.assertEqual(first_stdout.getvalue(), "")
            self.assertEqual(first_stderr.getvalue(), "")
            self.assertTrue(fixture.target.is_file())
            artifact_bytes = fixture.target.read_bytes()
            artifact = json.loads(artifact_bytes)
            publication_intent = artifact["publication_intent"]
            attempt_id = runtime_log_archive_git.derive_publication_attempt_id(
                artifact["materialization_id"],
                fixture.target.relative_to(fixture.source).as_posix(),
            )
            self.assertEqual(publication_intent["attempt_id"], attempt_id)
            self.assertEqual(publication_intent["prepared_state"], "prepared")
            self.assertNotIn("publication", artifact)
            self.assertNotIn("outcome", publication_intent)
            zeroed_artifact = dict(artifact)
            zeroed_artifact["artifact_sha256"] = "0" * 64
            self.assertEqual(
                artifact["artifact_sha256"],
                hashlib.sha256(
                    (
                        json.dumps(zeroed_artifact, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                ).hexdigest(),
            )

            attempt_directory = self.observation_directory(fixture, attempt_id)
            observation_paths = [
                path
                for path in attempt_directory.iterdir()
                if path.name != ".attempt.lock"
            ]
            self.assertEqual(len(observation_paths), 1)
            first_observation_path = observation_paths[0]
            first_observation_bytes = first_observation_path.read_bytes()
            first_observation = json.loads(first_observation_bytes)
            self.assertEqual(
                first_observation_path.name,
                f"000001-{first_observation['observation_sha256']}.json",
            )
            self.assertEqual(first_observation["outcome"], "uncertain")
            self.assertEqual(first_observation["evidence"]["source"], "publish")
            self.assertFalse(first_observation["evidence"]["causal_gap"])
            self.assertEqual(
                first_observation["evidence"]["target_directory_fsync_status"],
                "failed",
            )
            self.assertEqual(first_observation["evidence"]["readback_status"], "verified")
            self.assertEqual(
                first_observation["evidence"]["readback_sha256"],
                artifact["artifact_sha256"],
            )
            first_receipt_path = fixture.target.with_name(
                f"{fixture.target.stem}.outcome.{attempt_id}.000001.json"
            )
            self.assertFalse(first_receipt_path.exists())

            recovery_stdout = io.StringIO()
            recovery_stderr = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {
                        "AGENT_CANON_CODEX_SESSION_ROOT": str(fixture.session_root),
                    },
                    clear=False,
                ),
                contextlib.redirect_stdout(recovery_stdout),
                contextlib.redirect_stderr(recovery_stderr),
            ):
                self.assertEqual(
                    runtime_log_archive_git.command_materialize_runtime_event(
                        fixture.context, fixture.args
                    ),
                    0,
                )
            self.assertEqual(recovery_stderr.getvalue(), "")
            self.assertEqual(fixture.target.read_bytes(), artifact_bytes)
            self.assertEqual(first_observation_path.read_bytes(), first_observation_bytes)
            first_receipt_bytes = first_receipt_path.read_bytes()
            first_receipt = json.loads(first_receipt_bytes)
            second_receipt_path = fixture.target.with_name(
                f"{fixture.target.stem}.outcome.{attempt_id}.000002.json"
            )
            second_receipt_bytes = second_receipt_path.read_bytes()
            second_receipt = json.loads(second_receipt_bytes)
            second_observation = second_receipt["observation"]
            second_observation_path = attempt_directory / (
                f"000002-{second_observation['observation_sha256']}.json"
            )
            self.assertEqual(first_receipt["observation"], first_observation)
            self.assertEqual(
                second_observation["prior_observation_sha256"],
                first_observation["observation_sha256"],
            )
            self.assertEqual(
                second_receipt["prior_receipt_sha256"],
                first_receipt["receipt_sha256"],
            )
            self.assertEqual(second_observation["outcome"], "committed")
            self.assertEqual(second_observation_path.read_bytes(), (
                json.dumps(second_observation, separators=(",", ":")) + "\n"
            ).encode("utf-8"))
            expected_success = [
                f"RUNTIME_EVENT_PATH={fixture.target.relative_to(fixture.source).as_posix()}",
                f"RUNTIME_EVENT_UNIT_ID={fixture.target.stem.rsplit('.', 1)[-1]}",
                f"RUNTIME_EVENT_RECORD_SHA256={hashlib.sha256(fixture.raw_record).hexdigest()}",
                f"RUNTIME_EVENT_MATERIALIZATION_ID={artifact['materialization_id']}",
                f"RUNTIME_EVENT_ATTEMPT_ID={attempt_id}",
                f"RUNTIME_EVENT_RECEIPT_PATH={second_receipt_path.relative_to(fixture.source).as_posix()}",
                f"RUNTIME_EVENT_RECEIPT_SHA256={second_receipt['receipt_sha256']}",
                "RUNTIME_EVENT_OUTCOME=committed",
                "RUNTIME_EVENT_MATERIALIZE=pass",
            ]
            self.assertEqual(recovery_stdout.getvalue(), "\n".join(expected_success) + "\n")

            result, _stdout, stderr = self.invoke_materializer(fixture)
            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(fixture.target.read_bytes(), artifact_bytes)
            self.assertEqual(first_observation_path.read_bytes(), first_observation_bytes)
            self.assertEqual(first_receipt_path.read_bytes(), first_receipt_bytes)
            self.assertEqual(second_receipt_path.read_bytes(), second_receipt_bytes)

    def test_graph_status_query_context_consume_persisted_runtime_event(self) -> None:
        """The typed adapter consumes command responses without a producer route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            executable = root / "graph"
            executable.write_text(
                "#!/bin/sh\n"
                "case \"$2\" in\n"
                "status) printf '%s\\n' '{\"schema\":\"agent-canon.graph.status.v1\",\"command\":\"status\",\"status\":\"fresh\",\"exit_code\":0}'; exit 0 ;;\n"
                "query) printf '%s\\n' '{\"schema\":\"agent-canon.graph.query.v1\",\"command\":\"query\",\"status\":\"fresh\",\"nodes\":[],\"facts\":[],\"exit_code\":0}'; exit 0 ;;\n"
                "context) printf '%s\\n' '{\"schema\":\"agent-canon.graph.context.v1\",\"command\":\"context\",\"status\":\"stale\",\"exit_code\":2}'; exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            client = GraphClient(root, executable)
            self.assertEqual(client.status().status, "fresh")
            self.assertEqual(client.query(all_nodes=True).status, "fresh")
            self.assertEqual(
                client.context("documents/design/example.md", token="runtime-token").status,
                "stale",
            )

    def test_ingest_indexes_identical_projection_event_without_duplicate(self) -> None:
        """Ingest should index an identical unindexed event without appending it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            archive = root / "archive"
            source.mkdir()
            canon.mkdir()
            archive.mkdir()
            key = repo_log_key(source)
            context = runtime_log_archive_git.ArchiveContext(
                source_root=source,
                canon_root=canon,
                archive_root=archive,
                repo_key=key,
                env_key="test-env",
                branch_key="test-branch",
                branch="logs/test-branch",
                remote="unused",
                runtime_root=root / "runtime",
            )
            lock_path = context.runtime_root / "locks" / "archive-transaction.lock"
            lock_path.parent.mkdir(parents=True)
            spool_root = context.runtime_root / "spool" / "hook-events" / key
            events: list[runtime_log_archive_git.HookSpoolEvent] = []
            event_bytes: list[bytes] = []
            event_ids = ("hook-20260718-linear-a", "hook-20260718-linear-b")
            for event_id in event_ids:
                event = {
                    "hook_log_namespace": "test-runtime",
                    "hook_run_id": event_id,
                    "payload_fingerprint": event_id,
                    "source_repo_key": key,
                    "status": "pass",
                    "timestamp": "2026-07-18T00:00:00Z",
                }
                payload = runtime_log_archive_git._canonical_compact_json(event) + b"\n"
                path = spool_root / "test-runtime" / "posttooluse" / f"{event_id}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                events.append(
                    runtime_log_archive_git.HookSpoolEvent(
                        path=path,
                        size=len(payload),
                        bytes_sha256=hashlib.sha256(payload).hexdigest(),
                    )
                )
                event_bytes.append(payload)

            projection_path = archive / "hook-runs" / key / "test-runtime" / "posttooluse-no-git-head.jsonl"
            existing_bytes = event_bytes[0]
            projection_path.parent.mkdir(parents=True, exist_ok=True)
            projection_path.write_bytes(existing_bytes)
            transaction = runtime_log_archive_git.PreparedArchiveTransaction(
                context=context,
                lock_path=lock_path,
                lock_handle=lock_path.open("a+b"),
                archive_head_before="archive-head",
                ensured_branch=context.branch,
            )
            original_read_bytes = Path.read_bytes
            try:
                with patch.object(
                    Path,
                    "read_bytes",
                    autospec=True,
                    side_effect=original_read_bytes,
                ) as read_bytes:
                    result = runtime_log_archive_git.ingest_hook_event_spool(
                        transaction, tuple(events)
                    )
                projection_reads = [
                    call.args[0]
                    for call in read_bytes.call_args_list
                    if call.args and call.args[0] == projection_path
                ]
            finally:
                transaction.lock_handle.close()

            self.assertEqual(len(result.accepted_events), 2)
            self.assertEqual(projection_reads, [projection_path])
            self.assertEqual(projection_path.read_bytes(), existing_bytes + event_bytes[1])
            index_entries = runtime_log_archive_git._parse_spool_index_bytes(
                result.dedup_index_path.read_bytes()
            )
            self.assertEqual(index_entries[event_ids[0]][0], events[0].bytes_sha256)

    def test_finalize_hook_spool_readback_loads_each_projection_once(self) -> None:
        """Readback should load each indexed projection once across covered events."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            archive = root / "archive"
            source.mkdir()
            canon.mkdir()
            archive.mkdir()
            key = repo_log_key(source)
            context = runtime_log_archive_git.ArchiveContext(
                source_root=source,
                canon_root=canon,
                archive_root=archive,
                repo_key=key,
                env_key="test-env",
                branch_key="test-branch",
                branch="logs/test-branch",
                remote="unused",
                runtime_root=root / "runtime",
            )
            lock_path = context.runtime_root / "locks" / "archive-transaction.lock"
            lock_path.parent.mkdir(parents=True)
            spool_root = context.runtime_root / "spool" / "hook-events" / key
            projection_specs = (
                ("runtime-a", "posttooluse", "hook-20260718-readback-a1"),
                ("runtime-a", "posttooluse", "hook-20260718-readback-a2"),
                ("runtime-b", "posttooluse", "hook-20260718-readback-b1"),
                ("runtime-b", "posttooluse", "hook-20260718-readback-b2"),
            )
            events: list[runtime_log_archive_git.HookSpoolEvent] = []
            projection_bytes: dict[Path, bytes] = {}
            index_rows: list[bytes] = []
            for runtime_namespace, hook_name, event_id in projection_specs:
                event = {
                    "hook_log_namespace": runtime_namespace,
                    "hook_run_id": event_id,
                    "payload_fingerprint": event_id,
                    "source_repo_key": key,
                    "status": "pass",
                    "timestamp": "2026-07-18T00:00:00Z",
                }
                payload = runtime_log_archive_git._canonical_compact_json(event) + b"\n"
                path = spool_root / runtime_namespace / hook_name / f"{event_id}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                event_snapshot = runtime_log_archive_git.HookSpoolEvent(
                    path=path,
                    size=len(payload),
                    bytes_sha256=hashlib.sha256(payload).hexdigest(),
                )
                events.append(event_snapshot)
                projection_relative = (
                    Path("hook-runs")
                    / key
                    / runtime_namespace
                    / f"{hook_name}-projection.jsonl"
                )
                projection_path = archive / projection_relative
                projection_bytes[projection_path] = projection_bytes.get(projection_path, b"") + payload
                index_rows.append(
                    runtime_log_archive_git._canonical_compact_json(
                        {
                            "schema": runtime_log_archive_git.HOOK_SPOOL_INDEX_SCHEMA,
                            "event_id": event_id,
                            "event_sha256": event_snapshot.bytes_sha256,
                            "runtime_namespace": runtime_namespace,
                            "hook_name": hook_name,
                            "projection_path": projection_relative.as_posix(),
                            "transaction_id": "transaction",
                        }
                    )
                    + b"\n"
                )

            index_relative = Path("hook-runs") / key / runtime_log_archive_git.HOOK_SPOOL_INDEX_NAME
            index_bytes = b"".join(index_rows)
            ingest_result = runtime_log_archive_git.HookSpoolIngestResult(
                transaction_id="transaction",
                spool_snapshot=tuple(events),
                accepted_events=tuple(events),
                duplicate_events=(),
                failed_event_count=0,
                source_set_sha256="source-set",
                dedup_index_path=archive / index_relative,
                dedup_index_sha256=hashlib.sha256(index_bytes).hexdigest(),
                cursor_path=archive / "hook-runs" / key / runtime_log_archive_git.HOOK_SPOOL_CURSOR_NAME,
                cursor_sha256="cursor-sha",
            )
            receipt = runtime_log_archive_git.ArchivePublicationReceipt(
                status="committed",
                commit_created=True,
                pushed=True,
                archive_commit_oid="commit",
                archive_tree_oid="tree",
                dedup_index_sha256=ingest_result.dedup_index_sha256,
                cursor_sha256=ingest_result.cursor_sha256,
            )
            transaction = runtime_log_archive_git.PreparedArchiveTransaction(
                context=context,
                lock_path=lock_path,
                lock_handle=lock_path.open("a+b"),
                archive_head_before="archive-head",
                ensured_branch=context.branch,
            )
            archive_calls: list[Path] = []

            def fake_archive_blob(
                _context: runtime_log_archive_git.ArchiveContext,
                _commit_oid: str,
                relative_path: Path,
            ) -> bytes:
                archive_calls.append(relative_path)
                if relative_path == index_relative:
                    return index_bytes
                return projection_bytes[archive / relative_path]

            try:
                with patch.object(
                    runtime_log_archive_git,
                    "_archive_blob_at",
                    side_effect=fake_archive_blob,
                ):
                    removed = runtime_log_archive_git.finalize_hook_spool_readback(
                        transaction, receipt, ingest_result
                    )
            finally:
                transaction.lock_handle.close()

            self.assertEqual(removed, len(events))
            self.assertEqual(archive_calls.count(index_relative), 1)
            for projection_path in projection_bytes:
                self.assertEqual(archive_calls.count(projection_path.relative_to(archive)), 1)
            self.assertTrue(all(not event.path.exists() for event in events))

    def test_h03_sync_materializes_projection_cursor_and_replay_dedup(self) -> None:
        """One checkpoint publishes each identity once and finalizes replay."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            event_id = "hook-20260718-event-a"
            event = {
                "hook_log_namespace": "test-runtime",
                "hook_run_id": event_id,
                "payload_fingerprint": "fixture-a",
                "source_repo_key": key,
                "status": "pass",
                "timestamp": "2026-07-18T00:00:00Z",
            }
            event_bytes = (
                json.dumps(
                    event,
                    allow_nan=False,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            spool_path = (
                self.runtime_root(root)
                / "spool"
                / "hook-events"
                / key
                / "test-runtime"
                / "posttooluse"
                / f"{event_id}.json"
            )
            spool_path.parent.mkdir(parents=True)
            spool_path.write_bytes(event_bytes)

            synced = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS=committed", synced.stdout)
            self.assertFalse(spool_path.exists())

            archive_root = mounted_log_archive_root(canon, self.runtime_root(root))
            metadata_root = archive_root / "hook-runs" / key
            index_path = metadata_root / ".spool-index.jsonl"
            cursor_path = metadata_root / ".spool-cursor.json"
            projection_path = (
                metadata_root / "test-runtime" / "posttooluse-no-git-head.jsonl"
            )
            index_lines = index_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(index_lines), 1)
            index_row = json.loads(index_lines[0])
            self.assertEqual(index_row["event_id"], event_id)
            self.assertEqual(index_row["event_sha256"], hashlib.sha256(event_bytes).hexdigest())
            self.assertEqual(projection_path.read_bytes(), event_bytes)

            cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
            cursor_sha256 = cursor.pop("cursor_body_sha256")
            self.assertEqual(
                cursor_sha256,
                hashlib.sha256(
                    json.dumps(
                        cursor,
                        allow_nan=False,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )

            spool_path.write_bytes(event_bytes)
            replay = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assertFalse(spool_path.exists())
            self.assertEqual(index_path.read_text(encoding="utf-8").splitlines(), index_lines)
            self.assertEqual(projection_path.read_bytes(), event_bytes)

    def test_h04_partial_busy_and_malformed_transactions_retain_spool(self) -> None:
        """No-push, busy-lock, and validation failures retain exact source files."""
        import fcntl

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            event_id = "hook-20260718-retained"
            event = {
                "hook_log_namespace": "test-runtime",
                "hook_run_id": event_id,
                "payload_fingerprint": "retained",
                "source_repo_key": key,
                "status": "warn",
                "timestamp": "2026-07-18T00:00:00Z",
            }
            event_bytes = (
                json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            runtime_root = self.runtime_root(root)
            spool_directory = (
                runtime_root
                / "spool"
                / "hook-events"
                / key
                / "test-runtime"
                / "posttooluse"
            )
            spool_directory.mkdir(parents=True)
            spool_path = spool_directory / f"{event_id}.json"
            spool_path.write_bytes(event_bytes)

            partial = self.run_tool(
                "sync",
                "--no-agent-reports",
                "--no-push",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=partial_retained", partial.stdout)
            self.assertEqual(spool_path.read_bytes(), event_bytes)

            lock_path = runtime_root / "locks" / "archive-transaction.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+b") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                busy = self.run_tool(
                    "sync",
                    "--no-agent-reports",
                    source_root=source,
                    canon_root=canon,
                    remote=remote,
                )
            self.assertNotEqual(busy.returncode, 0)
            self.assertIn("archive_transaction_busy", busy.stdout)
            self.assertEqual(spool_path.read_bytes(), event_bytes)

            malformed = spool_directory / "hook-20260718-malformed.json"
            malformed.write_bytes(b"{not-json}\n")
            failed = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertTrue(malformed.exists())
            self.assertEqual(spool_path.read_bytes(), event_bytes)

    def test_h04_inconsistent_checkpoint_never_deduplicates_and_recovers(self) -> None:
        """Partial index/cursor/projection states retain sources until repaired."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            event_id = "hook-20260718-checkpoint-recovery"
            event_bytes = (
                json.dumps(
                    {
                        "hook_log_namespace": "test-runtime",
                        "hook_run_id": event_id,
                        "payload_fingerprint": "checkpoint-recovery",
                        "source_repo_key": key,
                        "status": "partial",
                        "timestamp": "2026-07-18T00:00:00Z",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            spool_path = (
                self.runtime_root(root)
                / "spool"
                / "hook-events"
                / key
                / "test-runtime"
                / "posttooluse"
                / f"{event_id}.json"
            )
            spool_path.parent.mkdir(parents=True)
            spool_path.write_bytes(event_bytes)
            prepared = self.run_tool(
                "sync",
                "--no-agent-reports",
                "--no-push",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
            self.assertEqual(spool_path.read_bytes(), event_bytes)

            archive_root = mounted_log_archive_root(canon, self.runtime_root(root))
            metadata_root = archive_root / "hook-runs" / key
            index_path = metadata_root / ".spool-index.jsonl"
            cursor_path = metadata_root / ".spool-cursor.json"
            index_bytes = index_path.read_bytes()
            cursor_bytes = cursor_path.read_bytes()
            index_row = json.loads(index_bytes.decode("utf-8"))
            projection_path = archive_root / index_row["projection_path"]
            projection_bytes = projection_path.read_bytes()
            archive_head = subprocess.run(
                ["git", "-C", str(archive_root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            def assert_inconsistent() -> None:
                failed = self.run_tool(
                    "sync",
                    "--no-agent-reports",
                    source_root=source,
                    canon_root=canon,
                    remote=remote,
                )
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(spool_path.read_bytes(), event_bytes)
                observed_head = subprocess.run(
                    ["git", "-C", str(archive_root), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                self.assertEqual(observed_head, archive_head)

            index_path.write_bytes(index_bytes + b'{"partial"')
            assert_inconsistent()
            index_path.write_bytes(index_bytes)

            cursor_path.unlink()
            assert_inconsistent()
            cursor_path.write_bytes(cursor_bytes)

            projection_path.unlink()
            assert_inconsistent()
            projection_path.write_bytes(projection_bytes)

            projection_path.write_bytes(projection_bytes.replace(b'"partial"', b'"warn"'))
            assert_inconsistent()
            projection_path.write_bytes(projection_bytes)

            stale_cursor = json.loads(cursor_bytes)
            stale_cursor["dedup_index_sha256"] = "0" * 64
            stale_cursor["cursor_body_sha256"] = runtime_log_archive_git._cursor_body_sha256(
                stale_cursor
            )
            cursor_path.write_bytes(
                runtime_log_archive_git._canonical_compact_json(stale_cursor) + b"\n"
            )
            assert_inconsistent()
            cursor_path.write_bytes(cursor_bytes)

            recovered = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertFalse(spool_path.exists())
            self.assertEqual(index_path.read_bytes(), index_bytes)
            self.assertEqual(projection_path.read_bytes(), projection_bytes)

    def test_h04_rejected_push_retains_then_recovers_same_event(self) -> None:
        """A committed local transaction is retained until remote publication succeeds."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            event_id = "hook-20260718-uncertain"
            event = {
                "hook_log_namespace": "test-runtime",
                "hook_run_id": event_id,
                "payload_fingerprint": "uncertain",
                "source_repo_key": key,
                "status": "pass",
                "timestamp": "2026-07-18T00:00:00Z",
            }
            event_bytes = (
                json.dumps(
                    event,
                    allow_nan=False,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            spool_path = (
                self.runtime_root(root)
                / "spool"
                / "hook-events"
                / key
                / "test-runtime"
                / "posttooluse"
                / f"{event_id}.json"
            )
            spool_path.parent.mkdir(parents=True)
            spool_path.write_bytes(event_bytes)

            reject_hook = remote / "hooks" / "pre-receive"
            reject_hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            reject_hook.chmod(reject_hook.stat().st_mode | stat.S_IXUSR)

            uncertain = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(uncertain.returncode, 0)
            self.assertIn(
                "RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS=uncertain",
                uncertain.stdout,
            )
            self.assertEqual(spool_path.read_bytes(), event_bytes)
            local_index = (
                mounted_log_archive_root(canon, self.runtime_root(root))
                / "hook-runs"
                / key
                / ".spool-index.jsonl"
            )
            self.assertTrue(local_index.is_file())
            self.assertEqual(len(local_index.read_text(encoding="utf-8").splitlines()), 1)

            reject_hook.unlink()
            recovered = self.run_tool(
                "sync",
                "--no-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertIn(
                "RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS=committed",
                recovered.stdout,
            )
            self.assertFalse(spool_path.exists())
            self.assertEqual(len(local_index.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
