"""Tests for the shared native SCIP index and bounded query API."""

# @dependency-start
# contract test
# responsibility Tests standard SCIP index outputs and bounded query projection.
# upstream implementation ../../tools/analysis/dependencies/scip_index.py owns native index use.
# upstream design ../../documents/tools/scip_index.md documents input and artifact boundaries.
# @dependency-end

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tools.analysis.dependencies.scip_index as scip_index  # noqa: E402


def occurrence(
    symbol: str, role: int, start: int, end: int, *, typed: bool = False
) -> dict[str, Any]:
    """Return a small official JSON occurrence."""
    range_fields: dict[str, Any] = (
        {
            "TypedRange": {
                "single_line_range": {
                    "line": 1,
                    "start_character": start,
                    "end_character": end,
                }
            }
        }
        if typed
        else {"range": [1, start, end]}
    )
    return {
        **range_fields,
        "symbol": symbol,
        "symbol_roles": role,
    }


class ScipIndexTest(unittest.TestCase):
    """Check artifact placement, official readback, and relation fidelity."""

    def test_query_projects_only_selected_symbol_relations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "source"
            runtime = workspace / "runtime"
            root.mkdir()
            runtime.mkdir()
            index_path = runtime / "runs" / "python" / "index.scip"
            index_path.parent.mkdir(parents=True)
            index_path.write_bytes(b"official-scip-index")
            target_symbol = "scip-python python demo 0.1.0 pkg.api/run()."
            implementation_symbol = "scip-python python demo 0.1.0 pkg.impl/FastRun#"
            payload = {
                "metadata": {
                    "project_root": root.as_uri(),
                    "tool_info": {"name": "scip-python", "version": "0.6.6"},
                    "text_document_encoding": 1,
                },
                "documents": [
                    {
                        "relative_path": "pkg/api.py",
                        "language": "python",
                        "occurrences": [
                            occurrence(target_symbol, 1, 4, 7, typed=True)
                        ],
                        "symbols": [
                            {"symbol": target_symbol, "relationships": []}
                        ],
                    },
                    {
                        "relative_path": "pkg/use.py",
                        "language": "python",
                        "occurrences": [occurrence(target_symbol, 8, 11, 14)],
                        "symbols": [],
                    },
                    {
                        "relative_path": "pkg/ref_only.py",
                        "language": "python",
                        "occurrences": [occurrence(target_symbol, 8, 2, 8)],
                        "symbols": [],
                    },
                    {
                        "relative_path": "pkg/impl.py",
                        "language": "python",
                        "occurrences": [
                            occurrence(implementation_symbol, 1, 0, 8)
                        ],
                        "symbols": [
                            {
                                "symbol": implementation_symbol,
                                "relationships": [
                                    {
                                        "symbol": target_symbol,
                                        "is_implementation": True,
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "relative_path": "pkg/unrelated.py",
                        "language": "python",
                        "occurrences": [
                            occurrence(
                                "scip-python python demo 0.1.0 pkg.other/unrelated().",
                                1,
                                0,
                                9,
                            )
                        ],
                        "symbols": [],
                    },
                ],
                "external_symbols": [],
            }
            args = SimpleNamespace(
                root=root,
                runtime_root=runtime,
                index=[Path("runs/python/index.scip")],
                path=["pkg/api.py"],
                symbol=[],
                limit=20,
            )

            def run(
                command: list[str], *, cwd: Path, env: dict[str, str]
            ) -> subprocess.CompletedProcess[str]:
                self.assertNotIn("AGENT_CANON_CONTROL_PARENT_ROOT", env)
                self.assertEqual(command[1:3], ["print", "--json"])
                self.assertEqual(cwd, root)
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

            with (
                patch.object(
                    scip_index,
                    "resolve_verified_tool",
                    return_value=scip_index.VerifiedTool(
                        Path("/usr/local/bin/scip"),
                        "scip-cli",
                        "0.10.0",
                        "scip version v0.10.0",
                    ),
                ),
                patch.object(scip_index, "_run", side_effect=run),
            ):
                result = scip_index.query_indexes(args)
                args.path = ["pkg/ref_only.py"]
                reference_seed = scip_index.query_indexes(args)
                args.path = ["."]
                directory_seed = scip_index.query_indexes(args)
                args.path = []
                args.symbol = [target_symbol]
                symbol_seed = scip_index.query_indexes(args)

            self.assertEqual(result["status"], "projected")
            self.assertEqual(result["symbols"], [target_symbol])
            self.assertEqual(
                [item["path"] for item in result["definitions"]],
                ["pkg/api.py"],
            )
            self.assertEqual(result["definitions"][0]["range"]["start"]["line"], 1)
            self.assertEqual(
                [item["path"] for item in result["references"]],
                ["pkg/use.py", "pkg/ref_only.py"],
            )
            self.assertEqual(
                [item["path"] for item in result["implementations"]],
                ["pkg/impl.py"],
            )
            self.assertEqual(result["references"][0]["range"]["start"]["line"], 1)
            self.assertEqual(result["references"][0]["roles"], ["read-access"])
            self.assertEqual(result["capabilities"]["callers"], "not-represented")
            self.assertEqual(
                result["capabilities"]["source_freshness"], "unverified"
            )
            self.assertEqual(
                result["index_refs"][0]["sha256"],
                hashlib.sha256(b"official-scip-index").hexdigest(),
            )
            self.assertEqual(
                sorted(path.name for path in runtime.rglob("*") if path.is_file()),
                ["index.scip"],
            )
            self.assertEqual(reference_seed["symbols"], [target_symbol])
            self.assertEqual(
                [item["path"] for item in reference_seed["definitions"]],
                ["pkg/api.py"],
            )
            self.assertEqual(
                directory_seed["capabilities"]["target_paths"], "partial"
            )
            self.assertEqual(
                symbol_seed["capabilities"]["target_paths"], "not-selected"
            )

    def test_query_marks_unindexed_target_without_claiming_no_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "source"
            runtime = workspace / "runtime"
            root.mkdir()
            runtime.mkdir()
            index_path = runtime / "index.scip"
            index_path.write_bytes(b"official-scip-index")
            payload = {
                "metadata": {
                    "project_root": root.as_uri(),
                    "tool_info": {"name": "rust-analyzer", "version": "1.89.0"},
                },
                "documents": [
                    {
                        "relative_path": "src/lib.rs",
                        "language": "rust",
                        "occurrences": [],
                        "symbols": [],
                    }
                ],
            }
            args = SimpleNamespace(
                root=root,
                runtime_root=runtime,
                index=[Path("index.scip")],
                path=["src/unsupported.sh"],
                symbol=[],
                limit=20,
            )
            with (
                patch.object(
                    scip_index,
                    "resolve_verified_tool",
                    return_value=scip_index.VerifiedTool(
                        Path("/usr/local/bin/scip"),
                        "scip-cli",
                        "0.10.0",
                        "scip version v0.10.0",
                    ),
                ),
                patch.object(
                    scip_index,
                    "_run",
                    return_value=subprocess.CompletedProcess(
                        ["scip", "print"], 0, json.dumps(payload), ""
                    ),
                ),
            ):
                result = scip_index.query_indexes(args)

            self.assertEqual(result["status"], "unindexed-target")
            self.assertEqual(result["unindexed_targets"], ["src/unsupported.sh"])
            self.assertEqual(result["definitions"], [])
            self.assertEqual(result["references"], [])
            self.assertEqual(result["capabilities"]["target_paths"], "partial")

    def test_cpp_index_writes_only_to_external_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / "source"
            runtime = workspace / "runtime"
            root.mkdir()
            runtime.mkdir()
            compdb = root / "compile_commands.json"
            compdb.write_text("[]\n", encoding="utf-8")
            args = SimpleNamespace(
                root=root,
                runtime_root=runtime,
                output=Path("runs/cpp/index.scip"),
                language="cpp",
                project_name=None,
                project_version=None,
                python_environment=None,
                compile_database=Path("compile_commands.json"),
            )
            commands: list[list[str]] = []

            def resolve(language: str) -> scip_index.VerifiedTool:
                executable = "scip" if language == "scip" else "scip-clang"
                version = "0.10.0" if language == "scip" else "0.4.0"
                return scip_index.VerifiedTool(
                    Path(f"/usr/local/bin/{executable}"),
                    f"{executable}-record",
                    version,
                    version,
                )

            def run(
                command: list[str], *, cwd: Path, env: dict[str, str]
            ) -> subprocess.CompletedProcess[str]:
                del cwd
                self.assertNotIn("AGENT_CANON_CONTROL_PARENT_ROOT", env)
                commands.append(command)
                if Path(command[0]).name == "scip-clang":
                    output_arg = next(
                        value
                        for value in command
                        if value.startswith("--index-output-path=")
                    )
                    Path(output_arg.split("=", 1)[1]).write_bytes(b"cpp-index")
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 0, "Documents: 1", "")

            with (
                patch.object(scip_index, "resolve_verified_tool", side_effect=resolve),
                patch.object(scip_index, "_run", side_effect=run),
            ):
                result = scip_index.index_project(args)

            output = runtime / "runs" / "cpp" / "index.scip"
            self.assertEqual(result["status"], "written")
            self.assertTrue(output.is_file())
            self.assertFalse((root / "index.scip").exists())
            self.assertIn(f"--compdb-path={compdb}", commands[0])
            self.assertIn(f"--index-output-path={output}", commands[0])
            self.assertIn(
                f"--supplementary-output-dir={output.parent / 'scip-clang-supplementary-output'}",
                commands[0],
            )

    def test_unqualified_language_index_request_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            for language in ("shell", "rust"):
                output = StringIO()
                with redirect_stdout(output):
                    status = scip_index.main(
                        [
                            "index",
                            "--root",
                            str(root),
                            "--runtime-root",
                            str(runtime),
                            "--output",
                            f"runs/{language}/index.scip",
                            "--language",
                            language,
                        ]
                    )
                payload = json.loads(output.getvalue())
                self.assertEqual(status, 0)
                self.assertEqual(payload["status"], "unsupported")
                self.assertEqual(
                    payload["capabilities"], {language: "unsupported"}
                )
            self.assertFalse(runtime.exists())

    def test_supported_indexer_requires_project_owned_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            output = StringIO()
            with redirect_stdout(output):
                status = scip_index.main(
                    [
                        "index",
                        "--root",
                        str(root),
                        "--runtime-root",
                        str(runtime),
                        "--output",
                        "runs/python/index.scip",
                        "--language",
                        "python",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(payload["status"], "input-required")
            self.assertEqual(
                payload["capabilities"], {"python": "input-required"}
            )
            self.assertFalse(runtime.exists())


if __name__ == "__main__":
    unittest.main()
