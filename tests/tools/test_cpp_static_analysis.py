"""Focused tests for the canonical C++ compile-database and analyzer route."""

# @dependency-start
# contract test
# responsibility Verifies CMake database selection, native checker forwarding, and VS Code policy.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared editor surface ownership
# upstream implementation ../../tools/static_analysis/cpp/static_analysis.py canonical C++ route
# downstream implementation ../../.vscode/extensions.json shared extension recommendations
# downstream implementation ../../.vscode/settings.json shared provider settings
# downstream implementation ../../.vscode/tasks.json shared task entrypoints
# @dependency-end

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "static_analysis" / "cpp" / "static_analysis.py"


def run_tool(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the route with an explicit workspace root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--workspace-root", str(root)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_database(root: Path, relative_build: str = "build/cpp/dev/autodiff") -> Path:
    """Write a minimal CMake-shaped compile database fixture."""
    directory = root / relative_build
    directory.mkdir(parents=True)
    database = directory / "compile_commands.json"
    database.write_text("[]\n", encoding="utf-8")
    return database


class CppStaticAnalysisTest(unittest.TestCase):
    """Exercise the tool contract without requiring a host clang installation."""

    def test_select_db_materializes_one_profile_view_and_rejects_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = write_database(root)
            selected = run_tool(root, "select-db", "--build-dir", "build/cpp/dev/autodiff")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            active = root / "build/cpp/dev/compile_commands.json"
            self.assertTrue(active.is_symlink())
            self.assertEqual(active.resolve(), database.resolve())
            self.assertIn("materialization=symlink", selected.stdout)

            repeated = run_tool(root, "select-db", "--build-dir", "build/cpp/dev/autodiff")
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn("materialization=already-active", repeated.stdout)

            active.unlink()
            active.write_text("user-owned\n", encoding="utf-8")
            refused = run_tool(root, "select-db", "--build-dir", "build/cpp/dev/autodiff")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("active_database_exists", refused.stderr)

    def test_select_db_rejects_symlinked_output_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_database(root)
            outside = root / "outside"
            outside.mkdir()
            escape_parent = root / "build/cpp/evil"
            escape_parent.parent.mkdir(parents=True, exist_ok=True)
            escape_parent.symlink_to(outside, target_is_directory=True)
            escaped = run_tool(
                root,
                "select-db",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--output",
                "build/cpp/evil/compile_commands.json",
            )
            self.assertEqual(escaped.returncode, 2)
            self.assertIn("active_database_outside_build", escaped.stderr)
            self.assertFalse((outside / "compile_commands.json").exists())

    def test_analyzers_use_real_tools_and_native_output_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = write_database(root)
            source = root / "custom.cpp"
            source.write_text("int main() { return 0; }\n", encoding="utf-8")
            clangd = shutil.which("clangd")
            clang_tidy = shutil.which("clang-tidy")
            clangxx = shutil.which("clang++")
            if not clangd or not clang_tidy or not clangxx:
                self.skipTest("clangd, clang-tidy, and clang++ are required for the native smoke")
            database.write_text(
                json.dumps(
                    [
                        {
                            "directory": str(root),
                            "command": f"{clangxx} -std=c++20 -fsyntax-only {source}",
                            "file": str(source),
                        }
                    ]
                ),
                encoding="utf-8",
            )
            checked = run_tool(
                root,
                "clangd-check",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--source",
                "custom.cpp",
                "--clangd",
                clangd,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

            config = root / "clang-tidy.yaml"
            config.write_text("Checks: '*'\n", encoding="utf-8")
            tidied = run_tool(
                root,
                "clang-tidy",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--source",
                "custom.cpp",
                "--clang-tidy",
                clang_tidy,
                "--config-file",
                "clang-tidy.yaml",
            )
            self.assertEqual(tidied.returncode, 0, tidied.stderr)
            self.assertNotIn("-I", SCRIPT.read_text(encoding="utf-8"))

    def test_clang_tidy_selects_conventional_config_and_preserves_explicit_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = write_database(root)
            source = root / "custom.cpp"
            source.write_text("int main() { return 0; }\n", encoding="utf-8")
            conventional = root / "clang" / "clang-tidy.yaml"
            conventional.parent.mkdir(parents=True)
            conventional.write_text("Checks: '*'\n", encoding="utf-8")
            explicit = root / "explicit.yaml"
            explicit.write_text("Checks: '-*'\n", encoding="utf-8")
            fake = root / "fake-clang-tidy"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "import sys\n"
                "print(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)

            automatic = run_tool(
                root,
                "clang-tidy",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--source",
                "custom.cpp",
                "--clang-tidy",
                str(fake),
            )
            self.assertEqual(automatic.returncode, 0, automatic.stderr)
            self.assertEqual(
                json.loads(automatic.stdout),
                [
                    "--config-file",
                    str(conventional),
                    str(source),
                    "-p",
                    str(database.parent),
                ],
            )

            overridden = run_tool(
                root,
                "clang-tidy",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--source",
                "custom.cpp",
                "--clang-tidy",
                str(fake),
                "--config-file",
                "explicit.yaml",
            )
            self.assertEqual(overridden.returncode, 0, overridden.stderr)
            self.assertEqual(json.loads(overridden.stdout)[0:2], ["--config-file", "explicit.yaml"])

            conventional.unlink()
            without_config = run_tool(
                root,
                "clang-tidy",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--source",
                "custom.cpp",
                "--clang-tidy",
                str(fake),
            )
            self.assertEqual(without_config.returncode, 0, without_config.stderr)
            self.assertEqual(
                json.loads(without_config.stdout),
                [str(source), "-p", str(database.parent)],
            )

    def test_missing_inputs_fail_before_native_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "custom.cpp"
            source.write_text("int value = 0;\n", encoding="utf-8")
            missing_db = run_tool(root, "clangd-check", "--source", "custom.cpp", "--build-dir", "build/cpp/dev")
            self.assertEqual(missing_db.returncode, 2)
            self.assertIn("build_directory_missing", missing_db.stderr)
            write_database(root)
            missing_executable = run_tool(
                root,
                "clangd-check",
                "--source",
                "custom.cpp",
                "--build-dir",
                "build/cpp/dev/autodiff",
                "--clangd",
                str(root / "missing-tool"),
            )
            self.assertEqual(missing_executable.returncode, 2)
            self.assertIn("tool_missing", missing_executable.stderr)

    def test_shared_editor_surfaces_select_clangd_only(self) -> None:
        extensions = json.loads((PROJECT_ROOT / ".vscode/extensions.json").read_text(encoding="utf-8"))
        recommendations = extensions["recommendations"]
        self.assertIn("llvm-vs-code-extensions.vscode-clangd", recommendations)
        self.assertIn("xaver.clang-format", recommendations)
        self.assertNotIn("ms-vscode.cpptools", recommendations)

        settings = json.loads((PROJECT_ROOT / ".vscode/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["C_Cpp.intelliSenseEngine"], "disabled")
        self.assertEqual(settings["C_Cpp.errorSquiggles"], "disabled")
        self.assertEqual(settings["clangd.path"], "clangd")
        self.assertEqual(settings["clang-format.executable"], "clang-format")
        self.assertEqual(settings["[cpp]"]["editor.defaultFormatter"], "xaver.clang-format")
        self.assertIn("--compile-commands-dir=${workspaceFolder}/build/cpp/dev", settings["clangd.arguments"])

        c_cpp = json.loads((PROJECT_ROOT / ".vscode/c_cpp_properties.json").read_text(encoding="utf-8"))
        self.assertEqual(c_cpp["configurations"], [])
        self.assertNotIn("includePath", json.dumps(c_cpp))

        tasks = json.loads((PROJECT_ROOT / ".vscode/tasks.json").read_text(encoding="utf-8"))
        task_text = json.dumps(tasks)
        self.assertIn("static_analysis/cpp/static_analysis.py", task_text)
        self.assertIn("${file}", task_text)
        self.assertIn("C++: Select Compile Database", task_text)


if __name__ == "__main__":
    unittest.main()
