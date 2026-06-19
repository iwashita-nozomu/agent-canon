# @dependency-start
# contract test
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

    def test_force_cuda_is_compatibility_input_and_builds_cpu_only(self) -> None:
        """Explicit CUDA mode should be accepted only as a CPU-only compatibility input."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            cmake_log = root / "cmake.log"
            cuda_driver = root / "cuda-driver"
            source = tools_home / "src" / "llama.cpp"
            (source / ".git").mkdir(parents=True)
            (source / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
            cuda_driver.mkdir()
            (cuda_driver / "libcuda.so.1").write_text("", encoding="utf-8")
            self.write_fake_git_and_cmake(fake_bin)
            self.write_fake_nvcc(fake_bin)
            self.write_fake_nvidia_smi(fake_bin)

            result = subprocess.run(
                ["bash", str(SCRIPT), "--skip-missing-source", "--force"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TOOLS_HOME": str(tools_home),
                    "AGENT_CANON_LLAMA_CPP_CUDA": "1",
                    "AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR": str(cuda_driver),
                    "AGENT_CANON_LLAMA_CPP_CMAKE_ARGS": "-DGGML_NATIVE=OFF",
                    "AGENT_CANON_LLAMA_CPP_BUILD_JOBS": "7",
                    "AGENT_CANON_TEST_CMAKE_LOG": str(cmake_log),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            log_text = cmake_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_LLAMA_CPP_CUDA_REQUESTED=1", result.stdout)
        self.assertIn("AGENT_CANON_LLAMA_CPP_CUDA_REQUEST_POLICY=ignored_cpu_only", result.stdout)
        self.assertIn("AGENT_CANON_LLAMA_CPP_BUILD_JOBS=7", result.stdout)
        self.assertNotIn(f"AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR={cuda_driver}", result.stdout)
        self.assert_cpu_only_build(result.stdout, log_text)
        self.assertNotIn("-DCMAKE_EXE_LINKER_FLAGS=", log_text)
        self.assertNotIn("rpath-link", log_text)
        self.assertNotIn(str(cuda_driver), log_text)
        self.assertIn("-DGGML_NATIVE=OFF", log_text)
        self.assertIn("--build", log_text)
        self.assertIn(" -j 7 ", f" {log_text} ")

    def test_auto_cuda_is_compatibility_input_and_builds_cpu_only(self) -> None:
        """Auto CUDA should not enable GPU build even when GPU runtime is visible."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            cmake_log = root / "cmake.log"
            missing_driver = root / "missing-driver"
            source = tools_home / "src" / "llama.cpp"
            (source / ".git").mkdir(parents=True)
            (source / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
            self.write_fake_git_and_cmake(fake_bin)
            self.write_fake_nvcc(fake_bin)
            self.write_fake_nvidia_smi(fake_bin)

            result = subprocess.run(
                ["bash", str(SCRIPT), "--skip-missing-source", "--force"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TOOLS_HOME": str(tools_home),
                    "AGENT_CANON_LLAMA_CPP_CUDA": "auto",
                    "AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR": str(missing_driver),
                    "AGENT_CANON_TEST_CMAKE_LOG": str(cmake_log),
                    "NVIDIA_VISIBLE_DEVICES": "0",
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            log_text = cmake_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_LLAMA_CPP_CUDA_REQUESTED=auto", result.stdout)
        self.assertIn("AGENT_CANON_LLAMA_CPP_CUDA_REQUEST_POLICY=ignored_cpu_only", result.stdout)
        self.assert_cpu_only_build(result.stdout, log_text)

    def test_cuda_disable_omits_gpu_cmake_option(self) -> None:
        """Explicit CUDA disable should win over any runtime GPU visibility."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            cmake_log = root / "cmake.log"
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
                    "AGENT_CANON_LLAMA_CPP_CUDA": "0",
                    "AGENT_CANON_TEST_CMAKE_LOG": str(cmake_log),
                    "NVIDIA_VISIBLE_DEVICES": "0",
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            log_text = cmake_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_cpu_only_build(result.stdout, log_text)

    def test_cpu_only_config_change_rebuilds_current_binary_without_force(self) -> None:
        """CPU-only build flag changes should invalidate an otherwise current binary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "fake-bin"
            tools_home = root / "tools-home"
            cmake_log = root / "cmake.log"
            cuda_driver = root / "cuda-driver"
            source = tools_home / "src" / "llama.cpp"
            build_dir = tools_home / "build" / "llama.cpp"
            install_dir = tools_home / "bin"
            (source / ".git").mkdir(parents=True)
            (source / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8"
            )
            build_dir.mkdir(parents=True)
            install_dir.mkdir(parents=True)
            cuda_driver.mkdir()
            (cuda_driver / "libcuda.so.1").write_text("", encoding="utf-8")
            (build_dir / "agent-canon-build-config.txt").write_text(
                "cuda_backend=disabled\n"
                "cmake_args=-DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=ON -DGGML_CUDA=OFF\n",
                encoding="utf-8",
            )
            for name in ("llama-cli", "llama-server"):
                binary = install_dir / name
                binary.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                binary.chmod(0o755)
            self.write_fake_git_and_cmake(fake_bin)
            self.write_fake_nvcc(fake_bin)
            self.write_fake_nvidia_smi(fake_bin)

            result = subprocess.run(
                ["bash", str(SCRIPT), "--skip-missing-source"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TOOLS_HOME": str(tools_home),
                    "AGENT_CANON_LLAMA_CPP_CUDA": "1",
                    "AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR": str(cuda_driver),
                    "AGENT_CANON_TEST_CMAKE_LOG": str(cmake_log),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            log_text = cmake_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_LLAMA_CPP=rebuilt", result.stdout)
        self.assertIn("AGENT_CANON_LLAMA_CPP_CUDA_REQUESTED=1", result.stdout)
        self.assert_cpu_only_build(result.stdout, log_text)

    def test_cmake_extra_args_cannot_enable_accelerators(self) -> None:
        """Extra CMake flags must not bypass the local LLM CPU-only policy."""
        for rejected_arg in (
            "-DGGML_CUDA=ON",
            "-DGGML_CUDA=on",
            "-DGGML_CUDA:BOOL=On",
            "-DGGML_CUDA:STRING=YES",
            "-DGGML_HIP=true",
            "-DGGML_METAL=1",
            "-DGGML_VULKAN:BOOL=yes",
            "-DGGML_SYCL:STRING=TRUE",
            "-DGGML_OPENCL=on",
            "-DLLAMA_CUBLAS=True",
        ):
            with self.subTest(rejected_arg=rejected_arg):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    fake_bin = root / "fake-bin"
                    tools_home = root / "tools-home"
                    cmake_log = root / "cmake.log"
                    source = tools_home / "src" / "llama.cpp"
                    (source / ".git").mkdir(parents=True)
                    (source / "CMakeLists.txt").write_text(
                        "cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8"
                    )
                    self.write_fake_git_and_cmake(fake_bin)

                    result = subprocess.run(
                        ["bash", str(SCRIPT), "--skip-missing-source", "--force"],
                        check=False,
                        capture_output=True,
                        text=True,
                        env={
                            **os.environ,
                            "AGENT_CANON_TOOLS_HOME": str(tools_home),
                            "AGENT_CANON_LLAMA_CPP_CMAKE_ARGS": rejected_arg,
                            "AGENT_CANON_TEST_CMAKE_LOG": str(cmake_log),
                            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                        },
                    )

                self.assertEqual(result.returncode, 2)
                self.assertIn("AGENT_CANON_LLAMA_CPP=fail", result.stdout)
                self.assertIn(
                    f"AGENT_CANON_LLAMA_CPP_ERROR=cpu_only_policy_rejects_cmake_arg:{rejected_arg}",
                    result.stdout,
                )
                self.assertFalse(cmake_log.exists())

    def assert_cpu_only_build(self, stdout: str, log_text: str) -> None:
        """Assert common CPU-only installer evidence."""
        self.assertIn("AGENT_CANON_LLAMA_CPP_CUDA=disabled", stdout)
        self.assertIn("AGENT_CANON_LLAMA_CPP_ACCELERATOR_POLICY=cpu_only", stdout)
        self.assertIn("-DGGML_CUDA=OFF", log_text)
        self.assertIn("-DGGML_METAL=OFF", log_text)
        self.assertIn("-DGGML_HIP=OFF", log_text)
        self.assertIn("-DGGML_VULKAN=OFF", log_text)
        self.assertIn("-DGGML_SYCL=OFF", log_text)
        self.assertNotIn("-DGGML_CUDA=ON", log_text)

    def write_fake_git_and_cmake(self, fake_bin: Path) -> None:
        """Write fake git and cmake executables for installer tests."""
        fake_bin.mkdir()
        git = fake_bin / "git"
        git.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        git.chmod(0o755)
        cmake = fake_bin / "cmake"
        cmake.write_text(
            "#!/usr/bin/env bash\n"
            "if [ -n \"${AGENT_CANON_TEST_CMAKE_LOG:-}\" ]; then\n"
            "  printf 'cmake' >>\"$AGENT_CANON_TEST_CMAKE_LOG\"\n"
            "  printf ' %q' \"$@\" >>\"$AGENT_CANON_TEST_CMAKE_LOG\"\n"
            "  printf '\\n' >>\"$AGENT_CANON_TEST_CMAKE_LOG\"\n"
            "fi\n"
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

    def write_fake_nvcc(self, fake_bin: Path) -> None:
        """Write a fake nvcc executable for CUDA routing tests."""
        fake_bin.mkdir(exist_ok=True)
        nvcc = fake_bin / "nvcc"
        nvcc.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        nvcc.chmod(0o755)

    def write_fake_nvidia_smi(self, fake_bin: Path) -> None:
        """Write a fake nvidia-smi executable that reports one device."""
        fake_bin.mkdir(exist_ok=True)
        nvidia_smi = fake_bin / "nvidia-smi"
        nvidia_smi.write_text(
            "#!/usr/bin/env bash\n"
            "if [ \"${1:-}\" = '-L' ]; then echo 'GPU 0: fixture'; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        nvidia_smi.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
