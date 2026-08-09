"""Tests for local issue and GitHub sync planning."""

# @dependency-start
# contract test
# responsibility Tests local issue validation and sync planning.
# upstream implementation ../../tools/agent_tools/issue_sync.py validates issue files
# upstream design ../../issues/README.md durable issue convention
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "issue_sync.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import issue_sync  # noqa: E402


class IssueSyncTest(unittest.TestCase):
    """Exercise local issue validation and sync planning."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the issue sync checker."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def run_checker_with_env(
        self,
        root: Path,
        env: dict[str, str],
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run the issue sync checker with an explicit environment."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_missing_required_field_fails(self) -> None:
        """Local issue files must keep required fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue = self.write_issue(root, "open", "AC-20260517-test-issue")
            issue.write_text(
                issue.read_text(encoding="utf-8").replace("edit_scope:", "scope:"),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing:edit_scope", result.stdout)

    def test_require_github_link_fails_when_missing(self) -> None:
        """Optional GitHub mirror links can be made mandatory by flag."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(root, "open", "AC-20260517-test-issue")

            result = self.run_checker(root, "--require-github-link")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing-github_issue", result.stdout)

    def test_sync_plan_lists_unlinked_issue(self) -> None:
        """The checker prints a deterministic gh command plan for unlinked issues."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(root, "open", "AC-20260517-test-issue")

            result = self.run_checker(root, "--repo", "owner/repo")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_PLAN=AC-20260517-test-issue:gh issue create", result.stdout)
            self.assertIn("--repo owner/repo", result.stdout)

    def test_github_check_passes_for_matching_link(self) -> None:
        """Read-only GitHub checks should pass when the mirror matches local state."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue = self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_fake_gh(
                root,
                title="Test Issue",
                body=issue.read_text(encoding="utf-8"),
                state="OPEN",
            )

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_GITHUB_CHECKED=1", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=0", result.stdout)

    def test_github_check_fails_on_state_drift(self) -> None:
        """Read-only GitHub checks should fail on linked mirror drift."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue = self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_fake_gh(
                root,
                title="Test Issue",
                body=issue.read_text(encoding="utf-8"),
                state="CLOSED",
            )

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("state-drift:expected=OPEN:actual=CLOSED", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=1", result.stdout)

    def test_github_check_fails_on_body_drift(self) -> None:
        """Read-only GitHub checks should fail when the mirror body is stale."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_fake_gh(root, title="Test Issue", body="stale body", state="OPEN")

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("body-drift", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=1", result.stdout)

    def test_github_checks_fail_for_unresolved_github_issue_states(self) -> None:
        """Read-only checks should fail when link is missing, pending, or not-created."""
        for state, marker in (
            ("empty", ""),
            ("pending", "pending"),
            ("not-created", "not-created"),
        ):
            with self.subTest(state=state):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    self.write_issue(root, "open", f"AC-20260517-test-{state}", github_issue=marker)
                    bin_dir = self.write_fake_gh_apply(root)
                    result = self.run_checker_with_env(
                        root,
                        self.env_with_path(bin_dir),
                        "--repo",
                        "owner/repo",
                        "--github-check",
                    )

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    marker_label = marker or "empty"
                    self.assertIn(f"unresolved-github_issue:{marker_label}", result.stdout)

    def test_summary_and_plan_count_resolve_github_issue_markers(self) -> None:
        """Summary and plan should treat empty/pending/not-created as unresolved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(root, "open", "AC-20260517-test-empty")
            self.write_issue(root, "open", "AC-20260517-test-pending", github_issue="pending")
            self.write_issue(root, "open", "AC-20260517-test-not-created", github_issue="not-created")
            self.write_issue(
                root,
                "open",
                "AC-20260517-test-linked",
                github_issue="https://github.com/owner/repo/issues/99",
            )
            summary = root / "summary.md"

            result = self.run_checker(root, "--repo", "owner/repo", "--summary-file", str(summary))
            text = summary.read_text(encoding="utf-8")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("missing_github_links: `3`", text)
            self.assertIn("ISSUE_SYNC_PLAN=AC-20260517-test-empty", result.stdout)
            self.assertIn("ISSUE_SYNC_PLAN=AC-20260517-test-pending", result.stdout)
            self.assertIn("ISSUE_SYNC_PLAN=AC-20260517-test-not-created", result.stdout)
            self.assertNotIn("AC-20260517-test-linked", result.stdout)

    def test_plan_and_apply_reuse_issue_title_with_leading_dependency_comment(self) -> None:
        """Plan and apply must both use the first H1 title even with leading comments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue_id = "AC-20260517-test-title-consistency"
            issue = root / "issues" / "open" / f"{issue_id}.md"
            issue.parent.mkdir(parents=True, exist_ok=True)
            issue.write_text(
                "\n".join(
                    [
                        "<!-- @dependency-start -->",
                        "# Dependency heading",
                        "",
                        "issue_id: AC-20260517-test-title-consistency",
                        "status: open",
                        "source: user",
                        "severity: S1",
                        "evidence: fixture",
                        "affected_surfaces: tools/example.py",
                        "edit_scope: tools/example.py",
                        "required_action: Keep title extraction consistent.",
                        "close_condition: title path is consistent.",
                        "",
                        "Body text for title consistency regression.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            expected_title = "Dependency heading"

            plan_result = self.run_checker(root, "--repo", "owner/repo")
            self.assertEqual(plan_result.returncode, 0, plan_result.stdout + plan_result.stderr)
            self.assertIn(f'--title {json.dumps(expected_title)}', plan_result.stdout)

            bin_dir = self.write_fake_gh_apply(root)
            apply_result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--apply",
            )
            self.assertEqual(apply_result.returncode, 0, apply_result.stdout + apply_result.stderr)
            self.assertIn(f"ISSUE_SYNC_CREATED=1", apply_result.stdout)
            state = json.loads((bin_dir / "gh_state.json").read_text(encoding="utf-8"))
            issue_number = next(iter(state["issues"]))
            self.assertEqual(state["issues"][issue_number]["title"], expected_title)

    def test_issue_record_github_issue_falls_back_to_fields_when_no_values(self) -> None:
        """Compatibility: direct IssueRecord construction reads github_issue from fields."""
        issue = issue_sync.IssueRecord(
            path=Path("/tmp/fallback-issue.md"),
            directory_state="open",
            fields={"issue_id": "AC-20260517-test-fallback", "github_issue": "https://github.com/owner/repo/issues/404"},
            body="",
        )

        self.assertEqual(
            issue.github_issue,
            "https://github.com/owner/repo/issues/404",
        )

    def test_apply_canonicalizes_valid_and_marker_github_issue_duplicates(self) -> None:
        """Canonical URL in mixed-field duplicates should be preserved and deduped before apply."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue_id = "AC-20260517-test-duplicate-canonical"
            issue = root / "issues" / "open" / f"{issue_id}.md"
            issue.parent.mkdir(parents=True, exist_ok=True)
            issue.write_text(
                "\n".join(
                    [
                        "# Duplicate GitHub issue references",
                        "",
                        "issue_id: AC-20260517-test-duplicate-canonical",
                        "status: open",
                        "source: user",
                        "severity: S1",
                        "evidence: fixture",
                        "github_issue: pending",
                        "github_issue: https://github.com/owner/repo/issues/42",
                        "affected_surfaces: tools/example.py",
                        "edit_scope: tools/example.py",
                        "required_action: Keep canonical references.",
                        "close_condition: one valid URL survives.",
                        "",
                        "Body text for duplicate reference canonicalization.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            bin_dir = self.write_fake_gh_apply(root)
            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--apply",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_CREATED=0", result.stdout)
            content = issue.read_text(encoding="utf-8")
            self.assertEqual(content.count("github_issue:"), 1)
            self.assertIn("github_issue: https://github.com/owner/repo/issues/42", content)
            state = json.loads((bin_dir / "gh_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["calls"], [])

    def test_require_github_link_fails_for_empty_and_marker_states(self) -> None:
        """Require-link mode should fail for unresolved issue links."""
        for state, marker in (
            ("empty", ""),
            ("pending", "pending"),
            ("not-created", "not-created"),
        ):
            with self.subTest(state=state):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    self.write_issue(root, "open", f"AC-20260517-test-{state}", github_issue=marker)

                    result = self.run_checker(root, "--require-github-link")

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("missing-github_issue", result.stdout)

    def test_apply_replaces_unresolved_links_and_syncs_updated_bodies(self) -> None:
        """Apply should create all unresolved issue links and sync remote bodies."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(root, "open", "AC-20260517-test-empty")
            self.write_issue(root, "open", "AC-20260517-test-pending", github_issue="pending")
            self.write_issue(
                root,
                "open",
                "AC-20260517-test-not-created",
                github_issue="not-created",
            )
            duplicate = self.write_issue(
                root,
                "open",
                "AC-20260517-test-duplicate",
                github_issue="pending",
            )
            duplicate.write_text(
                duplicate.read_text(encoding="utf-8").replace(
                    "github_issue: pending",
                    "github_issue: pending\ngithub_issue: pending",
                ),
                encoding="utf-8",
            )
            bin_dir = self.write_fake_gh_apply(root)

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--apply",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_CREATED=4", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_SYNCED=", result.stdout)
            created_urls: list[str] = []
            for line in result.stdout.splitlines():
                if line.startswith("ISSUE_SYNC_CREATED_ITEM="):
                    created_urls.append(line.split("=", 1)[1].split(":", 1)[1])
            self.assertEqual(len(created_urls), 4)
            for issue_file in (
                root / "issues" / "open" / "AC-20260517-test-empty.md",
                root / "issues" / "open" / "AC-20260517-test-pending.md",
                root / "issues" / "open" / "AC-20260517-test-not-created.md",
                root / "issues" / "open" / "AC-20260517-test-duplicate.md",
            ):
                content = issue_file.read_text(encoding="utf-8")
                self.assertEqual(content.count("github_issue:"), 1)
                self.assertIn("https://github.com/owner/repo/issues/", content)

            state = json.loads((bin_dir / "gh_state.json").read_text(encoding="utf-8"))
            for created_url in created_urls:
                issue_number = created_url.split("/")[-1]
                self.assertIn(issue_number, state["issues"])
                self.assertEqual(state["issues"][issue_number]["body"].count("github_issue:"), 1)
                self.assertIn("github_issue:", state["issues"][issue_number]["body"])
                self.assertIn("https://github.com/owner/repo/issues/", state["issues"][issue_number]["body"])

    def test_apply_syncs_only_created_and_reuses_existing_github_link(self) -> None:
        """Apply should sync only created links and leave stale pre-linked issues untouched."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stale_issue = self.write_issue(
                root,
                "open",
                "AC-20260517-test-stale",
                github_issue="https://github.com/owner/repo/issues/700",
            )
            stale_issue.write_text(
                stale_issue.read_text(encoding="utf-8").replace(
                    "status: open",
                    "status: open\nrequired_action: Keep stale issue untouched.",
                )
                .replace("close_condition: The fixture passes.", "close_condition: Must not sync stale issue."),
                encoding="utf-8",
            )
            self.write_issue(root, "open", "AC-20260517-test-missing")
            bin_dir = self.write_fake_gh_apply(root)
            state_path = bin_dir / "gh_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["issues"]["700"] = {
                "number": 700,
                "title": "Remote stale title",
                "body": "stale remote body",
                "state": "CLOSED",
                "url": "https://github.com/owner/repo/issues/700",
                "repo": "owner/repo",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--apply",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_CREATED=1", result.stdout)
            created = [line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("ISSUE_SYNC_CREATED_ITEM=")]
            self.assertEqual(len(created), 1)
            created_url = created[0].split(":", 1)[1]
            created_number = created_url.split("/")[-1]
            updated_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("issues", updated_state)
            self.assertIn(created_number, updated_state["issues"])
            self.assertIn(
                "github_issue:",
                updated_state["issues"][created_number]["body"],
            )
            self.assertIn(
                created_url,
                updated_state["issues"][created_number]["body"],
            )
            self.assertFalse(
                any(
                    call[1:4] == ["issue", "edit"] and call[3] == "700"
                    for call in updated_state["calls"]
                )
            )
            self.assertFalse(
                any(
                    call[1:4] == ["issue", "close"] and call[3] == "700"
                    or call[1:4] == ["issue", "reopen"] and call[3] == "700"
                    for call in updated_state["calls"]
                )
            )
            self.assertFalse(
                any(
                    call[1:4] == ["issue", "view"] and call[3] == "700"
                    for call in updated_state["calls"]
                )
            )

    def test_github_check_can_treat_auth_failure_as_unavailable(self) -> None:
        """Actions read-only checks should not block when GitHub auth is unavailable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_failing_gh(root, "HTTP 401: Bad credentials (https://api.github.com/graphql)")

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
                "--allow-github-auth-unavailable",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_GITHUB_CHECKED=0", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=0", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_UNAVAILABLE=1", result.stdout)
            self.assertIn("ISSUE_SYNC=pass", result.stdout)

    def test_summary_file_records_issue_mirror_status(self) -> None:
        """The checker can append a readable issue mirror summary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary = root / "summary.md"
            self.write_issue(root, "open", "AC-20260517-test-issue")

            result = self.run_checker(root, "--summary-file", str(summary))
            text = summary.read_text(encoding="utf-8")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("## Issue Mirror Check", text)
            self.assertIn("missing_github_links: `1`", text)

    def test_group_findings_reuses_one_owner_root_cause_fix(self) -> None:
        """Duplicate observations become one issue candidate without fan-out."""
        grouped = issue_sync.group_findings(
            [
                {
                    "owner": "issue_sync",
                    "root_cause": "duplicate warning",
                    "fix": "normalize once",
                    "evidence": "a.log",
                    "path": "tools/a.py",
                },
                {
                    "owner": "issue_sync",
                    "root_cause": "duplicate warning",
                    "fix": "normalize once",
                    "evidence": "b.log",
                    "path": "tools/b.py",
                },
            ]
        )
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["evidence"], ["a.log", "b.log"])
        self.assertEqual(grouped[0]["scope"], "changed")

    def test_compact_problem_evidence_done_issue_form_is_valid(self) -> None:
        """The minimum issue form does not require extended scope fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "issues" / "open" / "AC-20260517-compact.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "\n".join(
                    [
                        "# Compact",
                        "",
                        "issue_id: AC-20260517-compact",
                        "status: open",
                        "source: user",
                        "severity: S2",
                        "problem: warning is duplicated",
                        "evidence: reports/run.log",
                        "done: one owner groups the finding",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_issue(
        self,
        root: Path,
        state: str,
        issue_id: str,
        *,
        github_issue: str = "",
    ) -> Path:
        """Write one local issue file."""
        path = root / "issues" / state / f"{issue_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        status = "resolved" if state == "closed" else "open"
        resolved_by = "resolved_by: fixture\n" if state == "closed" else ""
        github_line = f"github_issue: {github_issue}" if github_issue else ""
        path.write_text(
            "\n".join(
                [
                    "# Test Issue",
                    "",
                    f"issue_id: {issue_id}",
                    f"status: {status}",
                    "source: user",
                    "severity: S1",
                    "evidence: fixture",
                    github_line,
                    "affected_surfaces: tools/example.py",
                    "edit_scope: tools/example.py",
                    "required_action: Fix the fixture.",
                    "close_condition: The fixture passes.",
                    resolved_by.rstrip(),
                    "",
                ]
            ).replace("\n\n\n", "\n\n"),
            encoding="utf-8",
        )
        return path

    def write_fake_gh(self, root: Path, *, title: str, body: str, state: str) -> Path:
        """Write a fake gh executable for deterministic GitHub check tests."""
        bin_dir = root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import sys",
                    "if sys.argv[1:3] == ['issue', 'view']:",
                    "    print(json.dumps("
                    f"{{'number': 7, 'title': {title!r}, 'body': {body!r}, "
                    f"'state': {state!r}, 'url': 'https://github.com/owner/repo/issues/7'}}"
                    "))",
                    "    raise SystemExit(0)",
                    "raise SystemExit('unexpected gh command: ' + ' '.join(sys.argv[1:]))",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return bin_dir

    def write_fake_gh_apply(self, root: Path) -> Path:
        """Write a fake gh executable for deterministic apply-and-sync tests."""
        bin_dir = root / "bin"
        bin_dir.mkdir()
        state_path = bin_dir / "gh_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "next": 101,
                    "issues": {},
                    "calls": [],
                    "edits": [],
                }
            ),
            encoding="utf-8",
        )
        gh = bin_dir / "gh"
        gh.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import sys",
                    "from pathlib import Path",
                    "",
                    "STATE_FILE = Path(__file__).with_name('gh_state.json')",
                    "REPO = 'owner/repo'",
                    "",
                    "def load_state():",
                    "    data = json.loads(STATE_FILE.read_text(encoding='utf-8'))",
                    "    data.setdefault('issues', {})",
                    "    data.setdefault('calls', [])",
                    "    data.setdefault('edits', [])",
                    "    data['next'] = int(data.get('next', 101))",
                    "    return data",
                    "",
                    "def save_state(state):",
                    "    STATE_FILE.write_text(json.dumps(state), encoding='utf-8')",
                    "",
                    "def log_call(state, argv):",
                    "    state['calls'].append(argv)",
                    "",
                    "def issue_number(argv):",
                    "    return argv[3] if len(argv) >= 4 else ''",
                    "",
                    "def handle_create(state, argv):",
                    "    title = argv[5]",
                    "    body = argv[7]",
                    "    num = str(state['next'])",
                    "    state['next'] = state['next'] + 1",
                    "    state['issues'][num] = {",
                    "        'number': int(num),",
                    "        'title': title,",
                    "        'body': body,",
                    "        'state': 'OPEN',",
                    "        'url': f'https://github.com/{REPO}/issues/{num}',",
                    "        'repo': REPO,",
                    "    }",
                    "    log_call(state, argv)",
                    "    save_state(state)",
                    "    print(state['issues'][num]['url'])",
                    "    raise SystemExit(0)",
                    "",
                    "def handle_view(state, argv):",
                    "    number = issue_number(argv)",
                    "    issue = state['issues'].get(number)",
                    "    if not issue:",
                    "        print('NOT_FOUND', file=sys.stderr)",
                    "        raise SystemExit(1)",
                    "    print(json.dumps(issue))",
                    "    log_call(state, argv)",
                    "    save_state(state)",
                    "    raise SystemExit(0)",
                    "",
                    "def handle_edit(state, argv):",
                    "    number = argv[3]",
                    "    body_file = Path(argv[argv.index('--body-file') + 1])",
                    "    if number not in state['issues']:",
                    "        print('NOT_FOUND', file=sys.stderr)",
                    "        raise SystemExit(1)",
                    "    state['issues'][number]['body'] = body_file.read_text(encoding='utf-8')",
                    "    if '--title' in argv:",
                    "        state['issues'][number]['title'] = argv[argv.index('--title') + 1]",
                    "    state['edits'].append({'number': number, 'body_file': str(body_file)})",
                    "    log_call(state, argv)",
                    "    save_state(state)",
                    "    raise SystemExit(0)",
                    "",
                    "def handle_state_change(state, argv):",
                    "    number = argv[3]",
                    "    if number in state['issues']:",
                    "        state['issues'][number]['state'] = 'CLOSED' if argv[2] == 'close' else 'OPEN'",
                    "    log_call(state, argv)",
                    "    save_state(state)",
                    "    raise SystemExit(0)",
                    "",
                    "def main():",
                    "    state = load_state()",
                    "    argv = ['gh'] + sys.argv[1:]",
                    "    if len(argv) < 4:",
                    "        print('unexpected gh command: ' + ' '.join(sys.argv[1:]), file=sys.stderr)",
                    "        raise SystemExit(1)",
                    "    if argv[1:3] == ['issue', 'create']:",
                    "        return handle_create(state, argv)",
                    "    if argv[1:3] == ['issue', 'view']:",
                    "        return handle_view(state, argv)",
                    "    if argv[1:3] == ['issue', 'edit']:",
                    "        return handle_edit(state, argv)",
                    "    if argv[2] in ('close', 'reopen'):",
                    "        return handle_state_change(state, argv)",
                    "    print('unexpected gh command: ' + ' '.join(sys.argv[1:]), file=sys.stderr)",
                    "    log_call(state, argv)",
                    "    save_state(state)",
                    "    raise SystemExit(1)",
                    "",
                    "if __name__ == '__main__':",
                    "    main()",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return bin_dir

    def write_failing_gh(self, root: Path, message: str) -> Path:
        """Write a fake gh executable that fails with one message."""
        bin_dir = root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import sys",
                    f"print({message!r}, file=sys.stderr)",
                    "raise SystemExit(1)",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return bin_dir

    def env_with_path(self, bin_dir: Path) -> dict[str, str]:
        """Return an environment that resolves the fake gh first."""
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        return env


if __name__ == "__main__":
    unittest.main()
