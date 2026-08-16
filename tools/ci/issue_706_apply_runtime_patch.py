#!/usr/bin/env python3
"""Apply the one-time Issue #706 runtime-alignment source correction."""

from __future__ import annotations

from pathlib import Path

PATH = Path("tools/agent_tools/check_agent_runtime_alignment.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace one exact source fragment or fail without partial output."""
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    """Patch the dependency edge, imports, and fixture-owner context."""
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "# upstream implementation ./workspace_scope.py owns typed workspace/source/report roots\n",
        "# upstream implementation ./workspace_scope.py owns typed workspace/source/report roots\n"
        "# upstream implementation ./fixture_spawn.py owns synthetic repository identity and writable-environment projection\n",
        "dependency header",
    )
    text = replace_once(
        text,
        '''try:
    from .parent_root_side_effects import (
        ParentRootSideEffectBoundary,
        public_session,
        resolve_parent_writer_attestation,
    )
except ImportError:
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootSideEffectBoundary,
        public_session,
        resolve_parent_writer_attestation,
    )
''',
        '''try:
    from .fixture_spawn import (
        bootstrap_fixture_public_environment,
        record_capability_from_environment,
    )
    from .parent_root_side_effects import (
        PRIVATE_RECORD_REQUIRED_ENV,
        ParentRootSideEffectBoundary,
        RecordCapability,
        public_session,
        resolve_parent_writer_attestation,
    )
except ImportError:
    from fixture_spawn import (  # type: ignore[no-redef]
        bootstrap_fixture_public_environment,
        record_capability_from_environment,
    )
    from parent_root_side_effects import (  # type: ignore[no-redef]
        PRIVATE_RECORD_REQUIRED_ENV,
        ParentRootSideEffectBoundary,
        RecordCapability,
        public_session,
        resolve_parent_writer_attestation,
    )
''',
        "runtime boundary imports",
    )
    text = replace_once(
        text,
        '''@contextmanager
def runtime_alignment_parent(source_resolution: RootResolution):
    """Yield an authenticated parent that can host derived alignment state.

    The standalone static-gate wrapper authenticates the source checkout itself
    as the parent.  A derived workspace cannot place reports below that source
    without violating the typed root boundary, so the self-check creates a
    short-lived Git parent beside the source checkout for this fixture only.
    Managed parent/derived executions retain their caller-provided parent.
    """
    source_root = source_resolution.source_root.resolve()
    configured_parent = os.environ.get("AGENT_CANON_SIDE_EFFECT_PARENT_ROOT", "").strip()
    parent = Path(configured_parent).resolve(strict=True) if configured_parent else source_root
    if parent != source_root:
        attestation = resolve_parent_writer_attestation(purpose="runtime-alignment")
        base = ParentRootSideEffectBoundary().ensure_parent_owned_directory(
            attestation,
            parent / ".agent-canon" / "tmp" / "runtime-alignment",
            "runtime-alignment-temp",
        )
        yield base.physical_path
        return

    source_origin = subprocess.run(
        ["git", "-C", str(source_root), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    with tempfile.TemporaryDirectory(
        prefix=".agent-canon-runtime-parent-",
        dir=source_root.parent,
    ) as fixture_parent_text:
        fixture_parent = Path(fixture_parent_text)
        subprocess.run(["git", "init", "-q", str(fixture_parent)], check=True)
        subprocess.run(
            ["git", "-C", str(fixture_parent), "remote", "add", "origin", source_origin],
            check=True,
        )
        boundary = ParentRootSideEffectBoundary()
        previous_cwd = Path.cwd()
        try:
            os.chdir(source_root)
            with public_session(
                invocation_script=Path(__file__), purpose="runtime-alignment"
            ) as outer:
                os.chdir(fixture_parent)
                base = boundary.ensure_parent_owned_directory(
                    outer.attestation,
                    fixture_parent / ".agent-canon" / "tmp" / "runtime-alignment",
                    "runtime-alignment-temp",
                )
                yield base.physical_path
        finally:
            os.chdir(previous_cwd)
''',
        '''@contextmanager
def runtime_alignment_parent(source_resolution: RootResolution):
    """Yield one fixture-owned parent for derived runtime-alignment state.

    Tooling remains loaded from ``source_root``.  When the caller's writable
    parent is the source checkout itself, the source record authorizes only a
    nested temporary Git fixture.  The central synthetic fixture bootstrap then
    projects an independent repository identity and fixture-local writable
    environment before any derived bundle is created.
    """
    source_root = source_resolution.source_root.resolve()
    configured_parent = os.environ.get(
        "AGENT_CANON_SIDE_EFFECT_PARENT_ROOT", ""
    ).strip()
    parent = (
        Path(configured_parent).resolve(strict=True)
        if configured_parent
        else source_root
    )
    if parent != source_root:
        attestation = resolve_parent_writer_attestation(
            purpose="runtime-alignment"
        )
        base = ParentRootSideEffectBoundary().ensure_parent_owned_directory(
            attestation,
            parent / ".agent-canon" / "tmp" / "runtime-alignment",
            "runtime-alignment-temp",
        )
        yield base.physical_path
        return

    boundary = ParentRootSideEffectBoundary()
    previous_cwd = Path.cwd().resolve()

    @contextmanager
    def source_capability():
        if os.environ.get(PRIVATE_RECORD_REQUIRED_ENV) == "1":
            yield (
                resolve_parent_writer_attestation(
                    purpose="runtime-alignment-source"
                ),
                record_capability_from_environment(
                    observed_cwd=source_root
                ),
            )
            return
        with public_session(
            invocation_script=Path(__file__).resolve(),
            purpose="runtime-alignment-source",
            cleanup_state=True,
        ) as source_session:
            yield (
                source_session.attestation,
                RecordCapability.from_record(source_session),
            )

    try:
        os.chdir(source_root)
        with source_capability() as (source_attestation, capability):
            fixture_receipt = boundary.create_parent_owned_temp_directory(
                source_attestation,
                source_root / ".agent-canon" / "tmp",
                "runtime-alignment-parent",
                "runtime-alignment",
            )
            fixture_parent = fixture_receipt.physical_path
            try:
                subprocess.run(
                    ["git", "init", "-q", str(fixture_parent)],
                    check=True,
                )
                source_origin = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(source_root),
                        "remote",
                        "get-url",
                        "origin",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if source_origin.returncode == 0 and source_origin.stdout.strip():
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(fixture_parent),
                            "remote",
                            "add",
                            "origin",
                            source_origin.stdout.strip(),
                        ],
                        check=True,
                    )

                with bootstrap_fixture_public_environment(
                    mode="synthetic_tool",
                    fixture_cwd=fixture_parent,
                    record_capability=capability,
                    ambient_env=os.environ,
                    purpose="agent-runtime-alignment",
                ) as fixture:
                    if fixture.session is None:
                        raise RuntimeError(
                            "runtime alignment synthetic session is missing"
                        )
                    base = boundary.ensure_parent_owned_directory(
                        fixture.session.attestation,
                        fixture_parent
                        / ".agent-canon"
                        / "tmp"
                        / "runtime-alignment",
                        "runtime-alignment-temp",
                    )
                    with _temporary_environment(fixture.environment):
                        os.chdir(fixture_parent)
                        try:
                            yield base.physical_path
                        finally:
                            os.chdir(source_root)
            finally:
                os.chdir(source_root)
                boundary.remove_parent_owned_tree(
                    source_attestation,
                    fixture_receipt,
                    "runtime-alignment-parent-cleanup",
                )
    finally:
        os.chdir(previous_cwd)
''',
        "runtime_alignment_parent",
    )
    PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
