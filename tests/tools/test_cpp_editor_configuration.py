# @dependency-start
# contract test
# responsibility Preserves shared C++ editor settings and direct native task wiring.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared editor surface ownership
# downstream implementation ../../.vscode/extensions.json shared extension recommendations
# downstream implementation ../../.vscode/settings.json shared provider settings
# downstream implementation ../../.vscode/tasks.json direct C++ task entrypoints
# @dependency-end
"""Retain shared editor policy after retiring the compile-database bridge."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CppEditorConfigurationTest(unittest.TestCase):
    """Keep shared editor configuration separate from consumer CMake state."""

    def test_shared_editor_surfaces_select_native_cpp_tools(self) -> None:
        extensions = json.loads(
            (PROJECT_ROOT / ".vscode/extensions.json").read_text(encoding="utf-8")
        )
        recommendations = extensions["recommendations"]
        self.assertIn("llvm-vs-code-extensions.vscode-clangd", recommendations)
        self.assertIn("xaver.clang-format", recommendations)
        self.assertIn("ms-vscode.cmake-tools", recommendations)
        self.assertNotIn("ms-vscode.cpptools", recommendations)

        settings = json.loads(
            (PROJECT_ROOT / ".vscode/settings.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("clangd.arguments", settings)
        self.assertEqual(settings["clangd.path"], "clangd")
        self.assertEqual(settings["clang-format.executable"], "clang-format")
        self.assertEqual(
            settings["[cpp]"]["editor.defaultFormatter"], "xaver.clang-format"
        )
        self.assertEqual(settings["C_Cpp.intelliSenseEngine"], "disabled")
        self.assertEqual(settings["C_Cpp.errorSquiggles"], "disabled")

        c_cpp = json.loads(
            (PROJECT_ROOT / ".vscode/c_cpp_properties.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(c_cpp["configurations"], [])
        self.assertNotIn("includePath", json.dumps(c_cpp))

        tasks = json.loads(
            (PROJECT_ROOT / ".vscode/tasks.json").read_text(encoding="utf-8")
        )
        by_label = {task["label"]: task for task in tasks["tasks"]}
        input_ids = {item["id"] for item in tasks.get("inputs", [])}
        self.assertNotIn("cppBuildDirectory", input_ids)
        self.assertNotIn("C++: Select Compile Database", by_label)
        self.assertEqual(by_label["C++: clangd Check"]["type"], "process")
        self.assertEqual(by_label["C++: clangd Check"]["command"], "clangd")
        self.assertEqual(
            by_label["C++: clangd Check"]["args"],
            [
                "--check=${file}",
                "--compile-commands-dir=${command:cmake.buildDirectory}",
            ],
        )
        self.assertEqual(by_label["C++: clang-tidy"]["type"], "process")
        self.assertEqual(by_label["C++: clang-tidy"]["command"], "run-clang-tidy.py")
        self.assertEqual(
            by_label["C++: clang-tidy"]["args"],
            ["-p", "${command:cmake.buildDirectory}", "${file}"],
        )
        task_text = json.dumps(tasks)
        self.assertNotIn("static_analysis.py", task_text)
        self.assertNotIn("build/cpp/dev", task_text)


if __name__ == "__main__":
    unittest.main()
