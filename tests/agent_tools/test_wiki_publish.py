from __future__ import annotations

"""Tests for the AgentCanon wiki publication deterministic gate and readback semantics."""

# @dependency-start
# contract test
# responsibility Tests the AgentCanon wiki page-set publication gates and workflow transitions.
# upstream implementation ../../tools/agent_tools/wiki_publish.py owns the canonical wiki publish tool.
# upstream design ../../agents/skills/wiki-publication.md owns the workflow contract.
# downstream implementation ../../documents/tools/wiki_publish.md documents the command semantics.
# @dependency-end

import argparse
import hashlib
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

        if key[:1] == ("git",) and key[1] in {
            "config",
            "add",
            "commit",
            "push",
            "status",
            "branch",
            "rev-parse",
            "ls-remote",
            "clone",
        }:
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="", stderr="")

        if key[:3] == ("tools/bin/agent-canon", "docs", "format"):
            return wiki_publish.CommandResult(args=key, returncode=0, stdout="", stderr="")

        raise wiki_publish.UserVisibleFailure(
            message=f"unexpected command: {' '.join(command)}",
            next_action="register_a_matching_fake_output",
        )


def build_args(**extra: object) -> argparse.Namespace:
    base = {
        "wiki_root": Path("/tmp/wiki"),
        "source_root": Path("."),
        "source_commit": "a" * 40,
        "repo": "iwashita-nozomu/agent-canon",
        "writer": "alice",
        "reviewer": "bob",
        "expected_page_set_digest": None,
        "summary_out": None,
    }
    base.update(extra)
    return argparse.Namespace(**base)


def compute_digest(page_root: Path, source_commit: str) -> str:
    hasher = hashlib.sha256()
    for path in sorted(p for p in page_root.iterdir() if p.is_file() and p.suffix == ".md"):
        text = path.read_text(encoding="utf-8")
        if f"<!-- AGENT_CANON_WIKI_SOURCE_COMMIT={source_commit}-->" not in text:
            raise AssertionError("missing marker in fixture")
        rel = path.name
        rel_data = f"{rel}\0{len(text.encode('utf-8'))}\0".encode("utf-8")
        hasher.update(rel_data)
        hasher.update(text.encode("utf-8"))
    return hasher.hexdigest()


class WikiPublishTests(unittest.TestCase):
    """Tests for wiki publish gates and page-set publication determinism."""

    def test_default_branch_unavailable_is_typed_failure(self) -> None:
        runner = FakeRunner()
        runner.add(["git", "cat-file", "-t", "a" * 40], returncode=1, stderr="not found")

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
                wiki_publish.publish_to_wiki(
                    build_args(source_root=source_root),
                    runner=runner,
                )
        self.assertEqual(exc.exception.next_action, "source_commit_not_found_in_source_repo")

    def test_publish_rejects_noncanonical_source_commit_in_source_root(self) -> None:
        runner = FakeRunner()
        runner.add(["git", "cat-file", "-t", "a" * 40], stdout="tree")

        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
                wiki_publish.publish_to_wiki(
                    build_args(source_root=source_root),
                    runner=runner,
                )
        self.assertEqual(exc.exception.next_action, "source_commit_not_found_in_source_repo")

    def test_required_top_level_wiki_pages_are_enforced(self) -> None:
        runner = FakeRunner()
        source_root = Path(tempfile.mkdtemp())
        wiki_root = source_root / "wiki"
        wiki_root.mkdir()
        runner.add(["git", "cat-file", "-t", "a" * 40], stdout="commit")
        runner.add(
            [
                "git",
                "ls-remote",
                "--symref",
                "https://github.com/iwashita-nozomu/agent-canon.wiki.git",
                "HEAD",
            ],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(["git", "rev-parse", "--is-inside-work-tree"], stdout="true")
        runner.add(["git", "branch", "--show-current"], stdout="main")

        (wiki_root / "Home.md").write_text("# Home\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=a" * 40 + "-->\n", encoding="utf-8")
        (wiki_root / "Other.md").write_text("# Other\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=a" * 40 + "-->\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp_output:
            with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
                wiki_publish.publish_to_wiki(
                    build_args(source_root=source_root, wiki_root=wiki_root, summary_out=Path(tmp_output) / "summary.json"),
                    runner=runner,
                )
        self.assertEqual(exc.exception.next_action, "add_required_wiki_pages")

    def test_prepare_without_expected_digest_outputs_page_set_digest(self) -> None:
        runner = FakeRunner()
        source_root = Path(tempfile.mkdtemp())
        wiki_root = source_root / "wiki"
        wiki_root.mkdir()
        source_page = "# Home\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=" + "a" * 40 + "-->\n"
        for name in ("Home.md", "_Sidebar.md", "_Footer.md"):
            (wiki_root / name).write_text(source_page, encoding="utf-8")
        runner.add(["git", "cat-file", "-t", "a" * 40], stdout="commit")
        runner.add(
            [
                "git",
                "ls-remote",
                "--symref",
                "https://github.com/iwashita-nozomu/agent-canon.wiki.git",
                "HEAD",
            ],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(["git", "rev-parse", "--is-inside-work-tree"], stdout="true")
        runner.add(["git", "branch", "--show-current"], stdout="main")

        summary = wiki_publish.publish_to_wiki(
            build_args(source_root=source_root, wiki_root=wiki_root),
            runner=runner,
        )

        self.assertEqual(summary["state"], "PREPARE_OK")
        expected = compute_digest(wiki_root, "a" * 40)
        self.assertEqual(summary["page_set_digest"], expected)

    def test_publish_rejects_digest_mismatch_after_reviewer_step(self) -> None:
        runner = FakeRunner()
        source_root = Path(tempfile.mkdtemp())
        wiki_root = source_root / "wiki"
        wiki_root.mkdir()
        source_page = "# Home\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=" + "a" * 40 + "-->\n"
        for name in ("Home.md", "_Sidebar.md", "_Footer.md"):
            (wiki_root / name).write_text(source_page, encoding="utf-8")
        runner.add(["git", "cat-file", "-t", "a" * 40], stdout="commit")
        runner.add(
            [
                "git",
                "ls-remote",
                "--symref",
                "https://github.com/iwashita-nozomu/agent-canon.wiki.git",
                "HEAD",
            ],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(["git", "rev-parse", "--is-inside-work-tree"], stdout="true")
        runner.add(["git", "branch", "--show-current"], stdout="main")

        with self.assertRaises(wiki_publish.UserVisibleFailure) as exc:
            wiki_publish.publish_to_wiki(
                build_args(
                    source_root=source_root,
                    wiki_root=wiki_root,
                    expected_page_set_digest="bad" + "1" * 63,
                ),
                runner=runner,
            )

        self.assertEqual(exc.exception.next_action, "page_set_digest_mismatch")

    def test_publish_requires_exact_default_branch_push_and_readback(self) -> None:
        runner = FakeRunner()
        source_root = Path(tempfile.mkdtemp())
        wiki_root = source_root / "wiki"
        wiki_root.mkdir()
        source_page = "# Home\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=" + "a" * 40 + "-->\n"
        for name in ("Home.md", "_Sidebar.md", "_Footer.md"):
            (wiki_root / name).write_text(source_page, encoding="utf-8")

        expected = compute_digest(wiki_root, "a" * 40)
        sidecar_head = "c" * 40

        runner.add(["git", "cat-file", "-t", "a" * 40], stdout="commit")
        runner.add(
            [
                "git",
                "ls-remote",
                "--symref",
                "https://github.com/iwashita-nozomu/agent-canon.wiki.git",
                "HEAD",
            ],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(["git", "rev-parse", "--is-inside-work-tree"], stdout="true")
        runner.add(["git", "branch", "--show-current"], stdout="main")
        runner.add(["git", "rev-parse", "HEAD"], stdout=sidecar_head)
        runner.add(["git", "ls-remote", "https://github.com/iwashita-nozomu/agent-canon.wiki.git", "refs/heads/main"], stdout=f"{sidecar_head}\trefs/heads/main\n")

        summary = wiki_publish.publish_to_wiki(
            build_args(
                source_root=source_root,
                wiki_root=wiki_root,
                expected_page_set_digest=expected,
            ),
            runner=runner,
        )

        self.assertEqual(summary["state"], "PUBLISHED")
        self.assertEqual(summary["local_head"], sidecar_head)
        self.assertEqual(summary["remote_head"], sidecar_head)

    def test_prepare_uses_supplied_wiki_root_including_untracked_pages_and_no_clone(self) -> None:
        runner = FakeRunner()
        source_root = Path(tempfile.mkdtemp())
        wiki_root = source_root / "wiki"
        wiki_root.mkdir()

        source_page = "# Untracked\n\n<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=" + "a" * 40 + "-->\n"
        for name in ("Home.md", "_Sidebar.md", "_Footer.md"):
            (wiki_root / name).write_text(source_page, encoding="utf-8")
        (wiki_root / "draft.txt").write_text("not a page\n", encoding="utf-8")

        runner.add(["git", "cat-file", "-t", "a" * 40], stdout="commit")
        runner.add(
            [
                "git",
                "ls-remote",
                "--symref",
                "https://github.com/iwashita-nozomu/agent-canon.wiki.git",
                "HEAD",
            ],
            stdout="ref: refs/heads/main\tHEAD\n",
        )
        runner.add(["git", "rev-parse", "--is-inside-work-tree"], stdout="true")
        runner.add(["git", "branch", "--show-current"], stdout="main")

        summary = wiki_publish.publish_to_wiki(
            build_args(source_root=source_root, wiki_root=wiki_root),
            runner=runner,
        )

        self.assertEqual(summary["state"], "PREPARE_OK")
        self.assertEqual(summary["page_count"], 3)
        self.assertEqual(summary["page_set_digest"], compute_digest(wiki_root, "a" * 40))
        self.assertFalse(any(cmd[:2] == ("git", "clone") for cmd, _ in runner.calls))


if __name__ == "__main__":
    unittest.main()
