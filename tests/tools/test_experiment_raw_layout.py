# @dependency-start
# contract test
# responsibility Tests canonical result/raw path derivation and managed raw-directory handoff.
# upstream implementation ../../tools/experiments/experiment_identity.py owns identity paths.
# upstream implementation ../../tools/experiments/run_managed_experiment.py owns managed reservation and child environment.
# @dependency-end

"""Focused tests for the split experiment result/raw layout."""

from __future__ import annotations

from pathlib import Path

from tools.experiments.experiment_identity import (
    ExperimentIdentity,
    raw_relative_path,
    result_relative_path,
)
from tools.experiments.run_managed_experiment import (
    CommandSelection,
    GitSnapshot,
    RegistryContext,
    RunContext,
    build_manifest,
    build_placeholders,
    build_run_environment,
    build_run_paths,
    reserve_run_paths,
    rollback_empty_reservation,
)


def _context(tmp_path: Path) -> RunContext:
    repo_root = tmp_path / "repo"
    topic_dir = repo_root / "experiments" / "demo"
    (topic_dir / "result").mkdir(parents=True)
    (topic_dir / "raw").mkdir()
    (repo_root / "experiments" / "report").mkdir()
    identity = ExperimentIdentity("demo", "formal", "run-a")
    report_path = (
        repo_root
        / "experiments"
        / "report"
        / identity.topic
        / identity.variant
        / f"{identity.run_name}.md"
    )
    paths = build_run_paths(topic_dir, identity, report_path)
    return RunContext(
        repo_root=repo_root,
        identity=identity,
        topic_dir=topic_dir,
        paths=paths,
        registry=RegistryContext(
            path=repo_root / "experiments" / "registry.toml",
            entry={},
            defaults={},
            available=False,
        ),
        command=CommandSelection(
            command=["python3", "experiments/demo/run.py"],
            source="manual",
            registered_match=None,
        ),
        created_at="2026-08-18T00:00:00Z",
        git=GitSnapshot(branch="main", commit="a" * 40, status_short=[]),
    )


def test_identity_derives_result_and_raw_paths_once(tmp_path: Path) -> None:
    """Both homes are projections of the same complete identity."""
    context = _context(tmp_path)
    identity = context.identity
    assert context.paths.result_dir == context.repo_root / result_relative_path(identity)
    assert context.paths.raw_dir == context.repo_root / raw_relative_path(identity)
    placeholders = build_placeholders(
        context.repo_root,
        identity,
        context.topic_dir,
        context.paths,
    )
    assert placeholders["run_dir"] == str(context.paths.result_dir)
    assert placeholders["raw_dir"] == str(context.paths.raw_dir)


def test_managed_child_environment_and_manifest_bind_raw_path(tmp_path: Path) -> None:
    """The managed owner supplies the raw path and records an unarchived binding."""
    context = _context(tmp_path)
    environment = build_run_environment(context)
    assert environment["EXPERIMENT_RUN_DIR"] == str(context.paths.result_dir)
    assert environment["EXPERIMENT_RAW_DIR"] == str(context.paths.raw_dir)
    manifest = build_manifest(context, "running")
    assert manifest["raw_dir"] == str(context.paths.raw_dir)
    assert manifest["raw_artifacts"] == {
        "path": raw_relative_path(context.identity).as_posix(),
        "retention": {"state": "unarchived"},
    }


def test_reservation_owns_result_raw_and_report_as_one_identity(tmp_path: Path) -> None:
    """A pre-artifact rollback removes all three exclusively reserved paths."""
    context = _context(tmp_path)
    receipt = reserve_run_paths(context, skip_report_init=False)
    assert context.paths.result_dir.is_dir()
    assert context.paths.raw_dir.is_dir()
    assert context.paths.report_path.is_file()
    assert rollback_empty_reservation(receipt)
    assert not context.paths.result_dir.exists()
    assert not context.paths.raw_dir.exists()
    assert not context.paths.report_path.exists()


def test_build_run_paths_rejects_symlinked_raw_variant(tmp_path: Path) -> None:
    """Raw writes fail closed when the identity path is redirected."""
    repo_root = tmp_path / "repo"
    topic_dir = repo_root / "experiments" / "demo"
    (topic_dir / "result").mkdir(parents=True)
    raw_root = topic_dir / "raw"
    raw_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (raw_root / "formal").symlink_to(outside, target_is_directory=True)
    identity = ExperimentIdentity("demo", "formal", "run-a")
    report_path = (
        repo_root
        / "experiments"
        / "report"
        / identity.topic
        / identity.variant
        / f"{identity.run_name}.md"
    )
    try:
        build_run_paths(topic_dir, identity, report_path)
    except ValueError as error:
        assert "raw" in str(error)
        assert "symlink" in str(error)
    else:
        raise AssertionError("symlinked raw variant was accepted")
    assert not list(outside.iterdir())
