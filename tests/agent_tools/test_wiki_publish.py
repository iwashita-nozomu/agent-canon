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
        if key in self.outputs:
            return self.outputs[key]

        # formatter and local non-network commands are accepted by default.
        if key[:3] == ("tools/bin/agent-canon", "docs", "format"):
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="", stderr="")
        if key[:1] == ("git",) and key[1] in {"config", "add", "commit", "push", "status", "clone"}:
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

    def test_blocked_when_wiki_default_branch_missing(self) -> None:
        """Uninitialized sidecar should return the typed REMOTE_UNINITIALIZED state."""
        runner = FakeRunner()
        runner.add(["git", "rev-parse", "main"], stdout="a" * 40)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            returncode=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "source.md").write_text("# Source\n", encoding="utf-8")
            args = build_args(root=source_root, source_page=Path("source.md"))
            summary = wiki_publish.publish_to_wiki(args, runner=runner)

        self.assertEqual(summary["state"], wiki_publish.REMOTE_UNINITIALIZED)
        self.assertEqual(summary["next_action"], "initialize_default_wiki_page_and_retry")

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

    def test_publish_binds_source_commit_marker_and_readback(self) -> None:
        """A successful publish verifies source commit marker and exact remote readback."""
        runner = FakeRunner()
        source_commit = "a" * 40
        sidecar_head = "b" * 40
        runner.add(["git", "rev-parse", "main"], stdout=source_commit)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
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
            source_page = source_root / "source.md"
            source_page.write_text("# Source\n", encoding="utf-8")

            summary = wiki_publish.publish_to_wiki(
                build_args(root=source_root, source_page=Path("source.md")),
                runner=runner,
            )

        self.assertEqual(summary["state"], "PUBLISHED")
        self.assertEqual(summary["local_head"], sidecar_head)
        self.assertEqual(summary["remote_head"], sidecar_head)

    def test_existing_marker_mismatch_is_rejected(self) -> None:
        """Wrong source marker in source page should block publication with a typed action."""
        runner = FakeRunner()
        runner.add(["git", "rev-parse", "main"], stdout="a" * 40)
        runner.add(
            ["git", "ls-remote", "--symref", "git@github.com:iwashita-nozomu/agent-canon.wiki.git", "HEAD"],
            stdout="ref: refs/heads/main\tHEAD\n",
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            source_page = source_root / "source.md"
            source_page.write_text(
                "# Source\n\n"
                + "<!-- AGENT_CANON_WIKI_SOURCE_COMMIT="
                + "b" * 40
                + "-->\n",
                encoding="utf-8",
            )
            with self.assertRaises(wiki_publish.UserVisibleFailure):
                wiki_publish.publish_to_wiki(
                    build_args(root=source_root, source_page=Path("source.md")),
                    runner=runner,
                )


if __name__ == "__main__":
    unittest.main()
