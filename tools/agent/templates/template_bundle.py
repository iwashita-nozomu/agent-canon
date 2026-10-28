# @dependency-start
# contract tool
# responsibility Exports canonical template profiles and native CLI resources to external packages.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md template ownership
# upstream design ../../../documents/contracts/template-bundle-manifest.toml profile manifest
# upstream implementation ./entrypoint_composer.py portable root guidance composer
# downstream implementation ../../../tests/agent_tools/test_template_bundle.py exporter tests
# @dependency-end
"""Deterministic source-commit-bound template bundle exporter."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import posixpath
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.agent.templates.entrypoint_composer import Composition

MANIFEST = "documents/contracts/template-bundle-manifest.toml"
CODEX_USER_PROFILE = "codex-user"
CODEX_USER_SCHEMA = "agent-canon.codex-user-bundle.v1"
CODEX_USER_MANIFEST = "codex-user-bundle.json"
CODEX_MARKETPLACE = ".agents/plugins/marketplace.json"
NATIVE_CLI_PROFILE = "native-cli"
NATIVE_CLI_CARGO_MANIFEST = "tools/runtime/dispatch/agent-canon/Cargo.toml"
NATIVE_CLI_SCHEMA = "agent-canon.native-cli-package.v1"
CODEX_HOOK_EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class TemplateBundleError(RuntimeError):
    """Raised for invalid source or output boundaries."""


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=False, capture_output=True
    )
    if result.returncode:
        raise TemplateBundleError(
            result.stderr.decode("utf-8", "replace").strip() or "git command failed"
        )
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
    return [
        (path, mode)
        for path, mode in _tree_entries(root, commit)
        if any(path == item or path.startswith(item + "/") for item in roots)
    ]


def _tree_entries(root: Path, commit: str) -> list[tuple[str, str]]:
    records = _git(root, "ls-tree", "-r", "-z", commit).split(b"\0")
    entries: list[tuple[str, str]] = []
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, _object_id = metadata.decode().split(" ", 2)
        path = raw_path.decode()
        if kind == "blob":
            entries.append((path, mode))
    return sorted(entries)


def _blob(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}")


def _bundle_relative(value: object) -> PurePosixPath:
    """Accept one portable relative file name in every producer/reader."""
    if not isinstance(value, str) or not value:
        raise TemplateBundleError("bundle file path is missing")
    path = PurePosixPath(value)
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    if (
        not path.parts
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {".", ".."} for part in path.parts)
        or any(character in value for character in '\\:<>"|?*')
        or any(ord(character) < 32 for character in value)
        or any(
            part.rstrip(" .") != part
            or part.split(".", 1)[0].rstrip(" ").upper() in reserved
            for part in path.parts
        )
    ):
        raise TemplateBundleError(f"unsafe bundle file path: {value}")
    return path


def _bundle_destination(root: Path, relative: str) -> Path:
    destination = root.joinpath(*_bundle_relative(relative).parts)
    if root.resolve() not in destination.resolve(strict=False).parents:
        raise TemplateBundleError(f"bundle file escapes output: {relative}")
    return destination


def _markdown_destinations(text: str) -> Iterator[tuple[int, int, str]]:
    """Locate authored inline/image/reference destinations, excluding code."""
    offset = 0
    fence = ""
    frontmatter = text.startswith("---\n")
    for line_number, line in enumerate(text.splitlines(keepends=True)):
        if frontmatter:
            if line_number and line.strip() in {"---", "..."}:
                frontmatter = False
            offset += len(line)
            continue
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if marker:
            ticks = marker.group(1)
            if not fence:
                fence = ticks
            elif ticks[0] == fence[0] and len(ticks) >= len(fence):
                fence = ""
            offset += len(line)
            continue
        if not fence:
            code = [match.span() for match in re.finditer(r"(`+).*?\1", line)]
            for match in re.finditer(r"\]\([ \t]*|^ {0,3}\[[^\]\n]+\]:[ \t]*", line):
                if any(start <= match.start() < end for start, end in code):
                    continue
                start = end = match.end()
                if start < len(line) and line[start] == "<":
                    start += 1
                    end = line.find(">", start)
                    if end < 0:
                        raise TemplateBundleError("unterminated Markdown resource")
                else:
                    depth = 0
                    while end < len(line) and not line[end].isspace():
                        character = line[end]
                        if character == "\\":
                            end += 2
                            continue
                        if character == ")":
                            if depth == 0:
                                break
                            depth -= 1
                        elif character == "(":
                            depth += 1
                        end += 1
                if end > start:
                    yield offset + start, offset + end, line[start:end]
        offset += len(line)


def _local_resource(source: str, target: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    path = unquote(re.sub(r"\\([\\() ])", r"\1", parsed.path))
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
    if path.startswith("/") or resolved == ".." or resolved.startswith("../"):
        raise TemplateBundleError(
            f"Markdown resource escapes source: {source}: {target}"
        )
    return resolved


def _codex_user_entries(
    root: Path, commit: str, entries: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Close local references at the same commit, retaining source-relative topology."""
    inventory = dict(_tree_entries(root, commit))
    selected = dict(entries)
    profiles = _manifest(root, commit)[0]["profiles"]
    template_roots = [
        item
        for name, profile in profiles.items()
        if name != CODEX_USER_PROFILE and isinstance(profile, dict)
        for item in profile.get("roots", [])
        if isinstance(item, str)
    ]

    def template_asset(path: str) -> bool:
        return any(
            path == item or path.startswith(item + "/") for item in template_roots
        )

    pending = list(selected)
    visited: set[str] = set()
    while pending:
        source = pending.pop()
        # Template links describe the eventual consumer instance, not this package.
        if source in visited or not source.endswith(".md") or template_asset(source):
            continue
        visited.add(source)
        content = _blob(root, commit, source).decode("utf-8")
        for _, _, target in _markdown_destinations(content):
            resource = _local_resource(source, target)
            if resource is None:
                continue
            if resource in inventory:
                resources = [resource]
            else:
                prefix = "" if resource == "." else resource + "/"
                children = [path for path in inventory if path.startswith(prefix)]
                index = prefix + "README.md"
                resources = (
                    [index]
                    if index in inventory and not template_asset(resource)
                    else children
                )
                if not resources:
                    raise TemplateBundleError(
                        f"missing Markdown resource: {source}: {target}"
                    )
            for path in resources:
                if inventory[path] not in {"100644", "100755"}:
                    raise TemplateBundleError(f"unsafe Markdown resource: {path}")
                if path not in selected:
                    selected[path] = inventory[path]
                    pending.append(path)
    return sorted(selected.items())


def _codex_skill_body(source: str, destination: str, content: bytes) -> bytes:
    """Move only link destinations; referenced files keep their original paths."""
    text = content.decode("utf-8")
    # Source-maintenance edges retain their original base in the copied source.
    # They are not runtime instructions and would have a false base in this view.
    text = re.sub(
        r"(?ms)^<!--\s*\n@dependency-start\n.*?^@dependency-end\n-->\n?",
        "",
        text,
        count=1,
    )
    for start, end, target in reversed(list(_markdown_destinations(text))):
        resource = _local_resource(source, target)
        if resource is None:
            continue
        parsed = urlsplit(target)
        relative = quote(
            posixpath.relpath(resource, posixpath.dirname(destination)), safe="/._-"
        )
        replacement = urlunsplit(("", "", relative, parsed.query, parsed.fragment))
        text = text[:start] + replacement + text[end:]
    return text.encode("utf-8")


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
                    raise TemplateBundleError(
                        f"canonical hook command is invalid: {event}"
                    )
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
    return (
        json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _codex_skill_frontmatter(content: bytes, skill: str) -> bytes:
    """Reuse the generated shim's plugin discovery metadata, not its source link."""
    match = re.match(rb"\A---\r?\n.*?\r?\n---\r?\n", content, re.DOTALL)
    if match is None:
        raise TemplateBundleError(
            f"generated Codex skill frontmatter is invalid: {skill}"
        )
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
) -> tuple[dict[str, bytes], dict[str, str], list[dict[str, str]]]:
    """Build the one source-free Codex package from existing canonical views."""
    payload: dict[str, bytes] = {}
    payload_modes: dict[str, str] = {}
    install_files: list[dict[str, str]] = []
    root_guidance: bytes | None = None
    skill_frontmatter: dict[str, bytes] = {}
    canonical_skills: dict[str, bytes] = {}
    source_paths = {path for path, _ in entries}
    if CODEX_USER_MANIFEST in source_paths:
        raise TemplateBundleError(
            f"Codex generated path collides with source: {CODEX_USER_MANIFEST}"
        )

    def project(path: str, content: bytes, mode: str = "100644") -> None:
        if path in source_paths or path in payload:
            raise TemplateBundleError(
                f"Codex generated path collides with source: {path}"
            )
        payload[path] = content
        payload_modes[path] = mode

    for source_path, mode in entries:
        if mode not in {"100644", "100755"}:
            raise TemplateBundleError(
                f"Codex bundle source is not a regular file: {source_path}"
            )
        content = _blob(root, commit, source_path)
        # Preserve source-relative resources alongside the generated Codex views.
        payload[source_path] = content
        payload_modes[source_path] = mode
        if source_path == "ROOT_AGENTS.md":
            root_guidance = content
            continue
        if source_path == ".codex/hooks.json":
            project("hooks/hooks.json", _codex_user_hook_configuration(root, commit))
            continue
        if source_path.startswith(".codex/agents/"):
            filename = source_path.rsplit("/", 1)[-1]
            if source_path.count("/") != 2 or not filename.endswith(".toml"):
                raise TemplateBundleError(
                    "Codex bundle agent source is not a direct TOML child"
                )
            destination = f"agents/agent-canon-{filename}"
            project(destination, content, mode)
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
                raise TemplateBundleError(
                    "Codex skill materialization is not one-file scoped"
                )
            skill = parts[0]
            if skill in skill_frontmatter:
                raise TemplateBundleError(f"Codex skill view is duplicated: {skill}")
            skill_frontmatter[skill] = _codex_skill_frontmatter(content, skill)
            continue
        if source_path.startswith("agents/skills/") and source_path.endswith(".md"):
            skill = source_path.rsplit("/", 1)[-1][:-3]
            if skill in skill_frontmatter:
                canonical_skills[skill] = content
    if set(skill_frontmatter) != set(canonical_skills):
        raise TemplateBundleError("Codex skill views and canonical owners differ")
    for skill, frontmatter in sorted(skill_frontmatter.items()):
        destination = f"skills/{skill}/SKILL.md"
        project(
            destination,
            frontmatter
            + b"\n"
            + _codex_skill_body(
                f"agents/skills/{skill}.md", destination, canonical_skills[skill]
            ),
        )

    if root_guidance is None:
        raise TemplateBundleError("portable common ROOT_AGENTS.md is missing")
    # Reuse the canonical root composer, with an empty consumer-owned layer:
    # user bundle guidance contains only the portable common base.
    project(
        "guidance/AGENTS.md",
        Composition(source_commit=commit, base=root_guidance, specific=b"").render(),
    )
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
    project(
        "plugin.json",
        (
            json.dumps(plugin, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode(),
    )
    marketplace = {
        "name": "agent-canon-user-bundle",
        "plugins": [
            {
                "name": "agent-canon",
                "source": {"source": "local", "path": "./"},
                "interface": {"displayName": "AgentCanon"},
            }
        ],
    }
    project(
        CODEX_MARKETPLACE,
        (
            json.dumps(marketplace, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode(),
    )
    for path in payload:
        payload_modes.setdefault(path, "100644")
    install_files.sort(key=lambda item: (item["destination"], item["bundle_path"]))
    return payload, payload_modes, install_files


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
            json.dumps(
                record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            + b"\0"
        )
    return digest.hexdigest()


def bundle_identity(root: Path, source_ref: str, profile: str) -> dict[str, Any]:
    """Return source-bound identity without writing an output directory."""
    root = root.resolve()
    commit = _commit(root, source_ref)
    manifest, manifest_digest = _manifest(root, commit)
    profile_record = manifest["profiles"].get(profile)
    if not isinstance(profile_record, dict) or not isinstance(
        profile_record.get("roots"), list
    ):
        raise TemplateBundleError(f"unknown template profile: {profile}")
    roots = [str(item) for item in profile_record["roots"]]
    digest = hashlib.sha256()
    digest.update(str(manifest["version"]).encode())
    digest.update(b"\0" + profile.encode() + b"\0" + manifest_digest.encode() + b"\0")
    entries = _entries(root, commit, roots)
    if profile == CODEX_USER_PROFILE:
        entries = _codex_user_entries(root, commit, entries)
    for path, mode in entries:
        content = _blob(root, commit, path)
        digest.update(path.encode() + b"\0" + mode.encode() + b"\0")
        digest.update(hashlib.sha256(content).digest() + b"\0")
    source_bundle_digest = digest.hexdigest()
    if profile == CODEX_USER_PROFILE:
        payload, _payload_modes, install_files = _codex_user_payload(
            root, commit, entries
        )
        source_tree = (
            _git(root, "rev-parse", "--verify", f"{commit}^{{tree}}").decode().strip()
        )
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


def export_bundle(
    *, source_root: Path, source_ref: str, profile: str, output: Path
) -> dict[str, Any]:
    """Export one profile without touching source or consumer repositories."""
    source_root = source_root.resolve()
    output = output if output.is_absolute() else Path.cwd() / output
    resolved_output = output.resolve(strict=False)
    if resolved_output == source_root or source_root in resolved_output.parents:
        raise TemplateBundleError("output must be outside AgentCanon source")
    # The dispatcher prepares an empty artifact root before invoking producers.
    # Existing content and symlinks remain outside this export's write authority.
    if output.is_symlink() or (
        output.exists() and (not output.is_dir() or any(output.iterdir()))
    ):
        raise TemplateBundleError("output must be a fresh directory")
    if profile == "static-seed":
        raise TemplateBundleError("static-seed uses export_static_seed.py")
    identity = bundle_identity(source_root, source_ref, profile)
    output.mkdir(parents=True, exist_ok=True)
    if profile == CODEX_USER_PROFILE:
        entries = _entries(
            source_root,
            identity["source_commit"],
            [
                str(item)
                for item in _manifest(source_root, identity["source_commit"])[0][
                    "profiles"
                ][profile]["roots"]
            ],
        )
        entries = _codex_user_entries(source_root, identity["source_commit"], entries)
        payload, payload_modes, install_files = _codex_user_payload(
            source_root, identity["source_commit"], entries
        )
        for path, content in sorted(payload.items()):
            destination = _bundle_destination(output, path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(content)
            if payload_modes[path] == "100755":
                destination.chmod(0o755)
        bundle_manifest = _codex_user_manifest(identity, payload, install_files)
        with (output / CODEX_USER_MANIFEST).open("x", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    bundle_manifest, ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n"
            )
        return {**identity, "output": str(output)}
    for path in identity["paths"]:
        destination = _bundle_destination(output, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(_blob(source_root, identity["source_commit"], path))
    provenance = {**identity, "output": str(output)}
    with (output / "template-bundle-provenance.json").open(
        "x", encoding="utf-8"
    ) as stream:
        stream.write(
            json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return provenance


def _native_package_output(output: Path, source_root: Path) -> Path:
    output = output if output.is_absolute() else Path.cwd() / output
    resolved = output.resolve(strict=False)
    if resolved == source_root or source_root in resolved.parents:
        raise TemplateBundleError(
            "native package output must be outside AgentCanon source"
        )
    if output.is_symlink() or (
        output.exists() and (not output.is_dir() or any(output.iterdir()))
    ):
        raise TemplateBundleError("native package output must be a fresh directory")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _native_tar_bytes(root_name: str, payload: dict[str, tuple[bytes, int]]) -> bytes:
    """Build a timestamp-stable gzip tar package from relative payload paths."""
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
        ) as archive,
    ):
        for relative, (content, mode) in sorted(payload.items()):
            info = tarfile.TarInfo(f"{root_name}/{relative}")
            info.size = len(content)
            info.mode = mode
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _native_zip_bytes(root_name: str, payload: dict[str, tuple[bytes, int]]) -> bytes:
    """Build a stable zip package with Unix executable bits preserved."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative, (content, mode) in sorted(payload.items()):
            info = zipfile.ZipInfo(
                f"{root_name}/{relative}", date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def _native_version(source_root: Path, commit: str) -> str:
    try:
        cargo = tomllib.loads(
            _blob(source_root, commit, NATIVE_CLI_CARGO_MANIFEST).decode("utf-8")
        )
        version = cargo["package"]["version"]
    except (KeyError, UnicodeDecodeError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise TemplateBundleError(
            "native CLI Cargo package version is invalid"
        ) from exc
    if not isinstance(version, str) or not PACKAGE_COMPONENT.fullmatch(version):
        raise TemplateBundleError("native CLI Cargo package version is invalid")
    return version


def package_native_cli(
    *,
    source_root: Path,
    source_ref: str,
    binary: Path,
    target: str,
    output: Path,
    toolchain: str,
) -> dict[str, Any]:
    """Package the native executable and its declared optional adapter resource."""
    source_root = source_root.resolve()
    if binary.is_symlink() or not binary.is_file():
        raise TemplateBundleError("native executable must be a regular file")
    binary = binary.resolve(strict=True)
    if not PACKAGE_COMPONENT.fullmatch(target):
        raise TemplateBundleError("native target is invalid")
    commit = _commit(source_root, source_ref)
    manifest, manifest_digest = _manifest(source_root, commit)
    profile = manifest["profiles"].get(NATIVE_CLI_PROFILE)
    if not isinstance(profile, dict) or not isinstance(profile.get("roots"), list):
        raise TemplateBundleError("native CLI package profile is missing")
    entries = _entries(source_root, commit, [str(item) for item in profile["roots"]])
    if any(mode not in {"100644", "100755"} for _path, mode in entries):
        raise TemplateBundleError("native CLI resources must be regular files")
    layout = profile.get("layout")
    if not isinstance(layout, dict) or set(layout) != {path for path, _mode in entries}:
        raise TemplateBundleError(
            "native CLI package layout must cover its declared resources"
        )
    package_paths: dict[str, bytes] = {}
    for source, destination in layout.items():
        try:
            relative = _bundle_relative(destination).as_posix()
        except TemplateBundleError as exc:
            raise TemplateBundleError(
                "native CLI package layout contains an unsafe path"
            ) from exc
        if relative in package_paths:
            raise TemplateBundleError(
                "native CLI package layout contains duplicate destinations"
            )
        package_paths[relative] = _blob(source_root, commit, source)

    version = _native_version(source_root, commit)

    binary_name = (
        "agent-canon.exe" if target.endswith("-windows-msvc") else "agent-canon"
    )
    package_paths[f"bin/{binary_name}"] = binary.read_bytes()
    modes = {path: 0o644 for path in package_paths}
    modes[f"bin/{binary_name}"] = 0o755
    provenance = {
        "schema": NATIVE_CLI_SCHEMA,
        "version": version,
        "target": target,
        "source_commit": commit,
        "source_tree": _git(source_root, "rev-parse", "--verify", f"{commit}^{{tree}}")
        .decode()
        .strip(),
        "manifest_digest": manifest_digest,
        "toolchain": toolchain,
        "files": [
            {"path": path, "sha256": hashlib.sha256(content).hexdigest()}
            for path, content in sorted(package_paths.items())
        ],
    }
    package_paths["share/agent-canon/provenance.json"] = (
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    modes["share/agent-canon/provenance.json"] = 0o644
    checksums = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {path}\n"
        for path, content in sorted(package_paths.items())
    )
    package_paths["share/agent-canon/SHA256SUMS"] = checksums.encode("ascii")
    modes["share/agent-canon/SHA256SUMS"] = 0o644
    payload = {path: (content, modes[path]) for path, content in package_paths.items()}

    output = _native_package_output(output, source_root)
    root_name = f"agent-canon-{version}-{target}"
    archives: list[dict[str, str]] = []
    for suffix, content in (
        ("tar.gz", _native_tar_bytes(root_name, payload)),
        ("zip", _native_zip_bytes(root_name, payload)),
    ):
        archive_path = output / f"{root_name}.{suffix}"
        with archive_path.open("xb") as stream:
            stream.write(content)
        checksum = hashlib.sha256(content).hexdigest()
        checksum_path = archive_path.with_name(f"{archive_path.name}.sha256")
        with checksum_path.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(f"{checksum}  {archive_path.name}\n")
        archives.append({"path": str(archive_path), "sha256": checksum})
    return {**provenance, "output": str(output), "archives": archives}


def _native_archive_payload(path: Path, prefix: str) -> dict[str, bytes]:
    """Read regular archive members without extracting them onto the filesystem."""
    payload: dict[str, bytes] = {}

    def add(name: str, content: bytes) -> None:
        if not name.startswith(prefix + "/"):
            raise TemplateBundleError("native archive root differs")
        relative = name[len(prefix) + 1 :]
        _bundle_relative(relative)
        if relative in payload:
            raise TemplateBundleError("native archive contains duplicate members")
        payload[relative] = content

    try:
        if path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        raise TemplateBundleError(
                            "native archive member is not regular"
                        )
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise TemplateBundleError("native archive member is unreadable")
                    add(member.name, stream.read())
        else:
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if stat.S_IFMT(member.external_attr >> 16) != stat.S_IFREG:
                        raise TemplateBundleError(
                            "native archive member is not regular"
                        )
                    add(member.filename, archive.read(member))
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise TemplateBundleError(f"native archive is unreadable: {path.name}") from exc
    return payload


def verify_native_packages(
    *, source_root: Path, source_ref: str, root: Path, targets: list[str]
) -> dict[str, Any]:
    """Verify the exact source-bound native release set before publication."""
    source_root = source_root.resolve()
    commit = _commit(source_root, source_ref)
    tree = _git(source_root, "rev-parse", f"{commit}^{{tree}}").decode().strip()
    manifest, manifest_digest = _manifest(source_root, commit)
    version = _native_version(source_root, commit)
    if (
        not targets
        or len(set(targets)) != len(targets)
        or any(not PACKAGE_COMPONENT.fullmatch(target) for target in targets)
    ):
        raise TemplateBundleError("native release targets are invalid")
    expected = {
        f"agent-canon-{version}-{target}.{suffix}"
        for target in targets
        for suffix in ("tar.gz", "tar.gz.sha256", "zip", "zip.sha256")
    }
    if root.is_symlink() or not root.is_dir():
        raise TemplateBundleError("native package directory is missing or unsafe")
    paths = list(root.iterdir())
    if {path.name for path in paths} != expected or any(
        path.is_symlink() or not path.is_file() for path in paths
    ):
        raise TemplateBundleError("native release file set differs")
    resources = {
        destination: _blob(source_root, commit, source)
        for source, destination in manifest["profiles"][NATIVE_CLI_PROFILE][
            "layout"
        ].items()
    }
    provenance_path = "share/agent-canon/provenance.json"
    sums_path = "share/agent-canon/SHA256SUMS"
    records: list[dict[str, Any]] = []
    try:
        for target in sorted(targets):
            prefix = f"agent-canon-{version}-{target}"
            binary = (
                "bin/agent-canon.exe"
                if target.endswith("-windows-msvc")
                else "bin/agent-canon"
            )
            previous: dict[str, bytes] | None = None
            for suffix in ("tar.gz", "zip"):
                path = root / f"{prefix}.{suffix}"
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                sidecar = path.with_name(path.name + ".sha256")
                if sidecar.read_text(encoding="ascii") != f"{digest}  {path.name}\n":
                    raise TemplateBundleError("native archive checksum differs")
                payload = _native_archive_payload(path, prefix)
                if set(payload) != {*resources, binary, provenance_path, sums_path}:
                    raise TemplateBundleError("native archive resource set differs")
                if any(payload[name] != content for name, content in resources.items()):
                    raise TemplateBundleError(
                        "native archive resource differs from source"
                    )
                provenance = json.loads(payload[provenance_path])
                identity = {
                    "schema": NATIVE_CLI_SCHEMA,
                    "version": version,
                    "target": target,
                    "source_commit": commit,
                    "source_tree": tree,
                    "manifest_digest": manifest_digest,
                }
                if not isinstance(provenance, dict) or any(
                    provenance.get(key) != value for key, value in identity.items()
                ):
                    raise TemplateBundleError("native archive source identity differs")
                hashes = {
                    name: hashlib.sha256(data).hexdigest()
                    for name, data in payload.items()
                }
                expected_sums = "".join(
                    f"{hashes[name]}  {name}\n"
                    for name in sorted(payload)
                    if name != sums_path
                )
                if payload[sums_path].decode("ascii") != expected_sums:
                    raise TemplateBundleError("native resource checksum differs")
                if provenance.get("files") != [
                    {"path": name, "sha256": hashes[name]}
                    for name in sorted(payload)
                    if name not in {provenance_path, sums_path}
                ]:
                    raise TemplateBundleError("native provenance file digests differ")
                if previous is not None and payload != previous:
                    raise TemplateBundleError(
                        "native archive formats contain different payloads"
                    )
                previous = payload
                for artifact in (path, sidecar):
                    records.append(
                        {
                            "path": artifact.name,
                            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                            "size": artifact.stat().st_size,
                        }
                    )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise TemplateBundleError("native release metadata is unreadable") from exc
    return {
        "schema": "agent-canon.native-release.v1",
        "source_commit": commit,
        "source_tree": tree,
        "version": version,
        "targets": sorted(targets),
        "files": sorted(records, key=lambda item: item["path"]),
    }


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
        relative = _bundle_relative(row["path"]).as_posix()
        sha256 = row["sha256"]
        if (
            not isinstance(sha256, str)
            or not HEX_64.fullmatch(sha256)
            or relative <= previous
        ):
            raise TemplateBundleError(
                "Codex user bundle file path or digest is invalid"
            )
        previous = relative
        current = root
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise TemplateBundleError("Codex user bundle contains a symlink")
        candidate = _bundle_destination(root, relative)
        if not candidate.is_file():
            raise TemplateBundleError(f"Codex user bundle file is missing: {relative}")
        content = candidate.read_bytes()
        if hashlib.sha256(content).hexdigest() != sha256:
            raise TemplateBundleError(
                f"Codex user bundle file digest differs: {relative}"
            )
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
        CODEX_MARKETPLACE,
        "skills/agent-canon-bootstrap/SKILL.md",
        "guidance/AGENTS.md",
    }
    if not required_paths.issubset(payload):
        raise TemplateBundleError("Codex user bundle is missing required runtime files")

    normalized_installs: list[dict[str, str]] = []
    seen_destinations: set[str] = set()
    for row in installs:
        if not isinstance(row, dict) or set(row) != {
            "component",
            "bundle_path",
            "destination",
        }:
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
            raise TemplateBundleError(
                "Codex user bundle guidance destination is invalid"
            )
        seen_destinations.add(destination)
        normalized_installs.append(
            {
                "component": component,
                "bundle_path": bundle_path,
                "destination": destination,
            }
        )
    normalized_installs.sort(
        key=lambda item: (item["destination"], item["bundle_path"])
    )
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
    native = sub.add_parser("native-package")
    native.add_argument("--source-root", required=True)
    native.add_argument("--source-ref", required=True)
    native.add_argument("--binary", required=True)
    native.add_argument("--target", required=True)
    native.add_argument("--output", required=True)
    native.add_argument("--toolchain", default="")
    native_verify = sub.add_parser("native-verify")
    native_verify.add_argument("--source-root", required=True)
    native_verify.add_argument("--source-ref", required=True)
    native_verify.add_argument("--root", required=True)
    native_verify.add_argument("--target", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "verify":
            result = verify_codex_user_bundle(Path(args.root))
        elif args.operation == "native-verify":
            result = verify_native_packages(
                source_root=Path(args.source_root),
                source_ref=args.source_ref,
                root=Path(args.root),
                targets=args.target,
            )
        elif args.operation == "export":
            result = export_bundle(
                source_root=Path(args.source_root),
                source_ref=args.source_ref,
                profile=args.profile,
                output=Path(args.output),
            )
        else:
            result = package_native_cli(
                source_root=Path(args.source_root),
                source_ref=args.source_ref,
                binary=Path(args.binary),
                target=args.target,
                output=Path(args.output),
                toolchain=args.toolchain,
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
