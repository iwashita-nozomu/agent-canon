#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Exports canonical template profiles to fresh external directories.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md template ownership
# upstream design ../../documents/contracts/template-bundle-manifest.toml profile manifest
# downstream implementation ../../tests/agent_tools/test_template_bundle.py exporter tests
# @dependency-end
"""Deterministic source-commit-bound template bundle exporter."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST = "documents/contracts/template-bundle-manifest.toml"


class TemplateBundleError(RuntimeError):
    """Raised for invalid source or output boundaries."""


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    if result.returncode:
        raise TemplateBundleError(result.stderr.decode("utf-8", "replace").strip() or "git command failed")
    return result.stdout


def _commit(root: Path, ref: str) -> str:
    value = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    if len(value) < 40 or any(char not in "0123456789abcdef" for char in value):
        raise TemplateBundleError("invalid source commit")
    return value


def _manifest(root: Path, commit: str) -> tuple[dict[str, Any], str]:
    raw = _git(root, "show", f"{commit}:{MANIFEST}")
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise TemplateBundleError("template bundle manifest is invalid") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise TemplateBundleError("template bundle manifest version must be 1")
    if not isinstance(value.get("profiles"), dict):
        raise TemplateBundleError("template bundle profiles are missing")
    return value, hashlib.sha256(raw).hexdigest()


def _entries(root: Path, commit: str, roots: list[str]) -> list[tuple[str, str]]:
    records = _git(root, "ls-tree", "-r", "-z", commit).split(b"\0")
    entries: list[tuple[str, str]] = []
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, _object_id = metadata.decode().split(" ", 2)
        path = raw_path.decode()
        if kind == "blob" and any(path == root_path or path.startswith(root_path + "/") for root_path in roots):
            entries.append((path, mode))
    return sorted(entries)


def _blob(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}")


def bundle_identity(root: Path, source_ref: str, profile: str) -> dict[str, Any]:
    """Return source-bound identity without writing an output directory."""
    root = root.resolve()
    commit = _commit(root, source_ref)
    manifest, manifest_digest = _manifest(root, commit)
    profile_record = manifest["profiles"].get(profile)
    if not isinstance(profile_record, dict) or not isinstance(profile_record.get("roots"), list):
        raise TemplateBundleError(f"unknown template profile: {profile}")
    roots = [str(item) for item in profile_record["roots"]]
    digest = hashlib.sha256()
    digest.update(str(manifest["version"]).encode())
    digest.update(b"\0" + profile.encode() + b"\0" + manifest_digest.encode() + b"\0")
    entries = _entries(root, commit, roots)
    for path, mode in entries:
        content = _blob(root, commit, path)
        digest.update(path.encode() + b"\0" + mode.encode() + b"\0")
        digest.update(hashlib.sha256(content).digest() + b"\0")
    return {
        "schema": "agent-canon.template-bundle.v1",
        "source_commit": commit,
        "profile": profile,
        "manifest_digest": manifest_digest,
        "bundle_digest": digest.hexdigest(),
        "paths": [path for path, _mode in entries],
    }


def export_bundle(*, source_root: Path, source_ref: str, profile: str, output: Path) -> dict[str, Any]:
    """Export one profile without touching source or consumer repositories."""
    source_root = source_root.resolve()
    output = output if output.is_absolute() else Path.cwd() / output
    resolved_output = output.resolve(strict=False)
    if resolved_output == source_root or source_root in resolved_output.parents:
        raise TemplateBundleError("output must be outside AgentCanon source")
    if output.exists() or output.is_symlink():
        raise TemplateBundleError("output must be a fresh directory")
    if profile == "static-seed":
        raise TemplateBundleError("static-seed uses export_static_seed.py")
    identity = bundle_identity(source_root, source_ref, profile)
    output.mkdir(parents=True)
    for path in identity["paths"]:
        destination = output.joinpath(*PurePosixPath(path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_blob(source_root, identity["source_commit"], path))
    provenance = {**identity, "output": str(output)}
    (output / "template-bundle-provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    export = sub.add_parser("export")
    export.add_argument("--source-root", required=True)
    export.add_argument("--source-ref", required=True)
    export.add_argument("--profile", required=True)
    export.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = export_bundle(
            source_root=Path(args.source_root),
            source_ref=args.source_ref,
            profile=args.profile,
            output=Path(args.output),
        )
    except TemplateBundleError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
