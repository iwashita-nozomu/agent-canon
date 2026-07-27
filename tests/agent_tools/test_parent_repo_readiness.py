"""Tests for parent repository readiness checker."""

# @dependency-start
# contract test
# responsibility Tests AgentCanon parent repository readiness checks.
# upstream implementation ../../tools/agent_tools/parent_repo_readiness.py checks parent repo surfaces
# upstream implementation ../../tools/agent_tools/surface_manifest.py parses shared surface manifest
# upstream design ../../documents/shared-runtime-surfaces.toml shared runtime surface manifest
# upstream design ../../documents/gpu-admission-r5-source-packet.md runtime identity receipt and shared-surface test contract
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "parent_repo_readiness.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import (  # noqa: E402
    load_manifest,
    render_regular_specs,
    target_for_entry,
)


class ParentRepoReadinessTest(unittest.TestCase):
    """Exercise parent repository readiness checks."""

    def run_checker(
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the checker against a fixture parent root."""
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--root",
                str(root),
                "--skip-container-config",
                "--skip-submodule-check",
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_materialized_parent_fixture_passes(self) -> None:
        """A correctly materialized parent fixture should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)
            self.assertFalse((root / ".codex" / "project-skills").exists())

    def test_runtime_identity_receipt(self) -> None:
        """Readiness fails when a script-owned runtime identity receipt edge is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            linked_devcontainer = root / ".devcontainer"
            if linked_devcontainer.is_dir():
                shutil.rmtree(linked_devcontainer)
            shutil.copytree(PROJECT_ROOT / ".devcontainer", linked_devcontainer)
            (linked_devcontainer / "finalize-shared-runtime.sh").unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:runtime_identity_receipt:"
                ".devcontainer/finalize-shared-runtime.sh:missing-file",
                result.stdout,
            )

    def test_shared_surface_receipt(self) -> None:
        """The shared devcontainer surface carries both exact identity receipt owners."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/shared-runtime-surfaces.toml",
        )
        devcontainer = next(
            entry for entry in manifest.entries if entry.path == ".devcontainer"
        )
        devcontainer_json = next(
            entry
            for entry in manifest.entries
            if entry.path == ".devcontainer/devcontainer.json"
        )

        self.assertEqual(devcontainer.mode, "regular")
        self.assertEqual(devcontainer.surface_class, "active_contract")
        self.assertTrue((PROJECT_ROOT / devcontainer.path).is_dir())
        self.assertTrue(
            (PROJECT_ROOT / devcontainer_json.source_or_default()).is_file()
        )
        self.assertEqual(devcontainer_json.mode, "symlink")

    def test_parent_post_create_wrapper_order(self) -> None:
        """Parent wrapper post-create calls shared standard first, then optional parent hook."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            post_create = (root / ".devcontainer" / "post-create.sh").read_text(
                encoding="utf-8"
            )
            standard_call = 'bash "${repo_root}/vendor/agent-canon/.devcontainer/post-create.sh" "$workspace"'
            parent_call = 'bash "$parent_hook" "$workspace"'

            standard_index = post_create.find(standard_call)
            parent_index = post_create.find(parent_call)

            self.assertGreaterEqual(standard_index, 0)
            self.assertGreaterEqual(parent_index, 0)
            self.assertLess(standard_index, parent_index)
            self.assertIn("set -euo pipefail", post_create)
            self.assertIn(
                'parent_hook="${script_dir}/post-create-parent.sh"', post_create
            )

    def test_parent_wrappers_resolve_from_script_location(self) -> None:
        """親wrapperがprocess cwdではなく自身の配置場所からsourceを解決する。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            wrapper_dir = root / ".devcontainer"
            wrapper_names = (
                "bootstrap-shared-runtime.sh",
                "finalize-shared-runtime.sh",
                "post-attach.sh",
                "generate-runtime-compose.sh",
            )

            for name in wrapper_names:
                content = (wrapper_dir / name).read_text(encoding="utf-8")
                self.assertIn('dirname -- "${BASH_SOURCE[0]}"', content)
                self.assertIn(
                    'repo_root="$(cd -- "${script_dir}/.." && pwd -P)"', content
                )
                self.assertNotIn("../vendor/agent-canon", content)
                self.assertIn(
                    f"${{repo_root}}/vendor/agent-canon/.devcontainer/{name}",
                    content,
                )

            compose = (wrapper_dir / "generate-runtime-compose.sh").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                'AGENT_CANON_DOCKER_COMPOSE_OUTPUT="${repo_root}/.devcontainer/docker-compose.generated.yml"',
                compose,
            )

    def test_parent_post_create_is_cwd_independent_and_fail_closed(self) -> None:
        """post-createがcwd非依存で順序と失敗伝播を守る。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            agent_canon = root / "vendor" / "agent-canon"
            agent_canon.unlink()
            source_devcontainer = agent_canon / ".devcontainer"
            source_devcontainer.mkdir(parents=True)
            log_path = root / "wrapper-order.log"
            self.write_file(
                root,
                "vendor/agent-canon/.devcontainer/post-create.sh",
                '#!/usr/bin/env bash\nprintf "standard:%s\\n" "$1" >> "$TEST_LOG"\nif [ "${FAIL_STANDARD:-0}" = "1" ]; then exit 17; fi\n',
            )
            self.write_file(
                root,
                ".devcontainer/post-create-parent.sh",
                '#!/usr/bin/env bash\nprintf "parent:%s\\n" "$1" >> "$TEST_LOG"\n',
            )
            outside_cwd = root / "outside-cwd"
            outside_cwd.mkdir()
            wrapper = root / ".devcontainer/post-create.sh"
            env = {**os.environ, "TEST_LOG": str(log_path)}

            success = subprocess.run(
                ["bash", str(wrapper), "/workspace/example"],
                cwd=outside_cwd,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
            self.assertEqual(
                log_path.read_text(encoding="utf-8").splitlines(),
                ["standard:/workspace/example", "parent:/workspace/example"],
            )

            log_path.unlink()
            failure = subprocess.run(
                ["bash", str(wrapper), "/workspace/example"],
                cwd=outside_cwd,
                env={**env, "FAIL_STANDARD": "1"},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(failure.returncode, 17, failure.stdout + failure.stderr)
            self.assertEqual(
                log_path.read_text(encoding="utf-8").splitlines(),
                ["standard:/workspace/example"],
            )

    def test_materialized_devcontainer_uses_child_symlink(self) -> None:
        """manifest materializationは実体directoryと個別symlinkを作る。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            devcontainer = root / ".devcontainer"
            devcontainer_json = devcontainer / "devcontainer.json"

            self.assertTrue(devcontainer.is_dir())
            self.assertFalse(devcontainer.is_symlink())
            self.assertTrue(devcontainer_json.is_symlink())
            self.assertEqual(
                os.readlink(devcontainer_json),
                "../vendor/agent-canon/.devcontainer/devcontainer.json",
            )

    def test_legacy_devcontainer_directory_symlink_is_rejected(self) -> None:
        """whole-directory .devcontainer symlinkはreadinessで拒否する。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            devcontainer = root / ".devcontainer"
            shutil.rmtree(devcontainer)
            devcontainer.symlink_to(
                "vendor/agent-canon/.devcontainer", target_is_directory=True
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:active_contract:"
                ".devcontainer:must-be-parent-owned-directory",
                result.stdout,
            )

    def test_regular_specs_skip_optional_project_skill_lane(self) -> None:
        """Optional project content should not be materialized by link-root."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/shared-runtime-surfaces.toml",
        )

        regular_specs = render_regular_specs(manifest.entries, manifest.prefix)

        self.assertNotIn(".codex/project-skills", regular_specs)
        self.assertNotIn(".codex/project-config.toml", regular_specs)

    def test_tree_present_adds_checked_token_and_command(self) -> None:
        """Tree availability should be reported without relying on the host tool."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            root.mkdir()
            self.write_parent_fixture(root)
            bin_dir = Path(tmp_dir) / "bin"
            bin_dir.mkdir()
            fake_tree = bin_dir / "tree"
            fake_tree.write_text(
                "#!/usr/bin/env sh\necho fake-tree\n", encoding="utf-8"
            )
            fake_tree.chmod(0o755)

            result = self.run_checker(
                root,
                "--tree-depth",
                "2",
                env={"PATH": str(bin_dir)},
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("tree_display:available:depth=2", result.stdout)
            self.assertIn(
                "PARENT_REPO_READINESS_TREE_COMMAND=tree -a -L 2 -I", result.stdout
            )
            self.assertIn(str(root), result.stdout)

    def test_tree_missing_is_warning_not_required_artifact(self) -> None:
        """Missing tree should warn without making generated tree output mandatory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            root.mkdir()
            self.write_parent_fixture(root)
            bin_dir = Path(tmp_dir) / "empty-bin"
            bin_dir.mkdir()

            result = self.run_checker(root, env={"PATH": str(bin_dir)})

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=warn:tree_display:tree:missing-command",
                result.stdout,
            )
            self.assertIn("tree_display:missing", result.stdout)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_readme_documents_expected_parent_structure_and_tree_command(self) -> None:
        """The README should document the parent root shape and tree inspection route."""
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("<parent-root>/", readme)
        self.assertIn("vendor/agent-canon/", readme)
        self.assertIn(".codex/project-config.toml", readme)
        self.assertIn(".codex/project-skills/", readme)
        self.assertIn("GitHub path-constrained copy", readme)
        self.assertIn(
            "tree -a -L <depth> -I '.git|__pycache__|.venv|node_modules|target|reports' <parent-root>",
            readme,
        )
        self.assertIn("parent_repo_readiness.py", readme)

    def test_missing_active_contract_fails(self) -> None:
        """Template-owned active contract files are required at the parent root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / "documents" / "server-host-contract.md").unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:active_contract:"
                "documents/server-host-contract.md:missing-regular-file",
                result.stdout,
            )

    def test_stale_github_copy_fails(self) -> None:
        """Copied GitHub path constraint files must match their AgentCanon source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (
                root / ".github" / "scripts" / "checkout_agent_canon_submodule.sh"
            ).write_text(
                "# stale\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:github_copy:"
                ".github/scripts/checkout_agent_canon_submodule.sh:"
                "copy-differs-from-agent-canon-source",
                result.stdout,
            )

    def test_standalone_only_root_document_fails(self) -> None:
        """Standalone-only AgentCanon docs must not leak into parent root docs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            self.write_file(
                root, "documents/SHARED_RUNTIME_SURFACES.md", "stale root copy\n"
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:standalone_only_leak:"
                "documents/SHARED_RUNTIME_SURFACES.md:must-not-exist-in-parent-root",
                result.stdout,
            )

    def write_parent_fixture(self, root: Path) -> None:
        """Create a synthetic template-derived parent repo."""
        agent_canon = root / "vendor" / "agent-canon"
        agent_canon.parent.mkdir(parents=True)
        os.symlink(PROJECT_ROOT, agent_canon, target_is_directory=True)
        self.write_required_parent_files(root)
        manifest = load_manifest(
            root, "vendor/agent-canon", "documents/shared-runtime-surfaces.toml"
        )
        for entry in manifest.entries:
            target = root / entry.path
            if entry.mode == "symlink":
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.is_file():
                    target.unlink()
                elif target.exists():
                    shutil.rmtree(target)
                os.symlink(target_for_entry(root, manifest.prefix, entry), target)
            elif entry.mode == "copy":
                source = root / manifest.prefix / entry.source_or_default()
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif entry.mode == "regular":
                if entry.optional:
                    continue
                if entry.surface_class == "project_content":
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                source = root / manifest.prefix / entry.source_or_default()
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not target.exists():
                    self.write_file(root, entry.path, f"{entry.path}\n")

    def write_required_parent_files(self, root: Path) -> None:
        """Write parent-owned files that are outside the shared surface manifest."""
        files = {
            "README.md": "readme\n",
            "QUICK_START.md": "quick start\n",
            "Makefile": "ci:\n\t@true\n",
            ".gitmodules": '[submodule "vendor/agent-canon"]\n\tpath = vendor/agent-canon\n\turl = https://github.com/iwashita-nozomu/agent-canon.git\n',
            "goal.md": "goal\n",
            "responsibility-scope.toml": 'catalog_kind = "agent_canon_responsibility_scope"\n',
            ".agent-canon/update-state.toml": 'tasks_applied_through = "fixture"\n',
            "scripts/README.md": "scripts\n",
            ".dockerignore": ".git\n",
            "docker/README.md": "docker\n",
            "docker/Dockerfile": "FROM ubuntu:24.04\n",
            "docker/requirements.txt": "pytest\n",
            "docker/install_python_dependencies.sh": "#!/usr/bin/env bash\n",
            "docker/register_safe_directories.sh": "#!/usr/bin/env bash\n",
            "docker/packs/default.toml": '[pack]\nname = "default"\n',
            "docker/packs/default-host-docker.toml": '[pack]\nname = "default-host-docker"\n',
            ".github/workflows/ci.yml": "name: CI\n",
            ".github/workflows/docker-build.yml": "name: Docker Build\n",
            ".devcontainer/devcontainer.json": "\n".join(
                [
                    "{",
                    '  "initializeCommand": "bash .devcontainer/bootstrap-shared-runtime.sh && bash .devcontainer/generate-runtime-compose.sh",',
                    '  "postCreateCommand": "bash .devcontainer/post-create.sh /workspace/${localWorkspaceFolderBasename}",',
                    '  "postAttachCommand": "bash .devcontainer/post-attach.sh",',
                    '  "dockerComposeFile": "docker-compose.generated.yml",',
                    '  "service": "workspace",',
                    '  "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",',
                    '  "name": "${localWorkspaceFolderBasename}-devcontainer"',
                    "}",
                ]
            )
            + "\n",
            ".devcontainer/bootstrap-shared-runtime.sh": '#!/usr/bin/env bash\nset -euo pipefail\nscript_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"\nrepo_root="$(cd -- "${script_dir}/.." && pwd -P)"\nbash "${repo_root}/vendor/agent-canon/.devcontainer/bootstrap-shared-runtime.sh" "$@"\n',
            ".devcontainer/finalize-shared-runtime.sh": '#!/usr/bin/env bash\nset -euo pipefail\nscript_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"\nrepo_root="$(cd -- "${script_dir}/.." && pwd -P)"\nbash "${repo_root}/vendor/agent-canon/.devcontainer/finalize-shared-runtime.sh" "$@"\n',
            ".devcontainer/post-create.sh": '#!/usr/bin/env bash\nset -euo pipefail\nscript_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"\nrepo_root="$(cd -- "${script_dir}/.." && pwd -P)"\nworkspace="${1:-}"\nif [ -z "$workspace" ]; then\n  echo "post-create requires workspace root argument" >&2\n  exit 1\nfi\nbash "${repo_root}/vendor/agent-canon/.devcontainer/post-create.sh" "$workspace"\nparent_hook="${script_dir}/post-create-parent.sh"\nif [ -f "$parent_hook" ]; then\n  bash "$parent_hook" "$workspace"\nfi\n',
            ".devcontainer/post-create-parent.sh": "#!/usr/bin/env bash\nset -euo pipefail\n",
            ".devcontainer/post-attach.sh": '#!/usr/bin/env bash\nset -euo pipefail\nscript_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"\nrepo_root="$(cd -- "${script_dir}/.." && pwd -P)"\nbash "${repo_root}/vendor/agent-canon/.devcontainer/post-attach.sh" "$@"\n',
            ".devcontainer/generate-runtime-compose.sh": '#!/usr/bin/env bash\nset -euo pipefail\nscript_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"\nrepo_root="$(cd -- "${script_dir}/.." && pwd -P)"\nexport AGENT_CANON_DOCKER_COMPOSE_OUTPUT="${repo_root}/.devcontainer/docker-compose.generated.yml"\nbash "${repo_root}/vendor/agent-canon/.devcontainer/generate-runtime-compose.sh" "$@"\n',
        }
        for path, text in files.items():
            self.write_file(root, path, text)
        for relative in [
            "docker/install_python_dependencies.sh",
            "docker/register_safe_directories.sh",
            ".devcontainer/bootstrap-shared-runtime.sh",
            ".devcontainer/finalize-shared-runtime.sh",
            ".devcontainer/post-create.sh",
            ".devcontainer/post-attach.sh",
            ".devcontainer/generate-runtime-compose.sh",
            ".devcontainer/post-create-parent.sh",
        ]:
            (root / relative).chmod(0o755)

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
