# @dependency-start
# contract test
# responsibility Verifies the derived C++ root-surface structure and review-routing contract.
# upstream design ../../documents/design/cpp-build-layout.md owns the canonical C++ path map.
# upstream design ../../documents/structure/repo-structure-contract.toml exposes optional derived-repository paths.
# downstream implementation ../../tools/agent_tools/manifest_rendering.py routes changed native paths to C++ review.
# @dependency-end

"""Regression tests for the derived-repository C++ root surface."""

from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from manifest_rendering import language_review_candidates  # noqa: E402


class CppRootSurfaceContractTest(unittest.TestCase):
    """Keep native ownership at the repository root without a cpp/ requirement."""

    def test_canonical_root_paths_select_cpp_review(self) -> None:
        """Every canonical native production/test path activates C++ review."""
        candidates = language_review_candidates(
            PROJECT_ROOT,
            (
                "CMakeLists.txt",
                "cmake/ProjectOptions.cmake",
                "include/project/api.hpp",
                "src/model.cpp",
                "tests/cpp/adapter.cpp",
                "experiments/cpp/experiment.cpp",
            ),
        )

        self.assertIn("cpp_reviewer", candidates)

    def test_derived_structure_contract_exposes_only_root_cpp_surface(self) -> None:
        """The derived profile accepts root native paths and does not expose cpp/."""
        contract_path = (
            PROJECT_ROOT / "documents" / "structure" / "repo-structure-contract.toml"
        )
        contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
        profiles = contract["profile"]
        derived_profile = next(
            profile
            for profile in profiles
            if profile["id"] == "template_or_derived_repo"
        )
        optional_paths = {entry["path"] for entry in derived_profile["optional"]}

        self.assertTrue(
            {
                "CMakeLists.txt",
                "cmake",
                "include",
                "src",
                "tests/cpp",
                "experiments/cpp",
            }.issubset(optional_paths)
        )
        self.assertNotIn("cpp", optional_paths)


if __name__ == "__main__":
    unittest.main()
