# @dependency-start
# contract test
# responsibility Verifies native release integrity and publication recovery without network mutations.
# upstream implementation ../../tools/agent/templates/template_bundle.py native archive verification
# upstream implementation ../../tools/repository/github/native_release.py release state transitions
# @dependency-end
"""Distribution contracts runnable with the Python standard-library test runner."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.agent_tools.test_native_cli_distribution import _source_fixture
from tools.agent.templates.template_bundle import (
    TemplateBundleError,
    _native_archive_payload,
    _native_tar_bytes,
    _native_zip_bytes,
    native_release_version,
    package_native_cli,
    verify_native_packages,
)
from tools.repository.github.github_publish import CommandResult
from tools.repository.github.native_release import (
    NativeReleaseError,
    publish_native_release,
    require_mainline_source,
    select_native_artifacts,
)


class FakeGitHub:
    """Stateful gh boundary: uploaded bytes and draft state survive a failed call."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.release: dict[str, Any] | None = None
        self.tagged: str | None = None
        self.fail_upload = False
        self.hide_draft_lists = False

    def __call__(self, command: Sequence[str]) -> CommandResult:
        args = list(command)
        self.commands.append(args)
        stdout, stderr, code = "", "", 0
        if args[:3] == ["gh", "api", "--include"]:
            if "/git/ref/tags/" in args[3]:
                value = (
                    {"object": {"type": "commit", "sha": self.tagged}}
                    if self.tagged
                    else None
                )
            elif "/releases?" in args[3]:
                value = (
                    [self.release] if self.release and not self.hide_draft_lists else []
                )
            elif "/releases/tags/" in args[3]:
                value = (
                    self.release if self.release and not self.release["draft"] else None
                )
            else:
                value = self.release
            status = 200 if value is not None else 404
            stdout = f"HTTP/2.0 {status}\ncontent-type: application/json\n\n{json.dumps(value)}"
            code = 0 if value is not None else 1
        elif args[:4] == ["gh", "api", "--method", "POST"]:
            if args[4].startswith("https://uploads.github.com/"):
                assert self.release is not None
                path = Path(args[args.index("--input") + 1])
                self.release["assets"].append(
                    {
                        "name": path.name,
                        "state": "uploaded",
                        "size": path.stat().st_size,
                        "digest": "sha256:"
                        + hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
                if self.fail_upload:
                    code, stderr = 1, "interrupted after one upload"
                else:
                    stdout = json.dumps(self.release["assets"][-1])
            else:
                fields = dict(value.split("=", 1) for value in args[6::2])
                self.release = {
                    "id": 1,
                    "tag_name": fields["tag_name"],
                    "draft": True,
                    "prerelease": False,
                    "target_commitish": fields["target_commitish"],
                    "assets": [],
                    "html_url": "https://github.com/owner/repo/releases/tag/untagged-test",
                }
                stdout = json.dumps(self.release)
        elif args[:4] == ["gh", "api", "--method", "PATCH"]:
            assert self.release is not None
            self.release["draft"] = False
            if self.tagged is None:
                self.tagged = self.release["target_commitish"]
        else:
            raise AssertionError(args)
        return CommandResult(tuple(args), code, stdout, stderr)

    def writes(self) -> list[list[str]]:
        return [
            args
            for args in self.commands
            if args[:2] == ["gh", "release"] or args[:3] == ["gh", "api", "--method"]
        ]

    def publications(self) -> list[list[str]]:
        return [
            args
            for args in self.commands
            if args[:4] == ["gh", "api", "--method", "PATCH"]
        ]


@dataclass(frozen=True)
class NativeReleaseFixture:
    root: Path
    source: Path
    target: str
    packages: Path
    identity: dict[str, Any]
    prefix: str


class NativeReleaseTest(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self._fixture: NativeReleaseFixture | None = None

    @property
    def fixture(self) -> NativeReleaseFixture:
        assert self._fixture is not None, "unittest setUp must prepare the fixture"
        return self._fixture

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="native-release-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = _source_fixture(root)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "update-ref",
                "refs/remotes/origin/main",
                "HEAD",
            ],
            check=True,
        )
        binary = root / "agent-canon"
        binary.write_bytes(b"fixture-native-binary")
        target = "x86_64-unknown-linux-gnu"
        packages = root / "packages"
        identity = package_native_cli(
            source_root=source,
            source_ref="HEAD",
            binary=binary,
            target=target,
            output=packages,
            toolchain="rustc fixture",
        )
        self._fixture = NativeReleaseFixture(
            root,
            source,
            target,
            packages,
            identity,
            f"agent-canon-0.1.0-{target}",
        )

    def verify(self) -> dict[str, Any]:
        return verify_native_packages(
            source_root=self.fixture.source,
            source_ref="HEAD",
            root=self.fixture.packages,
            targets=[self.fixture.target],
        )

    def rewrite(
        self,
        change: Callable[[dict[str, bytes], dict[str, Any]], None],
        suffixes: tuple[str, ...] = ("tar.gz", "zip"),
    ) -> None:
        for suffix in suffixes:
            path = self.fixture.packages / f"{self.fixture.prefix}.{suffix}"
            payload = _native_archive_payload(path, self.fixture.prefix)
            provenance_path = "share/agent-canon/provenance.json"
            sums_path = "share/agent-canon/SHA256SUMS"
            provenance = json.loads(payload[provenance_path])
            change(payload, provenance)
            provenance["files"] = [
                {"path": name, "sha256": hashlib.sha256(payload[name]).hexdigest()}
                for name in sorted(payload)
                if name not in {provenance_path, sums_path}
            ]
            payload[provenance_path] = (
                json.dumps(provenance, indent=2, sort_keys=True) + "\n"
            ).encode()
            payload[sums_path] = "".join(
                f"{hashlib.sha256(payload[name]).hexdigest()}  {name}\n"
                for name in sorted(payload)
                if name != sums_path
            ).encode()
            contents = {
                name: (content, 0o755 if name.startswith("bin/") else 0o644)
                for name, content in payload.items()
            }
            writer = _native_tar_bytes if suffix == "tar.gz" else _native_zip_bytes
            path.write_bytes(writer(self.fixture.prefix, contents))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")

    def test_valid_archives_bind_all_files_to_the_source(self) -> None:
        result = self.verify()
        self.assertEqual(
            result["source_commit"], self.fixture.identity["source_commit"]
        )
        self.assertEqual(result["version"], "0.1.0")
        self.assertEqual(len(result["files"]), 4)
        self.assertEqual(result["targets"], [self.fixture.target])

    def test_checksum_mismatch_is_rejected(self) -> None:
        path = self.fixture.packages / f"{self.fixture.prefix}.tar.gz"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(TemplateBundleError, "archive checksum differs"):
            self.verify()

    def test_self_consistent_wrong_source_is_rejected(self) -> None:
        self.rewrite(
            lambda _payload, provenance: provenance.update(source_commit="0" * 40)
        )
        with self.assertRaisesRegex(TemplateBundleError, "source identity differs"):
            self.verify()

    def test_self_consistent_different_archive_payloads_are_rejected(self) -> None:
        self.rewrite(
            lambda payload, _provenance: payload.update(
                {"bin/agent-canon": b"another binary"}
            ),
            suffixes=("zip",),
        )
        with self.assertRaisesRegex(
            TemplateBundleError, "formats contain different payloads"
        ):
            self.verify()

    def test_extra_or_missing_target_files_are_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateBundleError, "file set differs"):
            verify_native_packages(
                source_root=self.fixture.source,
                source_ref="HEAD",
                root=self.fixture.packages,
                targets=[self.fixture.target, "aarch64-unknown-linux-gnu"],
            )
        (self.fixture.packages / "unexpected.txt").write_text("extra")
        with self.assertRaisesRegex(TemplateBundleError, "file set differs"):
            self.verify()

    def publish(
        self, github: FakeGitHub, *, check_only: bool = False
    ) -> dict[str, Any]:
        return publish_native_release(
            source_root=self.fixture.source,
            source_ref="HEAD",
            artifacts=self.fixture.packages,
            targets=[self.fixture.target],
            repo="owner/repo",
            tag="v0.1.0",
            runner=github,
            check_only=check_only,
        )

    def test_release_is_verified_before_any_remote_write(self) -> None:
        self.rewrite(
            lambda _payload, provenance: provenance.update(source_commit="0" * 40)
        )
        github = FakeGitHub()
        with self.assertRaises(TemplateBundleError):
            self.publish(github)
        self.assertEqual(github.commands, [])

    def test_draft_becomes_public_only_after_all_assets_are_verified(self) -> None:
        github = FakeGitHub()
        result = self.publish(github)
        self.assertEqual(result["status"], "published")
        assert github.release is not None
        self.assertFalse(github.release["draft"])
        self.assertEqual(len(github.release["assets"]), 4)
        self.assertEqual(github.writes()[-1][:4], ["gh", "api", "--method", "PATCH"])
        self.assertIn("make_latest=legacy", github.writes()[-1])

    def test_creation_response_is_used_while_tag_and_list_reads_lag(self) -> None:
        github = FakeGitHub()
        github.hide_draft_lists = True
        result = self.publish(github)
        self.assertEqual(result["status"], "published")
        creates = [
            args
            for args in github.writes()
            if args[:4] == ["gh", "api", "--method", "POST"]
            and not args[4].startswith("https://uploads.github.com/")
        ]
        self.assertEqual(len(creates), 1)

    def test_interrupted_upload_resumes_only_missing_assets(self) -> None:
        github = FakeGitHub()
        github.fail_upload = True
        with self.assertRaisesRegex(NativeReleaseError, "upload incomplete"):
            self.publish(github)
        assert github.release is not None
        self.assertTrue(github.release["draft"])
        uploaded = github.release["assets"][0]["name"]
        self.assertEqual(github.publications(), [])
        github.fail_upload = False
        result = self.publish(github)
        self.assertEqual(result["status"], "published")
        uploads = [
            args
            for args in github.writes()
            if args[:4] == ["gh", "api", "--method", "POST"]
            and args[4].startswith("https://uploads.github.com/")
        ]
        paths = [args[args.index("--input") + 1] for args in uploads[1:]]
        self.assertEqual(len(paths), 3)
        self.assertNotIn(uploaded, [Path(path).name for path in paths])
        self.assertFalse(any("--clobber" in args for args in github.commands))

    def test_published_release_reexecution_does_not_mutate_it(self) -> None:
        github = FakeGitHub()
        self.publish(github)
        writes = len(github.writes())
        self.assertEqual(self.publish(github)["status"], "already-published")
        self.assertEqual(len(github.writes()), writes)

    def test_conflicting_existing_asset_is_preserved(self) -> None:
        github = FakeGitHub()
        self.publish(github)
        assert github.release is not None
        github.release["assets"][0]["digest"] = "sha256:" + "0" * 64
        writes = len(github.writes())
        with self.assertRaisesRegex(
            NativeReleaseError, "existing release asset differs"
        ):
            self.publish(github)
        self.assertEqual(len(github.writes()), writes)

    def test_wrong_tag_commit_never_creates_a_release(self) -> None:
        github = FakeGitHub()
        github.tagged = "0" * 40
        with self.assertRaisesRegex(NativeReleaseError, "different source commit"):
            self.publish(github)
        self.assertEqual(github.writes(), [])

    def test_missing_mainline_does_not_issue_any_remote_write(self) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self.fixture.source),
                "update-ref",
                "-d",
                "refs/remotes/origin/main",
            ],
            check=True,
        )
        github = FakeGitHub()
        with self.assertRaisesRegex(NativeReleaseError, "first-parent history"):
            self.publish(github)
        self.assertEqual(github.commands, [])

    def test_check_only_does_not_create_a_draft(self) -> None:
        github = FakeGitHub()
        self.assertEqual(self.publish(github, check_only=True)["status"], "checked")
        self.assertEqual(github.writes(), [])

    def test_changed_draft_source_is_rejected_before_publication(self) -> None:
        class ChangedSourceGitHub(FakeGitHub):
            def __call__(self, command: Sequence[str]) -> CommandResult:
                result = super().__call__(command)
                if list(command[:4]) == ["gh", "api", "--method", "POST"] and command[
                    4
                ].startswith("https://uploads.github.com/"):
                    assert self.release is not None
                    self.release["target_commitish"] = "0" * 40
                return result

        github = ChangedSourceGitHub()
        with self.assertRaisesRegex(NativeReleaseError, "not bound"):
            self.publish(github)
        self.assertEqual(github.publications(), [])

    def test_unrelated_draft_assets_are_not_published(self) -> None:
        github = FakeGitHub()
        github.release = {
            "id": 1,
            "tag_name": "v0.1.0",
            "draft": True,
            "prerelease": False,
            "target_commitish": self.fixture.identity["source_commit"],
            "assets": [{"name": "unrelated.txt"}],
        }
        with self.assertRaisesRegex(NativeReleaseError, "unrelated assets"):
            self.publish(github)
        self.assertEqual(github.writes(), [])

    def test_changed_tag_is_rejected_before_publication(self) -> None:
        class ChangedTagGitHub(FakeGitHub):
            def __call__(self, command: Sequence[str]) -> CommandResult:
                result = super().__call__(command)
                if list(command[:4]) == ["gh", "api", "--method", "POST"] and command[
                    4
                ].startswith("https://uploads.github.com/"):
                    self.tagged = "0" * 40
                return result

        github = ChangedTagGitHub()
        with self.assertRaisesRegex(NativeReleaseError, "tag changed"):
            self.publish(github)
        self.assertEqual(github.publications(), [])


class NativeReleaseVersionTest(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True
        ).strip()

    def commit_file(self, root: Path, name: str, text: str) -> str:
        (root / name).write_text(text)
        self.git(root, "add", name)
        self.git(root, "commit", "-qm", name)
        return self.git(root, "rev-parse", "HEAD")

    def test_every_main_update_has_a_stable_distinct_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _source_fixture(Path(directory))
            self.git(root, "tag", "v0.1.0")
            first = self.commit_file(root, "README.md", "small documentation fix\n")
            self.assertEqual(native_release_version(root, first), "0.1.1")
            second = self.commit_file(root, "ci-note.txt", "CI-only fix\n")
            self.assertEqual(native_release_version(root, second), "0.1.2")
            # Publishing another commit does not change an already assigned version.
            self.git(root, "tag", "v0.1.1", first)
            self.assertEqual(native_release_version(root, second), "0.1.2")
            self.assertEqual(native_release_version(root, first), "0.1.1")
            self.assertEqual(self.git(root, "status", "--porcelain"), "")

    def test_new_cargo_baseline_works_before_its_first_release_tag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _source_fixture(Path(directory))
            self.git(root, "tag", "v0.1.0")
            manifest = "tools/runtime/dispatch/agent-canon/Cargo.toml"
            content = (
                (root / manifest)
                .read_text()
                .replace('version = "0.1.0"', 'version = "0.2.0"')
            )
            first = self.commit_file(root, manifest, content)
            self.assertEqual(native_release_version(root, first), "0.2.0")
            second = self.commit_file(root, "README.md", "next small change\n")
            self.assertEqual(native_release_version(root, second), "0.2.1")
            self.git(root, "tag", "v0.2.0", first)
            self.assertEqual(native_release_version(root, second), "0.2.1")

    def test_unmerged_topic_cannot_consume_a_main_release_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _source_fixture(Path(directory))
            self.git(root, "tag", "v0.1.0")
            self.git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
            self.git(root, "switch", "-qc", "unmerged")
            branch = self.commit_file(root, "README.md", "unmerged small change\n")
            self.assertEqual(native_release_version(root, branch), "0.1.1")
            with self.assertRaisesRegex(NativeReleaseError, "first-parent history"):
                require_mainline_source(root, branch)

    def test_topic_commits_count_as_one_main_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _source_fixture(Path(directory))
            main = self.git(root, "branch", "--show-current")
            self.git(root, "tag", "v0.1.0")
            self.git(root, "switch", "-qc", "topic")
            self.commit_file(root, "first.txt", "one\n")
            self.commit_file(root, "second.txt", "two\n")
            self.git(root, "switch", "-q", main)
            self.git(root, "merge", "--no-ff", "-qm", "merge small fix", "topic")
            self.assertEqual(native_release_version(root, "HEAD"), "0.1.1")


class NativeArtifactSelectionTest(unittest.TestCase):
    def test_latest_retained_attempt_is_selected_per_target(self) -> None:
        rows = [
            {"name": "agent-canon-native-alpha-attempt-1", "id": 1, "expired": False},
            {"name": "agent-canon-native-alpha-attempt-10", "id": 10, "expired": False},
            {"name": "agent-canon-native-beta-attempt-1", "id": 20, "expired": False},
            {"name": "agent-canon-native-beta-attempt-2", "id": 21, "expired": True},
            {"name": "native-cli-checks-alpha-attempt-11", "id": 30, "expired": False},
        ]
        result = select_native_artifacts(rows, ["alpha", "beta"])
        self.assertEqual([row["artifact_id"] for row in result], [10, 20])
        self.assertEqual([row["attempt"] for row in result], [10, 1])

    def test_missing_target_artifacts_fail(self) -> None:
        with self.assertRaisesRegex(NativeReleaseError, "missing or expired"):
            select_native_artifacts([], ["alpha"])


if __name__ == "__main__":
    unittest.main()
