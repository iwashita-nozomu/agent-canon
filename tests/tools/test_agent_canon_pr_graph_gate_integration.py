"""Integration fixture for incomplete parent graph PR-gate orchestration."""

# @dependency-start
# contract test
# responsibility Verifies the real PR check routes incomplete graph builds to changed-responsibility acceptance.
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns parent PR graph orchestration
# upstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py classifies persisted incomplete graph diagnostics
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py owns the fixture's parent-local child state
# upstream design ../../documents/design/dependency-manifest-design.md owns changed-responsibility graph acceptance
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PR_CHECK = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
SELECTOR = PROJECT_ROOT / "tools" / "ci" / "agent_canon_pr_graph_selector.py"
REPO_PATHS = PROJECT_ROOT / "tools" / "lib" / "repo_paths.sh"
PARENT_PATH_ENV_KEYS = {
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "PYTHONPYCACHEPREFIX",
    "TEMP",
    "TMP",
    "TMPDIR",
    "XDG_CACHE_HOME",
}


def run(
    root: Path,
    *args: str,
    check: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one fixture command."""
    if environment is None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in PARENT_PATH_ENV_KEYS
        }
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


def pending_handoff_nonces(root: Path) -> dict[str, object]:
    """Read the single-use handoff ledger without creating it."""
    state = root / ".agent-canon" / "handoff" / "nonces.json"
    if not state.exists():
        return {}
    value = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


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
        shutil.copy2(
            PROJECT_ROOT / "tools" / "__init__.py",
            source / "tools" / "__init__.py",
        )
        boundary_target = (
            source / "tools" / "agent_tools" / "parent_root_side_effects.py"
        )
        boundary_target.parent.mkdir(parents=True)
        shutil.copy2(
            PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
            boundary_target,
        )
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
            source / "tools" / "agent_tools" / "graph_fixture.py",
            r"""
            #!/usr/bin/env python3
            import json
            import os
            import sqlite3
            import subprocess
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            if args[:2] == ["graph", "status"]:
                root = Path(args[args.index("--root") + 1]).resolve()
                scenario = os.environ["GRAPH_GATE_FIXTURE_SCENARIO"]
                if scenario == "status_missing":
                    raise SystemExit(1)
                database = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
                if not database.is_file():
                    raise SystemExit(1)
                with sqlite3.connect(database) as connection:
                    metadata = dict(
                        connection.execute(
                            "SELECT key, value FROM metadata WHERE key IN "
                            "('integration_record','input_fingerprint','graph_fingerprint')"
                        ).fetchall()
                    )
                    count_rows = connection.execute(
                        "SELECT rule, COUNT(*) FROM diagnostics WHERE layer='source' "
                        "GROUP BY rule"
                    ).fetchall()
                integration_record = json.loads(metadata["integration_record"])
                counts = {
                    "unresolved_count": 0,
                    "ambiguous_count": 0,
                    "uncovered_count": 0,
                }
                for rule, count in count_rows:
                    category = {
                        "target-ambiguous": "ambiguous_count",
                        "source-uncovered": "uncovered_count",
                    }.get(rule, "unresolved_count")
                    counts[category] += count
                complete = sum(counts.values()) == 0
                status_name = "fresh" if complete else "incomplete"
                reason = None if complete else "source_completeness_incomplete"
                probe_reason = None
                status_root = str(root)
                status_input = metadata["input_fingerprint"]
                if scenario == "status_source_changed":
                    status_name = "stale"
                    reason = "source_changed"
                    probe_reason = "source_changed"
                elif scenario == "status_stale":
                    status_name = "stale"
                    reason = "producer_identity_changed"
                    probe_reason = "producer_identity_changed"
                elif scenario == "status_mismatch":
                    status_input = "3" * 64
                elif scenario == "status_typed_verified_int":
                    integration_record["verified"] = 1
                elif scenario == "status_typed_fingerprint_int":
                    integration_record["input_fingerprint"] = 1
                elif scenario == "status_typed_path_int":
                    integration_record["db_path"] = 1
                elif scenario == "status_typed_profile_int":
                    integration_record["profile"] = 1
                print(
                    json.dumps(
                        {
                            "schema": "agent-canon.graph.status.v1",
                            "command": "status",
                            "status": status_name,
                            "profile": "default",
                            "root": status_root,
                            "db_path": str(database),
                            "input_fingerprint": status_input,
                            "graph_fingerprint": metadata["graph_fingerprint"],
                            "integration_record": integration_record,
                            **counts,
                            "probe_reason": probe_reason,
                            "reason": reason,
                            "exit_code": 0 if status_name == "fresh" else 2,
                        }
                    )
                )
                raise SystemExit(0 if status_name == "fresh" else 2)
            if args[:2] != ["graph", "build"]:
                raise SystemExit(0)
            root = Path(args[args.index("--root") + 1]).resolve()
            scenario = os.environ["GRAPH_GATE_FIXTURE_SCENARIO"]
            producer_identity = json.loads(
                args[args.index("--surface-manifest-producer-identity") + 1]
            )
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
                "producer_identity": producer_identity,
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
                    "CREATE TABLE diagnostics("
                    "layer TEXT, rule TEXT, message TEXT, target_node_id TEXT, "
                    "severity TEXT, payload_json TEXT)"
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
                    producer_target = "missing.md"
                    declaration = (
                        "upstream design missing.md fixture missing target"
                    )
                    typed_payload = {
                        "schema": "agent-canon.source-diagnostic.v1",
                        "code": "target-unresolved",
                        "source": source_path,
                        "target": producer_target,
                        "declaration": declaration,
                        "source_span": {
                            "path": source_path,
                            "start_line": 4,
                            "start_column": 1,
                            "end_line": 4,
                            "end_column": 2,
                        },
                        "declaration_components": {
                            "direction": "upstream",
                            "kind": "design",
                            "target": producer_target,
                            "reason": "fixture missing target",
                        },
                    }
                    if scenario == "malformed_payload":
                        typed_payload["source_span"]["start_line"] = True
                    connection.execute(
                        "INSERT INTO diagnostics VALUES('source', ?, ?, ?, ?, ?)",
                        (
                            "target-unresolved",
                            "fixture diagnostic",
                            f"node:source:{source_path}",
                            "blocker",
                            json.dumps(typed_payload, separators=(",", ":")),
                        ),
                    )
                for key, value in (
                    ("integration_record", json.dumps(persisted_record)),
                    ("producer_identity", json.dumps(producer_identity)),
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
                "producer_identity": producer_identity,
                "integration_record": integration_record,
                "publication": "published",
                "durability": "durable",
                "unresolved_count": 1 if has_diagnostic else 0,
                "ambiguous_count": 0,
                "uncovered_count": 0,
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
            raise SystemExit(
                2 if scenario == "hard_failure" else 1 if has_diagnostic else 0
            )
            """,
        )
        (source / "tools" / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            PROJECT_ROOT / "tools" / "bin" / "agent-canon",
            source / "tools" / "bin" / "agent-canon",
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
            if [[ -n "${RUN_ALL_CHECKS_FIXTURE_LOG:-}" ]]; then
                printf '%s\n' "$*" >>"${RUN_ALL_CHECKS_FIXTURE_LOG}"
            fi
            exit "${RUN_ALL_CHECKS_FIXTURE_RC:-0}"
            """,
        )
        shutil.copy2(
            PROJECT_ROOT / "tools" / "ci" / "run_python_quality_checks.sh",
            source / "tools" / "ci" / "run_python_quality_checks.sh",
        )
        (source / "tools" / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_PATHS, source / "tools" / "lib" / REPO_PATHS.name)
        write_executable(
            source / "tools" / "agent_tools" / "run_repo_dependency_review.sh",
            """
            #!/usr/bin/env bash
            if [[ "$*" == *"--header-scan-only"* \
                && "$*" == *"--changed-path-packet"* \
                && "$*" == *"--trusted-base-sha"* ]]; then
                echo 'HEADER_SCAN_REVIEW_CALLED'
                exit 0
            fi
            if [[ "$*" == *"--changed-path-packet"* \
                && "$*" == *"--trusted-base-sha"* ]]; then
                echo 'REPO_DEPENDENCY_REVIEW_CALLED'
                exit 0
            fi
            echo 'REPO_DEPENDENCY_REVIEW_CALLED'
            exit 99
            """,
        )
        (source / "tools" / "agent_tools" / "surface_manifest.py").write_text(
            "# current producer fixture\n",
            encoding="utf-8",
        )
        manifest = source / "documents" / "runtime" / "shared-runtime-surfaces.toml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            'version = 1\nprefix = "vendor/agent-canon"\n',
            encoding="utf-8",
        )
        shutil.copy2(
            PROJECT_ROOT / "tools" / "ci" / "pydocstyle.toml",
            source / "tools" / "ci" / "pydocstyle.toml",
        )
        catalog = source / "agents" / "skills" / "catalog.yaml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text("skills: []\n", encoding="utf-8")
        shutil.copy2(
            PROJECT_ROOT / "tools" / "agent_tools" / "agent_canon_source_root.py",
            source / "tools" / "agent_tools" / "agent_canon_source_root.py",
        )
        shutil.copy2(
            PROJECT_ROOT / "tools" / "agent_tools" / "pydocstyle_review.py",
            source / "tools" / "agent_tools" / "pydocstyle_review.py",
        )
        generic_python = "raise SystemExit(0)\n"
        eval_python = textwrap.dedent(
            """
            import os
            from pathlib import Path

            log_path = os.environ.get("AGENT_CANON_EVAL_CALL_LOG")
            if log_path:
                with Path(log_path).open("a", encoding="utf-8") as stream:
                    stream.write(Path(__file__).name + "\\n")
            if Path(__file__).name == "run_accumulated_agent_evals.py":
                raise SystemExit(int(os.environ.get("AGENT_CANON_EVAL_RC", "0")))
            raise SystemExit(0)
            """
        ).lstrip()
        eval_tools = {
            "tools/agent_tools/evaluate_codex_agent_roles.py",
            "tools/agent_tools/evaluate_skill_workflow_prompts.py",
            "tools/agent_tools/run_accumulated_agent_evals.py",
            "tools/agent_tools/eval_accumulation_check.py",
        }
        for relative in (
            "tools/agent_tools/artifact_identity.py",
            "tools/agent_tools/external_artifact_binding.py",
            "tools/agent_tools/publication_integrator.py",
            "tools/agent_tools/report_artifact_checks.py",
            "tools/agent_tools/review_dispatch.py",
            "tools/agent_tools/work_log.py",
            "tests/agent_tools/test_artifact_identity.py",
            "tests/agent_tools/test_codex_hooks.py",
            "tests/agent_tools/test_external_artifact_binding.py",
            "tests/agent_tools/test_publication_integrator.py",
            "tests/agent_tools/test_review_dispatch.py",
            "tests/agent_tools/test_work_log.py",
            "tools/agent_tools/tool_drift.py",
            "tools/agent_tools/tool_catalog.py",
            "tools/agent_tools/tool_proof_coverage.py",
            "tools/agent_tools/responsibility_scope.py",
            "tools/agent_tools/import_responsibility.py",
            "tools/agent_tools/issue_sync.py",
            "tools/agent_tools/run_accumulated_agent_evals.py",
            "tools/agent_tools/eval_accumulation_check.py",
            "tools/agent_tools/check_convention_compliance.py",
            "tools/agent_tools/check_agent_runtime_alignment.py",
            "tools/agent_tools/evaluate_codex_agent_roles.py",
            "tools/agent_tools/evaluate_skill_workflow_prompts.py",
            "tools/agent_tools/generated_artifact_guard.py",
            "tools/agent_tools/smoke_test_research_perspective_pack.py",
            "tools/agent_tools/skill_tool_commands.py",
            "tools/agent_tools/render_dependency_manifest_graph.py",
            "tools/ci/check_github_workflows.py",
            "tools/ci/container_config.py",
        ):
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                eval_python if relative in eval_tools else generic_python,
                encoding="utf-8",
            )

        run(source, "git", "add", ".")
        run(source, "git", "commit", "-m", "fixture source")
        return source

    def create_parent_repo(
        self,
        root: Path,
        source: Path,
        *,
        include_manifest: bool = True,
        baseline_doc_diagnostics: int = 0,
        project_quality_error: bool = False,
    ) -> tuple[Path, str]:
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
        shutil.copy2(PROJECT_ROOT / "tools" / "__init__.py", parent / "tools")
        parent_boundary = (
            parent / "tools" / "agent_tools" / "parent_root_side_effects.py"
        )
        parent_boundary.parent.mkdir(parents=True)
        shutil.copy2(
            PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
            parent_boundary,
        )
        repo_paths = parent / "tools" / "lib" / REPO_PATHS.name
        repo_paths.parent.mkdir(parents=True)
        shutil.copy2(REPO_PATHS, repo_paths)
        (parent / "changed.py").write_text("before\n", encoding="utf-8")
        (parent / "legacy.py").write_text("legacy\n", encoding="utf-8")
        (parent / "related.py").write_text("related\n", encoding="utf-8")
        if project_quality_error:
            (parent / "existing_project_type_error.py").write_text(
                "def existing_error(value: str) -> int:\n    return value\n",
                encoding="utf-8",
            )
            (parent / "pyrightconfig.json").write_text(
                '{"include":["existing_project_type_error.py"]}\n',
                encoding="utf-8",
            )
        for relative in (
            "tests/agent_tools/test_artifact_identity.py",
            "tests/agent_tools/test_codex_hooks.py",
            "tests/agent_tools/test_external_artifact_binding.py",
            "tests/agent_tools/test_publication_integrator.py",
            "tests/agent_tools/test_review_dispatch.py",
            "tests/agent_tools/test_work_log.py",
        ):
            target = parent / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# recorder-only fixture\n", encoding="utf-8")
        for index in range(baseline_doc_diagnostics):
            (parent / f"baseline_{index}.py").write_text(
                '"""Baseline fixture module."""\n\n\n'
                f"def old_{index}():\n"
                '    """Summary.\n\n    Detail.\n    """\n'
                "    pass\n",
                encoding="utf-8",
            )
        run(parent, "git", "add", ".")
        run(parent, "git", "commit", "-m", "base")
        base = run(parent, "git", "rev-parse", "HEAD").stdout.strip()
        origin = root / "parent-origin.git"
        run(root, "git", "init", "--bare", str(origin))
        run(parent, "git", "remote", "add", "origin", str(origin))
        run(parent, "git", "push", "origin", "HEAD:refs/heads/main")
        run(
            parent,
            "git",
            "fetch",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
        )
        if include_manifest:
            changed_content = textwrap.dedent(
                """
                # @dependency-start
                # contract implementation
                # responsibility Changed fixture responsibility.
                # upstream design missing.md fixture dependency
                # @dependency-end
                after
                """
            ).lstrip()
        else:
            changed_content = "after\n"
            (parent / "new.py").write_text("new source\n", encoding="utf-8")
        (parent / "changed.py").write_text(changed_content, encoding="utf-8")
        run(
            parent,
            "git",
            "add",
            "changed.py",
            "new.py" if not include_manifest else ".",
        )
        run(parent, "git", "commit", "-m", "change manifest")
        return parent, base

    def run_pr_check(
        self, scenario: str, *, fail_ls_remote: bool = False
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        """Run the production PR check with only unrelated gates stubbed."""
        fixture_root = Path(tempfile.mkdtemp(prefix=f"graph-gate-{scenario}-"))
        self.addCleanup(shutil.rmtree, fixture_root)
        source = self.create_source_repo(fixture_root)
        parent, _base = self.create_parent_repo(
            fixture_root,
            source,
            include_manifest=scenario != "no_manifest",
            baseline_doc_diagnostics=1 if scenario == "pydoc_baseline" else 0,
            project_quality_error=scenario == "parent_project_errors",
        )
        fake_bin = fixture_root / "bin"
        fake_home = parent / ".agent-canon" / "fixture-tools"
        fake_installed = fake_home / "agent-canon" / "bin" / "agent-canon"
        fake_installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            source / "tools" / "agent_tools" / "graph_fixture.py", fake_installed
        )
        fake_installed.chmod(fake_installed.stat().st_mode | stat.S_IXUSR)
        temp_root = parent / ".agent-canon" / "pr-check-state"
        temp_root.mkdir(parents=True)
        (temp_root / "preexisting.txt").write_text("preserve\n", encoding="utf-8")
        python_call_log = temp_root / "pr-python-calls.jsonl"
        write_executable(
            fake_bin / "python-recorder",
            """
            #!/usr/bin/env python3
            import json
            import os
            import sys

            with open(os.environ["PYTHON_CALL_LOG"], "a", encoding="utf-8") as stream:
                stream.write(json.dumps(sys.argv[1:]) + "\\n")
            raise SystemExit(0)
            """,
        )
        write_executable(
            fake_bin / "cargo",
            """
            #!/usr/bin/env bash
            exit 0
            """,
        )
        write_executable(
            fake_bin / "gh",
            """
            #!/usr/bin/env bash
            exit 1
            """,
        )
        if fail_ls_remote:
            real_git = shutil.which("git")
            assert real_git is not None
            origin_url = str(fixture_root / "parent-origin.git")
            ls_remote_marker = temp_root / "origin-ls-remote-called"
            write_executable(
                fake_bin / "git",
                f"""
                #!/usr/bin/env bash
                if [[ \"$1\" == \"ls-remote\" && \"$2\" == \"{origin_url}\" ]]; then
                    touch \"{ls_remote_marker}\"
                    exit 99
                fi
                exec {real_git} \"$@\"
                """,
            )
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in PARENT_PATH_ENV_KEYS
        }
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment['PATH']}",
                "AGENT_CANON_PR_TEMP_ROOT": str(temp_root),
                "GRAPH_GATE_FIXTURE_SCENARIO": scenario,
                "PYTHON_BIN": str(fake_bin / "python-recorder"),
                "PYTHON_CALL_LOG": str(python_call_log),
                "AGENT_CANON_TOOLS_HOME": str(fake_home),
                "RUN_ALL_CHECKS_FIXTURE_LOG": str(temp_root / "run-all-checks.log"),
                "AGENT_CANON_EVAL_CALL_LOG": str(
                    temp_root / "agent-canon-eval-calls.log"
                ),
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

    def test_local_route_consumes_existing_tracking_base_without_network(self) -> None:
        """Local graph selection uses the verified origin/main tracking SHA."""
        result, state = self.run_pr_check("valid_binding", fail_ls_remote=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=pass", result.stdout)
        self.assertFalse((state / "origin-ls-remote-called").exists())
        self.assertEqual(
            (state / "preexisting.txt").read_text(encoding="utf-8"), "preserve\n"
        )
        self.assertEqual(pending_handoff_nonces(state.parents[1]), {})

    def test_real_pr_check_routes_incomplete_graph_to_scoped_or_blocking_selector(
        self,
    ) -> None:
        """The same incomplete build reaches selector acceptance in both outcomes."""
        valid, valid_state = self.run_pr_check("valid_binding")
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertIn('"status": "incomplete"', valid.stdout)
        self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=pass", valid.stdout)
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", valid.stdout)
        self.assertFalse((valid_state / "run-all-checks.log").exists())
        self.assertNotIn("REPO_DEPENDENCY_REVIEW_CALLED", valid.stdout)
        self.assertIn('"publication": "published"', valid.stdout)
        self.assertIn('"durability": "durable"', valid.stdout)
        self.assertIn('"profile": "default"', valid.stdout)

        reachable, _reachable_state = self.run_pr_check("reachable")
        self.assertEqual(reachable.returncode, 2, reachable.stdout + reachable.stderr)
        self.assertIn('"status": "incomplete"', reachable.stdout)
        self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=fail", reachable.stdout)
        self.assertIn(
            "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=changed_responsibility_failed",
            reachable.stdout,
        )
        self.assertNotIn("REPO_DEPENDENCY_REVIEW_CALLED", reachable.stdout)
        self.assertIn('"classification": "changed_responsibility"', reachable.stdout)

    def test_real_pr_check_runs_header_scan_when_graph_selection_skips(self) -> None:
        """Changed/new files without manifests still reach the trusted header scan."""
        result, _ = self.run_pr_check("no_manifest")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("HEADER_SCAN_REVIEW_CALLED", result.stdout)
        self.assertIn(
            "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=not_required", result.stdout
        )
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", result.stdout)

    def test_derived_parent_delegates_project_quality_to_parent_ci(self) -> None:
        """Derived shared gates do not execute parent project quality checks."""
        result, state = self.run_pr_check("parent_project_errors")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", result.stdout)
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY_OWNER=parent_ci", result.stdout)
        self.assertFalse((state / "run-all-checks.log").exists())
        self.assertFalse((state / "agent-canon-eval-calls.log").exists())
        project_quality = run(
            state.parents[1],
            sys.executable,
            "-m",
            "pyright",
            "existing_project_type_error.py",
            check=False,
        )
        self.assertNotEqual(project_quality.returncode, 0)

    def test_standalone_ordinary_change_keeps_shared_gate_only(self) -> None:
        """Standalone owns shared graph completeness without a quality job."""
        fixture_root = Path(tempfile.mkdtemp(prefix="graph-gate-standalone-"))
        self.addCleanup(shutil.rmtree, fixture_root)
        source = self.create_source_repo(fixture_root)
        standalone_doc = source / "standalone_docstyle.py"
        standalone_doc.write_text(
            '"""Standalone fixture module."""\n\n\n'
            "def standalone_review():\n"
            '    """Summary.\n\n    Detail.\n    """\n'
            "    pass\n",
            encoding="utf-8",
        )
        clean_doc = source / "standalone_docstyle_clean.py"
        clean_doc.write_text('"""Clean standalone fixture."""\n', encoding="utf-8")
        clean_review = run(
            source,
            "tools/bin/agent-canon",
            "pydocstyle-review",
            "--target",
            clean_doc.name,
            check=False,
        )
        self.assertEqual(clean_review.returncode, 0, clean_review.stdout + clean_review.stderr)
        self.assertEqual(pending_handoff_nonces(source), {})
        standalone_review = run(
            source,
            "tools/bin/agent-canon",
            "pydocstyle-review",
            "--target",
            "standalone_docstyle.py",
            check=False,
        )
        self.assertEqual(standalone_review.returncode, 1)
        self.assertEqual(
            (standalone_review.stdout + standalone_review.stderr).count("D213:"),
            1,
            standalone_review.stdout + standalone_review.stderr,
        )
        self.assertEqual(pending_handoff_nonces(source), {})
        shutil.copy2(PR_CHECK, source / "tools" / "ci" / PR_CHECK.name)
        repo_paths = source / "tools" / "lib" / REPO_PATHS.name
        repo_paths.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_PATHS, repo_paths)
        ordinary = source / "changed.py"
        ordinary.write_text("before\n", encoding="utf-8")
        run(
            source,
            "git",
            "add",
            "changed.py",
            "tools/ci/check_agent_canon_pr.sh",
            "tools/lib/repo_paths.sh",
        )
        run(source, "git", "commit", "-m", "standalone base")
        _base = run(source, "git", "rev-parse", "HEAD").stdout.strip()
        ordinary.write_text("after\n", encoding="utf-8")
        run(source, "git", "add", "changed.py")
        run(source, "git", "commit", "-m", "ordinary change")

        origin = fixture_root / "standalone-origin.git"
        run(fixture_root, "git", "init", "--bare", str(origin))
        run(source, "git", "remote", "add", "origin", str(origin))
        run(source, "git", "push", "origin", "HEAD~1:refs/heads/main")
        run(
            source,
            "git",
            "fetch",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
        )

        fake_bin = fixture_root / "bin"
        fake_home = source / ".agent-canon" / "fixture-tools"
        fake_installed = fake_home / "agent-canon" / "bin" / "agent-canon"
        fake_installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            source / "tools" / "agent_tools" / "graph_fixture.py", fake_installed
        )
        fake_installed.chmod(fake_installed.stat().st_mode | stat.S_IXUSR)
        write_executable(
            fake_bin / "cargo",
            """
            #!/usr/bin/env bash
            set -euo pipefail
            target_dir="${CARGO_TARGET_DIR:?}"
            mkdir -p "${target_dir}/debug"
            cp tools/bin/agent-canon "${target_dir}/debug/agent-canon"
            chmod +x "${target_dir}/debug/agent-canon"
            exit 0
            """,
        )
        write_executable(
            fake_bin / "gh",
            """
            #!/usr/bin/env bash
            exit 1
            """,
        )
        temp_root = source / ".agent-canon" / "standalone-pr-check-state"
        temp_root.mkdir(parents=True)
        (temp_root / "preexisting.txt").write_text("preserve\n", encoding="utf-8")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in PARENT_PATH_ENV_KEYS
        }
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment['PATH']}",
                "AGENT_CANON_PR_TEMP_ROOT": str(temp_root),
                "GRAPH_GATE_FIXTURE_SCENARIO": "standalone",
                "AGENT_CANON_TOOLS_HOME": str(fake_home),
                "RUN_ALL_CHECKS_FIXTURE_LOG": str(temp_root / "run-all-checks.log"),
                "AGENT_CANON_EVAL_CALL_LOG": str(
                    temp_root / "agent-canon-eval-calls.log"
                ),
                "AGENT_CANON_EVAL_RC": "0",
            }
        )
        result = run(
            source,
            "bash",
            "tools/ci/check_agent_canon_pr.sh",
            check=False,
            environment=environment,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (temp_root / "preexisting.txt").read_text(encoding="utf-8"),
            "preserve\n",
        )
        self.assertFalse(
            any(path.name.startswith("pr-check.") for path in temp_root.iterdir())
        )
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", result.stdout)
        self.assertIn(
            "AGENT_CANON_PR_PROJECT_QUALITY_OWNER=agentcanon_project_ci",
            result.stdout,
        )
        self.assertFalse((temp_root / "run-all-checks.log").exists())
        eval_calls = (
            (temp_root / "agent-canon-eval-calls.log")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertIn("run_accumulated_agent_evals.py", eval_calls)
        self.assertIn("eval_accumulation_check.py", eval_calls)
        self.assertNotIn("evaluate_codex_agent_roles.py", eval_calls)
        self.assertNotIn("evaluate_skill_workflow_prompts.py", eval_calls)
        self.assertIn(
            "AGENT_CANON_PR_DEPENDENCY_GRAPH=required reason=standalone_source",
            result.stdout,
        )
        self.assertIn("REPO_DEPENDENCY_REVIEW_CALLED", result.stdout)
        self.assertIn('"status": "fresh"', result.stdout)
        self.assertNotIn(
            "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=not_required", result.stdout
        )

        environment["AGENT_CANON_EVAL_RC"] = "17"
        failed = run(
            source,
            "bash",
            "tools/ci/check_agent_canon_pr.sh",
            check=False,
            environment=environment,
        )
        self.assertEqual(failed.returncode, 17, failed.stdout + failed.stderr)
        self.assertGreaterEqual(
            (temp_root / "agent-canon-eval-calls.log")
            .read_text(encoding="utf-8")
            .splitlines()
            .count("run_accumulated_agent_evals.py"),
            2,
        )

    def test_real_pr_check_runs_header_scan_before_hard_graph_failure(self) -> None:
        """Trusted changed paths reach header scanning even when graph build fails hard."""
        result, state = self.run_pr_check("hard_failure")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("HEADER_SCAN_REVIEW_CALLED", result.stdout)
        self.assertIn(
            "AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=graph_build_failed rc=2",
            result.stdout,
        )
        self.assertNotIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", result.stdout)
        self.assertFalse((state / "run-all-checks.log").exists())
        self.assertEqual(pending_handoff_nonces(state.parents[1]), {})

    def test_real_pr_check_reports_unchanged_production_baseline_once(self) -> None:
        """Shared correctness stays green while explicit Docstring review reports violations."""
        result, state = self.run_pr_check("pydoc_baseline")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("PYDOCSTYLE", result.stdout)
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", result.stdout)
        self.assertFalse((state / "run-all-checks.log").exists())

        parent = state.parents[1]
        target = "baseline_0.py"
        docstyle = run(
            parent,
            sys.executable,
            str(parent / "tools" / "agent_tools" / "parent_root_side_effects.py"),
            "exec-parent-bound",
            "--root",
            str(parent),
            "--source-root",
            str(parent / "vendor" / "agent-canon"),
            "--purpose",
            "pydoc-wrapper-test",
            "--issue-handoff",
            "--",
            "vendor/agent-canon/tools/bin/agent-canon",
            "pydocstyle-review",
            "--target",
            target,
            check=False,
        )
        explicit_output = docstyle.stdout + docstyle.stderr
        self.assertEqual(docstyle.returncode, 1)
        self.assertEqual(explicit_output.count("D213:"), 1, explicit_output)
        self.assertEqual(pending_handoff_nonces(parent), {})
        direct_log = state / "direct-python-calls.jsonl"
        direct_environment = os.environ.copy()
        fake_bin = state.parents[2] / "bin"
        direct_environment.update(
            {
                "PATH": f"{fake_bin}:{direct_environment['PATH']}",
                "PYTHON_BIN": str(fake_bin / "python-recorder"),
                "PYTHON_CALL_LOG": str(direct_log),
            }
        )
        quality = run(
            parent,
            "bash",
            "vendor/agent-canon/tools/ci/run_python_quality_checks.sh",
            check=False,
            environment=direct_environment,
        )
        self.assertEqual(quality.returncode, 0, quality.stdout + quality.stderr)
        self.assertIn("PYTHON_QUALITY_CHECKS=pass", quality.stdout)
        direct_calls = [
            json.loads(line)
            for line in direct_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(any(call[:2] == ["-m", "pytest"] for call in direct_calls))
        self.assertTrue(any(call[:2] == ["-m", "pyright"] for call in direct_calls))
        self.assertTrue(
            any(call[:3] == ["-m", "ruff", "check"] for call in direct_calls)
        )
        self.assertFalse(any("pydocstyle" in call for call in direct_calls))

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
            "status_missing": "graph_status_result_unavailable",
            "status_source_changed": "graph_status_source_changed",
            "status_stale": "graph_status_stale",
            "status_mismatch": "graph_status_identity_mismatch",
            "status_typed_verified_int": "graph_identity_invalid",
            "status_typed_fingerprint_int": "graph_identity_invalid",
            "status_typed_path_int": "graph_identity_invalid",
            "status_typed_profile_int": "graph_identity_invalid",
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

    def test_real_pr_check_rejects_malformed_typed_diagnostic_before_receipt(
        self,
    ) -> None:
        """Malformed typed identity fails before scoped acceptance is published."""
        result, state = self.run_pr_check("malformed_payload")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_PR_GRAPH_ACCEPTANCE=fail", result.stdout)
        self.assertIn(
            "AGENT_CANON_PR_GRAPH_ACCEPTANCE_REASON=graph_diagnostic_invalid",
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
