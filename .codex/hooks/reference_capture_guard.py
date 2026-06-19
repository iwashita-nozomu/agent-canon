#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Logs and blocks unregistered external reference URLs.
# upstream implementation ../hooks.json invokes this hook at prompt, tool, and stop boundaries.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream implementation ../../tools/agent_tools/reference_materializer.py materializes PDF/HTML references as Markdown.
# upstream design ../../references/README.md defines reference capture policy.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates reference hook behavior.
# @dependency-end
"""Guard external references so consulted URLs are materialized under references/."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from hook_event_log import HookLogContext, fingerprint_json, utc_now

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_REFERENCE_CAPTURE_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
DISABLE_BLOCK_ENV = "AGENT_CANON_REFERENCE_CAPTURE_WARN_ONLY"
GIT_ROOT_TIMEOUT_SECONDS = 5
MAX_REASON_URLS = 5
URL_RE = re.compile(r"https?://[^\s<>'\"\]\)]+")
TEXT_FIELDS = ("prompt", "last_assistant_message", "message", "tool_input", "command", "cmd")
OPERATIONAL_GITHUB_PARTS = {"/pull/", "/issues/", "/actions/", "/commit/", "/compare/"}


@dataclass(frozen=True)
class ReferenceObservation:
    """URLs observed in one hook payload."""

    urls: tuple[str, ...]
    source_fields: tuple[str, ...]

    def has_urls(self) -> bool:
        """Return whether URLs were observed."""
        return bool(self.urls)


@dataclass(frozen=True)
class ReferenceCoverage:
    """Reference registration status for observed URLs."""

    registered_urls: tuple[str, ...]
    missing_urls: tuple[str, ...]
    reference_files: tuple[str, ...]

    def should_block(self, event: str) -> bool:
        """Return whether this hook event should block on missing references."""
        if os.environ.get(DISABLE_BLOCK_ENV, "").strip() in {"1", "true", "yes"}:
            return False
        return event in {"PostToolUse", "Stop"} and bool(self.missing_urls)


@dataclass(frozen=True)
class ReferenceDocument:
    """One Markdown reference document loaded for URL matching."""

    path: str
    text: str


def load_payload() -> dict[str, object]:
    """Read one Codex hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_EMPTY}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_INVALID_JSON}
    if isinstance(loaded, dict):
        loaded[PAYLOAD_STATUS_KEY] = PAYLOAD_STATUS_VALID
        return loaded
    return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_INVALID_JSON}


def payload_status(payload: dict[str, object]) -> str:
    """Return how the hook payload was parsed."""
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


def repo_root() -> Path:
    """Resolve the active Git repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) and value else "UnknownHookEvent"


def tool_name(payload: dict[str, object]) -> str:
    """Return the invoked tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def nested_texts(value: object) -> tuple[str, ...]:
    """Return text leaves from nested hook payload values."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(text for child in value.values() for text in nested_texts(child))
    if isinstance(value, list):
        return tuple(text for child in value for text in nested_texts(child))
    return ()


def observed_text_by_field(payload: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return observed text grouped by payload field."""
    return {
        field: nested_texts(payload[field])
        for field in TEXT_FIELDS
        if field in payload and nested_texts(payload[field])
    }


def normalize_url(raw_url: str) -> str:
    """Return a URL without trailing prose punctuation."""
    return raw_url.rstrip(".,;:")


def is_operational_url(url: str) -> bool:
    """Return whether a URL is PR/CI plumbing rather than a cited source."""
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return False
    path = f"{parsed.path}/"
    return any(part in path for part in OPERATIONAL_GITHUB_PARTS)


def extract_urls(texts: Iterable[str]) -> tuple[str, ...]:
    """Return sorted unique source-like URLs from text."""
    urls = {
        normalize_url(match.group(0))
        for text in texts
        for match in URL_RE.finditer(text)
    }
    return tuple(sorted(url for url in urls if not is_operational_url(url)))


def reference_observation(payload: dict[str, object]) -> ReferenceObservation:
    """Return observed URLs and the fields they came from."""
    by_field = observed_text_by_field(payload)
    urls = extract_urls(text for texts in by_field.values() for text in texts)
    source_fields = tuple(field for field, texts in by_field.items() if extract_urls(texts))
    return ReferenceObservation(urls=urls, source_fields=source_fields)


def reference_files(root: Path) -> tuple[Path, ...]:
    """Return Markdown reference files for the active repository."""
    directory = root / "references"
    if not directory.is_dir():
        return ()
    return tuple(sorted(path for path in directory.rglob("*.md") if path.is_file()))


def reference_documents(root: Path) -> tuple[ReferenceDocument, ...]:
    """Load Markdown reference documents for the active repository."""
    documents: list[ReferenceDocument] = []
    for path in reference_files(root):
        documents.append(
            ReferenceDocument(
                path=path.relative_to(root).as_posix(),
                text=path.read_text(encoding="utf-8", errors="replace"),
            )
        )
    return tuple(documents)


def registered_url_files(root: Path, urls: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Return reference files containing each URL."""
    return match_registered_urls(reference_documents(root), urls)


def match_registered_urls(
    documents: tuple[ReferenceDocument, ...],
    urls: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Return reference files containing each URL."""
    return {
        url: tuple(document.path for document in documents if url in document.text)
        for url in urls
    }


def reference_coverage(root: Path, observation: ReferenceObservation) -> ReferenceCoverage:
    """Return registration coverage for observed URLs."""
    files_by_url = registered_url_files(root, observation.urls)
    registered = tuple(url for url, paths in files_by_url.items() if paths)
    missing = tuple(url for url, paths in files_by_url.items() if not paths)
    files = tuple(sorted({path for paths in files_by_url.values() for path in paths}))
    return ReferenceCoverage(
        registered_urls=registered,
        missing_urls=missing,
        reference_files=files,
    )


def append_reference_log(
    root: Path,
    payload: dict[str, object],
    observation: ReferenceObservation,
    coverage: ReferenceCoverage,
) -> None:
    """Append one reference-capture hook log entry."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip() == "1":
        return
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    event = hook_event_name(payload)
    context = HookLogContext(
        active_root=root,
        hook_name="reference_capture_guard",
        override_path=os.environ.get(LOG_PATH_ENV, "").strip(),
    )
    context.append(
        {
            "timestamp": timestamp,
            "hook_run_id": context.run_id(timestamp, payload_fingerprint),
            "hook_log_namespace": context.runtime_namespace(),
            "payload_fingerprint": payload_fingerprint,
            "payload_status": payload_status(payload),
            "event": event,
            "tool_name": tool_name(payload),
            "root": str(root),
            "url_count": len(observation.urls),
            "urls": list(observation.urls),
            "source_fields": list(observation.source_fields),
            "source_field_count": len(observation.source_fields),
            "registered_urls": list(coverage.registered_urls),
            "registered_count": len(coverage.registered_urls),
            "missing_urls": list(coverage.missing_urls),
            "missing_count": len(coverage.missing_urls),
            "reference_files": list(coverage.reference_files),
            "reference_file_count": len(coverage.reference_files),
            "decision": "block" if coverage.should_block(event) else "pass",
            "status": "fail" if coverage.should_block(event) else "pass",
        }
    )


def block_payload(missing_urls: tuple[str, ...]) -> dict[str, object]:
    """Return a Codex blocking payload for missing reference registrations."""
    shown = "\n".join(f"- {url}" for url in missing_urls[:MAX_REASON_URLS])
    return {
        "decision": "block",
        "reason": (
            "Reference capture guard saw external source URLs that are not "
            "registered under references/. Materialize PDF or HTML sources as "
            "Markdown before continuing, for example:\n"
            "python3 tools/agent_tools/reference_materializer.py --url <url> "
            "--input <downloaded.pdf-or.html>\n"
            f"{shown}"
        ).strip(),
        "next_action": "materialize_external_references_then_retry",
        "remediation": [
            "Download or capture the referenced PDF/HTML source.",
            "Run `python3 tools/agent_tools/reference_materializer.py --url <url> --input <downloaded.pdf-or-html>`.",
            "Commit the resulting references/ Markdown artifact or cite an existing registered reference.",
        ],
    }


def main() -> int:
    """Run the reference capture guard."""
    payload = load_payload()
    observation = reference_observation(payload)
    if not observation.has_urls():
        return 0
    root = repo_root()
    coverage = reference_coverage(root, observation)
    append_reference_log(root, payload, observation, coverage)
    if coverage.should_block(hook_event_name(payload)):
        json.dump(block_payload(coverage.missing_urls), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
