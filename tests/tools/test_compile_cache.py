"""Tests the seeded Cargo registry-index merge used by the container compiler."""

# @dependency-start
# contract test
# responsibility Verifies the bootstrap compiler refreshes seeded mutable registry-index files only.
# upstream implementation ../../tools/runtime/container/compile.sh owns the sourceable registry-index merge.
# @dependency-end

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPILE_SCRIPT = PROJECT_ROOT / "tools" / "runtime" / "container" / "compile.sh"


def merge_seeded_registry_index(
    seed_index: Path, destination_index: Path
) -> subprocess.CompletedProcess[str]:
    """Call the product's sourceable merge function with isolated temporary roots."""
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; _refresh_seeded_registry_index "$2" "$3"',
            "compile-cache-test",
            str(COMPILE_SCRIPT),
            str(seed_index),
            str(destination_index),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_seeded_index_refresh_preserves_other_cache_and_target_bytes(
    tmp_path: Path,
) -> None:
    """Seeded index files refresh while archives, sources, unrelated entries, and targets remain intact."""
    seed_home = tmp_path / "seed cargo home"
    cargo_home = tmp_path / "persistent cargo home"
    registry = "index.crates.io-6f17d22bba15001f"
    seed_index = seed_home / "registry" / "index"
    destination_index = cargo_home / "registry" / "index"
    relative_cache = Path(registry) / ".cache" / "sy" / "nc" / "syn"
    seeded_cache = seed_index / relative_cache
    existing_cache = destination_index / relative_cache
    seeded_config = seed_index / registry / "config.json"
    existing_config = destination_index / registry / "config.json"
    unseeded_cache = (
        destination_index / "other-registry" / ".cache" / "un" / "kn" / "unknown"
    )
    seeded_archive = seed_home / "registry" / "cache" / registry / "syn-3.0.9.crate"
    existing_archive = cargo_home / "registry" / "cache" / registry / "syn-3.0.9.crate"
    seeded_source = (
        seed_home / "registry" / "src" / registry / "syn-3.0.9" / "Cargo.toml"
    )
    existing_source = (
        cargo_home / "registry" / "src" / registry / "syn-3.0.9" / "Cargo.toml"
    )
    target_sentinel = tmp_path / "cargo target" / "sentinel.bin"

    seed_cache_bytes = b"seeded sparse index record for syn 3.0.9\n"
    seed_config_bytes = b'{"dl":"https://static.crates.io/crates"}\n'
    unseeded_cache_bytes = b"unseeded index entry\n"
    existing_archive_bytes = b"persistent archive must remain unchanged\n"
    existing_source_bytes = b"persistent source must remain unchanged\n"
    target_bytes = b"existing Cargo target must remain unchanged\n"

    for path in (seeded_cache, seeded_config, seeded_archive, seeded_source):
        path.parent.mkdir(parents=True, exist_ok=True)
    for path in (
        existing_cache,
        existing_config,
        unseeded_cache,
        existing_archive,
        existing_source,
        target_sentinel,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)

    seeded_cache.write_bytes(seed_cache_bytes)
    seeded_config.write_bytes(seed_config_bytes)
    existing_cache.write_bytes(b"stale sparse index record for syn 3.0.4\n")
    existing_config.write_bytes(b'{"dl":"https://stale.example.invalid"}\n')
    unseeded_cache.write_bytes(unseeded_cache_bytes)
    seeded_archive.write_bytes(b"seed archive bytes\n")
    existing_archive.write_bytes(existing_archive_bytes)
    seeded_source.write_text("seed source\n", encoding="utf-8")
    existing_source.write_bytes(existing_source_bytes)
    target_sentinel.write_bytes(target_bytes)

    result = merge_seeded_registry_index(seed_index, destination_index)

    assert result.returncode == 0, result.stdout + result.stderr
    assert existing_cache.read_bytes() == seed_cache_bytes
    assert existing_config.read_bytes() == seed_config_bytes
    assert unseeded_cache.read_bytes() == unseeded_cache_bytes
    assert existing_archive.read_bytes() == existing_archive_bytes
    assert existing_source.read_bytes() == existing_source_bytes
    assert target_sentinel.read_bytes() == target_bytes
    assert seeded_cache.read_bytes() == seed_cache_bytes
    assert seeded_config.read_bytes() == seed_config_bytes
    assert seeded_archive.read_bytes() == b"seed archive bytes\n"
    assert seeded_source.read_text(encoding="utf-8") == "seed source\n"
    assert not any(".tmp." in path.name for path in destination_index.rglob("*"))


def test_seeded_index_merge_fails_without_replacing_a_conflicting_entry(
    tmp_path: Path,
) -> None:
    """A non-directory destination parent fails without changing its existing bytes."""
    seed_index = tmp_path / "seed" / "registry" / "index"
    destination_index = tmp_path / "persistent" / "registry" / "index"
    registry_name = "index.crates.io-6f17d22bba15001f"
    seeded_metadata = seed_index / registry_name / "config.json"
    conflicting_parent = destination_index / registry_name
    seeded_metadata.parent.mkdir(parents=True)
    destination_index.mkdir(parents=True)
    seeded_metadata.write_bytes(b'{"dl":"seed"}\n')
    conflicting_bytes = b"existing non-directory destination\n"
    conflicting_parent.write_bytes(conflicting_bytes)

    result = merge_seeded_registry_index(seed_index, destination_index)

    assert result.returncode != 0
    assert conflicting_parent.read_bytes() == conflicting_bytes
    assert not any(".tmp." in path.name for path in destination_index.rglob("*"))


def test_missing_seed_index_is_a_noop(tmp_path: Path) -> None:
    """An optional absent image index leaves persistent metadata untouched."""
    missing_seed = tmp_path / "seed" / "registry" / "index"
    destination_index = tmp_path / "persistent" / "registry" / "index"
    existing = destination_index / "index.crates.io-6f17d22bba15001f" / "config.json"
    existing.parent.mkdir(parents=True)
    existing_bytes = b"persistent index remains unchanged\n"
    existing.write_bytes(existing_bytes)

    result = merge_seeded_registry_index(missing_seed, destination_index)

    assert result.returncode == 0, result.stdout + result.stderr
    assert existing.read_bytes() == existing_bytes


def test_unreadable_seed_metadata_fails_without_partial_replacement(
    tmp_path: Path,
) -> None:
    """A non-root POSIX copy failure preserves the old index file and removes its temp."""
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("mode-zero seed files require a non-root POSIX test process")

    seed_index = tmp_path / "seed" / "registry" / "index"
    destination_index = tmp_path / "persistent" / "registry" / "index"
    relative = Path("index.crates.io-6f17d22bba15001f") / "config.json"
    seeded = seed_index / relative
    existing = destination_index / relative
    seeded.parent.mkdir(parents=True)
    existing.parent.mkdir(parents=True)
    seeded.write_bytes(b'{"dl":"seeded"}\n')
    existing_bytes = b'{"dl":"existing"}\n'
    existing.write_bytes(existing_bytes)
    seeded.chmod(0)
    try:
        result = merge_seeded_registry_index(seed_index, destination_index)
    finally:
        seeded.chmod(0o600)

    assert result.returncode != 0, result.stdout + result.stderr
    assert existing.read_bytes() == existing_bytes
    assert not any(".tmp." in path.name for path in destination_index.rglob("*"))
