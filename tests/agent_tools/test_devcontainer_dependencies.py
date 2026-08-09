"""Focused tests for the declarative devcontainer dependency model."""

# @dependency-start
# contract test
# responsibility Verifies schema, merge, order, security, and receipt semantics for devcontainer dependencies.
# upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md dependency model contract
# upstream implementation ../../tools/agent_tools/devcontainer_dependencies.py typed dependency engine
# downstream implementation ../../.devcontainer/dependencies.toml canonical manifest inventory
# downstream implementation ../../tools/rebuild_agent_tools.sh installed CLI provenance
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import shutil
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

from tools.agent_tools import devcontainer_dependencies as dependency_module
from tools.agent_tools.devcontainer_dependencies import (
    BASE_CAPABILITIES,
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
    build_plan,
    install_plan,
    load_plan,
    manifest_sources,
    parse_record,
    safe_extract_tar,
    validate_runtime_identity,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "tools" / "agent_tools" / "devcontainer_dependencies.py"


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
        'schema = "agent-canon.devcontainer-dependencies"',
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


def write_boundary_fixture(
    root: Path,
    requirements: str,
) -> tuple[EnvironmentBoundaryModel, Path]:
    """Build a valid parent boundary fixture with project-owned packaging."""
    vendor_root = root / "vendor" / "agent-canon"
    vendor_root.parent.mkdir(parents=True, exist_ok=True)
    vendor_root.symlink_to(ROOT, target_is_directory=True)

    def write_file(relative: str, content: str, *, executable: bool = False) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    write_file("README.md", "# fixture\n")
    write_file("docker/README.md", "# fixture\n")
    write_file(
        "docker/Dockerfile",
        "FROM ubuntu:22.04\n",
    )
    del requirements
    write_file("pyproject.toml", "[build-system]\n")
    write_file(".dockerignore", "vendor/agent-canon\n.git\n.state\n")
    write_file(".gitignore", ".venv/\nvenv/\n")
    write_file(
        ".devcontainer/devcontainer.json",
        '{"postCreateCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py '
        'exec .devcontainer/post-create-entrypoint.sh post-create-parent.sh"}\n',
    )
    write_file(".devcontainer/post-create-parent.sh", "#!/bin/sh\n", executable=True)
    write_file(
        ".devcontainer/dependencies.toml",
        'schema = "agent-canon.devcontainer-dependencies"\n'
        "schema_version = 2\nrecords = []\n",
    )
    return EnvironmentBoundaryModel(root, vendor_root), root / "pyproject.toml"


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

    def test_npm_global_uses_stable_prefix_for_install_and_verification(self) -> None:
        parsed = parse_record(
            record("codex", method="npm-global"),
            path=Path("fixture.toml"),
            index=0,
        )
        runner = FakeRunner(emulate_non_root_sudo=True)
        installer = Installer(runner)
        feature_bin = dependency_module.NPM_FEATURE_BIN
        trusted_path = os.pathsep.join(dependency_module.NPM_TRUSTED_BIN_DIRS)

        def feature_which(name: str, *, path: str | None = None) -> str:
            self.assertEqual(path, trusted_path)
            return f"{feature_bin}/{name}"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(
                dependency_module.shutil, "which", side_effect=feature_which
            ):
                installer.install_record(parsed, workspace=root)
                installer.verify(parsed, workspace=root)

        install_call = next(
            call
            for call in runner.calls
            if "install" in call and any(Path(item).name == "npm" for item in call)
        )
        self.assertEqual(
            install_call,
            (
                "sudo",
                "env",
                f"PATH={trusted_path}",
                f"{feature_bin}/npm",
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
            if call[:2] == (f"{feature_bin}/npm", "ls")
        )
        self.assertEqual(
            runner.calls[ls_index],
            (
                f"{feature_bin}/npm",
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
        feature_bin = dependency_module.NPM_FEATURE_BIN
        trusted_path = os.pathsep.join(dependency_module.NPM_TRUSTED_BIN_DIRS)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                (
                    "workspace",
                    {
                        "node": str(root / "node"),
                        "npm": f"{feature_bin}/npm",
                    },
                    "inside workspace",
                ),
                (
                    "untrusted",
                    {
                        "node": "/tmp/agent-canon-untrusted/node",
                        "npm": f"{feature_bin}/npm",
                    },
                    "outside trusted Node/system directories",
                ),
                (
                    "missing-node",
                    {"node": None, "npm": f"{feature_bin}/npm"},
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

                    with mock.patch.object(
                        dependency_module.shutil, "which", side_effect=fake_which
                    ):
                        with self.assertRaisesRegex(DependencyError, message):
                            Installer(FakeRunner()).install_record(
                                parsed, workspace=root
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

            vendored = root / "vendor" / "agent-canon" / "rust" / "agent-canon"
            vendored.mkdir(parents=True)
            self.assertEqual(installer._cargo_source(cargo, root), vendored)

            outside = root.parent / f"{root.name}-outside"
            outside.mkdir()
            vendor_root = root / "vendor" / "agent-canon"
            vendored.rmdir()
            (vendor_root / "rust").rmdir()
            vendor_root.rmdir()
            vendor_root.symlink_to(outside, target_is_directory=True)
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

        def write_fixture(url: str, destination: Path) -> None:
            self.assertEqual(
                url,
                "https://apt.example.test/jammy/dists/jammy/main/"
                "binary-amd64/Packages",
            )
            destination.write_bytes(payload)

        with mock.patch(
            "tools.agent_tools.devcontainer_dependencies._download",
            side_effect=write_fixture,
        ):
            Installer._verify_repository_packages_digest(parsed)

        mismatched = replace(
            parsed, repository_packages_sha256=hashlib.sha256(b"different").hexdigest()
        )
        with mock.patch(
            "tools.agent_tools.devcontainer_dependencies._download",
            side_effect=write_fixture,
        ):
            with self.assertRaisesRegex(DependencyError, "Packages index SHA256 mismatch"):
                Installer._verify_repository_packages_digest(mismatched)

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

        def write_download(url: str, destination: Path) -> None:
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

        with (
            mock.patch.object(runner, "run", side_effect=run_with_key_fingerprint),
            mock.patch(
                "tools.agent_tools.devcontainer_dependencies._download",
                side_effect=write_download,
            ),
        ):
            Installer(runner)._install_apt_repository(
                parsed, Path("/tmp/workspace"), repair=False
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
                Installer(runner)._install_apt_repository(
                    mismatched, Path("/tmp/workspace"), repair=False
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
            receipt = Path(temporary) / "repo.json"
            Installer._write_receipt(receipt, plan, parsed)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["repository_packages"]["sha256"], rolling_sha)
            self.assertEqual(payload["repository_package"]["sha256"], immutable_sha)
            self.assertTrue(Installer._receipt_matches(receipt, plan, parsed))
            payload["repository_package"]["sha256"] = rolling_sha
            receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            self.assertFalse(Installer._receipt_matches(receipt, plan, parsed))

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
            manifest = root / ".devcontainer" / "dependencies.toml"
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
                        root, None, receipts, "pyright-language-server", "pyright"
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
                            None,
                            receipts,
                            "pyright-language-server",
                            "pyright",
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
                            None,
                            receipts,
                            "pyright-language-server",
                            "pyright",
                        )

    def test_secondary_npm_binding_is_structural_not_a_help_probe(self) -> None:
        """A secondary provider may reject generic help while remaining bound."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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

        def download(url: str, destination: Path) -> None:
            self.assertEqual(
                url,
                "https://static.rust-lang.org/rustup/archive/1.28.2/"
                "x86_64-unknown-linux-gnu/rustup-init",
            )
            destination.write_bytes(content)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch(
                    "tools.agent_tools.devcontainer_dependencies.architecture",
                    return_value="x86_64",
                ),
                mock.patch(
                    "tools.agent_tools.devcontainer_dependencies._download",
                    side_effect=download,
                ),
            ):
                Installer(runner).install_record(parsed, workspace=root)

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

    def test_manifest_sources_parent_first_and_standalone_once(self) -> None:
        """Resolve structural roles parent-first and canonicalize standalone use."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / ".devcontainer" / "dependencies.toml"
            vendor = (
                root / "vendor" / "agent-canon" / ".devcontainer" / "dependencies.toml"
            )
            write_manifest(parent, [record("parent")])
            write_manifest(vendor, [record("vendor")])
            self.assertEqual(
                manifest_sources(root),
                (
                    ManifestSource(parent, ManifestRole.PARENT_OVERLAY),
                    ManifestSource(vendor, ManifestRole.CANONICAL),
                ),
            )
            agent_root = vendor.parents[1]
            self.assertEqual(
                manifest_sources(agent_root, agent_root),
                (ManifestSource(vendor, ManifestRole.CANONICAL),),
            )

    def test_manifest_sources_rejects_stale_tools_agent_canon_duplicate(self) -> None:
        """Reject an identical copied manifest that is not the canonical entity."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vendor = (
                root / "vendor" / "agent-canon" / ".devcontainer" / "dependencies.toml"
            )
            tools = (
                root / "tools" / "agent-canon" / ".devcontainer" / "dependencies.toml"
            )
            write_manifest(vendor, [record("vendor")])
            write_manifest(tools, [record("vendor")])

            with self.assertRaisesRegex(DependencyError, "ambiguous canonical"):
                manifest_sources(root, root / "vendor" / "agent-canon")

    def test_manifest_sources_never_uses_tools_projection_manifest(self) -> None:
        """A tools projection cannot become the canonical dependency manifest."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = (
                root / "tools" / "agent-canon" / ".devcontainer" / "dependencies.toml"
            )
            write_manifest(tools, [record("tools")])

            self.assertEqual(
                manifest_sources(root, root / "vendor" / "agent-canon"), ()
            )

    def test_boundary_requires_entrypoint_parent_hook_dispatch(self) -> None:
        """The resolver entrypoint, not JSON text, owns the derived parent hook."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model, _ = write_boundary_fixture(
                root,
                "jupyterlab\nnotebook\nipykernel\npydeps\nsnakeviz\npyyaml\n",
            )
            vendor_root = root / "vendor/agent-canon"
            vendor_root.unlink()
            vendor_root.mkdir(parents=True)
            entrypoint = vendor_root / ".devcontainer/post-create-entrypoint.sh"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_text("#!/bin/sh\n", encoding="utf-8")
            findings: list[Any] = []
            checked: list[str] = []
            model._check_parent_devcontainer(findings, checked)

        self.assertTrue(
            any(
                finding.detail.startswith("missing-parent-hook-dispatch:")
                for finding in findings
            )
        )

    def test_boundary_accepts_absent_parent_overlay_and_hook(self) -> None:
        """A derived repository may omit all parent-owned devcontainer overlays."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model, _ = write_boundary_fixture(
                root,
                "jupyterlab\nnotebook\nipykernel\npydeps\nsnakeviz\npyyaml\n",
            )
            (root / ".devcontainer/dependencies.toml").unlink()
            (root / ".devcontainer/post-create-parent.sh").unlink()

            report = model.validate()

        self.assertFalse(
            any(
                finding.path.endswith(
                    (".devcontainer/dependencies.toml", ".devcontainer/post-create-parent.sh")
                )
                and finding.detail == "missing-file"
                for finding in report.findings
            )
        )

    def test_canonical_manifest_is_a_small_default_tool_set(self) -> None:
        """Default startup retains only LSP and small structure/agent tools."""
        plan = load_plan(ROOT, ROOT)
        ids = {item.id for item in plan.records}
        self.assertEqual(
            ids,
            {
                "github-cli",
                "codex-cli",
                "pyright-language-server",
                "bash-language-server",
                "jq",
                "tree",
                "clang-format",
                "clangd-language-server",
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
            "rust-toolchain",
            "lean-toolchain",
            "agent-canon-cli",
            "pyyaml",
        ):
            self.assertNotIn(removed, ids)

    def test_canonical_apt_records_are_jammy_amd64_owned(self) -> None:
        """The shared apt tool records target the canonical Ubuntu 22.04 base."""
        plan = load_plan(ROOT, ROOT)
        apt_records = [
            item for item in plan.records if item.method.value == "apt-package"
        ]

        self.assertTrue(apt_records)
        self.assertTrue(
            all(item.platform == "linux/amd64" for item in apt_records)
        )
        self.assertTrue(all(item.source == "ubuntu:22.04" for item in apt_records))
        self.assertFalse(any(item.source == "ubuntu:24.04" for item in apt_records))

    def test_install_identity_accepts_ubuntu22_amd64(self) -> None:
        """The canonical install gate accepts only the selected base identity."""
        parsed = parse_record(
            record(
                "jammy-tool",
                method="apt-package",
                source="ubuntu:22.04",
                platform="linux/amd64",
            ),
            path=Path("identity.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("identity.toml"), (parsed,)),))
        identity = RuntimeIdentity("ubuntu", "22.04", "linux/amd64")
        self.assertEqual(validate_runtime_identity(plan, identity), identity)

    def test_install_identity_rejects_wrong_release_or_arch_before_runner(self) -> None:
        """Jammy/amd64 identity failures happen before Installer runner calls."""
        parsed = parse_record(
            record(
                "jammy-tool",
                method="apt-package",
                source="ubuntu:22.04",
                platform="linux/amd64",
            ),
            path=Path("identity.toml"),
            index=0,
        )
        plan = build_plan((loaded_manifest(Path("identity.toml"), (parsed,)),))
        for identity in (
            RuntimeIdentity("ubuntu", "24.04", "linux/amd64"),
            RuntimeIdentity("ubuntu", "22.04", "linux/arm64"),
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

    def test_empty_parent_overlay_merges_with_nonempty_vendor_manifest(self) -> None:
        """Allow an empty parent overlay when the canonical vendor is non-empty."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_manifest(root / ".devcontainer" / "dependencies.toml", [])
            write_manifest(
                root / "vendor" / "agent-canon" / ".devcontainer" / "dependencies.toml",
                [record("vendor")],
            )

            plan = load_plan(root)

        self.assertEqual(tuple(record.id for record in plan.records), ("vendor",))

    def test_standalone_empty_manifest_is_rejected(self) -> None:
        """Reject an empty standalone canonical manifest."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / ".devcontainer" / "dependencies.toml"
            write_manifest(manifest, [])

            with self.assertRaisesRegex(DependencyError, "non-empty"):
                load_plan(root, root)

    def test_vendor_empty_manifest_is_rejected(self) -> None:
        """Reject an empty vendor canonical manifest."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_manifest(
                root / "vendor" / "agent-canon" / ".devcontainer" / "dependencies.toml",
                [],
            )

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
        self.assertNotIn("shell=True", ENGINE.read_text(encoding="utf-8"))
        self.assertNotIn("eval(", ENGINE.read_text(encoding="utf-8"))

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
            (repository / "rust" / "agent-canon" / "Cargo.toml").write_text(
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
                                / "tools"
                                / "lib"
                                / "agent_canon_source_identity.sh"
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

        derived_cases = (
            ("detached-gitlink-match", "match"),
            ("detached-gitlink-drift", "mismatch"),
            ("missing-git-metadata", "missing"),
        )
        for case_name, case_kind in derived_cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                parent = root / "parent"
                source = parent / "vendor" / "agent-canon"
                source.mkdir(parents=True)
                init_repository(source)
                write_cli_source(source)
                source_commit = commit_repository(source, "vendor source")
                init_repository(parent)
                subprocess.run(
                    [
                        "git",
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        f"160000,{source_commit},vendor/agent-canon",
                    ],
                    cwd=parent,
                    check=True,
                )
                parent_commit = commit_repository(parent, "accepted vendor gitlink")
                self.assertEqual(
                    subprocess.run(
                        ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                        cwd=parent,
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip(),
                    source_commit,
                )
                self.assertNotEqual(parent_commit, source_commit)

                if case_kind == "mismatch":
                    (source / "provider-drift").write_text(
                        "drift\n", encoding="utf-8"
                    )
                    mismatched_source_commit = commit_repository(
                        source, "provider drift"
                    )
                    self.assertNotEqual(source_commit, mismatched_source_commit)
                    subprocess.run(
                        ["git", "checkout", "--detach", mismatched_source_commit],
                        cwd=source,
                        check=True,
                        capture_output=True,
                    )
                elif case_kind in ("match", "missing"):
                    subprocess.run(
                        ["git", "checkout", "--detach", source_commit],
                        cwd=source,
                        check=True,
                        capture_output=True,
                    )
                if case_kind == "missing":
                    shutil.rmtree(source / ".git")

                self.assertIsNone(installer.verify(active, workspace=parent))

    def test_active_source_build_always_invokes_cargo_and_has_no_receipt(self) -> None:
        """Cargo owns incremental detection; active-source installs are not cached."""
        active = self._active_source_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    str(ROOT / "tools" / "lib" / "agent_canon_source_identity.sh"),
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
                "mkdir -p \"$crate_dir/target/release\"\n"
                "printf '%s\\n' '#!/usr/bin/env sh' \"printf '%s\\n' 'agent-canon 0.1.0'\" > \"$crate_dir/target/release/agent-canon\"\n"
                "chmod +x \"$crate_dir/target/release/agent-canon\"\n"
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

    def test_rebuild_provenance_uses_parent_gitlink_and_rejects_source_drift(self) -> None:
        """The installed CLI state records and enforces the selected provider identity."""
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
            subprocess.run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"160000,{source_commit},vendor/agent-canon",
                ],
                cwd=parent,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "parent gitlink"], cwd=parent, check=True
            )

            tools = parent / "tools"
            tools.mkdir()
            (tools / "lib").mkdir()
            shutil.copy2(ROOT / "tools" / "rebuild_agent_tools.sh", tools)
            shutil.copy2(
                ROOT / "tools" / "lib" / "agent_canon_source_identity.sh",
                tools / "lib",
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
                "mkdir -p \"$crate_dir/target/release\"\n"
                "printf '%s\\n' '#!/usr/bin/env bash' \"echo 'agent-canon test 0.1.0'\" > \"$crate_dir/target/release/agent-canon\"\n"
                "chmod +x \"$crate_dir/target/release/agent-canon\"\n"
                "if [ \"${AGENT_CANON_TEST_MUTATE_SOURCE:-0}\" = \"1\" ]; then\n"
                "  printf '%s\\n' mutation > \"$crate_dir/build-mutation\"\n"
                "  git -C \"$crate_dir\" add build-mutation\n"
                "  git -C \"$crate_dir\" commit -m 'build mutation' >/dev/null\n"
                "fi\n",
                encoding="utf-8",
            )
            cargo.chmod(0o755)
            tools_home = root / "tools-home"
            environment = dict(os.environ)
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            environment["AGENT_CANON_TOOLS_HOME"] = str(tools_home)
            environment["AGENT_CANON_SKIP_USR_LOCAL_LINK"] = "1"

            accepted = subprocess.run(
                ["bash", str(tools / "rebuild_agent_tools.sh")],
                cwd=parent,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            state = (tools_home / "agent-canon" / ".build-state").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"agent_canon_source_commit={source_commit}\n", state)

            published_binary = tools_home / "agent-canon" / "bin" / "agent-canon"
            published_binary_before_mutation = published_binary.read_bytes()
            mutation_environment = dict(environment)
            mutation_environment["AGENT_CANON_FORCE_TOOL_REBUILD"] = "1"
            mutation_environment["AGENT_CANON_TEST_MUTATE_SOURCE"] = "1"
            mutation = subprocess.run(
                ["bash", str(tools / "rebuild_agent_tools.sh")],
                cwd=parent,
                env=mutation_environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mutation.returncode, 0)
            self.assertIn("provider identity mismatch", mutation.stderr)
            self.assertEqual(published_binary.read_bytes(), published_binary_before_mutation)
            self.assertEqual(
                (tools_home / "agent-canon" / ".build-state").read_text(
                    encoding="utf-8"
                ),
                state,
            )

            (source / "provider-drift").write_text("drift\n", encoding="utf-8")
            subprocess.run(["git", "add", "provider-drift"], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-m", "provider drift"], cwd=source, check=True
            )
            rejected = subprocess.run(
                ["bash", str(tools / "rebuild_agent_tools.sh")],
                cwd=parent,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("provider identity mismatch", rejected.stderr)

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
        self.assertEqual(tool_environment["CARGO_HOME"], f"{root}/.cargo")
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

    def test_image_feature_and_shared_post_create_contract(self) -> None:
        devcontainer = json.loads(
            (ROOT / ".devcontainer" / "devcontainer.json").read_text(
                encoding="utf-8"
            )
        )
        dockerfile = (ROOT / ".devcontainer" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        post_create = (ROOT / ".devcontainer" / "post-create.sh").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            devcontainer["features"],
            {
                "ghcr.io/devcontainers/features/node@sha256:586c9a6f7dd40bd3ba2cd41e7f2f88dcc31fbe5d1442afcbf07ffbc66b686857": {
                    "version": "22.14.0",
                    "npmVersion": "10.9.2",
                    "nodeGypDependencies": False,
                    "pnpmVersion": "none",
                }
            },
        )
        self.assertIn("python3-pip", dockerfile)
        self.assertIn("pipx", dockerfile)
        self.assertIn("python3-packaging", dockerfile)
        self.assertIn("build-essential", dockerfile)
        self.assertIn("ninja-build", dockerfile)
        self.assertNotIn("bootstrap-dependencies.sh", dockerfile)
        self.assertNotIn("--install-language-runtime", post_create)
        self.assertNotIn("npm install -g", post_create)
        self.assertNotIn("install_github_cli", post_create)
        self.assertNotIn("install_rust_toolchain", post_create)
        self.assertIn("STRUCTURED_ANALYSIS_BOOTSTRAP=warn", post_create)
        self.assertIn("project-install --workspace", post_create)
        self.assertNotIn("docker/install_python_dependencies.sh", post_create)
        self.assertIn(
            'state_home="${XDG_STATE_HOME:-$home/.local/state}"',
            post_create,
        )
        self.assertIn(
            'dependency_receipts="$state_home/agent-canon/dependency-receipts"',
            post_create,
        )
        self.assertNotIn(".agent-canon/dependency-receipts", post_create)
        validate_index = post_create.index("validate --workspace")
        install_index = post_create.index("install --workspace")
        cache_index = post_create.rindex("\nbuild_agent_canon_cache\n")
        projection_index = post_create.rindex("\npublish_container_local_runtime\n")
        self.assertLess(
            validate_index,
            install_index,
        )
        self.assertLess(cache_index, projection_index)
        self.assertNotIn("publish_agent_canon_cli", post_create)

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
