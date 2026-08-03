"""Integration fixture for incomplete parent graph PR-gate orchestration."""

# @dependency-start
# contract test
# responsibility Verifies the real PR check routes incomplete graph builds to changed-responsibility acceptance.
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns parent PR graph orchestration
# upstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py classifies persisted incomplete graph diagnostics
# upstream design ../../documents/design/dependency-manifest-design.md owns changed-responsibility graph acceptance
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PR_CHECK = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
SELECTOR = PROJECT_ROOT / "tools" / "ci" / "agent_canon_pr_graph_selector.py"
REPO_PATHS = PROJECT_ROOT / "tools" / "lib" / "repo_paths.sh"


def run(
    root: Path,
    *args: str,
    check: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one fixture command."""
    result = subprocess.run(
        list(args),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result


def write_executable(path: Path, content: str) -> None:
    """Write one fixture executable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class AgentCanonPrGraphGateIntegrationTest(unittest.TestCase):
    """Exercise the production PR shell around a persisted incomplete graph."""

    def create_source_repo(self, root: Path) -> Path:
        """Create a minimal AgentCanon source projection used by the parent gate."""
        source = root / "agent-canon-source"
        source.mkdir()
        run(source, "git", "init", "-b", "main")
        run(source, "git", "config", "user.email", "fixture@example.invalid")
        run(source, "git", "config", "user.name", "Graph Gate Fixture")

        (source / "rust" / "agent-canon").mkdir(parents=True)
        (source / "rust" / "agent-canon" / "Cargo.toml").write_text(
            "[package]\nname='fixture'\nversion='0.0.0'\n",
            encoding="utf-8",
        )
        selector_target = source / "tools" / "ci" / SELECTOR.name
        selector_target.parent.mkdir(parents=True)
        shutil.copy2(SELECTOR, selector_target)
        (source / "tools" / "ci" / "check_agent_canon_pr.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )
        owner = source / "documents" / "design" / "dependency-manifest-design.md"
        owner.parent.mkdir(parents=True)
        owner.write_text(
            textwrap.dedent(
                """
                # Dependency Manifest Design
                <!--
                @dependency-start
                contract design
                responsibility Defines fixture dependency graph selection.
                downstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py selector
                downstream implementation ../../tools/ci/check_agent_canon_pr.sh parent gate
                @dependency-end
                -->
                """
            ).lstrip(),
            encoding="utf-8",
        )
        inventory = (
            source / "documents" / "runtime" / "runtime-profiles-and-check-matrix.json"
        )
        inventory.parent.mkdir(parents=True)
        inventory.write_text(
            json.dumps(
                {
                    "profile_classes": [
                        {
                            "id": "maintenance",
                            "strict_dependency_graph_required": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        write_executable(
            source / "tools" / "bin" / "agent-canon",
            r"""
            #!/usr/bin/env python3
            import json
            import os
            import sqlite3
            import subprocess
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            if args[:2] != ["graph", "build"]:
                raise SystemExit(0)
            root = Path(args[args.index("--root") + 1]).resolve()
            scenario = os.environ["GRAPH_GATE_FIXTURE_SCENARIO"]
            source_path = "related.py" if scenario == "reachable" else "legacy.py"
            graph_dir = root / ".agent-canon" / "knowledge-graph"
            graph_dir.mkdir(parents=True, exist_ok=True)
            database = graph_dir / "graph.sqlite"
            changed_text = (root / "changed.py").read_text(encoding="utf-8")
            has_diagnostic = "upstream" in changed_text
            snapshot_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if scenario == "stale_head":
                snapshot_head = "0" * 40
            input_fingerprint = "1" * 64
            graph_fingerprint = "2" * 64
            integration_record = {
                "schema": "agent-canon.graph.integration.v1",
                "root": str(root),
                "db_path": str(database),
                "schema_version": "fixture",
                "profile": "default",
                "source_snapshot_profile": "parent",
                "snapshot_head": snapshot_head,
                "input_fingerprint": input_fingerprint,
                "graph_fingerprint": graph_fingerprint,
                "contract_fingerprint": "fixture",
                "producer_artifacts": [],
                "runtime_evidence": None,
                "verified": True,
                "verification_code": "source-facts-readback-v1",
            }
            persisted_record = dict(integration_record)
            if scenario == "persisted_verified_int":
                persisted_record["verified"] = 1
            elif scenario == "persisted_fingerprint_int":
                persisted_record["input_fingerprint"] = 1
            elif scenario == "persisted_path_int":
                persisted_record["db_path"] = 1
            elif scenario == "persisted_profile_int":
                persisted_record["profile"] = 1
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
                connection.execute("CREATE TABLE nodes(id TEXT, layer TEXT, payload_json TEXT)")
                connection.execute(
                    "CREATE TABLE edges(layer TEXT, from_node_id TEXT, to_node_id TEXT)"
                )
                connection.execute(
                    "CREATE TABLE diagnostics(layer TEXT, rule TEXT, message TEXT, target_node_id TEXT)"
                )
                for path in ("changed.py", source_path):
                    connection.execute(
                        "INSERT INTO nodes VALUES(?, 'source', ?)",
                        (f"node:source:{path}", json.dumps({"path": path})),
                    )
                if scenario == "reachable":
                    connection.execute(
                        "INSERT INTO edges VALUES('source', ?, ?)",
                        ("node:source:changed.py", "node:source:related.py"),
                    )
                if has_diagnostic:
                    connection.execute(
                        "INSERT INTO diagnostics VALUES('source', 'target-unresolved', ?, ?)",
                        (f"{source_path}:4:missing.md", f"node:source:{source_path}"),
                    )
                for key, value in (
                    ("integration_record", json.dumps(persisted_record)),
                    ("snapshot_head", snapshot_head),
                    ("input_fingerprint", input_fingerprint),
                    ("graph_fingerprint", graph_fingerprint),
                ):
                    connection.execute("INSERT INTO metadata VALUES(?, ?)", (key, value))
            result = {
                "schema": "agent-canon.graph.build.v1",
                "command": "build",
                "status": "incomplete" if has_diagnostic else "fresh",
                "graph_status": "incomplete" if has_diagnostic else "fresh",
                "exit_code": 1 if has_diagnostic else 0,
                "root": str(root),
                "profile": "default",
                "db_path": str(database),
                "input_fingerprint": input_fingerprint,
                "graph_fingerprint": graph_fingerprint,
                "integration_record": integration_record,
                "publication": "published",
                "durability": "durable",
                "unresolved_count": 1 if has_diagnostic else 0,
                "unresolved": (
                    [
                        {
                            "code": "target-unresolved",
                            "message": f"{source_path}:4:missing.md",
                        }
                    ]
                    if has_diagnostic
                    else []
                ),
            }
            if scenario == "missing_identity":
                del result["integration_record"]
            elif scenario == "stale_fingerprint":
                result["input_fingerprint"] = "3" * 64
            print(json.dumps(result))
            raise SystemExit(1 if has_diagnostic else 0)
            """,
        )
        write_executable(
            source / "tools" / "sync_agent_canon.sh",
            """
            #!/usr/bin/env bash
            exit 0
            """,
        )
        write_executable(
            source / "tools" / "ci" / "check_agent_canon_latest.sh",
            """
            #!/usr/bin/env bash
            exit 0
            """,
        )
        write_executable(
            source / "tools" / "ci" / "run_all_checks.sh",
            """
            #!/usr/bin/env bash
            receipt="${@: -1}"
            grep -q '^graph=scoped$' "${receipt}" || exit 91
            cp "${receipt}" "${AGENT_CANON_PR_TEMP_ROOT}/consumed.receipt"
            echo 'QUICK_CI_RECEIPT_GRAPH=scoped'
            """,
        )
        write_executable(
            source / "tools" / "agent_tools" / "run_repo_dependency_review.sh",
            """
            #!/usr/bin/env bash
            echo 'REPO_DEPENDENCY_REVIEW_CALLED'
            exit 99
            """,
        )
        generic_python = "raise SystemExit(0)\n"
        for relative in (
            "tools/agent_tools/check_convention_compliance.py",
            "tools/agent_tools/check_agent_runtime_alignment.py",
            "tools/agent_tools/evaluate_codex_agent_roles.py",
            "tools/agent_tools/evaluate_skill_workflow_prompts.py",
            "tools/agent_tools/generated_artifact_guard.py",
            "tools/agent_tools/render_dependency_manifest_graph.py",
            "tools/ci/check_github_workflows.py",
            "tools/ci/container_config.py",
        ):
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(generic_python, encoding="utf-8")

        run(source, "git", "add", ".")
        run(source, "git", "commit", "-m", "fixture source")
        return source

    def create_parent_repo(self, root: Path, source: Path) -> tuple[Path, str]:
        """Create a template-like parent with one manifest-touching PR diff."""
        parent = root / "parent"
        parent.mkdir()
        run(parent, "git", "init", "-b", "main")
        run(parent, "git", "config", "user.email", "fixture@example.invalid")
        run(parent, "git", "config", "user.name", "Graph Gate Fixture")
        run(
            parent,
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(source),
            "vendor/agent-canon",
        )
        run(parent, "git", "remote", "add", "agent-canon", str(source))
        script = parent / "tools" / "ci" / PR_CHECK.name
        script.parent.mkdir(parents=True)
        shutil.copy2(PR_CHECK, script)
        repo_paths = parent / "tools" / "lib" / REPO_PATHS.name
        repo_paths.parent.mkdir(parents=True)
        shutil.copy2(REPO_PATHS, repo_paths)
        (parent / "changed.py").write_text("before\n", encoding="utf-8")
        (parent / "legacy.py").write_text("legacy\n", encoding="utf-8")
        (parent / "related.py").write_text("related\n", encoding="utf-8")
        run(parent, "git", "add", ".")
        run(parent, "git", "commit", "-m", "base")
        base = run(parent, "git", "rev-parse", "HEAD").stdout.strip()
        (parent / "changed.py").write_text(
            textwrap.dedent(
                """
                # @dependency-start
                # contract implementation
                # responsibility Changed fixture responsibility.
                # upstream design missing.md fixture dependency
                # @dependency-end
                after
                """
            ).lstrip(),
            encoding="utf-8",
        )
        run(parent, "git", "add", "changed.py")
        run(parent, "git", "commit", "-m", "change manifest")
        return parent, base

    def run_pr_check(
        self, scenario: str
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        """Run the production PR check with only unrelated gates stubbed."""
        fixture_root = Path(tempfile.mkdtemp(prefix=f"graph-gate-{scenario}-"))
        self.addCleanup(shutil.rmtree, fixture_root)
        source = self.create_source_repo(fixture_root)
        parent, base = self.create_parent_repo(fixture_root, source)
        fake_bin = fixture_root / "bin"
        write_executable(
            fake_bin / "gh",
            """
            #!/usr/bin/env bash
            exit 1
            """,
        )
        temp_root = fixture_root / "pr-check-state"
        temp_root.mkdir()
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment['PATH']}",
                "AGENT_CANON_PR_BASE_REF": base,
                "AGENT_CANON_PR_TEMP_ROOT": str(temp_root),
                "GRAPH_GATE_FIXTURE_SCENARIO": scenario,
            }
        )
        result = run(
            parent,
            "bash",
            "tools/ci/check_agent_canon_pr.sh",
            check=False,
            environment=environment,
        )
        return result, temp_root

    def test_real_pr_check_routes_incomplete_graph_to_scoped_or_blocking_selector(
        self,
    ) -> None:
        """The same incomplete build reaches selector acceptance in both outcomes."""
        valid, valid_state = self.run_pr_check("valid_binding")
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertIn('"status": "incomplete"', valid.stdout)
        self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=pass", valid.stdout)
        self.assertIn("QUICK_CI_RECEIPT_GRAPH=scoped", valid.stdout)
        self.assertNotIn("REPO_DEPENDENCY_REVIEW_CALLED", valid.stdout)
        receipt = valid_state / "consumed.receipt"
        self.assertIn("graph=scoped", receipt.read_text(encoding="utf-8"))
        report = (
            valid_state
            / "dependency-review"
            / "agent-canon-pr"
            / "changed-responsibility-acceptance.json"
        )
        valid_identity = json.loads(report.read_text(encoding="utf-8"))[
            "graph_identity"
        ]
        self.assertEqual(valid_identity["publication"], "published")
        self.assertEqual(valid_identity["durability"], "durable")
        self.assertEqual(valid_identity["profile"], "default")

        reachable, reachable_state = self.run_pr_check("reachable")
        self.assertEqual(reachable.returncode, 2, reachable.stdout + reachable.stderr)
        self.assertIn('"status": "incomplete"', reachable.stdout)
        self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=fail", reachable.stdout)
        self.assertIn(
            "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=changed_responsibility_failed",
            reachable.stdout,
        )
        self.assertNotIn("REPO_DEPENDENCY_REVIEW_CALLED", reachable.stdout)
        report = (
            reachable_state
            / "dependency-review"
            / "agent-canon-pr"
            / "changed-responsibility-acceptance.json"
        )
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["blocking_diagnostics"][0]["classification"],
            "changed_responsibility",
        )

    def test_real_pr_check_rejects_missing_or_stale_graph_identity(self) -> None:
        """Identity defects fail before scoped/full diagnostic classification."""
        scenarios = {
            "missing_identity": "graph_identity_missing",
            "stale_fingerprint": "graph_identity_mismatch",
            "stale_head": "graph_snapshot_head_stale",
            "persisted_verified_int": "graph_identity_invalid",
            "persisted_fingerprint_int": "graph_identity_invalid",
            "persisted_path_int": "graph_identity_invalid",
            "persisted_profile_int": "graph_identity_invalid",
        }
        for scenario, reason in scenarios.items():
            with self.subTest(scenario=scenario):
                result, state = self.run_pr_check(scenario)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=fail", result.stdout)
                self.assertIn(
                    f"AGENT_CANON_PR_GRAPH_ACCEPTANCE_REASON={reason}",
                    result.stdout,
                )
                self.assertIn(
                    "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=changed_responsibility_failed",
                    result.stdout,
                )
                self.assertNotIn("QUICK_CI_RECEIPT_GRAPH=scoped", result.stdout)
                self.assertNotIn("REPO_DEPENDENCY_REVIEW_CALLED", result.stdout)
                report = (
                    state
                    / "dependency-review"
                    / "agent-canon-pr"
                    / "changed-responsibility-acceptance.json"
                )
                self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
