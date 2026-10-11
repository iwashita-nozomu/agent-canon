#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Exports canonical template profiles to fresh external directories.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md template ownership
# upstream design ../../../documents/contracts/template-bundle-manifest.toml profile manifest
# downstream implementation ../../../tests/agent_tools/test_template_bundle.py exporter tests
# @dependency-end
"""Deterministic source-commit-bound template bundle exporter."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 image/runtime
    import tomli as tomllib  # type: ignore[no-redef]

MANIFEST = "documents/contracts/template-bundle-manifest.toml"
CODEX_USER_PROFILE = "codex-user"
CODEX_USER_SCHEMA = "agent-canon.codex-user-bundle.v1"
CODEX_USER_MANIFEST = "codex-user-bundle.json"
CODEX_HOOK_EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


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


def _codex_user_hook_configuration(root: Path, commit: str) -> bytes:
    """Project the canonical active hooks onto the source-free host entry."""
    try:
        source = json.loads(_blob(root, commit, ".codex/hooks.json"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TemplateBundleError("canonical hook configuration is invalid") from exc
    hooks = source.get("hooks") if isinstance(source, dict) else None
    if not isinstance(hooks, dict) or set(hooks) != set(CODEX_HOOK_EVENTS):
        raise TemplateBundleError("canonical active hook events changed")
    projected: dict[str, Any] = {"hooks": {}}
    for event in CODEX_HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list) or not groups:
            raise TemplateBundleError(f"canonical hook groups are missing: {event}")
        projected_groups: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise TemplateBundleError(f"canonical hook group is invalid: {event}")
            projected_group = dict(group)
            projected_hooks: list[dict[str, Any]] = []
            for hook in group["hooks"]:
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    raise TemplateBundleError(f"canonical hook command is invalid: {event}")
                projected_hook = dict(hook)
                projected_hook["command"] = (
                    'bash "${PLUGIN_ROOT}/bootstrap.sh" '
                    '--control-parent-root "${AGENT_CANON_CONTROL_PARENT_ROOT:-${HOME}}" '
                    f"codex hook {event}"
                )
                projected_hooks.append(projected_hook)
            projected_group["hooks"] = projected_hooks
            projected_groups.append(projected_group)
        projected["hooks"][event] = projected_groups
    return (json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _codex_skill_frontmatter(content: bytes, skill: str) -> bytes:
    """Reuse the generated shim's plugin discovery metadata, not its source link."""
    match = re.match(rb"\A---\r?\n.*?\r?\n---\r?\n", content, re.DOTALL)
    if match is None:
        raise TemplateBundleError(f"generated Codex skill frontmatter is invalid: {skill}")
    frontmatter = match.group(0)
    try:
        lines = frontmatter.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise TemplateBundleError(
            f"generated Codex skill frontmatter is not UTF-8: {skill}"
        ) from exc
    if lines.count(f"name: {skill}") != 1:
        raise TemplateBundleError(f"generated Codex skill name differs: {skill}")
    return frontmatter


def _codex_user_payload(
    root: Path,
    commit: str,
    entries: list[tuple[str, str]],
) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    """Build the one source-free Codex package from existing canonical views."""
    payload: dict[str, bytes] = {}
    install_files: list[dict[str, str]] = []
    root_guidance: bytes | None = None
    skill_frontmatter: dict[str, bytes] = {}
    canonical_skills: dict[str, bytes] = {}
    for source_path, mode in entries:
        if mode not in {"100644", "100755"}:
            raise TemplateBundleError(f"Codex bundle source is not a regular file: {source_path}")
        content = _blob(root, commit, source_path)
        if source_path == "ROOT_AGENTS.md":
            root_guidance = content
            continue
        if source_path == ".codex/hooks.json":
            payload["hooks/hooks.json"] = _codex_user_hook_configuration(root, commit)
            continue
        if source_path.startswith(".codex/agents/"):
            filename = source_path.rsplit("/", 1)[-1]
            if source_path.count("/") != 2 or not filename.endswith(".toml"):
                raise TemplateBundleError("Codex bundle agent source is not a direct TOML child")
            destination = f"agents/agent-canon-{filename}"
            if destination in payload:
                raise TemplateBundleError("Codex bundle agent destination is duplicated")
            payload[destination] = content
            install_files.append(
                {
                    "component": "agent",
                    "bundle_path": destination,
                    "destination": f"codex/agents/agent-canon-{filename}",
                }
            )
            continue
        if source_path.startswith(".codex/personal/skills/"):
            relative = source_path.removeprefix(".codex/personal/skills/")
            parts = relative.split("/")
            if len(parts) != 2 or parts[1] != "SKILL.md":
                raise TemplateBundleError("Codex skill materialization is not one-file scoped")
            skill = parts[0]
            if skill in skill_frontmatter:
                raise TemplateBundleError(f"Codex skill view is duplicated: {skill}")
            skill_frontmatter[skill] = _codex_skill_frontmatter(content, skill)
            continue
        if source_path.startswith("agents/skills/"):
            if source_path.endswith(".md"):
                skill = source_path.rsplit("/", 1)[-1][:-3]
                if skill in skill_frontmatter:
                    canonical_skills[skill] = content
            continue
        payload[source_path] = content

    if set(skill_frontmatter) != set(canonical_skills):
        raise TemplateBundleError("Codex skill views and canonical owners differ")
    for skill, frontmatter in sorted(skill_frontmatter.items()):
        payload[f"skills/{skill}/SKILL.md"] = (
            frontmatter + b"\n" + canonical_skills[skill]
        )

    if root_guidance is None:
        raise TemplateBundleError("portable common ROOT_AGENTS.md is missing")
    if "plugin.json" in payload or "marketplace.json" in payload:
        raise TemplateBundleError("Codex bundle plugin paths collide with source files")

    # Reuse the canonical root composer, with an empty consumer-owned layer:
    # user bundle guidance contains only the portable common base.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools.agent.templates.entrypoint_composer import Composition

    payload["guidance/AGENTS.md"] = Composition(
        source_commit=commit,
        base=root_guidance,
        specific=b"",
    ).render()
    install_files.append(
        {
            "component": "guidance",
            "bundle_path": "guidance/AGENTS.md",
            "destination": "codex/AGENTS.md",
        }
    )

    plugin = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "agent-canon",
        "version": "0.1.0",
        "description": "AgentCanon user-scoped agents, guidance, skills, and trusted-project hooks.",
    }
    payload["plugin.json"] = (
        json.dumps(plugin, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    marketplace = {
        "name": "agent-canon-user-bundle",
        "plugins": [
            {
                "name": "agent-canon",
                "source": {"path": "./"},
                "interface": {"displayName": "AgentCanon"},
            }
        ],
    }
    payload["marketplace.json"] = (
        json.dumps(marketplace, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    install_files.sort(key=lambda item: (item["destination"], item["bundle_path"]))
    return payload, install_files


def _codex_user_bundle_digest(
    source_commit: str,
    source_bundle_digest: str,
    manifest_digest: str,
    payload: dict[str, bytes],
    install_files: list[dict[str, str]],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        CODEX_USER_SCHEMA.encode()
        + b"\0"
        + source_commit.encode()
        + b"\0"
        + source_bundle_digest.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    )
    for path, content in sorted(payload.items()):
        digest.update(path.encode() + b"\0" + hashlib.sha256(content).digest() + b"\0")
    for record in install_files:
        digest.update(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            + b"\0"
        )
    return digest.hexdigest()


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
    source_bundle_digest = digest.hexdigest()
    if profile == CODEX_USER_PROFILE:
        payload, install_files = _codex_user_payload(root, commit, entries)
        source_tree = _git(root, "rev-parse", "--verify", f"{commit}^{{tree}}").decode().strip()
        return {
            "schema": CODEX_USER_SCHEMA,
            "source_commit": commit,
            "source_tree": source_tree,
            "profile": profile,
            "manifest_digest": manifest_digest,
            "source_bundle_digest": source_bundle_digest,
            "bundle_digest": _codex_user_bundle_digest(
                commit,
                source_bundle_digest,
                manifest_digest,
                payload,
                install_files,
            ),
            "paths": sorted(payload),
        }
    return {
        "schema": "agent-canon.template-bundle.v1",
        "source_commit": commit,
        "profile": profile,
        "manifest_digest": manifest_digest,
        "bundle_digest": source_bundle_digest,
        "paths": [path for path, _mode in entries],
    }


def _codex_user_manifest(
    identity: dict[str, Any],
    payload: dict[str, bytes],
    install_files: list[dict[str, str]],
) -> dict[str, Any]:
    """Bind every generated/runtime file to one deterministic bundle digest."""
    return {
        "schema": CODEX_USER_SCHEMA,
        "version": 1,
        "source_commit": identity["source_commit"],
        "source_tree": identity["source_tree"],
        "profile": CODEX_USER_PROFILE,
        "manifest_digest": identity["manifest_digest"],
        "source_bundle_digest": identity["source_bundle_digest"],
        "bundle_digest": identity["bundle_digest"],
        "files": [
            {"path": path, "sha256": hashlib.sha256(payload[path]).hexdigest()}
            for path in sorted(payload)
        ],
        "install_files": install_files,
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
    if profile == CODEX_USER_PROFILE:
        entries = _entries(
            source_root,
            identity["source_commit"],
            [
                str(item)
                for item in _manifest(source_root, identity["source_commit"])[0]["profiles"][profile]["roots"]
            ],
        )
        payload, install_files = _codex_user_payload(
            source_root, identity["source_commit"], entries
        )
        for path, content in sorted(payload.items()):
            destination = output.joinpath(*PurePosixPath(path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        bundle_manifest = _codex_user_manifest(identity, payload, install_files)
        (output / CODEX_USER_MANIFEST).write_text(
            json.dumps(bundle_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {**identity, "output": str(output)}
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


def _verify_codex_user_bundle(root: Path) -> dict[str, Any]:
    """Validate the exact source-free user package and its install projection."""
    if root.is_symlink() or not root.is_dir():
        raise TemplateBundleError("Codex user bundle root is missing or unsafe")
    root = root.resolve()
    manifest_path = root / CODEX_USER_MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise TemplateBundleError("Codex user bundle manifest is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TemplateBundleError("Codex user bundle manifest is invalid") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != CODEX_USER_SCHEMA
        or manifest.get("version") != 1
        or manifest.get("profile") != CODEX_USER_PROFILE
    ):
        raise TemplateBundleError("Codex user bundle schema or profile is invalid")
    source_commit = manifest.get("source_commit")
    source_tree = manifest.get("source_tree")
    bundle_digest = manifest.get("bundle_digest")
    source_bundle_digest = manifest.get("source_bundle_digest")
    manifest_digest = manifest.get("manifest_digest")
    if (
        not isinstance(source_commit, str)
        or not HEX_40.fullmatch(source_commit)
        or not isinstance(source_tree, str)
        or not HEX_40.fullmatch(source_tree)
        or not isinstance(bundle_digest, str)
        or not HEX_64.fullmatch(bundle_digest)
        or not isinstance(source_bundle_digest, str)
        or not HEX_64.fullmatch(source_bundle_digest)
        or not isinstance(manifest_digest, str)
        or not HEX_64.fullmatch(manifest_digest)
    ):
        raise TemplateBundleError("Codex user bundle identity is invalid")
    rows = manifest.get("files")
    installs = manifest.get("install_files")
    if not isinstance(rows, list) or not isinstance(installs, list):
        raise TemplateBundleError("Codex user bundle file records are missing")
    payload: dict[str, bytes] = {}
    previous = ""
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise TemplateBundleError("Codex user bundle file record is invalid")
        relative = row["path"]
        sha256 = row["sha256"]
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or any(character in relative for character in "\x00\t\n\r")
            or PurePosixPath(relative).is_absolute()
            or ".." in PurePosixPath(relative).parts
            or not isinstance(sha256, str)
            or not HEX_64.fullmatch(sha256)
            or relative <= previous
        ):
            raise TemplateBundleError("Codex user bundle file path or digest is invalid")
        previous = relative
        candidate = root.joinpath(*PurePosixPath(relative).parts)
        current = root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise TemplateBundleError("Codex user bundle contains a symlink")
        if not candidate.is_file():
            raise TemplateBundleError(f"Codex user bundle file is missing: {relative}")
        content = candidate.read_bytes()
        if hashlib.sha256(content).hexdigest() != sha256:
            raise TemplateBundleError(f"Codex user bundle file digest differs: {relative}")
        payload[relative] = content

    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise TemplateBundleError("Codex user bundle contains a symlink")
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(root).as_posix())
    if actual != set(payload):
        raise TemplateBundleError("Codex user bundle contains unmanifested files")

    required_paths = {
        "bootstrap.sh",
        "bootstrap/host/lifecycle/entrypoint.sh",
        "tools/runtime/container/bootstrap_runtime.py",
        ".codex/hooks/hook_dispatcher.py",
        "hooks/hooks.json",
        "plugin.json",
        "marketplace.json",
        "skills/agent-canon-bootstrap/SKILL.md",
        "guidance/AGENTS.md",
    }
    if not required_paths.issubset(payload):
        raise TemplateBundleError("Codex user bundle is missing required runtime files")

    normalized_installs: list[dict[str, str]] = []
    seen_destinations: set[str] = set()
    for row in installs:
        if not isinstance(row, dict) or set(row) != {"component", "bundle_path", "destination"}:
            raise TemplateBundleError("Codex user bundle install record is invalid")
        component = row["component"]
        bundle_path = row["bundle_path"]
        destination = row["destination"]
        if (
            not isinstance(component, str)
            or component not in {"agent", "guidance"}
            or not isinstance(bundle_path, str)
            or not isinstance(destination, str)
            or bundle_path not in payload
            or any(character in destination for character in "\\\x00\t\n\r")
            or destination in seen_destinations
        ):
            raise TemplateBundleError("Codex user bundle install record is invalid")
        if component == "agent" and not (
            bundle_path.startswith("agents/agent-canon-")
            and bundle_path.count("/") == 1
            and bundle_path.endswith(".toml")
            and destination == f"codex/agents/{bundle_path.rsplit('/', 1)[-1]}"
        ):
            raise TemplateBundleError("Codex user bundle agent destination is invalid")
        if component == "guidance" and not (
            bundle_path == "guidance/AGENTS.md" and destination == "codex/AGENTS.md"
        ):
            raise TemplateBundleError("Codex user bundle guidance destination is invalid")
        seen_destinations.add(destination)
        normalized_installs.append(
            {"component": component, "bundle_path": bundle_path, "destination": destination}
        )
    normalized_installs.sort(key=lambda item: (item["destination"], item["bundle_path"]))
    expected_installs = [
        {
            "component": "agent",
            "bundle_path": path,
            "destination": f"codex/agents/{path.rsplit('/', 1)[-1]}",
        }
        for path in sorted(payload)
        if path.startswith("agents/agent-canon-") and path.endswith(".toml")
    ]
    expected_installs.append(
        {
            "component": "guidance",
            "bundle_path": "guidance/AGENTS.md",
            "destination": "codex/AGENTS.md",
        }
    )
    expected_installs.sort(key=lambda item: (item["destination"], item["bundle_path"]))
    if normalized_installs != expected_installs:
        raise TemplateBundleError("Codex user bundle install projection is incomplete")
    computed = _codex_user_bundle_digest(
        source_commit,
        source_bundle_digest,
        manifest_digest,
        payload,
        normalized_installs,
    )
    if computed != bundle_digest:
        raise TemplateBundleError("Codex user bundle aggregate digest differs")
    return {**manifest, "install_files": normalized_installs}


def verify_codex_user_bundle(root: Path) -> dict[str, Any]:
    """Validate one source-free Codex package without requiring Git metadata."""
    return _verify_codex_user_bundle(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    export = sub.add_parser("export")
    export.add_argument("--source-root", required=True)
    export.add_argument("--source-ref", required=True)
    export.add_argument("--profile", required=True)
    export.add_argument("--output", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", required=True)
    verify.add_argument("--format", choices=("json", "install-tsv"), default="json")
    args = parser.parse_args(argv)
    try:
        if args.operation == "verify":
            result = verify_codex_user_bundle(Path(args.root))
        else:
            result = export_bundle(
                source_root=Path(args.source_root),
                source_ref=args.source_ref,
                profile=args.profile,
                output=Path(args.output),
            )
    except TemplateBundleError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    if args.operation == "verify" and args.format == "install-tsv":
        print(f"bundle\t{result['bundle_digest']}\t{result['source_commit']}")
        digests = {row["path"]: row["sha256"] for row in result["files"]}
        for row in result["install_files"]:
            print(
                "\t".join(
                    (
                        "install",
                        row["component"],
                        row["bundle_path"],
                        row["destination"],
                        digests[row["bundle_path"]],
                    )
                )
            )
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
