# @dependency-start
# responsibility Tests llama.cpp installer behavior.
# upstream implementation ../../tools/install_llama_cpp.sh builds llama.cpp under AGENT_CANON_TOOLS_HOME
# upstream design ../../documents/local-llm-responsibility-analysis.md local LLM install boundary
# @dependency-end

"""Tests for the shared llama.cpp installer."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "install_llama_cpp.sh"


class InstallLlamaCppTest(unittest.TestCase):
    """Exercise llama.cpp installer routes without network access."""

    def test_skips_missing_source_without_fetch(self) -> None:
        """Canon update rebuild should not clone llama.cpp on hosts without source."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            self.write_fake_git_and_cmake(fake_bin)

            result = subprocess.run(
                ["bash", str(SCRIPT), "--skip-missing-source"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TOOLS_HOME": str(tools_home),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_CANON_LLAMA_CPP=skipped_missing_source", result.stdout)
            self.assertFalse((tools_home / "src" / "llama.cpp").exists())

    def test_builds_existing_source_checkout(self) -> None:
        """Existing post-create llama.cpp source should rebuild on canon update."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            source = tools_home / "src" / "llama.cpp"
            (source / ".git").mkdir(parents=True)
            (source / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
            self.write_fake_git_and_cmake(fake_bin)

            result = subprocess.run(
                ["bash", str(SCRIPT), "--skip-missing-source", "--force"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TOOLS_HOME": str(tools_home),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_CANON_LLAMA_CPP=rebuilt", result.stdout)
            self.assertTrue((tools_home / "bin" / "llama-cli").is_symlink())
            self.assertTrue((tools_home / "bin" / "llama-server").is_symlink())

    def write_fake_git_and_cmake(self, fake_bin: Path) -> None:
        """Write fake git and cmake executables for installer tests."""
        fake_bin.mkdir()
        git = fake_bin / "git"
        git.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        git.chmod(0o755)
        cmake = fake_bin / "cmake"
        cmake.write_text(
            "#!/usr/bin/env bash\n"
            "if [ \"$1\" = '--build' ]; then\n"
            "  build_dir=\"$2\"\n"
            "  mkdir -p \"$build_dir/bin\"\n"
            "  for name in llama-cli llama-server; do\n"
            "    cat >\"$build_dir/bin/$name\" <<'SH'\n"
            "#!/usr/bin/env bash\n"
            "exit 0\n"
            "SH\n"
            "    chmod +x \"$build_dir/bin/$name\"\n"
            "  done\n"
            "  exit 0\n"
            "fi\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = '-B' ]; then mkdir -p \"$2\"; shift 2; else shift; fi\n"
            "done\n",
            encoding="utf-8",
        )
        cmake.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
