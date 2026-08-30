"""Focused tests for the declarative AgentCanon tool dependency model."""

# @dependency-start
# contract test
# responsibility Verifies schema, merge, order, security, and receipt semantics for the shared tool image.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md bootstrap dependency contract
# upstream implementation ../../tools/analysis/dependencies/dependency_plan.py typed dependency engine
# downstream implementation ../../bootstrap/container/image/dependencies.toml canonical manifest inventory
# @dependency-end

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

from tools.runtime.container import devcontainer_dependencies as dependency_module
from tools.runtime.container.devcontainer_dependencies import (
    BASE_CAPABILITIES,
    CommandCapability,
    CommandProvenance,
    DependencyError,
    EnvironmentBoundaryModel,
    Installer,
    LoadedManifest,
    ManifestRole,
    ManifestSource,
    RuntimeIdentity,
    _parse_dpkg_owned_paths,
    _repository_package_filename,
    _repository_packages_url,
    build_parser,
    build_plan,
    check_python_source_safety,
    classify_command,
    image_install_plan,
    image_verify_plan,
    install_plan,
    load_plan,
    manifest_sources,
    parse_record,
    safe_extract_tar,
    select_record_ids,
    validate_runtime_identity,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "tools" / "runtime" / "container" / "devcontainer_dependencies.py"
_PARENT_BOUNDARY_PATH_KEYS = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
)


def init_authentic_git(root: Path, *, remote: str = "https://example.invalid/fixture.git") -> None:
    """Create the minimal authenticated Git parent used by side-effect fixtures."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main", str(root)], check=True
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Fixture Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"],
        check=True,
    )
    marker = root / ".fixture-root"
    marker.write_text("authenticated fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", ".fixture-root"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "--quiet", "-m", "fixture root"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", remote], check=True
    )


def default_verification(
    record_id: str,
    method: str,
    version: str,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one valid owner-specific verification fixture."""
    if method == "apt-package":
        return {"kind": "apt-package"}
    if method == "apt-repository":
        return {"kind": "apt-repository"}
    if method == "npm-global":
        return {
            "kind": "npm-package",
            "executable": record_id,
            "args": ["--version"],
            "output_contains": version,
        }
    if method == "pipx":
        return {
            "kind": "pipx-package",
            "executable": record_id,
            "args": ["--version"],
            "output_contains": version,
        }
    if method == "release-asset":
        return {
            "kind": "absolute-executable",
            "path": fields.get("destination", f"/usr/local/bin/{record_id}"),
            "args": ["--version"],
            "output_contains": version.lstrip("v"),
        }
    if method == "rust-toolchain":
        return {"kind": "rust-toolchain"}
    if method == "lean-toolchain":
        return {"kind": "lean-toolchain"}
    if method == "cargo-source-build":
        return {
            "kind": "cargo-binary",
            "path": f"target/release/{record_id}",
            "args": ["--version"],
            "output_contains": version,
        }
    if method == "browser-install":
        return {
            "kind": "browser-executable",
            "executable_globs": ["chromium-*/chrome-linux/chrome"],
            "args": ["--version"],
            "output_contains": "Google Chrome for Testing",
        }
    raise AssertionError(f"unsupported fixture method: {method}")


def record(
    record_id: str,
    *,
    method: str = "npm-global",
    deps: list[str] | None = None,
    provides: list[str] | None = None,
    version: str = "1.0.0",
    source: str = "https://registry.example.test/package",
    **extra: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": record_id,
        "package": record_id,
        "method": method,
        "version": version,
        "source": source,
        "deps": deps or [],
        "provides": provides or [record_id],
        "failure_policy": "fail",
    }
    value.update(extra)
    value.setdefault(
        "verification",
        default_verification(record_id, method, version, value),
    )
    return value


def render_toml(value: object) -> str:
    """Render the small TOML value subset used by these fixtures."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(f"{key} = {render_toml(item)}" for key, item in value.items())
            + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(render_toml(item) for item in value) + "]"
    return json.dumps(value)


def write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    """Write a small TOML fixture without depending on a TOML writer."""
    lines = [
        'schema = "agent-canon.tool-dependencies"',
        "schema_version = 2",
        "",
    ]
    if records:
        for item in records:
            lines.append("[[records]]")
            for key, value in item.items():
                lines.append(f"{key} = {render_toml(value)}")
            lines.append("")
    else:
        lines.append("records = []")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def loaded_manifest(
    path: Path,
    records: tuple[Any, ...],
    *,
    role: ManifestRole = ManifestRole.CANONICAL,
) -> LoadedManifest:
    """Build a loaded fixture with an explicit structural manifest role."""
    return LoadedManifest(ManifestSource(path, role), records)


class FakeRunner:
    """Capture argv calls without performing installs or network work."""

    def __init__(
        self,
        fail_on: str | None = None,
        fail_once_on: str | None = None,
        emulate_non_root_sudo: bool = False,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str] | None] = []
        self.fail_on = fail_on
        self.fail_once_on = fail_once_on
        self.emulate_non_root_sudo = emulate_non_root_sudo
        self.ownership_lists: dict[str, tuple[str, ...]] = {}
        self.resolved_paths: dict[str, str] = {}
        self.virtual_executables: set[str] = set()
        self.non_executable_paths: set[str] = set()

    def resolve_executable(self, path: Path) -> Path:
        """Resolve virtual symlink targets for deterministic ownership fixtures."""
        return Path(self.resolved_paths.get(str(path), str(path)))

    def is_regular_executable(self, path: Path) -> bool:
        """Model executable file state without touching host `/usr` paths."""
        path_text = str(path)
        if path_text in self.non_executable_paths:
            return False
        return path_text in self.virtual_executables or path_text.startswith("/usr/bin/")

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output
        command = tuple(argv)
        if self.emulate_non_root_sudo and privileged:
            command = ("sudo", *command)
        self.calls.append(command)
        self.environments.append(dict(env) if env is not None else None)
        if self.fail_once_on and (
            command[0] == self.fail_once_on
            or Path(command[0]).name == self.fail_once_on
        ):
            self.fail_once_on = None
            raise subprocess.CalledProcessError(1, command)
        if self.fail_on and (
            command[0] == self.fail_on or Path(command[0]).name == self.fail_on
        ):
            raise subprocess.CalledProcessError(1, command)
        if Path(command[0]).name == "dpkg-query" and command[1:2] == ("--show",):
            package = command[-1]
            return subprocess.CompletedProcess(
                command,
                0,
                f"install ok installed\t1.0.0\t{package}\n",
                "",
            )
        if command[:2] == ("/usr/bin/dpkg-query", "--listfiles"):
            package = command[-1]
            owned = self.ownership_lists.get(package, (f"/usr/bin/{package}",))
            return subprocess.CompletedProcess(command, 0, "\n".join(owned) + "\n", "")
        if (
            Path(command[0]).name == "npm"
            and command[1:3] == ("ls", "--global")
            and "--json" in command
        ):
            package = command[-1]
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"dependencies": {package: {"version": "1.0.0"}}}),
                "",
            )
        if command[:2] == ("pipx", "runpip") and command[3:4] == ("show",):
            return subprocess.CompletedProcess(
                command,
                0,
                f"Name: {command[-1]}\nVersion: 1.0.0\n",
                "",
            )
        if command[:2] == ("git", "-C"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ("rustup", "show", "active-toolchain"):
            return subprocess.CompletedProcess(command, 0, "1.89.0 (default)\n", "")
        if command[:3] == ("rustup", "toolchain", "list"):
            return subprocess.CompletedProcess(command, 0, "1.89.0 (default)\n", "")
        if command[:3] == ("rustup", "component", "list"):
            return subprocess.CompletedProcess(
                command,
                0,
                "rust-src-x86_64-unknown-linux-gnu (installed)\n"
                "rustfmt-x86_64-unknown-linux-gnu (installed)\n"
                "clippy-x86_64-unknown-linux-gnu (installed)\n",
                "",
            )
        if command[:2] == ("elan", "show"):
            return subprocess.CompletedProcess(
                command,
                0,
                "leanprover/lean4:v4.30.0 (default)\n"
                "Lean (version 4.30.0, stable)\n",
                "",
            )
        if command[:3] == ("elan", "toolchain", "list"):
            return subprocess.CompletedProcess(
                command, 0, "leanprover/lean4:v4.30.0\n", ""
            )
        if Path(command[0]).name == "chrome":
            return subprocess.CompletedProcess(
                command, 0, "Google Chrome for Testing 149.0.7827.55\n", ""
            )
        return subprocess.CompletedProcess(command, 0, "1.0.0\n", "")


class ActiveSourceCargoRunner(FakeRunner):
    """Build a source-local test binary without consulting repository metadata."""

    def __init__(self) -> None:
        super().__init__()
        self.cargo_builds = 0

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = tuple(argv)
        if command[:2] == ("cargo", "build"):
            manifest = Path(command[command.index("--manifest-path") + 1])
            binary = manifest.parent / "target" / "release" / "agent-canon"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text(
                "#!/usr/bin/env sh\nprintf '%s\\n' 'agent-canon 0.1.0'\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            self.cargo_builds += 1
        result = super().run(
            argv,
            cwd=cwd,
            privileged=privileged,
            capture_output=capture_output,
            env=env,
        )
        if Path(command[0]).name == "agent-canon":
            return subprocess.CompletedProcess(command, 0, "agent-canon 0.1.0\n", "")
        return result


class MismatchedCommitRunner(FakeRunner):
    """Return a different source HEAD to exercise fixed-commit rejection."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = super().run(
            argv,
            cwd=cwd,
            privileged=privileged,
            capture_output=capture_output,
            env=env,
        )
        command = tuple(argv)
        if command[:2] == ("git", "-C"):
            return subprocess.CompletedProcess(command, 0, f"{'b' * 40}\n", "")
        return result


class LeanToolchainRetryRunner(FakeRunner):
    """Model an install that leaves a live Lean toolchain before failing."""

    def __init__(self) -> None:
        super().__init__()
        self.lean_toolchain_installed = False
        self.fail_install_once = True

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = tuple(argv)
        result = super().run(
            argv,
            cwd=cwd,
            privileged=privileged,
            capture_output=capture_output,
            env=env,
        )
        if command[:3] == ("elan", "toolchain", "list"):
            if not self.lean_toolchain_installed:
                return subprocess.CompletedProcess(command, 0, "", "")
            return result
        if command[:3] == ("elan", "toolchain", "install"):
            self.lean_toolchain_installed = True
            if self.fail_install_once:
                self.fail_install_once = False
                raise subprocess.CalledProcessError(1, command)
        return result


class DependencyModelTests(unittest.TestCase):
    def setUp(self) -> None:
        """Keep synthetic repository boundaries independent of the outer test runner."""
        super().setUp()
        saved = {key: os.environ.get(key) for key in _PARENT_BOUNDARY_PATH_KEYS}
        for key in _PARENT_BOUNDARY_PATH_KEYS:
            os.environ.pop(key, None)

        def restore_environment() -> None:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore_environment)

    def test_base_capabilities_include_gnupg_for_repository_bootstrap(self) -> None:
        """A fixed image capability satisfies apt-repository gpg prerequisites."""
        self.assertIn("gnupg", BASE_CAPABILITIES)

    """Exercise schema, merge, order, security, and receipt behavior."""

    def test_repository_manifest_validates_and_dry_run_has_stable_order(self) -> None:
        plan = build_plan(
            (
                loaded_manifest(
                    Path("parent.toml"),
                    (
                        parse_record(
                            record("parent"), path=Path("parent.toml"), index=0
                        ),
                    ),
                    role=ManifestRole.PARENT_OVERLAY,
                ),
                loaded_manifest(
                    Path("vendor.toml"),
                    (
                        parse_record(
                            record("child", deps=["parent"]),
                            path=Path("vendor.toml"),
                            index=0,
                        ),
                    ),
                ),
            )
        )
        self.assertEqual(plan.order, ("parent", "child"))
        dry_run = Installer().dry_run(plan)
        self.assertEqual(dry_run["order"], ["parent", "child"])
        self.assertEqual(
            dry_run["actions"][0]["verification"]["kind"],
            "npm-package",
        )
        self.assertNotIn("commands", dry_run["actions"][0])

    def test_plan_fingerprint_is_path_independent_but_role_bound(self) -> None:
        parsed = parse_record(
            record("tool", method="apt-package"),
            path=Path("one.toml"),
            index=0,
        )
        first = build_plan(
            (loaded_manifest(Path("/tmp/first/.devcontainer/dependencies.toml"), (parsed,)),)
        )
        second = build_plan(
            (loaded_manifest(Path("/tmp/second/.devcontainer/dependencies.toml"), (parsed,)),)
        )
        parent_role = build_plan(
            (
                loaded_manifest(
                    Path("/tmp/second/.devcontainer/dependencies.toml"),
                    (parsed,),
                    role=ManifestRole.PARENT_OVERLAY,
                ),
            )
        )

        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertNotEqual(first.fingerprint, parent_role.fingerprint)
        self.assertEqual(first.source_roles, (ManifestRole.CANONICAL.value,))

    def test_record_selection_is_deterministic_and_provider_closed(self) -> None:
        provider = parse_record(
            record("provider", method="apt-package", provides=["runtime"]),
            path=Path("fixture.toml"),
            index=0,
        )
        selected = parse_record(
            record("selected", method="apt-package", deps=["runtime"]),
            path=Path("fixture.toml"),
            index=1,
        )
        unrelated = parse_record(
            record("unrelated", method="apt-package"),
            path=Path("fixture.toml"),
            index=2,
        )
        plan = build_plan(
            (loaded_manifest(Path("fixture.toml"), (provider, selected, unrelated)),)
        )

        self.assertEqual(select_record_ids(plan, ("selected",)), ("provider", "selected"))
        self.assertEqual(
            select_record_ids(plan, ("selected", "provider", "selected")),
            ("provider", "selected"),
        )
        self.assertEqual(select_record_ids(plan, None), plan.order)
        with self.assertRaisesRegex(DependencyError, "at least one"):
            select_record_ids(plan, [])
        with self.assertRaisesRegex(DependencyError, "at least one"):
            select_record_ids(plan, ())
        with self.assertRaisesRegex(DependencyError, "empty record IDs"):
            select_record_ids(plan, [""])

    def test_image_install_and_verify_are_immutable_and_read_only(self) -> None:
        parsed = parse_record(
            record("image-tool", method="apt-package"),
            path=Path("fixture.toml"),
            index=0,
        )
        unrelated = parse_record(
            record("unrelated", method="apt-package"),
            path=Path("fixture.toml"),
            index=1,
        )
        plan = build_plan(
            (loaded_manifest(Path("fixture.toml"), (parsed, unrelated)),)
        )
        identity = RuntimeIdentity("ubuntu", "22.04", "linux/amd64")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            image_root = root / "image-dependencies"
            install_runner = FakeRunner()
            self.assertEqual(
                image_install_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=install_runner,
                    identity=identity,
                ),
                ("image-tool",),
            )
            before = {
                path.relative_to(image_root): path.read_bytes()
                for path in image_root.rglob("*")
                if path.is_file()
            }
            verify_runner = FakeRunner()
            self.assertEqual(
                image_verify_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=verify_runner,
                ),
                ("image-tool",),
            )
            self.assertEqual(
                image_verify_plan(
                    plan,
                    workspace=root,
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                ),
                ("image-tool",),
            )
            with self.assertRaisesRegex(DependencyError, "at least one"):
                image_verify_plan(
                    plan,
                    workspace=root,
                    records=[],
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                )
            after = {
                path.relative_to(image_root): path.read_bytes()
                for path in image_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertNotIn("apt-get", [call[0] for call in verify_runner.calls])
            plan_path = image_root / "plan.json"
            plan_path.chmod(0o644)
            with self.assertRaisesRegex(DependencyError, "rebuild-required"):
                image_verify_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                )
            plan_path.chmod(0o444)
            receipts_path = image_root / "receipts"
            receipts_path.chmod(0o755)
            with self.assertRaisesRegex(DependencyError, "rebuild-required"):
                image_verify_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                )
            receipts_path.chmod(0o555)
            with self.assertRaisesRegex(DependencyError, "rebuild-required"):
                image_verify_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=FakeRunner(fail_on="dpkg-query"),
                )
            with self.assertRaisesRegex(DependencyError, "already exists"):
                image_install_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                    identity=identity,
                )

            image_plan = json.loads(
                (image_root / "plan.json").read_text(encoding="utf-8")
            )
            image_plan["plan_fingerprint"] = "0" * 64
            (image_root / "plan.json").chmod(0o644)
            (image_root / "plan.json").write_text(
                json.dumps(image_plan), encoding="utf-8"
            )
            (image_root / "plan.json").chmod(0o444)
            with self.assertRaisesRegex(DependencyError, "rebuild-required"):
                image_verify_plan(
                    plan,
                    workspace=root,
                    records=("image-tool",),
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                )

    def test_image_install_requires_root_and_image_safe_method_whitelist(self) -> None:
        unsafe = parse_record(
            record(
                "unsafe",
                method="browser-install",
                package="chromium",
                browser="chromium",
                browser_cache_path="/usr/local/share/agent-canon-browser-cache",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (unsafe,)),))
        identity = RuntimeIdentity("ubuntu", "22.04", "linux/amd64")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(dependency_module.os, "geteuid", return_value=1000):
                with self.assertRaisesRegex(DependencyError, "euid=0"):
                    image_install_plan(
                        plan,
                        workspace=root,
                        identity=identity,
                        runner=FakeRunner(),
                    )
            image_root = root / "image-dependencies"
            with self.assertRaisesRegex(DependencyError, "image-safe whitelist"):
                image_install_plan(
                    plan,
                    workspace=root,
                    _test_image_root=image_root,
                    identity=identity,
                    runner=FakeRunner(),
                )
            self.assertFalse(image_root.exists())

    def test_image_safe_gate_accepts_only_immutable_rust_and_cargo_records(self) -> None:
        """Image installs admit pinned pipx, Rust, and Cargo records only."""
        pipx = parse_record(
            record(
                "python-tool",
                method="pipx",
                source="https://pypi.example.test/simple",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        rust = parse_record(
            record(
                "rust-toolchain",
                method="rust-toolchain",
                version="1.89.0",
                source="https://static.rust-lang.org/dist",
                components=["rust-analyzer"],
            ),
            path=Path("fixture.toml"),
            index=1,
        )
        cargo = parse_record(
            record(
                "agent-canon-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://github.com/example/agent-canon.git",
                source_identity="canonical-snapshot",
                source_tree_sha256="a" * 64,
                cargo_lock_sha256="b" * 64,
                locked=True,
            ),
            path=Path("fixture.toml"),
            index=2,
        )
        active = parse_record(
            record(
                "active-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://github.com/example/agent-canon.git",
                source_identity="active-source",
                locked=True,
            ),
            path=Path("fixture.toml"),
            index=3,
        )

        self.assertTrue(dependency_module._image_record_is_safe(pipx))
        self.assertTrue(dependency_module._image_record_is_safe(rust))
        self.assertTrue(dependency_module._image_record_is_safe(cargo))
        self.assertFalse(dependency_module._image_record_is_safe(active))

    def test_image_owned_full_plan_publishes_final_binary_only_for_cargo(self) -> None:
        """Image final-binary publication does not run for apt or Rust records."""
        apt = parse_record(
            record("apt-tool", method="apt-package"),
            path=Path("fixture.toml"),
            index=0,
        )
        rust = parse_record(
            record(
                "rust-toolchain",
                method="rust-toolchain",
                version="1.89.0",
                source="https://static.rust-lang.org/dist",
            ),
            path=Path("fixture.toml"),
            index=1,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (apt, rust)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_root = root / "image-layer"
            installer = Installer(
                FakeRunner(), image_owned=True, image_owned_root=image_root
            )
            with mock.patch.object(installer, "_publish_final_binary") as publish:
                self.assertEqual(
                    installer.install(
                        plan,
                        workspace=root,
                        receipts=image_root / "receipts",
                        final_binary_dir=Path("/usr/local/bin"),
                    ),
                    ("apt-tool", "rust-toolchain"),
                )
            publish.assert_not_called()

            cargo = parse_record(
                record(
                    "agent-canon-cli",
                    method="cargo-source-build",
                    source="rust/agent-canon",
                    repo="https://github.com/example/agent-canon.git",
                    source_identity="canonical-snapshot",
                    source_tree_sha256="a" * 64,
                    cargo_lock_sha256="b" * 64,
                    locked=True,
                ),
                path=Path("fixture.toml"),
                index=2,
            )
            cargo_plan = build_plan(
                (loaded_manifest(Path("fixture.toml"), (cargo,)),)
            )
            with self.assertRaisesRegex(
                DependencyError, "requires a final binary directory"
            ):
                Installer(
                    FakeRunner(), image_owned=True, image_owned_root=image_root
                ).install(
                    cargo_plan,
                    workspace=root,
                    receipts=image_root / "missing-receipts",
                )

    def test_image_install_failure_does_not_publish_target_and_freezes_tree(self) -> None:
        parsed = parse_record(
            record("image-tool", method="apt-package"),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
        identity = RuntimeIdentity("ubuntu", "22.04", "linux/amd64")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            failed_root = root / "failed-image"
            with self.assertRaises(DependencyError):
                image_install_plan(
                    plan,
                    workspace=root,
                    _test_image_root=failed_root,
                    runner=FakeRunner(fail_on="apt-get"),
                    identity=identity,
                )
            self.assertFalse(failed_root.exists())

            publish_failure_root = root / "publish-failure"
            original_replace = dependency_module.os.replace

            def fail_target_publish(
                source: object, destination: object, **kwargs: object
            ) -> None:
                if destination == publish_failure_root:
                    raise OSError("publish")
                original_replace(source, destination, **kwargs)

            with mock.patch.object(
                dependency_module.os, "replace", side_effect=fail_target_publish
            ):
                with self.assertRaises(OSError):
                    image_install_plan(
                        plan,
                        workspace=root,
                        _test_image_root=publish_failure_root,
                        runner=FakeRunner(),
                        identity=identity,
                    )
            self.assertFalse(publish_failure_root.exists())

            image_root = root / "image-dependencies"
            image_install_plan(
                plan,
                workspace=root,
                _test_image_root=image_root,
                runner=FakeRunner(),
                identity=identity,
            )
            for path in (image_root, *image_root.rglob("*")):
                observed = path.stat()
                self.assertEqual(observed.st_uid, os.geteuid())
                self.assertEqual(observed.st_gid, os.getegid())
                expected_mode = (
                    0o555 if stat.S_ISDIR(observed.st_mode) else 0o444
                )
                self.assertEqual(stat.S_IMODE(observed.st_mode), expected_mode)

    def test_image_install_rejects_symlinked_parent_component(self) -> None:
        parsed = parse_record(
            record("image-tool", method="apt-package"),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
        identity = RuntimeIdentity("ubuntu", "22.04", "linux/amd64")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_parent = root / "real"
            real_parent.mkdir()
            linked_parent = root / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(DependencyError, "must not be a symlink"):
                image_install_plan(
                    plan,
                    workspace=root,
                    _test_image_root=linked_parent / "image-dependencies",
                    runner=FakeRunner(),
                    identity=identity,
                )
            self.assertFalse((real_parent / "image-dependencies").exists())

    def test_image_verify_apt_repository_disables_network_digest(self) -> None:
        fingerprint = "2C6106201985B60E6C7AC87323F3D4EA75716059"
        parsed = parse_record(
            record(
                "repo",
                method="apt-repository",
                key_url="https://apt.example.test/key",
                key_fingerprint=fingerprint,
                repository_suite="jammy",
                repository_components=["main"],
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()
        installer = Installer(runner)
        keyring = Path("/etc/apt/keyrings/repo.gpg")
        expected_source = Installer._apt_repository_line(parsed, keyring)
        result = subprocess.CompletedProcess(
            ("gpg",), 0, f"fpr:::::::::{fingerprint}:\n", ""
        )
        with (
            mock.patch.object(installer, "_verify_apt_package"),
            mock.patch.object(installer, "_capture", return_value=result),
            mock.patch.object(Path, "is_symlink", return_value=False),
            mock.patch.object(Path, "is_file", return_value=True),
            mock.patch.object(Path, "read_text", return_value=expected_source),
            mock.patch.object(
                dependency_module, "_download", side_effect=AssertionError("network")
            ),
        ):
            installer._verify_apt_repository(
                parsed,
                workspace=Path("/tmp/workspace"),
                allow_network=False,
            )

    def test_image_freeze_requests_production_root_ownership_and_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            receipts = staging / "receipts"
            receipts.mkdir(parents=True)
            (staging / "plan.json").write_text("{}", encoding="utf-8")
            (receipts / "tool.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(dependency_module.os, "chown") as chown:
                dependency_module._freeze_image_tree(
                    staging,
                    owner_uid=0,
                    owner_gid=0,
                )
            self.assertEqual(chown.call_count, 4)
            self.assertTrue(
                all(call.args[1:] == (0, 0) for call in chown.call_args_list)
            )
            self.assertEqual(stat.S_IMODE(staging.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(receipts.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE((staging / "plan.json").stat().st_mode), 0o444)
            self.assertEqual(
                stat.S_IMODE((receipts / "tool.json").stat().st_mode), 0o444
            )

    def test_image_verify_plan_apt_repository_is_read_only_and_offline(self) -> None:
        parsed = parse_record(
            record(
                "repo",
                method="apt-repository",
                key_url="https://apt.example.test/key",
                key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
                platform="linux/amd64",
                repository_suite="jammy",
                repository_components=["main"],
                repository_packages_sha256="a" * 64,
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
        identity = RuntimeIdentity("ubuntu", "22.04", "linux/amd64")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            image_root = root / "image-dependencies"
            with (
                mock.patch.object(Installer, "install_record"),
                mock.patch.object(Installer, "verify", return_value=None) as verify,
                mock.patch.object(
                    dependency_module,
                    "_download",
                    side_effect=AssertionError("network"),
                ),
            ):
                image_install_plan(
                    plan,
                    workspace=root,
                    _test_image_root=image_root,
                    runner=FakeRunner(),
                    identity=identity,
                )
                verify.reset_mock()
                self.assertEqual(
                    image_verify_plan(
                        plan,
                        workspace=root,
                        _test_image_root=image_root,
                        runner=FakeRunner(),
                    ),
                    ("repo",),
                )
                verify.assert_called_once()
                self.assertFalse(verify.call_args.kwargs["allow_network"])

    def test_image_commands_accept_records_without_root_override(self) -> None:
        args = build_parser().parse_args(
            [
                "image-install",
                "--records",
                "provider,selected",
                "--records",
                "unrelated",
            ]
        )
        self.assertEqual(args.records, [["provider,selected"], ["unrelated"]])
        self.assertIsNone(build_parser().parse_args(["image-install"]).records)

    def test_cli_omitted_records_passes_none_and_blank_records_fail(self) -> None:
        parsed = parse_record(
            record("image-tool", method="apt-package"),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(dependency_module, "_cli_plan", return_value=plan),
                mock.patch.object(
                    dependency_module,
                    "image_install_plan",
                    return_value=("image-tool",),
                ) as install,
            ):
                self.assertEqual(
                    dependency_module.main(
                        ["image-install", "--workspace", str(root)]
                    ),
                    0,
                )
                self.assertIsNone(install.call_args.kwargs["records"])

            def select_cli_records(plan_arg: Any, **kwargs: Any) -> tuple[str, ...]:
                return select_record_ids(plan_arg, kwargs["records"])

            with (
                mock.patch.object(dependency_module, "_cli_plan", return_value=plan),
                mock.patch.object(
                    dependency_module,
                    "image_install_plan",
                    side_effect=select_cli_records,
                ),
            ):
                self.assertEqual(
                    dependency_module.main(
                        [
                            "image-install",
                            "--workspace",
                            str(root),
                            "--records",
                            "",
                        ]
                    ),
                    1,
                )

    def test_npm_global_uses_oci_image_bin_for_install_and_verification(self) -> None:
        parsed = parse_record(
            record("codex", method="npm-global"),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner(emulate_non_root_sudo=True)
        installer = Installer(runner)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oci_root = root / "usr" / "local"
            oci_bin = oci_root / "bin"
            system_bin = root / "usr" / "bin"
            oci_bin.mkdir(parents=True)
            system_bin.mkdir(parents=True)
            trusted_dirs = (str(oci_bin), str(system_bin))
            trusted_roots = {
                str(oci_bin): str(oci_root),
                str(system_bin): str(root / "usr"),
            }
            trusted_path = os.pathsep.join(trusted_dirs)
            workspace = root / "workspace"
            workspace.mkdir()

            def oci_which(name: str, *, path: str | None = None) -> str:
                self.assertEqual(path, trusted_path)
                return str(oci_bin / name)

            with mock.patch.object(
                dependency_module,
                "NPM_SYSTEM_BIN_DIRS",
                trusted_dirs,
            ), mock.patch.object(
                dependency_module,
                "NPM_TRUSTED_BIN_DIRS",
                trusted_dirs,
            ), mock.patch.object(
                dependency_module,
                "NPM_TRUSTED_BIN_ROOTS",
                trusted_roots,
            ), mock.patch.object(
                dependency_module.shutil, "which", side_effect=oci_which
            ):
                installer.install_record(parsed, workspace=workspace)
                installer.verify(parsed, workspace=workspace)

        install_call = next(
            call
            for call in runner.calls
            if "install" in call and any(Path(item).name == "npm" for item in call)
        )
        self.assertEqual(
            install_call,
            (
                "sudo",
                dependency_module.NPM_ENV_EXECUTABLE,
                f"PATH={trusted_path}",
                f"{oci_bin}/npm",
                "install",
                "--global",
                "--prefix",
                "/usr/local",
                "codex@1.0.0",
            ),
        )
        ls_index = next(
            index
            for index, call in enumerate(runner.calls)
            if call[:2] == (f"{oci_bin}/npm", "ls")
        )
        self.assertEqual(
            runner.calls[ls_index],
            (
                f"{oci_bin}/npm",
                "ls",
                "--global",
                "--prefix",
                "/usr/local",
                "--json",
                "--depth=0",
                "codex",
            ),
        )
        self.assertIsNotNone(runner.environments[ls_index])
        assert runner.environments[ls_index] is not None
        self.assertEqual(runner.environments[ls_index]["PATH"], trusted_path)
        executable_index = next(
            index
            for index, call in enumerate(runner.calls)
            if call == ("codex", "--version")
        )
        self.assertEqual(runner.calls[executable_index], ("codex", "--version"))
        self.assertIsNotNone(runner.environments[executable_index])

    def test_npm_global_rejects_workspace_untrusted_or_missing_node(self) -> None:
        """npm installation fails closed before sudo for unsafe Node resolution."""
        parsed = parse_record(
            record("codex", method="npm-global"),
            path=Path("fixture.toml"),
            index=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oci_root = root / "usr" / "local"
            oci_bin = oci_root / "bin"
            system_bin = root / "usr" / "bin"
            oci_bin.mkdir(parents=True)
            system_bin.mkdir(parents=True)
            trusted_dirs = (str(oci_bin), str(system_bin))
            trusted_roots = {
                str(oci_bin): str(oci_root),
                str(system_bin): str(root / "usr"),
            }
            trusted_path = os.pathsep.join(trusted_dirs)
            cases = (
                (
                    "workspace",
                    {
                        "node": str(root / "node"),
                        "npm": f"{oci_bin}/npm",
                    },
                    "inside workspace",
                ),
                (
                    "untrusted",
                    {
                        "node": "/tmp/agent-canon-untrusted/node",
                        "npm": f"{oci_bin}/npm",
                    },
                    "outside trusted Node/system directories",
                ),
                (
                    "missing-node",
                    {"node": None, "npm": f"{oci_bin}/npm"},
                    "requires a trusted node executable",
                ),
            )
            for name, paths, message in cases:
                with self.subTest(name=name):

                    def fake_which(
                        executable: str, *, path: str | None = None
                    ) -> str | None:
                        self.assertEqual(path, trusted_path)
                        return paths[executable]

                    with (
                        mock.patch.object(
                            dependency_module,
                            "NPM_SYSTEM_BIN_DIRS",
                            trusted_dirs,
                        ),
                        mock.patch.object(
                            dependency_module,
                            "NPM_TRUSTED_BIN_DIRS",
                            trusted_dirs,
                        ),
                        mock.patch.object(
                            dependency_module,
                            "NPM_TRUSTED_BIN_ROOTS",
                            trusted_roots,
                        ),
                        mock.patch.object(
                            dependency_module.shutil,
                            "which",
                            side_effect=fake_which,
                        ),
                    ):
                        with self.assertRaisesRegex(DependencyError, message):
                            Installer(FakeRunner()).install_record(
                                parsed, workspace=root
                            )

    def test_npm_global_rejects_escaped_node_and_npm_symlinks(self) -> None:
        """OCI image bin symlinks cannot resolve into workspace or outside roots."""
        parsed = parse_record(
            record("codex", method="npm-global"),
            path=Path("fixture.toml"),
            index=0,
        )
        system_dirs = dependency_module.NPM_SYSTEM_BIN_DIRS
        system_roots = {
            directory: dependency_module.NPM_TRUSTED_BIN_ROOTS[directory]
            for directory in system_dirs
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                ("node", "inside workspace"),
                ("npm", "escapes trusted Node/system root"),
            )
            for escaped, message in cases:
                with self.subTest(escaped=escaped):
                    case_root = root / escaped
                    oci_root = case_root / "usr" / "local"
                    oci_bin = oci_root / "bin"
                    oci_bin.mkdir(parents=True)
                    workspace = case_root / "workspace"
                    workspace.mkdir()
                    target = (
                        workspace / f"{escaped}-target"
                        if escaped == "node"
                        else Path("/tmp/agent-canon-npm-escaped-target")
                    )
                    if escaped == "node":
                        target.write_text("workspace target\n", encoding="utf-8")
                    escaped_path = oci_bin / escaped
                    escaped_path.symlink_to(target)
                    other = oci_bin / ("npm" if escaped == "node" else "node")
                    other.write_text("oci target\n", encoding="utf-8")

                    trusted_dirs = (str(oci_bin), *system_dirs)
                    trusted_roots = {
                        str(oci_bin): str(oci_root),
                        **system_roots,
                    }

                    def fake_which(
                        executable: str, *, path: str | None = None
                    ) -> str:
                        self.assertEqual(path, os.pathsep.join(trusted_dirs))
                        return str(oci_bin / executable)

                    with (
                        mock.patch.object(
                            dependency_module,
                            "NPM_TRUSTED_BIN_DIRS",
                            trusted_dirs,
                        ),
                        mock.patch.object(
                            dependency_module,
                            "NPM_TRUSTED_BIN_ROOTS",
                            trusted_roots,
                        ),
                        mock.patch.object(
                            dependency_module.shutil, "which", side_effect=fake_which
                        ),
                    ):
                        with self.assertRaisesRegex(DependencyError, message):
                            Installer(FakeRunner()).install_record(
                                parsed, workspace=workspace
                            )

    def test_npm_global_ignores_legacy_nvm_bin(self) -> None:
        """A legacy NVM directory is not a Node resolution source."""
        parsed = parse_record(
            record("codex", method="npm-global"),
            path=Path("fixture.toml"),
            index=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_bin = root / "usr" / "local" / "share" / "nvm" / "current" / "bin"
            legacy_bin.mkdir(parents=True)
            (legacy_bin / "node").write_text("node\n", encoding="utf-8")
            (legacy_bin / "npm").write_text("npm\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            oci_bin = root / "usr" / "local" / "bin"
            oci_bin.mkdir(parents=True)
            trusted_dirs = (str(oci_bin),)
            trusted_roots = {str(oci_bin): str(root / "usr" / "local")}

            with (
                mock.patch.object(
                    dependency_module,
                    "NPM_SYSTEM_BIN_DIRS",
                    trusted_dirs,
                ),
                mock.patch.object(
                    dependency_module,
                    "NPM_TRUSTED_BIN_DIRS",
                    trusted_dirs,
                ),
                mock.patch.object(
                    dependency_module,
                    "NPM_TRUSTED_BIN_ROOTS",
                    trusted_roots,
                ),
            ):
                with self.assertRaisesRegex(
                    DependencyError, "requires a trusted node executable"
                ):
                    Installer(FakeRunner()).install_record(
                        parsed, workspace=workspace
                    )

    def test_pipx_installs_and_verifies_one_isolated_cli(self) -> None:
        """Python CLI records use pipx without a shared pip install surface."""
        parsed = parse_record(
            record(
                "python-tool",
                method="pipx",
                source="https://pypi.example.test/simple",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()
        installer = Installer(runner)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installer.install_record(parsed, workspace=root)
            installer.verify(parsed, workspace=root)

        self.assertIn(
            (
                "pipx",
                "install",
                "--index-url",
                "https://pypi.example.test/simple",
                "python-tool==1.0.0",
            ),
            runner.calls,
        )
        self.assertIn(
            ("pipx", "runpip", "python-tool", "show", "python-tool"),
            runner.calls,
        )

    def test_cargo_source_prefers_vendored_canonical_and_rejects_escape(self) -> None:
        cargo = parse_record(
            record(
                "agent-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://example.test/agent-canon.git",
                commit="a" * 40,
                locked=True,
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        installer = Installer(FakeRunner())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            standalone = root / "rust" / "agent-canon"
            standalone.mkdir(parents=True)
            self.assertEqual(installer._cargo_source(cargo, root), standalone)

            outside = root.parent / f"{root.name}-outside"
            outside.mkdir()
            (root / "rust" / "agent-canon").rmdir()
            (root / "rust").rmdir()
            (root / "rust").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(DependencyError, "escapes workspace"):
                installer._cargo_source(cargo, root)

    def test_fixed_commit_rejects_mismatched_source_head(self) -> None:
        """Explicit commit records retain Git validation and reject source drift."""
        expected_commit = "a" * 40
        cargo = parse_record(
            record(
                "agent-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://example.test/agent-canon.git",
                commit=expected_commit,
                locked=True,
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = MismatchedCommitRunner()
        installer = Installer(runner)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rust" / "agent-canon").mkdir(parents=True)
            with self.assertRaisesRegex(DependencyError, "cargo source commit mismatch"):
                installer.verify(cargo, workspace=root)
        self.assertTrue(any(command[:2] == ("git", "-C") for command in runner.calls))

    def test_schema_rejects_missing_and_unknown_fields(self) -> None:
        value = record("invalid")
        value.pop("failure_policy")
        with self.assertRaisesRegex(DependencyError, "missing fields"):
            parse_record(value, path=Path("fixture.toml"), index=0)
        value = record("invalid", unknown="value")
        with self.assertRaisesRegex(DependencyError, "unknown fields"):
            parse_record(value, path=Path("fixture.toml"), index=0)

    def test_all_methods_and_method_specific_security_fields_are_typed(self) -> None:
        common = {
            "deps": [],
            "provides": ["tool"],
            "failure_policy": "fail",
        }
        values = [
            record("apt", method="apt-package"),
            record(
                "apt-tool",
                method="apt-package",
                verification={
                    "kind": "apt-package",
                    "executable": "apt-tool",
                    "args": ["--version"],
                    "output_contains": "1.0.0",
                },
            ),
            record(
                "repo",
                method="apt-repository",
                key_url="https://example.test/key",
                key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
            ),
            record("npm", method="npm-global"),
            record("python-tool", method="pipx"),
            record(
                "asset",
                method="release-asset",
                checksum="0" * 64,
                asset="tool.tar.gz",
                archive_format="tar.gz",
                extract="tool",
                destination="/usr/local/bin/tool",
                source="https://example.test/releases",
            ),
            record("rust", method="rust-toolchain"),
            record(
                "lean",
                method="lean-toolchain",
                version="leanprover/lean4:v4.30.0",
            ),
            record(
                "cargo",
                method="cargo-source-build",
                repo="https://example.test/repo.git",
                commit="a" * 40,
                locked=True,
                source="rust/agent-canon",
            ),
            record(
                "browser",
                method="browser-install",
                package="chromium",
                browser="chromium",
                browser_cache_path="/usr/local/share/ms-playwright",
            ),
        ]
        for index, value in enumerate(values):
            value.update(common)
            parsed = parse_record(value, path=Path("fixture.toml"), index=index)
            self.assertEqual(parsed.method.value, value["method"])
            self.assertEqual(
                parsed.verification.kind.value,
                value["verification"]["kind"],
            )
        apt_with_owner = parse_record(
            record(
                "apt-owner",
                method="apt-package",
                executable_owner_packages=["apt", "apt-tools"],
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        self.assertEqual(
            apt_with_owner.executable_owner_packages, ("apt", "apt-tools")
        )
        apt_default_owner = parse_record(
            record("apt-default", method="apt-package"), path=Path("fixture.toml"), index=1
        )
        self.assertEqual(apt_default_owner.executable_owner_packages, ("apt-default",))
        self.assertEqual(
            apt_default_owner.payload()["executable_owner_packages"],
            ("apt-default",),
        )
        non_apt_ownerless = parse_record(
            record("npm-default", method="npm-global"),
            path=Path("fixture.toml"),
            index=2,
        )
        self.assertEqual(non_apt_ownerless.executable_owner_packages, ())
        self.assertEqual(non_apt_ownerless.payload()["executable_owner_packages"], ())
        self.assertNotEqual(
            non_apt_ownerless.fingerprint(),
            apt_default_owner.fingerprint(),
        )
        explicit_apt_owner = parse_record(
            record(
                "apt-default",
                method="apt-package",
                executable_owner_packages=["apt-default", "apt-tools"],
            ),
            path=Path("fixture.toml"),
            index=3,
        )
        self.assertEqual(
            explicit_apt_owner.executable_owner_packages,
            ("apt-default", "apt-tools"),
        )

    def test_non_apt_executable_owner_packages_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            DependencyError, "unsupported fields for npm-global: executable_owner_packages"
        ):
            parse_record(
                record(
                    "npm-with-owners",
                    method="npm-global",
                    executable_owner_packages=["npm", "nodejs"],
                ),
                path=Path("fixture.toml"),
                index=0,
            )

    def test_apt_repository_suite_components_digest_and_executable_are_typed(self) -> None:
        """Repository records derive one signed source and Packages index identity."""
        packages = b"Package: clangd-18\nVersion: pinned\n"
        digest = hashlib.sha256(packages).hexdigest()
        package_url = (
            "https://apt.example.test/jammy/pool/main/c/clangd-18/"
            "clangd-18_1.2.3_amd64.deb"
        )
        package_sha = hashlib.sha256(b"immutable deb").hexdigest()
        parsed = parse_record(
            record(
                "clangd-language-server",
                method="apt-repository",
                package="clangd-18",
                version="1:18.1.8~exp1",
                platform="linux/amd64",
                source="https://apt.llvm.org/jammy/",
                repository_suite="llvm-toolchain-jammy-18",
                repository_components=["main"],
                repository_packages_sha256=digest,
                repository_package_url=package_url,
                repository_package_sha256=package_sha,
                key_url="https://apt.llvm.org/llvm-snapshot.gpg.key",
                key_fingerprint="6084F3CF814B57C1CF12EFD515CF4D18AF4F7421",
                verification={
                    "kind": "apt-repository",
                    "executable": "clangd-18",
                    "args": ["--version"],
                    "output_contains": "clangd version 18.1.8",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        self.assertEqual(parsed.repository_suite, "llvm-toolchain-jammy-18")
        self.assertEqual(parsed.repository_components, ("main",))
        self.assertEqual(parsed.repository_packages_sha256, digest)
        self.assertEqual(parsed.repository_package_url, package_url)
        self.assertEqual(parsed.repository_package_sha256, package_sha)
        self.assertEqual(
            _repository_package_filename(parsed), "clangd-18_1.2.3_amd64.deb"
        )
        self.assertEqual(
            _repository_packages_url(parsed),
            "https://apt.llvm.org/jammy/dists/llvm-toolchain-jammy-18/main/"
            "binary-amd64/Packages",
        )
        self.assertEqual(
            Installer._apt_repository_line(parsed, Path("/etc/apt/keyrings/clangd.gpg")),
            "deb [signed-by=/etc/apt/keyrings/clangd.gpg] "
            "https://apt.llvm.org/jammy/ llvm-toolchain-jammy-18 main\n",
        )

    def test_apt_repository_packages_digest_fails_closed(self) -> None:
        """Derived Packages bytes must match the typed digest before acceptance."""
        payload = b"signed Packages fixture\n"
        parsed = parse_record(
            record(
                "repo",
                method="apt-repository",
                platform="linux/amd64",
                source="https://apt.example.test/jammy/",
                repository_suite="jammy",
                repository_components=["main"],
                repository_packages_sha256=hashlib.sha256(payload).hexdigest(),
                key_url="https://apt.example.test/key",
                key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
            ),
            path=Path("fixture.toml"),
            index=0,
        )

        def write_fixture(
            url: str,
            destination: Path,
            **_: object,
        ) -> None:
            self.assertEqual(
                url,
                "https://apt.example.test/jammy/dists/jammy/main/"
                "binary-amd64/Packages",
            )
            destination.write_bytes(payload)

        with mock.patch(
            "tools.runtime.container.devcontainer_dependencies._download",
            side_effect=write_fixture,
        ):
            Installer(image_owned=True)._verify_repository_packages_digest(parsed)

        mismatched = replace(
            parsed, repository_packages_sha256=hashlib.sha256(b"different").hexdigest()
        )
        with mock.patch(
            "tools.runtime.container.devcontainer_dependencies._download",
            side_effect=write_fixture,
        ):
            with self.assertRaisesRegex(DependencyError, "Packages index SHA256 mismatch"):
                Installer(image_owned=True)._verify_repository_packages_digest(mismatched)

    def test_apt_repository_artifact_pair_and_url_sha_validation_fail_closed(self) -> None:
        base = record(
            "repo",
            method="apt-repository",
            key_url="https://example.test/key",
            key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
        )
        for field in ("repository_package_url", "repository_package_sha256"):
            with self.subTest(field=field):
                incomplete = dict(base)
                incomplete[field] = (
                    "https://example.test/repo/tool_1.0.0_amd64.deb"
                    if field == "repository_package_url"
                    else "0" * 64
                )
                with self.assertRaisesRegex(DependencyError, "provided together"):
                    parse_record(incomplete, path=Path("fixture.toml"), index=0)
        invalid_url = dict(base)
        invalid_url.update(
            repository_package_url="http://example.test/tool.deb",
            repository_package_sha256="0" * 64,
        )
        with self.assertRaisesRegex(DependencyError, "https"):
            parse_record(invalid_url, path=Path("fixture.toml"), index=0)
        invalid_sha = dict(base)
        invalid_sha.update(
            repository_package_url="https://example.test/tool.deb",
            repository_package_sha256="not-a-sha",
        )
        with self.assertRaisesRegex(DependencyError, "64-character SHA256"):
            parse_record(invalid_sha, path=Path("fixture.toml"), index=0)

    def test_apt_repository_installs_verified_immutable_deb_and_separates_rolling_hash(
        self,
    ) -> None:
        rolling = b"rolling Packages index"
        immutable = b"immutable clangd deb"
        rolling_sha = hashlib.sha256(rolling).hexdigest()
        immutable_sha = hashlib.sha256(immutable).hexdigest()
        package_url = "https://apt.example.test/clangd-18_1.2.3_amd64.deb"
        fingerprint = "2C6106201985B60E6C7AC87323F3D4EA75716059"
        parsed = parse_record(
            record(
                "clangd-language-server",
                method="apt-repository",
                package="clangd-18",
                version="1.2.3",
                platform="linux/amd64",
                source="https://apt.example.test/jammy/",
                repository_suite="jammy",
                repository_components=["main"],
                repository_packages_sha256=rolling_sha,
                repository_package_url=package_url,
                repository_package_sha256=immutable_sha,
                key_url="https://apt.example.test/key",
                key_fingerprint=fingerprint,
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()

        def write_download(
            url: str,
            destination: Path,
            **_: object,
        ) -> None:
            if url == package_url:
                destination.write_bytes(immutable)
            elif url.endswith("/Packages"):
                destination.write_bytes(rolling)
            else:
                destination.write_bytes(b"key")

        original_run = runner.run

        def run_with_key_fingerprint(
            argv: Sequence[str],
            *,
            cwd: Path | None = None,
            privileged: bool = False,
            capture_output: bool = False,
            env: Mapping[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            result = original_run(
                argv,
                cwd=cwd,
                privileged=privileged,
                capture_output=capture_output,
                env=env,
            )
            if tuple(argv[:3]) == ("gpg", "--show-keys", "--with-colons"):
                return subprocess.CompletedProcess(
                    argv, 0, f"fpr:::::::::{fingerprint}:\n", ""
                )
            return result

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            init_authentic_git(workspace)
            with (
                mock.patch.object(runner, "run", side_effect=run_with_key_fingerprint),
                mock.patch(
                    "tools.runtime.container.devcontainer_dependencies._download",
                    side_effect=write_download,
                ),
            ):
                Installer(runner, image_owned=True)._install_apt_repository(
                    parsed, workspace, repair=False
                )
                successful_calls = tuple(runner.calls)
                runner.calls.clear()
                runner.environments.clear()
                mismatched = replace(
                    parsed,
                    repository_package_sha256=hashlib.sha256(b"different deb").hexdigest(),
                )
                with self.assertRaisesRegex(
                    DependencyError, "immutable apt package SHA256 mismatch"
                ):
                    Installer(runner, image_owned=True)._install_apt_repository(
                        mismatched, workspace, repair=False
                    )
                self.assertFalse(
                    any(command[:2] == ("apt-get", "install") for command in runner.calls)
                )

        local_installs = [
            command
            for command in successful_calls
            if command[:2] == ("apt-get", "install")
        ]
        self.assertEqual(len(local_installs), 1)
        self.assertEqual(Path(local_installs[0][-1]).name, "clangd-18_1.2.3_amd64.deb")
        self.assertNotIn("clangd-18=1.2.3", local_installs[0])
        self.assertIn(("apt-get", "update"), runner.calls)

    def test_apt_repository_receipt_keeps_immutable_and_rolling_hashes_distinct(self) -> None:
        rolling_sha = "1" * 64
        immutable_sha = "2" * 64
        parsed = parse_record(
            record(
                "repo",
                method="apt-repository",
                platform="linux/amd64",
                source="https://apt.example.test/jammy/",
                repository_suite="jammy",
                repository_components=["main"],
                repository_packages_sha256=rolling_sha,
                repository_package_url="https://apt.example.test/repo_1.0_amd64.deb",
                repository_package_sha256=immutable_sha,
                key_url="https://apt.example.test/key",
                key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            receipt = root / "repo.json"
            installer = Installer()
            installer._parent_attestation = dependency_module._parent_attestation(
                root, "test-receipt"
            )
            installer._write_receipt(receipt, plan, parsed)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["repository_packages"]["sha256"], rolling_sha)
            self.assertEqual(payload["repository_package"]["sha256"], immutable_sha)
            self.assertTrue(installer._receipt_matches(receipt, plan, parsed))
            payload["repository_package"]["sha256"] = rolling_sha
            receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            self.assertFalse(installer._receipt_matches(receipt, plan, parsed))

    def test_apt_executable_ownership_resolves_symlink_with_same_package(self) -> None:
        parsed = parse_record(
            record(
                "clangd-language-server",
                method="apt-repository",
                package="clangd-18",
                version="1.2.3",
                platform="linux/amd64",
                source="https://apt.example.test/jammy/",
                repository_suite="jammy",
                repository_components=["main"],
                key_url="https://apt.example.test/key",
                key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
                verification={
                    "kind": "apt-repository",
                    "executable": "clangd-18",
                    "args": ["--version"],
                    "output_contains": "clangd version 18.1.8",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()
        lexical = "/usr/bin/clangd-18"
        resolved = "/usr/lib/llvm-18/bin/clangd"
        runner.ownership_lists["clangd-18"] = (lexical, resolved)
        runner.resolved_paths[lexical] = resolved
        runner.virtual_executables.add(resolved)
        lexical_path, resolved_path = Installer(runner)._resolve_executable_binding(
            parsed, "clangd-18", workspace=Path("/tmp/workspace")
        )
        self.assertEqual(lexical_path, Path(lexical))
        self.assertEqual(resolved_path, Path(resolved))
        self.assertIn(("/usr/bin/dpkg-query", "--listfiles", "clangd-18"), runner.calls)

    def test_apt_executable_ownership_resolves_symlink_across_owner_union(self) -> None:
        parsed = parse_record(
            record(
                "clang-format",
                method="apt-package",
                package="clang-format",
                version="1.2.3",
                platform="linux/amd64",
                source="ubuntu:22.04",
                verification={
                    "kind": "apt-package",
                    "executable": "clang-format",
                    "args": ["--version"],
                    "output_contains": "clang-format version 14.0.0",
                },
                executable_owner_packages=["clang-format", "clang-format-14"],
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()
        lexical = "/usr/bin/clang-format"
        resolved = "/usr/lib/clang-format-14/bin/clang-format"
        runner.ownership_lists["clang-format"] = ("/usr/bin/clangd-18",)
        runner.ownership_lists["clang-format-14"] = (lexical, resolved)
        runner.resolved_paths[lexical] = resolved
        runner.virtual_executables.add(resolved)
        lexical_path, resolved_path = Installer(runner)._resolve_executable_binding(
            parsed, "clang-format", workspace=Path("/tmp/workspace")
        )
        self.assertEqual(lexical_path, Path(lexical))
        self.assertEqual(resolved_path, Path(resolved))
        self.assertEqual(
            [command for command in runner.calls if command[0] == "/usr/bin/dpkg-query"],
            [
                ("/usr/bin/dpkg-query", "--listfiles", "clang-format"),
                ("/usr/bin/dpkg-query", "--listfiles", "clang-format-14"),
            ],
        )

    def test_dpkg_owned_paths_normalize_leading_dot_entry(self) -> None:
        owned = _parse_dpkg_owned_paths("/.\n/usr/bin/jq\n", "jq")
        self.assertIn("/", owned)
        self.assertIn("/usr/bin/jq", owned)
        with self.assertRaisesRegex(DependencyError, "unsafe path"):
            _parse_dpkg_owned_paths("relative/path\n", "jq")
        with self.assertRaisesRegex(DependencyError, "unsafe path"):
            _parse_dpkg_owned_paths("/usr/bin/jq\x00evil\n", "jq")

    def test_strict_apt_verify_uses_absolute_dpkg_query_for_version_and_ownership(self) -> None:
        parsed = parse_record(
            record(
                "tool",
                method="apt-package",
                verification={
                    "kind": "apt-package",
                    "executable": "tool",
                    "args": ["--version"],
                    "output_contains": "1.0.0",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()
        Installer(runner).verify(
            parsed, workspace=Path("/tmp/workspace"), strict_executables=True
        )
        dpkg_calls = [
            command for command in runner.calls if Path(command[0]).name == "dpkg-query"
        ]
        self.assertEqual(len(dpkg_calls), 2)
        self.assertTrue(all(command[0] == "/usr/bin/dpkg-query" for command in dpkg_calls))

    def test_apt_executable_ownership_rejects_unowned_cross_package_target(self) -> None:
        parsed = parse_record(
            record(
                "clangd-language-server",
                method="apt-repository",
                package="clangd-18",
                version="1.2.3",
                platform="linux/amd64",
                source="https://apt.example.test/jammy/",
                repository_suite="jammy",
                repository_components=["main"],
                key_url="https://apt.example.test/key",
                key_fingerprint="2C6106201985B60E6C7AC87323F3D4EA75716059",
                verification={
                    "kind": "apt-repository",
                    "executable": "clangd-18",
                    "args": ["--version"],
                    "output_contains": "clangd version 18.1.8",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()
        lexical = "/usr/bin/clangd-18"
        resolved = "/usr/lib/llvm-18/bin/clangd"
        runner.ownership_lists["clangd-18"] = (lexical, "/usr/lib/other/clangd")
        runner.resolved_paths[lexical] = resolved
        runner.virtual_executables.add(resolved)
        with self.assertRaisesRegex(DependencyError, "not owned"):
            Installer(runner)._resolve_executable_binding(
                parsed, "clangd-18", workspace=Path("/tmp/workspace")
            )

        runner.ownership_lists["clangd-18"] = ("relative/clangd",)
        with self.assertRaisesRegex(DependencyError, "unsafe path"):
            Installer(runner)._resolve_executable_binding(
                parsed, "clangd-18", workspace=Path("/tmp/workspace")
            )

    def test_verified_executable_requires_receipt_binding_and_rejects_path_drift(self) -> None:
        """Manifest executable resolution is receipt-bound and independent of PATH."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            prefix = root / "npm"
            bin_dir = prefix / "bin"
            bin_dir.mkdir(parents=True)
            target_dir = prefix / "lib"
            target_dir.mkdir(parents=True)
            target_v1 = target_dir / "pyright-v1"
            target_v2 = target_dir / "pyright-v2"
            for target in (target_v1, target_v2, bin_dir / "pyright-langserver"):
                target.write_text("#!/usr/bin/env true\n", encoding="utf-8")
                target.chmod(0o755)
            (bin_dir / "pyright").symlink_to(target_v1)
            manifest = root / "bootstrap" / "container" / "image" / "dependencies.toml"
            write_manifest(
                manifest,
                [
                    record(
                        "pyright-language-server",
                        package="pyright",
                        version="1.0.0",
                        provides=["pyright", "pyright-langserver"],
                        verification={
                            "kind": "npm-package",
                            "executable": "pyright",
                            "args": ["--version"],
                            "output_contains": "1.0.0",
                        },
                    )
                ],
            )
            fake = FakeRunner()
            receipts = root / "receipts"
            parsed = parse_record(
                record(
                    "pyright-language-server",
                    package="pyright",
                    version="1.0.0",
                    provides=["pyright", "pyright-langserver"],
                    verification={
                        "kind": "npm-package",
                        "executable": "pyright",
                        "args": ["--version"],
                        "output_contains": "1.0.0",
                    },
                ),
                path=manifest,
                index=0,
            )
            plan = build_plan((loaded_manifest(manifest, (parsed,)),))
            with mock.patch.object(
                dependency_module, "NPM_GLOBAL_PREFIX", str(prefix)
            ):
                Installer(fake).install(
                    plan,
                    workspace=root,
                    receipts=receipts,
                )
                with mock.patch.object(
                    dependency_module,
                    "Installer",
                    lambda: Installer(fake),
                ):
                    resolved = dependency_module.resolve_verified_executable(
                        root, receipts, "pyright-language-server", "pyright",
                        manifest=manifest,
                    )
                self.assertEqual(resolved.absolute_path, str(target_v1.resolve()))
                self.assertEqual(resolved.executable, "pyright")
                self.assertIn((str(target_v1.resolve()), "--version"), fake.calls)
                payload = json.loads(
                    (receipts / "pyright-language-server.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    set(payload["executable_bindings"]),
                    {"pyright", "pyright-langserver"},
                )
                payload["record_fingerprint"] = "0" * 64
                (receipts / "pyright-language-server.json").write_text(
                    json.dumps(payload) + "\n", encoding="utf-8"
                )
                with mock.patch.object(
                    dependency_module,
                    "Installer",
                    lambda: Installer(fake),
                ):
                    with self.assertRaisesRegex(
                        DependencyError, "executable receipt binding is stale"
                    ):
                        dependency_module.resolve_verified_executable(
                            root,
                            receipts,
                            "pyright-language-server",
                            "pyright",
                            manifest=manifest,
                        )
                payload["record_fingerprint"] = plan.by_id()[
                    "pyright-language-server"
                ].fingerprint()
                (receipts / "pyright-language-server.json").write_text(
                    json.dumps(payload) + "\n", encoding="utf-8"
                )
                (bin_dir / "pyright").unlink()
                (bin_dir / "pyright").symlink_to(target_v2)
                with mock.patch.object(
                    dependency_module,
                    "Installer",
                    lambda: Installer(fake),
                ):
                    with self.assertRaisesRegex(
                        DependencyError, "receipt path or output drift"
                    ):
                        dependency_module.resolve_verified_executable(
                            root,
                            receipts,
                            "pyright-language-server",
                            "pyright",
                            manifest=manifest,
                        )

    def test_secondary_npm_binding_is_structural_not_a_help_probe(self) -> None:
        """A secondary provider may reject generic help while remaining bound."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            prefix = root / "npm"
            bin_dir = prefix / "bin"
            bin_dir.mkdir(parents=True)
            primary = bin_dir / "pyright"
            secondary = bin_dir / "pyright-langserver"
            marker = root / "secondary-called"
            primary.write_text("#!/bin/sh\nprintf 'pyright 1.0.0\\n'\n", encoding="utf-8")
            secondary.write_text(
                f"#!/bin/sh\ntouch '{marker}'\nprintf 'usage is intentionally nonzero\\n' >&2\nexit 1\n",
                encoding="utf-8",
            )
            primary.chmod(0o755)
            secondary.chmod(0o755)
            parsed = parse_record(
                record(
                    "pyright-language-server",
                    package="pyright",
                    version="1.0.0",
                    provides=["pyright", "pyright-langserver"],
                    verification={
                        "kind": "npm-package",
                        "executable": "pyright",
                        "args": ["--version"],
                        "output_contains": "1.0.0",
                    },
                ),
                path=Path("fixture.toml"),
                index=0,
            )
            plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
            with mock.patch.object(dependency_module, "NPM_GLOBAL_PREFIX", str(prefix)):
                installer = Installer()
                installer._parent_attestation = dependency_module._parent_attestation(
                    root, "test-receipt"
                )
                bindings = installer._executable_bindings(parsed, workspace=root)
                receipt = root / "receipts" / "pyright-language-server.json"
                installer._write_receipt(receipt, plan, parsed, executable_bindings=bindings)

                self.assertEqual(
                    bindings["pyright-langserver"]["verification_output"],
                    "agent-canon.executable-binding.structural.v1:npm-global:pyright-langserver",
                )
                self.assertFalse(marker.exists())
                self.assertTrue(installer._receipt_matches(receipt, plan, parsed))

    def test_secondary_npm_binding_rejects_escape_and_missing_provider(self) -> None:
        """Secondary providers remain fail-closed on escape, missing, or non-exec path."""
        for case in ("escape", "missing", "non_executable"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                prefix = root / "npm"
                bin_dir = prefix / "bin"
                bin_dir.mkdir(parents=True)
                primary = bin_dir / "pyright"
                primary.write_text("#!/bin/sh\nprintf 'pyright 1.0.0\\n'\n", encoding="utf-8")
                primary.chmod(0o755)
                secondary = bin_dir / "pyright-langserver"
                if case == "escape":
                    outside = root / "outside-provider"
                    outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    outside.chmod(0o755)
                    secondary.symlink_to(outside)
                elif case == "non_executable":
                    secondary.write_text("#!/bin/sh\necho blocked\\n", encoding="utf-8")
                    secondary.chmod(0o644)
                parsed = parse_record(
                    record(
                        "pyright-language-server",
                        package="pyright",
                        version="1.0.0",
                        provides=["pyright", "pyright-langserver"],
                        verification={
                            "kind": "npm-package",
                            "executable": "pyright",
                            "args": ["--version"],
                            "output_contains": "1.0.0",
                        },
                    ),
                    path=Path("fixture.toml"),
                    index=0,
                )
                with mock.patch.object(dependency_module, "NPM_GLOBAL_PREFIX", str(prefix)):
                    with self.assertRaisesRegex(
                        DependencyError,
                        "(escapes its method-owned root|executable is missing|executable is not executable)",
                    ):
                        Installer()._executable_bindings(parsed, workspace=root)

    def test_rust_analyzer_binding_uses_cargo_home_not_path(self) -> None:
        """Rust executable bindings stay inside the pinned Cargo home."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo_home = root / "cargo"
            rust_analyzer = cargo_home / "bin" / "rust-analyzer"
            rust_analyzer.parent.mkdir(parents=True)
            rust_analyzer.write_text("#!/usr/bin/env true\n", encoding="utf-8")
            rust_analyzer.chmod(0o755)
            parsed = parse_record(
                record(
                    "rust-toolchain",
                    method="rust-toolchain",
                    version="1.89.0",
                    source="https://static.rust-lang.org/dist",
                    components=["rust-analyzer"],
                    verification={"kind": "rust-toolchain"},
                    provides=["rust-analyzer"],
                ),
                path=Path("fixture.toml"),
                index=0,
            )
            with mock.patch.dict(
                os.environ,
                {"CARGO_HOME": str(cargo_home), "PATH": str(root / "ambient-bin")},
                clear=False,
            ):
                self.assertEqual(
                    dependency_module._current_executable_path(parsed, "rust-analyzer"),
                    rust_analyzer.resolve(),
                )

    def test_binary_release_asset_accepts_pinned_architecture_paths(self) -> None:
        parsed = parse_record(
            record(
                "binary",
                method="release-asset",
                checksum="0" * 64,
                checksums={"aarch64": "1" * 64, "x86_64": "0" * 64},
                asset="x86_64-unknown-linux-gnu/tool",
                assets={
                    "aarch64": "aarch64-unknown-linux-gnu/tool",
                    "x86_64": "x86_64-unknown-linux-gnu/tool",
                },
                archive_format="binary",
                extract="none",
                destination="/usr/local/bin/tool",
                source="https://example.test/releases",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        self.assertEqual(parsed.archive_format, "binary")
        self.assertEqual(
            dict(parsed.assets)["aarch64"], "aarch64-unknown-linux-gnu/tool"
        )
        with self.assertRaisesRegex(DependencyError, "safe relative asset path"):
            parse_record(
                record(
                    "unsafe-binary",
                    method="release-asset",
                    checksum="0" * 64,
                    asset="../tool",
                    archive_format="binary",
                    extract="none",
                    destination="/usr/local/bin/tool",
                    source="https://example.test/releases",
                ),
                path=Path("fixture.toml"),
                index=0,
            )

    def test_binary_release_asset_installs_verified_nested_asset(self) -> None:
        content = b"pinned-rustup-init"
        parsed = parse_record(
            record(
                "rustup-init",
                method="release-asset",
                checksum=hashlib.sha256(content).hexdigest(),
                checksums={
                    "aarch64": hashlib.sha256(b"aarch64").hexdigest(),
                    "x86_64": hashlib.sha256(content).hexdigest(),
                },
                asset="x86_64-unknown-linux-gnu/rustup-init",
                assets={
                    "aarch64": "aarch64-unknown-linux-gnu/rustup-init",
                    "x86_64": "x86_64-unknown-linux-gnu/rustup-init",
                },
                archive_format="binary",
                extract="none",
                destination="/usr/local/bin/rustup-init",
                source="https://static.rust-lang.org/rustup/archive/1.28.2",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner()

        def download(
            url: str,
            destination: Path,
            **_: object,
        ) -> None:
            self.assertEqual(
                url,
                "https://static.rust-lang.org/rustup/archive/1.28.2/"
                "x86_64-unknown-linux-gnu/rustup-init",
            )
            destination.write_bytes(content)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            with (
                mock.patch(
                    "tools.runtime.container.devcontainer_dependencies.architecture",
                    return_value="x86_64",
                ),
                mock.patch(
                    "tools.runtime.container.devcontainer_dependencies._download",
                    side_effect=download,
                ),
            ):
                Installer(runner, image_owned=True).install_record(parsed, workspace=root)

        install_call = next(call for call in runner.calls if call[0] == "install")
        self.assertEqual(install_call[1:4], ("-D", "-m", "0755"))
        self.assertEqual(install_call[-1], "/usr/local/bin/rustup-init")

    def test_parent_values_are_retained_and_compatible_sets_union(self) -> None:
        parent = parse_record(
            record("shared", deps=["node"], provides=["codex"]),
            path=Path("parent.toml"),
            index=0,
        )
        vendor = parse_record(
            record(
                "shared",
                deps=["ninja-build"],
                provides=["shared-cli"],
            ),
            path=Path("vendor.toml"),
            index=0,
        )
        merged = build_plan(
            (
                loaded_manifest(
                    Path("parent.toml"),
                    (parent,),
                    role=ManifestRole.PARENT_OVERLAY,
                ),
                loaded_manifest(Path("vendor.toml"), (vendor,)),
            )
        ).records[0]
        self.assertEqual(merged.version, "1.0.0")
        self.assertEqual(merged.deps, ("node", "ninja-build"))
        self.assertEqual(merged.provides, ("codex", "shared-cli"))
        self.assertEqual(merged.verification.kind.value, "npm-package")

    def test_incompatible_executable_owner_packages_fail_merge(self) -> None:
        parent = parse_record(
            record(
                "shared",
                method="apt-package",
                source="ubuntu:22.04",
                executable_owner_packages=["clang-format", "clang-format-14"],
            ),
            path=Path("parent.toml"),
            index=0,
        )
        vendor = parse_record(
            record(
                "shared",
                method="apt-package",
                source="ubuntu:22.04",
                executable_owner_packages=["clang-format", "llvm"],
            ),
            path=Path("vendor.toml"),
            index=0,
        )
        with self.assertRaisesRegex(DependencyError, "incompatible duplicate"):
            build_plan(
                (
                    loaded_manifest(
                        Path("parent.toml"),
                        (parent,),
                        role=ManifestRole.PARENT_OVERLAY,
                    ),
                    loaded_manifest(Path("vendor.toml"), (vendor,)),
                )
            )

    def test_incompatible_duplicate_provider_missing_and_cycle_fail(self) -> None:
        parent = parse_record(record("shared"), path=Path("parent.toml"), index=0)
        incompatible = parse_record(
            record("shared", version="2.0.0"),
            path=Path("vendor.toml"),
            index=0,
        )
        with self.assertRaisesRegex(DependencyError, "incompatible duplicate"):
            build_plan(
                (
                    loaded_manifest(
                        Path("parent.toml"),
                        (parent,),
                        role=ManifestRole.PARENT_OVERLAY,
                    ),
                    loaded_manifest(Path("vendor.toml"), (incompatible,)),
                )
            )
        with self.assertRaisesRegex(DependencyError, "provider ambiguity"):
            build_plan(
                (
                    loaded_manifest(
                        Path("a.toml"),
                        (
                            parse_record(
                                record("a", provides=["same"]),
                                path=Path("a.toml"),
                                index=0,
                            ),
                        ),
                    ),
                    loaded_manifest(
                        Path("b.toml"),
                        (
                            parse_record(
                                record("b", provides=["same"]),
                                path=Path("b.toml"),
                                index=0,
                            ),
                        ),
                    ),
                )
            )
        with self.assertRaisesRegex(DependencyError, "missing dependency"):
            build_plan(
                (
                    loaded_manifest(
                        Path("missing.toml"),
                        (
                            parse_record(
                                record("missing", deps=["absent"]),
                                path=Path("missing.toml"),
                                index=0,
                            ),
                        ),
                    ),
                )
            )
        cycle_a = parse_record(
            record("a", deps=["b"]), path=Path("cycle.toml"), index=0
        )
        cycle_b = parse_record(
            record("b", deps=["a"]), path=Path("cycle.toml"), index=1
        )
        with self.assertRaisesRegex(DependencyError, "cycle"):
            build_plan((loaded_manifest(Path("cycle.toml"), (cycle_a, cycle_b)),))

    def test_manifest_sources_discovers_bootstrap_manifest_only(self) -> None:
        """Automatic discovery has one bootstrap-owned source."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "bootstrap" / "container" / "image" / "dependencies.toml"
            legacy = root / ".devcontainer" / "dependencies.toml"
            vendor = root / "vendor" / "agent-canon" / "dependencies.toml"
            write_manifest(manifest, [record("bootstrap")])
            write_manifest(legacy, [record("legacy")])
            write_manifest(vendor, [record("vendor")])
            self.assertEqual(
                manifest_sources(root),
                (ManifestSource(manifest, ManifestRole.CANONICAL),),
            )

    def test_manifest_sources_ignores_legacy_layout(self) -> None:
        """Legacy editor/vendor paths cannot become a dependency source."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_manifest(root / ".devcontainer" / "dependencies.toml", [record("legacy")])
            write_manifest(
                root / "vendor" / "agent-canon" / "dependencies.toml",
                [record("vendor")],
            )
            self.assertEqual(manifest_sources(root), ())

    def test_manifest_sources_accepts_explicit_standalone_path_without_devcontainer(self) -> None:
        """An explicit image manifest bypasses parent and synthetic path discovery."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            explicit = root / "bootstrap" / "container" / "image" / "dependencies.toml"
            parent = root / ".devcontainer" / "dependencies.toml"
            vendor = root / "vendor" / "agent-canon" / ".devcontainer" / "dependencies.toml"
            write_manifest(explicit, [record("explicit")])
            write_manifest(parent, [record("parent")])
            write_manifest(vendor, [record("vendor")])

            self.assertEqual(
                manifest_sources(root, manifest=explicit),
                (ManifestSource(explicit, ManifestRole.CANONICAL),),
            )
            with self.assertRaisesRegex(DependencyError, "manifest not found"):
                manifest_sources(root, manifest=root / "missing.toml")

    def test_cli_parser_exposes_explicit_manifest_option(self) -> None:
        """The image installer can select a standalone manifest explicitly."""
        parsed = build_parser().parse_args(
            ["image-install", "--workspace", "/image", "--manifest", "/manifest.toml"]
        )
        self.assertEqual(parsed.manifest, "/manifest.toml")

    def test_standalone_manifest_requires_no_devcontainer_overlay(self) -> None:
        """The shared image plan is explicit and independent of `.devcontainer`."""
        self.assertFalse((ROOT / ".devcontainer").exists())
        plan = load_plan(
            ROOT,
            manifest=ROOT / "bootstrap" / "container" / "image" / "dependencies.toml",
        )
        self.assertTrue(plan.records)

    def test_bootstrap_boundary_uses_shared_runtime_contract(self) -> None:
        """Boundary validation does not require editor hooks or product mounts."""
        report = EnvironmentBoundaryModel(ROOT, ROOT).validate()
        self.assertEqual(report.status, "pass")
        self.assertIn("bootstrap/container/image/dependencies.toml", report.checked)
        self.assertIn("bootstrap/container/image/Dockerfile", report.checked)
        self.assertNotIn(".devcontainer/devcontainer.json", report.checked)
        self.assertNotIn(".devcontainer/post-create.sh", report.checked)

    def test_canonical_manifest_is_a_small_default_tool_set(self) -> None:
        """Default startup retains only LSP and small structure/agent tools."""
        plan = load_plan(
            ROOT,
            manifest=ROOT / "bootstrap" / "container" / "image" / "dependencies.toml",
        )
        ids = {item.id for item in plan.records}
        self.assertEqual(
            ids,
            {
                "pyright-language-server",
                "bash-language-server",
                "jq",
                "tree",
                "clang-format",
                "clangd-language-server",
                "rust-toolchain",
                "agent-canon-cli",
            },
        )
        for removed in (
            "playwright",
            "playwright-chromium",
            "pdflatex",
            "gitleaks",
            "trufflehog",
            "detect-secrets",
            "elan",
            "rustup-init",
            "lean-toolchain",
            "pyyaml",
        ):
            self.assertNotIn(removed, ids)

    def test_canonical_apt_records_are_jammy_multiarch_owned(self) -> None:
        """Shared apt records target Jammy without pinning one host architecture."""
        plan = load_plan(
            ROOT,
            manifest=ROOT / "bootstrap" / "container" / "image" / "dependencies.toml",
        )
        apt_records = [
            item for item in plan.records if item.method.value == "apt-package"
        ]

        self.assertTrue(apt_records)
        self.assertTrue(all(item.platform is None for item in apt_records))
        self.assertTrue(all(item.source == "ubuntu:22.04" for item in apt_records))
        self.assertFalse(any(item.source == "ubuntu:24.04" for item in apt_records))

    def test_install_identity_accepts_ubuntu22_multiarch(self) -> None:
        """The canonical install gate accepts both supported OCI variants."""
        parsed = parse_record(
            record(
                "jammy-tool",
                method="apt-package",
                source="ubuntu:22.04",
                platforms=["linux/amd64", "linux/arm64"],
            ),
            path=Path("identity.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("identity.toml"), (parsed,)),))
        for identity in (
            RuntimeIdentity("ubuntu", "22.04", "linux/amd64"),
            RuntimeIdentity("ubuntu", "22.04", "linux/arm64"),
        ):
            self.assertEqual(validate_runtime_identity(plan, identity), identity)

    def test_install_identity_rejects_wrong_release_or_arch_before_runner(self) -> None:
        """Unsupported identities fail before Installer runner calls."""
        parsed = parse_record(
            record(
                "jammy-tool",
                method="apt-package",
                source="ubuntu:22.04",
                platforms=["linux/amd64", "linux/arm64"],
            ),
            path=Path("identity.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("identity.toml"), (parsed,)),))
        for identity in (
            RuntimeIdentity("ubuntu", "24.04", "linux/amd64"),
            RuntimeIdentity("ubuntu", "22.04", "linux/riscv64"),
        ):
            runner = FakeRunner()
            with self.assertRaises(DependencyError):
                install_plan(
                    plan,
                    workspace=Path("/tmp/identity-workspace"),
                    receipts=Path("/tmp/identity-receipts"),
                    runner=runner,
                    identity=identity,
                )
            self.assertEqual(runner.calls, [])

    def test_platform_mismatch_fails_without_compatibility_fallback(self) -> None:
        """A platform-owned record fails closed instead of selecting another base."""
        parsed = parse_record(
            record(
                "arm-only",
                method="apt-package",
                source="ubuntu:22.04",
                platform="linux/arm64",
            ),
            path=Path("platform.toml"),
            index=0,
        )

        with self.assertRaisesRegex(DependencyError, "no compatibility fallback"):
            build_plan((loaded_manifest(Path("platform.toml"), (parsed,)),))

    def test_duplicate_merge_preserves_platform_owner(self) -> None:
        """Parent-first duplicate merging cannot erase the platform pin."""
        parent = parse_record(
            record(
                "shared-tool",
                method="apt-package",
                source="ubuntu:22.04",
                version="1.0-1",
            ),
            path=Path("parent.toml"),
            index=0,
        )
        vendor = parse_record(
            record(
                "shared-tool",
                method="apt-package",
                source="ubuntu:22.04",
                version="1.0-1",
                platform="linux/amd64",
            ),
            path=Path("vendor.toml"),
            index=0,
        )

        plan = build_plan(
            (
                loaded_manifest(
                    Path("parent.toml"),
                    (parent,),
                    role=ManifestRole.PARENT_OVERLAY,
                ),
                loaded_manifest(Path("vendor.toml"), (vendor,)),
            )
        )
        self.assertEqual(plan.records[0].platform, "linux/amd64")

    def test_standalone_empty_manifest_is_rejected(self) -> None:
        """Reject an empty bootstrap canonical manifest."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "bootstrap" / "container" / "image" / "dependencies.toml"
            write_manifest(manifest, [])

            with self.assertRaisesRegex(DependencyError, "non-empty"):
                load_plan(root)

    def test_empty_merged_plan_is_rejected(self) -> None:
        """Reject an aggregate plan with no dependency records."""
        with self.assertRaisesRegex(DependencyError, "merged dependency plan"):
            build_plan(
                (
                    loaded_manifest(
                        Path("parent.toml"),
                        (),
                        role=ManifestRole.PARENT_OVERLAY,
                    ),
                )
            )

    def test_verification_rejects_legacy_commands_and_shell_executables(self) -> None:
        legacy = record("unsafe", commands=[["unsafe", "--version"]])
        with self.assertRaisesRegex(DependencyError, "unknown fields: commands"):
            parse_record(legacy, path=Path("fixture.toml"), index=0)
        unsafe = record(
            "unsafe",
            verification={
                "kind": "npm-package",
                "executable": "sh",
                "args": ["--version"],
                "output_contains": "1.0.0",
            },
        )
        with self.assertRaisesRegex(DependencyError, "one command name"):
            parse_record(unsafe, path=Path("fixture.toml"), index=0)
        for method, verification_kind in (
            ("npm-global", "npm-package"),
            ("pipx", "pipx-package"),
        ):
            for verification in (
                {"kind": verification_kind},
                {
                    "kind": verification_kind,
                    "executable": "tool",
                    "args": ["--version"],
                },
                {
                    "kind": verification_kind,
                    "executable": "tool",
                    "output_contains": "1.0.0",
                },
                {
                    "kind": verification_kind,
                    "args": ["--version"],
                    "output_contains": "1.0.0",
                },
            ):
                with self.subTest(method=method, verification=verification):
                    with self.assertRaisesRegex(
                        DependencyError, "requires executable, args"
                    ):
                        parse_record(
                            record(
                                f"incomplete-{method}",
                                method=method,
                                verification=verification,
                            ),
                            path=Path("fixture.toml"),
                            index=0,
                        )
        incomplete_apt = record(
            "incomplete-apt",
            method="apt-package",
            verification={
                "kind": "apt-package",
                "executable": "clang-format",
            },
        )
        with self.assertRaisesRegex(DependencyError, "requires executable, args"):
            parse_record(incomplete_apt, path=Path("fixture.toml"), index=0)

    def test_source_command_safety_is_structural(self) -> None:
        """AST findings track executable calls, not comments or spelling."""
        fixtures = (
            ("import subprocess as sp\nsp.run([], shell=True)\n", CommandCapability.SHELL_EVALUATION),
            ("from subprocess import run as execute\nexecute([], shell=value)\n", CommandCapability.SHELL_EVALUATION),
            ("import subprocess\nsubprocess.run([], shell=False)\n", None),
            ("# shell=True\nmessage = 'eval('\n", None),
            ("eval(value)\n", CommandCapability.DYNAMIC_INTERPRETER),
            ("eval_result = 'diagnostic'\n", None),
        )
        for source, capability in fixtures:
            with self.subTest(source=source):
                findings = check_python_source_safety(source)
                self.assertEqual(
                    findings[0].capability if findings else None,
                    capability,
                )
        self.assertEqual(check_python_source_safety(ENGINE), ())

    def test_verification_command_capabilities(self) -> None:
        """Typed verifier commands pass while mutating graphs fail closed."""
        context = CommandProvenance(
            "image-verify", "typed-verifier", "verify-declared-executable"
        )
        safe = (
            ("dpkg-query", "--show", "--showformat=x", "pkg"),
            ("npm", "ls", "--global", "--prefix", "/usr/local", "--json", "--depth=0", "pkg"),
            ("rustup", "show", "active-toolchain"),
            ("git", "-C", "/src", "rev-parse", "--verify", "HEAD"),
            ("tool", "--version"),
        )
        for command in safe:
            with self.subTest(command=command):
                self.assertIn(CommandCapability.ARGV, classify_command(command, context=context))
        unsafe = (
            ("env", "sh", "-c", "echo unsafe"),
            ("python3", "-c", "print(unsafe)"),
            ("sudo", "apt-get", "install", "pkg"),
            ("apt-get", "install", "pkg"),
            ("npm", "install", "pkg"),
            ("curl", "https://example.invalid/pkg"),
        )
        for command in unsafe:
            with self.subTest(command=command):
                with self.assertRaisesRegex(DependencyError, r"command-boundary-"):
                    classify_command(command, context=context)

    def test_wrappers_are_recursive(self) -> None:
        """Apply the finite wrapper grammar recursively and fail closed."""
        context = CommandProvenance(
            "image-verify", "typed-verifier", "verify-declared-executable"
        )
        self.assertIn(
            CommandCapability.EXECUTABLE_VERIFICATION,
            classify_command(("env", "FOO=bar", "tool", "--version"), context=context),
        )
        for command, prefix in (
            (("env", "sh", "-c", "tool --version"), "command-boundary-shell-evaluation"),
            (("timeout", "5", "python3", "-c", "x"), "command-boundary-unknown"),
            (("env", "-S", "tool --version"), "command-boundary-unknown"),
        ):
            with self.subTest(command=command):
                with self.assertRaisesRegex(DependencyError, prefix):
                    classify_command(command, context=context)

    def test_image_receipt_binds_install_owner(self) -> None:
        """Image plan and receipt records retain image-install ownership."""
        parsed = parse_record(record("image-tool", method="apt-package"), path=Path("fixture.toml"), index=0)
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (parsed,)),))
        payload = dependency_module._image_plan_payload(plan, ("image-tool",))
        self.assertEqual(payload["owner"], "image-installer")
        self.assertEqual(payload["phase"], "image-install")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            receipt = root / "receipt.json"
            installer = Installer(FakeRunner())
            installer._parent_attestation = dependency_module._parent_attestation(root, "receipt-owner")
            installer._write_receipt(receipt, plan, parsed)
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(saved["owner"], "image-installer")
            self.assertEqual(saved["phase"], "image-install")
            self.assertEqual(saved["record_fingerprint"], parsed.fingerprint())

    def test_network_operations_are_phase_gated(self) -> None:
        """Reject unowned and image-verify network edges before URL open."""
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "asset"
            with self.assertRaisesRegex(DependencyError, "command-boundary-network-fetch"):
                dependency_module._download("https://example.invalid/asset", destination)
            with self.assertRaisesRegex(DependencyError, "command-boundary-network-fetch"):
                dependency_module._download(
                    "https://example.invalid/asset",
                    destination,
                    operation=dependency_module.NetworkOperation(
                        phase="image-verify",
                        owner="typed-verifier",
                        operation="download-release-asset",
                        method="release-asset",
                        record_id="asset",
                        url="https://example.invalid/asset",
                        allow_network=False,
                    ),
                )
            for operation, method, record_id in (
                ("unknown-download", "release-asset", "asset"),
                ("download-apt-key", "release-asset", "asset"),
                ("download-release-asset", "release-asset", ""),
            ):
                with self.subTest(operation=operation, method=method, record_id=record_id):
                    with self.assertRaisesRegex(DependencyError, "command-boundary-network-fetch"):
                        dependency_module._download(
                            "https://example.invalid/asset",
                            destination,
                            operation=dependency_module.NetworkOperation(
                                phase="image-install",
                                owner="image-installer",
                                operation=operation,
                                method=method,
                                record_id=record_id,
                                url="https://example.invalid/asset",
                                allow_network=True,
                            ),
                        )

    def test_single_runner_adapter_inventory(self) -> None:
        """Keep the Installer's direct runner edge inside one adapter."""
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "runner"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
        ]
        self.assertEqual(len(calls), 1)

    def test_safe_extraction_rejects_traversal_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            traversal = root / "traversal.tar"
            with tarfile.open(traversal, "w") as stream:
                file_info = tarfile.TarInfo("../outside")
                file_info.size = 1
                stream.addfile(file_info, fileobj=__import__("io").BytesIO(b"x"))
            with self.assertRaisesRegex(DependencyError, "escapes"):
                safe_extract_tar(traversal, root / "extract")

    def test_receipt_hit_verifies_live_state_and_reinstalls_after_rebuild(self) -> None:
        parsed = parse_record(
            record(
                "tool",
                method="apt-package",
                verification={
                    "kind": "apt-package",
                    "executable": "tool",
                    "args": ["--version"],
                    "output_contains": "1.0.0",
                },
            ),
            path=Path("x.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("x.toml"), (parsed,)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            runner = FakeRunner()
            installer = Installer(runner)
            receipts = root / "receipts"
            self.assertEqual(
                installer.install(plan, workspace=root, receipts=receipts), ("tool",)
            )

            resumed = FakeRunner()
            self.assertEqual(
                Installer(resumed).install(plan, workspace=root, receipts=receipts),
                ("tool",),
            )
            self.assertNotIn(("dpkg", "--verify", "tool"), resumed.calls)
            self.assertIn(("/usr/bin/tool", "--version"), resumed.calls)
            self.assertFalse(any(command[0] == "apt-get" for command in resumed.calls))

            rebuilt = FakeRunner(fail_once_on="dpkg-query")
            self.assertEqual(
                Installer(rebuilt).install(plan, workspace=root, receipts=receipts),
                ("tool",),
            )
            self.assertEqual(
                sum(command[0] == "apt-get" for command in rebuilt.calls),
                1,
            )
            self.assertEqual(
                sum(Path(command[0]).name == "dpkg-query" for command in rebuilt.calls),
                4,
            )
            apt_install = next(
                command for command in rebuilt.calls if command[0] == "apt-get"
            )
            self.assertIn("--reinstall", apt_install)

            failing = FakeRunner(fail_on="apt-get")
            with self.assertRaises(DependencyError):
                Installer(failing).install(
                    plan,
                    workspace=root,
                    receipts=root / "failed-receipts",
                )
            self.assertFalse((root / "failed-receipts" / "tool.json").exists())

    def _active_source_record(self) -> Any:
        return parse_record(
            record(
                "agent-canon-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://example.test/agent-canon.git",
                source_identity="active-source",
                locked=True,
                verification={
                    "kind": "cargo-binary",
                    "path": "target/release/agent-canon",
                    "args": ["--version"],
                    "output_contains": "agent-canon 0.1.0",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )

    def test_active_source_build_ignores_parent_gitlink_and_source_metadata(self) -> None:
        """Active-source verification uses the binary and does not inspect Git."""
        active = parse_record(
            record(
                "agent-canon-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://example.test/agent-canon.git",
                source_identity="active-source",
                locked=True,
                verification={
                    "kind": "cargo-binary",
                    "path": "target/release/agent-canon",
                    "args": ["--version"],
                    "output_contains": "agent-canon 0.1.0",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )

        def init_repository(repository: Path) -> None:
            subprocess.run(["git", "init", "-b", "main", str(repository)], check=True)
            subprocess.run(
                ["git", "config", "user.name", "Active Source Test"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "active-source@example.invalid"],
                cwd=repository,
                check=True,
            )

        def commit_repository(repository: Path, message: str) -> str:
            subprocess.run(["git", "add", "-A"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-m", message], cwd=repository, check=True)
            return subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        def write_cli_source(repository: Path) -> None:
            binary = repository / "rust" / "agent-canon" / "target" / "release" / "agent-canon"
            binary.parent.mkdir(parents=True)
            binary.write_text(
                "#!/usr/bin/env sh\nprintf '%s\\n' 'agent-canon 0.1.0'\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            cargo_manifest = repository / "tools" / "runtime" / "dispatch" / "agent-canon" / "Cargo.toml"
            cargo_manifest.parent.mkdir(parents=True, exist_ok=True)
            cargo_manifest.write_text(
                "[package]\nname = 'agent-canon'\nversion = '0.1.0'\nedition = '2021'\n",
                encoding="utf-8",
            )

        installer = Installer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_repository(root)
            write_cli_source(root)
            standalone_commit = commit_repository(root, "standalone source")
            self.assertIsNone(installer.verify(active, workspace=root))
            standalone_resolver_cases = (("standalone-prefix-dot", "."),)
            for case_name, source_prefix in standalone_resolver_cases:
                with self.subTest(case=case_name):
                    resolved = subprocess.run(
                        [
                            "bash",
                            "-c",
                            "source \"$1\"\n"
                            "agent_canon_source_identity \"$2\" \"$3\" \"$4\"\n",
                            "bash",
                            str(
                                ROOT
                                / "tools" / "runtime" / "support" / "agent_canon_source_identity.sh"
                            ),
                            str(root),
                            source_prefix,
                            str(root),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        resolved.returncode, 0, resolved.stdout + resolved.stderr
                    )
                    self.assertEqual(resolved.stdout.strip(), standalone_commit)

    def test_active_source_build_always_invokes_cargo_and_has_no_receipt(self) -> None:
        """Cargo owns incremental detection; active-source installs are not cached."""
        active = self._active_source_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            source = root / "rust" / "agent-canon"
            source.mkdir(parents=True)
            (source / "Cargo.toml").write_text(
                "[package]\nname = 'agent-canon'\nversion = '0.1.0'\nedition = '2021'\n",
                encoding="utf-8",
            )
            runner = ActiveSourceCargoRunner()
            plan = build_plan((loaded_manifest(Path("fixture.toml"), (active,)),))
            receipts = root / "receipts"
            installer = Installer(runner)
            installer.install(plan, workspace=root, receipts=receipts)
            installer.install(plan, workspace=root, receipts=receipts)
            self.assertEqual(runner.cargo_builds, 2)
            cargo_commands = [
                command for command in runner.calls if command[:2] == ("cargo", "build")
            ]
            self.assertTrue(
                all(
                    "--release" in command and "--locked" in command
                    for command in cargo_commands
                )
            )
            self.assertFalse((receipts / "agent-canon-cli.json").exists())
            self.assertFalse(any(command[:2] == ("git", "-C") for command in runner.calls))

    def test_active_source_build_accepts_source_mutation_without_identity_checks(self) -> None:
        """Cargo owns source change handling and the active install stays receipt-free."""
        active = parse_record(
            record(
                "agent-canon-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://example.test/agent-canon.git",
                source_identity="active-source",
                locked=True,
                verification={
                    "kind": "cargo-binary",
                    "path": "target/release/agent-canon",
                    "args": ["--version"],
                    "output_contains": "agent-canon 0.1.0",
                },
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-b", "main", str(root)], check=True)
            for key, value in (
                ("user.name", "Active Source Build Test"),
                ("user.email", "active-source-build@example.invalid"),
            ):
                subprocess.run(["git", "config", key, value], cwd=root, check=True)
            source = root / "rust" / "agent-canon"
            source.mkdir(parents=True)
            (source / "Cargo.toml").write_text(
                "[package]\nname = 'agent-canon'\nversion = '0.1.0'\nedition = '2021'\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "source"], cwd=root, check=True
            )
            source_identity = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps({"source_identity": source_identity}) + "\n",
                encoding="utf-8",
            )
            (root / "receipt-mutation").write_text("mutation\n", encoding="utf-8")
            subprocess.run(["git", "add", "receipt-mutation"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "receipt mutation"], cwd=root, check=True
            )
            receipt_check = subprocess.run(
                [
                    "bash",
                    "-c",
                    "source \"$1\"\n"
                    "current=\"$(agent_canon_source_identity \"$2\" \"$3\" \"$4\")\"\n"
                    "agent_canon_receipt_matches_identity \"$5\" \"$current\"\n",
                    "bash",
                    str(ROOT / "tools" / "runtime" / "support" / "agent_canon_source_identity.sh"),
                    str(root),
                    "vendor/agent-canon",
                    str(root),
                    str(receipt),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(receipt_check.returncode, 0)
            self.assertIn("receipt source identity mismatch", receipt_check.stderr)
            fake_cargo_home = root / "fake-cargo-home"
            fake_bin = fake_cargo_home / "bin"
            fake_bin.mkdir(parents=True)
            cargo = fake_bin / "cargo"
            cargo.write_text(
                "#!/usr/bin/env bash\n"
                "manifest=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = '--manifest-path' ]; then manifest=\"$2\"; shift 2; else shift; fi\n"
                "done\n"
                "crate_dir=\"$(dirname \"$manifest\")\"\n"
                "mkdir -p \"${CARGO_TARGET_DIR:?}/release\"\n"
                "printf '%s\\n' '#!/usr/bin/env sh' \"printf '%s\\n' 'agent-canon 0.1.0'\" > \"${CARGO_TARGET_DIR:?}/release/agent-canon\"\n"
                "chmod +x \"${CARGO_TARGET_DIR:?}/release/agent-canon\"\n"
                "printf '%s\\n' mutation > \"$crate_dir/build-mutation\"\n"
                "git -C \"$crate_dir\" add build-mutation\n"
                "git -C \"$crate_dir\" commit -m 'build mutation' >/dev/null\n",
                encoding="utf-8",
            )
            cargo.chmod(0o755)
            plan = build_plan((loaded_manifest(Path("fixture.toml"), (active,)),))
            receipts = root / "receipts"
            environment = dict(os.environ)
            environment["CARGO_HOME"] = str(fake_cargo_home)
            with mock.patch.dict(os.environ, environment, clear=True):
                Installer().install(plan, workspace=root, receipts=receipts)
            self.assertFalse((receipts / "agent-canon-cli.json").exists())

    def _retired_rebuild_uses_external_runtime_and_rejects_mid_build_source_drift(self) -> None:
        """A standalone source clone builds externally and cannot mutate during build."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "parent"
            source = parent / "vendor" / "agent-canon"
            source.mkdir(parents=True)

            for repository in (source, parent):
                subprocess.run(
                    ["git", "init", "-b", "main", str(repository)], check=True
                )
                subprocess.run(
                    ["git", "config", "user.name", "Provenance Test"],
                    cwd=repository,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", "provenance@example.invalid"],
                    cwd=repository,
                    check=True,
                )
            rust_root = source / "rust" / "agent-canon"
            rust_root.mkdir(parents=True)
            (rust_root / "Cargo.toml").write_text(
                "[package]\nname = 'agent-canon'\nversion = '0.1.0'\nedition = '2021'\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-m", "source"], cwd=source, check=True
            )
            source_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            tools = source / "tools"
            tools.mkdir()
            (tools / "lib").mkdir()
            (tools / "agent_tools").mkdir()
            shutil.copy2(ROOT / "bootstrap.sh", tools / "retired-rebuild-agent-tools")
            shutil.copy2(
                ROOT / "tools" / "runtime" / "support" / "agent_canon_source_identity.sh",
                tools / "lib",
            )
            shutil.copy2(
                ROOT / "tools" / "repository" / "workspace" / "parent_root_side_effects.py",
                tools / "agent_tools",
            )
            shutil.copy2(
                ROOT / "tools" / "runtime" / "artifacts" / "runtime_artifacts.py",
                tools / "agent_tools",
            )
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            cargo = fake_bin / "cargo"
            cargo.write_text(
                "#!/usr/bin/env bash\n"
                "manifest=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = '--manifest-path' ]; then manifest=\"$2\"; shift 2; else shift; fi\n"
                "done\n"
                "crate_dir=\"$(dirname \"$manifest\")\"\n"
                "mkdir -p \"${CARGO_TARGET_DIR:?}/release\"\n"
                "printf '%s\\n' '#!/usr/bin/env bash' \"echo 'agent-canon test 0.1.0'\" > \"${CARGO_TARGET_DIR:?}/release/agent-canon\"\n"
                "chmod +x \"${CARGO_TARGET_DIR:?}/release/agent-canon\"\n"
                "if [ \"${AGENT_CANON_TEST_MUTATE_SOURCE:-0}\" = \"1\" ]; then\n"
                "  printf '%s\\n' mutation > \"$crate_dir/build-mutation\"\n"
                "  git -C \"$crate_dir\" add build-mutation\n"
                "  git -C \"$crate_dir\" commit -m 'build mutation' >/dev/null\n"
                "fi\n",
                encoding="utf-8",
            )
            cargo.chmod(0o755)
            runtime_root = parent / "workspace" / "agent-canon-runtime"
            runtime_root.mkdir(parents=True)
            tools_home = runtime_root / "tools-home"
            environment = dict(os.environ)
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            environment["AGENT_CANON_CONTROL_PARENT_ROOT"] = str(parent)
            environment["AGENT_CANON_RUNTIME_ROOT"] = str(runtime_root)
            environment["AGENT_CANON_TOOLS_HOME"] = str(tools_home)
            environment["CARGO_HOME"] = str(runtime_root / "cache/cargo-home")
            environment["CARGO_TARGET_DIR"] = str(runtime_root / "cache/cargo-target")
            environment["AGENT_CANON_CLI_TARGET_DIR"] = environment[
                "CARGO_TARGET_DIR"
            ]
            host_home = parent / "host-home"
            environment["HOME"] = str(host_home)
            environment["AGENT_CANON_SKIP_USR_LOCAL_LINK"] = "1"

            accepted = subprocess.run(
                ["bash", str(tools / "retired-rebuild-agent-tools")],
                cwd=parent,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            self.assertIn(
                f"AGENT_CANON_TOOL_REBUILD_CARGO_HOME={runtime_root / 'cache/cargo-home'}",
                accepted.stdout,
            )
            self.assertFalse((host_home / ".cargo").exists())
            self.assertFalse((source / "target").exists())
            self.assertFalse((source / "rust" / "agent-canon" / "target").exists())
            state = (tools_home / "agent-canon" / ".build-state").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"agent_canon_source_commit={source_commit}\n", state)

            outside_environment = dict(environment)
            outside_tools = root / "outside-tools"
            outside_environment["AGENT_CANON_TOOLS_HOME"] = str(outside_tools)
            outside = subprocess.run(
                ["bash", str(tools / "retired-rebuild-agent-tools")],
                cwd=parent,
                env=outside_environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(outside.returncode, 0)
            self.assertIn("runtime boundary invalid", outside.stderr)
            self.assertFalse(outside_tools.exists())

            published_binary = tools_home / "agent-canon" / "bin" / "agent-canon"
            published_binary_before_mutation = published_binary.read_bytes()
            mutation_environment = dict(environment)
            mutation_environment["AGENT_CANON_FORCE_TOOL_REBUILD"] = "1"
            mutation_environment["AGENT_CANON_TEST_MUTATE_SOURCE"] = "1"
            mutation = subprocess.run(
                ["bash", str(tools / "retired-rebuild-agent-tools")],
                cwd=parent,
                env=mutation_environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mutation.returncode, 0)
            self.assertIn("source identity changed during build", mutation.stderr)
            self.assertEqual(published_binary.read_bytes(), published_binary_before_mutation)
            self.assertEqual(
                (tools_home / "agent-canon" / ".build-state").read_text(
                    encoding="utf-8"
                ),
                state,
            )

    def test_warn_provider_is_unavailable_to_dependents(self) -> None:
        provider = parse_record(
            record("provider", method="apt-package", failure_policy="warn"),
            path=Path("x.toml"),
            index=0,
        )
        dependent = parse_record(
            record("dependent", method="npm-global", deps=["provider"]),
            path=Path("x.toml"),
            index=1,
        )
        plan = build_plan((loaded_manifest(Path("x.toml"), (provider, dependent)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            runner = FakeRunner(fail_on="apt-get")
            with self.assertRaisesRegex(
                DependencyError, "dependency unavailable: dependent depends on provider"
            ):
                Installer(runner).install(
                    plan, workspace=root, receipts=root / "receipts"
                )
            self.assertEqual([call[0] for call in runner.calls], ["apt-get"])
            self.assertFalse((root / "receipts" / "provider.json").exists())
            self.assertFalse((root / "receipts" / "dependent.json").exists())

    def test_browser_install_uses_typed_shared_cache_environment(self) -> None:
        browser = parse_record(
            record(
                "browser",
                method="browser-install",
                package="chromium",
                browser="chromium",
                browser_cache_path="/usr/local/share/ms-playwright",
            ),
            path=Path("x.toml"),
            index=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            cache = root / "ms-playwright"
            executable = cache / "chromium-123" / "chrome-linux" / "chrome"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/usr/bin/env true\n", encoding="utf-8")
            executable.chmod(0o755)
            browser = replace(browser, browser_cache_path=str(cache))
            plan = build_plan((loaded_manifest(Path("x.toml"), (browser,)),))
            runner = FakeRunner(emulate_non_root_sudo=True)
            Installer(runner).install(plan, workspace=root, receipts=root / "receipts")
            privileged_install = (
                "sudo",
                "env",
                f"PLAYWRIGHT_BROWSERS_PATH={cache}",
                "playwright",
                "install",
                "--with-deps",
                "chromium",
            )
            self.assertIn(privileged_install, runner.calls)
            self.assertIsNone(
                runner.environments[runner.calls.index(privileged_install)]
            )
            verifier = (str(executable), "--version")
            self.assertIn(verifier, runner.calls)
            verifier_environment = runner.environments[runner.calls.index(verifier)]
            self.assertIsNotNone(verifier_environment)
            assert verifier_environment is not None
            self.assertEqual(
                verifier_environment["PLAYWRIGHT_BROWSERS_PATH"],
                str(cache),
            )

    def test_toolchain_installers_bootstrap_and_publish_home_paths(self) -> None:
        rust = parse_record(
            record(
                "rust",
                method="rust-toolchain",
                version="1.89.0",
                provides=["rust", "cargo"],
                components=["rustfmt", "clippy"],
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        lean = parse_record(
            record(
                "lean",
                method="lean-toolchain",
                version="leanprover/lean4:v4.30.0",
            ),
            path=Path("fixture.toml"),
            index=1,
        )
        cargo = parse_record(
            record(
                "agent-cli",
                method="cargo-source-build",
                source="rust/agent-canon",
                repo="https://example.test/agent-canon.git",
                commit="a" * 40,
                locked=True,
                deps=["cargo"],
            ),
            path=Path("fixture.toml"),
            index=2,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (rust, lean, cargo)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            (root / "rust" / "agent-canon").mkdir(parents=True)
            binary = root / "rust" / "agent-canon" / "target" / "release" / "agent-cli"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/usr/bin/env true\n", encoding="utf-8")
            binary.chmod(0o755)
            runner = FakeRunner()
            with mock.patch.dict(
                os.environ, {"HOME": str(root), "PATH": "/usr/bin"}, clear=False
            ):
                Installer(runner).install(
                    plan, workspace=root, receipts=root / "receipts"
                )

        self.assertIn(
            (
                "/usr/local/bin/rustup-init",
                "-y",
                "--default-toolchain",
                "none",
                "--profile",
                "minimal",
                "--no-modify-path",
            ),
            runner.calls,
        )
        self.assertIn(
            (
                "/usr/local/bin/elan-init",
                "-y",
                "--default-toolchain",
                "leanprover/lean4:v4.30.0",
                "--no-modify-path",
            ),
            runner.calls,
        )
        self.assertIn(("elan", "show"), runner.calls)
        self.assertNotIn(("elan", "default"), runner.calls)
        cargo_build_index = next(
            index
            for index, command in enumerate(runner.calls)
            if command[:2] == ("cargo", "build")
        )
        tool_environment = runner.environments[cargo_build_index]
        self.assertIsNotNone(tool_environment)
        assert tool_environment is not None
        self.assertEqual(
            tool_environment["CARGO_HOME"], f"{root}/.agent-canon/cache/cargo-home"
        )
        self.assertEqual(tool_environment["RUSTUP_HOME"], f"{root}/.rustup")
        self.assertEqual(tool_environment["ELAN_HOME"], f"{root}/.elan")
        self.assertEqual(
            tool_environment["PATH"],
            f"{root}/.cargo/bin:{root}/.elan/bin:{root}/.local/bin:/usr/bin",
        )

    def test_lean_retry_uses_live_toolchain_without_receipt(self) -> None:
        lean = parse_record(
            record(
                "lean",
                method="lean-toolchain",
                version="leanprover/lean4:v4.30.0",
            ),
            path=Path("fixture.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("fixture.toml"), (lean,)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_authentic_git(root)
            receipts = root / "receipts"
            runner = LeanToolchainRetryRunner()
            with self.assertRaises(DependencyError):
                Installer(runner).install(plan, workspace=root, receipts=receipts)
            self.assertFalse((receipts / "lean.json").exists())

            first_attempt_calls = tuple(runner.calls)
            self.assertIn(
                ("elan", "toolchain", "install", "leanprover/lean4:v4.30.0"),
                first_attempt_calls,
            )
            self.assertEqual(
                Installer(runner).install(plan, workspace=root, receipts=receipts),
                ("lean",),
            )

        second_attempt_calls = runner.calls[len(first_attempt_calls) :]
        self.assertNotIn(
            ("elan", "toolchain", "install", "leanprover/lean4:v4.30.0"),
            second_attempt_calls,
        )
        self.assertIn(
            ("elan", "default", "leanprover/lean4:v4.30.0"),
            second_attempt_calls,
        )

    def test_method_specific_security_values_fail_closed(self) -> None:
        with self.assertRaisesRegex(DependencyError, "full 40-digit"):
            parse_record(
                record(
                    "repo",
                    method="apt-repository",
                    key_url="https://example.test/key",
                    key_fingerprint="C99B11DEB97541F0",
                ),
                path=Path("x.toml"),
                index=0,
            )
        with self.assertRaisesRegex(DependencyError, "unsupported fields"):
            parse_record(
                record(
                    "npm",
                    method="npm-global",
                    browser_cache_path="/usr/local/share/ms-playwright",
                ),
                path=Path("x.toml"),
                index=0,
            )
        with self.assertRaisesRegex(DependencyError, "workspace"):
            parse_record(
                record(
                    "cargo",
                    method="cargo-source-build",
                    source="../outside",
                    repo="https://example.test/repo.git",
                    commit="a" * 40,
                    locked=True,
                ),
                path=Path("x.toml"),
                index=0,
            )

    def test_image_owned_dependency_and_shared_bootstrap_contract(self) -> None:
        dockerfile = (ROOT / "bootstrap" / "container" / "image" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertFalse((ROOT / ".devcontainer").exists())
        self.assertIn("node:22.14.0-bullseye-slim@sha256:", dockerfile)
        self.assertIn("COPY --from=node-provider /usr/local/lib/node_modules", dockerfile)
        self.assertIn(
            "COPY tools/repository/workspace/parent_root_side_effects.py "
            "/opt/agent-canon/tools/repository/workspace/parent_root_side_effects.py",
            dockerfile,
        )
        self.assertIn("!tools/repository/workspace/parent_root_side_effects.py", dockerignore)
        self.assertIn("dependency_plan.py", dockerfile)
        self.assertIn("image-install --workspace /opt/agent-canon", dockerfile)
        self.assertIn(
            "CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo", dockerfile
        )
        self.assertIn(
            "PATH=/usr/local/share/agent-canon/toolchains/cargo/bin", dockerfile
        )
        self.assertIn("--final-binary-dir /usr/local/bin", dockerfile)
        self.assertIn("rm -rf /opt/agent-canon", dockerfile)
        self.assertIn("/usr/local/share/agent-canon/image-dependencies", dockerfile)
        self.assertIn("python3-pip", dockerfile)
        self.assertIn("python3-packaging", dockerfile)
        self.assertIn("build-essential", dockerfile)
        self.assertIn("ninja-build", dockerfile)
        self.assertNotIn("USER agentcanon", dockerfile)
        self.assertNotIn("AGENT_CANON_RUNTIME_UID", dockerfile)
        self.assertNotIn("AGENT_CANON_RUNTIME_GID", dockerfile)
        self.assertIn("ARG TARGETARCH", dockerfile)
        self.assertIn("linux/arm64", dockerfile)
        self.assertIn('io.agent-canon.run.network="none"', dockerfile)

    def test_project_extras_are_ordered_and_installed_then_checked(self) -> None:
        workspace = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, workspace)
        (workspace / "pyproject.toml").write_text(
            "[project]\nname='fixture'\nversion='0.1'\n"
            "[project.optional-dependencies]\ndev=[]\ncuda12=[]\n",
            encoding="utf-8",
        )
        runner = FakeRunner()
        installed = dependency_module.install_project_extras(
            workspace, ("dev", "cuda12"), runner=runner
        )
        self.assertEqual(installed, ("dev", "cuda12"))
        self.assertEqual(runner.calls[0][4], "--editable")
        self.assertIn("[dev,cuda12]", runner.calls[0][5])
        self.assertEqual(runner.calls[1], (sys.executable, "-m", "pip", "check"))

    def test_project_extras_reject_unknown_and_duplicate_names(self) -> None:
        with self.assertRaisesRegex(DependencyError, "duplicate"):
            dependency_module.parse_python_extras(("dev", "DEV"))
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "pyproject.toml").write_text(
                "[project.optional-dependencies]\ndev=[]\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(DependencyError, "not declared"):
                dependency_module.validate_project_extras(workspace, ("cuda12",))


if __name__ == "__main__":
    unittest.main()
