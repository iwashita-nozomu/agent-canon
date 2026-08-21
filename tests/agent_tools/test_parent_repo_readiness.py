"""Tests for parent repository readiness checker."""

# @dependency-start
# contract test
# responsibility Tests AgentCanon parent repository readiness checks.
# upstream implementation ../../tools/agent_tools/parent_repo_readiness.py checks parent repo surfaces
# upstream implementation ../../tools/agent_tools/surface_manifest.py parses shared surface manifest
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml shared runtime surface manifest
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent readiness boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md opt-in runtime identity and shared-surface test contract
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "parent_repo_readiness.py"
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "test-parent-repo-readiness"
TEST_HOME = PROJECT_ROOT / ".agent-canon" / "test-home"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from agent_canon_source_root import resolve_agent_canon_source_root  # noqa: E402
from parent_repo_readiness import SubmoduleShapeChecker  # noqa: E402
from surface_manifest import (  # noqa: E402
    load_manifest,
    render_copy_specs,
    render_regular_specs,
    render_root_absent_paths,
    render_specs,
    target_for_entry,
)


class ParentRepoReadinessTest(unittest.TestCase):
    """Exercise parent repository readiness checks."""

    def run_checker(
        self,
        root: Path,
        *args: str,
        skip_submodule_check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the checker against a fixture parent root."""
        checker_args = ["--skip-container-config"]
        if skip_submodule_check:
            checker_args.append("--skip-submodule-check")
        checker_env = self.subprocess_environment()
        if env is not None:
            checker_env.update(env)
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--root",
                str(root),
                *checker_args,
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=checker_env,
        )

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        """Allocate test state inside the repository-owned temporary boundary."""
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_HOME.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)

    def subprocess_environment(self) -> dict[str, str]:
        """Keep subprocess HOME and temporary state inside the clone."""
        return {
            **os.environ,
            "HOME": str(TEST_HOME),
            "TMPDIR": str(TEST_TEMP_ROOT),
            "TEMP": str(TEST_TEMP_ROOT),
            "TMP": str(TEST_TEMP_ROOT),
        }

    def test_materialized_parent_fixture_passes(self) -> None:
        """A correctly materialized parent fixture should pass."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_skip_container_config_skips_parent_environment_semantics(self) -> None:
        """Readiness skip mode leaves parent-environment semantics to container_config."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            self.write_file(
                root,
                ".devcontainer/parent-environment.sh",
                "touch should-not-be-validated\n",
            )

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("container_config:skipped", result.stdout)

    def test_unconfigured_parent_environment_is_not_a_required_path(self) -> None:
        """Readiness accepts a parent that does not opt into environment projection."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".devcontainer/parent-environment.sh").unlink()
            (root / ".devcontainer/parent-environment.toml").unlink()

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_missing_parent_executable_capability_still_fails(self) -> None:
        """The optional environment change does not weaken executable sources."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".devcontainer/post-create-parent.sh").chmod(0o644)

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                ".devcontainer/post-create-parent.sh:not-executable",
                result.stdout,
            )

    def test_shared_surface_receipt(self) -> None:
        """The manifest exposes the complete minimal runtime projection."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )
        active = {
            entry.path: entry
            for entry in manifest.entries
            if entry.mode in {"symlink", "repo_state"} and not entry.optional
        }
        self.assertEqual(
            set(active),
            {
                "AGENTS.md",
                ".codex/config.toml",
                ".codex/agents",
                ".codex/hooks.json",
                ".codex/hooks",
            },
        )
        for entry in active.values():
            self.assertEqual(entry.projection_producer, "agent-canon")
            self.assertEqual(entry.projection_kind, "runtime_surface")

    def test_materialized_minimal_projection(self) -> None:
        """Materialization keeps every relative role config reference loadable."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            for path, target in {
                "AGENTS.md": "vendor/agent-canon/ROOT_AGENTS.md",
                ".codex/config.toml": "vendor/agent-canon/.codex/config.toml",
                ".codex/agents": "vendor/agent-canon/.codex/agents",
                ".codex/hooks.json": "vendor/agent-canon/.codex/hooks.json",
                ".codex/hooks": "vendor/agent-canon/.codex/hooks",
            }.items():
                projection = root / path
                self.assertTrue(projection.is_symlink(), path)
                self.assertEqual(
                    os.readlink(projection),
                    os.path.relpath(root / target, projection.parent),
                    path,
                )

            config_path = root / ".codex" / "config.toml"
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            for role_name, role in config["agents"].items():
                if not isinstance(role, dict):
                    continue
                role_path = config_path.parent / role["config_file"]
                self.assertTrue(role_path.is_file(), f"{role_name}: {role_path}")

    def test_derived_projection_resolves_source_and_public_tool_roots(self) -> None:
        """A derived parent keeps source bytes below vendor and exposes one public prefix."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.git(root, "init", "--quiet")
            source = root / "agent-canon-source"
            (source / "agents" / "skills").mkdir(parents=True)
            (source / "agents" / "skills" / "catalog.yaml").write_text(
                "skills: []\n", encoding="utf-8"
            )
            vendor = root / "vendor" / "agent-canon"
            vendor.parent.mkdir(parents=True)
            vendor.symlink_to("../agent-canon-source", target_is_directory=True)

            resolution = resolve_agent_canon_source_root(root)

            self.assertEqual(resolution.layout, "vendored")
            self.assertEqual(resolution.source_root, source.resolve())
            self.assertEqual(
                resolution.public_tool_root,
                (root / "tools" / "agent-canon").absolute(),
            )
            self.assertNotEqual(
                resolution.current_repository_root, resolution.source_root
            )

    def test_tree_present_adds_checked_token_and_command(self) -> None:
        """Tree availability should be reported without relying on the host tool."""
        with self.temporary_directory() as tmp_dir:
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
                skip_submodule_check=True,
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
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            root.mkdir()
            self.write_parent_fixture(root)
            bin_dir = Path(tmp_dir) / "empty-bin"
            bin_dir.mkdir()

            result = self.run_checker(
                root,
                skip_submodule_check=True,
                env={"PATH": str(bin_dir)},
            )

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

        self.assertIn("documents/parent-repository/README.md", readme)
        self.assertIn("vendor/agent-canon/", readme)

    def test_missing_active_contract_fails(self) -> None:
        """Active AgentCanon projection views are required at the parent root."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / "AGENTS.md").unlink()

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:shared_surface:"
                "AGENTS.md:missing-symlink",
                result.stdout,
            )

    def test_missing_github_copy_fails(self) -> None:
        """The runtime config projection is required at the parent root."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".codex" / "config.toml").unlink()

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:shared_surface:"
                ".codex/config.toml:missing-symlink",
                result.stdout,
            )

    def test_standalone_only_root_document_absence_is_expected(self) -> None:
        """Standalone-only AgentCanon root docs should be absent in parent fixtures."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_retired_entries_stay_out_of_active_projection_specs(self) -> None:
        """Manifest retirement modes drive root absence without exact names."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )
        retired = {
            entry.path
            for entry in manifest.entries
            if entry.mode in {"removed_legacy", "standalone_only"}
        }
        root_absent_paths = set(
            render_root_absent_paths(manifest.deletion_targets).splitlines()
        )
        active_spec_paths = {
            line.split(":", 1)[0]
            for rendered in (
                render_specs(manifest.entries, PROJECT_ROOT, manifest.prefix),
                render_copy_specs(manifest.entries, manifest.prefix),
                render_regular_specs(manifest.entries, manifest.prefix),
            )
            for line in rendered.splitlines()
            if line
        }

        self.assertTrue(retired)
        self.assertEqual(retired, root_absent_paths)
        self.assertTrue(retired.isdisjoint(active_spec_paths))

    def test_authentic_embedded_and_absorbed_submodules_pass(self) -> None:
        """Both supported Git storage layouts satisfy the identity contract."""
        for storage in ("embedded", "absorbed"):
            with self.subTest(storage=storage), self.temporary_directory() as tmp_dir:
                root = Path(tmp_dir) / "parent"
                self.write_authentic_parent_fixture(root, storage)

                result = self.run_checker(
                    root,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("submodule_check:git-identity", result.stdout)
                self.assertNotIn("expected-submodule-gitfile", result.stdout)

    def test_staged_gitlink_update_uses_index_authority(self) -> None:
        """A staged pin ahead of parent HEAD passes when child HEAD matches."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            child = root / "vendor/agent-canon"
            original_child_oid = self.git(
                child, "rev-parse", "--verify", "HEAD"
            ).stdout.strip()
            self.write_file(child, "README.md", "staged pin update\n")
            self.git(child, "add", "README.md")
            self.git(child, "commit", "--quiet", "-m", "staged-pin-update")
            child_oid = self.git(child, "rev-parse", "--verify", "HEAD").stdout.strip()
            self.assertNotEqual(original_child_oid, child_oid)
            self.git(
                root,
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{child_oid},vendor/agent-canon",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("submodule_check:git-identity", result.stdout)

    def test_missing_gitlink_index_is_typed(self) -> None:
        """An absent parent index entry is distinct from a missing manifest."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            self.git(root, "update-index", "--force-remove", "--", "vendor/agent-canon")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing-gitlink-index", result.stdout)

    def test_descendant_gitlink_without_exact_prefix_is_missing(self) -> None:
        """A descendant index record cannot stand in for the exact gitlink."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            child_oid = self.git(
                root / "vendor/agent-canon", "rev-parse", "--verify", "HEAD"
            ).stdout.strip()
            self.git(root, "update-index", "--force-remove", "--", "vendor/agent-canon")
            self.git(
                root,
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{child_oid},vendor/agent-canon/child",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing-gitlink-index", result.stdout)
            self.assertNotIn("index-entry-not-gitlink", result.stdout)

    def test_index_parser_ignores_descendant_records(self) -> None:
        """An exact record remains one entry when Git output has descendants."""
        output = "\n".join(
            (
                "160000 aaa 0\tvendor/agent-canon",
                "160000 bbb 0\tvendor/agent-canon/child",
            )
        )

        entries = SubmoduleShapeChecker.parse_index_entries(
            output, "vendor/agent-canon"
        )

        self.assertEqual(entries, (("vendor/agent-canon", "160000", "aaa", "0"),))

    def test_non_gitlink_index_mode_is_typed(self) -> None:
        """A stage-zero non-gitlink index entry is rejected by mode, not layout."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            blob_oid = self.git(
                root,
                "hash-object",
                "-w",
                "vendor/agent-canon/README.md",
            ).stdout.strip()
            self.git(
                root,
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{blob_oid},vendor/agent-canon",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("index-entry-not-gitlink", result.stdout)

    def test_uninitialized_submodule_is_typed(self) -> None:
        """A gitlink without a checked-out child is an uninitialized submodule."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            shutil.rmtree(root / "vendor/agent-canon")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("uninitialized-submodule", result.stdout)
            self.assertIn("vendor/agent-canon:missing-directory", result.stdout)
            self.assertIn(
                "vendor/agent-canon/documents/runtime/shared-runtime-surfaces.toml:missing-manifest",
                result.stdout,
            )

    def test_project_design_readme_is_parent_owned(self) -> None:
        """Project-owned design README paths are not standalone-only leaks."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            self.write_file(
                root,
                "documents/design/README.md",
                "project-owned design index\n",
            )

            result = self.run_checker(root, skip_submodule_check=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_plain_nested_clone_is_rejected_by_identity(self) -> None:
        """A plain nested clone fails through an observable OID mismatch."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            shutil.rmtree(root / "vendor/agent-canon")
            child = root / "vendor/agent-canon"
            self.git(
                root.parent,
                "clone",
                "--quiet",
                "--no-local",
                str(PROJECT_ROOT),
                str(child),
            )
            self.git(child, "config", "user.email", "readiness@example.com")
            self.git(child, "config", "user.name", "Readiness Fixture")
            self.write_file(child, "README.md", "plain nested clone\n")
            self.git(child, "add", "README.md")
            self.git(child, "commit", "--quiet", "-m", "plain-nested-clone")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("gitlink-oid-mismatch", result.stdout)

    def test_gitlink_and_child_head_mismatch_is_typed(self) -> None:
        """A checked-out child at another commit fails the OID identity check."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            child = root / "vendor/agent-canon"
            self.write_file(child, "README.md", "changed child commit\n")
            self.git(child, "add", "README.md")
            self.git(child, "commit", "--quiet", "-m", "child-change")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("gitlink-oid-mismatch", result.stdout)

    def test_dirty_submodule_is_typed_separately(self) -> None:
        """A dirty child is reported after identity and superproject checks pass."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            self.write_authentic_parent_fixture(root, "embedded")
            self.write_file(root / "vendor/agent-canon", "README.md", "dirty child\n")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("dirty-submodule", result.stdout)

    def test_wrong_superproject_is_typed(self) -> None:
        """A child whose Git superproject is another parent is rejected."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            wrong_root = Path(tmp_dir) / "wrong-parent"
            self.write_authentic_parent_fixture(root, "embedded")
            self.write_authentic_parent_fixture(wrong_root, "embedded")
            shutil.rmtree(root / "vendor/agent-canon")
            os.symlink(
                wrong_root / "vendor/agent-canon",
                root / "vendor/agent-canon",
                target_is_directory=True,
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("wrong-superproject", result.stdout)

    def git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a fixture Git operation with repository-local identity."""
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=False,
            capture_output=True,
            text=True,
            env=self.subprocess_environment(),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}",
        )
        return result

    def write_authentic_parent_fixture(self, root: Path, storage: str) -> None:
        """Create a real parent/gitlink fixture in one of the valid layouts."""
        self.assertIn(storage, {"embedded", "absorbed"})
        root.mkdir(parents=True)
        self.write_required_parent_files(root)
        self.git(root, "init", "--quiet")
        self.git(root, "config", "user.email", "readiness@example.com")
        self.git(root, "config", "user.name", "Readiness Fixture")
        self.git(root, "add", "--all")
        self.git(root, "commit", "--quiet", "-m", "parent-scaffold")

        source = root.parent / f"{root.name}-agent-canon-source"
        self.git(
            root.parent,
            "clone",
            "--quiet",
            "--no-local",
            str(PROJECT_ROOT),
            str(source),
        )
        child = root / "vendor/agent-canon"
        child.parent.mkdir(parents=True, exist_ok=True)
        self.git(
            root.parent,
            "clone",
            "--quiet",
            "--no-local",
            str(source),
            str(child),
        )
        self.git(child, "config", "user.email", "readiness@example.com")
        self.git(child, "config", "user.name", "Readiness Fixture")
        self.materialize_parent_fixture(root)
        self.git(root, "add", "--all")
        self.git(root, "commit", "--quiet", "-m", "parent-submodule")
        if storage == "absorbed":
            self.git(root, "submodule", "absorbgitdirs", "--", "vendor/agent-canon")

    def materialize_parent_fixture(self, root: Path) -> None:
        """Materialize the manifest-defined root views for a fixture parent."""
        manifest = load_manifest(
            root, "vendor/agent-canon", "documents/runtime/shared-runtime-surfaces.toml"
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
                if entry.projection_kind == "project_content":
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                source = root / manifest.prefix / entry.source_or_default()
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not target.exists():
                    self.write_file(root, entry.path, f"{entry.path}\n")

    def write_parent_fixture(self, root: Path) -> None:
        """Create a synthetic template-derived parent repo."""
        agent_canon = root / "vendor" / "agent-canon"
        agent_canon.parent.mkdir(parents=True)
        os.symlink(PROJECT_ROOT, agent_canon, target_is_directory=True)
        self.write_required_parent_files(root)
        self.materialize_parent_fixture(root)

    def write_required_parent_files(self, root: Path) -> None:
        """Write parent-owned files that are outside the shared surface manifest."""
        files = {
            "README.md": "readme\n",
            "QUICK_START.md": "quick start\n",
            "Makefile": "ci:\n\t@true\n",
            ".gitmodules": '[submodule "vendor/agent-canon"]\n\tpath = vendor/agent-canon\n\turl = https://github.com/iwashita-nozomu/agent-canon.git\n',
            "documents/README.md": "documents\n",
            "responsibility-scope.toml": 'catalog_kind = "agent_canon_responsibility_scope"\n',
            ".agent-canon/update-state.toml": 'tasks_applied_through = "fixture"\n',
            "scripts/README.md": "scripts\n",
            ".dockerignore": ".git\n",
            "docker/README.md": "docker\n",
            "docker/Dockerfile": "FROM ubuntu:24.04\n",
            "docker/packs/default.toml": '[pack]\nname = "default"\n',
            "docker/packs/default-host-docker.toml": '[pack]\nname = "default-host-docker"\n',
            ".github/workflows/ci.yml": "name: CI\n",
            ".github/workflows/docker-build.yml": "name: Docker Build\n",
            ".devcontainer/devcontainer.json": "\n".join(
                [
                    "{",
                    '  "initializeCommand": "AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",',
                    '  "postCreateCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-create-entrypoint.sh /workspace/${localWorkspaceFolderBasename}",',
                    '  "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",',
                    '  "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",',
                    '  "service": "workspace",',
                    '  "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",',
                    '  "name": "${localWorkspaceFolderBasename}-devcontainer"',
                    "}",
                ]
            )
            + "\n",
            ".devcontainer/post-create-parent.sh": "#!/usr/bin/env bash\nset -euo pipefail\n",
            ".devcontainer/parent-environment.sh": "",
            ".devcontainer/parent-environment.toml": "variables = []\n",
        }
        for path, text in files.items():
            self.write_file(root, path, text)
        for relative in [
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
