# @dependency-start
# contract test
# responsibility Tests the canonical experiment identity codec and path grammar.
# upstream implementation ../../tools/experiments/experiment_identity.py canonical owner
# @dependency-end

"""Tests for canonical experiment identity validation and serialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.experiments.experiment_identity import (
    DuplicateJSONKeyError,
    ExperimentIdentity,
    ExperimentIdentityError,
    contained_path,
    identity_from_raw_relative_path,
    load_json_text,
    raw_relative_path,
    report_relative_path,
    result_relative_path,
    validate_segment,
)


def test_identity_round_trip_is_nested_v2_wire() -> None:
    """Round-trip the complete tuple through the nested v2 wire form."""
    identity = ExperimentIdentity("topic.v1", "smoke.v2", "run.3")
    payload = identity.to_dict()
    assert payload == {
        "identity": {
            "schema": "agentcanon.experiment-run-identity/v2",
            "topic": "topic.v1",
            "variant": "smoke.v2",
            "run_name": "run.3",
        }
    }
    assert ExperimentIdentity.from_dict(payload) == identity
    assert result_relative_path(identity) == Path("experiments/topic.v1/result/run.3")
    assert raw_relative_path(identity) == Path("experiments/topic.v1/result/run.3/raw")
    assert (
        identity_from_raw_relative_path(raw_relative_path(identity), identity.variant)
        == identity
    )
    assert report_relative_path(identity) == Path(
        "experiments/topic.v1/report/run.3.md"
    )


@pytest.mark.parametrize("value", ["", ".", "..", "a/b", "a\\b", "a b", "a\x00b", "é"])
def test_identity_segment_rejects_unsafe_values(value: str) -> None:
    """Reject path separators, traversal names, whitespace, and unsafe text."""
    with pytest.raises(ExperimentIdentityError):
        validate_segment(value)


def test_identity_rejects_normalization_change() -> None:
    """Reject a segment whose Unicode normalization would change its bytes."""
    with pytest.raises(ExperimentIdentityError):
        validate_segment("Ａ")


def test_identity_from_dict_rejects_top_level_duplicates() -> None:
    """Reject identity fields repeated outside the canonical nested object."""
    payload = ExperimentIdentity("topic", "variant", "run").to_dict()
    payload["topic"] = "topic"
    with pytest.raises(ExperimentIdentityError, match="duplicated"):
        ExperimentIdentity.from_dict(payload)


@pytest.mark.parametrize(
    "payload",
    [
        '{"identity": {"schema": "agentcanon.experiment-run-identity/v2", "schema": "agentcanon.experiment-run-identity/v2", "topic": "topic", "variant": "variant", "run_name": "run"}}',
        '{"identity": {"schema": "agentcanon.experiment-run-identity/v2", "topic": "topic", "variant": "variant", "run_name": "run"}, "identity": {"schema": "agentcanon.experiment-run-identity/v2", "topic": "topic", "variant": "variant", "run_name": "run"}}',
    ],
)
def test_strict_json_decoder_rejects_nested_and_outer_duplicate_keys(
    payload: str,
) -> None:
    """Reject duplicate keys before any identity mapping can consume them."""
    with pytest.raises(DuplicateJSONKeyError):
        load_json_text(payload)


@pytest.mark.parametrize(
    "path",
    (
        Path("experiments/demo/result/run-a"),
        Path("experiments/demo/result/run-a/summary"),
        Path("experiments/demo/result/run-a/raw/extra"),
        Path("../experiments/demo/result/run-a/raw"),
    ),
)
def test_raw_path_inverse_rejects_noncanonical_shapes(path: Path) -> None:
    """Only the complete canonical raw path is invertible."""
    with pytest.raises(ExperimentIdentityError):
        identity_from_raw_relative_path(path, "formal")


def test_contained_path_rejects_escape(tmp_path: Path) -> None:
    """Reject paths that resolve outside the repository boundary."""
    with pytest.raises(ExperimentIdentityError):
        contained_path(tmp_path, tmp_path / ".." / "outside")
