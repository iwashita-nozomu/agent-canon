# @dependency-start
# contract test
# responsibility Tests GitHub workflow convention checker behavior.
# upstream implementation ../../tools/ci/check_github_workflows.py convention checker
# @dependency-end

"""Tests for GitHub workflow convention checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "ci" / "check_github_workflows.py"


class GitHubWorkflowCheckTest(unittest.TestCase):
    """Exercise the GitHub workflow checker."""

    def test_current_repository_passes(self) -> None:
        """The current repository should satisfy GitHub workflow conventions."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO_ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_legacy_auto_submodule_checkout_fails(self) -> None:
        """Checkout steps must use the explicit AgentCanon helper."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "ci.yml").write_text(
                "name: CI\n"
                "on: [push]\n"
                "permissions:\n"
                "  contents: read\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "        with:\n"
                "          submodules: true\n"
                "          persist-credentials: true\n",
                encoding="utf-8",
            )
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checkout_1_missing_submodules_false", result.stdout)
            self.assertIn("checkout_1_missing_persist_credentials_false", result.stdout)
            self.assertIn("missing_agent_canon_checkout_helper", result.stdout)
            self.assertIn("missing_agent_canon_repo_credential_env", result.stdout)

    def test_docker_build_workflow_requires_agent_canon_checkout(self) -> None:
        """Docker build workflow consumes shared devcontainer files from AgentCanon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "docker-build.yml").write_text(
                "name: Docker Build\n"
                "on: [push]\n"
                "permissions:\n"
                "  contents: read\n"
                "concurrency:\n"
                "  group: docker-${{ github.ref }}\n"
                "jobs:\n"
                "  docker-build:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "        with:\n"
                "          submodules: false\n"
                "          persist-credentials: false\n"
                "      - run: bash docker/check_build.sh --pack docker/packs/default.toml\n",
                encoding="utf-8",
            )
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_agent_canon_checkout_helper", result.stdout)
            self.assertIn("missing_agent_canon_repo_credential_env", result.stdout)

    def test_docker_build_workflow_with_agent_canon_checkout_passes(self) -> None:
        """Docker build workflow should be explicit about the AgentCanon checkout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "docker-build.yml").write_text(
                "name: Docker Build\n"
                "on: [push]\n"
                "permissions:\n"
                "  contents: read\n"
                "concurrency:\n"
                "  group: docker-${{ github.ref }}\n"
                "jobs:\n"
                "  docker-build:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "        with:\n"
                "          submodules: false\n"
                "          persist-credentials: false\n"
                "      - name: Checkout AgentCanon submodule\n"
                "        env:\n"
                "          AGENT_CANON_REPO_TOKEN: ${{ secrets.AGENT_CANON_REPO_TOKEN }}\n"
                "          AGENT_CANON_REPO_SSH_KEY: ${{ secrets.AGENT_CANON_REPO_SSH_KEY }}\n"
                "        run: bash .github/scripts/checkout_agent_canon_submodule.sh\n"
                "      - run: bash docker/check_build.sh --pack docker/packs/default.toml\n",
                encoding="utf-8",
            )
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_missing_pr_template_evidence_fails(self) -> None:
        """PR templates must retain validation and submodule evidence fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            (root / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text(
                "# Pull Request\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_text:Validation Evidence", result.stdout)
            self.assertIn("missing_text:Agent Orchestration Evidence", result.stdout)
            self.assertIn(
                "missing_text:expected template submodule SHA:",
                result.stdout,
            )

    def test_missing_pr_template_issue_gate_fails(self) -> None:
        """PR templates must require durable operational issue evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "Operational Findings / Issues",
                    "Findings",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_text:Operational Findings / Issues", result.stdout)

    def test_static_gates_require_accumulated_eval_parity(self) -> None:
        """Static gates must keep parity with accumulated eval checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            workflow = root / ".github" / "workflows" / "agent-canon-static-gates.yml"
            shutil.copy2(
                REPO_ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml",
                workflow,
            )
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "run_accumulated_agent_evals.py",
                    "run_accumulated_agent_evals_REMOVED.py",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "missing_text:run_accumulated_agent_evals.py",
                result.stdout,
            )

    def test_missing_agentcanon_issues_readme_fails(self) -> None:
        """Durable AgentCanon issue conventions must remain present."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            (root / "issues" / "README.md").unlink()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("path=issues/README.md", result.stdout)

    def test_issue_file_requires_edit_scope_field(self) -> None:
        """Operational issue files must include dependency-expanded edit scope."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            issue = next((root / "issues" / "open").glob("*.md"))
            issue.write_text(
                issue.read_text(encoding="utf-8").replace("edit_scope:", "scope:"),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_text:edit_scope:", result.stdout)

    def write_template_root_pr_template(self, root: Path) -> None:
        """Write a minimal valid template-root PR template."""
        path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "# Template / derived project PR",
                    "Validation Evidence",
                    "Plan Mode Evidence",
                    "Agent Orchestration Evidence",
                    "workflow=<family>",
                    "skills=$agent-orchestration",
                    "review=<...>",
                    "python3 tools/agent_tools/route.py --prompt",
                    "PR Mutation Authority",
                    "Authority / blocker notes",
                    "GitHub Automation Output",
                    "GITHUB_PR_AUTOMATION_DECISION",
                    "github_pr_automation_when_green",
                    "Operational Findings / Issues",
                    "vendor/agent-canon/issues/README.md",
                    "vendor/agent-canon/issues/closed/",
                    "Agent Improvement Guide artifact",
                    "Issue Mirror artifact",
                    "run_repo_dependency_review.sh --search-hits-file",
                    "Template / derived project PR",
                    "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing",
                    "make ci",
                    "AgentCanon Evidence",
                    "template submodule SHA:",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def copy_template_agent_canon_template(self, root: Path) -> None:
        """Copy the template-side AgentCanon PR template."""
        source = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md"
        destination = root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def test_job_level_permissions_are_accepted(self) -> None:
        """Workflow permissions may be declared on every job."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root, top_permissions=False, job_permissions=True)
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_missing_referenced_helper_path_fails(self) -> None:
        """Standalone workflows must reference an available checkout helper."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            (root / ".github" / "scripts" / "checkout_agent_canon_submodule.sh").unlink()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_referenced_agent_canon_checkout_helper", result.stdout)

    def test_helper_step_requires_credential_env(self) -> None:
        """Checkout helper steps need token or SSH credential context."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root, helper_env=False)
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "checkout_helper_1_missing_agent_canon_repo_credential_env",
                result.stdout,
            )

    def test_pr_flow_requires_separate_standalone_and_template_templates(self) -> None:
        """Ensure PR workflow does not route all PRs to one template."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            workflow_path = root / "agents" / "workflows" / "agent-canon-pr-workflow.md"
            workflow_path.write_text(
                "6. PR を作る\n\n"
                "- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` を使います。\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_text:standalone AgentCanon repo", result.stdout)
            self.assertIn("missing_text:template / derived repo", result.stdout)

    def test_vendor_path_without_gitmodules_uses_standalone_mode(self) -> None:
        """A vendor path alone must not trigger template-mode checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            (root / "vendor" / "agent-canon").mkdir(parents=True)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_template_mode_requires_template_agent_canon_template(self) -> None:
        """A real template root must keep the template-side AgentCanon PR template."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            (root / ".gitmodules").write_text(
                "[submodule \"vendor/agent-canon\"]\n"
                "\tpath = vendor/agent-canon\n"
                "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                encoding="utf-8",
            )
            (root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md").unlink()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "path=.github/PULL_REQUEST_TEMPLATE/agent_canon.md",
                result.stdout,
            )

    def test_template_root_pr_template_evidence_fails_when_present(self) -> None:
        """Optional template-root PR templates must keep orchestration evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            self.write_template_root_pr_template(root)
            self.copy_template_agent_canon_template(root)
            (root / ".gitmodules").write_text(
                "[submodule \"vendor/agent-canon\"]\n"
                "\tpath = vendor/agent-canon\n"
                "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                encoding="utf-8",
            )
            path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "Agent Orchestration Evidence",
                    "Routing Evidence",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_text:Agent Orchestration Evidence", result.stdout)

    def test_template_mode_does_not_require_standalone_root_docs(self) -> None:
        """Template roots should not require standalone-only root docs or PR templates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            (root / ".gitmodules").write_text(
                "[submodule \"vendor/agent-canon\"]\n"
                "\tpath = vendor/agent-canon\n"
                "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                encoding="utf-8",
            )
            (root / ".github" / "PULL_REQUEST_TEMPLATE.md").unlink()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def write_valid_workflow(
        self,
        root: Path,
        *,
        top_permissions: bool = True,
        job_permissions: bool = False,
        helper_env: bool = True,
    ) -> None:
        """Write one minimal valid workflow."""
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        permissions = "permissions:\n  contents: read\n" if top_permissions else ""
        job_permission_block = (
            "    permissions:\n"
            "      contents: read\n"
            if job_permissions
            else ""
        )
        env_block = (
            "        env:\n"
            "          AGENT_CANON_REPO_TOKEN: ${{ secrets.AGENT_CANON_REPO_TOKEN }}\n"
            "          AGENT_CANON_REPO_SSH_KEY: ${{ secrets.AGENT_CANON_REPO_SSH_KEY }}\n"
            if helper_env
            else ""
        )
        helper_command = "        run: bash .github/scripts/checkout_agent_canon_submodule.sh\n"
        (workflow_dir / "ci.yml").write_text(
            "name: CI\n"
            + "on: [push]\n"
            + permissions
            + "concurrency:\n"
            + "  group: ci-${{ github.ref }}\n"
            + "jobs:\n"
            + "  test:\n"
            + job_permission_block
            + "    runs-on: ubuntu-latest\n"
            + "    steps:\n"
            + "      - uses: actions/checkout@v4\n"
            + "        with:\n"
            + "          submodules: false\n"
            + "          persist-credentials: false\n"
            + "      - name: Checkout AgentCanon submodule\n"
            + env_block
            + helper_command,
            encoding="utf-8",
        )

    def copy_required_surfaces(self, root: Path) -> None:
        """Copy non-workflow surfaces required by the checker."""
        for relative in [
            ".github/AGENTS.md",
            ".github/scripts/checkout_agent_canon_submodule.sh",
            "tools/ci/checkout_agent_canon_submodule.sh",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
            "agents/workflows/agent-canon-pr-workflow.md",
            "issues/README.md",
            "issues/open/AC-20260517-eval-accumulation-gaps.md",
            "issues/closed/AC-20260513-durable-finding-auto-promotion.md",
            "README.md",
        ]:
            source = REPO_ROOT / relative
            if (
                relative == ".github/scripts/checkout_agent_canon_submodule.sh"
                and not source.exists()
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    'script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"\n'
                    'repo_root="$(cd "${script_dir}/../.." && pwd -P)"\n'
                    'exec bash "${repo_root}/tools/ci/checkout_agent_canon_submodule.sh" "$@"\n',
                    encoding="utf-8",
                )
                continue
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                source = source.resolve()
            shutil.copy2(source, destination)

    def copy_vendor_surfaces(self, root: Path) -> None:
        """Copy minimal vendor surfaces required by template-mode checks."""
        for relative in [
            "README.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "agents/workflows/agent-canon-pr-workflow.md",
            ".github/workflows/agent-coordination.yml",
            ".github/workflows/agent-runtime-dashboard.yml",
            "issues/README.md",
            "issues/open/AC-20260517-eval-accumulation-gaps.md",
            "issues/closed/AC-20260513-durable-finding-auto-promotion.md",
        ]:
            source = REPO_ROOT / relative
            destination = root / "vendor" / "agent-canon" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                source = source.resolve()
            shutil.copy2(source, destination)

    def test_template_runtime_dashboard_root_copy_is_rejected(self) -> None:
        """Template roots should use the AgentCanon repo dashboard, not a root copy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            self.copy_template_agent_canon_template(root)
            (root / ".gitmodules").write_text(
                '[submodule "vendor/agent-canon"]\n'
                "\tpath = vendor/agent-canon\n"
                "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                encoding="utf-8",
            )
            stale_dashboard = root / ".github" / "workflows" / "agent-runtime-dashboard.yml"
            stale_dashboard.parent.mkdir(parents=True, exist_ok=True)
            stale_dashboard.write_text("name: stale dashboard\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "template_runtime_dashboard_workflow_must_be_absent_use_agentcanon_repo",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
