"""Focused tests for the declarative devcontainer dependency model."""

# @dependency-start
# contract test
# responsibility Verifies schema, merge, order, security, and receipt semantics for devcontainer dependencies.
# upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md dependency model contract
# upstream implementation ../../tools/agent_tools/devcontainer_dependencies.py typed dependency engine
# downstream implementation ../../.devcontainer/dependencies.toml canonical manifest inventory
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

from tools.agent_tools.devcontainer_dependencies import (
    DependencyError,
    Installer,
    LoadedManifest,
    build_plan,
    manifest_paths,
    parse_record,
    safe_extract_tar,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "tools" / "agent_tools" / "devcontainer_dependencies.py"


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
        "commands": [["true"]],
        "deps": deps or [],
        "provides": provides or [record_id],
        "failure_policy": "fail",
    }
    value.update(extra)
    return value


def write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    """Write a small TOML fixture without depending on a TOML writer."""
    lines = ['schema = "agent-canon.devcontainer-dependencies"', "schema_version = 1", ""]
    for item in records:
        lines.append("[[records]]")
        for key, value in item.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, list):
                rendered = "[" + ", ".join(
                    "[" + ", ".join(json.dumps(part) for part in command) + "]"
                    if command and isinstance(command, list)
                    else json.dumps(command)
                    for command in value
                ) + "]" if key == "commands" else "[" + ", ".join(json.dumps(part) for part in value) + "]"
            else:
                rendered = json.dumps(value)
            lines.append(f"{key} = {rendered}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


class FakeRunner:
    """Capture argv calls without performing installs or network work."""

    def __init__(
        self,
        fail_on: str | None = None,
        fail_once_on: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str] | None] = []
        self.fail_on = fail_on
        self.fail_once_on = fail_once_on

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, privileged, capture_output
        command = tuple(argv)
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
        return subprocess.CompletedProcess(command, 0, "", "")


class DependencyModelTests(unittest.TestCase):
    """Exercise schema, merge, order, security, and receipt behavior."""

    def test_repository_manifest_validates_and_dry_run_has_stable_order(self) -> None:
        plan = build_plan(
            (
                LoadedManifest(
                    Path("parent.toml"),
                    (
                        parse_record(record("parent"), path=Path("parent.toml"), index=0),
                    ),
                ),
                LoadedManifest(
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
        self.assertEqual(Installer().dry_run(plan)["order"], ["parent", "child"])

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
            "commands": [["true"]],
            "deps": [],
            "provides": ["tool"],
            "failure_policy": "fail",
        }
        values = [
            record("apt", method="apt-package"),
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
        plan = build_plan((LoadedManifest(Path("fixture.toml"), (parsed,)),))
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
                Installer(runner).install(
                    plan, workspace=root, receipts=root / "receipts"
                )

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
                commands=[["true"], ["printf", "ok"]],
            ),
            path=Path("vendor.toml"),
            index=0,
        )
        merged = build_plan(
            (
                LoadedManifest(Path("parent.toml"), (parent,)),
                LoadedManifest(Path("vendor.toml"), (vendor,)),
            )
        ).records[0]
        self.assertEqual(merged.version, "1.0.0")
        self.assertEqual(merged.deps, ("node", "ninja-build"))
        self.assertEqual(merged.provides, ("codex", "shared-cli"))
        self.assertEqual(merged.commands[0], ("true",))

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
                    LoadedManifest(Path("parent.toml"), (parent,)),
                    LoadedManifest(Path("vendor.toml"), (incompatible,)),
                )
            )
        with self.assertRaisesRegex(DependencyError, "provider ambiguity"):
            build_plan(
                (
                    LoadedManifest(
                        Path("a.toml"),
                        (parse_record(record("a", provides=["same"]), path=Path("a.toml"), index=0),),
                    ),
                    LoadedManifest(
                        Path("b.toml"),
                        (parse_record(record("b", provides=["same"]), path=Path("b.toml"), index=0),),
                    ),
                )
            )
        with self.assertRaisesRegex(DependencyError, "missing dependency"):
            build_plan(
                (
                    LoadedManifest(
                        Path("missing.toml"),
                        (parse_record(record("missing", deps=["absent"]), path=Path("missing.toml"), index=0),),
                    ),
                )
            )
        cycle_a = parse_record(record("a", deps=["b"]), path=Path("cycle.toml"), index=0)
        cycle_b = parse_record(record("b", deps=["a"]), path=Path("cycle.toml"), index=1)
        with self.assertRaisesRegex(DependencyError, "cycle"):
            build_plan((LoadedManifest(Path("cycle.toml"), (cycle_a, cycle_b)),))

    def test_manifest_paths_parent_first_and_standalone_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / ".devcontainer" / "dependencies.toml"
            vendor = root / "vendor" / "agent-canon" / ".devcontainer" / "dependencies.toml"
            write_manifest(parent, [record("parent")])
            write_manifest(vendor, [record("vendor")])
            self.assertEqual(manifest_paths(root), (parent, vendor))
            agent_root = vendor.parents[1]
            self.assertEqual(manifest_paths(agent_root, agent_root), (vendor,))

    def test_commands_reject_shell_evaluation(self) -> None:
        unsafe = record("unsafe", commands=[["sh", "-c", "echo unsafe"]])
        with self.assertRaisesRegex(DependencyError, "shell interpreter"):
            parse_record(unsafe, path=Path("fixture.toml"), index=0)
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
                commands=[["tool", "--version"]],
            ),
            path=Path("x.toml"),
            index=0,
        )
        plan = build_plan((LoadedManifest(Path("x.toml"), (parsed,)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FakeRunner()
            installer = Installer(runner)
            receipts = root / "receipts"
            self.assertEqual(installer.install(plan, workspace=root, receipts=receipts), ("tool",))

            resumed = FakeRunner()
            self.assertEqual(
                Installer(resumed).install(plan, workspace=root, receipts=receipts),
                ("tool",),
            )
            self.assertIn(("tool", "--version"), resumed.calls)
            self.assertFalse(any(command[0] == "apt-get" for command in resumed.calls))

            rebuilt = FakeRunner(fail_once_on="tool")
            self.assertEqual(
                Installer(rebuilt).install(plan, workspace=root, receipts=receipts),
                ("tool",),
            )
            self.assertEqual(
                sum(command[0] == "apt-get" for command in rebuilt.calls),
                1,
            )
            self.assertEqual(
                rebuilt.calls.count(("tool", "--version")),
                2,
            )

            failing = FakeRunner(fail_on="apt-get")
            with self.assertRaises(DependencyError):
                Installer(failing).install(
                    plan,
                    workspace=root,
                    receipts=root / "failed-receipts",
                )
            self.assertFalse((root / "failed-receipts" / "tool.json").exists())

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
        plan = build_plan((LoadedManifest(Path("x.toml"), (provider, dependent)),))
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
        plan = build_plan((LoadedManifest(Path("x.toml"), (browser,)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FakeRunner()
            Installer(runner).install(plan, workspace=root, receipts=root / "receipts")
            self.assertIn(
                {"PLAYWRIGHT_BROWSERS_PATH": "/usr/local/share/ms-playwright"},
                runner.environments,
            )

    def test_toolchain_installers_bootstrap_and_publish_home_paths(self) -> None:
        rust = parse_record(
            record(
                "rust",
                method="rust-toolchain",
                version="1.89.0",
                commands=[["rustc", "--version"], ["cargo", "--version"]],
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
                commands=[["lean", "--version"], ["lake", "--version"]],
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
                commands=[["cargo", "--version"]],
                deps=["cargo"],
            ),
            path=Path("fixture.toml"),
            index=2,
        )
        plan = build_plan((LoadedManifest(Path("fixture.toml"), (rust, lean, cargo)),))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "rust" / "agent-canon").mkdir(parents=True)
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

    def test_static_bootstrap_and_post_create_contract_has_no_legacy_install_routes(self) -> None:
        bootstrap = (ROOT / ".devcontainer" / "bootstrap-dependencies.sh").read_text(
            encoding="utf-8"
        )
        post_create = (ROOT / ".devcontainer" / "post-create.sh").read_text(
            encoding="utf-8"
        )
        validator = (ROOT / "tools" / "docker_dependency_validator.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('NODE_VERSION="22.14.0"', bootstrap)
        self.assertIn("NODE_X86_64_SHA256", bootstrap)
        self.assertIn("NODE_AARCH64_SHA256", bootstrap)
        self.assertIn("ninja-build", bootstrap)
        self.assertIn("python3-pip", bootstrap)
        self.assertIn("NODE_BOOTSTRAP_RECEIPT", bootstrap)
        self.assertIn('NODE_NPM_VERSION="10.9.2"', bootstrap)
        self.assertIn("tomllib", bootstrap)
        self.assertIn("tomli", bootstrap)
        self.assertNotIn("NODE_VERSION:-", bootstrap)
        self.assertNotIn("npm install -g", post_create)
        self.assertNotIn("install_github_cli", post_create)
        self.assertNotIn("install_rust_toolchain", post_create)
        self.assertNotIn("grep", validator)
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH", post_create)
        self.assertIn('export CARGO_HOME="$cargo_home"', post_create)
        self.assertIn('export RUSTUP_HOME="$rustup_home"', post_create)
        self.assertIn('export ELAN_HOME="$elan_home"', post_create)
        self.assertIn("STRUCTURED_ANALYSIS_BOOTSTRAP=warn", post_create)
        cache_function = post_create.split("build_agent_canon_cache() {", 1)[1].split(
            "\n}\n", 1
        )[0]
        self.assertIn(
            "if agent-canon structured-analysis build", cache_function
        )
        self.assertNotIn("return 1", cache_function)
        self.assertEqual(
            post_create.count('"$devcontainer_dir/finalize-shared-runtime.sh"'), 1
        )
        bootstrap_index = post_create.rindex(
            '"$devcontainer_dir/bootstrap-dependencies.sh" --check'
        )
        pip_user_path_index = post_create.index('pip_user_script_dir="$(')
        validate_index = post_create.index("validate --workspace")
        install_index = post_create.index("install --workspace")
        python_installer_index = post_create.rindex(
            "docker/install_python_dependencies.sh"
        )
        finalize_index = post_create.rindex(
            '"$devcontainer_dir/finalize-shared-runtime.sh"'
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
        self.assertLess(python_installer_index, finalize_index)
        self.assertLess(finalize_index, cache_index)
        self.assertLess(cache_index, projection_index)
        self.assertLess(
            python_installer_index,
            post_create.rindex("\npublish_agent_canon_cli\n"),
        )


if __name__ == "__main__":
    unittest.main()
