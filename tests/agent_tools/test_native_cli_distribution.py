# @dependency-start
# contract test
# responsibility Verifies native CLI archive layout, checksums, source-free behavior, and wrapper handoff.
# upstream implementation ../../tools/agent/templates/template_bundle.py native package producer
# upstream implementation ../../tools/bin/agent-canon source checkout entrypoint
# downstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs native CLI entrypoint
# @dependency-end
"""Native AgentCanon package checks and source-free command smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.agent.templates.template_bundle import package_native_cli  # noqa: E402


def _source_fixture(root: Path) -> Path:
    source = root / "source"
    files = {
        "documents/contracts/template-bundle-manifest.toml": (
            'version = 1\nsource_index = "templates/README.md"\n\n'
            "[profiles.native-cli]\n"
            'roots = ["LICENSE"]\n'
            "\n[profiles.native-cli.layout]\n"
            '"LICENSE" = "LICENSE"\n'
        ),
        "tools/runtime/dispatch/agent-canon/Cargo.toml": (
            '[package]\nname = "agent-canon"\nversion = "0.1.0"\n'
        ),
        "LICENSE": "Fixture license\n",
    }
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.name", "Native fixture"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "native@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(source), "add", "--all"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
    return source


def test_native_packages_include_layout_provenance_and_archive_checksums(
    tmp_path: Path,
) -> None:
    source = _source_fixture(tmp_path)
    binary = tmp_path / "agent-canon"
    binary.write_bytes(b"fixture native executable")
    result = package_native_cli(
        source_root=source,
        source_ref="HEAD",
        binary=binary,
        target="x86_64-unknown-linux-gnu",
        output=tmp_path / "packages",
        toolchain="rustc fixture",
    )
    assert result["schema"] == "agent-canon.native-cli-package.v1"
    assert result["version"] == "0.1.0"
    assert len(result["archives"]) == 2

    for item in result["archives"]:
        archive_path = Path(item["path"])
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == item["sha256"]
        checksum = archive_path.with_name(f"{archive_path.name}.sha256")
        assert checksum.read_text(encoding="ascii") == (
            f"{item['sha256']}  {archive_path.name}\n"
        )
        with tempfile.TemporaryDirectory() as extracted_name:
            extracted = Path(extracted_name)
            if archive_path.name.endswith(".zip"):
                with zipfile.ZipFile(archive_path) as archive:
                    archive.extractall(extracted)
            else:
                with tarfile.open(archive_path, "r:gz") as archive:
                    archive.extractall(extracted, filter="data")
            package = extracted / "agent-canon-0.1.0-x86_64-unknown-linux-gnu"
            assert (package / "bin/agent-canon").read_bytes() == binary.read_bytes()
            assert not (package / "share/agent-canon/private_feedback.py").exists()
            provenance = json.loads(
                (package / "share/agent-canon/provenance.json").read_text(
                    encoding="utf-8"
                )
            )
            assert provenance["source_commit"] == result["source_commit"]
            assert provenance["target"] == "x86_64-unknown-linux-gnu"
            checksum_rows = (
                (package / "share/agent-canon/SHA256SUMS")
                .read_text(encoding="ascii")
                .splitlines()
            )
            for row in checksum_rows:
                digest, relative = row.split("  ", 1)
                assert (
                    hashlib.sha256((package / relative).read_bytes()).hexdigest()
                    == digest
                )


def test_source_wrapper_execs_native_candidate_and_preserves_exit_status(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    wrapper = source / "tools/bin/agent-canon"
    wrapper.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "tools/bin/agent-canon", wrapper)
    native = tmp_path / "native"
    native.write_text(
        "#!/bin/sh\nprintf 'native:%s\\n' \"$*\"\nexit 7\n", encoding="utf-8"
    )
    native.chmod(0o755)
    result = subprocess.run(
        [str(wrapper), "codex-config", "--source-config", "custom.toml"],
        cwd=tmp_path,
        env={**os.environ, "AGENT_CANON_NATIVE_BIN": str(native)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 7
    assert result.stdout == "native:codex-config --source-config custom.toml\n"
    assert result.stderr == ""

    self_reference = subprocess.run(
        [str(wrapper), "--version"],
        cwd=tmp_path,
        env={**os.environ, "AGENT_CANON_NATIVE_BIN": str(wrapper)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert self_reference.returncode == 2
    assert "resolves to its source wrapper" in self_reference.stderr


def _smoke_package(package_dir: Path, target: str, version: str) -> None:
    expected_root = f"agent-canon-{version}-{target}"
    executable_name = (
        "agent-canon.exe" if target.endswith("-windows-msvc") else "agent-canon"
    )
    archives = sorted(
        [
            *package_dir.glob(f"{expected_root}.tar.gz"),
            *package_dir.glob(f"{expected_root}.zip"),
        ]
    )
    if len(archives) != 2:
        raise AssertionError(f"expected tar.gz and zip packages under {package_dir}")
    for archive_path in archives:
        expected_checksum = archive_path.with_name(f"{archive_path.name}.sha256")
        row = expected_checksum.read_text(encoding="ascii").split()
        if len(row) != 2 or row[1] != archive_path.name:
            raise AssertionError(f"invalid archive checksum file: {expected_checksum}")
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != row[0]:
            raise AssertionError(f"archive checksum mismatch: {archive_path}")

        with tempfile.TemporaryDirectory(
            prefix="agent-canon-consumer-", dir=package_dir.parent
        ) as temp_name:
            temporary = Path(temp_name)
            if archive_path.name.endswith(".zip"):
                with zipfile.ZipFile(archive_path) as archive:
                    binary_member = next(
                        member
                        for member in archive.infolist()
                        if member.filename.endswith(f"/bin/{executable_name}")
                    )
                    binary_mode = (binary_member.external_attr >> 16) & 0o777
                    archive.extractall(temporary)
            else:
                with tarfile.open(archive_path, "r:gz") as archive:
                    archive.extractall(temporary, filter="data")
            package = temporary / expected_root
            executable = package / "bin" / executable_name
            if (package / "share/agent-canon/private_feedback.py").exists():
                raise AssertionError("retired feedback implementation remains in native package")
            license_path = package / "LICENSE"
            provenance_path = package / "share/agent-canon/provenance.json"
            sums_path = package / "share/agent-canon/SHA256SUMS"
            if not all(
                path.is_file()
                for path in (
                    executable,
                    license_path,
                    provenance_path,
                    sums_path,
                )
            ):
                raise AssertionError(
                    "native package is missing an executable or declared resource"
                )
            if archive_path.name.endswith(".zip") and os.name != "nt":
                executable.chmod(binary_mode)
            for line in sums_path.read_text(encoding="ascii").splitlines():
                digest, relative = line.split("  ", 1)
                if (
                    hashlib.sha256((package / relative).read_bytes()).hexdigest()
                    != digest
                ):
                    raise AssertionError(f"package checksum mismatch: {relative}")

            consumer = temporary / "consumer"
            consumer.mkdir()
            env = os.environ.copy()
            env["AGENT_CANON_SOURCE_ROOT"] = str(consumer)
            env["AGENT_CANON_RUNTIME_TOOLS_ROOT"] = str(consumer)
            env.pop("AGENT_CANON_NATIVE_BIN", None)
            env["AGENT_CANON_PYTHON"] = str(temporary / "python-must-not-run")
            version_result = subprocess.run(
                [str(executable), "--version"],
                cwd=consumer,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if (
                version_result.returncode != 0
                or version_result.stdout != f"agent-canon {version}\n"
            ):
                raise AssertionError(f"--version failed: {version_result.stderr}")
            help_result = subprocess.run(
                [str(executable), "--help"],
                cwd=consumer,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if (
                help_result.returncode != 0
                or "Usage: agent-canon" not in help_result.stdout
                or help_result.stderr
            ):
                raise AssertionError("native --help did not use stdout and exit 0")
            invalid_result = subprocess.run(
                [str(executable), "unknown-command"],
                cwd=consumer,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if (
                invalid_result.returncode != 2
                or invalid_result.stdout
                or "unknown" not in invalid_result.stderr
            ):
                raise AssertionError("invalid command status or streams changed")

            canonical = consumer / "canonical.toml"
            canonical.write_text(
                "model_context_window = 1050000\n"
                "model_auto_compact_token_limit = 900000\n",
                encoding="utf-8",
            )
            personal = (
                "# keep this comment\napproval_policy = 'never'\n"
                "provider = 'custom'\nmodel_context_window = 1\n"
                "[profiles.custom]\nkeep = true\n"
            )
            config_result = subprocess.run(
                [str(executable), "codex-config", "--source-config", str(canonical)],
                cwd=consumer,
                env=env,
                input=personal,
                check=False,
                capture_output=True,
                text=True,
            )
            if config_result.returncode != 0 or config_result.stderr:
                raise AssertionError(f"codex-config failed: {config_result.stderr}")
            if (
                "model_context_window = 1050000" not in config_result.stdout
                or "provider = 'custom'" not in config_result.stdout
                or "keep = true" not in config_result.stdout
                or "# keep this comment" not in config_result.stdout
            ):
                raise AssertionError("codex-config did not preserve custom TOML values")

            runtime = temporary / "private-runtime"
            log_root = temporary / "private-log"
            feedback_result = subprocess.run(
                [
                    str(executable),
                    "knowledge",
                    "--runtime-root",
                    str(runtime),
                    "--log-root",
                    str(log_root),
                    "add",
                    "distribution-smoke",
                    "private body",
                    "--run",
                    "smoke-run",
                    "--task",
                    "smoke-task",
                ],
                cwd=consumer,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if (
                feedback_result.returncode != 0
                or "private body" in feedback_result.stdout
            ):
                raise AssertionError(
                    f"packaged native feedback failed: {feedback_result.stderr}"
                )
            if not (
                runtime
                / "spool/private-feedback/knowledge/topics/distribution-smoke/candidate.md"
            ).is_file():
                raise AssertionError(
                    "packaged native feedback wrote no private record"
                )
            for family, topic in (("k", "knowledge-alias"), ("f", "feedback-alias")):
                alias_result = subprocess.run(
                    [
                        str(executable),
                        family,
                        "--runtime-root",
                        str(runtime),
                        "--log-root",
                        str(log_root),
                        "add",
                        topic,
                        "alias body",
                        "--task",
                        "alias-smoke",
                    ],
                    cwd=consumer,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if alias_result.returncode != 0 or "alias body" in alias_result.stdout:
                    raise AssertionError(
                        f"packaged {family} alias failed: {alias_result.stderr}"
                    )

            lock_ready = temporary / "lock-ready"
            lock_release = temporary / "lock-release"
            # Independent OS oracle: the package no longer contains Python code.
            lock_script = (
                "import os, sys, time\n"
                "from pathlib import Path\n"
                "runtime, ready, release = map(Path, sys.argv[1:])\n"
                "path = runtime / 'spool/.private-feedback.lock'\n"
                "path.parent.mkdir(parents=True, exist_ok=True)\n"
                "with path.open('a+b') as lock:\n"
                " if path.stat().st_size == 0: lock.write(b'\\0'); lock.flush()\n"
                " lock.seek(0)\n"
                " if os.name == 'nt':\n"
                "  import msvcrt\n"
                "  msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)\n"
                " else:\n"
                "  import fcntl\n"
                "  fcntl.flock(lock.fileno(), fcntl.LOCK_EX)\n"
                " ready.write_text('ready', encoding='utf-8')\n"
                " while not release.exists(): time.sleep(0.01)\n"
                " lock.seek(0)\n"
                " if os.name == 'nt': msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)\n"
                " else: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)\n"
            )
            lock_holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    lock_script,
                    str(runtime),
                    str(lock_ready),
                    str(lock_release),
                ],
                cwd=consumer,
                env={**env, "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            locked_writer: subprocess.Popen[str] | None = None
            writer_waited = False
            record = (
                runtime
                / "spool/private-feedback/knowledge/topics/distribution-lock/candidate.md"
            )
            try:
                deadline = time.monotonic() + 10
                while not lock_ready.is_file() and lock_holder.poll() is None:
                    if time.monotonic() >= deadline:
                        raise AssertionError(
                            "packaged native feedback did not acquire its spool lock"
                        )
                    time.sleep(0.01)
                if not lock_ready.is_file():
                    raise AssertionError(
                        "packaged lock holder exited before acquiring the lock"
                    )
                locked_writer = subprocess.Popen(
                    [
                        str(executable),
                        "knowledge",
                        "--runtime-root",
                        str(runtime),
                        "--log-root",
                        str(log_root),
                        "add",
                        "distribution-lock",
                        "locked body",
                        "--task",
                        "lock-smoke",
                    ],
                    cwd=consumer,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                time.sleep(0.25)
                writer_waited = locked_writer.poll() is None and not record.exists()
            finally:
                lock_release.touch()
                holder_output, holder_error = lock_holder.communicate(timeout=10)
                if locked_writer is not None and locked_writer.poll() is None:
                    locked_writer.communicate(timeout=10)
            if lock_holder.returncode != 0:
                raise AssertionError(
                    f"packaged native feedback lock holder failed: {holder_error}"
                )
            if not writer_waited or locked_writer is None:
                raise AssertionError(
                    "private feedback writer did not wait on the packaged lock"
                )
            writer_output, writer_error = locked_writer.communicate(timeout=10)
            if locked_writer.returncode != 0 or "locked body" in writer_output:
                raise AssertionError(f"packaged native feedback writer failed: {writer_error}")
            if not record.is_file():
                raise AssertionError(
                    "locked feedback writer produced no private record"
                )

            bare = temporary / "without-resources/bin" / executable_name
            bare.parent.mkdir(parents=True)
            shutil.copyfile(executable, bare)
            if os.name != "nt":
                bare.chmod(0o755)
            bare_feedback = subprocess.run(
                [
                    str(bare),
                    "knowledge",
                    "--runtime-root",
                    str(runtime),
                    "--log-root",
                    str(log_root),
                    "status",
                ],
                cwd=consumer,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if bare_feedback.returncode != 0 or bare_feedback.stderr:
                raise AssertionError("bare native feedback still needs an implementation adapter")
            if json.loads(bare_feedback.stdout).get("schema") != "agent-canon.private-feedback.v1":
                raise AssertionError("bare native feedback returned no metadata receipt")


def test_source_free_package_smoke_when_binary_package_is_supplied() -> None:
    package_dir = os.environ.get("AGENT_CANON_NATIVE_PACKAGE_DIR")
    target = os.environ.get("AGENT_CANON_NATIVE_TARGET")
    version = os.environ.get("AGENT_CANON_NATIVE_VERSION")
    if not package_dir or not target or not version:
        if pytest is None:
            return
        pytest.skip("native package smoke inputs are not configured")
    _smoke_package(Path(package_dir), target, version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    _smoke_package(Path(args.package_dir), args.target, args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
