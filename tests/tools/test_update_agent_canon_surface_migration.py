"""Tests for AgentCanon shared surface migration correctness."""

# @dependency-start
# contract test
# responsibility Verifies parent submodule readiness and non-destructive root-surface migration.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream implementation ../../tools/sync_agent_canon.sh root-surface synchronization
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py RootResolution contract
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml typed retired descendant paths
# downstream implementation ../../test/testrunner.sh runs this migration regression from the source Git root
# @dependency-end

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_RESOLUTION = PROJECT_ROOT / "tools" / "agent_tools" / "agent_canon_source_root.py"
LEGACY_AGENT_CANON_PIN = "5ea949c85d74b66427efdc4d2b847c62e547515c"
LEGACY_ROOT_PROJECTIONS = {
    "tools/sync_agent_canon.sh": (
        "tools/sync_agent_canon.sh",
        "a354e6597b7337a39bc650ff61dd57cab08981e8",
        "100755",
    ),
    "tools/agent_tools/surface_manifest.py": (
        "tools/agent_tools/surface_manifest.py",
        "9ebdc1f8198fbe63c037186da81867901f300ef5",
        "100644",
    ),
    "tools/agent_tools/update_agent_canon.sh": (
        "tools/update_agent_canon.sh",
        "7c673f9b5b2bddac85d87f14466020acdeb9dd78",
        "100644",
    ),
}


def load_root_resolution_module() -> ModuleType:
    """Load the current RootResolution implementation."""
    spec = importlib.util.spec_from_file_location("agent_canon_source_root", ROOT_RESOLUTION)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {ROOT_RESOLUTION}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SurfaceMigrationTest(unittest.TestCase):
    """Verify migration behavior for legacy parent root surfaces."""

    def test_source_notes_do_not_retain_personal_memory_projections(self) -> None:
        """Source notes remain usable without the retired personal-memory links."""
        for name in ("USER_PREFERENCES.md", "AGENT_PHILOSOPHY.md"):
            path = PROJECT_ROOT / "notes" / "themes" / name
            self.assertFalse(os.path.lexists(path), path)

    def git(self, root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run one Git command in a fixture repository."""
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=check,
            capture_output=True,
            text=True,
        )

    def configure_git(self, root: Path) -> None:
        """Configure an isolated fixture repository."""
        self.git(root, "config", "user.email", "agent-canon-test@example.invalid")
        self.git(root, "config", "user.name", "AgentCanon test")

    def historical_file(self, path: str) -> bytes:
        """Read one exact pre-transition file from the repository history."""
        result = subprocess.run(
            ["git", "show", f"{LEGACY_AGENT_CANON_PIN}:{path}"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def materialize_legacy_root_projections(self, parent: Path) -> None:
        """Write the exact pre-#520 root projection bytes and Git modes."""
        for destination_path, (source_path, expected_blob, expected_mode) in (
            LEGACY_ROOT_PROJECTIONS.items()
        ):
            destination = parent / destination_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(self.historical_file(source_path))
            self.git(parent, "add", destination_path)
            chmod = "+x" if expected_mode == "100755" else "-x"
            self.git(parent, "update-index", f"--chmod={chmod}", destination_path)
            index_entry = self.git(parent, "ls-files", "-s", "--", destination_path).stdout
            self.assertEqual(
                index_entry.split()[:2],
                [expected_mode, expected_blob],
                destination_path,
            )

    def clone_parent_fixture(self, *, activate_transition: bool = False) -> Path:
        """Return a parent fixture with a real main-branch AgentCanon submodule."""
        tmp_root_handle = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_root_handle.cleanup)
        tmp_root = Path(tmp_root_handle.name)
        source = tmp_root / "source"
        parent = tmp_root / "parent"

        shutil.copytree(
            PROJECT_ROOT,
            source,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".agent-canon",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                "reports",
            ),
        )
        self.assertFalse(
            (source / "reports").exists(),
            "fixture copy must not ingest parent-local reports/temp output",
        )
        self.git(source, "init")
        self.configure_git(source)
        self.git(source, "branch", "-M", "main")
        self.git(source, "add", "-A")
        self.git(source, "update-index", "--chmod=+x", "tools/sync_agent_canon.sh")
        self.git(
            source,
            "update-index",
            "--chmod=-x",
            "tools/agent_tools/surface_manifest.py",
        )
        self.git(source, "update-index", "--chmod=-x", "tools/update_agent_canon.sh")
        self.git(source, "commit", "-m", "fixture current AgentCanon source")

        parent.mkdir()
        self.git(parent, "init")
        self.configure_git(parent)
        self.git(
            parent,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "--branch",
            "main",
            str(source),
            "vendor/agent-canon",
        )
        if activate_transition:
            self.materialize_legacy_root_projections(parent)
            self.git(
                parent,
                "update-index",
                "--cacheinfo",
                f"160000,{LEGACY_AGENT_CANON_PIN},vendor/agent-canon",
            )
        else:
            self.git(parent / "vendor" / "agent-canon", "checkout", "-B", "main")
            self.git(parent, "add", "vendor/agent-canon")
        self.git(parent, "add", ".gitmodules")
        self.git(parent, "commit", "-m", "fixture parent submodule")
        if activate_transition:
            old_object = self.git(
                parent / "vendor" / "agent-canon",
                "cat-file",
                "-e",
                f"{LEGACY_AGENT_CANON_PIN}^{{commit}}",
                check=False,
            )
            self.assertNotEqual(old_object.returncode, 0)
            self.git(parent, "add", "vendor/agent-canon")
        return parent

    def run_sync(
        self,
        root: Path,
        *commands: str,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one sync command in the fixture root."""
        environment = dict(os.environ)
        for name in tuple(environment):
            if name.startswith("AGENT_CANON_") or name in {
                "TMPDIR",
                "TEMP",
                "TMP",
                "HOME",
                "XDG_CACHE_HOME",
                "PYTHONPYCACHEPREFIX",
                "CARGO_HOME",
                "CARGO_TARGET_DIR",
            }:
                environment.pop(name)
        state_root = root / ".agent-canon" / "surface-test-state"
        tmp_root = state_root / "tmp"
        cache_root = state_root / "cache"
        home_root = state_root / "home"
        tools_root = state_root / "tools"
        for path in (tmp_root, cache_root, home_root, tools_root):
            path.mkdir(parents=True, exist_ok=True)
        environment.update(
            {
                "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": "evidence:" + ("0" * 64),
                "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
                "AGENT_CANON_BRANCH_WORKTREE_REASON": "AgentCanon root surface repair requested by user",
                "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
                "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "Fixture-only legacy surface pruning",
                "AGENT_CANON_FORCE_RELINK": "1",
                "TMPDIR": str(tmp_root),
                "TEMP": str(tmp_root),
                "TMP": str(tmp_root),
                "HOME": str(home_root),
                "XDG_CACHE_HOME": str(cache_root / "xdg"),
                "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "CARGO_HOME": str(cache_root / "cargo-home"),
                "CARGO_TARGET_DIR": str(cache_root / "cargo-target"),
                "AGENT_CANON_TOOLS_HOME": str(tools_root),
                "AGENT_CANON_CLI_TARGET_DIR": str(cache_root / "cargo-target"),
            }
        )
        environment.update(env_overrides or {})
        return subprocess.run(
            [
                "bash",
                str(root / "vendor" / "agent-canon" / "tools" / "sync_agent_canon.sh"),
                *commands,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def run_resolved_sync(
        self,
        root: Path,
        *commands: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run sync through the public source-root resolver from a parent."""
        source = root / "vendor" / "agent-canon"
        return subprocess.run(
            [
                sys.executable,
                str(source / "tools" / "agent_tools" / "agent_canon_source_root.py"),
                "exec",
                "tools/sync_agent_canon.sh",
                *commands,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, text: str) -> None:
        """Write a file for the fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def add_regular_surface(self, root: Path, path: str, source: str | None = None) -> None:
        """Add one regular-path contract to the fixture's source manifest."""
        manifest = root / "vendor" / "agent-canon" / "documents" / "runtime" / "shared-runtime-surfaces.toml"
        manifest_text = manifest.read_text(encoding="utf-8")
        if path == ".vscode":
            manifest_text = manifest_text.replace('  ".vscode",\n', "")
        entry = [
            "",
            "[[surface]]",
            f'path = "{path}"',
            'mode = "regular"',
            'projection_producer = "template-or-derived-repo"',
            'projection_kind = "active_contract"',
        ]
        if source is not None:
            entry.append(f'source = "{source}"')
        manifest.write_text(
            manifest_text + "\n".join(entry) + "\n",
            encoding="utf-8",
        )

    def regular_fixture(self, path: str, source: str | None = "seed/regular.txt") -> Path:
        """Create a fixture with one regular-path contract and optional seed."""
        root = self.clone_parent_fixture()
        self.add_regular_surface(root, path, source)
        if source is not None:
            self.write_file(
                root / "vendor" / "agent-canon" / source,
                "canonical regular seed\n",
            )
        return root

    def assert_regular_collision_preserved(self, path: str, create_collision) -> tuple[Path, Path]:
        """A non-regular target fails and remains byte/identity-preserved."""
        root = self.regular_fixture(path)
        target = root / path
        create_collision(target)
        before = os.lstat(target)
        result = self.run_sync(root, "link-root")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"regular[{path}]=collision", result.stderr)
        after = os.lstat(target)
        self.assertEqual(
            (after.st_mode, after.st_dev, after.st_ino),
            (before.st_mode, before.st_dev, before.st_ino),
        )
        return root, target

    def test_regular_path_state_machine_preserves_types_and_materializes_only_safe_targets(self) -> None:
        """Regular materialization handles expected, absent, link, and typed collisions."""
        existing = self.regular_fixture("regular-existing.txt")
        existing_target = existing / "regular-existing.txt"
        existing_target.write_text("parent-owned regular\n", encoding="utf-8")
        existing_before = os.lstat(existing_target)
        result = self.run_sync(existing, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        existing_after = os.lstat(existing_target)
        self.assertEqual(
            (existing_after.st_mode, existing_after.st_dev, existing_after.st_ino),
            (existing_before.st_mode, existing_before.st_dev, existing_before.st_ino),
        )
        self.assertEqual(existing_target.read_text(encoding="utf-8"), "parent-owned regular\n")

        absent = self.regular_fixture("nested/regular-absent.txt")
        result = self.run_sync(absent, "link-root")
        absent_target = absent / "nested/regular-absent.txt"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(absent_target.read_text(encoding="utf-8"), "canonical regular seed\n")

        symlink = self.regular_fixture("regular-symlink.txt")
        symlink_target = symlink / "regular-symlink.txt"
        symlink_target.symlink_to("vendor/agent-canon/seed/regular.txt")
        result = self.run_sync(symlink, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(symlink_target.is_file() and not symlink_target.is_symlink())
        self.assertEqual(symlink_target.read_text(encoding="utf-8"), "canonical regular seed\n")

        _, directory_target = self.assert_regular_collision_preserved(
            "regular-directory.txt",
            lambda target: (target.mkdir(), (target / "sentinel").write_text("keep\n", encoding="utf-8")),
        )
        self.assertEqual(
            (directory_target / "sentinel").read_text(encoding="utf-8"),
            "keep\n",
        )

        def make_fifo(target: Path) -> None:
            os.mkfifo(target)

        self.assert_regular_collision_preserved("regular-fifo", make_fifo)

        def make_socket(target: Path) -> None:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(server.close)
            server.bind(str(target))

        self.assert_regular_collision_preserved("regular-socket", make_socket)

        vscode_absent = self.regular_fixture(".vscode", source=None)
        result = self.run_sync(vscode_absent, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((vscode_absent / ".vscode").is_dir())

        vscode_existing = self.regular_fixture(".vscode", source=None)
        vscode_existing_target = vscode_existing / ".vscode"
        vscode_existing_target.mkdir()
        vscode_existing_sentinel = vscode_existing_target / "sentinel"
        vscode_existing_sentinel.write_text("keep vscode directory\n", encoding="utf-8")
        vscode_existing_before = os.lstat(vscode_existing_target)
        result = self.run_sync(vscode_existing, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        vscode_existing_after = os.lstat(vscode_existing_target)
        self.assertEqual(
            (vscode_existing_after.st_mode, vscode_existing_after.st_dev, vscode_existing_after.st_ino),
            (vscode_existing_before.st_mode, vscode_existing_before.st_dev, vscode_existing_before.st_ino),
        )
        self.assertEqual(
            vscode_existing_sentinel.read_text(encoding="utf-8"),
            "keep vscode directory\n",
        )

        vscode_link = self.regular_fixture(".vscode", source=None)
        vscode_link_target = vscode_link / ".vscode"
        vscode_link_target.symlink_to("vendor/agent-canon")
        result = self.run_sync(vscode_link, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(vscode_link_target.is_dir() and not vscode_link_target.is_symlink())

        vscode_file = self.regular_fixture(".vscode", source=None)
        vscode_file_target = vscode_file / ".vscode"
        vscode_file_target.write_text("parent-owned vscode file\n", encoding="utf-8")
        result = self.run_sync(vscode_file, "link-root")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("regular[.vscode]=collision", result.stderr)
        self.assertEqual(vscode_file_target.read_text(encoding="utf-8"), "parent-owned vscode file\n")

    def retired_descendant_paths(self) -> tuple[str, ...]:
        """Return all manifest-listed test/fixture and note descendants."""
        manifest_path = PROJECT_ROOT / "documents" / "runtime" / "shared-runtime-surfaces.toml"
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        paths: set[str] = set()
        for group in manifest.get("group", []):
            if group.get("mode") != "removed_legacy":
                continue
            paths.update(
                path
                for path in group.get("paths", [])
                if path.startswith("tests/agent_tools/")
                or path.startswith("tests/tools/")
                or path == "tests/fixtures/python_algorithm_contract"
                or path.startswith("notes/")
            )
        return tuple(sorted(paths))

    def test_parent_root_resolution_and_devcontainer_migration(self) -> None:
        """RootResolution and the minimal projection preserve parent content."""
        root = self.clone_parent_fixture(activate_transition=True)
        root_resolution = load_root_resolution_module()
        resolution = root_resolution.resolve_agent_canon_source_root(root)
        self.assertEqual(resolution.layout, root_resolution.LAYOUT_VENDORED)
        self.assertEqual(resolution.current_repository_root, root.resolve())
        self.assertEqual(
            resolution.source_root,
            (root / "vendor" / "agent-canon").resolve(),
        )
        parent_templates = root / "templates"
        parent_templates.mkdir()
        template_sentinel = parent_templates / "parent-owned.txt"
        template_sentinel.write_text("keep parent templates\n", encoding="utf-8")
        parent_tools = root / "tools"
        parent_tools.mkdir(exist_ok=True)
        tools_sentinel = parent_tools / "parent-local-tool.sh"
        tools_sentinel.write_text("keep parent tools\n", encoding="utf-8")
        devcontainer = root / ".devcontainer"
        devcontainer.mkdir()
        custom_hook = devcontainer / "post-create-parent.sh"
        unknown_file = devcontainer / "parent-local-marker.txt"
        custom_hook.write_text("#!/usr/bin/env bash\necho parent hook\n", encoding="utf-8")
        custom_hook.chmod(0o755)
        unknown_file.write_text("keep this parent-owned file\n", encoding="utf-8")
        parent_devcontainer_files = (
            "finalize-shared-runtime.sh",
            "generate-runtime-compose.sh",
            "docker-compose.generated.yml",
            "post-attach.sh",
            "post-create.sh",
        )
        for name in parent_devcontainer_files:
            self.write_file(devcontainer / name, "legacy wrapper\n")

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("agent_canon_parent_submodule=projection_ready", result.stdout)
        self.assertNotIn("update_transition[", result.stdout)
        self.assertTrue(parent_templates.is_dir())
        self.assertFalse(parent_templates.is_symlink())
        self.assertEqual(
            template_sentinel.read_text(encoding="utf-8"),
            "keep parent templates\n",
        )
        self.assertEqual(
            tools_sentinel.read_text(encoding="utf-8"),
            "keep parent tools\n",
        )
        # Legacy tool files are parent-owned regular content and remain intact.
        self.assertTrue((root / "tools" / "sync_agent_canon.sh").is_file())
        self.assertTrue((root / "tools" / "agent_tools" / "surface_manifest.py").is_file())
        self.assertTrue((root / "tools" / "agent_tools" / "update_agent_canon.sh").is_file())
        self.assertTrue((root / "tools" / "agent-canon").is_symlink())
        self.assertTrue(devcontainer.is_dir() and not devcontainer.is_symlink())
        self.assertEqual(custom_hook.read_text(encoding="utf-8"), "#!/usr/bin/env bash\necho parent hook\n")
        self.assertTrue(os.access(custom_hook, os.X_OK))
        self.assertEqual(unknown_file.read_text(encoding="utf-8"), "keep this parent-owned file\n")
        for name in parent_devcontainer_files:
            path = devcontainer / name
            self.assertTrue(path.is_file() and not path.is_symlink(), name)
            self.assertEqual(path.read_text(encoding="utf-8"), "legacy wrapper\n")

        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("shared surface is in sync", check.stdout)
        self.assertEqual(
            template_sentinel.read_text(encoding="utf-8"),
            "keep parent templates\n",
        )
        self.assertEqual(
            tools_sentinel.read_text(encoding="utf-8"),
            "keep parent tools\n",
        )
        resolved_check = self.run_resolved_sync(root, "check")
        self.assertEqual(
            resolved_check.returncode,
            0,
            resolved_check.stdout + resolved_check.stderr,
        )

    def test_empty_copy_and_regular_specs_preserve_parent_root(self) -> None:
        """Zero copy/regular specs never resolve a blank target to the fixture root."""
        root = self.clone_parent_fixture()
        sentinel = root / "parent-sentinel.txt"
        sentinel.write_text("preserve parent root\n", encoding="utf-8")

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(root.is_dir())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve parent root\n")
        self.assertTrue((root / "vendor" / "agent-canon").is_dir())

    def test_diverged_transition_path_is_preserved_without_blocking(self) -> None:
        """Preserve parent-owned divergence while migrating every known identity."""
        root = self.clone_parent_fixture(activate_transition=True)
        root_tools = root / "tools"
        exact_copy = root_tools / "sync_agent_canon.sh"
        diverged = root_tools / "agent_tools" / "surface_manifest.py"
        self.write_file(diverged, "# parent-owned implementation\n")

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("update_transition[", result.stdout)
        self.assertTrue(exact_copy.exists())
        self.assertTrue((root_tools / "agent_tools" / "update_agent_canon.sh").exists())
        self.assertEqual(
            diverged.read_text(encoding="utf-8"),
            "# parent-owned implementation\n",
        )
        self.assertTrue((root_tools / "agent-canon").is_symlink())
        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_transition_uses_history_bound_git_index_mode(self) -> None:
        """Preserve byte-identical content whose tracked mode is not historical."""
        root = self.clone_parent_fixture(activate_transition=True)
        destination = root / "tools" / "sync_agent_canon.sh"
        self.git(root, "update-index", "--chmod=-x", "tools/sync_agent_canon.sh")

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("update_transition[", result.stdout)
        self.assertTrue(destination.is_file())

    def test_unknown_symlink_identity_is_preserved(self) -> None:
        """Do not widen a regular-file history identity through symlink resolution."""
        root = self.clone_parent_fixture(activate_transition=True)
        destination = root / "tools" / "agent_tools" / "update_agent_canon.sh"
        destination.unlink()
        target = "../../vendor/agent-canon/tools/update_agent_canon.sh"
        destination.symlink_to(target)
        self.git(root, "add", destination.relative_to(root).as_posix())

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(os.readlink(destination), target)
        self.assertNotIn("update_transition[", result.stdout)

    def test_parent_can_own_retired_names_after_transition(self) -> None:
        """A completed transition does not create a permanent absent-path gate."""
        root = self.clone_parent_fixture(activate_transition=True)
        first = self.run_sync(root, "link-root")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.git(root, "add", "-A")
        self.git(root, "commit", "-m", "integrate transition-aware AgentCanon")

        for path in LEGACY_ROOT_PROJECTIONS:
            self.write_file(root / path, f"parent owns {path}\n")
        self.git(root, "add", "-A")
        self.git(root, "commit", "-m", "add parent-owned tool paths")

        second = self.run_sync(root, "link-root")
        check = self.run_sync(root, "check")

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        for path in LEGACY_ROOT_PROJECTIONS:
            self.assertEqual((root / path).read_text(encoding="utf-8"), f"parent owns {path}\n")

    def test_transition_move_failure_restores_every_candidate(self) -> None:
        """A failed move rolls back earlier moves instead of partially deleting."""
        root = self.clone_parent_fixture(activate_transition=True)
        wrapper_dir = root / "test-bin"
        wrapper_dir.mkdir()
        count_path = root / "mv-count"
        real_mv = shutil.which("mv")
        self.assertIsNotNone(real_mv)
        wrapper = wrapper_dir / "mv"
        self.write_file(
            wrapper,
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'count="$(cat "$TEST_MV_COUNT" 2>/dev/null || printf 0)"\n'
            'count="$((count + 1))"\n'
            'printf "%s\\n" "$count" >"$TEST_MV_COUNT"\n'
            'if [ "$count" -eq 2 ]; then exit 91; fi\n'
            f'exec "{real_mv}" "$@"\n',
        )
        wrapper.chmod(0o755)

        result = self.run_sync(
            root,
            "link-root",
            env_overrides={
                "PATH": f"{wrapper_dir}{os.pathsep}{os.environ['PATH']}",
                "TEST_MV_COUNT": str(count_path),
            },
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(count_path.exists())
        for path in LEGACY_ROOT_PROJECTIONS:
            self.assertTrue((root / path).is_file(), path)
        self.assertTrue((root / "tools" / "agent-canon").is_symlink())

    def test_removed_legacy_surface_preserves_unknown_mirror(self) -> None:
        """Known retired mirrors are removed while unknown mirrors remain untouched."""
        root = self.clone_parent_fixture()
        retired = root / "tests" / "tools" / "test_check_markdown_math.py"
        retired.parent.mkdir(parents=True, exist_ok=True)
        retired.symlink_to(
            root / "vendor" / "agent-canon" / "tests" / "tools" / "test_check_markdown_math.py"
        )
        unknown = root / "tests" / "tools" / "test_unknown_mirror.py"
        unknown.symlink_to(
            root / "vendor" / "agent-canon" / "tests" / "tools" / "test_check_markdown_math.py"
        )
        regular = root / "tests" / "tools" / "parent-owned.txt"
        regular.write_text("keep parent file\n", encoding="utf-8")

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(retired.exists(), "exact retired symlink must be removed")
        self.assertFalse(retired.is_symlink(), "exact retired symlink must be removed")
        self.assertTrue(unknown.is_symlink(), "unknown mirror must not be removed")
        self.assertEqual(regular.read_text(encoding="utf-8"), "keep parent file\n")

        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_all_retired_test_fixture_and_note_descendants_are_pruned(self) -> None:
        """Prune the 83 known descendants while preserving parent notes and tools."""
        root = self.clone_parent_fixture()
        retired_paths = self.retired_descendant_paths()
        self.assertEqual(len(retired_paths), 83)
        self.assertIn("tests/fixtures/python_algorithm_contract", retired_paths)
        self.assertEqual(
            sum(path.startswith("notes/") for path in retired_paths),
            27,
        )

        notes_hub = root / "notes" / "README.md"
        project_note = root / "notes" / "project-note.md"
        self.write_file(notes_hub, "parent note hub\n")
        self.write_file(project_note, "parent project note\n")
        for relative_path in retired_paths:
            destination = root / relative_path
            source = root / "vendor" / "agent-canon" / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(os.path.relpath(source, destination.parent))

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for relative_path in retired_paths:
            self.assertFalse(os.path.lexists(root / relative_path), relative_path)
        self.assertEqual(notes_hub.read_text(encoding="utf-8"), "parent note hub\n")
        self.assertEqual(project_note.read_text(encoding="utf-8"), "parent project note\n")

        public_tools = root / "tools" / "agent-canon"
        self.assertTrue(public_tools.is_symlink())
        self.assertEqual(os.readlink(public_tools), "../vendor/agent-canon/tools")
        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_removed_legacy_devcontainer_symlink_is_removed(self) -> None:
        """A stale top-level .devcontainer symlink is removed without projection."""
        root = self.clone_parent_fixture()
        devcontainer = root / ".devcontainer"
        devcontainer.symlink_to("vendor/agent-canon/.devcontainer")

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(devcontainer))

    def test_regular_parent_devcontainer_directory_and_json_are_preserved(self) -> None:
        """Parent-owned devcontainer directories keep non-canonical file identities."""
        root = self.clone_parent_fixture()
        devcontainer = root / ".devcontainer"
        devcontainer.mkdir()
        marker = devcontainer / "parent-owned-marker.txt"
        marker.write_text("keep this directory\n", encoding="utf-8")
        dev_json = devcontainer / "devcontainer.json"
        dev_json.write_text("{\"parent\": true}\n", encoding="utf-8")

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(devcontainer.is_dir() and not devcontainer.is_symlink())
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep this directory\n")
        self.assertEqual(dev_json.read_text(encoding="utf-8"), '{"parent": true}\n')

    def test_retired_direct_unrelated_symlinks_are_preserved(self) -> None:
        """Retired names preserve unrelated absolute and relative symlinks."""
        root = self.clone_parent_fixture()
        self.assertEqual(
            self.run_sync(root, "link-root").returncode,
            0,
        )
        absolute_target = root.parent / "unrelated-absolute-target"
        relative_target = root.parent / "unrelated-relative-target"
        absolute_target.write_text("absolute parent target\n", encoding="utf-8")
        relative_target.write_text("relative parent target\n", encoding="utf-8")
        absolute_link = root / ".agents"
        relative_link = root / "agents"
        absolute_link.symlink_to(absolute_target)
        relative_link.symlink_to("../unrelated-relative-target")

        result = self.run_sync(root, "link-root")
        check = self.run_sync(root, "check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertTrue(absolute_link.is_symlink())
        self.assertEqual(os.readlink(absolute_link), str(absolute_target))
        self.assertTrue(relative_link.is_symlink())
        self.assertEqual(os.readlink(relative_link), "../unrelated-relative-target")

    def test_retired_direct_agentcanon_symlink_is_removed(self) -> None:
        """Live AgentCanon targets at retired names are removed by link-root."""
        root = self.clone_parent_fixture()
        self.assertEqual(
            self.run_sync(root, "link-root").returncode,
            0,
        )
        retired = root / ".agents"
        retired.symlink_to("vendor/agent-canon/README.md")

        result = self.run_sync(root, "link-root")
        check = self.run_sync(root, "check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(retired))
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_absolute_agentcanon_symlink_is_removed(self) -> None:
        """An absolute AgentCanon target is removed at a retired name."""
        root = self.clone_parent_fixture()
        self.assertEqual(
            self.run_sync(root, "link-root").returncode,
            0,
        )
        retired = root / ".codex" / "hooks"
        retired.symlink_to((root / "vendor" / "agent-canon" / "README.md").resolve())

        result = self.run_sync(root, "link-root")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(retired))

    def test_broken_agentcanon_traversal_symlink_is_flagged_then_removed(self) -> None:
        """Canonical traversal targets fail check and are removed by link-root."""
        root = self.clone_parent_fixture()
        self.assertEqual(
            self.run_sync(root, "link-root").returncode,
            0,
        )
        retired = root / "agents"
        retired.symlink_to("vendor/agent-canon/../agent-canon/missing-file")

        preflight = self.run_sync(root, "check")
        result = self.run_sync(root, "link-root")

        self.assertNotEqual(preflight.returncode, 0)
        self.assertIn("absent[agents]=present", preflight.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(retired))


if __name__ == "__main__":
    unittest.main()
