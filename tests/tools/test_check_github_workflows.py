# @dependency-start
# contract test
# responsibility Tests GitHub workflow convention checker behavior.
# upstream implementation ../../tools/ci/check_github_workflows.py convention checker
# upstream implementation ../../.github/workflows/agent-runtime-dashboard.yml scheduled graph producer orchestration
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py canonical source-root command execution
# @dependency-end

"""Tests for GitHub workflow convention checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from collections.abc import Callable
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "ci" / "check_github_workflows.py"
RUNTIME_DASHBOARD_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "agent-runtime-dashboard.yml"
)
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


class GitHubWorkflowCheckTest(unittest.TestCase):
    """Exercise the GitHub workflow checker."""

    def scheduled_graph_command(self) -> tuple[str, str]:
        """Read the producer-owned scheduled graph command from its workflow."""
        payload = yaml.safe_load(
            RUNTIME_DASHBOARD_WORKFLOW.read_text(encoding="utf-8")
        )
        steps = payload["jobs"]["dashboard"]["steps"]
        step = next(
            item
            for item in steps
            if item.get("name") == "Build and read back canonical graph"
        )
        return str(step["if"]), str(step["run"])

    def scheduled_graph_fixture(self, root: Path) -> tuple[Path, Path]:
        """Create a fresh source root with a recording canonical Graph CLI."""
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "graph@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Graph Fixture"],
            cwd=root,
            check=True,
        )
        (root / "README.md").write_text("scheduled graph fixture\n", encoding="utf-8")
        (root / ".gitignore").write_text(
            ".agent-canon/\n.scheduled-graph-calls\n",
            encoding="utf-8",
        )
        catalog = root / "agents" / "skills" / "catalog.yaml"
        catalog.parent.mkdir(parents=True)
        catalog.write_text("skills: {}\n", encoding="utf-8")
        module = root / "tools" / "agent_tools" / "agent_canon_source_root.py"
        module.parent.mkdir(parents=True)
        shutil.copy2(
            REPO_ROOT / "tools" / "agent_tools" / "agent_canon_source_root.py",
            module,
        )
        shutil.copy2(
            REPO_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
            module.parent / "parent_root_side_effects.py",
        )
        executable = root / "tools" / "bin" / "agent-canon"
        executable.parent.mkdir(parents=True)
        executable.write_text(
            """#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[sys.argv.index("--root") + 1]).resolve()
command = sys.argv[1:3]
calls = root / ".scheduled-graph-calls"
prior = calls.read_text(encoding="utf-8") if calls.exists() else ""
calls.write_text(prior + " ".join(command) + "\\n", encoding="utf-8")
db = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
head = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=root, text=True
).strip()
content_fingerprint = hashlib.sha256(
    (root / "README.md").read_bytes()
).hexdigest()

if command == ["graph", "build"]:
    mode = os.environ.get("GRAPH_BUILD_MODE", "fresh")
    if mode == "failure":
        print(json.dumps({
            "schema": "agent-canon.graph.build.v1",
            "command": "build",
            "status": "unavailable",
            "exit_code": 1,
        }))
        raise SystemExit(1)
    status = "incomplete" if mode == "incomplete" else "fresh"
    exit_code = 1 if status == "incomplete" else 0
    record = {
        "schema": "agent-canon.graph.build.v1",
        "command": "build",
        "status": status,
        "input_fingerprint": content_fingerprint,
        "integration_record": {
            "snapshot_head": head,
            "input_fingerprint": content_fingerprint,
        },
        "publication": "published",
        "durability": "durable",
        "exit_code": exit_code,
    }
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text(json.dumps(record), encoding="utf-8")
    print(json.dumps(record))
    raise SystemExit(exit_code)

if command == ["graph", "status"]:
    if not db.exists():
        print(json.dumps({
            "schema": "agent-canon.graph.status.v1",
            "command": "status",
            "status": "unavailable",
            "exit_code": 1,
        }))
        raise SystemExit(1)
    record = json.loads(db.read_text(encoding="utf-8"))
    integration = record["integration_record"]
    fresh = (
        record["status"] == "fresh"
        and integration["snapshot_head"] == head
        and integration["input_fingerprint"] == content_fingerprint
    )
    status = "fresh" if fresh else "stale"
    reason = None if fresh else "source_changed"
    payload = {
        "schema": "agent-canon.graph.status.v1",
        "command": "status",
        "status": status,
        "input_fingerprint": integration["input_fingerprint"],
        "integration_record": integration,
        "reason": reason,
        "probe_reason": reason,
        "exit_code": 0 if fresh else 2,
    }
    print(json.dumps(payload))
    raise SystemExit(payload["exit_code"])

raise SystemExit(2)
""",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        subprocess.run(
            ["git", "add", "."],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "scheduled graph fixture"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        db = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
        return root / ".scheduled-graph-calls", db

    def run_scheduled_graph_fixture(
        self,
        root: Path,
        *,
        build_mode: str,
    ) -> subprocess.CompletedProcess[str]:
        """Execute the workflow-owned schedule command in a fresh root."""
        _condition, command = self.scheduled_graph_command()
        environment = os.environ.copy()
        for key in _PARENT_BOUNDARY_PATH_KEYS:
            environment.pop(key, None)
        environment.update(
            {
                "GITHUB_WORKSPACE": str(root),
                "GRAPH_BUILD_MODE": build_mode,
            }
        )
        return subprocess.run(
            ["bash", "-c", command],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_scheduled_graph_bootstraps_absent_db_and_reads_fresh(self) -> None:
        """The schedule owner builds once before fresh identity readback."""
        condition, _command = self.scheduled_graph_command()
        self.assertEqual(condition, "github.event_name == 'schedule'")
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            calls, db = self.scheduled_graph_fixture(root)
            self.assertFalse(db.exists())

            result = self.run_scheduled_graph_fixture(root, build_mode="fresh")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(db.is_file())
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines(),
                ["graph build", "graph status"],
            )
            payload = json.loads(result.stdout.splitlines()[-1])
            expected_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            expected_fingerprint = hashlib.sha256(
                (root / "README.md").read_bytes()
            ).hexdigest()
            self.assertEqual(payload["status"], "fresh")
            self.assertEqual(
                payload["integration_record"]["snapshot_head"], expected_head
            )
            self.assertEqual(payload["input_fingerprint"], expected_fingerprint)

    def test_scheduled_graph_build_failure_and_incomplete_stop_readback(self) -> None:
        """Build failure and incomplete publication fail before status readback."""
        for build_mode in ("failure", "incomplete"):
            with self.subTest(build_mode=build_mode), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                calls, _db = self.scheduled_graph_fixture(root)

                result = self.run_scheduled_graph_fixture(
                    root,
                    build_mode=build_mode,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    calls.read_text(encoding="utf-8").splitlines(),
                    ["graph build"],
                )

    def test_template_agentcanon_source_and_projection_have_concise_identity_contract(
        self,
    ) -> None:
        """Canonical and checked-in targets expose one concise identity relation."""
        for relative in (
            "templates/documents/github/pull-request/agent_canon.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        ):
            with self.subTest(path=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")
                for field in ("source_commit:", "template_pin:", "pr_head:"):
                    self.assertEqual(text.count(field), 1)
                self.assertIn(
                    "identity relation (source_commit -> template_pin -> pr_head):",
                    text,
                )
                self.assertNotIn("Plan Mode Evidence", text)
                self.assertNotIn("Operational Findings / Issues", text)

    def test_template_agentcanon_identity_and_legacy_gates_are_rejected(self) -> None:
        """Missing or duplicate identities and universal gates fail closed."""
        variants: dict[str, tuple[Callable[[str], str], str]] = {
            "missing": (
                lambda text: text.replace("- source_commit:\n", ""),
                "identity_field_count:source_commit:0",
            ),
            "duplicate": (
                lambda text: text + "\n- pr_head:\n",
                "identity_field_count:pr_head:2",
            ),
            "legacy": (
                lambda text: text + "\n## Plan Mode Evidence\n",
                "forbidden_universal_pr_gate:Plan Mode Evidence",
            ),
        }
        targets = (
            "templates/documents/github/pull-request/agent_canon.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        )
        for relative in targets:
            for variant, (mutate, finding) in variants.items():
                with (
                    self.subTest(path=relative, variant=variant),
                    tempfile.TemporaryDirectory() as tmp_dir,
                ):
                    root = Path(tmp_dir)
                    self.write_valid_workflow(root)
                    self.copy_required_surfaces(root)
                    path = root / relative
                    path.write_text(
                        mutate(path.read_text(encoding="utf-8")),
                        encoding="utf-8",
                    )

                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), "--root", str(root)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(finding, result.stdout)

    def test_alternatives_are_optional_and_validation_is_surface_selected(self) -> None:
        """A PR without a real choice may omit alternatives and choose its check."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            for relative in (
                "templates/documents/github/pull-request/agent_canon.md",
                ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
            ):
                path = root / relative
                text = path.read_text(encoding="utf-8")
                text = text.split("## Alternatives / Independent Review", 1)[0]
                text += "\n- changed-surface validation: make ci\n"
                path.write_text(text, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_agent_canon_candidate_tree_has_one_remote_gate_consumer(self) -> None:
        """PR CI invokes the canonical gate once and has no duplicate push trigger."""
        workflow = REPO_ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
        text = workflow.read_text(encoding="utf-8")
        run_lines = [
            line.strip()
            for line in text.splitlines()
            if line.lstrip().startswith("run:")
        ]

        self.assertNotIn("\n  push:", text)
        self.assertEqual(
            [line for line in run_lines if "check_agent_canon_pr.sh" in line],
            ["run: bash tools/ci/check_agent_canon_pr.sh"],
        )
        self.assertIn(
            "github.event.pull_request.head.sha || github.sha",
            text,
        )
        self.assertIn("persist-credentials: false", text)
        self.assertIn("AGENT_CANON_PR_READ_TOKEN: ${{ github.token }}", text)
        self.assertFalse(
            any(
                command in "\n".join(run_lines)
                for command in (
                    "check_agent_runtime_alignment.py",
                    "evaluate_skill_workflow_prompts.py",
                    "check_github_workflows.py",
                )
            )
        )

    def test_standalone_static_gates_have_no_project_quality_job(self) -> None:
        """Standalone static gates do not create a repository-wide quality owner."""
        source = (
            REPO_ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("project-quality:", source)
        self.assertNotIn("run_python_quality_checks.sh", source)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow = root / ".github" / "workflows" / "agent-canon-static-gates.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(source, encoding="utf-8")
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_derived_parent_quality_route_uses_owner_and_command_not_job_name(
        self,
    ) -> None:
        """Derived quality ownership is bound to a parent marker and command."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            self.write_template_root_pr_template(root)
            self.copy_template_agent_canon_template(root)
            (root / ".gitmodules").write_text(
                '[submodule "vendor/agent-canon"]\n'
                "\tpath = vendor/agent-canon\n"
                "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                encoding="utf-8",
            )
            workflow_path = root / ".github" / "workflows" / "ci.yml"
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8").replace(
                    "  test:\n", "  project-quality-owner:\n"
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_derived_parent_quality_route_fails_without_owner_or_command(self) -> None:
        """Derived quality routes fail closed when owner or canonical command is absent."""
        variants = {
            "missing_owner": (
                "",
                "        run: make ci\n",
                "missing_parent_project_quality_owner",
            ),
            "missing_command": (
                "          AGENT_CANON_PR_PROJECT_QUALITY_OWNER: parent_ci\n",
                "        run: echo no-quality-route\n",
                "parent_project_quality_route_missing_canonical_command",
            ),
            "wrong_owner": (
                "          AGENT_CANON_PR_PROJECT_QUALITY_OWNER: wrong_owner\n",
                "        run: make ci\n",
                "parent_project_quality_owner_must_be_parent_ci",
            ),
        }
        for name, (owner_text, command_text, finding) in variants.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                self.write_valid_workflow(root)
                self.copy_required_surfaces(root)
                self.copy_vendor_surfaces(root)
                self.write_template_root_pr_template(root)
                self.copy_template_agent_canon_template(root)
                (root / ".gitmodules").write_text(
                    '[submodule "vendor/agent-canon"]\n'
                    "\tpath = vendor/agent-canon\n"
                    "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                    encoding="utf-8",
                )
                workflow_path = root / ".github" / "workflows" / "ci.yml"
                workflow_text = workflow_path.read_text(encoding="utf-8")
                workflow_text = workflow_text.replace(
                    "          AGENT_CANON_PR_PROJECT_QUALITY_OWNER: parent_ci\n",
                    owner_text,
                )
                workflow_text = workflow_text.replace(
                    "        run: make ci\n", command_text
                )
                workflow_path.write_text(workflow_text, encoding="utf-8")

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(root)],
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(finding, result.stdout)

    def test_agent_canon_candidate_gate_requires_step_local_read_credential(
        self,
    ) -> None:
        """The trusted-base token cannot be omitted or promoted to job scope."""
        source = (
            REPO_ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
        ).read_text(encoding="utf-8")
        step_local = (
            "        env:\n          AGENT_CANON_PR_READ_TOKEN: ${{ github.token }}\n"
        )
        variants = {
            "missing": source.replace(step_local, ""),
            "job_scope": source.replace(
                "    runs-on: ubuntu-latest\n",
                "    runs-on: ubuntu-latest\n"
                "    env:\n"
                "      AGENT_CANON_PR_READ_TOKEN: ${{ github.token }}\n",
            ).replace(step_local, ""),
        }
        for name, workflow_text in variants.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                workflow = (
                    root / ".github" / "workflows" / "agent-canon-static-gates.yml"
                )
                workflow.parent.mkdir(parents=True)
                workflow.write_text(workflow_text, encoding="utf-8")
                self.copy_required_surfaces(root)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(root)],
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "missing_step_local_github_read_credential",
                    result.stdout,
                )
                if name == "job_scope":
                    self.assertIn(
                        "canonical_candidate_gate_read_credential_must_be_step_local",
                        result.stdout,
                    )

    def test_direct_workflow_dispatch_input_in_run_fails(self) -> None:
        """Shell run blocks must not interpolate workflow-dispatch inputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            workflow = root / ".github" / "workflows" / "agent-coordination.yml"
            shutil.copy2(
                REPO_ROOT / ".github" / "workflows" / "agent-coordination.yml",
                workflow,
            )
            source = workflow.read_text(encoding="utf-8")
            for interpolation in (
                "${{ inputs.task }}",
                "${{ inputs['task'] }}",
                "${{ github.event.inputs.task }}",
            ):
                with self.subTest(interpolation=interpolation):
                    workflow.write_text(
                        source.replace(
                            '--task "${AGENT_COORDINATION_TASK}"',
                            '--task "' + interpolation + '"',
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
                        "direct_workflow_dispatch_input_interpolation",
                        result.stdout,
                    )

    def test_specialist_allowlist_rejects_multiline_values(self) -> None:
        """The canonical workflow guards malformed specialist input before parsing."""
        workflow = REPO_ROOT / ".github" / "workflows" / "agent-coordination.yml"
        text = workflow.read_text(encoding="utf-8")

        self.assertIn('case "${AGENT_COORDINATION_SPECIALISTS}" in', text)
        self.assertIn("*$'\\n'*|*$'\\r'*)", text)
        self.assertIn(
            "researcher|research_reviewer|scheduler|schedule_reviewer|"
            "infra_steward|infra_reviewer",
            text,
        )
        self.assertIn("unsupported specialist role", text)

    def test_coordination_uses_one_intake_bundle(self) -> None:
        """Normal coordination keeps intake evidence in one job."""
        workflow = REPO_ROOT / ".github" / "workflows" / "agent-coordination.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("  coordinate:", source)
        self.assertNotIn("\n  manager:\n", source)
        self.assertNotIn("manager_reviewer", source)
        self.assertNotIn("manager_response", source)
        self.assertNotIn("\n    needs:", source)
        self.assertEqual(source.count("name: Upload coordination bundle"), 1)
        self.assertIn("team_manifest.yaml", source)
        self.assertIn("run.capacity_request.lineage.role_ids", source)
        self.assertIn("GITHUB_STEP_SUMMARY", source)
        self.assertIn("SCHEDULED_SPECIALISTS=", source)
        self.assertIn("executed_role=coordination", source)
        self.assertIn("finding=none at intake", source)
        self.assertIn("result=bundle_ready", source)
        self.assertEqual(source.count("--role manager"), 1)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            target = root / ".github" / "workflows" / "agent-coordination.yml"
            shutil.copy2(workflow, target)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_coordination_summary_route_is_required(self) -> None:
        """The checker rejects coordination without packet readback summary evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            target = root / ".github" / "workflows" / "agent-coordination.yml"
            source = REPO_ROOT.joinpath(
                ".github/workflows/agent-coordination.yml"
            ).read_text(encoding="utf-8")
            target.write_text(
                source.replace("GITHUB_STEP_SUMMARY", "STEP_SUMMARY_REMOVED"),
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
            "coordination_summary_missing:GITHUB_STEP_SUMMARY",
            result.stdout,
        )

    def test_coordination_readback_executes_against_generated_manifest(self) -> None:
        """The workflow's packet readback resolves specialists from a real bundle."""
        workflow = REPO_ROOT / ".github/workflows/agent-coordination.yml"
        source = workflow.read_text(encoding="utf-8")
        start = 'if ! role_readback="$(python3 - "${manifest_path}" <<\'PY\'\n'
        end = "\n          PY\n"
        self.assertIn(start, source)
        embedded = source.split(start, 1)[1].split(end, 1)[0]
        readback_script = textwrap.dedent(embedded)
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir)
            bootstrap_environment = os.environ.copy()
            bootstrap_environment["AGENT_CANON_PARENT_ROOT"] = str(REPO_ROOT)
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    "tools/agent_tools/bootstrap_agent_run.py",
                    "--skip-agent-canon-preflight",
                    "--task",
                    "coordination readback test",
                    "--owner",
                    "workflow-test",
                    "--workspace-root",
                    str(REPO_ROOT),
                    "--report-root",
                    str(report_root),
                    "--enable",
                    "researcher",
                    "--enable",
                    "scheduler",
                ],
                cwd=REPO_ROOT,
                env=bootstrap_environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stdout + bootstrap.stderr)
            report_dir = next(
                Path(line.split("=", 1)[1])
                for line in bootstrap.stdout.splitlines()
                if line.startswith("REPORT_DIR=")
            )
            readback = subprocess.run(
                [sys.executable, "-", str(report_dir / "team_manifest.yaml")],
                input=readback_script,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(readback.returncode, 0, readback.stdout + readback.stderr)
        self.assertIn(
            "SCHEDULED_SPECIALISTS=test_designer,researcher,scheduler",
            readback.stdout,
        )

    def test_improvement_guide_is_bounded_and_manual(self) -> None:
        """Improvement guidance does not run for every push or unscoped PR."""
        workflow = REPO_ROOT / ".github" / "workflows" / "agent-improvement-guide.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertNotIn("\n  push:", source)
        self.assertIn("pull_request:\n    paths:", source)
        self.assertIn("workflow_dispatch:", source)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            shutil.copy2(workflow, root / ".github/workflows/agent-improvement-guide.yml")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_root_improvement_guide_allows_standalone_or_template_claim(self) -> None:
        """Root improvement workflow accepts standalone or template contract phrasing."""
        workflow = REPO_ROOT / ".github" / "workflows" / "agent-improvement-guide.yml"
        source = workflow.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            root_workflow = root / ".github" / "workflows" / "agent-improvement-guide.yml"
            shutil.copy2(workflow, root_workflow)

            for allowed in (
                "Standalone AgentCanon improvement guidance workflow",
                "Template AgentCanon improvement guidance workflow",
            ):
                rewritten = re.sub(
                    r"Standalone AgentCanon improvement guidance workflow|Template AgentCanon improvement guidance workflow",
                    allowed,
                    source,
                )
                root_workflow.write_text(rewritten, encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(root)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            root_workflow.write_text(
                root_workflow.read_text(encoding="utf-8").replace(
                    "AgentCanon improvement guidance workflow",
                    "General improvement guidance workflow",
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("missing_text_any_of:", result.stdout)

    def test_legacy_auto_submodule_checkout_fails_safety_settings(self) -> None:
        """Unsafe checkout settings fail without inventing an AgentCanon dependency."""
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
            self.assertNotIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_project_only_docker_build_does_not_require_agent_canon_checkout(
        self,
    ) -> None:
        """A direct project Docker build has no AgentCanon checkout dependency."""
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_agent_canon_tool_workflow_requires_agent_canon_checkout(self) -> None:
        """A workflow invoking the shared tool view must prepare the submodule."""
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
                "      - run: python3 tools/agent-canon/ci/container_config.py\n",
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

    def test_workflow_env_agent_canon_path_requires_helper(self) -> None:
        """Workflow env is part of every step's effective execution context."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            env:
              CANON_TOOL: tools/agent-canon/ci/container_config.py
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: python3 "$CANON_TOOL"
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_job_env_agent_canon_path_requires_helper(self) -> None:
        """Job env is inherited by its execution steps."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                env:
                  CANON_ROOT: tools/agent-canon
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: python3 "${CANON_ROOT}/ci/container_config.py"
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_step_env_resolves_inherited_literal_agent_canon_path(self) -> None:
        """Step env resolves literal references inherited from wider scopes."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            env:
              CANON_ROOT: tools/agent-canon
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - env:
                      CANON_TOOL: ${{ env.CANON_ROOT }}/ci/container_config.py
                    run: python3 "$CANON_TOOL"
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_job_default_working_directory_requires_helper(self) -> None:
        """Job run defaults override workflow defaults in effective context."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            defaults:
              run:
                working-directory: docker
            jobs:
              test:
                runs-on: ubuntu-latest
                defaults:
                  run:
                    working-directory: tools/agent-canon
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: python3 ci/container_config.py
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_shell_line_continuation_agent_canon_path_requires_helper(self) -> None:
        """Shell continuation cannot hide an AgentCanon-owned path."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: |
                      python3 tools/agent-\\
                      canon/ci/container_config.py
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("missing_agent_canon_checkout_helper", result.stdout)

    def test_agent_canon_consumer_without_repository_checkout_fails(self) -> None:
        """An AgentCanon consumer requires both repository and helper checkout."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 tools/agent-canon/ci/container_config.py
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "agent_canon_consumer_missing_prior_repository_checkout:job=test",
            result.stdout,
        )
        self.assertIn(
            "agent_canon_consumer_missing_prior_checkout_helper:job=test",
            result.stdout,
        )

    def test_agent_canon_helper_without_repository_checkout_fails(self) -> None:
        """The submodule helper cannot run before actions/checkout prepares the repo."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: bash .github/scripts/checkout_agent_canon_submodule.sh
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "agent_canon_checkout_helper_missing_prior_repository_checkout:job=test",
            result.stdout,
        )

    def test_agent_canon_consumer_before_helper_fails(self) -> None:
        """The helper must run before the first consumer in its job."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: python3 tools/agent-canon/ci/container_config.py
                  - run: bash .github/scripts/checkout_agent_canon_submodule.sh
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "agent_canon_consumer_missing_prior_checkout_helper:job=test",
            result.stdout,
        )

    def test_agent_canon_helper_before_repository_checkout_fails(self) -> None:
        """The repository checkout must precede the helper in the same job."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - run: bash .github/scripts/checkout_agent_canon_submodule.sh
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: python3 tools/agent-canon/ci/container_config.py
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "agent_canon_checkout_helper_missing_prior_repository_checkout:job=test",
            result.stdout,
        )
        self.assertIn(
            "agent_canon_consumer_missing_prior_checkout_helper:job=test",
            result.stdout,
        )

    def test_agent_canon_helper_in_another_job_does_not_satisfy_consumer(self) -> None:
        """Checkout/helper preparation is local to each consuming job."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              prepare:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: bash .github/scripts/checkout_agent_canon_submodule.sh
              consume:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: python3 tools/agent-canon/ci/container_config.py
            """
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "agent_canon_consumer_missing_prior_checkout_helper:job=consume",
            result.stdout,
        )

    def test_ordered_same_job_agent_canon_checkout_sequence_passes(self) -> None:
        """Repository checkout, helper, and consumer form the canonical sequence."""
        result = self.run_custom_workflow(
            """
            name: CI
            on: [push]
            permissions:
              contents: read
            concurrency:
              group: ci-${{ github.ref }}
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                    with:
                      submodules: false
                      persist-credentials: false
                  - run: bash .github/scripts/checkout_agent_canon_submodule.sh
                  - run: python3 tools/agent-canon/ci/container_config.py
            """
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

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
        """PR templates must retain the concise PR Essence fields."""
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
            self.assertIn("missing_text:## PR Essence", result.stdout)
            self.assertIn("missing_text:source_commit:", result.stdout)
            self.assertIn("missing_text:changed-surface validation:", result.stdout)

    def test_missing_pr_template_risk_gate_fails(self) -> None:
        """PR templates must record risk and follow-up without an issue sweep."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "- risk:",
                    "- risk omitted:",
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
            self.assertIn("missing_text:risk:", result.stdout)

    def test_static_gates_require_the_canonical_candidate_gate(self) -> None:
        """Static gates cannot replace the one candidate-tree gate consumer."""
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
                    "bash tools/ci/check_agent_canon_pr.sh",
                    "bash tools/ci/check_agent_canon_pr_REMOVED.sh",
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
                "missing_text:bash tools/ci/check_agent_canon_pr.sh",
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
            issue = root / "issues" / "closed" / "AC-20260517-eval-accumulation-gaps.md"
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

    def test_issue_mirror_workflow_with_checkout_failure_summary_passes(self) -> None:
        """Standalone issue mirror can only fail checkout by writing failure summary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_required_surfaces(root)
            self.ensure_issue_readme_contains_issue_required_fields(root)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True, exist_ok=True)
            (workflow_dir / "issue-mirror.yml").write_text(
                (REPO_ROOT / ".github" / "workflows" / "issue-mirror.yml").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_issue_mirror_fails_with_continue_on_error_checkout(self) -> None:
        """Issue-mirror checkout must not swallow failures with continue-on-error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_required_surfaces(root)
            self.ensure_issue_readme_contains_issue_required_fields(root)
            workflow = root / ".github" / "workflows" / "issue-mirror.yml"
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(
                (REPO_ROOT / ".github" / "workflows" / "issue-mirror.yml").read_text(
                    encoding="utf-8"
                ).replace(
                    "      - name: Checkout repository\n"
                    "        id: checkout\n"
                    "        uses: actions/checkout@v4\n",
                    "      - name: Checkout repository\n"
                    "        id: checkout\n"
                    "        uses: actions/checkout@v4\n        continue-on-error: true\n",
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
                "issue_mirror_checkout_continue_on_error_not_allowed",
                result.stdout,
            )

    def test_issue_mirror_fails_with_checkout_pass_fallback(self) -> None:
        """Issue-mirror checkout failure handling must not emit pass status."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_required_surfaces(root)
            self.ensure_issue_readme_contains_issue_required_fields(root)
            workflow = root / ".github" / "workflows" / "issue-mirror.yml"
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(
                (
                    REPO_ROOT / ".github" / "workflows" / "issue-mirror.yml"
                ).read_text(encoding="utf-8").replace(
                    "echo \"- status: \\\\`fail\\\\`\"",
                    "echo \"- status: \\\\`pass\\\\`\"",
                ).replace(
                    "echo \"ISSUE_SYNC=fail\"",
                    "echo \"ISSUE_SYNC=pass\"",
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
                "issue_mirror_checkout_failure_fallback_must_fail",
                result.stdout,
            )

    def test_issue_mirror_fails_without_failure_gate_on_checkout_summary(self) -> None:
        """Failure fallback must be gated by failure() and outcome predicate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_required_surfaces(root)
            self.ensure_issue_readme_contains_issue_required_fields(root)
            workflow = root / ".github" / "workflows" / "issue-mirror.yml"
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(
                (REPO_ROOT / ".github" / "workflows" / "issue-mirror.yml").read_text(
                    encoding="utf-8"
                ).replace(
                    "if: failure() && steps.checkout.outcome != 'success'",
                    "if: steps.checkout.outcome != 'success'",
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
                "issue_mirror_checkout_failure_summary_must_be_gated_by_failure",
                result.stdout,
            )

    def ensure_issue_readme_contains_issue_required_fields(self, root: Path) -> None:
        """Add missing durable fields to a temporary issue README fixture."""
        issues_readme = root / "issues" / "README.md"
        issues_readme_text = issues_readme.read_text(encoding="utf-8")
        if "affected_surfaces:" not in issues_readme_text:
            issues_readme_text += "\naffected_surfaces:\n  - issue-mirror-check.yml\n"
        if "edit_scope:" not in issues_readme_text:
            issues_readme_text += "edit_scope:\n  - write issue mirror workflow\n"
        issues_readme.write_text(issues_readme_text, encoding="utf-8")

    def write_template_root_pr_template(self, root: Path) -> None:
        """Write a minimal valid template-root PR template."""
        path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        source = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
        shutil.copy2(source, path)

    def copy_template_agent_canon_template(self, root: Path) -> None:
        """Project the temporary root's canonical AgentCanon PR template."""
        source = (
            root
            / "templates"
            / "documents"
            / "github"
            / "pull-request"
            / "agent_canon.md"
        )
        destination = root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        self.assertEqual(
            source.read_text(encoding="utf-8"),
            destination.read_text(encoding="utf-8"),
        )

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
            (
                root / ".github" / "scripts" / "checkout_agent_canon_submodule.sh"
            ).unlink()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "missing_referenced_agent_canon_checkout_helper", result.stdout
            )

    def test_helper_step_allows_anonymous_public_checkout(self) -> None:
        """Checkout helper steps may omit credentials for a public remote."""
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_workflow_level_credentials_fail(self) -> None:
        """Credentials for AgentCanon must stay on the checkout-helper step."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            workflow_path = root / ".github" / "workflows" / "ci.yml"
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8").replace(
                    "concurrency:\n",
                    "env:\n"
                    "  AGENT_CANON_REPO_SSH_KEY: "
                    "${{ secrets.AGENT_CANON_REPO_SSH_KEY }}\n"
                    "concurrency:\n",
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
                "agent_canon_credentials_must_be_step_local:AGENT_CANON_REPO_SSH_KEY",
                result.stdout,
            )

    def test_pr_flow_requires_typed_candidate_and_pr_identity(self) -> None:
        """The PR workflow cannot replace typed lifecycle records with prose."""
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
            self.assertIn("missing_text:SourceMainRebindReceipt", result.stdout)
            self.assertIn("missing_text:PullRequestLifecycle", result.stdout)

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

    def test_template_mode_allows_missing_parent_agent_canon_template(self) -> None:
        """Derived templates may omit parent-owned root agentcanon templates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            (root / ".gitmodules").write_text(
                '[submodule "vendor/agent-canon"]\n'
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_template_mode_ignores_arbitrary_parent_root_pr_template(self) -> None:
        """Arbitrary parent-root PR templates are ignored by template-mode checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            self.write_template_root_pr_template(root)
            self.copy_template_agent_canon_template(root)
            (root / ".gitmodules").write_text(
                '[submodule "vendor/agent-canon"]\n'
                "\tpath = vendor/agent-canon\n"
                "\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
                encoding="utf-8",
            )
            path = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "- canonical route (choose one):",
                    "- route omitted:",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_template_mode_does_not_require_standalone_root_docs(self) -> None:
        """Template roots should not require standalone-only root docs or PR templates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            self.copy_vendor_surfaces(root)
            derived_template = (
                root
                / "templates"
                / "documents"
                / "github"
                / "pull-request"
                / "agent_canon.md"
            )
            self.assertIn("changed-surface validation:", derived_template.read_text(encoding="utf-8"))
            (root / ".gitmodules").write_text(
                '[submodule "vendor/agent-canon"]\n'
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
            "    permissions:\n      contents: read\n" if job_permissions else ""
        )
        env_block = (
            "        env:\n"
            "          AGENT_CANON_REPO_TOKEN: ${{ secrets.AGENT_CANON_REPO_TOKEN }}\n"
            "          AGENT_CANON_REPO_SSH_KEY: ${{ secrets.AGENT_CANON_REPO_SSH_KEY }}\n"
            if helper_env
            else ""
        )
        helper_command = (
            "        run: bash .github/scripts/checkout_agent_canon_submodule.sh\n"
        )
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
            + helper_command
            + "      - name: Parent project quality\n"
            + "        env:\n"
            + "          AGENT_CANON_PR_PROJECT_QUALITY_OWNER: parent_ci\n"
            + "        run: make ci\n",
            encoding="utf-8",
        )

    def run_custom_workflow(self, source: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against one custom workflow and canonical fixtures."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow = root / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
            self.copy_required_surfaces(root)
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

    def copy_required_surfaces(self, root: Path) -> None:
        """Copy non-workflow surfaces required by the checker."""
        for relative in [
            ".github/AGENTS.md",
            ".github/scripts/checkout_agent_canon_submodule.sh",
            "tools/ci/checkout_agent_canon_submodule.sh",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "templates/documents/github/pull-request/agent_canon.md",
            "agents/workflows/agent-canon-pr-workflow.md",
            "issues/README.md",
            "issues/closed/AC-20260517-eval-accumulation-gaps.md",
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
        self.copy_template_agent_canon_template(root)

    def copy_vendor_surfaces(self, root: Path) -> None:
        """Copy minimal vendor surfaces required by template-mode checks."""
        for relative in [
            "README.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "templates/documents/github/pull-request/agent_canon.md",
            "agents/workflows/agent-canon-pr-workflow.md",
            ".github/workflows/agent-coordination.yml",
            ".github/workflows/agent-runtime-dashboard.yml",
            "issues/README.md",
            "issues/closed/AC-20260517-eval-accumulation-gaps.md",
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
            stale_dashboard = (
                root / ".github" / "workflows" / "agent-runtime-dashboard.yml"
            )
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
