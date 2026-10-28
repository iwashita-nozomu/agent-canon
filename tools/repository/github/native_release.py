# @dependency-start
# contract implementation
# responsibility Publishes verified native archives through resumable GitHub draft releases.
# upstream implementation ../../agent/templates/template_bundle.py verifies native release inputs
# upstream implementation github_publish.py owns the configured gh command runner
# downstream implementation ../../../.github/workflows/agent-canon-native-release.yml release caller
# downstream implementation ../../../tests/agent_tools/test_native_release.py integrity and recovery checks
# @dependency-end
"""Publish a complete source-bound native release without replacing existing assets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.agent.templates.template_bundle import (
    TemplateBundleError,
    verify_native_packages,
)
from tools.repository.github.github_publish import (
    Runner,
    subprocess_runner,
)


class NativeReleaseError(RuntimeError):
    """Release state cannot safely advance with the supplied artifacts."""


def select_native_artifacts(
    artifacts: list[dict[str, Any]],
    targets: list[str],
) -> list[dict[str, Any]]:
    """Select each target's latest retained successful upload across run attempts."""
    selected: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if artifact["expired"]:
            continue
        for target in targets:
            prefix = f"agent-canon-native-{target}-attempt-"
            attempt = artifact["name"].removeprefix(prefix)
            if not artifact["name"].startswith(prefix) or not attempt.isdigit():
                continue
            number = int(attempt)
            if target not in selected or number > selected[target]["attempt"]:
                selected[target] = {
                    "target": target,
                    "attempt": number,
                    "artifact_id": artifact["id"],
                }
    missing = sorted(set(targets) - set(selected))
    if missing:
        raise NativeReleaseError(
            f"native CI artifacts are missing or expired: {missing}"
        )
    return [selected[target] for target in targets]


def _api(
    runner: Runner, endpoint: str, *, optional: bool = False
) -> dict[str, Any] | None:
    result = runner(["gh", "api", "--include", endpoint])
    headers, separator, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    status = re.match(r"HTTP/\S+ (\d+)", headers)
    if not separator or status is None:
        raise NativeReleaseError("gh did not return an HTTP response")
    code = int(status[1])
    if optional and code == 404:
        return None
    if result.returncode or code != 200:
        raise NativeReleaseError(
            f"GitHub read failed with HTTP {code}: {result.stderr.strip()}"
        )
    value = json.loads(body)
    if not isinstance(value, dict):
        raise NativeReleaseError("GitHub returned invalid release metadata")
    return value


def _tag_commit(runner: Runner, repo: str, tag: str) -> str | None:
    value = _api(
        runner, f"repos/{repo}/git/ref/tags/{quote(tag, safe='')}", optional=True
    )
    if value is None:
        return None
    obj = value["object"]
    while obj["type"] == "tag":
        annotated = _api(runner, f"repos/{repo}/git/tags/{obj['sha']}")
        if annotated is None:
            raise NativeReleaseError("annotated tag metadata is missing")
        obj = annotated["object"]
    if obj["type"] != "commit":
        raise NativeReleaseError("release tag does not resolve to a commit")
    return str(obj["sha"])


def _missing_assets(
    release: dict[str, Any], expected: dict[str, dict[str, Any]]
) -> list[str]:
    assets = {item["name"]: item for item in release["assets"]}
    if release["draft"] and set(assets) - set(expected):
        raise NativeReleaseError(
            "draft contains unrelated assets; preserved without publication"
        )
    for name in set(assets) & set(expected):
        actual, wanted = assets[name], expected[name]
        if (
            actual["state"] != "uploaded"
            or actual["size"] != wanted["size"]
            or actual.get("digest") != "sha256:" + wanted["sha256"]
        ):
            raise NativeReleaseError(f"existing release asset differs: {name}")
    return sorted(set(expected) - set(assets))


def _validate_release(
    release: dict[str, Any],
    expected: dict[str, dict[str, Any]],
    tag: str,
    commit: str,
) -> list[str]:
    if release["tag_name"] != tag or release["prerelease"]:
        raise NativeReleaseError(
            "existing release does not match the stable release request"
        )
    if release["draft"] and release["target_commitish"] != commit:
        raise NativeReleaseError("draft is not bound to the requested source commit")
    return _missing_assets(release, expected)


def publish_native_release(
    *,
    source_root: Path,
    source_ref: str,
    artifacts: Path,
    targets: list[str],
    repo: str,
    tag: str,
    runner: Runner = subprocess_runner,
    check_only: bool = False,
) -> dict[str, Any]:
    identity = verify_native_packages(
        source_root=source_root,
        source_ref=source_ref,
        root=artifacts,
        targets=targets,
    )
    if tag != "v" + identity["version"]:
        raise NativeReleaseError("release tag must match the Cargo version")
    commit = identity["source_commit"]
    endpoint = f"repos/{repo}/releases/tags/{quote(tag, safe='')}"
    expected = {item["path"]: item for item in identity["files"]}
    recovered: list[dict[str, str]] = []
    tagged = _tag_commit(runner, repo, tag)
    if tagged is not None and tagged != commit:
        raise NativeReleaseError("release tag points to a different source commit")
    release = _api(runner, endpoint, optional=True)
    if release is not None:
        missing = _validate_release(release, expected, tag, commit)
        if not release["draft"]:
            if tagged != commit or missing:
                raise NativeReleaseError(
                    "published release is incomplete or has a different source"
                )
            return {
                **identity,
                "status": "already-published",
                "url": release["html_url"],
            }
    else:
        missing = sorted(expected)
    if check_only:
        return {**identity, "status": "checked", "missing_assets": missing}
    if release is None:
        notes = (
            f"Native CLI {identity['version']}: archives and SHA256 sidecars for "
            f"{', '.join(targets)}. Extract the matching archive and add bin/ to PATH. "
            f"Source and command dependencies: https://github.com/{repo}/blob/{commit}/README.md"
            "#native-cli-distribution"
        )
        created = runner(
            [
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                repo,
                "--draft",
                "--target",
                commit,
                "--title",
                f"AgentCanon {tag}",
                "--notes",
                notes,
            ]
        )
        release = _api(runner, endpoint, optional=True)
        if release is None:
            raise NativeReleaseError(
                f"draft creation did not complete: {created.stderr.strip()}"
            )
        # Read back an ambiguous creation before issuing another mutation.
        if not release["draft"] or release["target_commitish"] != commit:
            raise NativeReleaseError("new draft does not match the requested source")
        missing = _validate_release(release, expected, tag, commit)
        if created.returncode:
            recovered.append({"operation": "create", "error": created.stderr.strip()})
    if missing:
        uploaded = runner(
            [
                "gh",
                "release",
                "upload",
                tag,
                "--repo",
                repo,
                *[str(artifacts / name) for name in missing],
            ]
        )
        release = _api(runner, endpoint)
        if release is None:
            raise NativeReleaseError("draft disappeared after upload")
        missing = _validate_release(release, expected, tag, commit)
        if missing:
            raise NativeReleaseError(
                f"upload incomplete; rerun the failed publication job to resume {missing}: "
                f"{uploaded.stderr.strip()}"
            )
        if uploaded.returncode:
            recovered.append({"operation": "upload", "error": uploaded.stderr.strip()})
    # A stable release becomes visible only after every expected asset is verified.
    tagged = _tag_commit(runner, repo, tag)
    if tagged is not None and tagged != commit:
        raise NativeReleaseError("release tag changed before publication")
    publish_error = ""
    if release["draft"]:
        published = runner(
            ["gh", "release", "edit", tag, "--repo", repo, "--draft=false"]
        )
        publish_error = published.stderr.strip()
        if published.returncode:
            recovered.append({"operation": "publish", "error": publish_error})
    release = _api(runner, endpoint)
    if release is None or release["draft"]:
        raise NativeReleaseError(
            f"release publication did not complete: {publish_error}"
        )
    if _tag_commit(runner, repo, tag) != commit or _validate_release(
        release, expected, tag, commit
    ):
        raise NativeReleaseError("published release readback differs")
    return {
        **identity,
        "status": "published",
        "url": release["html_url"],
        "recovered_operations": recovered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--target", action="append", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = publish_native_release(
            source_root=args.source_root,
            source_ref=args.source_ref,
            artifacts=args.artifacts,
            targets=args.target,
            repo=args.repo,
            tag=args.tag,
            check_only=args.check_only,
        )
    except (
        TemplateBundleError,
        NativeReleaseError,
        KeyError,
        ValueError,
        OSError,
    ) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
