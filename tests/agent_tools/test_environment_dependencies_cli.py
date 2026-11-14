"""Public native CLI oracles for the shared environment dependency owner."""

# @dependency-start
# contract test
# responsibility Checks the native environment dependency command contract with independent manifests and provider fixtures.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/environment_dependencies.rs owns plan and installer behavior
# downstream environment ../../bootstrap/container/image/dependencies.toml declares the shared image providers
# @dependency-end

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "bin" / "agent-canon"


def dependency_manifest() -> str:
    """Return a fixed two-record graph with a provider that sorts after its consumer."""
    return """schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "consumer"
package = "consumer"
method = "npm-global"
version = "1.0.0"
source = "https://registry.npmjs.org/consumer"
deps = ["base-capability"]
provides = ["consumer"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "consumer"
args = ["--version"]
output_contains = "1.0.0"

[[records]]
id = "provider"
package = "provider"
method = "npm-global"
version = "2.0.0"
source = "https://registry.npmjs.org/provider"
deps = []
provides = ["base-capability"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "provider"
args = ["--version"]
output_contains = "2.0.0"
"""


class EnvironmentDependenciesCliTests(unittest.TestCase):
    """Exercise the public Rust command and its external provider boundary."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="agent-canon-dependency-cli-"
        )
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "dependencies.toml"
        self.manifest.write_text(dependency_manifest(), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        selected_cli = os.environ.get("AGENT_CANON_CLI")
        if selected_cli:
            environment["AGENT_CANON_NATIVE_BIN"] = selected_cli
        if extra:
            environment.update(extra)
        return environment

    def run_cli(
        self, *args: str, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(CLI),
                "environment-dependencies",
                *args,
                "--workspace",
                str(self.root),
                "--manifest",
                str(self.manifest),
            ],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            env=self.environment(environment),
        )

    def test_validate_and_dry_run_keep_provider_order_and_typed_actions(self) -> None:
        validated = self.run_cli("validate", "--format", "json")
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
        validation_payload = json.loads(validated.stdout)
        self.assertEqual(validation_payload["status"], "pass")
        self.assertEqual(validation_payload["order"], ["provider", "consumer"])
        self.assertEqual(validation_payload["sources"], [str(self.manifest.resolve())])
        self.assertRegex(validation_payload["plan_fingerprint"], r"^[0-9a-f]{64}$")

        dry_run = self.run_cli("dry-run", "--format", "json")
        self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
        dry_run_payload = json.loads(dry_run.stdout)
        self.assertEqual(dry_run_payload["order"], ["provider", "consumer"])
        self.assertEqual(
            [(action["id"], action["method"]) for action in dry_run_payload["actions"]],
            [("provider", "npm-global"), ("consumer", "npm-global")],
        )
        self.assertEqual(
            dry_run_payload["actions"][0]["verification"]["output_contains"],
            "2.0.0",
        )

    def test_boundary_checks_the_native_runtime_contract(self) -> None:
        paths = {
            "bootstrap.sh": True,
            "bootstrap/container/image/dependencies.toml": False,
            "bootstrap/container/image/Dockerfile": False,
            "bootstrap/container/lifecycle/entrypoint.sh": True,
            "tools/runtime/dispatch/agent-canon/src/environment_dependencies.rs": False,
            "tools/runtime/dispatch/agent-canon/src/bootstrap_runtime.rs": False,
            "tools/runtime/dispatch/agent-canon/src/runtime_boundary.rs": False,
            "CONTAINER_OPERATIONS.md": False,
        }
        for relative, executable in paths.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
            if executable:
                path.chmod(0o755)

        boundary = self.run_cli("boundary", "--format", "json")
        self.assertEqual(boundary.returncode, 0, boundary.stdout + boundary.stderr)
        payload = json.loads(boundary.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["checked"], list(paths))
        self.assertEqual(payload["findings"], [])

        (self.root / "CONTAINER_OPERATIONS.md").unlink()
        missing = self.run_cli("boundary", "--format", "json")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(
            json.loads(missing.stdout)["findings"],
            [
                {
                    "category": "bootstrap-runtime",
                    "path": "CONTAINER_OPERATIONS.md",
                    "detail": "missing-file",
                }
            ],
        )

    def test_project_install_validates_extras_then_invokes_python_provider(
        self,
    ) -> None:
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture-project'\n"
            "[project.optional-dependencies]\ndev_tools = []\n",
            encoding="utf-8",
        )
        bin_directory = self.root / "provider-bin"
        bin_directory.mkdir()
        provider_log = self.root / "provider.log"
        provider = bin_directory / "python3"
        provider.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' '--call--' >> \"$AGENT_CANON_TEST_PROVIDER_LOG\"\n"
            'printf \'%s\\n\' "$@" >> "$AGENT_CANON_TEST_PROVIDER_LOG"\n',
            encoding="utf-8",
        )
        provider.chmod(0o755)
        path = os.pathsep.join([str(bin_directory), os.environ.get("PATH", "")])
        installed = self.run_cli(
            "project-install",
            "--extras",
            "dev-tools",
            "--format",
            "json",
            environment={
                "PATH": path,
                "AGENT_CANON_TEST_PROVIDER_LOG": str(provider_log),
            },
        )
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        self.assertEqual(
            json.loads(installed.stdout),
            {"extras": ["dev-tools"], "status": "pass"},
        )
        calls = provider_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            calls,
            [
                "--call--",
                "-m",
                "pip",
                "install",
                "--editable",
                f"{self.root}[dev-tools]",
                "--call--",
                "-m",
                "pip",
                "check",
            ],
        )

    def test_parser_and_missing_extra_fail_without_invoking_a_provider(self) -> None:
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture-project'\n"
            "[project.optional-dependencies]\ndev = []\n",
            encoding="utf-8",
        )
        provider_log = self.root / "provider.log"
        missing = self.run_cli(
            "project-install",
            "--extras",
            "absent",
            "--format",
            "json",
            environment={"AGENT_CANON_TEST_PROVIDER_LOG": str(provider_log)},
        )
        self.assertEqual(missing.returncode, 1)
        self.assertIn("project extras are not declared", missing.stderr)
        self.assertFalse(provider_log.exists())

        invalid_format = self.run_cli("validate", "--format=xml")
        self.assertEqual(invalid_format.returncode, 2)
        self.assertIn("invalid choice", invalid_format.stderr)

    def test_install_command_keeps_warning_and_provider_closure_semantics(self) -> None:
        manifest = """schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "consumer"
package = "consumer"
method = "npm-global"
version = "1.0.0"
source = "https://registry.npmjs.org/consumer"
deps = ["base-capability"]
provides = ["consumer"]
failure_policy = "warn"
[records.verification]
kind = "npm-package"
executable = "consumer"
args = ["--version"]
output_contains = "1.0.0"

[[records]]
id = "release-provider"
package = "release-provider"
method = "release-asset"
version = "1.0.0"
source = "https://example.invalid/release-provider"
checksum = "0000000000000000000000000000000000000000000000000000000000000000"
asset = "release-provider"
archive_format = "binary"
extract = "none"
destination = "/usr/local/bin/release-provider"
deps = []
provides = ["base-capability"]
failure_policy = "warn"
[records.verification]
kind = "absolute-executable"
path = "/usr/local/bin/release-provider"
args = ["--version"]
output_contains = "1.0.0"
"""
        self.manifest.write_text(manifest, encoding="utf-8")
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.invalid/fixture.git"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=AgentCanon test",
                "-c",
                "user.email=agent-canon-test@example.invalid",
                "add",
                "dependencies.toml",
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=AgentCanon test",
                "-c",
                "user.email=agent-canon-test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture manifest",
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        provider_bin = self.root / "provider-bin"
        provider_bin.mkdir()
        curl = provider_bin / "curl"
        curl.write_text(
            "#!/bin/sh\n"
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = --output ]; then shift; : > "$1"; fi\n'
            "  shift\n"
            "done\n"
            "exit 0\n",
            encoding="utf-8",
        )
        curl.chmod(0o755)
        runtime = tempfile.TemporaryDirectory(prefix="agent-canon-dependency-runtime-")
        self.addCleanup(runtime.cleanup)
        runtime_root = Path(runtime.name)
        environment = self.environment(
            {
                "AGENT_CANON_CONTROL_PARENT_ROOT": str(self.root.parent),
                "AGENT_CANON_RUNTIME_ROOT": str(runtime_root),
                "PATH": os.pathsep.join(
                    [str(provider_bin), os.environ.get("PATH", "")]
                ),
            }
        )
        installed = self.run_cli("install", "--format", "json", environment=environment)
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        payload = json.loads(installed.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["completed"], [])
        self.assertRegex(payload["plan_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertIn("DEPENDENCY_RECORD_WARN=release-provider", installed.stderr)
        self.assertIn("release checksum mismatch", installed.stderr)
        self.assertIn("depends on release-provider", installed.stderr)


if __name__ == "__main__":
    unittest.main()
