"""Focused tests for the declarative devcontainer dependency model."""

# @dependency-start
# contract test
# responsibility Verifies schema, merge, order, security, and receipt semantics for devcontainer dependencies.
# upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md dependency model contract
# upstream implementation ../../tools/agent_tools/devcontainer_dependencies.py typed dependency engine
# upstream implementation ../../tools/agent_tools/requirements_lock.py canonical requirements lock parser and result/error model
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

from tools.agent_tools.devcontainer_dependencies import (
    BASE_CAPABILITIES,
    DependencyError,
    EnvironmentBoundaryModel,
    Installer,
    LoadedManifest,
    ManifestRole,
    ManifestSource,
    RuntimeIdentity,
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
    if method == "pip-user":
        return {
            "kind": "python-distribution",
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
    """Build a valid parent boundary fixture with supplied requirements."""
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
        "FROM python:3.11\n"
        "RUN apt-get install -y rsync openssh-client graphviz python3-venv\n",
    )
    requirements_path = write_file("docker/requirements.txt", requirements)
    write_file(
        "docker/install_python_dependencies.sh",
        "python3 -m pip install -r docker/requirements.txt\n",
        executable=True,
    )
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
    return EnvironmentBoundaryModel(root, vendor_root), requirements_path


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
        if self.fail_once_on and command[0] == self.fail_once_on:
            self.fail_once_on = None
            raise subprocess.CalledProcessError(1, command)
        if self.fail_on and command[0] == self.fail_on:
            raise subprocess.CalledProcessError(1, command)
        if command == (sys.executable, "-c", "import site; print(site.getuserbase())"):
            return subprocess.CompletedProcess(
                command, 0, "/tmp/fake-python-user-base\n", ""
            )
        if command[:2] == ("dpkg-query", "--show"):
            package = command[-1]
            return subprocess.CompletedProcess(
                command,
                0,
                f"install ok installed\t1.0.0\t{package}\n",
                "",
            )
        if command[:3] == ("npm", "ls", "--global") and "--json" in command:
            package = command[-1]
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"dependencies": {package: {"version": "1.0.0"}}}),
                "",
            )
        if command[:4] == ("python3", "-m", "pip", "show"):
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
        runner = FakeRunner()
        installer = Installer(runner)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installer.install_record(parsed, workspace=root)
            installer.verify(parsed, workspace=root)

        install_call = next(
            call for call in runner.calls if call[:2] == ("npm", "install")
        )
        self.assertEqual(
            install_call,
            ("npm", "install", "--global", "--prefix", "/usr/local", "codex@1.0.0"),
        )
        ls_index = next(
            index
            for index, call in enumerate(runner.calls)
            if call[:2] == ("npm", "ls")
        )
        self.assertEqual(
            runner.calls[ls_index],
            (
                "npm",
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
        self.assertIn("/usr/local/bin", runner.environments[ls_index]["PATH"].split(os.pathsep))
        executable_index = next(
            index
            for index, call in enumerate(runner.calls)
            if call == ("codex", "--version")
        )
        self.assertEqual(runner.calls[executable_index], ("codex", "--version"))
        self.assertIsNotNone(runner.environments[executable_index])

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
            record("pip", method="pip-user"),
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

    def test_boundary_tool_resolution_uses_real_tools_projection(self) -> None:
        """Strip the source tools prefix when resolving the parent projection."""
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            vendor_root = workspace / "vendor" / "agent-canon"
            vendor_tools = vendor_root / "tools"
            vendor_tools.mkdir(parents=True)
            for relative in (
                "tools/requirement_sync_validator.py",
                "tools/ci/python_env_policy.py",
            ):
                path = vendor_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("print('ok')\n", encoding="utf-8")
            projection_root = workspace / "tools" / "agent-canon"
            projection_root.parent.mkdir(parents=True)
            projection_root.symlink_to(
                Path("..") / "vendor" / "agent-canon" / "tools",
                target_is_directory=True,
            )
            model = EnvironmentBoundaryModel(workspace, vendor_root)
            self.assertEqual(
                model._resolve_agent_canon_root_path(
                    "tools/requirement_sync_validator.py"
                ),
                vendor_root / "tools" / "requirement_sync_validator.py",
            )
            self.assertEqual(
                model._resolve_agent_canon_root_path("tools/ci/python_env_policy.py"),
                vendor_root / "tools" / "ci" / "python_env_policy.py",
            )

    def test_boundary_tool_resolution_rejects_stale_projection_ambiguity(
        self,
    ) -> None:
        """Reject identical copied roots and ignore parent compatibility wrappers."""
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            vendor_root = workspace / "vendor" / "agent-canon"
            source = vendor_root / "tools" / "requirement_sync_validator.py"
            projection = (
                workspace / "tools" / "agent-canon" / "requirement_sync_validator.py"
            )
            wrapper = workspace / "tools" / "requirement_sync_validator.py"
            for path, content in (
                (source, "source\n"),
                (projection, "source\n"),
                (wrapper, "wrapper\n"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            model = EnvironmentBoundaryModel(workspace, vendor_root)

            with self.assertRaisesRegex(DependencyError, "ambiguous AgentCanon"):
                model._resolve_agent_canon_root_path(
                    "tools/requirement_sync_validator.py"
                )

            projection.unlink()
            source.unlink()
            self.assertEqual(
                model._resolve_agent_canon_root_path(
                    "tools/requirement_sync_validator.py"
                ),
                source,
            )

    def test_requirements_parse_errors_project_to_boundary_findings(self) -> None:
        """Preserve the base finding detail for every parser error category."""
        backslash = chr(92)
        cases = {
            "malformed continuation": (
                f"package==1.0 {backslash}\n    not-a-hash\n",
                lambda path: f"{path}:2: malformed requirement continuation",
            ),
            "orphan hash": (
                f"--hash=sha256:{'a' * 64}\n",
                lambda path: f"{path}:1: orphan requirement hash",
            ),
            "malformed hash": (
                f"package==1.0 {backslash}\n    --hash=sha256:short\n",
                lambda path: f"{path}:2: malformed requirement hash",
            ),
            "requirement option": (
                "--index-url https://pypi.org/simple\n",
                lambda path: f"{path}:1: requirement option without requirement",
            ),
            "unterminated continuation": (
                f"package==1.0 {backslash}\n",
                lambda path: f"{path}: unterminated requirement continuation",
            ),
            "invalid requirement": (
                "not a requirement\n",
                lambda _path: "unsupported requirement syntax: not a requirement",
            ),
        }

        for name, (contents, expected_detail) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                model, path = write_boundary_fixture(Path(temporary), contents)
                report = model.validate()

                findings = [
                    finding for finding in report.findings if finding.path == str(path)
                ]

            self.assertEqual(
                [finding.detail for finding in findings],
                [expected_detail(path)],
            )

    def test_boundary_accepts_native_python_venv_package(self) -> None:
        """Ubuntu 22.04 uses the minor-independent python3-venv package."""
        with tempfile.TemporaryDirectory() as temporary:
            model, _ = write_boundary_fixture(
                Path(temporary),
                "jupyterlab\nnotebook\nipykernel\npydeps\nsnakeviz\npyyaml\n",
            )
            report = model.validate()

        self.assertNotIn(
            "missing-runtime-package:python3-venv",
            [finding.detail for finding in report.findings],
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

    def test_canonical_manifest_owns_pinned_pyyaml_independently(self) -> None:
        """AgentCanon's mounted validators receive their own exact PyYAML record."""
        plan = load_plan(ROOT, ROOT)
        pyyaml = next(item for item in plan.records if item.id == "pyyaml")

        self.assertEqual(pyyaml.package, "pyyaml")
        self.assertEqual(pyyaml.method.value, "pip-user")
        self.assertEqual(pyyaml.version, "6.0.3")
        self.assertEqual(pyyaml.deps, ("python3-pip",))
        self.assertEqual(pyyaml.verification.executable, "python3")
        self.assertTrue(
            any("yaml.__version__" in arg for arg in pyyaml.verification.args)
        )

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
            ("pip-user", "python-distribution"),
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
            self.assertIn(("tool", "--version"), resumed.calls)
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
                sum(command[0] == "dpkg-query" for command in rebuilt.calls),
                2,
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

    def test_active_source_identity_uses_standalone_head_and_parent_gitlink(self) -> None:
        """Active-source verification accepts the selected provider and rejects drift."""
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
            self.assertEqual(
                installer.verify(active, workspace=root), standalone_commit
            )
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
            ("detached-gitlink-match", "match", None),
            ("detached-gitlink-mismatch", "mismatch", "provider identity mismatch"),
            ("missing-git-metadata", "missing", "source-root Git metadata"),
        )
        for case_name, case_kind, failure_text in derived_cases:
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

                if failure_text is None:
                    self.assertEqual(
                        installer.verify(active, workspace=parent), source_commit
                    )
                    with self.assertRaisesRegex(
                        DependencyError, "binary source identity mismatch"
                    ):
                        installer.verify(
                            active,
                            workspace=parent,
                            expected_source_identity="0" * 40,
                        )
                else:
                    with self.assertRaisesRegex(DependencyError, failure_text):
                        installer.verify(active, workspace=parent)

    def test_active_source_receipt_rejects_build_time_source_change(self) -> None:
        """A source mutation during Cargo build removes the receipt and fails closed."""
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
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            with mock.patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(
                    DependencyError, "source identity changed during build"
                ):
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
            f"{root}/.cargo/bin:{root}/.elan/bin:/tmp/fake-python-user-base/bin:/usr/bin",
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

    def test_static_bootstrap_and_post_create_contract_has_no_legacy_install_routes(
        self,
    ) -> None:
        bootstrap = (ROOT / ".devcontainer" / "bootstrap-dependencies.sh").read_text(
            encoding="utf-8"
        )
        post_create = (ROOT / ".devcontainer" / "post-create.sh").read_text(
            encoding="utf-8"
        )
        identity_helper = (
            ROOT / "tools" / "lib" / "agent_canon_source_identity.sh"
        ).read_text(encoding="utf-8")
        validator = (ROOT / "tools" / "docker_dependency_validator.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('NODE_VERSION="22.14.0"', bootstrap)
        self.assertIn("NODE_X86_64_SHA256", bootstrap)
        self.assertIn("NODE_AARCH64_SHA256", bootstrap)
        self.assertIn("ninja-build", bootstrap)
        self.assertIn("python3-pip", bootstrap)
        self.assertIn("python3-packaging", bootstrap)
        self.assertIn("gnupg", bootstrap)
        self.assertIn("command -v gpg", bootstrap)
        self.assertIn("packaging.requirements", bootstrap)
        self.assertIn("NODE_BOOTSTRAP_RECEIPT", bootstrap)
        self.assertIn('NODE_NPM_VERSION="10.9.2"', bootstrap)
        self.assertIn(
            '"$NODE_INSTALL_PATH/lib/node_modules/npm/bin/npm-cli.js"', bootstrap
        )
        self.assertNotIn('"$NODE_INSTALL_PATH/bin/npm"', bootstrap)
        self.assertIn("tomllib", bootstrap)
        self.assertIn("tomli", bootstrap)
        self.assertIn('"$devcontainer_dir/bootstrap-dependencies.sh" --install-language-runtime', post_create)
        self.assertNotIn("NODE_VERSION:-", bootstrap)
        self.assertNotIn("npm install -g", post_create)
        self.assertNotIn("install_github_cli", post_create)
        self.assertNotIn("install_rust_toolchain", post_create)
        self.assertNotIn("grep", validator)
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH", post_create)
        self.assertIn('export CARGO_HOME="$cargo_home"', post_create)
        self.assertIn('export RUSTUP_HOME="$rustup_home"', post_create)
        self.assertIn("agent_canon_source_identity", post_create)
        self.assertIn('"HEAD:$source_prefix"', identity_helper)
        self.assertIn("agent_canon_receipt_matches_identity", post_create)
        self.assertIn("agent_canon_source_commit", post_create)
        self.assertIn('export ELAN_HOME="$elan_home"', post_create)
        self.assertIn("STRUCTURED_ANALYSIS_BOOTSTRAP=warn", post_create)
        cache_function = post_create.split("build_agent_canon_cache() {", 1)[1].split(
            "\n}\n", 1
        )[0]
        self.assertIn("if agent-canon structured-analysis build", cache_function)
        self.assertNotIn("return 1", cache_function)
        self.assertNotIn('"$devcontainer_dir/finalize-shared-runtime.sh"', post_create)
        self.assertIn("ensure_container_local_runtime()", post_create)
        self.assertIn("validate_runtime_identity", bootstrap)
        self.assertLess(
            bootstrap.index("validate_runtime_identity"),
            bootstrap.index("apt-get update"),
        )
        self.assertIn("ensure_container_local_runtime\n", post_create)
        bootstrap_index = post_create.rindex(
            '"$devcontainer_dir/bootstrap-dependencies.sh" --check'
        )
        pip_user_path_index = post_create.index('pip_user_script_dir="$(')
        validate_index = post_create.index("validate --workspace")
        install_index = post_create.index("install --workspace")
        python_installer_index = post_create.rindex(
            "docker/install_python_dependencies.sh"
        )
        cache_index = post_create.rindex("\nbuild_agent_canon_cache\n")
        projection_index = post_create.rindex("\npublish_container_local_runtime\n")
        self.assertLess(bootstrap_index, pip_user_path_index)
        self.assertLess(pip_user_path_index, validate_index)
        self.assertLess(
            validate_index,
            install_index,
        )
        self.assertLess(
            install_index,
            python_installer_index,
        )
        self.assertLess(python_installer_index, cache_index)
        self.assertLess(cache_index, projection_index)
        self.assertLess(
            python_installer_index,
            post_create.rindex("\npublish_agent_canon_cli\n"),
        )


if __name__ == "__main__":
    unittest.main()
