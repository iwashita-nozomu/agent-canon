"""Native wiki CLI qualification; page-set and Git oracles live in Rust."""

import os
import subprocess


def test_wiki_help_exposes_existing_required_input_contract() -> None:
    result = subprocess.run(
        [os.environ["AGENT_CANON_CLI"], "wiki-publish", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for option in (
        "--wiki-root",
        "--source-root",
        "--source-commit",
        "--writer",
        "--reviewer",
        "--expected-page-set-digest",
    ):
        assert option in result.stdout


def test_missing_publication_inputs_fail_before_provider_execution() -> None:
    result = subprocess.run(
        [os.environ["AGENT_CANON_CLI"], "wiki-publish"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--wiki-root" in result.stderr
