"""Public native status CLI; stateful GitHub failure oracles are Rust tests."""

import os
import subprocess


def test_status_cli_help_exposes_evidence_and_facts_inputs() -> None:
    result = subprocess.run(
        [os.environ["AGENT_CANON_CLI"], "github-status-lifecycle", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for option in (
        "--repo",
        "--issue",
        "--facts-json",
        "--comment-body-file",
        "--comment-id",
    ):
        assert option in result.stdout


def test_unknown_status_option_never_reaches_github() -> None:
    result = subprocess.run(
        [os.environ["AGENT_CANON_CLI"], "github-status-lifecycle", "--unknown"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr
