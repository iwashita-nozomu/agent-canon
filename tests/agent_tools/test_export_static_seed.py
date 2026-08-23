# @dependency-start
# contract test
# responsibility Verifies deterministic static-seed export, forbidden-surface rejection, and source-hidden consumer validation.
# upstream implementation ../../tools/agent_tools/export_static_seed.py exports one committed exact-path seed.
# upstream design ../../documents/contracts/static-seed-export.md defines the static seed boundary.
# upstream design ../../documents/contracts/static-seed-allowlist.toml defines the canonical production allowlist.
# @dependency-end
"""Focused tests for the canonical static AgentCanon seed export."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "export_static_seed.py"
ALLOWLIST_PATH = Path("documents/contracts/static-seed-allowlist.toml")
PROVENANCE_PATH = "agent-canon-static-seed.json"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_static_seed", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EXPORTER = _load_module()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_index(repo: Path, message: str) -> None:
    _git(
        repo,
        "-c",
        "user.name=Static Seed Test",
        "-c",
        "user.email=static-seed@example.invalid",
        "commit",
        "-qm",
        message,
    )


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _commit_index(repo, message)


def _allowlist_text(paths: list[str], **extra: object) -> str:
    lines = [
        "version = 1",
        'source_repository = "iwashita-nozomu/agent-canon"',
        "files = [",
    ]
    lines.extend(f'  {json.dumps(path)},' for path in sorted(paths))
    lines.append("]")
    for key, value in extra.items():
        lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines) + "\n"


def _write_allowlist(repo: Path, paths: list[str], **extra: object) -> None:
    target = repo / ALLOWLIST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_allowlist_text(paths, **extra), encoding="utf-8")


def _make_fixture(root: Path) -> Path:
    repo = root / "source"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    config = repo / ".codex" / "config.toml"
    worker = repo / ".codex" / "agents" / "worker.toml"
    reviewer = repo / ".codex" / "agents" / "reviewer.toml"
    worker.parent.mkdir(parents=True)
    config.write_text(
        'approval_policy = "on-request"\n'
        'sandbox_mode = "workspace-write"\n'
        "\n"
        "[agents]\n"
        "max_threads = 2\n"
        "\n"
        "[agents.reviewer]\n"
        'description = "Reviews a bounded change."\n'
        'config_file = "agents/reviewer.toml"\n'
        "\n"
        "[agents.worker]\n"
        'description = "Implements a bounded change."\n'
        'config_file = "agents/worker.toml"\n',
        encoding="utf-8",
    )
    reviewer.write_text(
        'name = "reviewer"\n'
        'sandbox_mode = "read-only"\n'
        'developer_instructions = "Review the bounded diff."\n',
        encoding="utf-8",
    )
    worker.write_text(
        'name = "worker"\n'
        'sandbox_mode = "workspace-write"\n'
        'developer_instructions = "Implement the bounded change."\n',
        encoding="utf-8",
    )
    (repo / "unlisted.txt").write_text("must stay out\n", encoding="utf-8")
    _write_allowlist(
        repo,
        [
            ".codex/agents/reviewer.toml",
            ".codex/agents/worker.toml",
            ".codex/config.toml",
        ],
    )
    _commit(repo, "fixture")
    return repo


def _make_canonical_35_role_fixture(root: Path) -> Path:
    """Create a committed source snapshot from the canonical static role set."""
    repo = root / "canonical-source"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    allowlist = tomllib.loads(
        (PROJECT_ROOT / ALLOWLIST_PATH).read_text(encoding="utf-8")
    )
    paths = list(allowlist["files"])
    for relative in paths:
        source = PROJECT_ROOT / relative
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    _write_allowlist(repo, paths)
    _commit(repo, "canonical 35-role static fixture")
    return repo


def _run_export(repo: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            str(SCRIPT),
            "--source-root",
            str(repo),
            "--source-ref",
            "HEAD",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def _tree_snapshot(root: Path) -> tuple[tuple[str, int, bytes], ...]:
    rows: list[tuple[str, int, bytes]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            continue
        rows.append((relative, mode, path.read_bytes()))
    return tuple(rows)


def _assert_source_free_seed(testcase: unittest.TestCase, root: Path) -> None:
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    testcase.assertEqual(
        files,
        {
            ".codex/agents/reviewer.toml",
            ".codex/agents/worker.toml",
            ".codex/config.toml",
            PROVENANCE_PATH,
        },
    )
    for path in root.rglob("*"):
        testcase.assertFalse(path.is_symlink(), path)
        if path.is_file():
            testcase.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
    config = tomllib.loads((root / ".codex" / "config.toml").read_text(encoding="utf-8"))
    for role, value in config["agents"].items():
        if not isinstance(value, dict) or "config_file" not in value:
            continue
        referenced = root / ".codex" / value["config_file"]
        testcase.assertTrue(referenced.is_file(), f"missing role {role}: {referenced}")
    forbidden = (
        b"vendor/agent-canon",
        b"tools/agent-canon",
        b"agent_canon_source_root",
        b"https://",
        b"git submodule",
        b"agent_canon_repo_token",
    )
    for path in root.rglob("*"):
        if path.is_file():
            lowered = path.read_bytes().lower()
            testcase.assertFalse(any(marker in lowered for marker in forbidden), path)


class ExportStaticSeedTest(unittest.TestCase):
    """Exercise the producer-only static seed contract."""

    def test_repeated_exports_are_byte_for_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            first = root / "first"
            second = root / "second"

            first_result = _run_export(repo, first)
            second_result = _run_export(repo, second)

            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            self.assertEqual(_tree_snapshot(first), _tree_snapshot(second))
            self.assertNotIn("unlisted.txt", {row[0] for row in _tree_snapshot(first)})
            provenance = json.loads((first / PROVENANCE_PATH).read_text(encoding="utf-8"))
            self.assertEqual(
                set(provenance),
                {"schema_version", "source_commit", "source_repository"},
            )
            self.assertEqual(provenance["source_commit"], _git(repo, "rev-parse", "HEAD"))
            self.assertEqual(
                provenance["source_repository"],
                "iwashita-nozomu/agent-canon",
            )

    def test_source_hidden_fixture_remains_structurally_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            output = root / "seed"
            result = _run_export(repo, output)
            self.assertEqual(result.returncode, 0, result.stderr)

            hidden = root / "source.hidden"
            repo.rename(hidden)
            _assert_source_free_seed(self, output)

    def test_canonical_35_role_fixture_is_deterministic_closed_and_source_hidden(self) -> None:
        """The real canonical role set exports as one closed source-free snapshot."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_canonical_35_role_fixture(root)
            first = root / "first"
            second = root / "second"
            first_result = _run_export(repo, first)
            second_result = _run_export(repo, second)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            self.assertEqual(_tree_snapshot(first), _tree_snapshot(second))
            role_files = sorted(first.glob(".codex/agents/*.toml"))
            self.assertEqual(len(role_files), 35)
            config = tomllib.loads((first / ".codex" / "config.toml").read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    f".codex/{value['config_file']}"
                    for value in config["agents"].values()
                    if isinstance(value, dict) and "config_file" in value
                },
                {path.relative_to(first).as_posix() for path in role_files},
            )
            checker = subprocess.run(
                (
                    sys.executable,
                    str(PROJECT_ROOT / "tools" / "docs" / "check_bootstrap_docs.py"),
                    "--root",
                    str(first),
                    "--static-seed-consumer",
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checker.returncode, 0, checker.stdout + checker.stderr)
            repo.rename(root / "canonical-source.hidden")
            self.assertFalse((root / "canonical-source").exists())
            self.assertFalse((first / "vendor").exists())
            for path in first.rglob("*"):
                self.assertFalse(path.is_symlink(), path)
                if path.is_file():
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_forbidden_paths_and_out_of_root_entries_are_rejected(self) -> None:
        cases = (
            "../escape.toml",
            "AGENTS.md",
            "tools/agent-canon/run.py",
            "vendor/agent-canon/README.md",
            ".agent-canon/update-state.toml",
            ".github/workflows/update.yml",
        )
        for forbidden_path in cases:
            with self.subTest(path=forbidden_path), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                repo = _make_fixture(root)
                if not forbidden_path.startswith("../"):
                    target = repo / forbidden_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text('name = "forbidden"\n', encoding="utf-8")
                _write_allowlist(
                    repo,
                    [
                        ".codex/agents/reviewer.toml",
                        ".codex/agents/worker.toml",
                        ".codex/config.toml",
                        forbidden_path,
                    ],
                )
                _commit(repo, "forbidden path")

                result = _run_export(repo, root / "seed")

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AGENT_CANON_STATIC_SEED=fail", result.stderr)
                self.assertFalse((root / "seed").exists())

    def test_symlink_and_gitlink_sources_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            linked = repo / ".codex" / "agents" / "linked.toml"
            os.symlink("worker.toml", linked)
            _write_allowlist(
                repo,
                [
                    ".codex/agents/linked.toml",
                    ".codex/agents/reviewer.toml",
                    ".codex/agents/worker.toml",
                    ".codex/config.toml",
                ],
            )
            _commit(repo, "symlink fixture")

            result = _run_export(repo, root / "symlink-seed")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("regular non-executable tracked file", result.stderr)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            object_id = _git(repo, "rev-parse", "HEAD")
            gitlink_path = ".codex/agents/module.toml"
            _write_allowlist(
                repo,
                [
                    gitlink_path,
                    ".codex/agents/reviewer.toml",
                    ".codex/agents/worker.toml",
                    ".codex/config.toml",
                ],
            )
            _git(repo, "add", ALLOWLIST_PATH.as_posix())
            _git(
                repo,
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{object_id},{gitlink_path}",
            )
            _commit_index(repo, "gitlink fixture")

            result = _run_export(repo, root / "gitlink-seed")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("regular non-executable tracked file", result.stderr)

    def test_runtime_network_and_secret_content_is_rejected(self) -> None:
        cases = (
            'command = "curl https://example.invalid/seed"\n',
            'developer_instructions = "use agent_canon_source_root"\n',
            'developer_instructions = "read AGENT_CANON_REPO_TOKEN"\n',
            'developer_instructions = "import agent_tools"\n',
            'update_state = "sync-state.json"\n',
        )
        for payload in cases:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                repo = _make_fixture(root)
                (repo / ".codex" / "agents" / "worker.toml").write_text(
                    'name = "worker"\n' + payload,
                    encoding="utf-8",
                )
                _commit(repo, "forbidden content")

                result = _run_export(repo, root / "seed")

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AGENT_CANON_STATIC_SEED=fail", result.stderr)
                self.assertFalse((root / "seed").exists())

    def test_exact_case_normalized_producer_prefixes_are_rejected_before_output(self) -> None:
        """Every exact forbidden producer prefix is rejected case-insensitively."""
        prefixes = (
            "AgEnTs/SkIlLs/",
            "AgEnTs/MoDeL_PrOfIlEs.ToMl",
            "ToOlS/AgEnT_ToOlS/",
            "../../AgEnTs/",
            "../../ToOlS/",
        )
        for prefix in prefixes:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                repo = _make_fixture(root)
                (repo / ".codex" / "agents" / "worker.toml").write_text(
                    'name = "worker"\n'
                    f'developer_instructions = "prefix {prefix}payload"\n',
                    encoding="utf-8",
                )
                _commit(repo, "forbidden producer prefix")
                result = _run_export(repo, root / "seed")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("forbidden producer prefix", result.stderr)
                self.assertFalse((root / "seed").exists())

    def test_unlisted_role_and_unknown_allowlist_control_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            _write_allowlist(
                repo,
                [
                    ".codex/agents/worker.toml",
                    ".codex/config.toml",
                ],
            )
            _commit(repo, "missing role")

            result = _run_export(repo, root / "missing-role-seed")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("references an unexported file", result.stderr)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            _write_allowlist(
                repo,
                [
                    ".codex/agents/reviewer.toml",
                    ".codex/agents/worker.toml",
                    ".codex/config.toml",
                ],
                updater="enabled",
            )
            _commit(repo, "unknown control")

            result = _run_export(repo, root / "unknown-control-seed")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported keys", result.stderr)

    def test_loaded_plan_can_be_written_after_source_disappears(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = _make_fixture(root)
            plan = EXPORTER.load_export_plan(repo, "HEAD")
            shutil.rmtree(repo)

            output = root / "seed"
            EXPORTER.write_export(plan, output)

            _assert_source_free_seed(self, output)


if __name__ == "__main__":
    unittest.main()
