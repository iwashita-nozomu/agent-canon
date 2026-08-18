"""Tests for fail-closed parent PR dependency graph selection."""

# @dependency-start
# contract test
# responsibility Verifies canonical selection, trusted diff bases, changed-responsibility reachability, and typed graph failures.
# upstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py selects parent strict graph gating
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh prepares and passes the trusted GitHub base
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json owns canonical validation profile IDs and graph requirements
# upstream design ../../documents/design/dependency-manifest-design.md owns canonical dependency surfaces
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTOR_PATH = PROJECT_ROOT / "tools" / "ci" / "agent_canon_pr_graph_selector.py"
CHECKER_PATH = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
SPEC = importlib.util.spec_from_file_location(
    "agent_canon_pr_graph_selector", SELECTOR_PATH
)
assert SPEC is not None and SPEC.loader is not None
selector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selector
SPEC.loader.exec_module(selector)
FIXTURE_PRODUCER_IDENTITY = selector.current_producer_identity(PROJECT_ROOT)


def git(root: Path, *args: str, input_text: str | None = None) -> str:
    """Run one Git fixture command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    )
    return result.stdout.strip()


def commit_change(root: Path, relative: str) -> str:
    """Create a two-commit fixture and return the base commit."""
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "selector@example.invalid")
    git(root, "config", "user.name", "Selector Fixture")
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("before\n", encoding="utf-8")
    git(root, "add", relative)
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    path.write_text("after\n", encoding="utf-8")
    git(root, "add", relative)
    git(root, "commit", "-m", "change")
    return base


def shallow_pr_checkout(root: Path) -> tuple[Path, Path, str]:
    """Create a depth-one PR checkout, event payload, and missing base SHA."""
    source = root / "source"
    source.mkdir()
    base = commit_change(source, "vendor/agent-canon")
    remote = root / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    checkout = root / "checkout"
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            "main",
            remote.as_uri(),
            str(checkout),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    event = root / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"base": {"sha": base}}}),
        encoding="utf-8",
    )
    return checkout, event, base


def graph_change_fixture(root: Path, extra_base_files: dict[str, str]) -> str:
    """Create one changed path plus unchanged base-owned graph sources."""
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "selector@example.invalid")
    git(root, "config", "user.name", "Selector Fixture")
    (root / "changed.py").write_text("before\n", encoding="utf-8")
    for relative, content in extra_base_files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    (root / "changed.py").write_text("after\n", encoding="utf-8")
    git(root, "add", "changed.py")
    git(root, "commit", "-m", "change")
    return base


def derived_parent_graph_fixture(root: Path) -> tuple[Path, str, str]:
    """Create a derived parent whose base contains an AgentCanon gitlink."""
    parent = root / "derived-parent"
    parent.mkdir()
    git(parent, "init", "-b", "main")
    git(parent, "config", "user.email", "selector@example.invalid")
    git(parent, "config", "user.name", "Selector Fixture")
    git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        PROJECT_ROOT.as_uri(),
        "vendor/agent-canon",
    )
    manifest = parent / "documents" / "runtime" / "shared-runtime-surfaces.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "documents" / "runtime" / "shared-runtime-surfaces.toml",
        manifest,
    )
    (parent / "changed.py").write_text("before\n", encoding="utf-8")
    git(parent, "add", ".")
    git(parent, "commit", "-m", "derived parent base")
    base = git(parent, "rev-parse", "HEAD")
    gitlink = git(parent, "ls-tree", "HEAD", "vendor/agent-canon").split()[2]
    (parent / "changed.py").write_text("after\n", encoding="utf-8")
    git(parent, "add", "changed.py")
    git(parent, "commit", "-m", "derived parent change")
    return parent, base, gitlink


def graph_builder_exit_fixture(
    root: Path,
    process_exit_code: int,
    result_exit_code: int,
) -> tuple[Path, Path, str]:
    """Create a base repo and builder executable with independently chosen exits."""
    parent = root / "base-repo"
    parent.mkdir()
    manifest = parent / "documents" / "runtime" / "shared-runtime-surfaces.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        'version = 1\n'
        'prefix = "vendor/agent-canon"\n'
        'integration_mode = "live-agent-canon"\n'
        'default_consumer = false\n'
        'selection = "explicit-opt-in"\n',
        encoding="utf-8",
    )
    base = graph_change_fixture(parent, {})
    source_root = root / "builder-source"
    executable = source_root / "tools" / "bin" / "agent-canon"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        f"print(json.dumps({{'exit_code': {result_exit_code}}}))\n"
        f"raise SystemExit({process_exit_code})\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    producer = source_root / "tools" / "agent_tools" / "surface_manifest.py"
    producer.parent.mkdir(parents=True)
    producer.write_text("# current producer fixture\n", encoding="utf-8")
    manifest = source_root / "documents" / "runtime" / "shared-runtime-surfaces.toml"
    manifest.parent.mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "documents" / "runtime" / "shared-runtime-surfaces.toml",
        manifest,
    )
    return parent, source_root, base


def experiment_runner_legacy_base_fixture(root: Path) -> tuple[Path, str]:
    """Create an ExperimentRunner-shaped parent pinned to the legacy AgentCanon."""
    legacy_source = root / "agent-canon-f7e79cec"
    subprocess.run(
        [
            "git",
            "clone",
            "--local",
            "--no-hardlinks",
            str(PROJECT_ROOT),
            str(legacy_source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    git(legacy_source, "checkout", "--detach", "--quiet", "f7e79cec")

    parent = root / "experiment-runner"
    parent.mkdir()
    git(parent, "init", "-b", "main")
    git(parent, "config", "user.email", "selector@example.invalid")
    git(parent, "config", "user.name", "Selector Fixture")
    git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        legacy_source.as_uri(),
        "vendor/agent-canon",
    )
    (parent / "changed.py").write_text("before\n", encoding="utf-8")
    git(parent, "add", ".")
    git(parent, "commit", "-m", "ExperimentRunner legacy base")
    base = git(parent, "rev-parse", "HEAD")
    (parent / "changed.py").write_text(
        "# @dependency-start\n"
        "# contract implementation\n"
        "# responsibility Current graph gate fixture.\n"
        "# upstream design missing-base.md fixture target\n"
        "# @dependency-end\n"
        "after\n",
        encoding="utf-8",
    )
    git(parent, "add", "changed.py")
    git(parent, "commit", "-m", "ExperimentRunner current head")
    return parent, base


def write_graph_result(
    root: Path,
    paths: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
    diagnostics: tuple[dict[str, object], ...],
) -> Path:
    """Write one result bound to canonical persisted integration metadata."""
    graph_dir = root / ".agent-canon" / "knowledge-graph"
    graph_dir.mkdir(parents=True)
    database = graph_dir / "graph.sqlite"
    snapshot_head = git(root, "rev-parse", "HEAD")
    input_fingerprint = "1" * 64
    graph_fingerprint = "2" * 64
    diagnostic_counts = {
        "unresolved_count": sum(
            diagnostic["code"] not in {"target-ambiguous", "source-uncovered"}
            for diagnostic in diagnostics
        ),
        "ambiguous_count": sum(
            diagnostic["code"] == "target-ambiguous" for diagnostic in diagnostics
        ),
        "uncovered_count": sum(
            diagnostic["code"] == "source-uncovered" for diagnostic in diagnostics
        ),
    }
    integration_record: dict[str, object] = {
        "schema": "agent-canon.graph.integration.v1",
        "root": str(root.resolve()),
        "db_path": str(database.resolve()),
        "schema_version": "fixture",
        "profile": "default",
        "source_snapshot_profile": "parent",
        "snapshot_head": snapshot_head,
        "input_fingerprint": input_fingerprint,
        "graph_fingerprint": graph_fingerprint,
        "producer_identity": FIXTURE_PRODUCER_IDENTITY.json(),
        "contract_fingerprint": "fixture",
        "producer_artifacts": [],
        "runtime_evidence": None,
        "verified": True,
        "verification_code": "source-facts-readback-v1",
    }
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
        for path in paths:
            connection.execute(
                "INSERT INTO nodes VALUES(?, 'source', ?)",
                (f"node:source:{path}", json.dumps({"path": path})),
            )
        for source, target in edges:
            connection.execute(
                "INSERT INTO edges VALUES('source', ?, ?)",
                (f"node:source:{source}", f"node:source:{target}"),
            )
        for diagnostic in diagnostics:
            connection.execute(
                "INSERT INTO diagnostics VALUES('source', ?, ?, ?, ?, ?)",
                (
                    diagnostic["code"],
                    diagnostic["message"],
                    diagnostic["target_node_id"],
                    diagnostic["severity"],
                    diagnostic["payload_json"],
                ),
            )
        for key, value in (
            ("integration_record", json.dumps(integration_record)),
            ("producer_identity", json.dumps(FIXTURE_PRODUCER_IDENTITY.json())),
            ("snapshot_head", snapshot_head),
            ("input_fingerprint", input_fingerprint),
            ("graph_fingerprint", graph_fingerprint),
        ):
            connection.execute("INSERT INTO metadata VALUES(?, ?)", (key, value))
    result = graph_dir / "graph-build.json"
    result.write_text(
        json.dumps(
            {
                "schema": "agent-canon.graph.build.v1",
                "command": "build",
                "status": "incomplete",
                "graph_status": "incomplete",
                "exit_code": 1,
                "root": str(root.resolve()),
                "profile": "default",
                "db_path": str(database.resolve()),
                "input_fingerprint": input_fingerprint,
                "graph_fingerprint": graph_fingerprint,
                "producer_identity": FIXTURE_PRODUCER_IDENTITY.json(),
                "integration_record": integration_record,
                "publication": "published",
                "durability": "durable",
                **diagnostic_counts,
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "graph-status.json").write_text(
        json.dumps(
            {
                "schema": "agent-canon.graph.status.v1",
                "command": "status",
                "status": "incomplete",
                "profile": "default",
                "root": str(root.resolve()),
                "db_path": str(database.resolve()),
                "input_fingerprint": input_fingerprint,
                "graph_fingerprint": graph_fingerprint,
                "integration_record": integration_record,
                **diagnostic_counts,
                "probe_reason": None,
                "reason": "source_completeness_incomplete",
                "exit_code": 2,
            }
        ),
        encoding="utf-8",
    )
    return result


def source_diagnostic_fixture(
    code: str,
    source: str,
    target: str,
    direction: str,
    kind: str,
    reason: str,
    *,
    severity: str = "blocker",
    message: str = "fixture diagnostic",
    start_line: int = 4,
) -> dict[str, object]:
    """Construct one explicit producer-owned typed diagnostic fixture."""
    declaration = f"{direction} {kind} {target} {reason}"
    payload = {
        "schema": selector.SOURCE_DIAGNOSTIC_SCHEMA,
        "code": code,
        "source": source,
        "target": target,
        "declaration": declaration,
        "source_span": {
            "path": source,
            "start_line": start_line,
            "start_column": 1,
            "end_line": start_line,
            "end_column": 2,
        },
        "declaration_components": {
            "direction": direction,
            "kind": kind,
            "target": target,
            "reason": reason,
        },
    }
    return {
        "code": code,
        "message": message,
        "target_node_id": f"node:source:{source}",
        "severity": severity,
        "payload_json": json.dumps(payload, separators=(",", ":")),
    }


def isolated_current_builder_environment(root: Path) -> dict[str, str]:
    """Bind real-builder fixtures to current source and temporary Cargo state."""
    return {
        "AGENT_CANON_TOOLS_HOME": str(root / "agent-canon-tools-home"),
        "CARGO_TARGET_DIR": str(root / "agent-canon-cargo-target"),
    }


class AgentCanonPrGraphSelectorTest(unittest.TestCase):
    """Exercise required, skipped, and typed failure states."""

    def setUp(self) -> None:
        """Keep unit fixtures focused on head classification semantics."""
        self.base_graph_patch = patch.object(
            selector,
            "build_trusted_base_graph",
            return_value=selector.TrustedBaseGraph(
                "0" * 40,
                "1" * 64,
                "2" * 64,
                FIXTURE_PRODUCER_IDENTITY,
                "published",
                "durable",
                True,
                "fresh",
                (),
            ),
        )
        self.base_graph_patch.start()
        self.addCleanup(self.base_graph_patch.stop)

    def test_semantic_declaration_change_blocks_when_scoped(self) -> None:
        """A declaration change is a new identity even when target and source match."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "old formatting",
            "source_path": "changed.py",
            "target_path": "missing.md",
            "declaration": "upstream design missing.md missing target",
            "severity": "blocker",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "changed reason",
                        message="new line 99: missing.md",
                        start_line=99,
                    ),
                ),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    FIXTURE_PRODUCER_IDENTITY,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {},
                    trusted_base_sha=base,
                )

        self.assertEqual(acceptance.status, "fail")
        self.assertEqual(len(acceptance.report["blocking_diagnostics"]), 1)
        self.assertFalse(acceptance.report["blocking_diagnostics"][0]["base_match"])

    def test_line_and_message_changes_with_same_identity_remain_baseline(self) -> None:
        """Location and message formatting do not create a diagnostic identity change."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "legacy.py:4:missing.md",
            "source_path": "legacy.py",
            "target_path": "missing.md",
            "declaration": "upstream design missing.md missing target",
            "severity": "blocker",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "legacy.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="legacy.py:19:formatted differently",
                        start_line=19,
                    ),
                ),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    FIXTURE_PRODUCER_IDENTITY,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {},
                    trusted_base_sha=base,
                )

        self.assertEqual(acceptance.status, "pass")
        self.assertEqual(acceptance.report["blocking_diagnostics"], [])
        self.assertEqual(len(acceptance.report["baseline_diagnostics"]), 1)

    def test_same_identity_with_worse_severity_blocks(self) -> None:
        """Severity remains outside identity but a worsening severity blocks."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "warning formatting",
            "source_path": "changed.py",
            "target_path": "missing.md",
            "declaration": "upstream design missing.md missing target",
            "severity": "warning",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        severity="error",
                    ),
                ),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    FIXTURE_PRODUCER_IDENTITY,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {},
                    trusted_base_sha=base,
                )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(len(blocking), 1)
        self.assertTrue(blocking[0]["base_match"])
        self.assertTrue(blocking[0]["worsened"])

    def test_diagnostic_partition_is_exhaustive_and_duplicate_free(self) -> None:
        """Blocking and baseline output partitions every unique head identity once."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        severity="warning",
                    ),
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        severity="blocker",
                        message="duplicate stronger row",
                    ),
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "legacy.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                    ),
                ),
            )
            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {},
                trusted_base_sha=base,
            )

        partitions = (
            acceptance.report["blocking_diagnostics"]
            + acceptance.report["baseline_diagnostics"]
        )
        identities = [item["identity"] for item in partitions]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual(
            set(identities),
            {
                selector.diagnostic_identity_text(
                    {
                        "code": "target-unresolved",
                        "message": "fixture",
                        "source_path": "changed.py",
                        "target_path": "missing.md",
                        "declaration": "upstream design missing.md missing target",
                        "severity": "blocker",
                    }
                ),
                selector.diagnostic_identity_text(
                    {
                        "code": "target-unresolved",
                        "message": "fixture",
                        "source_path": "legacy.py",
                        "target_path": "missing.md",
                        "declaration": "upstream design missing.md missing target",
                        "severity": "blocker",
                    }
                ),
            },
        )

    def test_missing_payload_object_fails_before_classification(self) -> None:
        """A missing typed payload object is rejected before reachability."""
        fixture = source_diagnostic_fixture(
            "target-unresolved",
            "changed.py",
            "missing.md",
            "upstream",
            "design",
            "missing target",
        )
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.validate_source_diagnostic(
                rule=fixture["code"],
                message=fixture["message"],
                target_node_id=fixture["target_node_id"],
                severity=fixture["severity"],
                payload_value={},
                node_paths={fixture["target_node_id"]: "changed.py"},
                owner="fixture",
            )

        self.assertEqual(raised.exception.reason, "graph_diagnostic_invalid")

    def test_missing_payload_column_fails_before_classification(self) -> None:
        """A legacy diagnostics table without payload_json is rejected at readback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                    ),
                ),
            )
            database = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("ALTER TABLE diagnostics RENAME TO diagnostics_old")
                connection.execute(
                    "CREATE TABLE diagnostics(layer TEXT, rule TEXT, message TEXT, target_node_id TEXT)"
                )
                connection.execute(
                    "INSERT INTO diagnostics SELECT layer, rule, message, target_node_id FROM diagnostics_old"
                )
                connection.execute("DROP TABLE diagnostics_old")
            identity = selector.graph_build_identity(root, graph_result)
            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.read_bound_graph_acceptance_facts(
                    identity,
                    git(root, "rev-parse", "HEAD"),
                )

        self.assertEqual(raised.exception.reason, "graph_diagnostic_schema_missing")

    def test_wrong_typed_source_span_bool_fails_before_classification(self) -> None:
        """A bool source-span coordinate is not accepted as an integer."""
        fixture = source_diagnostic_fixture(
            "target-unresolved",
            "changed.py",
            "missing.md",
            "upstream",
            "design",
            "missing target",
        )
        payload = json.loads(cast(str, fixture["payload_json"]))
        payload["source_span"]["start_line"] = True
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.validate_source_diagnostic(
                rule=fixture["code"],
                message=fixture["message"],
                target_node_id=fixture["target_node_id"],
                severity=fixture["severity"],
                payload_value=payload,
                node_paths={fixture["target_node_id"]: "changed.py"},
                owner="fixture",
            )

        self.assertEqual(raised.exception.reason, "graph_diagnostic_invalid")
        self.assertIn("start_line", raised.exception.evidence)

    def test_source_span_and_target_node_mismatch_fail_before_classification(self) -> None:
        """Source span and target-node source mismatches fail closed."""
        fixture = source_diagnostic_fixture(
            "target-unresolved",
            "changed.py",
            "missing.md",
            "upstream",
            "design",
            "missing target",
        )
        for mismatch in ("span", "node"):
            with self.subTest(mismatch=mismatch):
                payload = json.loads(cast(str, fixture["payload_json"]))
                node_paths = {fixture["target_node_id"]: "changed.py"}
                if mismatch == "span":
                    payload["source_span"]["path"] = "other.py"
                else:
                    node_paths[fixture["target_node_id"]] = "other.py"
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.validate_source_diagnostic(
                        rule=fixture["code"],
                        message=fixture["message"],
                        target_node_id=fixture["target_node_id"],
                        severity=fixture["severity"],
                        payload_value=payload,
                        node_paths=node_paths,
                        owner="fixture",
                    )
                self.assertEqual(raised.exception.reason, "graph_diagnostic_invalid")

    def test_declaration_component_mismatch_fails_before_classification(self) -> None:
        """The persisted declaration must equal its typed components."""
        fixture = source_diagnostic_fixture(
            "target-unresolved",
            "changed.py",
            "missing.md",
            "upstream",
            "design",
            "missing target",
        )
        payload = json.loads(cast(str, fixture["payload_json"]))
        payload["declaration"] = "upstream design missing.md other reason"
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.validate_source_diagnostic(
                rule=fixture["code"],
                message=fixture["message"],
                target_node_id=fixture["target_node_id"],
                severity=fixture["severity"],
                payload_value=payload,
                node_paths={fixture["target_node_id"]: "changed.py"},
                owner="fixture",
            )

        self.assertEqual(raised.exception.reason, "graph_diagnostic_invalid")
        self.assertIn("declaration", raised.exception.evidence)

    def test_base_builder_process_zero_and_result_one_mismatch_fails_closed(
        self,
    ) -> None:
        """A successful process cannot publish a failing JSON result."""
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.validate_graph_build_exit_code(
                0,
                json.dumps({"exit_code": 1}),
            )

        self.assertEqual(
            raised.exception.reason,
            "trusted_base_graph_exit_code_mismatch",
        )

    def test_base_builder_process_one_and_result_zero_mismatch_fails_closed(
        self,
    ) -> None:
        """A failing process cannot publish a successful JSON result."""
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.validate_graph_build_exit_code(
                1,
                json.dumps({"exit_code": 0}),
            )

        self.assertEqual(
            raised.exception.reason,
            "trusted_base_graph_exit_code_mismatch",
        )

    def test_selector_writes_trusted_changed_path_packet(self) -> None:
        """The selector owns exact trusted base/head path evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            packet = root / "reports" / "dependency-review" / "changed-paths.json"

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {},
                trusted_base_sha=base,
                changed_path_packet=packet,
            )

            self.assertEqual(selection.status, "skipped")
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "agent-canon.pr-changed-paths.v1")
            self.assertEqual(payload["root"], str(root.resolve()))
            self.assertEqual(payload["base_sha"], base)
            self.assertEqual(payload["head_sha"], git(root, "rev-parse", "HEAD"))
            self.assertEqual(payload["changed_paths"], ["changed.py"])
            self.assertEqual(
                payload["changed_paths_sha256"],
                selector.changed_paths_digest(("changed.py",)),
            )

    def test_selector_rejects_an_arbitrary_producer_source_root(self) -> None:
        """Producer execution authority is limited to the selector source tree."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.current_producer_identity(Path(tmp_dir))

        self.assertEqual(
            raised.exception.reason,
            "trusted_base_graph_source_root_unauthorized",
        )

    def test_modified_producer_content_invalidates_captured_identity(self) -> None:
        """A producer replacement after identity capture cannot be reused."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            _parent, source_root, _base = graph_builder_exit_fixture(
                Path(tmp_dir), 0, 1
            )
            with patch.object(
                selector, "selector_source_root", return_value=source_root
            ):
                identity = selector.current_producer_identity(source_root)
                (source_root / "tools/agent_tools/surface_manifest.py").write_text(
                    "# replaced producer\n",
                    encoding="utf-8",
                )
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.validate_producer_identity(
                        identity.json(),
                        "fixture.producer_identity",
                        identity,
                    )

        self.assertEqual(raised.exception.reason, "graph_identity_mismatch")

    def test_head_and_trusted_base_producer_identities_must_match(self) -> None:
        """Base/head graph comparison rejects different producer semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(root, ("changed.py",), (), ())
            mismatched = replace(
                FIXTURE_PRODUCER_IDENTITY,
                version="agent-canon.surface-manifest-producer.other",
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    mismatched,
                    "published",
                    "durable",
                    True,
                    "fresh",
                    (),
                ),
            ):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.evaluate_built_graph(
                        root,
                        graph_result,
                        {},
                        trusted_base_sha=base,
                    )

        self.assertEqual(raised.exception.reason, "graph_identity_mismatch")

    def test_result_and_database_producer_identity_types_fail_closed(self) -> None:
        """Both JSON result and SQLite readback require an identity object."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(root, ("changed.py",), (), ())
            payload = json.loads(graph_result.read_text(encoding="utf-8"))
            valid_payload = dict(payload)
            payload["producer_identity"] = []
            graph_result.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(selector.SelectorFailure) as result_error:
                selector.graph_build_identity(root, graph_result)

            graph_result.write_text(json.dumps(valid_payload), encoding="utf-8")
            database = root / ".agent-canon/knowledge-graph/graph.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE metadata SET value=? WHERE key='producer_identity'",
                    ("[]",),
                )
            identity = selector.graph_build_identity(root, graph_result)
            with self.assertRaises(selector.SelectorFailure) as database_error:
                selector.read_bound_graph_acceptance_facts(identity, base)

        self.assertEqual(result_error.exception.reason, "graph_identity_invalid")
        self.assertEqual(database_error.exception.reason, "graph_identity_invalid")

    def test_trusted_base_builder_rejects_process_zero_result_one_fixture(self) -> None:
        """The trusted-base process path rejects a zero/one exit mismatch."""
        self.base_graph_patch.stop()
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent, source_root, base = graph_builder_exit_fixture(
                Path(tmp_dir),
                process_exit_code=0,
                result_exit_code=1,
            )
            with patch.object(
                selector, "selector_source_root", return_value=source_root
            ):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.build_trusted_base_graph(parent, base, source_root)

        self.assertEqual(
            raised.exception.reason,
            "trusted_base_graph_exit_code_mismatch",
        )

    def test_trusted_base_builder_rejects_process_one_result_zero_fixture(self) -> None:
        """The trusted-base process path rejects a one/zero exit mismatch."""
        self.base_graph_patch.stop()
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent, source_root, base = graph_builder_exit_fixture(
                Path(tmp_dir),
                process_exit_code=1,
                result_exit_code=0,
            )
            with patch.object(
                selector, "selector_source_root", return_value=source_root
            ):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.build_trusted_base_graph(parent, base, source_root)

        self.assertEqual(
            raised.exception.reason,
            "trusted_base_graph_exit_code_mismatch",
        )

    @unittest.skipUnless(
        shutil.which("cargo"), "cargo is required for the real builder"
    )
    def test_real_builder_reads_materialized_derived_parent_base_submodule(
        self,
    ) -> None:
        """The trusted base build uses the exact derived-parent AgentCanon gitlink."""
        self.base_graph_patch.stop()
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent, base, gitlink = derived_parent_graph_fixture(Path(tmp_dir))
            expected_gitlink = git(
                parent, "ls-tree", base, "vendor/agent-canon"
            ).split()[2]

            with patch.dict(
                os.environ,
                isolated_current_builder_environment(Path(tmp_dir)),
                clear=False,
            ):
                trusted_base = selector.build_trusted_base_graph(
                    parent,
                    base,
                    PROJECT_ROOT,
                )

        self.assertEqual(gitlink, expected_gitlink)
        self.assertEqual(trusted_base.snapshot_head, base)
        self.assertTrue(trusted_base.verified)

    @unittest.skipUnless(
        shutil.which("cargo"), "cargo is required for the real builder"
    )
    def test_experiment_runner_legacy_pin_reaches_partition_with_current_producer(
        self,
    ) -> None:
        """A legacy base pin builds and exposes a new head diagnostic to partitioning."""
        self.base_graph_patch.stop()
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent, base = experiment_runner_legacy_base_fixture(Path(tmp_dir))
            legacy_script = (
                parent
                / "vendor"
                / "agent-canon"
                / "tools"
                / "agent_tools"
                / "surface_manifest.py"
            )
            self.assertNotIn(
                "normalized-snapshot", legacy_script.read_text(encoding="utf-8")
            )
            graph_result = write_graph_result(
                parent,
                ("changed.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "missing-base.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="changed.py:4:missing-base.md",
                    ),
                ),
            )

            with patch.dict(
                os.environ,
                isolated_current_builder_environment(Path(tmp_dir)),
                clear=False,
            ):
                acceptance = selector.evaluate_built_graph(
                    parent,
                    graph_result,
                    {},
                    trusted_base_sha=base,
                    source_root=PROJECT_ROOT,
                )

        self.assertEqual(acceptance.status, "fail")
        self.assertEqual(
            acceptance.report["trusted_base_graph"]["snapshot_head"],
            base,
        )
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(len(blocking), 1)
        self.assertFalse(blocking[0]["base_match"])

    def test_pr_entrypoint_prepares_and_passes_trusted_base(self) -> None:
        """The parent gate wires shallow preparation to the exact selector argument."""
        entrypoint = CHECKER_PATH.read_text(encoding="utf-8")

        self.assertIn("--prepare-ci-base", entrypoint)
        self.assertIn(
            'selector_args+=(--trusted-base-sha "${trusted_base_sha}")',
            entrypoint,
        )
        self.assertIn(
            '--trusted-base-sha "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}"',
            entrypoint,
        )

    def test_pin_only_diff_is_skipped_with_reason_and_evidence(self) -> None:
        """A pin-only parent diff does not select strict parent graph completeness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {},
                trusted_base_sha=base,
            )

        self.assertEqual(selection.status, "skipped")
        self.assertEqual(selection.reason, "parent_graph_completeness_not_selected")
        self.assertIn(f"base={base}", selection.evidence)
        self.assertIn("dependency_surface_owner=", selection.evidence)
        self.assertIn("changed_paths_sha256=", selection.evidence)

    def test_canonical_maintenance_profile_requires_graph(self) -> None:
        """Strict graph selection comes from the canonical profile inventory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {
                    "AGENT_CANON_PR_VALIDATION_PROFILE": "maintenance",
                },
                trusted_base_sha=base,
            )

        self.assertEqual(selection.status, "required")
        self.assertIn("canonical_profile_requires_graph", selection.reason)
        self.assertIn("graph_profiles=maintenance", selection.evidence)

    def test_canonical_non_graph_profile_keeps_pin_only_diff_skipped(self) -> None:
        """A known profile with a false canonical requirement does not escalate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {
                    "AGENT_CANON_PR_VALIDATION_PROFILE": "agent-runtime",
                },
                trusted_base_sha=base,
            )

        self.assertEqual(selection.status, "skipped")
        self.assertIn("selected_profiles=agent-runtime", selection.evidence)

    def test_unknown_profile_is_typed_failure(self) -> None:
        """Unknown local profile strings never degrade to a skipped graph gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.select(
                    root,
                    PROJECT_ROOT,
                    {
                        "AGENT_CANON_PR_VALIDATION_PROFILE": "strict-dependency",
                    },
                    trusted_base_sha=base,
                )

        self.assertEqual(raised.exception.reason, "unknown_validation_profile")

    def test_dependency_surfaces_come_from_canonical_owner_manifest(self) -> None:
        """All graph adapters named by review are manifest-derived surfaces."""
        surfaces = selector.dependency_surface_paths(PROJECT_ROOT)

        self.assertTrue(
            {
                "tools/agent_tools/scan_dependency_headers.sh",
                "tools/agent_tools/check_dependency_headers.py",
                "tools/agent_tools/render_dependency_manifest_graph.py",
                "tools/agent_tools/graph_client.py",
                "tools/ci/check_agent_canon_pr.sh",
                "tools/ci/run_all_checks.sh",
            }.issubset(surfaces)
        )

    def test_canonical_dependency_surface_change_requires_graph(self) -> None:
        """A manifest-owned dependency surface selects strict graph completeness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "tools/agent_tools/graph_client.py")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {},
                trusted_base_sha=base,
            )

        self.assertEqual(selection.status, "required")
        self.assertIn("canonical_dependency_surface_touched", selection.reason)
        self.assertIn("tools/agent_tools/graph_client.py", selection.evidence)

    def test_graph_storage_dispatch_and_bootstrap_surfaces_require_graph(self) -> None:
        """Every reviewed graph storage/dispatch/bootstrap surface selects strict graph."""
        reviewed_surfaces = (
            "rust/agent-canon/src/structured_analysis.rs",
            "rust/agent-canon/src/main.rs",
            "tools/bin/agent-canon",
        )
        for relative in reviewed_surfaces:
            with self.subTest(path=relative):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    base = commit_change(root, relative)

                    selection = selector.select(
                        root,
                        PROJECT_ROOT,
                        {},
                        trusted_base_sha=base,
                    )

                self.assertEqual(selection.status, "required")
                self.assertIn(
                    "canonical_dependency_surface_touched",
                    selection.reason,
                )
                self.assertIn(relative, selection.evidence)

    def test_dependency_manifest_change_requires_graph(self) -> None:
        """A changed dependency header selects strict graph completeness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "README.md")
            readme = root / "README.md"
            readme.write_text(
                "# @dependency-start\n# responsibility Fixture manifest.\n# @dependency-end\n",
                encoding="utf-8",
            )
            git(root, "add", "README.md")
            git(root, "commit", "-m", "manifest")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {},
                trusted_base_sha=base,
            )

        self.assertEqual(selection.status, "required")
        self.assertIn("dependency_manifest_touched", selection.reason)

    def test_unrelated_base_unresolved_is_reported_without_blocking(self) -> None:
        """An unchanged non-reachable declaration remains evidence, not a PR blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "legacy.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="legacy.py:4:missing.md",
                    ),
                ),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {},
                trusted_base_sha=base,
            )
            head = git(root, "rev-parse", "HEAD")

        self.assertEqual(acceptance.status, "pass")
        self.assertEqual(
            acceptance.reason,
            "unrelated_baseline_incompleteness_reported",
        )
        self.assertEqual(acceptance.report["blocking_diagnostics"], [])
        graph_identity = acceptance.report["graph_identity"]
        self.assertEqual(graph_identity["snapshot_head"], head)
        self.assertEqual(graph_identity["publication"], "published")
        self.assertEqual(
            graph_identity["db_path"],
            str(root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"),
        )
        baseline = acceptance.report["baseline_diagnostics"]
        self.assertEqual(len(baseline), 1)
        self.assertEqual(baseline[0]["source_path"], "legacy.py")

    def test_concurrent_database_replacement_is_typed_failure(self) -> None:
        """Replacing the canonical DB after open cannot reach classification."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "legacy.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="legacy.py:4:missing.md",
                    ),
                ),
            )
            database = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
            real_identity = selector.regular_file_identity
            database_reads = 0

            def replace_after_open(
                path: Path,
                unavailable_reason: str,
                invalid_reason: str,
            ) -> object:
                """Replace the database after the selector opens it."""
                nonlocal database_reads
                if path == database:
                    database_reads += 1
                    if database_reads == 2:
                        replacement = database.with_name("replacement.sqlite")
                        replacement.write_bytes(database.read_bytes())
                        os.replace(replacement, database)
                return real_identity(path, unavailable_reason, invalid_reason)

            with patch.object(
                selector,
                "regular_file_identity",
                side_effect=replace_after_open,
            ):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.evaluate_built_graph(
                        root,
                        graph_result,
                        {},
                        trusted_base_sha=base,
                    )

        self.assertEqual(raised.exception.reason, "graph_identity_replaced")
        self.assertIn("artifact=graph_database", raised.exception.evidence)

    def test_reachable_unresolved_blocks_changed_responsibility(self) -> None:
        """A diagnostic reached through a dependency edge remains a blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"related.py": "related\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "related.py"),
                (("changed.py", "related.py"),),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "related.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="related.py:4:missing.md",
                    ),
                ),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {},
                trusted_base_sha=base,
            )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["classification"], "changed_responsibility")

    def test_reachable_base_identity_is_evidence_not_a_new_blocker(self) -> None:
        """Reachability alone does not block a diagnostic already in trusted base."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "related.py:4:missing.md",
            "source_path": "related.py",
            "target_path": "missing.md",
            "declaration": "upstream design missing.md missing target",
            "severity": "blocker",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"related.py": "related\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "related.py"),
                (("changed.py", "related.py"),),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "related.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="related.py:19:missing.md",
                        start_line=19,
                    ),
                ),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    FIXTURE_PRODUCER_IDENTITY,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {},
                    trusted_base_sha=base,
                )

        self.assertEqual(acceptance.status, "pass")
        self.assertEqual(acceptance.report["blocking_diagnostics"], [])
        self.assertEqual(len(acceptance.report["baseline_diagnostics"]), 1)
        self.assertEqual(
            acceptance.report["baseline_diagnostics"][0]["declaration"],
            "upstream design missing.md missing target",
        )

    def test_same_count_replacement_is_a_new_blocker(self) -> None:
        """Replacing one diagnostic identity cannot be hidden by equal counts."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "changed.py:4:old.md",
            "source_path": "changed.py",
            "target_path": "old.md",
            "declaration": "upstream design old.md old target",
            "severity": "blocker",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "changed.py",
                        "new.md",
                        "upstream",
                        "design",
                        "new target",
                        message="changed.py:40:new.md",
                        start_line=40,
                    ),
                ),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    FIXTURE_PRODUCER_IDENTITY,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {},
                    trusted_base_sha=base,
                )

        self.assertEqual(acceptance.status, "fail")
        self.assertEqual(len(acceptance.report["blocking_diagnostics"]), 1)
        self.assertFalse(acceptance.report["blocking_diagnostics"][0]["base_match"])

    def test_changed_manifest_grammar_blocks_without_target_node(self) -> None:
        """Invalid grammar in a changed declaration is always in the gate closure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "manifest-grammar",
                        "changed.py",
                        "invalid-target:fixture",
                        "upstream",
                        "bad-kind",
                        "invalid reason",
                        message="changed.py:3:upstream bad",
                        start_line=3,
                    ),
                ),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {},
                trusted_base_sha=base,
            )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(blocking[0]["code"], "manifest-grammar")
        self.assertEqual(blocking[0]["source_path"], "changed.py")

    def test_changed_target_blocks_an_unchanged_unresolved_declaration(self) -> None:
        """Deleting a declared target keeps its unchanged source in changed scope."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            git(root, "init", "-b", "main")
            git(root, "config", "user.email", "selector@example.invalid")
            git(root, "config", "user.name", "Selector Fixture")
            (root / "legacy.py").write_text("legacy\n", encoding="utf-8")
            (root / "deleted.md").write_text("target\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")
            base = git(root, "rev-parse", "HEAD")
            (root / "deleted.md").unlink()
            git(root, "add", "deleted.md")
            git(root, "commit", "-m", "delete target")
            graph_result = write_graph_result(
                root,
                ("legacy.py",),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "legacy.py",
                        "deleted.md",
                        "upstream",
                        "design",
                        "deleted target",
                        message="legacy.py:4:deleted.md",
                    ),
                ),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {},
                trusted_base_sha=base,
            )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(blocking[0]["target_path"], "deleted.md")
        self.assertEqual(blocking[0]["classification"], "changed_responsibility")

    def test_explicit_parent_migration_keeps_full_graph_completeness(self) -> None:
        """A declared migration owns baseline diagnostics across the whole graph."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (
                    source_diagnostic_fixture(
                        "target-unresolved",
                        "legacy.py",
                        "missing.md",
                        "upstream",
                        "design",
                        "missing target",
                        message="legacy.py:4:missing.md",
                    ),
                ),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {
                    "AGENT_CANON_PR_PARENT_GRAPH_MIGRATION": "yes",
                },
                trusted_base_sha=base,
            )

        self.assertEqual(acceptance.status, "fail")
        self.assertTrue(acceptance.report["full_scope"])

    def test_pr_entrypoint_keeps_graph_analysis_outside_source_receipt(self) -> None:
        """The selector supplies scope; the source receipt owns two statuses."""
        entrypoint = CHECKER_PATH.read_text(encoding="utf-8")
        quick_ci = (PROJECT_ROOT / "tools" / "ci" / "run_all_checks.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("PR_GATE_DEPENDENCY_GRAPH_STATUS", entrypoint)
        self.assertNotIn("PR_GATE_DEPENDENCY_GRAPH_STATUS", quick_ci)
        self.assertIn("pr_gate_receipt.py", quick_ci)
        self.assertIn("validated_source_receipt_consumed", quick_ci)

    def test_base_equal_to_head_is_typed_failure(self) -> None:
        """An equal base cannot masquerade as an empty PR diff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            commit_change(root, "vendor/agent-canon")
            head = git(root, "rev-parse", "HEAD")

            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.load_diff(root, {}, head)

        self.assertEqual(raised.exception.reason, "pr_base_equals_head")

    def test_local_trusted_base_sha_is_required(self) -> None:
        """Local callers cannot fall back to origin/main or HEAD parents."""
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.trusted_base_ref({})

        self.assertEqual(raised.exception.reason, "local_trusted_base_argument_required")

    def test_local_trusted_base_sha_is_consumed_without_environment_override(self) -> None:
        """The owner-provided SHA is sufficient without a base environment variable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            resolved, source = selector.trusted_base_ref({}, base)
            diff = selector.load_diff(root, {}, base)

        self.assertEqual(resolved, base)
        self.assertEqual(source, "owner_trusted_base_sha")
        self.assertEqual(diff.base_sha, base)

    def test_history_unreachable_base_is_typed_failure(self) -> None:
        """A resolvable commit without common history cannot define the PR diff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            commit_change(root, "vendor/agent-canon")
            empty_tree = git(root, "mktree", input_text="")
            unrelated = git(root, "commit-tree", empty_tree, input_text="unrelated\n")

            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.load_diff(root, {}, unrelated)

        self.assertEqual(raised.exception.reason, "pr_base_unreachable_from_head")

    def test_diff_command_failure_is_typed_failure(self) -> None:
        """A failed Git diff cannot become an empty changed-path set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            real_run_git = selector.run_git

            def fail_diff(
                command_root: Path,
                args: list[str] | tuple[str, ...],
                extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                """Return a typed failure for the changed-path diff command."""
                if args and args[0] == "diff":
                    return subprocess.CompletedProcess(
                        ["git", *args],
                        128,
                        stdout="",
                        stderr="fixture diff failure",
                    )
                return real_run_git(command_root, args, extra_environment)

            with patch.object(selector, "run_git", side_effect=fail_diff):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.load_diff(root, {}, base)

        self.assertEqual(raised.exception.reason, "pr_changed_paths_diff_failed")

    def test_ci_auth_required_fetch_succeeds_without_persisting_credential(
        self,
    ) -> None:
        """CI authenticates a needed fetch and binds selection to the event base."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            checkout, event, base = shallow_pr_checkout(root)
            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
                "AGENT_CANON_PR_READ_TOKEN": "fixture-read-token",
            }
            unresolved = subprocess.run(
                ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unresolved.returncode, 0)

            real_run_git = selector.run_git
            fetch_environments: list[dict[str, str]] = []

            def inspect_fetch(
                command_root: Path,
                args: list[str] | tuple[str, ...],
                extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                """Record the authenticated fetch environment before delegation."""
                if args and args[0] == "fetch":
                    self.assertEqual(tuple(args[-2:]), ("origin", base))
                    self.assertIsNotNone(extra_environment)
                    fetch_environment = dict(extra_environment or {})
                    self.assertEqual(fetch_environment["GIT_TERMINAL_PROMPT"], "0")
                    self.assertEqual(
                        fetch_environment["GIT_CONFIG_KEY_0"],
                        "http.https://github.com/.extraheader",
                    )
                    self.assertTrue(
                        fetch_environment["GIT_CONFIG_VALUE_0"].startswith(
                            "AUTHORIZATION: basic "
                        )
                    )
                    fetch_environments.append(fetch_environment)
                return real_run_git(command_root, args, extra_environment)

            with patch.object(selector, "run_git", side_effect=inspect_fetch):
                prepared = selector.prepare_ci_base(checkout, environment)

            diff = selector.load_diff(
                checkout,
                environment,
                prepared.base_sha,
            )
            persisted = subprocess.run(
                [
                    "git",
                    "config",
                    "--local",
                    "--get-all",
                    "http.https://github.com/.extraheader",
                ],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(diff.base_sha, base)
        self.assertTrue(prepared.fetched)
        self.assertEqual(len(fetch_environments), 1)
        self.assertEqual(prepared.base_source, "github_event_pull_request_base_sha")
        self.assertEqual(diff.base_source, "github_event_pull_request_base_sha")
        self.assertNotEqual(persisted.returncode, 0)
        self.assertEqual(persisted.stdout, "")

    def test_ci_skips_fetch_when_base_object_and_history_are_available(self) -> None:
        """A complete checkout needs neither a fetch nor a read credential."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"base": {"sha": base}}}),
                encoding="utf-8",
            )
            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
            }
            real_run_git = selector.run_git

            def reject_fetch(
                command_root: Path,
                args: list[str] | tuple[str, ...],
                extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                """Reject an unexpected fetch when the base history is present."""
                if args and args[0] == "fetch":
                    self.fail("history-ready CI preparation must not fetch")
                return real_run_git(command_root, args, extra_environment)

            with patch.object(selector, "run_git", side_effect=reject_fetch):
                prepared = selector.prepare_ci_base(root, environment)

        self.assertEqual(prepared.base_sha, base)
        self.assertFalse(prepared.fetched)

    def test_ci_missing_fetch_credential_is_typed_failure(self) -> None:
        """A fetch-required GitHub checkout fails before unauthenticated fetch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            checkout, event, _base = shallow_pr_checkout(root)
            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.prepare_ci_base(
                    checkout,
                    {
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": str(event),
                    },
                )

        self.assertEqual(
            raised.exception.reason,
            "pr_base_read_credential_missing",
        )

    def test_ci_rejects_missing_or_mismatched_trusted_base_argument(self) -> None:
        """Normal CI selection cannot invent or replace the prepared event base."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"base": {"sha": base}}}),
                encoding="utf-8",
            )
            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
            }

            with self.assertRaises(selector.SelectorFailure) as missing:
                selector.load_diff(root, environment)
            with self.assertRaises(selector.SelectorFailure) as mismatch:
                selector.load_diff(root, environment, "0" * 40)

        self.assertEqual(missing.exception.reason, "trusted_pr_base_argument_invalid")
        self.assertEqual(mismatch.exception.reason, "trusted_pr_base_argument_mismatch")

if __name__ == "__main__":
    unittest.main()
