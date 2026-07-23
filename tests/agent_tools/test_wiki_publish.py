# @dependency-start
# contract test
# responsibility Tests the AgentCanon wiki publication deterministic gate and binding tool.
# upstream implementation ../../tools/agent_tools/wiki_publish.py implements the gate tool.
# downstream design ../../agents/skills/wiki-publication.md defines the workflow contract.
# @dependency-end

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from tools.agent_tools import wiki_publish


class FakeRunner:
    """Minimal command runner used by deterministic wiki publish tests."""

    def __init__(self) -> None:
        self.outputs: dict[tuple[str, ...], wiki_publish.CommandResult] = {}
        self.calls: list[tuple[tuple[str, ...], Path]] = []

    def add(
        self,
        command: list[str],
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.outputs[tuple(command)] = wiki_publish.CommandResult(
            args=tuple(command),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def __call__(self, command: list[str] | tuple[str, ...], cwd: Path) -> wiki_publish.CommandResult:
        key = tuple(command)
        self.calls.append((key, cwd))
        if key in self.outputs:
            return self.outputs[key]

        # formatter and local non-network commands are accepted by default.
        if key[:3] == ("tools/bin/agent-canon", "docs", "format"):
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="", stderr="")
        if key[:1] == ("git",) and key[1] in {"config", "add", "commit", "push", "status", "clone", "ls-remote"}:
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="", stderr="")
        if key[:1] == ("git",) and key[1:3] == ("branch", "--show-current"):
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="main", stderr="")
        if key[:1] == ("git",) and key[1:3] == ("rev-parse", "HEAD"):
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="b" * 40, stderr="")

        raise wiki_publish.UserVisibleFailure(
            message=f"unexpected command: {' '.join(command)}",
            next_action="register_a_matching_fake_output",
        )


def build_args(**extra: object) -> argparse.Namespace:
    base = {
        "root": ".",
        "repo": "iwashita-nozomu/agent-canon",
        "source_branch": "main",
        "source_page": Path("source.md"),
        "page_name": "Home.md",
        "writer": "alice",
        "reviewer": "bob",
        "summary_out": None,
    }
    base.update(extra)
    return argparse.Namespace(**base)


class WikiPublishTests(unittest.TestCase):
    """Tests for wiki publish gates and readback determinism."""

    def test_default_branch_unavailable_is_typed_failure(self) -> None:
        """Missing remote symref HEAD should produce a typed default-branch failure."""
        runner = FakeRunner()
        runner.add(["git", "rev-parse", "main"], stdout="a" * 40)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            returncode=1,
        )
        runner.add(["git", "ls-tree", "-z", "a" * 40, "--", "source.md"], stdout="100644 blob " + "c" * 40 + "\tsource.md\x00")
        runner.add(
            ["git", "show", "a" * 40 + ":source.md"],
            stdout="# Source\n\n"
            + "<!-- AGENT_CANON_WIKI_SOURCE_COMMIT="
            + "b" * 40
            + "-->\n",
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "source.md").write_text("# Source\n", encoding="utf-8")

            with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
                wiki_publish.publish_to_wiki(build_args(root=source_root), runner=runner)

        self.assertEqual(exc.exception.next_action, "default_branch_unavailable")

    def test_wiki_publish_rejects_writer_reviewer_collision(self) -> None:
        """Writer and reviewer must remain independent."""
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "source.md").write_text("# Source\n", encoding="utf-8")

            with self.assertRaises(wiki_publish.UserVisibleFailure):
                wiki_publish.publish_to_wiki(
                    build_args(root=source_root, writer="same", reviewer="same"),
                    runner=runner,
                )

    def test_publish_reads_source_from_exact_commit_blob(self) -> None:
        """Published bytes must come from the exact source commit tree."""
        runner = FakeRunner()
        source_commit = "a" * 40
        sidecar_head = "b" * 40
        source_path = Path("source.md")

        runner.add(["git", "rev-parse", "main"], stdout=source_commit)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(
            ["git", "ls-tree", "-z", source_commit, "--", str(source_path)],
            stdout=f"100644 blob {'c'*40}\t{source_path}\x00",
        )
        runner.add(["git", "show", f"{source_commit}:{source_path}"], stdout="# Source @ {source_commit[:5]}\n")
        runner.add(
            [
                "git",
                "ls-remote",
                "git@github.com:iwashita-nozomu/agent-canon.wiki.git",
                "refs/heads/main",
            ],
            stdout=f"{sidecar_head}\trefs/heads/main\n",
        )
        runner.add(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "main",
                "git@github.com:iwashita-nozomu/agent-canon.wiki.git",
                "",
            ],
            returncode=0,
        )
        runner.add(["git", "status", "--porcelain"], stdout="M\tHome.md")
        runner.add(["git", "rev-parse", "HEAD"], stdout=sidecar_head)

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            source_root.joinpath("source.md").write_text("# Working tree content\n", encoding="utf-8")

            summary = wiki_publish.publish_to_wiki(
                build_args(root=source_root, source_page=source_path),
                runner=runner,
            )

        self.assertEqual(summary["state"], "PUBLISHED")
        self.assertIn(("git", "show", f"{source_commit}:{source_path}"), [cmd for cmd, _ in runner.calls])
        self.assertEqual(summary["source_commit"], source_commit)
        self.assertEqual(summary["local_head"], sidecar_head)
        self.assertEqual(summary["remote_head"], sidecar_head)

    def test_publish_source_path_missing_in_commit_fails_typed(self) -> None:
        """Absent source path in commit tree is rejected with typed source path failure."""
        runner = FakeRunner()
        runner.add(["git", "rev-parse", "main"], stdout="a" * 40)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(["git", "ls-tree", "-z", "a" * 40, "--", "source.md"], stdout="")

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            source_root.joinpath("source.md").write_text("# Source\n", encoding="utf-8")

            with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
                wiki_publish.publish_to_wiki(
                    build_args(root=source_root, source_page=Path("source.md")),
                    runner=runner,
                )

        self.assertEqual(exc.exception.next_action, "source_path_missing_or_not_blob")

    def test_publish_source_path_non_blob_is_rejected(self) -> None:
        """Directory-like tree entries are rejected with the source-path failure."""
        runner = FakeRunner()
        runner.add(["git", "rev-parse", "main"], stdout="a" * 40)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(
            ["git", "ls-tree", "-z", "a" * 40, "--", "source.md"],
            stdout=f"040000 tree {'d'*40}\tsource.md\x00",
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            source_root.joinpath("source.md").write_text("# Source\n", encoding="utf-8")

            with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
                wiki_publish.publish_to_wiki(
                    build_args(root=source_root, source_page=Path("source.md")),
                    runner=runner,
                )

        self.assertEqual(exc.exception.next_action, "source_path_missing_or_not_blob")

    def test_existing_marker_mismatch_is_rejected(self) -> None:
        """Wrong source marker in target wiki page blocks publication with a typed action."""
        runner = FakeRunner()
        runner.add(["git", "rev-parse", "main"], stdout="a" * 40)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(
            ["git", "ls-tree", "-z", "a" * 40, "--", "source.md"],
            stdout="100644 blob " + "c" * 40 + "\tsource.md\x00",
        )
        runner.add(
            ["git", "show", "a" * 40 + ":source.md"],
            stdout="# Source\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=" + "b" * 40 + "-->\n",
        )
        runner.add(
            [
                "git",
                "ls-remote",
                "git@github.com:iwashita-nozomu/agent-canon.wiki.git",
                "refs/heads/main",
            ],
            stdout="b" * 40 + "\trefs/heads/main\n",
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "source.md").write_text("# Working tree source\n", encoding="utf-8")
            with self.assertRaises(wiki_publish.UserVisibleFailure):
                wiki_publish.publish_to_wiki(
                    build_args(root=source_root, source_page=Path("source.md")),
                    runner=runner,
                )


if __name__ == "__main__":
    unittest.main()
