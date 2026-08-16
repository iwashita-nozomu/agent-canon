# @dependency-start
# contract test
# responsibility Tests test update agent canon behavior.
# upstream design ../../documents/agent-canon/agent-canon-update-route.md owns update materialization acceptance
# upstream design ../../tools/README.md validated automation surface
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml typed retired descendant paths
# downstream implementation ../../test/testrunner.sh runs this migration regression from the source Git root
# @dependency-end

"""Tests for the derived-repo agent-canon update wrapper."""

from __future__ import annotations

import hashlib
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tools.agent_tools.fixture_spawn import record_environment

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib


def resolve_repo_root() -> Path:
    """Return the repository root for both vendored and mirrored test paths."""
    cwd_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if cwd_root:
        candidate = Path(cwd_root)
        if (
            (candidate / "ROOT_AGENTS.md").is_file()
            and (candidate / "tools" / "update_agent_canon.sh").is_file()
        ):
            return candidate
        if (candidate / "vendor" / "agent-canon").exists():
            return candidate

    git_root = None
    for candidate in Path(__file__).absolute().parents:
        if (candidate / ".git").exists():
            git_root = candidate
            if (candidate / "vendor" / "agent-canon").exists():
                return candidate
            if (
                (candidate / "ROOT_AGENTS.md").is_file()
                and (candidate / "tools" / "update_agent_canon.sh").is_file()
            ):
                return candidate
    if git_root is not None:
        raise unittest.SkipTest("derived-repo agent-canon wrapper tests require vendor/agent-canon")
    raise RuntimeError("git repository root not found")


REPO_ROOT = resolve_repo_root()
AGENT_CANON_IS_SUBMODULE = bool(
    subprocess.run(
        [
            "git",
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.vendor/agent-canon.path",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
AGENT_CANON_IS_STANDALONE = not (REPO_ROOT / "vendor" / "agent-canon").exists()
AGENT_CANON_SOURCE_ROOT = (
    REPO_ROOT / "vendor" / "agent-canon"
    if AGENT_CANON_IS_SUBMODULE
    else REPO_ROOT
)
sys.path.insert(0, str(AGENT_CANON_SOURCE_ROOT / "tools" / "agent_tools"))
sys.path.insert(0, str(AGENT_CANON_SOURCE_ROOT / "tools" / "ci"))

from check_agent_canon_pr import (  # noqa: E402
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)
from github_publish import materialize_pr_identity_gate  # noqa: E402
from update_lifecycle_contract import (  # noqa: E402
    SourceMainReadbackIdentity,
    materialize_dependency_frontier,
    materialize_gate_verdict,
    materialize_publication_readback_receipt,
    materialize_queue_receipt,
    materialize_source_main_rebind_receipt,
    materialize_source_projection_packet,
    pull_request_branch_table,
    validate_dependency_frontier_transition,
)

OVERLAY_EXCLUDED_NAMES = {".git", ".pytest_cache", ".ruff_cache", "reports"}
SUBMODULE_GITFILE = Path("vendor") / "agent-canon" / ".git"
COMMIT_REQUEST_EVIDENCE = "evidence:" + ("0" * 64)


def authorized_test_env() -> dict[str, str]:
    """Return the explicit authority and provenance inputs for mutating routes."""
    env = dict(os.environ)
    env.update(
        {
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
            "AGENT_CANON_BRANCH_WORKTREE_REASON": "test-approved-update",
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "test-approved-update",
            "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": COMMIT_REQUEST_EVIDENCE,
        }
    )
    return env


class GitAuthorityPredicateTest(unittest.TestCase):
    """Exercise the shared mode-aware authority matrix without side effects."""

    def run_predicate(self, mode: str, authority: str) -> subprocess.CompletedProcess[str]:
        """Run the shared shell predicate with one authority profile."""
        env = dict(os.environ)
        for name in (
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY",
            "AGENT_CANON_BRANCH_WORKTREE_REASON",
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY",
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        ):
            env.pop(name, None)
        if authority in {"creation", "both"}:
            env.update(
                {
                    "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
                    "AGENT_CANON_BRANCH_WORKTREE_REASON": "test-creation",
                }
            )
        elif authority == "destructive_wrong_branch":
            env.update(
                {
                    "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "wrong",
                    "AGENT_CANON_BRANCH_WORKTREE_REASON": "irrelevant-to-update",
                }
            )
        if authority in {"destructive", "destructive_wrong_branch", "both"}:
            env.update(
                {
                    "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
                    "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "test-destructive",
                }
            )
        command = [
            "bash",
            "-c",
            "source tools/lib/git_authority.sh; "
            "git_authority_check_protected_git_authority \"$1\"",
            "git-authority-test",
            mode,
        ]
        with record_environment(cwd=REPO_ROOT, base_env=env) as signed_env:
            return subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=signed_env,
            )

    def test_mode_aware_authority_matrix(self) -> None:
        """Update modes are destructive-only; creation and force routes are scoped."""
        expected = {
            ("latest", "destructive"): True,
            ("latest", "destructive_wrong_branch"): True,
            ("latest", "both"): True,
            ("latest", "creation"): False,
            ("submodule-add", "creation"): True,
            ("submodule-add", "both"): True,
            ("submodule-add", "destructive"): False,
            ("force-create", "both"): True,
            ("force-create", "creation"): False,
            ("force-create", "destructive"): False,
        }
        for (mode, authority), should_pass in expected.items():
            with self.subTest(mode=mode, authority=authority):
                result = self.run_predicate(mode, authority)
                self.assertEqual(result.returncode == 0, should_pass, result.stderr)

    def test_public_diagnostics_match_mode_requirements(self) -> None:
        """Wrapper failures expose only the guard markers required by each mode."""
        env = dict(os.environ)
        for name in (
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY",
            "AGENT_CANON_BRANCH_WORKTREE_REASON",
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY",
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        ):
            env.pop(name, None)
        update = subprocess.run(
            ["bash", "tools/update_agent_canon.sh", "latest"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(update.returncode, 0)
        self.assertIn("DESTRUCTIVE_GIT_GUARD=block", update.stdout)
        self.assertNotIn("BRANCH_WORKTREE_CREATION_GUARD=block", update.stdout)

        creation = subprocess.run(
            ["bash", "tools/sync_agent_canon.sh", "submodule-add"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(creation.returncode, 0)
        self.assertIn("BRANCH_WORKTREE_CREATION_GUARD=block", creation.stdout)
        self.assertNotIn("DESTRUCTIVE_GIT_GUARD=block", creation.stdout)

def git_global_safe_directory_snapshot() -> tuple[int, tuple[str, ...]]:
    """Capture global safe.directory lines and git exit status."""
    result = subprocess.run(
        ["git", "config", "--global", "--get-all", "safe.directory"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines = tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    )
    return result.returncode, lines


def git_config_sentinel_state(path: Path) -> tuple[bytes, str]:
    """Capture bytes and hash for an explicit global config sentinel."""
    payload = path.read_bytes() if path.exists() else b""
    return payload, hashlib.sha256(payload).hexdigest()


def run_fresh_clone_check(
    check_script: str,
    root: Path,
    env: dict[str, str],
    signal_name: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run fresh-clone check once, optionally signaling the process once."""
    with record_environment(cwd=root, base_env=env) as signed_env:
        if signal_name is None:
            return subprocess.run(
                ["bash", check_script],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
                env=signed_env,
            )

        process = subprocess.Popen(
            ["bash", check_script],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=signed_env,
            start_new_session=True,
        )
        stdout_prefix: list[str] = []
        start = time.time()
        while time.time() - start < 5 and process.poll() is None:
            readable, _, _ = select.select([process.stdout], [], [], 0.02)
            if not readable:
                continue
            line = process.stdout.readline()
            if not line:
                break
            stdout_prefix.append(line)
            if line.startswith("fresh-clone source:"):
                break
        os.killpg(
            process.pid,
            {"INT": signal.SIGINT, "TERM": signal.SIGTERM, "HUP": signal.SIGHUP}[signal_name],
        )
        stdout, stderr = process.communicate(timeout=120)
        return subprocess.CompletedProcess(
            process.args,
            process.returncode,
            "".join(stdout_prefix) + stdout,
            stderr,
        )


class SharedSurfaceRetirementContractTest(unittest.TestCase):
    """Keep the retired descendant inventory and source reader boundary typed."""

    EXPECTED_NOTE_DESCENDANTS = frozenset(
        {
            "notes/branches/BRANCH_NOTE_TEMPLATE.md",
            "notes/branches/README.md",
            "notes/experiments/README.md",
            "notes/experiments/REPORT_TEMPLATE.md",
            "notes/experiments/results/README.md",
            "notes/failures/FAILURE_NOTE_TEMPLATE.md",
            "notes/failures/README.md",
            "notes/github-mirror-procedure.md",
            "notes/guardrails/README.md",
            "notes/guardrails/engineering_avoidances.md",
            "notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md",
            "notes/knowledge/README.md",
            "notes/knowledge/benchmark_levels_analysis.md",
            "notes/knowledge/benchmark_vs_experiment.md",
            "notes/knowledge/coding_decision_methods.md",
            "notes/knowledge/environment_setup.md",
            "notes/knowledge/experiment_directory_planning.md",
            "notes/knowledge/experiment_operations.md",
            "notes/knowledge/git_mirroring.md",
            "notes/knowledge/literature_intake.md",
            "notes/knowledge/path_resolution.md",
            "notes/knowledge/pyright_operations.md",
            "notes/themes/README.md",
            "notes/themes/THEME_NOTE_TEMPLATE.md",
            "notes/themes/from_another_agent.md",
            "notes/worktrees/README.md",
            "notes/worktrees/WORKTREE_LOG_TEMPLATE.md",
        }
    )

    def retired_paths(self) -> frozenset[str]:
        """Read the source manifest's removed descendant paths."""
        manifest_path = AGENT_CANON_SOURCE_ROOT / "documents/runtime/shared-runtime-surfaces.toml"
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        paths: set[str] = set()
        for group in manifest.get("group", []):
            if group.get("mode") == "removed_legacy":
                paths.update(group.get("paths", []))
        return frozenset(paths)

    def test_removed_descendant_inventory_preserves_source_ownership(self) -> None:
        """The manifest retires exactly 56 test/fixture and 27 note descendants."""
        retired = self.retired_paths()
        tests = frozenset(
            path
            for path in retired
            if path.startswith("tests/agent_tools/")
            or path.startswith("tests/tools/")
            or path == "tests/fixtures/python_algorithm_contract"
        )
        notes = frozenset(path for path in retired if path.startswith("notes/"))

        self.assertEqual(len(tests), 56)
        self.assertEqual(sum(path.startswith("tests/agent_tools/") for path in tests), 42)
        self.assertEqual(sum(path.startswith("tests/tools/") for path in tests), 13)
        self.assertIn("tests/fixtures/python_algorithm_contract", tests)
        self.assertEqual(notes, self.EXPECTED_NOTE_DESCENDANTS)
        self.assertNotIn("notes/README.md", notes)

    def test_source_reader_contract_keeps_notes_and_public_tools_non_projected(self) -> None:
        """Reader docs state source-note ownership, preservation, and no regeneration."""
        surface_doc = (
            AGENT_CANON_SOURCE_ROOT / "documents/runtime/SHARED_RUNTIME_SURFACES.md"
        ).read_text(encoding="utf-8")
        container_doc = (AGENT_CANON_SOURCE_ROOT / "CONTAINER_OPERATIONS.md").read_text(
            encoding="utf-8"
        )
        for document in (surface_doc, container_doc):
            document = " ".join(document.split())
            self.assertIn("notes/README.md", document)
            self.assertIn("never regenerated", document)
        self.assertIn("tools/agent-canon", surface_doc)
        self.assertIn("tools/agent-canon", container_doc)


class CommitProvenanceStaticContractTest(unittest.TestCase):
    """Check that the representative fresh-clone caller forwards provenance."""

    def test_nested_update_requires_exact_parent_handoff(self) -> None:
        """A nested update keeps the outer parent only through an exact handoff."""
        with tempfile.TemporaryDirectory(prefix="nested-update-parent-") as sandbox:
            root = Path(sandbox)
            outer = root / "parent"
            nested = outer / "workspace" / "agent-canon"
            subprocess.run(["git", "init", "-q", "-b", "main", str(outer)], check=True)
            for relative in (
                "tools/update_agent_canon.sh",
                "tools/sync_agent_canon.sh",
                "tools/rebuild_agent_tools.sh",
                "tools/lib/repo_paths.sh",
                "tools/lib/update_materialization.sh",
                "tools/lib/git_authority.sh",
                "tools/lib/agent_canon_source_identity.sh",
                "tools/agent_tools/parent_root_side_effects.py",
            ):
                source = AGENT_CANON_SOURCE_ROOT / relative
                target = nested / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            subprocess.run(["git", "init", "-q", "-b", "main", str(nested)], check=True)
            subprocess.run(["git", "-C", str(nested), "add", "-A"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(nested), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "-q", "-m", "fixture",
                ],
                check=True,
            )
            home = root / "unchanged-home"
            home.mkdir()
            outside = root / "outside-sentinel"
            env = os.environ.copy()
            for name in tuple(env):
                if name.startswith("AGENT_CANON_") or name in {
                    "TMPDIR", "TEMP", "TMP", "XDG_CACHE_HOME",
                    "PYTHONPYCACHEPREFIX", "CARGO_HOME", "CARGO_TARGET_DIR",
                }:
                    env.pop(name)
            env["HOME"] = str(home)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["AGENT_CANON_PARENT_ROOT"] = str(outer)

            rejected = subprocess.run(
                ["bash", str(nested / "tools" / "update_agent_canon.sh"), "status"],
                cwd=nested,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
            self.assertIn(
                "PARENT_ROOT_SIDE_EFFECT_ERROR=handoff_invalid: legacy_authority_forbidden",
                rejected.stderr,
            )
            self.assertFalse((outer / ".agent-canon").exists())
            self.assertFalse((nested / ".agent-canon").exists())

            rebuild_rejected = subprocess.run(
                ["bash", str(nested / "tools" / "rebuild_agent_tools.sh")],
                cwd=nested,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(rebuild_rejected.returncode, 2, rebuild_rejected.stderr)
            self.assertIn(
                "PARENT_ROOT_SIDE_EFFECT_ERROR=handoff_invalid: legacy_authority_forbidden",
                rebuild_rejected.stderr,
            )
            self.assertFalse((outer / ".agent-canon").exists())
            self.assertFalse((nested / ".agent-canon").exists())

            sync_rejected = subprocess.run(
                ["bash", str(nested / "tools" / "sync_agent_canon.sh"), "status"],
                cwd=nested,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(sync_rejected.returncode, 2, sync_rejected.stderr)
            self.assertIn(
                "PARENT_ROOT_SIDE_EFFECT_ERROR=handoff_invalid: legacy_authority_forbidden",
                sync_rejected.stderr,
            )
            self.assertFalse((outer / ".agent-canon").exists())
            self.assertFalse((nested / ".agent-canon").exists())

            env.pop("AGENT_CANON_PARENT_ROOT")
            accepted = subprocess.run(
                [
                    sys.executable,
                    str(nested / "tools" / "agent_tools" / "parent_root_side_effects.py"),
                    "exec-parent-bound",
                    "--root", str(outer),
                    "--source-root", str(nested),
                    "--purpose", "agent-canon-update-script",
                    "--issue-handoff",
                    "--",
                    "bash", str(nested / "tools" / "update_agent_canon.sh"), "status",
                ],
                cwd=nested,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(
                accepted.returncode,
                0,
                f"stdout={accepted.stdout!r} stderr={accepted.stderr!r}",
            )
            self.assertIn("agent_canon_source_mode=standalone_source", accepted.stdout)

            sync_accepted = subprocess.run(
                [
                    sys.executable,
                    str(nested / "tools" / "agent_tools" / "parent_root_side_effects.py"),
                    "exec-parent-bound",
                    "--root", str(outer),
                    "--source-root", str(nested),
                    "--purpose", "agent-canon-sync-script",
                    "--issue-handoff",
                    "--",
                    "bash", str(nested / "tools" / "sync_agent_canon.sh"), "status",
                ],
                cwd=nested,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(
                sync_accepted.returncode,
                0,
                f"stdout={sync_accepted.stdout!r} stderr={sync_accepted.stderr!r}",
            )
            self.assertIn(f"repo_root={nested}", sync_accepted.stdout)

            rebuild_accepted = subprocess.run(
                [
                    sys.executable,
                    str(nested / "tools" / "agent_tools" / "parent_root_side_effects.py"),
                    "exec-parent-bound",
                    "--root", str(outer),
                    "--source-root", str(nested),
                    "--purpose", "agent-canon-rebuild-script",
                    "--issue-handoff",
                    "--",
                    "bash", str(nested / "tools" / "rebuild_agent_tools.sh"),
                ],
                cwd=nested,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(
                rebuild_accepted.returncode,
                0,
                f"stdout={rebuild_accepted.stdout!r} stderr={rebuild_accepted.stderr!r}",
            )
            self.assertIn(
                "AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_rust_manifest",
                rebuild_accepted.stdout,
            )

            nested_session_root = (
                nested / ".agent-canon" / "runtime" / "side-effect-sessions-v2"
            )
            if nested_session_root.exists():
                for record_path in sorted(nested_session_root.glob("*/record.json")):
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    self.assertEqual(record["parent_root_realpath"], str(nested.resolve()))
                    self.assertEqual(record["role"], "supervisor")
            # A nested .agent-canon containing v2 records is owned by the
            # nested CWD; its existence is not accepted-command completion
            # evidence. The observable completion evidence is status/output,
            # cleanup, and unchanged external state below.
            legacy_update_tmp = outer / ".agent-canon" / "tmp" / "update"
            self.assertFalse(legacy_update_tmp.exists())
            legacy_nonce = outer / ".agent-canon" / "handoff" / "nonces.json"
            self.assertFalse(legacy_nonce.exists())
            self.assertEqual(env["HOME"], str(home))
            self.assertFalse(outside.exists())

    def test_fresh_clone_route_sets_commit_request_evidence(self) -> None:
        """Fresh-clone update calls must pass the canonical workflow digest."""
        script = (AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_fresh_clone.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'AGENT_CANON_COMMIT_REQUEST_EVIDENCE="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE}"',
            script,
        )
        self.assertIn(
            "AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH=vendor/agent-canon/agents/workflows/agent-canon-pr-workflow.md",
            script,
        )
        self.assertIn(
            "AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH=agents/workflows/agent-canon-pr-workflow.md",
            script,
        )
        self.assertIn(
            'COMMIT_REQUEST_EVIDENCE_DIGEST="$(sha256sum "${AGENT_CANON_COMMIT_REQUEST_WORKFLOW_PATH}"',
            script,
        )
        self.assertNotIn('sync_agent_canon.sh" check || true', script)
        self.assertIn('make -C "${CLONE_DIR}" agent-canon-check', script)
        self.assertNotIn('make -C "${CLONE_DIR}" agent-checks', script)
        sync_check = (
            '\nrun_parent_bound_sync \\\n'
            '  "${CLONE_SOURCE_ROOT}" \\\n'
            '  "${CLONE_TOOLS_ROOT}/sync_agent_canon.sh" \\\n'
            "  check"
        )
        self.assertIn(sync_check, script)
        self.assertLess(
            script.index('attach_submodule_main_to_staged_pin "vendor/agent-canon"'),
            script.index(sync_check),
        )
        sync_script = (AGENT_CANON_SOURCE_ROOT / "tools" / "sync_agent_canon.sh").read_text(
            encoding="utf-8"
        )
        start = sync_script.index("cmd_ensure_latest() {")
        ensure_latest = sync_script[start : sync_script.index("\ncmd_push() {", start)]
        ordered_update = (
            '"refs/heads/$branch:refs/remotes/origin/$branch"',
            '"refs/remotes/origin/$branch^{commit}"',
            '"$worktree_commit" "$remote_sha" "$branch" "$materialization_result_tree"',
            'git -C "$ROOT_DIR" add -A -- "$PREFIX"',
        )
        for before, after in zip(ordered_update, ordered_update[1:]):
            self.assertLess(ensure_latest.index(before), ensure_latest.index(after))
        self.assertNotIn("switch -C", ensure_latest)

    def test_fresh_clone_accepts_materializable_local_branch_state(self) -> None:
        """Fresh-clone acceptance should admit collision-free local branch state."""
        script = (AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_fresh_clone.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("assert_update_plan_acceptance", script)
        self.assertIn("deferred_branch_pr|subtree_pull|submodule_update", script)
        self.assertIn("agent_canon_plan_requires_clean=no", script)
        self.assertIn("agent_canon_plan_unresolved_merge_conflict=no", script)
        self.assertIn("agent_canon_plan_merge_conflict=no", script)
        self.assertIn("agent_canon_plan_merge_conflict_type=none", script)
        self.assertIn("agent_canon_plan_materialization_collision=no", script)
        self.assertIn(
            "materialization_merge_conflict_or_unpreservable_materialization_collision",
            script,
        )

    def test_fresh_clone_rebinds_tracking_ref_with_the_fixture_remote(self) -> None:
        """The disposable remote replacement must replace its stale tracking identity."""
        script = (AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_fresh_clone.sh").read_text(
            encoding="utf-8"
        )
        remote_rebind = (
            'git -C vendor/agent-canon fetch --force origin \\\n'
            '    "refs/heads/main:refs/remotes/origin/main"'
        )
        self.assertIn(remote_rebind, script)
        self.assertLess(
            script.index(remote_rebind),
            script.index("materialize_current_lifecycle_projection"),
        )

    def test_fresh_clone_routes_parent_mode_before_compose_assertions(self) -> None:
        """Parent projection mode is decided before compose generation checks."""
        script = (
            AGENT_CANON_SOURCE_ROOT
            / "tools"
            / "ci"
            / "check_fresh_clone.sh"
        ).read_text(encoding="utf-8")
        parse_position = script.index(
            "python3 -m json.tool .devcontainer/devcontainer.json"
        )
        mode_position = script.index("parent_projection_mode=false")
        standalone_branch_position = script.index(
            'if [ "$parent_projection_mode" = false ]; then'
        )
        compose_call_position = script.index(
            'bash "${runtime_compose_generator}"',
            standalone_branch_position,
        )
        parent_branch_position = script.index(
            'if [ "$parent_projection_mode" = true ]; then'
        )
        self.assertLess(parse_position, mode_position)
        self.assertLess(mode_position, standalone_branch_position)
        self.assertLess(standalone_branch_position, compose_call_position)
        self.assertLess(standalone_branch_position, parent_branch_position)
        self.assertLess(compose_call_position, parent_branch_position)
        self.assertIn("bash \"${runtime_compose_generator}\"", script)
        self.assertIn("AGENT_CANON_DOCKER_COMPOSE_OUTPUT", script)

    def test_merge_invocations_disable_configured_autostash(self) -> None:
        """Every AgentCanon update merge must refuse config-driven autostash."""
        for relative_path in ("tools/sync_agent_canon.sh", "tools/update_agent_canon.sh"):
            script = (AGENT_CANON_SOURCE_ROOT / relative_path).read_text(encoding="utf-8")
            merge_lines = [
                line
                for line in script.splitlines()
                if "git -C" in line and " merge " in line and "merge-base" not in line
            ]
            self.assertTrue(merge_lines, relative_path)
            for line in merge_lines:
                self.assertIn("--no-autostash", line, (relative_path, line))

    def test_clone_docs_route_all_repository_kinds_through_generic_lifecycle(
        self,
    ) -> None:
        """Clone mechanics stay generic while repository policies decorate afterward."""
        orchestration = (
            AGENT_CANON_SOURCE_ROOT / "agents" / "skills" / "agent-orchestration.md"
        ).read_text(encoding="utf-8")
        waterfall = (
            AGENT_CANON_SOURCE_ROOT
            / "agents"
            / "workflows"
            / "implementation-waterfall-workflow.md"
        ).read_text(encoding="utf-8")
        dependency = (
            AGENT_CANON_SOURCE_ROOT / "documents" / "tools" / "dependency_module_change.md"
        ).read_text(encoding="utf-8")
        self.assertIn("repository-topic-clone", orchestration)
        self.assertIn("repository kind は prepare 後の policy decorator", orchestration)
        self.assertIn("repository-topic-clone", waterfall)
        self.assertIn("repository kind は clone 後の decorator", waterfall)
        self.assertIn("generic `repository_topic_clone.py`", dependency)
        self.assertIn("fresh/continuation の別 route は持ちません", dependency)
        for text in (orchestration, waterfall, dependency):
            self.assertNotIn("--placement workspace", text)
            self.assertNotIn("workspace-continuation", text)

        latest_check = (
            AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("submodule_materialization_collision)", latest_check)
        self.assertIn("exact_materialization_merge_conflict_or_collision_predicate", latest_check)
        self.assertNotIn("--placement workspace", latest_check)
        self.assertNotIn("after cleaning the worktree", latest_check)

    def test_collision_emitter_blocks_current_checkout_without_clone_route(self) -> None:
        """Typed collision/conflict emission never selects the workspace clone route."""
        script = (AGENT_CANON_SOURCE_ROOT / "tools" / "update_agent_canon.sh").read_text(
            encoding="utf-8"
        )
        start = script.index("emit_agentcanon_conflict_workflow_route() {")
        end = script.index("\nroute_requires_agent_workflow()", start)
        emitter = script[start:end]
        blocked_emission = emitter[: emitter.index(
            '\n  echo "AGENT_CANON_LATEST_TOOL_RESULT=agent_workflow_required"'
        )]
        self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=blocked_current_checkout", emitter)
        self.assertIn("AGENT_CANON_LATEST_BLOCK_SCOPE=current_checkout", emitter)
        self.assertNotIn("NEXT_ACTION=prepare_topic_workspace_source_clone", blocked_emission)
        self.assertNotIn("AGENT_CANON_LATEST_DEPENDENCY_ROUTE=", blocked_emission)

    def test_fresh_clone_cleanup_contract_with_success_failure_signal(self) -> None:
        """Fresh-clone contract enforces scoped temp lifecycle across paths and signals."""
        with tempfile.TemporaryDirectory(prefix="fc-contract-") as sandbox:
            temp_root = Path(sandbox)
            fixture_root = next(
                (
                    candidate
                    for candidate in (REPO_ROOT, *REPO_ROOT.parents)
                    if (candidate / "vendor" / "agent-canon").exists()
                ),
                REPO_ROOT,
            )
            submodule_remote = temp_root / "agent-canon-upstream.git"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--bare",
                    "--no-local",
                    str(AGENT_CANON_SOURCE_ROOT),
                    str(submodule_remote),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            source_head = subprocess.run(
                ["git", "-C", str(AGENT_CANON_SOURCE_ROOT), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "--git-dir", str(submodule_remote), "update-ref", "refs/heads/main", source_head],
                check=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(submodule_remote), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
            )
            script_root = Path(temp_root / "check-source")
            subprocess.run(
                ["git", "clone", "--no-local", str(fixture_root), str(script_root)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(script_root), "config", "user.name", "Fresh Clone Fixture"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(script_root), "config", "user.email", "fresh-clone@example.invalid"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root),
                    "config",
                    "-f",
                    ".gitmodules",
                    "submodule.vendor/agent-canon.url",
                    str(submodule_remote),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root),
                    "config",
                    "-f",
                    ".gitmodules",
                    "submodule.vendor/agent-canon.path",
                    "vendor/agent-canon",
                ],
                check=True,
            )
            for key, expected in (
                ("submodule.vendor/agent-canon.path", "vendor/agent-canon"),
                ("submodule.vendor/agent-canon.url", str(submodule_remote)),
            ):
                readback = subprocess.run(
                    ["git", "-C", str(script_root), "config", "-f", ".gitmodules", "--get", key],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                self.assertEqual(readback, expected)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root),
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"160000,{source_head},vendor/agent-canon",
                ],
                check=True,
            )
            (script_root / "Makefile").write_text(
                ".PHONY: agent-canon-check\nagent-canon-check:\n\t@:\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "-C", str(script_root), "add", ".gitmodules", "Makefile"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(script_root), "commit", "-m", "fixture parent projection"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root),
                    "-c",
                    "protocol.file.allow=always",
                    "submodule",
                    "update",
                    "--init",
                    "--recursive",
                    "vendor/agent-canon",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            index_entry = subprocess.run(
                ["git", "-C", str(script_root), "ls-files", "--stage", "--", "vendor/agent-canon"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip().split()
            self.assertEqual(index_entry[0], "160000")
            self.assertEqual(index_entry[1], source_head)
            initialized_head = subprocess.run(
                ["git", "-C", str(script_root / "vendor/agent-canon"), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(initialized_head, source_head)
            initialized_status = subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root / "vendor/agent-canon"),
                    "status",
                    "--short",
                    "--untracked-files=all",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(initialized_status, "")
            for relative in (
                "tools/update_agent_canon.sh",
                "tools/sync_agent_canon.sh",
                "tools/rebuild_agent_tools.sh",
                "tools/agent_tools/agent_canon_source_root.py",
                "tools/agent_tools/parent_root_side_effects.py",
            ):
                shutil.copy2(
                    AGENT_CANON_SOURCE_ROOT / relative,
                    script_root / "vendor" / "agent-canon" / relative,
                )
            (script_root / "vendor" / "agent-canon" / "fresh-clone-fixture-delta.txt").write_text(
                "fresh-clone-fixture-delta-v1\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "-C", str(script_root / "vendor" / "agent-canon"), "add", "-A"],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(script_root / "vendor" / "agent-canon"),
                    "-c", "user.name=Fresh Clone Fixture", "-c",
                    "user.email=fresh-clone@example.invalid", "commit", "-q",
                    "-m", "fixture current parent-bound owners",
                ],
                check=True,
            )
            source_head = subprocess.run(
                ["git", "-C", str(script_root / "vendor" / "agent-canon"), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                [
                    "git", "-C", str(script_root / "vendor" / "agent-canon"),
                    "push", "origin", "HEAD:refs/heads/main",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(script_root), "update-index", "--add", "--cacheinfo",
                    f"160000,{source_head},vendor/agent-canon",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(script_root), "commit", "-q", "-m", "fixture current AgentCanon pin"],
                check=True,
            )
            if (script_root / "tools").exists() or (script_root / "tools").is_symlink():
                subprocess.run(
                    ["git", "rm", "-r", "--", "tools"],
                    cwd=script_root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "fixture remove legacy tools view"],
                    cwd=script_root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            surface_manifest = (
                script_root
                / "vendor"
                / "agent-canon"
                / "tools"
                / "agent_tools"
                / "surface_manifest.py"
            )
            absent_paths = subprocess.run(
                [
                    "python3",
                    str(surface_manifest),
                    "--root",
                    str(script_root),
                    "--prefix",
                    "vendor/agent-canon",
                    "--manifest",
                    str(
                        script_root
                        / "vendor"
                        / "agent-canon"
                        / "documents"
                        / "runtime"
                        / "shared-runtime-surfaces.toml"
                    ),
                    "root-absent-paths",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            required_paths: set[str] = set()
            for manifest_command in ("link-specs", "copy-specs", "regular-specs"):
                required_paths.update(
                    line.split(":", 1)[0]
                    for line in subprocess.run(
                        [
                            "python3",
                            str(surface_manifest),
                            "--root",
                            str(script_root),
                            "--prefix",
                            "vendor/agent-canon",
                            "--manifest",
                            str(
                                script_root
                                / "vendor"
                                / "agent-canon"
                                / "documents"
                                / "runtime"
                                / "shared-runtime-surfaces.toml"
                            ),
                            manifest_command,
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.splitlines()
                    if line
                )
            for relative_path in absent_paths:
                if any(
                    relative_path == required
                    or required.startswith(relative_path + "/")
                    for required in required_paths
                ):
                    continue
                candidate = script_root / relative_path
                if candidate.exists() or candidate.is_symlink():
                    subprocess.run(
                        ["git", "rm", "-r", "--ignore-unmatch", "--", relative_path],
                        cwd=script_root,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
            staged_fixture_cleanup = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=script_root,
                check=False,
            )
            if staged_fixture_cleanup.returncode == 1:
                subprocess.run(
                    ["git", "commit", "-m", "fixture remove retired root views"],
                    cwd=script_root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            fixture_tools = script_root / ".state" / "fixture-tools"
            fixture_tools.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "sync_agent_canon.sh",
                fixture_tools / "sync_agent_canon.sh",
            )
            shutil.copytree(
                AGENT_CANON_SOURCE_ROOT / "tools" / "lib",
                fixture_tools / "lib",
                dirs_exist_ok=True,
            )
            fixture_agent_tools = fixture_tools / "agent_tools"
            fixture_agent_tools.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
                fixture_agent_tools / "parent_root_side_effects.py",
            )
            workflow_path = (
                script_root
                / "vendor"
                / "agent-canon"
                / "agents"
                / "workflows"
                / "agent-canon-pr-workflow.md"
            )
            fixture_env = authorized_test_env()
            fixture_env["AGENT_CANON_COMMIT_REQUEST_EVIDENCE"] = (
                "evidence:" + hashlib.sha256(workflow_path.read_bytes()).hexdigest()
            )
            fixture_env["AGENT_CANON_PREFIX"] = "vendor/agent-canon"
            fixture_env["AGENT_CANON_PARENT_TMPDIR"] = str(
                script_root / ".state" / "fixture-sync"
            )
            fixture_env["TMPDIR"] = str(script_root / ".state" / "tmp")
            fixture_env["TEMP"] = fixture_env["TMPDIR"]
            fixture_env["TMP"] = fixture_env["TMPDIR"]
            fixture_env["XDG_CACHE_HOME"] = str(script_root / ".state" / "cache")
            fixture_env["PYTHONPYCACHEPREFIX"] = str(
                script_root / ".state" / "cache" / "pycache"
            )
            fixture_env["AGENT_CANON_TOOLS_HOME"] = str(
                script_root / ".state" / "tools-home"
            )
            fixture_env["CARGO_HOME"] = str(
                script_root / ".state" / "cache" / "cargo-home"
            )
            fixture_env["CARGO_TARGET_DIR"] = str(
                script_root / ".state" / "cache" / "cargo-target"
            )
            fixture_env["AGENT_CANON_CLI_TARGET_DIR"] = fixture_env["CARGO_TARGET_DIR"]
            fixture_link = subprocess.run(
                ["bash", str(fixture_tools / "sync_agent_canon.sh"), "link-root"],
                cwd=script_root,
                check=False,
                capture_output=True,
                text=True,
                env=fixture_env,
            )
            self.assertEqual(fixture_link.returncode, 0, fixture_link.stderr)
            for relative_path in ("ROOT_AGENTS.md", ".codex/config.toml"):
                projected_source = script_root / "vendor" / "agent-canon" / relative_path
                if projected_source.is_symlink():
                    projected_source.unlink()
                shutil.copy2(
                    AGENT_CANON_SOURCE_ROOT / relative_path,
                    projected_source,
                )
            devcontainer_config = script_root / ".devcontainer" / "devcontainer.json"
            devcontainer_config.parent.mkdir(parents=True, exist_ok=True)
            if devcontainer_config.is_symlink():
                devcontainer_config.unlink()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / ".devcontainer" / "devcontainer.json",
                devcontainer_config,
            )
            fixture_check = subprocess.run(
                ["bash", str(fixture_tools / "sync_agent_canon.sh"), "check"],
                cwd=script_root,
                check=False,
                capture_output=True,
                text=True,
                env=fixture_env,
            )
            self.assertEqual(
                fixture_check.returncode,
                0,
                f"stdout={fixture_check.stdout!r} stderr={fixture_check.stderr!r}",
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=script_root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "fixture canonical root projection"],
                cwd=script_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (script_root / "tools" / "ci").mkdir(parents=True, exist_ok=True)
            (script_root / "tools" / "lib").mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_fresh_clone.sh",
                script_root / "tools" / "ci" / "check_fresh_clone.sh",
            )
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "lib" / "repo_paths.sh",
                script_root / "tools" / "lib" / "repo_paths.sh",
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root),
                    "add",
                    "tools/ci/check_fresh_clone.sh",
                    "tools/lib/repo_paths.sh",
                ],
                check=True,
            )
            staged_diff = subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root),
                    "diff",
                    "--cached",
                    "--quiet",
                    "--",
                    "tools/ci/check_fresh_clone.sh",
                    "tools/lib/repo_paths.sh",
                ],
                check=False,
            )
            self.assertIn(staged_diff.returncode, (0, 1))
            if staged_diff.returncode == 1:
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(script_root),
                        "commit",
                        "-m",
                        "fixture fresh clone checker",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            check_script = script_root / "tools" / "ci" / "check_fresh_clone.sh"
            self.assertTrue(check_script.exists(), check_script)
            check_script = str(check_script)
            script_root_vendor = script_root / "vendor" / "agent-canon"
            script_root_vendor_head = subprocess.run(
                ["git", "-C", str(script_root_vendor), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            script_root_vendor_status = subprocess.run(
                [
                    "git",
                    "-C",
                    str(script_root_vendor),
                    "status",
                    "--short",
                    "--untracked-files=all",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            test_contracts = [
                {
                    "name": "success",
                    "signal": None,
                    "expected_rc": 0,
                    "expect_parent_projection": True,
                },
                {
                    "name": "forced-failure",
                    "signal": None,
                    "expected_rc": 1,
                    "expect_error": "fresh_clone_overlay=fail",
                },
                {
                    "name": "sigint",
                    "signal": "INT",
                    "expected_rc": 130,
                    "dynamic_signal": True,
                },
                {
                    "name": "sigterm",
                    "signal": "TERM",
                    "expected_rc": 143,
                    "dynamic_signal": True,
                },
                {
                    "name": "sighup",
                    "signal": "HUP",
                    "expected_rc": 129,
                    "dynamic_signal": True,
                },
                {
                    "name": "default-temp",
                    "signal": None,
                    "expected_rc": 0,
                    "expect_parent_projection": True,
                    "use_default_parent_tmp": True,
                },
            ]

            for test_case in test_contracts:
                with self.subTest(test_case["name"]):
                    case_root = temp_root / test_case["name"]
                    home_root = case_root / "home"
                    tmpdir = case_root / "tmp"
                    if test_case.get("use_default_parent_tmp", False):
                        parent_tmp_root = script_root / ".agent-canon" / "tmp" / "fresh-clone"
                    else:
                        parent_tmp_root = script_root / ".state" / "fresh-clone" / test_case["name"]
                    home_root.mkdir(parents=True)
                    tmpdir.mkdir()
                    sentinel = home_root / ".agent-canon-gitconfig-sentinel"
                    sentinel.write_bytes(
                        b"[safe]\n"
                        b"\tdirectory = /existing/safe-directory\n"
                        b"[user]\n"
                        b"\tname = Existing Fixture User\n"
                        b"\temail = existing-fixture@example.invalid\n"
                        b"[custom]\n"
                        b"\tsetting = preserve\n"
                    )
                    subprocess.run(
                        ["git", "config", "--file", str(sentinel), "--list"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    env = os.environ.copy()
                    for key in tuple(env):
                        if key.startswith("AGENT_CANON_"):
                            env.pop(key)
                    env["HOME"] = str(home_root)
                    env["GIT_CONFIG_GLOBAL"] = str(sentinel)
                    env["GIT_CONFIG_NOSYSTEM"] = "1"
                    env["TMPDIR"] = str(
                        script_root / ".agent-canon" / "tmp" / test_case["name"]
                    )
                    env["TEMP"] = env["TMPDIR"]
                    env["TMP"] = env["TMPDIR"]
                    env["PYTHONPYCACHEPREFIX"] = str(
                        script_root / ".agent-canon" / "cache" / "pycache"
                    )
                    env["XDG_CACHE_HOME"] = str(
                        script_root / ".agent-canon" / "cache"
                    )
                    env["AGENT_CANON_TOOLS_HOME"] = str(
                        script_root / ".agent-canon" / "tools"
                    )
                    env["CARGO_HOME"] = str(
                        script_root / ".agent-canon" / "cache" / "cargo-home"
                    )
                    env["CARGO_TARGET_DIR"] = str(
                        script_root / ".agent-canon" / "cache" / "cargo-target"
                    )
                    env["AGENT_CANON_CLI_TARGET_DIR"] = env["CARGO_TARGET_DIR"]
                    if not test_case.get("use_default_parent_tmp", False):
                        env["AGENT_CANON_PARENT_TMP_ROOT"] = str(parent_tmp_root)

                    if test_case["name"] == "forced-failure":
                        bin_root = case_root / "bin"
                        bin_root.mkdir()
                        (bin_root / "make").write_text(
                            "#!/usr/bin/env bash\n"
                            "echo \"fresh_clone_overlay=fail\" >&2\n"
                            "exit 1\n",
                            encoding="utf-8",
                        )
                        os.chmod(bin_root / "make", 0o755)
                        env["PATH"] = f"{bin_root}:{env['PATH']}"

                    baseline = git_config_sentinel_state(sentinel)
                    result = run_fresh_clone_check(
                        check_script,
                        script_root,
                        env=env,
                        signal_name=test_case.get("signal"),
                    )
                    self.assertEqual(
                        result.returncode,
                        test_case["expected_rc"],
                        f"stdout={result.stdout!r} stderr={result.stderr!r}",
                    )
                    self.assertTrue(script_root_vendor.is_dir())
                    self.assertEqual(
                        subprocess.run(
                            ["git", "-C", str(script_root_vendor), "rev-parse", "HEAD"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                        script_root_vendor_head,
                    )
                    self.assertEqual(
                        subprocess.run(
                            [
                                "git",
                                "-C",
                                str(script_root_vendor),
                                "status",
                                "--short",
                                "--untracked-files=all",
                            ],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout,
                        script_root_vendor_status,
                    )
                    if test_case.get("expect_parent_projection", False):
                        self.assertIn("FRESH_CLONE_PARENT_PROJECTION=enabled", result.stdout)
                        self.assertIn("FRESH_CLONE_ACCEPTANCE=pass", result.stdout)
                    if "expect_error" in test_case:
                        self.assertIn(test_case["expect_error"], result.stderr)
                    sentinel_bytes, sentinel_hash = git_config_sentinel_state(sentinel)
                    baseline_bytes, baseline_hash = baseline
                    self.assertEqual(sentinel_bytes, baseline_bytes)
                    self.assertEqual(sentinel_hash, baseline_hash)
                    self.assertTrue(parent_tmp_root.is_dir(), parent_tmp_root)
                    self.assertFalse(
                        any(
                            child.name.startswith("template-fresh-clone-")
                            for child in parent_tmp_root.iterdir()
                            if child.is_dir()
                        )
                    )
                    if test_case.get("use_default_parent_tmp", False):
                        self.assertEqual(tuple(parent_tmp_root.iterdir()), ())


class UpdateMaterializationPredicateTest(unittest.TestCase):
    """Exercise the collision predicate directly in a standalone source checkout."""

    MATERIALIZATION_LIB = AGENT_CANON_SOURCE_ROOT / "tools" / "lib" / "update_materialization.sh"

    def init_repo(self, root: Path, files: dict[str, str]) -> Path:
        """Create one repository with a committed main branch."""
        repo = root / "materialization"
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "config", "user.name", "Materialization Test"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "materialization@example.invalid"],
            cwd=repo,
            check=True,
        )
        for relative, content in files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)
        return repo

    def commit(self, repo: Path, message: str) -> str:
        """Commit the current repository state and return its commit id."""
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def collision(self, repo: Path, current: str, remote: str) -> subprocess.CompletedProcess[str]:
        """Return the direct helper result for one virtual materialization."""
        return subprocess.run(
            [
                "bash",
                "-c",
                (
                    'source "$1"; '
                    'result_tree="$(update_materialization_result_tree "$2" "$3" "$4")" '
                    '|| exit $?; update_materialization_collision_path "$2" "$3" "$result_tree"'
                ),
                "materialization-test",
                str(self.MATERIALIZATION_LIB),
                str(repo),
                current,
                remote,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def result_tree(
        self,
        repo: Path,
        current: str,
        remote: str,
    ) -> subprocess.CompletedProcess[str]:
        """Return the virtual merge-result helper status."""
        return subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; update_materialization_result_tree "$2" "$3" "$4"',
                "materialization-test",
                str(self.MATERIALIZATION_LIB),
                str(repo),
                current,
                remote,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def local_paths(self, repo: Path) -> subprocess.CompletedProcess[str]:
        """Return the complete local materialization path union, including hidden flags."""
        return subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; update_materialization_local_paths "$2"',
                "materialization-test",
                str(self.MATERIALIZATION_LIB),
                str(repo),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_ignored_untracked_overwrite_candidate_collides(self) -> None:
        """Ignored untracked materialization participates in the local path set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.init_repo(Path(tmp_dir), {"README.md": "base\n"})
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "switch", "-c", "remote"], cwd=repo, check=True)
            (repo / "ignored.txt").write_text("remote\n", encoding="utf-8")
            remote = self.commit(repo, "remote ignored candidate")
            subprocess.run(["git", "switch", "main"], cwd=repo, check=True)
            git_exclude = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            exclude_path = Path(git_exclude)
            if not exclude_path.is_absolute():
                exclude_path = repo / exclude_path
            exclude_path.write_text("ignored.txt\n", encoding="utf-8")
            (repo / "ignored.txt").write_text("local ignored\n", encoding="utf-8")

            collision = self.collision(repo, base, remote)

            self.assertEqual(collision.returncode, 0, collision.stderr)
            self.assertEqual(collision.stdout, "ignored.txt\n")

    def test_virtual_merge_write_set_includes_local_rename_destination(self) -> None:
        """Git's virtual merge result exposes the dirty local rename destination."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.init_repo(Path(tmp_dir), {"a.txt": "one\ntwo\nthree\nfour\n"})
            subprocess.run(["git", "switch", "-c", "remote"], cwd=repo, check=True)
            (repo / "a.txt").write_text("one\ntwo remote\nthree\nfour\n", encoding="utf-8")
            remote = self.commit(repo, "remote edit")
            subprocess.run(["git", "switch", "main"], cwd=repo, check=True)
            subprocess.run(["git", "switch", "-c", "local"], cwd=repo, check=True)
            subprocess.run(["git", "mv", "a.txt", "b.txt"], cwd=repo, check=True)
            current = self.commit(repo, "local rename")
            (repo / "b.txt").write_text(
                "one\ntwo\nthree\nfour\nlocal dirty\n",
                encoding="utf-8",
            )

            collision = self.collision(repo, current, remote)

            self.assertEqual(collision.returncode, 0, collision.stderr)
            self.assertEqual(collision.stdout, "b.txt\n")

    def test_noncolliding_dirty_path_is_accepted(self) -> None:
        """A dirty path outside the virtual write set does not block materialization."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.init_repo(Path(tmp_dir), {"README.md": "base\n"})
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "switch", "-c", "remote"], cwd=repo, check=True)
            (repo / "remote.txt").write_text("remote\n", encoding="utf-8")
            remote = self.commit(repo, "remote addition")
            subprocess.run(["git", "switch", "main"], cwd=repo, check=True)
            (repo / "local.txt").write_text("local dirty\n", encoding="utf-8")

            collision = self.collision(repo, base, remote)

            self.assertEqual(collision.returncode, 1, collision.stderr)
            self.assertEqual(collision.stdout, "")

    def test_virtual_merge_conflict_is_typed_separately(self) -> None:
        """A committed conflict returns the dedicated merge-tree status."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.init_repo(Path(tmp_dir), {"README.md": "base\n"})
            subprocess.run(["git", "switch", "-c", "remote"], cwd=repo, check=True)
            (repo / "README.md").write_text("remote\n", encoding="utf-8")
            remote = self.commit(repo, "remote conflict")
            subprocess.run(["git", "switch", "main"], cwd=repo, check=True)
            subprocess.run(["git", "switch", "-c", "local"], cwd=repo, check=True)
            (repo / "README.md").write_text("local\n", encoding="utf-8")
            current = self.commit(repo, "local conflict")

            result = self.result_tree(repo, current, remote)

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_assume_unchanged_and_skip_worktree_changes_are_materialized_paths(self) -> None:
        """Index flags cannot hide changed tracked content from collision detection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self.init_repo(
                Path(tmp_dir),
                {"assume.txt": "base assume\n", "skip.txt": "base skip\n"},
            )
            subprocess.run(
                ["git", "update-index", "--assume-unchanged", "--", "assume.txt"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "update-index", "--skip-worktree", "--", "skip.txt"],
                cwd=repo,
                check=True,
            )
            flags_before = subprocess.run(
                ["git", "ls-files", "-v", "--", "assume.txt", "skip.txt"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            (repo / "assume.txt").write_text("hidden assume change\n", encoding="utf-8")
            (repo / "skip.txt").write_text("hidden skip change\n", encoding="utf-8")
            status = subprocess.run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )

            paths = self.local_paths(repo)

            self.assertEqual(status.stdout, "")
            self.assertEqual(paths.returncode, 0, paths.stderr)
            self.assertEqual(
                set(filter(None, paths.stdout.split("\0"))),
                {"assume.txt", "skip.txt"},
            )
            flags_after = subprocess.run(
                ["git", "ls-files", "-v", "--", "assume.txt", "skip.txt"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertEqual(flags_after, flags_before)


@unittest.skipIf(
    AGENT_CANON_IS_SUBMODULE or AGENT_CANON_IS_STANDALONE,
    "subtree snapshot wrapper tests require a derived subtree checkout",
)
class UpdateAgentCanonTest(unittest.TestCase):
    """Exercise the wrapper through a cloned repository."""

    def overlay_working_tree(self, target: Path) -> None:
        """Mirror the current working tree into one clone without external tools."""
        for child in target.iterdir():
            if child.name in OVERLAY_EXCLUDED_NAMES:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in REPO_ROOT.iterdir():
            if child.name in OVERLAY_EXCLUDED_NAMES:
                continue
            destination = target / child.name
            subprocess.run(
                ["cp", "-a", str(child), str(destination)],
                check=True,
                capture_output=True,
                text=True,
            )
        submodule_gitfile = target / SUBMODULE_GITFILE
        if submodule_gitfile.is_file():
            submodule_gitfile.unlink()

    def clone_repo(self, target: Path) -> None:
        """Clone the current repository into one temporary target."""
        subprocess.run(
            ["git", "clone", "--no-local", str(REPO_ROOT), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.overlay_working_tree(target)
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if status:
            subprocess.run(
                ["git", "config", "user.name", "Update Agent Canon Test"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "update-agent-canon@example.invalid"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "test: overlay current working tree"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )

    def split_agent_canon_snapshot(self, repo: Path) -> str:
        """Return a split commit for fresh clones that may not have subtree join objects."""
        plain = subprocess.run(
            ["git", "subtree", "split", "--prefix=vendor/agent-canon", "HEAD"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        if plain.returncode == 0 and plain.stdout.strip():
            return plain.stdout.strip()

        ignore_joins = subprocess.run(
            ["git", "subtree", "split", "--ignore-joins", "--prefix=vendor/agent-canon", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return ignore_joins.stdout.strip()

    def replace_tree(self, source: Path, target: Path) -> None:
        """Replace target contents without depending on rsync in minimal containers."""
        for child in target.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in source.iterdir():
            if child.name == ".git":
                continue
            destination = target / child.name
            if child.is_symlink():
                os.symlink(os.readlink(child), destination)
            elif child.is_dir():
                shutil.copytree(child, destination, symlinks=True)
            else:
                shutil.copy2(child, destination, follow_symlinks=False)

    def test_link_root_converts_shared_goal_symlink_to_repo_local_file(self) -> None:
        """goal.md is repo-local state and must not be a shared canon symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            self.clone_repo(clone_dir)
            goal_path = clone_dir / "goal.md"
            if goal_path.exists() or goal_path.is_symlink():
                goal_path.unlink()
            os.symlink("vendor/agent-canon/goal.md", goal_path)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=authorized_test_env(),
            )
            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(goal_path.is_symlink())
            self.assertIn("repo-local goal", goal_path.read_text(encoding="utf-8"))
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_plan_reports_snapshot_import_without_subtree_binary(self) -> None:
        """Plan should report the no-subtree route when git-subtree is unavailable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            missing_exec = root / "missing-git-exec"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = work_dir / ".plan-no-subtree-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: advance agent canon",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            missing_exec.mkdir(parents=True, exist_ok=True)
            git_binary = shutil.which("git")
            self.assertIsNotNone(git_binary)
            git_wrapper = missing_exec / "git"
            git_wrapper.write_text(
                "#!/usr/bin/env bash\n"
                "for arg in \"$@\"; do\n"
                "  if [[ \"$arg\" == \"subtree\" ]]; then\n"
                "    echo 'git: subtree unavailable in test' >&2\n"
                "    exit 1\n"
                "  fi\n"
                "done\n"
                f"exec {git_binary} \"$@\"\n",
                encoding="utf-8",
            )
            git_wrapper.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{missing_exec}{os.pathsep}{env['PATH']}"

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertRegex(
                plan.stdout,
                r"agent_canon_plan_route=(snapshot_import_tree_match|snapshot_import_no_subtree)",
            )

    def test_plan_prefers_subtree_pull_when_local_split_is_remote_ancestor(self) -> None:
        """Plan should prefer subtree_pull over tree-match snapshot route when subtree metadata exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = work_dir / ".subtree-pull-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: advance agent canon with subtree metadata available",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=subtree_pull", plan.stdout)

    def test_apply_succeeds_when_local_history_diverged_but_tree_matches_remote_history(
        self,
    ) -> None:
        """Apply should recover when local split diverged but the current tree exists upstream."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "remove", "agent-canon"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            remote_marker_a = work_dir / ".remote-tree-match-marker"
            remote_marker_a.write_text("remote-a\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker_a.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: remote tree match base",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            local_diverged_marker = clone_dir / "vendor" / "agent-canon" / ".diverged-local-marker"
            local_diverged_marker.write_text("diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(local_diverged_marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge local shared canon",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            self.replace_tree(work_dir, clone_dir / "vendor" / "agent-canon")
            subprocess.run(
                ["git", "add", "-A"], cwd=clone_dir, check=True, capture_output=True, text=True
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: realign local tree to remote history",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            remote_marker_b = work_dir / ".remote-after-tree-match-marker"
            remote_marker_b.write_text("remote-b\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker_b.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: remote advance after tree match",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=snapshot_import_tree_match", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=authorized_test_env(),
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn(
                "agent_canon_snapshot_import=tree_match_in_remote_history", combined_output
            )
            self.assertIn(
                "agent_canon_update_method=snapshot_import_after_subtree_pull_failure",
                combined_output,
            )

    def test_apply_fails_closed_when_local_shared_canon_history_diverges(self) -> None:
        """Apply should stop before mutating the worktree when local vendor history diverges."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            remote_marker = work_dir / ".remote-diverged-marker"
            remote_marker.write_text("remote-diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge remote shared canon",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            diverged_marker = clone_dir / "vendor" / "agent-canon" / ".diverged-local-marker"
            diverged_marker.write_text("diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(diverged_marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge local shared canon",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=diverged_local_history", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=authorized_test_env(),
            )
            self.assertNotEqual(apply.returncode, 0)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn("agent_canon_snapshot_import=diverged_history", combined_output)
            self.assertIn("diverged", combined_output)

            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(status, "")

@unittest.skipUnless(
    AGENT_CANON_IS_SUBMODULE,
    "submodule wrapper tests only apply when vendor/agent-canon is a submodule",
)
class SubmoduleUpdateAgentCanonTest(unittest.TestCase):
    """Exercise submodule-specific update routes."""

    PROTECTED_GIT_ENV = {
        "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
        "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "test-approved-update",
        "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": COMMIT_REQUEST_EVIDENCE,
    }

    def setUp(self) -> None:
        """Authorize protected mutations explicitly inside tempfile test repos."""
        previous = {name: os.environ.get(name) for name in self.PROTECTED_GIT_ENV}
        os.environ.update(self.PROTECTED_GIT_ENV)

        def restore_environment() -> None:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.addCleanup(restore_environment)

    def unauthorized_env(self, **overrides: str) -> dict[str, str]:
        """Return a subprocess environment without inherited protected authority."""
        env = dict(os.environ)
        for name in self.PROTECTED_GIT_ENV:
            env.pop(name, None)
        env.update(overrides)
        return env

    def make_agent_canon_remote(self, root: Path) -> tuple[Path, Path]:
        """Create one bare AgentCanon remote and working clone."""
        root.mkdir(parents=True, exist_ok=True)
        bare_repo = root / "agent-canon.git"
        work_dir = root / "agent-canon-work"
        subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True)
        subprocess.run(["git", "clone", str(bare_repo), str(work_dir)], check=True)
        subprocess.run(["git", "switch", "-c", "main"], cwd=work_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=work_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "submodule-test@example.invalid"],
            cwd=work_dir,
            check=True,
        )
        (work_dir / "README.md").write_text("# AgentCanon\n", encoding="utf-8")
        (work_dir / "ROOT_AGENTS.md").write_text("# Root agents\n", encoding="utf-8")
        (work_dir / "tools" / "agent_tools").mkdir(parents=True)
        shutil.copy2(
            AGENT_CANON_SOURCE_ROOT / "tools" / "agent_tools" / "surface_manifest.py",
            work_dir / "tools" / "agent_tools" / "surface_manifest.py",
        )
        github_template_paths = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for template_dir in (
                REPO_ROOT / ".github" / "ISSUE_TEMPLATE",
                REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE",
            )
            for path in template_dir.iterdir()
            if path.is_file()
        )
        (work_dir / "documents" / "runtime").mkdir(parents=True)
        (work_dir / "documents" / "runtime" / "shared-runtime-surfaces.toml").write_text(
            "\n".join(
                [
                    'version = 1',
                    'prefix = "vendor/agent-canon"',
                    'integration_mode = "live-agent-canon"',
                    'default_consumer = false',
                    'selection = "explicit-opt-in"',
                    '',
                    '[[surface]]',
                    'path = "AGENTS.md"',
                    'mode = "symlink"',
                    'source = "ROOT_AGENTS.md"',
                    'projection_producer = "agent-canon"',
                    'projection_kind = "runtime_surface"',
                    '',
                    '[[surface]]',
                    'path = ".vscode"',
                    'mode = "regular"',
                    'projection_producer = "template-or-derived-repo"',
                    'projection_kind = "active_contract"',
                    'source = ".vscode"',
                    '',
                    '[[group]]',
                    'mode = "symlink"',
                    'projection_producer = "agent-canon"',
                    'projection_kind = "runtime_surface"',
                    'source_prefix = ""',
                    'paths = [',
                    '  ".vscode/c_cpp_properties.json",',
                    '  ".vscode/extensions.json",',
                    '  ".vscode/settings.json",',
                    '  ".vscode/tasks.json",',
                    '  ".github/AGENTS.md",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "copy"',
                    'projection_producer = "github-path-constraint"',
                    'projection_kind = "github_copy"',
                    'local_override_allowed = false',
                    'paths = [',
                    *(f'  "{path}",' for path in github_template_paths),
                    ']',
                    '',
                    '[[group]]',
                    'mode = "removed_legacy"',
                    'projection_producer = "legacy"',
                    'projection_kind = "removed_legacy"',
                    'local_override_allowed = false',
                    'paths = [',
                    '  ".github/workflows/agent-improvement-guide.yml",',
                    '  ".github/workflows/agent-coordination.yml",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "regular"',
                    'projection_producer = "template-or-derived-repo"',
                    'projection_kind = "active_contract"',
                    'local_override_allowed = true',
                    'source_prefix = ""',
                    'paths = [',
                    '  "documents/README.md",',
                    ']',
                    '',
                    '[[surface]]',
                    'path = "tools/agent-canon"',
                    'mode = "symlink"',
                    'source = "tools"',
                    'projection_producer = "agent-canon"',
                    'projection_kind = "runtime_surface"',
                    '',
                    '[[group]]',
                    'mode = "standalone_only"',
                    'projection_producer = "agent-canon-standalone"',
                    'projection_kind = "standalone_only"',
                    'local_override_allowed = false',
                    'paths = [',
                    '  "documents/runtime/SHARED_RUNTIME_SURFACES.md",',
                    ']',
                    '',
                    '[[surface]]',
                    'path = "goal.md"',
                    'mode = "repo_state"',
                    'projection_producer = "project"',
                    'projection_kind = "durable_state"',
                    'local_override_allowed = true',
                    '',
                ]
            ),
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows").mkdir(parents=True)
        (work_dir / ".vscode").mkdir()
        for vscode_name in (
            "c_cpp_properties.json",
            "extensions.json",
            "settings.json",
            "tasks.json",
        ):
            (work_dir / ".vscode" / vscode_name).write_text(
                '{"agentCanonTest": true}\n',
                encoding="utf-8",
            )
        (work_dir / "documents" / "README.md").write_text(
            "# Derived Documents Seed\n",
            encoding="utf-8",
        )
        (work_dir / "documents" / "runtime" / "SHARED_RUNTIME_SURFACES.md").write_text(
            "\n".join(
                [
                    "# Standalone Surface Policy",
                    "",
                    "documents/runtime/shared-runtime-surfaces.toml",
                    "AGENTS.md",
                    ".codex/config.toml",
                    ".codex/agents",
                    ".codex/hooks.json",
                    ".codex/hooks",
                    ".devcontainer/",
                    "documents/README.md",
                    "documents/contracts/template-bootstrap.md",
                    "documents/contracts/github-first-module-and-devcontainer-policy.md",
                    "memory/README.md",
                    "memory/records/",
                    "tests/agent_tools/",
                    "Root `tools/` is a parent-owned regular container",
                    "tools/agent-canon -> ../vendor/agent-canon/tools",
                    "vendor/agent-canon/tools/",
                    "Project-local automation must stay in project-owned paths",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (work_dir / ".github" / "AGENTS.md").write_text(
            "# GitHub agents\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows" / "agent-coordination.yml").write_text(
            "name: agent coordination\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows" / "agent-improvement-guide.yml").write_text(
            "name: agent improvement guide\non:\n  workflow_dispatch:\n",
            encoding="utf-8",
        )
        for template_path in github_template_paths:
            destination = work_dir / template_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "python3 tools/agent_tools/route.py\n"
                if "PULL_REQUEST_TEMPLATE" in destination.parts
                else "name: issue fixture\n"
            )
            destination.write_text(content, encoding="utf-8")
        subprocess.run(
            [
                "git",
                "add",
                "README.md",
                "ROOT_AGENTS.md",
                ".github",
                ".vscode",
                "documents",
                "tools",
            ],
            cwd=work_dir,
            check=True,
        )
        subprocess.run(["git", "commit", "-m", "initial agent canon"], cwd=work_dir, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
        subprocess.run(
            ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
        )
        return bare_repo, work_dir

    def make_superproject(
        self,
        root: Path,
        bare_repo: Path,
        *,
        public_submodule_add: bool = False,
        commit_submodule: bool = True,
    ) -> Path:
        """Create one derived repo with AgentCanon as a submodule."""
        repo = root / "derived"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "submodule-test@example.invalid"],
            cwd=repo,
            check=True,
        )
        (repo / "tools").mkdir()
        shutil.copy2(
            AGENT_CANON_SOURCE_ROOT / "tools" / "sync_agent_canon.sh",
            repo / "tools",
        )
        shutil.copy2(AGENT_CANON_SOURCE_ROOT / "tools" / "update_agent_canon.sh", repo / "tools")
        shutil.copy2(AGENT_CANON_SOURCE_ROOT / "tools" / "rebuild_agent_tools.sh", repo / "tools")
        shutil.copytree(AGENT_CANON_SOURCE_ROOT / "tools" / "lib", repo / "tools" / "lib")
        fixture_agent_tools = repo / "tools" / "agent_tools"
        fixture_agent_tools.mkdir()
        fixture_tool_closure = (
            "artifact_identity.py",
            "parent_root_side_effects.py",
            "update_lifecycle_contract.py",
            "attach_clean_detached_submodule.py",
        )
        for name in fixture_tool_closure:
            source_file = AGENT_CANON_SOURCE_ROOT / "tools" / "agent_tools" / name
            target_file = fixture_agent_tools / name
            shutil.copy2(source_file, target_file)
            self.assertEqual(
                target_file.read_bytes(),
                source_file.read_bytes(),
                f"fixture closure readback mismatch: {name}",
            )
        if public_submodule_add:
            subprocess.run(["git", "add", "tools"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial parent"], cwd=repo, check=True)
            env = dict(os.environ)
            env["GIT_ALLOW_PROTOCOL"] = "file"
            env["AGENT_CANON_BRANCH_WORKTREE_AUTHORITY"] = "user_request"
            env["AGENT_CANON_BRANCH_WORKTREE_REASON"] = "test submodule creation"
            subprocess.run(
                [
                    "bash",
                    "tools/sync_agent_canon.sh",
                    "submodule-add",
                    str(bare_repo),
                    "main",
                ],
                cwd=repo,
                check=True,
                env=env,
            )
        else:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "protocol.file.allow=always",
                    "submodule",
                    "add",
                    "-b",
                    "main",
                    str(bare_repo),
                    "vendor/agent-canon",
                ],
                cwd=repo,
                check=True,
            )
        if commit_submodule:
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "add submodule"], cwd=repo, check=True)
        return repo

    def protected_state(self, repo: Path) -> tuple[str, ...]:
        """Return protected Git state used to prove a blocked command is inert."""
        submodule = repo / "vendor" / "agent-canon"
        commands = (
            (["git", "rev-parse", "HEAD"], repo),
            (["git", "ls-files", "--stage", "--", "vendor/agent-canon"], repo),
            (["git", "status", "--porcelain=v1", "--untracked-files=all"], repo),
            (["git", "rev-parse", "HEAD"], submodule),
            (["git", "status", "--porcelain=v1", "--untracked-files=all"], submodule),
            (["git", "stash", "list"], submodule),
            (["git", "branch", "--show-current"], submodule),
            (["git", "worktree", "list", "--porcelain"], submodule),
        )
        return tuple(
            subprocess.run(
                command,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            for command, cwd in commands
        )

    def source_bytewise_state(self, repo: Path) -> tuple[object, ...]:
        """Capture source refs, config, FETCH_HEAD, and object bytes for plan oracles."""
        source = repo / "vendor" / "agent-canon"
        git_dir_text = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        git_dir = Path(git_dir_text)
        if not git_dir.is_absolute():
            git_dir = (source / git_dir).resolve()
        fetch_head = git_dir / "FETCH_HEAD"
        refs = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)=%(objectname)"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        config = subprocess.run(
            ["git", "config", "--local", "--null", "--get-regexp", r"^branch\.main\."],
            cwd=source,
            check=False,
            capture_output=True,
        ).stdout
        origin_url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=source,
            check=False,
            capture_output=True,
            text=True,
        ).stdout
        objects = git_dir / "objects"
        object_files = tuple(
            (
                str(path.relative_to(objects)),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted(objects.rglob("*"))
            if path.is_file()
        )
        object_ids = subprocess.run(
            ["git", "cat-file", "--batch-all-objects", "--batch-check"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        fetch_state = (
            fetch_head.exists(),
            hashlib.sha256(fetch_head.read_bytes()).hexdigest() if fetch_head.exists() else "",
        )
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=source, check=True, capture_output=True, text=True
            ).stdout,
            refs,
            config,
            origin_url,
            fetch_state,
            object_ids,
            object_files,
            subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=source,
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
        )

    def materialize_parent_projection_frontier(
        self,
        repo: Path,
        source: Path,
    ) -> None:
        """Materialize accepted lifecycle evidence for one parent projection fixture."""
        lifecycle = StandaloneUpdateLifecycleTest()
        binding, rebind = lifecycle.binding_and_rebind(source)
        packet = lifecycle.source_projection_packet(binding, rebind)
        readback_ref = "evidence:" + "9" * 64
        queue = materialize_queue_receipt(
            binding=binding,
            source_namespace=str(source.resolve()),
            source_main_rebind_receipt_id=str(rebind["rebind_receipt_id"]),
            source_main_readback_evidence_ref=readback_ref,
            publication_readback_receipt=packet["publication_readback_receipt"],
            state="accepted",
        )
        predecessors = [
            {
                "queue_number": 388,
                "source_pr": "#388",
                "publication_evidence_id": "evidence:" + "5" * 64,
            },
            {
                "queue_number": 389,
                "source_pr": "#389",
                "source_pr_sha": "6" * 40,
                "publication_evidence_id": "evidence:" + "7" * 64,
            },
        ]
        pending = materialize_dependency_frontier(
            binding=binding,
            queue_receipt=queue,
            rebind_receipt=rebind,
            source_main_readback_evidence_ref=readback_ref,
            ordered_predecessor_evidence=predecessors,
        )
        accepted = json.loads(json.dumps(pending))
        accepted["frontier_state"] = "accepted"
        accepted["preceding_frontier_evidence_id"] = binding["evidence_ref"]
        accepted["acceptance_evidence_ref"] = packet["acceptance_evidence_ref"]
        accepted = validate_dependency_frontier_transition(
            pending,
            accepted,
            queue_receipt=queue,
            rebind_receipt=rebind,
            origin_main_readback=SourceMainReadbackIdentity(
                commit_sha=str(binding["candidate_sha"]),
                tree_sha=str(binding["tree_sha"]),
            ),
            ordered_oracle=(
                "source_pr:#388",
                "source_pr:#389",
                f"transaction:{binding['transaction_id']}",
            ),
        )
        g4 = materialize_gate_verdict(
            binding=accepted["binding"],
            gate_id="G4",
            ordered_input_evidence_refs=(
                packet["source_gate_verdicts"][2]["binding"]["evidence_ref"],
                queue["binding"]["evidence_ref"],
                accepted["acceptance_evidence_ref"],
            ),
            invariant="parent_projection_integrity",
            output_digest="sha256:" + "a" * 64,
            owner=str(repo.resolve())
            + "/tools/update_agent_canon.sh#accept_dependency_frontier",
            verdict="pass",
        )
        namespace = repo / ".agent-canon" / "update-lifecycle"
        records = {
            namespace / "projection-queue" / "queue.accepted.json": queue,
            namespace / "projection-queue" / "frontier.accepted.json": accepted,
            namespace / "evidence" / "g4.parent-projection-integrity.json": g4,
            namespace / "state" / "current-transaction": {
                "schema": "agent-canon.update-lifecycle-current-transaction.v1",
                "transaction_id": binding["transaction_id"],
                "queue_receipt_id": queue["queue_receipt_id"],
                "frontier_id": accepted["frontier_id"],
            },
        }
        for path, record in records.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def test_update_modes_require_destructive_authority_before_side_effects(self) -> None:
        """Update modes require destructive authority, without a creation gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            modes = (
                "latest",
                "apply",
                "merge-main-into-current",
            )
            invalid_environments = (
                self.unauthorized_env(),
                self.unauthorized_env(
                    AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY="wrong",
                    AGENT_CANON_DESTRUCTIVE_GIT_REASON="reason",
                ),
                self.unauthorized_env(
                    AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY="explicit_user_approval",
                    AGENT_CANON_DESTRUCTIVE_GIT_REASON="",
                ),
            )
            before = self.protected_state(repo)
            for mode in modes:
                for env in invalid_environments:
                    with self.subTest(mode=mode, env_case=invalid_environments.index(env)):
                        result = subprocess.run(
                            ["bash", "tools/update_agent_canon.sh", mode],
                            cwd=repo,
                            check=False,
                            capture_output=True,
                            text=True,
                            env=env,
                        )
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("DESTRUCTIVE_GIT_GUARD=block", result.stdout)
                        self.assertNotIn("BRANCH_WORKTREE_CREATION_GUARD=block", result.stdout)
                        self.assertIn(
                            f"AGENT_CANON_PROTECTED_GIT_SUBCOMMAND={mode}", result.stdout
                        )
                        self.assertIn(
                            "NEXT_ACTION=request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason",
                            result.stdout,
                        )
                        self.assertNotIn("AGENT_CANON_EVAL_LOG_PARK=", result.stdout)
                        self.assertEqual(self.protected_state(repo), before)

    def test_sync_ensure_latest_requires_destructive_authority(self) -> None:
        """The low-level update boundary requires destructive authority only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            before = self.protected_state(repo)
            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=self.unauthorized_env(),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DESTRUCTIVE_GIT_GUARD=block", result.stdout)
            self.assertNotIn("BRANCH_WORKTREE_CREATION_GUARD=block", result.stdout)
            self.assertIn(
                "AGENT_CANON_PROTECTED_GIT_SUBCOMMAND=ensure-latest", result.stdout
            )
            self.assertEqual(self.protected_state(repo), before)

    def test_commit_request_evidence_fails_before_any_mutation(self) -> None:
        """Missing or malformed request evidence blocks wrapper and low-level routes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            before = self.protected_state(repo)
            invalid_evidence = ("", "evidence:" + ("A" * 64), "evidence:" + ("0" * 63))
            commands = (
                ("latest", "tools/update_agent_canon.sh"),
                ("apply", "tools/update_agent_canon.sh"),
                ("ensure-latest", "tools/sync_agent_canon.sh"),
                ("pull", "tools/sync_agent_canon.sh"),
            )

            for evidence in invalid_evidence:
                env = self.unauthorized_env(
                    AGENT_CANON_BRANCH_WORKTREE_AUTHORITY="user_request",
                    AGENT_CANON_BRANCH_WORKTREE_REASON="test-approved-update",
                    AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY="explicit_user_approval",
                    AGENT_CANON_DESTRUCTIVE_GIT_REASON="test-approved-update",
                    AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence,
                )
                for subcommand, script in commands:
                    with self.subTest(evidence=evidence, subcommand=subcommand):
                        result = subprocess.run(
                            ["bash", script, subcommand],
                            cwd=repo,
                            check=False,
                            capture_output=True,
                            text=True,
                            env=env,
                        )
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("COMMIT_PROVENANCE_GUARD=block", result.stdout)
                        self.assertNotIn("AGENT_CANON_EVAL_LOG_PARK=", result.stdout)
                        self.assertEqual(self.protected_state(repo), before)

    def test_sync_auto_commit_excludes_unrelated_pre_staged_sentinel(self) -> None:
        """Owned-path sync commits preserve but never absorb another chat's staged path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            sentinel = repo / "other-chat-sentinel.txt"
            sentinel.write_text("owned elsewhere\n", encoding="utf-8")
            subprocess.run(["git", "add", sentinel.name], cwd=repo, check=True)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)

            result = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "apply"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Hostile Author",
                    "GIT_AUTHOR_EMAIL": "hostile-author@example.invalid",
                    "GIT_COMMITTER_NAME": "Hostile Committer",
                    "GIT_COMMITTER_EMAIL": "hostile-committer@example.invalid",
                    "EMAIL": "hostile@example.invalid",
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            committed_paths = subprocess.run(
                ["git", "show", "--pretty=format:", "--name-only", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            staged_paths = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertNotIn(sentinel.name, committed_paths)
            self.assertIn(sentinel.name, staged_paths)
            identity = subprocess.run(
                ["git", "show", "-s", "--format=%an%n%ae%n%cn%n%ce", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertEqual(
                identity,
                [
                    "AgentCanon Sync Automation",
                    "agent-canon-sync@automation.invalid",
                    "AgentCanon Sync Automation",
                    "agent-canon-sync@automation.invalid",
                ],
            )
            commit_message = subprocess.run(
                ["git", "show", "-s", "--format=%B", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            trailers = subprocess.run(
                ["git", "interpret-trailers", "--parse"],
                input=commit_message,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            for trailer in (
                "AgentCanon-Automation-Actor: agent-canon-sync",
                "AgentCanon-Authority-Source: not-required",
                "AgentCanon-Destructive-Authority: explicit_user_approval",
                f"AgentCanon-Request-Evidence: {COMMIT_REQUEST_EVIDENCE}",
                f"AgentCanon-Remote: {remote_sha}",
                "AgentCanon-Update-Method: submodule_update",
                "AgentCanon-Prefix: vendor/agent-canon",
            ):
                self.assertIn(trailer, trailers)

    def test_update_todo_auto_commit_excludes_unrelated_pre_staged_sentinel(self) -> None:
        """TODO acknowledgement commits only its state path and preserves staged dirt."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            todo_dir = repo / "tools" / "agent_tools"
            todo_dir.mkdir(exist_ok=True)
            state_dir = repo / ".agent-canon"
            state_dir.mkdir()
            state_path = state_dir / "update-state.toml"
            state_path.write_text("state = 'old'\n", encoding="utf-8")
            todo_tool = todo_dir / "agent_canon_update_todos.py"
            todo_tool.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "import sys",
                        "if sys.argv[1] == 'plan':",
                        "    print('AGENT_CANON_UPDATE_TODO_PENDING_COUNT=0')",
                        "elif sys.argv[1] == 'acknowledge':",
                        "    Path('.agent-canon/update-state.toml').write_text(\"state = 'new'\\n\", encoding='utf-8')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "tools/agent_tools/agent_canon_update_todos.py", ".agent-canon/update-state.toml"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "seed todo state"], cwd=repo, check=True)
            sentinel = repo / "other-chat-todo-sentinel.txt"
            sentinel.write_text("owned elsewhere\n", encoding="utf-8")
            subprocess.run(["git", "add", sentinel.name], cwd=repo, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)

            result = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=authorized_test_env(),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            committed_paths = subprocess.run(
                ["git", "show", "--pretty=format:", "--name-only", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            staged_paths = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertEqual(committed_paths, [".agent-canon/update-state.toml"])
            self.assertIn(sentinel.name, staged_paths)

    def test_plan_does_not_initialize_absent_submodule_checkout(self) -> None:
        """Planning an uninitialized gitlink reports approval without mutation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            subprocess.run(
                ["git", "submodule", "deinit", "-f", "vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            checkout = repo / "vendor" / "agent-canon"
            self.assertFalse((checkout / ".git").exists())
            before_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
            ).stdout
            before_status = subprocess.run(
                ["git", "status", "--porcelain=v1"], cwd=repo, check=True, capture_output=True, text=True
            ).stdout

            result = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=self.unauthorized_env(),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_plan_route=submodule_checkout_uninitialized", result.stdout)
            self.assertIn("agent_canon_plan_status=approval_required", result.stdout)
            self.assertFalse((checkout / ".git").exists())
            self.assertEqual(
                subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
                ).stdout,
                before_head,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "status", "--porcelain=v1"], cwd=repo, check=True, capture_output=True, text=True
                ).stdout,
                before_status,
            )

    def test_plan_uses_captured_remote_sha_without_touching_fetch_head(self) -> None:
        """Concurrent FETCH_HEAD contents never select or change the planned target."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            git_dir_text = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            git_dir = Path(git_dir_text)
            if not git_dir.is_absolute():
                git_dir = (submodule / git_dir).resolve()
            fetch_head = git_dir / "FETCH_HEAD"
            sentinel = "0" * 40 + "\tnot-for-merge\tconcurrent sentinel\n"
            fetch_head.write_text(sentinel, encoding="utf-8")
            (work_dir / "captured-target.txt").write_text("target\n", encoding="utf-8")
            subprocess.run(["git", "add", "captured-target.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance captured target"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn(f"agent_canon_plan_remote_sha={remote_sha}", plan.stdout)
            self.assertEqual(fetch_head.read_text(encoding="utf-8"), sentinel)
            sync_script = (repo / "tools" / "sync_agent_canon.sh").read_text(encoding="utf-8")
            self.assertIn("plan_remote_probe", sync_script)
            self.assertIn("--no-write-fetch-head", sync_script)
            plan_body = sync_script[
                sync_script.index("cmd_plan() {") : sync_script.index("\ncmd_submodule_add() {")
            ]
            self.assertNotIn(
                'fetch --no-write-fetch-head origin "refs/heads/$branch:refs/remotes/origin/$branch"',
                plan_body,
            )
            self.assertNotIn('ensure_remote_commit_object "$ROOT_DIR/$PREFIX"', plan_body)

    def test_ensure_latest_reports_already_current_submodule(self) -> None:
        """Ensure-latest should no-op when the parent pin already matches remote main."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest_submodule_local_state_checked=yes", result.stdout)
            self.assertIn("agent_canon_latest=already_current_submodule", result.stdout)

    def test_plan_accepts_named_topic_branch_without_mutation(self) -> None:
        """Plan should report a named topic branch as deferred state evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"

            subprocess.run(
                ["git", "switch", "-c", "canon-pr/non-main"],
                cwd=submodule,
                check=True,
            )
            before = self.protected_state(repo)

            plan = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=deferred_branch_pr", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_branch=canon-pr/non-main", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_history_state=equal", plan.stdout)
            self.assertIn("agent_canon_plan_requires_clean=no", plan.stdout)
            self.assertIn("agent_canon_plan_unresolved_merge_conflict=no", plan.stdout)
            self.assertIn("agent_canon_plan_merge_conflict=no", plan.stdout)
            self.assertIn("agent_canon_plan_materialization_collision=no", plan.stdout)
            self.assertIn("agent_canon_plan_apply_command=", plan.stdout)
            self.assertEqual(self.protected_state(repo), before)

            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "detached unique commit",
                ],
                cwd=submodule,
                check=True,
            )
            detached_before = self.protected_state(repo)
            detached = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(detached.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_detached_nonpin", detached.stdout)
            self.assertIn("agent_canon_plan_status=blocked", detached.stdout)
            self.assertIn(
                "NEXT_ACTION=select_source_or_pin_owner_then_repair_detached_submodule",
                detached.stdout,
            )
            self.assertIn(
                "agent_canon_plan_remote_sha=<unavailable>", detached.stdout
            )
            self.assertNotIn("agent_canon_plan_apply_command=", detached.stdout)
            self.assertEqual(self.protected_state(repo), detached_before)

    def test_plan_accepts_clean_detached_stage0_pin(self) -> None:
        """A clean detached checkout at the staged pin is an attach candidate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)

            plan = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=submodule_detached_parent_pin", plan.stdout)
            self.assertIn("agent_canon_plan_status=ready", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_stage0_mode=160000", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_stage0_stage=0", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_stage0_path=vendor/agent-canon", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_main_ref_state=same", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_origin_main_status=matched", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_probe_cleanup_status=pass", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_probe_path=<none>", plan.stdout)
            self.assertIn("agent_canon_plan_apply_command=", plan.stdout)

    def test_detached_stage0_main_state_matrix_preserves_unsafe_refs(self) -> None:
        """Absent main is safe; a descendant main remains an explicit hold."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "update-ref", "-d", "refs/heads/main"],
                cwd=submodule,
                check=True,
            )
            absent = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(absent.returncode, 0, absent.stderr)
            self.assertIn("agent_canon_plan_route=submodule_detached_parent_pin", absent.stdout)
            self.assertIn("agent_canon_plan_submodule_main_ref_state=absent", absent.stdout)

            subprocess.run(
                ["git", "switch", "-c", "main"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "descendant main",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "switch", "--detach", "HEAD~1"], cwd=submodule, check=True)
            before = self.protected_state(repo)
            descendant = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(descendant.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_detached_main_descendant", descendant.stdout)
            self.assertIn("agent_canon_plan_submodule_main_ref_state=descendant", descendant.stdout)
            self.assertNotIn("agent_canon_plan_apply_command=", descendant.stdout)
            self.assertEqual(self.protected_state(repo), before)

    def test_plan_invalid_stage0_gitlink_keeps_stage_and_remote_facts_separate(self) -> None:
        """Invalid stage-0 facts must not shift into the remote resolver fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            submodule_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                [
                    "git",
                    "update-index",
                    "--cacheinfo",
                    f"100644,{submodule_sha},vendor/agent-canon",
                ],
                cwd=repo,
                check=True,
            )

            plan = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(plan.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_detached_invalid_stage0_gitlink", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_stage0_mode=100644", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_stage0_error_kind=mode", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_resolution_status=not_attempted", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_error_kind=none", plan.stdout)

    def test_plan_accepts_missing_local_tracking_ref_as_attach_prerequisite(self) -> None:
        """An absent origin/main is an attach prerequisite, not a plan mismatch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "update-ref", "-d", "refs/remotes/origin/main"], cwd=submodule, check=True
            )
            before = self.source_bytewise_state(repo)
            plan = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_submodule_origin_main_status=missing", plan.stdout)
            self.assertIn("agent_canon_plan_route=submodule_detached_parent_pin", plan.stdout)
            self.assertEqual(self.source_bytewise_state(repo), before)

    def test_plan_uses_staged_gitlink_over_parent_head_pin(self) -> None:
        """A staged parent pin is authoritative even when parent HEAD differs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            (work_dir / "staged-pin.txt").write_text("staged\n", encoding="utf-8")
            subprocess.run(["git", "add", "staged-pin.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "staged pin"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            staged_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=work_dir, check=True, capture_output=True, text=True
            ).stdout.strip()
            parent_head_pin = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(submodule), "fetch", "origin", staged_sha],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "update-index", "--cacheinfo", f"160000,{staged_sha},vendor/agent-canon"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "switch", "--detach", parent_head_pin], cwd=submodule, check=True)

            plan = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(plan.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_detached_nonpin", plan.stdout)
            self.assertIn(f"agent_canon_plan_submodule_stage0_oid={staged_sha}", plan.stdout)
            self.assertIn(f"agent_canon_plan_submodule_parent_head_pin={parent_head_pin}", plan.stdout)
            self.assertNotIn("agent_canon_plan_apply_command=", plan.stdout)

    def test_latest_returns_plan_failure_before_frontier_for_tracking_mismatch(self) -> None:
        """Tracking mismatch is complete plan evidence and cannot be masked by frontier."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            new_bare_repo, new_work_dir = self.make_agent_canon_remote(root / "new")
            repo = self.make_superproject(root, old_bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            subprocess.run(["git", "switch", "--orphan", "replacement-main"], cwd=new_work_dir, check=True)
            subprocess.run(["git", "clean", "-fdx"], cwd=new_work_dir, check=True)
            (new_work_dir / "tracking-mismatch.txt").write_text("new\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracking-mismatch.txt"], cwd=new_work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "create unrelated replacement remote"], cwd=new_work_dir, check=True)
            subprocess.run(["git", "push", "--force", "origin", "HEAD:main"], cwd=new_work_dir, check=True)
            new_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=new_work_dir, check=True, capture_output=True, text=True
            ).stdout.strip()
            subprocess.run(
                ["git", "config", "-f", ".gitmodules", "submodule.vendor/agent-canon.url", str(new_bare_repo)],
                cwd=repo,
                check=True,
            )
            before = self.protected_state(repo)

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=authorized_test_env(),
            )
            self.assertNotEqual(latest.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_origin_main_mismatch", latest.stdout)
            self.assertIn("agent_canon_plan_status=blocked", latest.stdout)
            self.assertIn(f"agent_canon_plan_submodule_origin_main_expected_sha={new_sha}", latest.stdout)
            self.assertIn("agent_canon_plan_submodule_origin_main_status=mismatch", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_PLAN_RC=", latest.stdout)
            self.assertNotIn("parent projection blocked", latest.stderr)
            self.assertEqual(self.protected_state(repo), before)
            self.assertEqual(
                subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=submodule,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "",
            )

    def test_plan_reports_remote_resolution_and_object_failures_completely(self) -> None:
        """Remote probes become typed plan facts instead of early shell exits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root / "unreachable")
            repo = self.make_superproject(root / "unreachable", bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            unreachable_source_before = self.source_bytewise_state(repo)
            missing_url = root / "unreachable" / "missing-agent-canon.git"
            subprocess.run(
                ["git", "config", "-f", ".gitmodules", "submodule.vendor/agent-canon.url", str(missing_url)],
                cwd=repo,
                check=True,
            )
            unreachable = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unreachable.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_remote_resolution_failed", unreachable.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_resolution_status=unreachable", unreachable.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_error_kind=ls_remote_failed", unreachable.stdout)
            self.assertIn("agent_canon_plan_status=blocked", unreachable.stdout)
            self.assertNotIn("agent_canon_plan_apply_command=", unreachable.stdout)
            self.assertEqual(self.source_bytewise_state(repo), unreachable_source_before)

            object_root = root / "object"
            object_bare, _object_work = self.make_agent_canon_remote(object_root)
            object_repo = self.make_superproject(object_root, object_bare)
            object_submodule = object_repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=object_submodule, check=True)
            object_source_before = self.source_bytewise_state(object_repo)
            missing_sha = "f" * 40
            (object_bare / "refs" / "heads" / "main").write_text(missing_sha + "\n", encoding="ascii")
            unavailable = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=object_repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unavailable.returncode, 0)
            self.assertIn("agent_canon_plan_route=submodule_remote_object_unavailable", unavailable.stdout)
            self.assertIn(f"agent_canon_plan_remote_sha={missing_sha}", unavailable.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_object_status=unavailable", unavailable.stdout)
            self.assertIn("agent_canon_plan_status=blocked", unavailable.stdout)
            self.assertNotIn("agent_canon_plan_apply_command=", unavailable.stdout)
            self.assertEqual(self.source_bytewise_state(object_repo), object_source_before)
            self.assertIn("agent_canon_plan_remote_probe_cleanup_status=pass", unavailable.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_probe_path=<none>", unavailable.stdout)

    def test_plan_remote_probe_accepts_one_remote_advance_without_source_mutation(self) -> None:
        """A coherent S1/S2 remote advance is selected without touching source Git state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            start_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=work_dir, check=True, capture_output=True, text=True
            ).stdout.strip()
            (work_dir / "remote-race.txt").write_text("race\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-race.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote during probe"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            selected_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=work_dir, check=True, capture_output=True, text=True
            ).stdout.strip()
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            counter = root / "ls-remote-count"
            counter.write_text("0\n", encoding="ascii")
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/usr/bin/env bash\n"
                "if [ \"${1:-}\" = \"ls-remote\" ]; then\n"
                f"  n=$(cat {counter})\n"
                f"  if [ \"$n\" -eq 0 ]; then sha='{start_sha}'; else sha='{selected_sha}'; fi\n"
                "  printf '%s %s\\n' \"$sha\" refs/heads/main\n"
                f"  printf '%s\\n' $((n + 1)) > {counter}\n"
                "  exit 0\n"
                "fi\n"
                "exec /usr/bin/git \"$@\"\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            before = self.source_bytewise_state(repo)
            env = self.unauthorized_env()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            plan = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn(f"agent_canon_plan_remote_snapshot_start_sha={start_sha}", plan.stdout)
            self.assertIn(f"agent_canon_plan_remote_snapshot_selected_sha={selected_sha}", plan.stdout)
            self.assertIn("agent_canon_plan_remote_snapshot_coherence=advanced", plan.stdout)
            self.assertIn("agent_canon_plan_route=submodule_detached_parent_pin", plan.stdout)
            self.assertIn("agent_canon_plan_remote_probe_cleanup_status=pass", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_remote_probe_path=<none>", plan.stdout)
            self.assertEqual(self.source_bytewise_state(repo), before)

    def test_detached_attach_failure_injection_rolls_back_exact_source_state(self) -> None:
        """Fetch, upstream, and readback failures restore pre-attach source state."""
        for phase in ("upstream", "readback", "fetch"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                bare_repo, _work_dir = self.make_agent_canon_remote(root)
                repo = self.make_superproject(root, bare_repo)
                submodule = repo / "vendor/agent-canon"
                subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
                env = authorized_test_env()
                if phase == "fetch":
                    subprocess.run(
                        ["git", "remote", "set-url", "origin", str(root / "missing-origin.git")],
                        cwd=submodule,
                        check=True,
                    )
                else:
                    env["AGENT_CANON_ATTACH_FAIL_PHASE"] = phase
                before_source = self.source_bytewise_state(repo)
                before_parent = self.protected_state(repo)
                result = subprocess.run(
                    ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                    cwd=repo,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("agent_canon_attach_rollback=pass", result.stdout)
                if phase == "fetch":
                    self.assertIn("agent_canon_attach_result=blocked_origin_main_fetch", result.stdout)
                else:
                    self.assertIn(f"agent_canon_attach_result=blocked_injected_{phase}_failure", result.stdout)
                self.assertIn("agent_canon_attach_transaction_cleanup=pass", result.stdout)
                self.assertNotIn("agent_canon_attach_transaction_dir=", result.stdout)
                self.assertEqual(self.source_bytewise_state(repo), before_source)
                self.assertEqual(self.protected_state(repo), before_parent)

    def test_detached_attach_capture_failure_aborts_before_mutation(self) -> None:
        """Capture failure stops before attach and cleans its transaction evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            env = authorized_test_env()
            env["AGENT_CANON_ATTACH_FAIL_PHASE"] = "capture"
            before_source = self.source_bytewise_state(repo)
            before_parent = self.protected_state(repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("agent_canon_attach_result=blocked_transaction_capture_failed", result.stdout)
            self.assertIn("agent_canon_attach_transaction_cleanup=pass", result.stdout)
            self.assertNotIn("agent_canon_attach_transaction_dir=", result.stdout)
            self.assertEqual(self.source_bytewise_state(repo), before_source)
            self.assertEqual(self.protected_state(repo), before_parent)

    def test_detached_attach_rollback_failure_preserves_transaction_evidence(self) -> None:
        """A rollback failure is a distinct hold and retains transaction evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor/agent-canon"
            subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
            env = authorized_test_env()
            env["AGENT_CANON_ATTACH_FAIL_PHASE"] = "upstream"
            env["AGENT_CANON_ATTACH_FAIL_ROLLBACK"] = "1"

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("agent_canon_attach_rollback=fail", result.stdout)
            self.assertIn("agent_canon_attach_rollback_error_kind=injected_failure", result.stdout)
            self.assertIn("agent_canon_attach_result=blocked_rollback_failed", result.stdout)
            self.assertNotIn("agent_canon_attach_transaction_cleanup=pass", result.stdout)
            transaction_lines = [
                line
                for line in result.stdout.splitlines()
                if line.startswith("agent_canon_attach_transaction_dir=")
            ]
            self.assertTrue(transaction_lines, result.stdout)
            transaction_dir = Path(transaction_lines[-1].split("=", 1)[1].strip("'"))
            self.assertTrue(transaction_dir.is_dir(), transaction_dir)
            self.assertTrue((transaction_dir / "objects.before").is_file())

    def test_plan_classifies_malformed_and_multiple_remote_records(self) -> None:
        """Malformed and ambiguous ls-remote output remains typed plan evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/usr/bin/env bash\n"
                "if [ \"${1:-}\" = \"ls-remote\" ]; then\n"
                "  if [ \"${FAKE_LS_REMOTE_MODE:-}\" = \"malformed\" ]; then\n"
                "    printf '%s\\n' 'not-a-sha refs/heads/main'\n"
                "  else\n"
                "    printf '%s\\n' '1111111111111111111111111111111111111111 refs/heads/main'\n"
                "    printf '%s\\n' '2222222222222222222222222222222222222222 refs/heads/main'\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "exec /usr/bin/git \"$@\"\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            for mode, status, error_kind in (
                ("malformed", "malformed", "invalid_object_id"),
                ("ambiguous", "ambiguous", "matching_ref_count"),
            ):
                fixture_root = root / mode
                bare_repo, _work_dir = self.make_agent_canon_remote(fixture_root)
                repo = self.make_superproject(fixture_root, bare_repo)
                submodule = repo / "vendor/agent-canon"
                subprocess.run(["git", "switch", "--detach"], cwd=submodule, check=True)
                env = authorized_test_env()
                env["PATH"] = f"{fake_bin}:{env['PATH']}"
                env["FAKE_LS_REMOTE_MODE"] = mode
                plan = subprocess.run(
                    ["bash", "tools/sync_agent_canon.sh", "plan"],
                    cwd=repo,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                self.assertNotEqual(plan.returncode, 0)
                self.assertIn("agent_canon_plan_route=submodule_remote_resolution_failed", plan.stdout)
                self.assertIn(f"agent_canon_plan_submodule_remote_resolution_status={status}", plan.stdout)
                self.assertIn(f"agent_canon_plan_submodule_remote_error_kind={error_kind}", plan.stdout)
                self.assertIn("agent_canon_plan_status=blocked", plan.stdout)
                self.assertNotIn("agent_canon_plan_apply_command=", plan.stdout)

    def test_pull_redirects_to_ensure_latest_for_submodules(self) -> None:
        """The legacy pull command should use submodule ensure-latest semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "pull"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())

    def test_status_reports_submodule_mode_and_pin(self) -> None:
        """Submodule-add should project parent headers before exposing pin status."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            subprocess.run(
                ["git", "push", "--force", str(bare_repo), "HEAD:refs/heads/main"],
                cwd=REPO_ROOT,
                check=True,
            )
            repo = self.make_superproject(
                root,
                bare_repo,
                public_submodule_add=True,
                commit_submodule=False,
            )

            index_entry = subprocess.run(
                ["git", "ls-files", "--stage", "--", "vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertRegex(index_entry, r"^160000 [0-9a-f]{40} 0\tvendor/agent-canon$")

            issue_templates = sorted(
                path
                for path in (repo / ".github" / "ISSUE_TEMPLATE").iterdir()
                if path.is_file() and not path.is_symlink()
            )
            pull_request_templates = sorted(
                path
                for path in (repo / ".github" / "PULL_REQUEST_TEMPLATE").iterdir()
                if path.is_file() and not path.is_symlink()
            )
            projected_templates = [*issue_templates, *pull_request_templates]
            self.assertEqual(len(issue_templates), 3)
            self.assertEqual(len(pull_request_templates), 1)
            for template in projected_templates:
                body = template.read_text(encoding="utf-8")
                self.assertIn("../../vendor/agent-canon/", body)
                self.assertIn("../../tools/agent-canon/", body)

            format_check = subprocess.run(
                [
                    "bash",
                    str(
                        REPO_ROOT
                        / "tools"
                        / "agent_tools"
                        / "check_dependency_header_format.sh"
                    ),
                    "--root",
                    str(repo),
                    *(path.relative_to(repo).as_posix() for path in projected_templates),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(format_check.returncode, 0, format_check.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", format_check.stdout)

            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "add submodule"], cwd=repo, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "status"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("prefix_mode_name=submodule", result.stdout)
            self.assertIn(f"submodule_url={bare_repo}", result.stdout)
            self.assertRegex(result.stdout, r"submodule_pin=[0-9a-f]{40}")

    def test_snapshot_alias_reports_deprecation(self) -> None:
        """The legacy snapshot alias should advertise link-root as the replacement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "snapshot"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_snapshot_alias=deprecated_use_link_root", result.stdout)

    def test_link_root_keeps_goal_local_and_excludes_agentcanon_workflows(self) -> None:
        """Link-root keeps local state and leaves AgentCanon workflows source-only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            goal_path = repo / "goal.md"
            os.symlink("vendor/agent-canon/goal.md", goal_path)
            workflow_root = repo / ".github" / "workflows"
            workflow_root.mkdir(parents=True, exist_ok=True)
            workflow_paths = {
                workflow: workflow_root / workflow
                for workflow in (
                    "agent-improvement-guide.yml",
                    "agent-coordination.yml",
                )
            }
            os.symlink(
                "missing-agentcanon-workflow",
                workflow_paths["agent-improvement-guide.yml"],
            )
            regular_sentinel = "name: parent-owned workflow\n"
            workflow_paths["agent-coordination.yml"].write_text(
                regular_sentinel,
                encoding="utf-8",
            )

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(goal_path.is_symlink())
            self.assertIn("repo-local goal", goal_path.read_text(encoding="utf-8"))
            self.assertFalse(
                os.path.lexists(workflow_paths["agent-improvement-guide.yml"])
            )
            regular_workflow = workflow_paths["agent-coordination.yml"]
            self.assertTrue(os.path.lexists(regular_workflow))
            self.assertTrue(regular_workflow.is_file())
            self.assertEqual(
                regular_workflow.read_text(encoding="utf-8"),
                regular_sentinel,
            )
            for workflow, path in workflow_paths.items():
                source = (
                    repo
                    / "vendor"
                    / "agent-canon"
                    / ".github"
                    / "workflows"
                    / workflow
                )
                self.assertTrue(source.is_file(), workflow)
            issue_templates = sorted(
                path
                for path in (repo / ".github" / "ISSUE_TEMPLATE").iterdir()
                if path.is_file() and not path.is_symlink()
            )
            pull_request_templates = sorted(
                path
                for path in (repo / ".github" / "PULL_REQUEST_TEMPLATE").iterdir()
                if path.is_file() and not path.is_symlink()
            )
            self.assertEqual(len(issue_templates), 3)
            self.assertEqual(len(pull_request_templates), 1)
            pull_request_body = pull_request_templates[0].read_text(encoding="utf-8")
            self.assertIn("tools/agent-canon/agent_tools/route.py", pull_request_body)
            self.assertNotIn("tools/agent_tools/route.py", pull_request_body)
            self.assertFalse((repo / ".github" / "PULL_REQUEST_TEMPLATE.md").exists())

    def test_link_root_migrates_legacy_vscode_directory_before_child_links(self) -> None:
        """Link-root preserves regular parent editor content after projection retirement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            vscode_dir = repo / ".vscode"
            vscode_dir.mkdir()
            vscode_files = {
                name: f"parent-owned-{name}\n"
                for name in (
                    "c_cpp_properties.json",
                    "extensions.json",
                    "settings.json",
                    "tasks.json",
                )
            }
            for name, content in vscode_files.items():
                (vscode_dir / name).write_text(content, encoding="utf-8")
            subprocess.run(["git", "add", ".vscode"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add parent vscode settings"],
                cwd=repo,
                check=True,
            )

            # Keep this historical fixture, but remove its retired VS Code
            # projection entries before exercising the current contract.
            manifest = repo / "vendor" / "agent-canon" / "documents" / "runtime" / "shared-runtime-surfaces.toml"
            manifest_text = manifest.read_text(encoding="utf-8")
            manifest_text = manifest_text.replace(
                '\n[[surface]]\npath = ".vscode"\nmode = "regular"\n'
                'projection_producer = "template-or-derived-repo"\n'
                'projection_kind = "active_contract"\nsource = ".vscode"\n',
                "\n",
            )
            for name in vscode_files:
                manifest_text = manifest_text.replace(f'  ".vscode/{name}",\n', "")
            manifest.write_text(manifest_text, encoding="utf-8")
            source_doc = manifest.with_name("SHARED_RUNTIME_SURFACES.md")
            source_doc.write_text(
                source_doc.read_text(encoding="utf-8")
                + "\nAGENTS.md\n.codex/config.toml\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(vscode_dir.is_symlink())
            for vscode_name, content in vscode_files.items():
                path = vscode_dir / vscode_name
                self.assertTrue(path.is_file() and not path.is_symlink())
                self.assertEqual(path.read_text(encoding="utf-8"), content)
            self.assertEqual(check.returncode, 0, check.stderr)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "sync vscode shared surface"],
                cwd=repo,
                check=True,
            )
            status = subprocess.run(
                ["git", "status", "--short", "--", ".vscode"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout.strip(), "")

    def test_link_root_materializes_missing_and_legacy_regular_active_contracts(self) -> None:
        """Link-root should seed active-contract docs without keeping legacy symlinks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            readme_path = documents_dir / "README.md"

            result_missing = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result_missing.returncode, 0, result_missing.stderr)
            self.assertFalse(readme_path.is_symlink())
            self.assertIn(
                "Derived Documents Seed",
                readme_path.read_text(encoding="utf-8"),
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            readme_path = documents_dir / "README.md"
            os.symlink("../vendor/agent-canon/documents/README.md", readme_path)
            result_symlink = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result_symlink.returncode, 0, result_symlink.stderr)
            self.assertFalse(readme_path.is_symlink())
            self.assertIn(
                "Derived Documents Seed",
                readme_path.read_text(encoding="utf-8"),
            )

    def test_link_root_removes_standalone_only_root_views(self) -> None:
        """Link-root and check should keep standalone-only docs out of parent roots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            policy_path = documents_dir / "SHARED_RUNTIME_SURFACES.md"
            os.symlink(
                "../vendor/agent-canon/documents/runtime/SHARED_RUNTIME_SURFACES.md",
                policy_path,
            )

            check_before = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(check_before.returncode, 0)
            self.assertIn(
                "absent[documents/runtime/SHARED_RUNTIME_SURFACES.md]=present",
                check_before.stderr,
            )

            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            self.assertFalse(policy_path.exists())
            self.assertFalse(policy_path.is_symlink())

    def test_check_rejects_broken_tracked_root_view_symlink(self) -> None:
        """Check should catch retired tracked symlink views into AgentCanon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            retired = repo / "tests" / "tools" / "test_retired_mirror.py"
            retired.parent.mkdir(parents=True)
            os.symlink(
                "../../vendor/agent-canon/tests/tools/test_retired_mirror.py",
                retired,
            )
            subprocess.run(["git", "add", "tests/tools/test_retired_mirror.py"], cwd=repo, check=True)

            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(check.returncode, 0)
            self.assertIn(
                "root-symlink[tests/tools/test_retired_mirror.py]=broken",
                check.stderr,
            )

    def test_plan_reports_submodule_update_without_root_commit_lookup_errors(self) -> None:
        """Plan should compare submodule commits inside the submodule repo."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertNotIn("Not a valid commit name", plan.stderr)
            self.assertIn("agent_canon_plan_prefix_mode=submodule", plan.stdout)
            self.assertIn("agent_canon_plan_route=submodule_update", plan.stdout)

    def test_latest_updates_clean_submodule_and_reports_tool_completion(self) -> None:
        """The high-level latest command should apply safe submodule updates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("agent_canon_plan_route=submodule_update", latest.stdout)
            self.assertIn("agent_canon_latest=updating_submodule", latest.stdout)
            self.assertIn("shared surface is in sync", latest.stdout)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_rust_manifest", latest.stdout)
            self.assertIn("AGENT_CANON_TOOL_REBUILD=pass", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TODOS=skipped_missing_tool", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=updated", latest.stdout)
            self.assertIn("NEXT_ACTION=run_validation_then_push_parent_repo", latest.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())

    def test_latest_rebases_inherited_temp_through_sync_and_rebuild(self) -> None:
        """A signed inherited runner temp is untouched by nested update handoffs."""
        # Keep this authenticated fixture below the record's physical parent;
        # the signed inherited session must be able to validate every nested
        # Git root before update/sync begins.
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            # The parent fixture includes a tiny rebuild entrypoint so latest
            # exercises the same parent-bound rebuild handoff as a real source
            # checkout without requiring a Rust toolchain in this test.
            shared_surface_doc = (
                work_dir / "documents" / "runtime" / "SHARED_RUNTIME_SURFACES.md"
            )
            with shared_surface_doc.open("a", encoding="utf-8") as document:
                document.write("\nAGENTS.md\n.codex/config.toml\n.codex/agents\n")
            rebuild_script = repo / "tools" / "rebuild_agent_tools.sh"
            rebuild_script.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo AGENT_CANON_REBUILD_OBSERVED_TMPDIR=\"$TMPDIR\"\n"
                "echo AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_rust_manifest\n"
                "echo AGENT_CANON_TOOL_REBUILD=pass\n",
                encoding="utf-8",
            )
            rebuild_script.chmod(0o755)
            subprocess.run(
                [
                    "git",
                    "add",
                    "documents/runtime/SHARED_RUNTIME_SURFACES.md",
                ],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "add rebuild fixture entrypoint"],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)

            outer_temp = root / "outer-runner-temp"
            outer_temp.mkdir()
            outer_sentinel = outer_temp / "runner-sentinel"
            outer_sentinel.write_text("must remain untouched\n", encoding="utf-8")
            outer_latest = outer_temp / "latest"
            env = authorized_test_env()
            env["GIT_ALLOW_PROTOCOL"] = "file"
            env["AGENT_CANON_PARENT_TMPDIR"] = str(outer_latest)
            for name in ("TMPDIR", "TEMP", "TMP"):
                env[name] = str(outer_temp)

            with record_environment(cwd=repo, base_env=env) as signed_env:
                signed_parent_root = Path(
                    signed_env["AGENT_CANON_SIDE_EFFECT_PARENT_ROOT"]
                ).resolve()
                latest = subprocess.run(
                    ["bash", "tools/update_agent_canon.sh", "latest"],
                    cwd=repo,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=signed_env,
                )

            combined_output = f"{latest.stdout}\n{latest.stderr}"
            self.assertEqual(latest.returncode, 0, combined_output)
            self.assertIn("agent_canon_latest=updating_submodule", combined_output)
            self.assertIn("agent_canon_latest_submodule_local_state_checked=yes", combined_output)
            self.assertIn("shared surface is in sync", combined_output)
            self.assertIn("AGENT_CANON_REBUILD_OBSERVED_TMPDIR=", combined_output)
            self.assertIn("AGENT_CANON_TOOL_REBUILD=pass", combined_output)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=updated", combined_output)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())

            nested_sync_tmp = signed_parent_root / ".agent-canon" / "tmp" / "sync"
            boundary_tmp = signed_parent_root / ".agent-canon" / "tmp"
            observed_rebuild_tmp = next(
                line.split("=", 1)[1]
                for line in combined_output.splitlines()
                if line.startswith("AGENT_CANON_REBUILD_OBSERVED_TMPDIR=")
            )
            self.assertTrue(outer_latest.is_dir())
            self.assertTrue(nested_sync_tmp.is_dir())
            self.assertTrue(outer_latest.resolve().is_relative_to(signed_parent_root))
            self.assertTrue(nested_sync_tmp.resolve().is_relative_to(signed_parent_root))
            self.assertNotEqual(outer_latest.resolve(), nested_sync_tmp.resolve())
            self.assertNotEqual(boundary_tmp.resolve(), outer_latest.resolve())
            self.assertEqual(observed_rebuild_tmp, str(boundary_tmp))
            self.assertTrue(Path(observed_rebuild_tmp).resolve().is_relative_to(signed_parent_root))
            self.assertNotEqual(Path(observed_rebuild_tmp).resolve(), outer_latest.resolve())
            self.assertNotEqual(Path(observed_rebuild_tmp).resolve(), outer_temp.resolve())
            self.assertEqual(outer_sentinel.read_text(encoding="utf-8"), "must remain untouched\n")

    def test_rebuild_tools_installs_rust_cli_from_current_submodule(self) -> None:
        """Rebuild-tools should install a Rust CLI matching the current AgentCanon source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            rust_root = submodule / "rust" / "agent-canon"
            fake_bin = root / "fake-bin"
            tools_home = repo / ".agent-canon" / "tools-home"
            rust_root.mkdir(parents=True)
            (rust_root / "Cargo.toml").write_text("[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\nedition = \"2021\"\n", encoding="utf-8")
            fake_bin.mkdir()
            cargo = fake_bin / "cargo"
            cargo.write_text(
                "#!/usr/bin/env bash\n"
                "manifest=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = '--manifest-path' ]; then manifest=\"$2\"; shift 2; else shift; fi\n"
                "done\n"
                "crate_dir=\"$(dirname \"$manifest\")\"\n"
                "mkdir -p \"${CARGO_TARGET_DIR:?}/release\"\n"
                "cat >\"${CARGO_TARGET_DIR:?}/release/agent-canon\" <<'SH'\n"
                "#!/usr/bin/env bash\n"
                "echo 'agent-canon test 0.1.0'\n"
                "SH\n"
                "chmod +x \"${CARGO_TARGET_DIR:?}/release/agent-canon\"\n",
                encoding="utf-8",
            )
            cargo.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["AGENT_CANON_TOOLS_HOME"] = str(tools_home)
            env["CARGO_TARGET_DIR"] = str(repo / ".agent-canon" / "cache" / "cargo-target")
            env["AGENT_CANON_CLI_TARGET_DIR"] = env["CARGO_TARGET_DIR"]
            env["AGENT_CANON_SKIP_USR_LOCAL_LINK"] = "1"

            first = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            time.sleep(1.1)
            (rust_root / "Cargo.toml").write_text(
                "[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\nedition = \"2021\"\n# dirty source\n",
                encoding="utf-8",
            )
            third = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=rebuilt", first.stdout)
            self.assertIn("AGENT_CANON_TOOL_REBUILD=pass", first.stdout)
            self.assertTrue((tools_home / "bin" / "agent-canon").is_symlink())
            self.assertFalse((rust_root / "target").exists())
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=already_current", second.stdout)
            self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
            self.assertIn("AGENT_CANON_TOOL_REBUILD_RUST=rebuilt", third.stdout)

            source_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            parent_gitlink = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(source_commit, parent_gitlink)
            state = (tools_home / "agent-canon" / ".build-state").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"agent_canon_source_commit={parent_gitlink}\n", state)

            (submodule / "provider-drift").write_text("drift\n", encoding="utf-8")
            subprocess.run(["git", "add", "provider-drift"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "commit", "-m", "provider drift"], cwd=submodule, check=True
            )
            mismatch = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "rebuild-tools"],
                cwd=repo,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("provider identity mismatch", mismatch.stderr)

    def test_latest_preserves_dirty_submodule_and_merges_remote_main(self) -> None:
        """Latest should preserve dirty shared canon work while merging remote main."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "config", "user.email", "submodule-test@example.invalid"],
                cwd=submodule,
                check=True,
            )
            (submodule / "local-branch-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-branch-marker.txt"], cwd=submodule, check=True)
            subprocess.run(["git", "commit", "-m", "local branch work"], cwd=submodule, check=True)
            (submodule / "dirty-marker.txt").write_text("dirty\n", encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("agent_canon_plan_route=deferred_branch_pr", latest.stdout)
            self.assertIn("agent_canon_plan_submodule_worktree_status=dirty", latest.stdout)
            self.assertIn("agent_canon_plan_submodule_history_state=diverged", latest.stdout)
            self.assertIn("agent_canon_plan_requires_clean=no", latest.stdout)
            self.assertIn("agent_canon_plan_unresolved_merge_conflict=no", latest.stdout)
            self.assertIn("agent_canon_plan_merge_conflict=no", latest.stdout)
            self.assertIn("agent_canon_plan_materialization_collision=no", latest.stdout)
            self.assertIn("agent_canon_materialization_result=merged_remote", latest.stdout)
            self.assertIn("agent_canon_latest_submodule_applied_status=dirty_preserved", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr", latest.stdout)
            self.assertTrue((submodule / "local-branch-marker.txt").is_file())
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertTrue((submodule / "dirty-marker.txt").is_file())
            self.assertIn("?? dirty-marker.txt", status)
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", remote_sha, "HEAD"],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )

    def test_latest_preserves_noncolliding_eval_logs_in_place(self) -> None:
        """Latest should retain non-colliding eval logs in the source worktree."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            log_path = (
                submodule
                / "agents"
                / "evals"
                / "results"
                / "hook-runs"
                / "derived-devcontainer"
                / "skill_usage.jsonl"
            )
            log_path.parent.mkdir(parents=True)
            log_path.write_text('{"hook_run_id":"local-log","status":"pass"}\n', encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("agent_canon_plan_requires_clean=no", latest.stdout)
            self.assertIn("agent_canon_plan_materialization_collision=no", latest.stdout)
            self.assertIn("agent_canon_latest=updating_submodule", latest.stdout)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=updated", latest.stdout)
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertTrue(log_path.is_file())
            self.assertIn('"hook_run_id":"local-log"', log_path.read_text(encoding="utf-8"))

    def test_plan_ignores_removed_source_repo_override_for_submodule_remote(self) -> None:
        """Submodule plan should keep GitHub-first submodule remote semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            removed_source_repo = root / "new" / "agent-canon-work"
            repo = self.make_superproject(root, old_bare_repo)

            env = {
                **os.environ,
                "AGENT_CANON_SOURCE_REPO": str(removed_source_repo),
                "AGENT_CANON_REMOTE_URL": str(old_bare_repo),
            }
            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertNotIn("agent_canon_plan_effective_remote_url=", plan.stdout)
            self.assertIn("agent_canon_plan_remote_source=submodule", plan.stdout)
            self.assertIn(f"agent_canon_plan_remote_url={old_bare_repo}", plan.stdout)
            self.assertIn("agent_canon_plan_route=already_current_submodule", plan.stdout)

    def test_latest_check_reports_clean_submodule_worktree_at_remote_with_stale_parent_pin(
        self,
    ) -> None:
        """A stale parent gitlink is a hard blocker unless update is applied."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "fetch", "origin", "main"], cwd=submodule, check=True)
            subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=submodule, check=True)
            (repo / "UNRELATED_ROOT_FILE").write_text("dirty parent\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_LATEST=fail", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_REASON=submodule-gitlink-worktree-mismatch", result.stdout)
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--", "vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(staged.stdout.strip(), "")

    def test_latest_check_accepts_non_main_reachable_submodule_pin(self) -> None:
        """A clean reachable non-main branch pin can remain PR work and still pass latest CI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "push",
                    "origin",
                    "HEAD:refs/heads/agent-canon-local-ahead",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin local proposal"], cwd=repo, check=True)

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_LATEST=pass", result.stdout)
            self.assertRegex(result.stdout, r"AGENT_CANON_LATEST_ROUTE=(local_contains_remote|deferred_branch_pr)")

    def test_latest_check_fails_when_parent_pin_worktree_mismatch(self) -> None:
        """A submodule pin mismatch is an actionable blocker until ensure-latest is run."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            original_parent_pin = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin-stale"], cwd=repo, check=True)
            # Leave the submodule one commit ahead, so gitlink no longer matches.
            subprocess.run(["git", "switch", "-"], cwd=submodule, check=True)
            subprocess.run(["git", "checkout", original_parent_pin[:7]], cwd=submodule, check=True)

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST=fail", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_REASON=submodule-gitlink-worktree-mismatch", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence", result.stdout)

    def test_latest_check_fails_when_pinned_commit_unreachable_from_configured_remote(self) -> None:
        """A reachable local pin is required for ordinary latest CI; unreachable pins block CI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "pinless-marker.txt").write_text("proposed\n", encoding="utf-8")
            subprocess.run(["git", "add", "pinless-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "pinless marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin to unpushed commit"], cwd=repo, check=True)

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST=fail", result.stdout)
            self.assertIn(
                "AGENT_CANON_LATEST_REASON=submodule-pinned-commit-unreachable-from-configured-remote",
                result.stdout,
            )
            self.assertIn("AGENT_CANON_LATEST_NEXT_ACTION=run_make_agent-canon-ensure-latest_then_commit_updated_submodule_pin_with_request_evidence", result.stdout)

    def test_latest_defers_clean_pushed_agentcanon_branch_pin(self) -> None:
        """A clean pushed AgentCanon branch head is deferred to the AgentCanon PR."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin pushed proposal"], cwd=repo, check=True)
            subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "add", "AGENTS.md", ".github", ".vscode", "documents/README.md", "goal.md"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "sync root views"], cwd=repo, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            ensure_latest = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest_check = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=deferred_branch_pr", plan.stdout)
            self.assertIn("agent_canon_plan_submodule_local_state_checked=yes", plan.stdout)
            self.assertIn(
                "agent_canon_plan_submodule_deferred_branch=canon-pr/local-work",
                plan.stdout,
            )
            self.assertIn(
                "agent_canon_plan_submodule_deferred_remote_branch=origin/canon-pr/local-work",
                plan.stdout,
            )
            self.assertEqual(ensure_latest.returncode, 0, ensure_latest.stderr)
            self.assertIn(
                "agent_canon_latest_submodule_local_state_checked=yes",
                ensure_latest.stdout,
            )
            self.assertIn("agent_canon_latest=deferred_branch_pr", ensure_latest.stdout)
            self.assertIn("agent_canon_latest_branch=canon-pr/local-work", ensure_latest.stdout)
            self.assertIn(
                "agent_canon_latest_remote_branch=origin/canon-pr/local-work",
                ensure_latest.stdout,
            )
            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr", latest.stdout)
            self.assertIn(
                "NEXT_ACTION=after_agentcanon_PR_merge_rerun_make_agent-canon-ensure-latest",
                latest.stdout,
            )
            self.assertEqual(latest_check.returncode, 0, latest_check.stdout + latest_check.stderr)
            self.assertIn("AGENT_CANON_LATEST=pass", latest_check.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=deferred_branch_pr", latest_check.stdout)

    def test_latest_defers_clean_pushed_agentcanon_branch_when_parent_pin_is_stale(self) -> None:
        """A deferred AgentCanon branch context still fails when parent gitlink is stale."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                AGENT_CANON_SOURCE_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            initial_parent_pin = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/worktree-only"],
                cwd=submodule,
                check=True,
            )
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "canon-pr/worktree-only"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "add", "AGENTS.md", ".github", ".vscode", "documents/README.md", "goal.md"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "sync root views"], cwd=repo, check=True)
            subprocess.run(
                [
                    "git",
                    "update-index",
                    "--cacheinfo",
                    f"160000,{initial_parent_pin},vendor/agent-canon",
                ],
                cwd=repo,
                check=True,
            )
            if subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", "vendor/agent-canon"],
                cwd=repo,
                check=False,
            ).returncode != 0:
                subprocess.run(
                    ["git", "commit", "-m", "keep stale agent canon parent pin"],
                    cwd=repo,
                    check=True,
                )

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            ensure_latest = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            latest_check = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=deferred_branch_pr", plan.stdout)
            self.assertIn(
                "agent_canon_plan_submodule_deferred_branch=canon-pr/worktree-only",
                plan.stdout,
            )
            self.assertEqual(ensure_latest.returncode, 0, ensure_latest.stderr)
            self.assertIn("agent_canon_latest=deferred_branch_pr", ensure_latest.stdout)
            self.assertIn("agent_canon_latest_branch=canon-pr/worktree-only", ensure_latest.stdout)
            self.assertIn("agent_canon_latest_parent_pin_status=stale", ensure_latest.stdout)
            self.assertNotIn("local_submodule_worktree_differs_from_parent_pin", ensure_latest.stdout)
            self.assertEqual(latest.returncode, 0, latest.stdout + latest.stderr)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=deferred_branch_pr", latest.stdout)
            self.assertNotEqual(latest_check.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST=fail", latest_check.stdout)
            self.assertIn(
                "AGENT_CANON_LATEST_REASON=submodule-gitlink-worktree-mismatch",
                latest_check.stdout,
            )

    def test_apply_updates_submodule_pin_with_untracked_root_file(self) -> None:
        """Apply should update the gitlink without requiring unrelated root cleanup."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)
            (repo / "UNTRACKED_ROOT_FILE").write_text("root dirty\n", encoding="utf-8")

            apply = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "apply"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", apply.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("?? UNTRACKED_ROOT_FILE", status)

    def test_ensure_latest_does_not_commit_dirty_regular_active_contract(self) -> None:
        """Submodule updates should not sweep template-owned active contracts into sync commits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add generated root views"],
                cwd=repo,
                check=True,
            )
            (repo / "documents" / "README.md").write_text(
                "# Locally Edited Documents\n",
                encoding="utf-8",
            )
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--", "documents/README.md"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            committed_paths = subprocess.run(
                ["git", "show", "--name-only", "--format=", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertEqual(status, " M documents/README.md\n")
            self.assertNotIn("documents/README.md", committed_paths)

    def test_ensure_latest_defers_unpinned_local_submodule_commits(self) -> None:
        """Ensure-latest should preserve and defer committed local history."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "local-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "local marker",
                ],
                cwd=submodule,
                check=True,
            )
            local_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            after_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("agent_canon_latest_submodule_history_state=ahead", result.stdout)
            self.assertIn("agent_canon_latest_parent_pin_status=stale", result.stdout)
            self.assertIn("agent_canon_materialization_collision=no", result.stdout)
            self.assertIn("agent_canon_latest=deferred_branch_pr", result.stdout)
            self.assertEqual(after_head, local_head)

    def test_ensure_latest_rejects_origin_main_expected_mismatch(self) -> None:
        """Ensure-latest should reject mismatched origin/main without changing Git state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            new_bare_repo, new_work_dir = self.make_agent_canon_remote(root / "new")
            repo = self.make_superproject(root, old_bare_repo)
            subprocess.run(
                [
                    "git",
                    "config",
                    "-f",
                    ".gitmodules",
                    "submodule.vendor/agent-canon.url",
                    str(new_bare_repo),
                ],
                cwd=repo,
                check=True,
            )
            (new_work_dir / "new-remote-marker.txt").write_text("new remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "new-remote-marker.txt"], cwd=new_work_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "advance new remote"],
                cwd=new_work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=new_work_dir, check=True)
            before = self.protected_state(repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("origin/main", result.stderr)
            self.assertIn("does not match expected", result.stderr)
            self.assertFalse(
                (repo / "vendor" / "agent-canon" / "new-remote-marker.txt").exists()
            )
            self.assertEqual(self.protected_state(repo), before)

    def test_merge_main_into_current_merges_remote_main_into_local_branch(self) -> None:
        """Merge-main should merge GitHub main into the current AgentCanon branch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=submodule, check=True)
            subprocess.run(
                ["git", "config", "user.email", "submodule-test@example.invalid"],
                cwd=submodule,
                check=True,
            )
            (submodule / "local-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-marker.txt"], cwd=submodule, check=True)
            subprocess.run(["git", "commit", "-m", "local branch work"], cwd=submodule, check=True)
            local_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            post_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(merge.returncode, 0, merge.stderr)
            self.assertIn("agent_canon_merge_result=merged", merge.stdout)
            self.assertIn("agent_canon_merge_source_sha=", merge.stdout)
            self.assertIn("agent_canon_merge_remote_main_in_post_head=yes", merge.stdout)
            self.assertIn("agent_canon_merge_remote_main_verified=yes", merge.stdout)
            self.assertIn("agent_canon_parent_pin_pending=yes", merge.stdout)
            self.assertIn("NEXT_ACTION=run_validation_then_push_current_agentcanon_branch", merge.stdout)
            self.assertTrue((submodule / "local-marker.txt").is_file())
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", local_sha, post_sha],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", remote_sha, post_sha],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )

    def test_merge_main_into_current_preserves_noncolliding_dirty_submodule(self) -> None:
        """Merge-main should merge around non-colliding uncommitted work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            (submodule / "dirty-marker.txt").write_text("dirty\n", encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
            self.assertIn("agent_canon_merge_worktree_status=dirty", merge.stdout)
            self.assertIn("agent_canon_merge_merge_conflict=no", merge.stdout)
            self.assertIn("agent_canon_merge_materialization_collision=no", merge.stdout)
            self.assertIn("agent_canon_merge_result=fast_forwarded", merge.stdout)
            self.assertIn("agent_canon_merge_local_changes=preserved", merge.stdout)
            self.assertTrue((submodule / "dirty-marker.txt").is_file())
            self.assertTrue((submodule / "remote-marker.txt").is_file())

    def test_merge_main_into_current_never_autostashes_when_configured(self) -> None:
        """The explicit no-autostash merge flag preserves dirty state and stash refs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            subprocess.run(["git", "config", "merge.autoStash", "true"], cwd=submodule, check=True)
            dirty_readme = "# Dirty local change\n"
            (submodule / "README.md").write_text(dirty_readme, encoding="utf-8")
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            stash_list = subprocess.run(
                ["git", "stash", "list"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
            self.assertIn("agent_canon_merge_result=fast_forwarded", merge.stdout)
            self.assertEqual((submodule / "README.md").read_text(encoding="utf-8"), dirty_readme)
            self.assertTrue((submodule / "remote-marker.txt").is_file())
            self.assertEqual(stash_list, "")

    def test_latest_collision_blocks_current_checkout_without_workspace_clone(self) -> None:
        """A typed collision blocks the current checkout and never prepares a clone."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            git_exclude = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            exclude_path = Path(git_exclude)
            if not exclude_path.is_absolute():
                exclude_path = submodule / exclude_path
            exclude_path.write_text("collision.txt\n", encoding="utf-8")
            (submodule / "collision.txt").write_text("local collision\n", encoding="utf-8")
            (work_dir / "collision.txt").write_text("remote collision\n", encoding="utf-8")
            subprocess.run(["git", "add", "collision.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "remote collision"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)

            latest = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(latest.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST_TOOL_RESULT=blocked_current_checkout", latest.stdout)
            self.assertIn(
                "NEXT_ACTION=resolve_agentcanon_materialization_collision_or_merge_conflict_in_current_checkout_then_rerun_latest",
                latest.stdout,
            )
            self.assertNotIn("NEXT_ACTION=prepare_topic_workspace_source_clone", latest.stdout)
            self.assertFalse((root / "workspace").exists())

    def test_merge_main_into_current_blocks_materialization_collision(self) -> None:
        """Merge-main should block an uncommitted path in the remote write set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            local_readme = "# Local uncommitted change\n"
            (submodule / "README.md").write_text(local_readme, encoding="utf-8")
            (work_dir / "README.md").write_text("# Remote update\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            before_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            after_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_materialization_collision=yes", merge.stdout)
            self.assertIn("agent_canon_merge_materialization_collision_path=README.md", merge.stdout)
            self.assertIn("agent_canon_merge_result=blocked_unpreservable_collision", merge.stdout)
            self.assertEqual(after_head, before_head)
            self.assertEqual((submodule / "README.md").read_text(encoding="utf-8"), local_readme)

    def test_merge_main_into_current_blocks_ignored_untracked_collision(self) -> None:
        """Ignored untracked paths must remain protected from remote materialization."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "switch", "-c", "canon-pr/local-work"], cwd=submodule, check=True)
            git_exclude = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            exclude_path = Path(git_exclude)
            if not exclude_path.is_absolute():
                exclude_path = submodule / exclude_path
            exclude_path.write_text("ignored-overwrite.txt\n", encoding="utf-8")
            local_content = "ignored local materialization\n"
            (submodule / "ignored-overwrite.txt").write_text(local_content, encoding="utf-8")
            self.assertEqual(
                subprocess.run(
                    ["git", "check-ignore", "--quiet", "ignored-overwrite.txt"],
                    cwd=submodule,
                    check=False,
                ).returncode,
                0,
            )
            (work_dir / "ignored-overwrite.txt").write_text(
                "remote materialization\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "ignored-overwrite.txt"], cwd=work_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add ignored candidate"],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=submodule_materialization_collision", plan.stdout)
            self.assertIn("agent_canon_plan_merge_conflict=no", plan.stdout)
            self.assertIn("agent_canon_plan_materialization_collision=yes", plan.stdout)
            self.assertIn(
                "agent_canon_plan_materialization_collision_path=ignored-overwrite.txt",
                plan.stdout,
            )

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_worktree_status=clean", merge.stdout)
            self.assertIn("agent_canon_merge_materialization_collision=yes", merge.stdout)
            self.assertIn(
                "agent_canon_merge_materialization_collision_path=ignored-overwrite.txt",
                merge.stdout,
            )
            self.assertIn("agent_canon_merge_result=blocked_unpreservable_collision", merge.stdout)
            self.assertEqual(
                (submodule / "ignored-overwrite.txt").read_text(encoding="utf-8"),
                local_content,
            )

    def test_merge_main_into_current_blocks_dirty_local_rename_destination(self) -> None:
        """Virtual merge write paths must include a committed local rename destination."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            (work_dir / "a.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "add rename source"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "mv", "a.txt", "b.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "rename a to b",
                ],
                cwd=submodule,
                check=True,
            )
            local_content = "one\ntwo\nthree\nfour\nlocal dirty destination\n"
            (submodule / "b.txt").write_text(local_content, encoding="utf-8")
            (work_dir / "a.txt").write_text("one\ntwo remote\nthree\nfour\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=work_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "update rename source"],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=submodule_materialization_collision", plan.stdout)
            self.assertIn("agent_canon_plan_merge_conflict=no", plan.stdout)
            self.assertIn("agent_canon_plan_materialization_collision_path=b.txt", plan.stdout)

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_merge_conflict=no", merge.stdout)
            self.assertIn("agent_canon_merge_materialization_collision=yes", merge.stdout)
            self.assertIn("agent_canon_merge_materialization_collision_path=b.txt", merge.stdout)
            self.assertIn("agent_canon_merge_result=blocked_unpreservable_collision", merge.stdout)
            self.assertEqual((submodule / "b.txt").read_text(encoding="utf-8"), local_content)
            self.assertFalse((submodule / "a.txt").exists())

    def test_merge_main_into_current_blocks_virtual_merge_conflict(self) -> None:
        """Committed divergence should fail with a typed virtual-merge conflict."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(
                ["git", "switch", "-c", "canon-pr/local-work"],
                cwd=submodule,
                check=True,
            )
            (submodule / "README.md").write_text("# Local committed update\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "local readme update",
                ],
                cwd=submodule,
                check=True,
            )
            (work_dir / "README.md").write_text("# Remote committed update\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "remote readme update"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=submodule_merge_conflict", plan.stdout)
            self.assertIn("agent_canon_plan_merge_conflict=yes", plan.stdout)
            self.assertIn(
                "agent_canon_plan_merge_conflict_type=virtual_merge_result",
                plan.stdout,
            )
            self.assertIn("agent_canon_plan_materialization_collision=no", plan.stdout)

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            conflict_paths = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_unresolved_merge_conflict=no", merge.stdout)
            self.assertIn("agent_canon_merge_merge_conflict=yes", merge.stdout)
            self.assertIn("agent_canon_merge_conflict_type=virtual_merge_result", merge.stdout)
            self.assertIn("agent_canon_merge_result=blocked_merge_conflict", merge.stdout)
            self.assertEqual(conflict_paths, [])

    def test_merge_main_into_current_blocks_detached_submodule(self) -> None:
        """Merge-main should require a named AgentCanon branch for PR flow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "checkout", "--detach"], cwd=submodule, check=True)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote main"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            merge = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "merge-main-into-current"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(merge.returncode, 0)
            self.assertIn("agent_canon_merge_result=blocked_detached_head", merge.stdout)
            self.assertIn(
                "NEXT_ACTION=request_user_direction_preserve_current_checkout_then_rerun_with_inline_git_authority_and_reason",
                merge.stdout,
            )

    def test_removed_proposal_command_is_not_user_facing(self) -> None:
        """The GitHub-first wrapper should reject removed proposal commands."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            push = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "push-proposal", "canon-proposal/test"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(push.returncode, 0)
            self.assertIn("unknown subcommand 'push-proposal'", push.stderr)

    def test_sync_push_refuses_default_branch_for_submodule(self) -> None:
        """Low-level sync push should not directly update AgentCanon main by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            push = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "push", "main"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(push.returncode, 0)
            self.assertIn("submodule push to 'main' is forbidden", push.stderr)

    def test_apply_updates_submodule_pin_after_main_contains_branch_work(self) -> None:
        """Apply should update the pin after GitHub main contains the branch work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "merge proposal marker"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            self.materialize_parent_projection_frontier(repo, work_dir)
            remote_sha = subprocess.run(
                ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            apply = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "apply"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            pinned_sha = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", apply.stdout)
            self.assertEqual(pinned_sha, remote_sha)


class StandaloneUpdateLifecycleTest(unittest.TestCase):
    """Exercise the single standalone queue/frontier transaction entry."""

    def make_source_repo(self, root: Path) -> tuple[Path, Path]:
        """Create a local source clone and local main remote with lifecycle tools."""
        source = root / "source"
        remote = root / "origin.git"
        source.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.name", "Lifecycle Test"], cwd=source, check=True)
        subprocess.run(
            ["git", "config", "user.email", "lifecycle@example.invalid"],
            cwd=source,
            check=True,
        )
        tool_dir = source / "tools" / "agent_tools"
        tool_dir.mkdir(parents=True)
        repo_lib_dir = source / "tools" / "lib"
        repo_lib_dir.mkdir(parents=True)
        shutil.copy2(AGENT_CANON_SOURCE_ROOT / "tools" / "update_agent_canon.sh", source / "tools")
        for name in (
            "artifact_identity.py",
            "parent_root_side_effects.py",
            "update_lifecycle_contract.py",
        ):
            shutil.copy2(AGENT_CANON_SOURCE_ROOT / "tools" / "agent_tools" / name, tool_dir / name)
        shutil.copy2(AGENT_CANON_SOURCE_ROOT / "tools" / "lib" / "repo_paths.sh", repo_lib_dir / "repo_paths.sh")
        shutil.copy2(
            AGENT_CANON_SOURCE_ROOT / "tools" / "lib" / "update_materialization.sh",
            repo_lib_dir / "update_materialization.sh",
        )
        shutil.copy2(
            AGENT_CANON_SOURCE_ROOT / "tools" / "lib" / "git_authority.sh",
            repo_lib_dir / "git_authority.sh",
        )
        shutil.copy2(
            AGENT_CANON_SOURCE_ROOT / "tools" / "sync_agent_canon.sh",
            source / "tools" / "sync_agent_canon.sh",
        )
        (source / "ROOT_AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "fixture source"], cwd=source, check=True)
        subprocess.run(["git", "init", "--bare", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=source, check=True)
        subprocess.run(
            ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
        )
        return source, remote

    def binding_and_rebind(self, source: Path) -> tuple[dict[str, object], dict[str, object]]:
        """Return one exact binding and immutable pre-freeze rebind receipt."""
        candidate = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        binding: dict[str, object] = {
            "transaction_id": "tx:" + "1" * 64,
            "snapshot_id": "snapshot:" + "2" * 64,
            "candidate_sha": candidate,
            "tree_sha": tree,
            "input_digest": "sha256:" + "3" * 64,
            "tool_id": "update-agent-canon",
            "tool_version": "test.v1",
            "evidence_ref": "evidence:" + "4" * 64,
            "evidence_digest": "sha256:" + "5" * 64,
            "timing": {
                "started_at": "2026-07-18T00:00:00Z",
                "finished_at": "2026-07-18T00:00:00Z",
                "last_attempt_at": "2026-07-18T00:00:00Z",
                "duration_ms": 0,
                "attempt": 1,
                "replayed": False,
            },
        }
        base = {
            "remote": "origin",
            "ref": "refs/heads/main",
            "commit_sha": candidate,
            "tree_sha": tree,
        }
        rebind = materialize_source_main_rebind_receipt(
            binding=binding,
            old_base_identity=base,
            new_base_identity=base,
            origin_main_readback_evidence_ref="evidence:" + "6" * 64,
        )
        return binding, rebind

    def source_projection_packet(
        self,
        binding: dict[str, object],
        rebind: dict[str, object],
        *,
        publication_sha: str | None = None,
        publication_tree: str | None = None,
    ) -> dict[str, object]:
        """Materialize one exact merged-source packet for the sole `latest` entry."""
        candidate = str(binding["candidate_sha"])
        tree = str(binding["tree_sha"])
        merge_sha = publication_sha or candidate
        merge_tree = publication_tree or tree
        rebind_id = str(rebind["rebind_receipt_id"])
        cas_evidence_ref = "evidence:" + "a" * 64
        cas_binding = dict(binding)
        cas_binding["evidence_ref"] = cas_evidence_ref
        cas_binding["evidence_digest"] = "sha256:" + "a" * 64
        cas = {
            "schema": "agent-canon.candidate-cas-receipt.v1",
            "cas_receipt_id": "cas:" + "b" * 64,
            "binding": cas_binding,
            "predecessor_evidence_id": binding["evidence_ref"],
            "rebind_receipt_evidence_id": rebind_id,
            "candidate_identity": {
                "candidate_sha": candidate,
                "tree_sha": tree,
            },
            "cas_base_identity": {"commit_sha": candidate, "tree_sha": tree},
            "cas_evidence_ref": cas_evidence_ref,
            "cas_stage": "cas",
        }
        lifecycle_binding = dict(binding)
        lifecycle_binding["evidence_ref"] = "evidence:" + "c" * 64
        lifecycle_binding["evidence_digest"] = "sha256:" + "c" * 64
        lifecycle = {
            "schema": "agent-canon.pull-request-lifecycle.v1",
            "kind": "user",
            "binding": lifecycle_binding,
            "state": "merged",
            "remote_identity": {
                "repo_owner": "owner",
                "repo_name": "agent-canon",
                "remote_name": "origin",
                "url_digest": "sha256:" + "d" * 64,
                "ref": "refs/heads/canon/update-lifecycle",
                "commit_sha": candidate,
                "tree_sha": tree,
            },
            "base_identity": {
                "repo_owner": "owner",
                "repo_name": "agent-canon",
                "ref": "refs/heads/main",
                "commit_sha": candidate,
                "tree_sha": tree,
            },
            "head_identity": {
                "repo_owner": "owner",
                "repo_name": "agent-canon",
                "ref": "refs/heads/canon/update-lifecycle",
                "commit_sha": candidate,
                "tree_sha": tree,
            },
            "branch": pull_request_branch_table(),
            "permission_identity": {
                "actor_id": "github-user:7",
                "permission_state": "verified_true",
                "permission_evidence_id": "evidence:" + "e" * 64,
                "authority_source": "fixture GitHub readback",
                "assumption_forbidden": True,
            },
            "pr_essence": {
                "problem": "project merged source transaction",
                "intent": "queue exact source publication",
                "canonical_owner": "tools/update_agent_canon.sh",
                "contract_delta": "single-entry source projection",
                "evidence_refs": ["evidence:" + "f" * 64],
            },
            "reviews": [],
            "user_identity": {
                "actor_id": "github-user:7",
                "display_name": "Lifecycle Test",
            },
        }
        readback = materialize_publication_readback_receipt(
            candidate_cas_receipt=cas,
            pull_request_lifecycle=lifecycle,
            authoritative_pr_readback={
                "number": 390,
                "state": "MERGED",
                "baseRefName": "main",
                "baseRefOid": merge_sha,
                "mergeCasBaseOid": candidate,
                "mergeCasBaseTreeOid": tree,
                "headRefName": "canon/update-lifecycle",
                "headRefOid": candidate,
                "headRepository": {"nameWithOwner": "owner/agent-canon"},
                "mergeCommit": {"oid": merge_sha},
                "mergeTreeOid": merge_tree,
            },
        )
        g1 = materialize_gate_verdict(
            binding=binding,
            gate_id="G1",
            ordered_input_evidence_refs=[str(binding["evidence_ref"])],
            invariant="source_correctness",
            output_digest="sha256:" + "2" * 64,
            owner=str(AGENT_CANON_SOURCE_ROOT / "tools" / "agent_tools" / "publication_integrator.py")
            + "#resolve_publication_eligibility",
            verdict="pass",
        )
        g2 = materialize_generated_completeness_receipt(
            g1_gate=g1,
            candidate_sha=candidate,
            tree_sha=tree,
            check_results=[
                {"check_id": check_id, "status": "pass"}
                for check_id in GENERATED_COMPLETENESS_CHECK_IDS
            ],
        )
        g3 = materialize_pr_identity_gate(
            lifecycle,
            cas,
            rebind,
            [g1, g2],
        )
        return materialize_source_projection_packet(
            binding=binding,
            source_main_rebind_receipt=rebind,
            candidate_cas_receipt=cas,
            pull_request_lifecycle=lifecycle,
            publication_readback_receipt=readback,
            source_gate_verdicts=[g1, g2, g3],
            ordered_predecessor_evidence=[
                {
                    "queue_number": 388,
                    "source_pr": "#388",
                    "publication_evidence_id": "evidence:" + "5" * 64,
                },
                {
                    "queue_number": 389,
                    "source_pr": "#389",
                    "source_pr_sha": "6" * 40,
                    "publication_evidence_id": "evidence:" + "7" * 64,
                },
            ],
            acceptance_evidence_ref="evidence:" + "8" * 64,
        )

    def test_latest_materializes_queue_and_frontier_once_from_source_packet(self) -> None:
        """The sole source entry queues and accepts one exact publication packet."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, remote = self.make_source_repo(root)
            binding, rebind = self.binding_and_rebind(source)
            (source / "publication-marker.txt").write_text(
                "authoritative merge result\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "add", "publication-marker.txt"], cwd=source, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "authoritative publication merge"],
                cwd=source,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=source, check=True)
            publication_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            publication_tree = subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"],
                cwd=source,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            owner_namespace = source / ".agent-canon" / "update-lifecycle"
            packet_path = owner_namespace / "state" / "source-publication-ready.json"
            packet_path.parent.mkdir(parents=True)
            packet_path.write_text(
                json.dumps(
                    self.source_projection_packet(
                        binding,
                        rebind,
                        publication_sha=publication_sha,
                        publication_tree=publication_tree,
                    )
                ),
                encoding="utf-8",
            )
            unknown_sibling = source / ".agent-canon" / "shared" / "sentinel"
            unknown_sibling.parent.mkdir(parents=True)
            unknown_sibling.write_text("preserve\n", encoding="utf-8")
            env = os.environ.copy()
            for name in tuple(env):
                if name.startswith("AGENT_CANON_") or name in {
                    "TMPDIR", "TEMP", "TMP", "XDG_CACHE_HOME",
                    "PYTHONPYCACHEPREFIX", "CARGO_HOME", "CARGO_TARGET_DIR",
                }:
                    env.pop(name)
            fixture_tmp = source / ".agent-canon" / "tmp" / "lifecycle-test"
            fixture_cache = source / ".agent-canon" / "cache" / "lifecycle-test"
            fixture_tmp.mkdir(parents=True)
            fixture_cache.mkdir(parents=True)
            env.update({
                "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "agent_canon_workflow",
                "AGENT_CANON_BRANCH_WORKTREE_REASON": "frontier test",
                "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
                "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "frontier test",
                "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": COMMIT_REQUEST_EVIDENCE,
                "TMPDIR": str(fixture_tmp),
                "TEMP": str(fixture_tmp),
                "TMP": str(fixture_tmp),
                "XDG_CACHE_HOME": str(fixture_cache / "xdg"),
                "PYTHONPYCACHEPREFIX": str(fixture_cache / "pycache"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "CARGO_HOME": str(fixture_cache / "cargo-home"),
                "CARGO_TARGET_DIR": str(fixture_cache / "cargo-target"),
            })
            command = ["bash", "tools/update_agent_canon.sh", "latest"]
            first = subprocess.run(
                command,
                cwd=source,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            replay = subprocess.run(
                command,
                cwd=source,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assertIn("AGENT_CANON_QUEUE_REPLAYED=true", replay.stdout)
            frontier = json.loads(
                (owner_namespace / "projection-queue" / "frontier.accepted.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(frontier["frontier_state"], "accepted")
            self.assertEqual(
                [item["source_pr"] for item in frontier["ordered_predecessor_evidence"]],
                ["#388", "#389"],
            )
            self.assertIn("AGENT_CANON_FRONTIER_REPLAYED=true", replay.stdout)
            self.assertEqual(unknown_sibling.read_text(encoding="utf-8"), "preserve\n")


if __name__ == "__main__":
    unittest.main()
