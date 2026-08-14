# @dependency-start
# contract test
# responsibility Tests default bootstrap docs and source-hidden static-seed consumer validation.
# upstream implementation ../../tools/docs/check_bootstrap_docs.py bootstrap and static-consumer checker under test
# upstream design ../../documents/contracts/template-bootstrap.md default static-seed bootstrap contract
# upstream design ../../documents/contracts/static-seed-export.md static seed boundary
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml explicit live-integration manifest metadata
# @dependency-end
"""Tests for bootstrap-facing docs and source-free static-seed validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "check_bootstrap_docs.py"


class CheckBootstrapDocsTest(unittest.TestCase):
    """Exercise bootstrap and static-consumer validation through the CLI."""

    def run_cli(
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the validator for one temporary root."""
        command = [sys.executable, str(SCRIPT_PATH), "--root", str(root), *args]
        return subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create one file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def write_minimal_bootstrap_docs(self, root: Path) -> None:
        """Create compliant bootstrap-facing files the validator scans."""
        for relative_path in (
            "README.md",
            "QUICK_START.md",
            "docker/README.md",
            "scripts/README.md",
            "documents/contracts/linux-wsl-host-requirements.md",
        ):
            self.write_file(root / relative_path, "# Doc\n")
        self.write_file(
            root / "documents/contracts/template-bootstrap.md",
            "# Bootstrap\n\n"
            "The default path owns a static seed as a regular file set.\n"
            "The provenance file is agent-canon-static-seed.json.\n"
            "Maintenance is a one-way export.\n",
        )
        self.write_file(
            root / "agents/skills/start-repository.md",
            "# start-repository\n\nInitialize the static consumer tree.\n",
        )
        self.write_file(
            root / "templates/README.md",
            "# Templates\n\nExport regular consumer files in one direction.\n",
        )

    def write_static_seed_consumer(self, root: Path) -> None:
        """Create one structurally complete consumer with no source checkout."""
        self.write_file(
            root / ".codex" / "config.toml",
            'approval_policy = "on-request"\n'
            'sandbox_mode = "workspace-write"\n'
            "\n"
            "[agents]\n"
            "max_threads = 1\n"
            "\n"
            "[agents.worker]\n"
            'description = "Implements a bounded change."\n'
            'config_file = "agents/worker.toml"\n',
        )
        self.write_file(
            root / ".codex" / "agents" / "worker.toml",
            'name = "worker"\n'
            'sandbox_mode = "workspace-write"\n'
            'developer_instructions = "Implement the bounded change."\n',
        )
        self.write_file(
            root / "agent-canon-static-seed.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "source_commit": "a" * 40,
                    "source_repository": "iwashita-nozomu/agent-canon",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    def test_fails_on_workspace_absolute_links(self) -> None:
        """Workspace-absolute markdown links should be rejected everywhere."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "project-template"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "README.md",
                "[doc](/mnt/l/workspace/project_template/README.md)\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("replace workspace-absolute markdown links", result.stdout)

    def test_fails_on_stale_template_strings_in_derived_repo(self) -> None:
        """Derived repos should not keep template bootstrap identifiers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "derived-project"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "QUICK_START.md",
                "docker build -t project-template -f docker/Dockerfile .\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("stale template bootstrap text remains: project-template", result.stdout)

    def test_rejects_symlinked_default_consumer_contract(self) -> None:
        """Default bootstrap docs must not resolve through a live source tree."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "derived-project"\n')
            self.write_minimal_bootstrap_docs(root)
            source_doc = root / "external-source" / "template-bootstrap.md"
            self.write_file(
                source_doc,
                "# Bootstrap\nstatic seed regular file agent-canon-static-seed.json one-way\n",
            )
            contract = root / "documents" / "contracts" / "template-bootstrap.md"
            contract.unlink()
            contract.symlink_to(source_doc)

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("default consumer contract must be a regular file", result.stdout)

    def test_rejects_live_runtime_markers_in_default_docs(self) -> None:
        """Default docs and skills must not reintroduce runtime/update requirements."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "project-template"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "agents" / "skills" / "start-repository.md",
                "# start-repository\nRun make agent-canon-ensure-latest.\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("default consumer contract references live runtime marker", result.stdout)

    def test_passes_when_template_strings_are_replaced(self) -> None:
        """Derived repos should pass once bootstrap-facing docs are rendered."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "derived-project"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "README.md",
                "# Derived Project\n\n[quick-start](QUICK_START.md)\n",
            )
            self.write_file(
                root / "QUICK_START.md",
                "docker build -t derived-project -f docker/Dockerfile .\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("Bootstrap docs check passed", result.stdout)

    def test_static_seed_consumer_passes_with_source_hidden(self) -> None:
        """Consumer validation must pass without importing or resolving AgentCanon source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_static_seed_consumer(root)
            guard = root / "import-guard"
            self.write_file(
                guard / "sitecustomize.py",
                "import builtins\n"
                "_original_import = builtins.__import__\n"
                "def _guarded_import(name, *args, **kwargs):\n"
                "    if name.startswith('agent_tools') or 'agent_canon_source_root' in name:\n"
                "        raise RuntimeError(f'forbidden source import: {name}')\n"
                "    return _original_import(name, *args, **kwargs)\n"
                "builtins.__import__ = _guarded_import\n",
            )
            env = dict(os.environ)
            env["PYTHONPATH"] = str(guard)

            result = self.run_cli(root, "--static-seed-consumer", env=env)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Static seed consumer check passed", result.stdout)
            self.assertFalse((root / "vendor").exists())
            self.assertFalse((root / ".gitmodules").exists())

    def test_static_seed_consumer_rejects_runtime_surface_and_role_symlink(self) -> None:
        """Live runtime paths and linked role files are outside the static boundary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_static_seed_consumer(root)
            self.write_file(root / "vendor" / "agent-canon" / "README.md", "# Source\n")

            result = self.run_cli(root, "--static-seed-consumer")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("live AgentCanon consumer surface is forbidden", result.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_static_seed_consumer(root)
            role = root / ".codex" / "agents" / "worker.toml"
            role.unlink()
            role.symlink_to(root / ".codex" / "config.toml")

            result = self.run_cli(root, "--static-seed-consumer")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("static seed must not contain symlinks", result.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_static_seed_consumer(root)
            self.write_file(
                root / "documents" / "runtime" / "shared-runtime-surfaces.toml",
                'version = 1\nprefix = "vendor/agent-canon"\n',
            )

            result = self.run_cli(root, "--static-seed-consumer")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn(
                "documents/runtime/shared-runtime-surfaces.toml: live AgentCanon consumer surface is forbidden",
                result.stdout,
            )

    def test_live_runtime_manifest_is_explicit_opt_in(self) -> None:
        """The legacy projection manifest must identify itself as non-default."""
        manifest = tomllib.loads(
            (PROJECT_ROOT / "documents" / "runtime" / "shared-runtime-surfaces.toml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["integration_mode"], "live-agent-canon")
        self.assertFalse(manifest["default_consumer"])
        self.assertEqual(manifest["selection"], "explicit-opt-in")


if __name__ == "__main__":
    unittest.main()
