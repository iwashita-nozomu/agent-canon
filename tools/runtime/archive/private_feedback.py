#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns private feedback/knowledge production and the body-free request/read boundary; the host shell owns archive publication.
# upstream design ../../../documents/runtime/private-feedback-knowledge.md private feedback command and storage contract
# downstream implementation ../dispatch/agent-canon/src/private_feedback.rs exposes the Rust CLI route
# downstream implementation ../../../tests/agent_tools/test_private_feedback.py validates the bounded adapter
# @dependency-end
"""Private feedback and reusable knowledge adapter.

The adapter deliberately keeps prose in an external runtime spool or the
private ``agent-canon-log`` checkout.  Normal command output is metadata only;
``read --show`` is the explicit opt-in path for displaying the private body.
The public AgentCanon source tree, public skill catalog, and ordinary runtime
logs are never used as a knowledge store.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA = "agent-canon.private-feedback.v1"
PRIVATE_SPOOL_NAME = "private-feedback"
PRIVATE_SKILLS_DIR = "private-skills"
SYNC_REQUEST_NAME = "sync-request.json"
SYNC_REQUEST_SCHEMA = "agent-canon.private-feedback-sync-request.v1"
SECRET_PATTERN = re.compile(
    r"(?is)(?:\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b\s*[:=]\s*\S+|"
    r"\bBearer\s+\S+|-----BEGIN (?:OPENSSH|RSA|EC|PRIVATE) KEY-----)"
)
TOPIC_PATTERN = re.compile(r"[^a-z0-9]+")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PrivateFeedbackError(RuntimeError):
    """Typed private feedback failure; body is never included in the message."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def topic_slug(value: str) -> str:
    value = value.strip().lower()
    slug = TOPIC_PATTERN.sub("-", value).strip("-")
    if not slug or len(slug) > 96:
        raise PrivateFeedbackError("topic_invalid", "topic must be lowercase ASCII and non-empty")
    return slug


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_commit(source_root: Path | None = None) -> str:
    configured = os.environ.get("AGENT_CANON_SOURCE_COMMIT", "").strip()
    if configured and re.fullmatch(r"[0-9a-f]{40,64}", configured):
        return configured
    root = source_root or Path.cwd()
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _runtime_root(value: str | None) -> Path:
    raw = value or os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
    if not raw:
        raise PrivateFeedbackError("runtime_root_required", "pass --runtime-root or set AGENT_CANON_RUNTIME_ROOT")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise PrivateFeedbackError("runtime_root_invalid", "runtime root must be absolute")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _log_root(value: str | None) -> Path:
    raw = value or os.environ.get("AGENT_CANON_LOG_ROOT", "").strip()
    if not raw:
        parent = os.environ.get("AGENT_CANON_CONTROL_PARENT_ROOT", "").strip()
        if not parent:
            raise PrivateFeedbackError(
                "log_root_required",
                "pass --log-root or set AGENT_CANON_LOG_ROOT/AGENT_CANON_CONTROL_PARENT_ROOT",
            )
        raw = str(Path(parent) / "agent-canon-log")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise PrivateFeedbackError("log_root_invalid", "private log root must be absolute")
    return path.resolve()


def _spool_root(runtime: Path) -> Path:
    path = runtime / "spool" / PRIVATE_SPOOL_NAME
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


@contextmanager
def _private_feedback_spool_lock(spool: Path) -> Iterator[None]:
    """Serialize spool mutations with the host's exact-snapshot cleanup."""
    lock_path = spool.parent / ".private-feedback.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _sync_request_path(spool: Path) -> Path:
    """Return the credential-free request exchanged with the host adapter."""
    return spool / SYNC_REQUEST_NAME


def _valid_sync_request(request: object) -> bool:
    return (
        isinstance(request, dict)
        and request.get("schema") == SYNC_REQUEST_SCHEMA
        and request.get("operation") == "sync"
        and request.get("execution_plane") == "agentcanon_tool_container"
    )


def _read_sync_request(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PrivateFeedbackError("sync_request_invalid", "private feedback sync request is invalid")
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrivateFeedbackError("sync_request_invalid", "private feedback sync request is invalid") from exc
    if not _valid_sync_request(request):
        raise PrivateFeedbackError("sync_request_invalid", "private feedback sync request schema is invalid")
    return request


def _ensure_sync_request(runtime: Path) -> bool:
    """Create or reuse the one body-free host publication request.

    Capture is complete only after this request exists.  Keeping the helper
    behind the spool boundary makes both explicit ``sync`` and automatic
    capture use the same idempotency record without copying private prose into
    the request.
    """
    spool = _spool_root(runtime)
    request_path = _sync_request_path(spool)
    if request_path.exists() or request_path.is_symlink():
        _read_sync_request(request_path)
        return True
    request = {
        "schema": SYNC_REQUEST_SCHEMA,
        "operation": "sync",
        "execution_plane": "agentcanon_tool_container",
        "requested_at": _now(),
        "source_commit": _source_commit(),
    }
    _write_once(
        request_path,
        json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
    )
    return False


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise PrivateFeedbackError("locator_invalid", "locator must be a controlled relative path")
    return path


def _sensitive(body: str) -> bool:
    return bool(SECRET_PATTERN.search(body))


def _body(args: argparse.Namespace) -> tuple[str, str]:
    if bool(args.stdin) == bool(args.text):
        raise PrivateFeedbackError("input_required", "provide direct prose or --stdin, exactly once")
    if args.stdin:
        value = sys.stdin.read()
        mode = "stdin"
    else:
        value = " ".join(args.text).strip()
        mode = "text"
    if not value.strip() or "\x00" in value:
        raise PrivateFeedbackError("body_invalid", "body must be non-empty UTF-8 text")
    if _sensitive(value):
        raise PrivateFeedbackError("private_data_rejected", "credential-shaped or private payload is not accepted")
    return value.rstrip() + "\n", mode


def _scope(args: argparse.Namespace) -> tuple[str, str, str]:
    run = str(args.run or os.environ.get("AGENT_CANON_RUN_ID", "")).strip()
    task = str(args.task or os.environ.get("AGENT_CANON_TASK_ID", "")).strip()
    scope = task or run
    return run, task, scope


def _metadata(
    *, kind: str, topic: str, locator: str, digest: str, run: str, task: str,
    input_mode: str, status: str, source_commit: str,
) -> dict[str, str]:
    return {
        "schema": SCHEMA,
        "kind": kind,
        "topic": topic,
        "locator": locator,
        "content_digest": f"sha256:{digest}",
        "source_commit": source_commit,
        "run": run,
        "task": task,
        "input_mode": input_mode,
        "status": status,
    }


def _frontmatter(meta: dict[str, str], body: str) -> str:
    fields = {
        "kind": meta["kind"],
        "topic": meta["topic"],
        "source_locator": meta["locator"],
        "source_digest": meta["content_digest"],
        "run": meta["run"],
        "input_mode": meta["input_mode"],
        "status": meta["status"],
    }
    lines = ["---"] + [f"{key}: {value}" for key, value in fields.items()] + ["---", "", body.rstrip(), ""]
    return "\n".join(lines)


def _json_meta(meta: dict[str, str]) -> None:
    print(json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise PrivateFeedbackError("content_conflict", f"existing private record differs: {path.name}")
        return
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _candidate_locator(topic: str) -> Path:
    return Path("knowledge") / "topics" / topic / "candidate.md"


def _record_path(kind: str, topic: str, digest: str, spool: Path) -> Path:
    if kind == "feedback":
        return spool / "feedback" / topic / f"{digest[:16]}.md"
    return spool / _candidate_locator(topic)


def _pending_paths(spool: Path) -> Iterable[Path]:
    for family in ("feedback", "knowledge", "runtime", PRIVATE_SKILLS_DIR):
        root = spool / family
        if root.is_dir():
            yield from (path for path in root.rglob("*") if path.is_file())


def _receipt_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _receipt_metadata(topic: str, digest: str, run: str, task: str, source_commit: str) -> str:
    return "\n".join(
        [
            "## Read receipt",
            "kind: knowledge-read-receipt",
            f"topic: {topic}",
            f"candidate_locator: {_candidate_locator(topic).as_posix()}",
            f"candidate_digest: sha256:{digest}",
            "reader: agent-canon",
            f"read_at: {_now()}",
            f"run: {run}",
            f"task: {task}",
            f"source_commit: {source_commit}",
            "result: read",
            "",
        ]
    )


def _distinct_scopes(text: str) -> set[str]:
    scopes: set[str] = set()
    run = ""
    task = ""
    for line in text.splitlines() + ["## Read receipt"]:
        if line.startswith("run:"):
            run = line.split(":", 1)[1].strip()
        elif line.startswith("task:"):
            task = line.split(":", 1)[1].strip()
        elif line == "## Read receipt":
            if task:
                scopes.add(f"task:{task}")
            elif run:
                scopes.add(f"run:{run}")
            run = ""
            task = ""
    return scopes


def _skill_content(topic: str, body: str, digest: str, scopes: set[str]) -> str:
    return "\n".join(
        [
            "---",
            "kind: skill-candidate",
            f"topic: {topic}",
            f"source_locator: {_candidate_locator(topic).as_posix()}",
            f"source_digest: sha256:{digest}",
            "run: private-feedback-promotion",
            "input_mode: structured-log",
            "status: candidate",
            "---",
            "",
            f"# {topic}",
            "",
            body.rstrip(),
            "",
            "## Evidence",
            "",
            "Repeated private reads in distinct task/run scopes:",
            *[f"- {scope}" for scope in sorted(scopes)],
            "",
            "## Use and limits",
            "",
            "Use only for the private runtime context represented by the source feedback.",
            "This candidate is not public AgentCanon policy and is not approval or proof.",
            "",
        ]
    )


def _source_candidate(log_root: Path, spool: Path, topic: str) -> tuple[Path | None, Path]:
    relative = _candidate_locator(topic)
    for root in (log_root, spool):
        path = root / relative
        if path.is_file() and not path.is_symlink():
            return path, relative
    return None, relative


def add(args: argparse.Namespace, kind: str) -> int:
    body, input_mode = _body(args)
    topic = topic_slug(args.topic)
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    run, task, _ = _scope(args)
    digest = _sha256(body.encode("utf-8"))
    locator = (
        f"feedback/{topic}/{digest[:16]}.md"
        if kind == "feedback"
        else _candidate_locator(topic).as_posix()
    )
    meta = _metadata(
        kind=kind,
        topic=topic,
        locator=locator,
        digest=digest,
        run=run,
        task=task,
        input_mode=input_mode,
        status="observed" if kind == "feedback" else "candidate",
        source_commit=_source_commit(),
    )
    path = _record_path(kind, topic, digest, spool)
    with _private_feedback_spool_lock(spool):
        _write_once(path, _frontmatter(meta, body))
        request_reused = _ensure_sync_request(runtime)
    meta["status"] = "spooled"
    meta["sync_request"] = "reused" if request_reused else "created"
    _json_meta(meta)
    return 0


def read(args: argparse.Namespace) -> int:
    topic = topic_slug(args.topic)
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    log_root = _log_root(args.log_root)
    with _private_feedback_spool_lock(spool):
        candidate, relative = _source_candidate(log_root, spool, topic)
        if candidate is None:
            raise PrivateFeedbackError("knowledge_not_found", "private knowledge candidate is unavailable")
        content = candidate.read_text(encoding="utf-8")
        body = content.split("---", 2)[-1].strip() if content.startswith("---") else content.strip()
        digest = _sha256(body.encode("utf-8"))
        run, task, scope = _scope(args)
        source_commit = _source_commit()
        receipt_path = spool / "knowledge" / "topics" / topic / "read-receipt.md"
        old = receipt_path.read_text(encoding="utf-8") if receipt_path.exists() else ""
        duplicate = bool(scope) and (f"task: {task}" in old if task else f"run: {run}" in old)
        receipt = _receipt_metadata(topic, digest, run, task, source_commit)
        if not duplicate:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("a", encoding="utf-8") as handle:
                if old and not old.endswith("\n"):
                    handle.write("\n")
                handle.write(receipt)
        scopes = _distinct_scopes(old + ("\n" + receipt if not duplicate else ""))
        promoted = False
        if len(scopes) >= 2:
            skill_path = spool / "runtime" / "skills" / topic / "SKILL.md"
            _write_once(skill_path, _skill_content(topic, body, digest, scopes))
            private_root = runtime / PRIVATE_SKILLS_DIR / topic
            _write_once(private_root / "SKILL.md", _skill_content(topic, body, digest, scopes))
            promoted = True
        meta = _metadata(
            kind="knowledge-read-receipt", topic=topic,
            locator=relative.as_posix(), digest=digest, run=run, task=task,
            input_mode="read", status="duplicate" if duplicate else "read",
            source_commit=source_commit,
        )
        meta["promotion"] = "private-skill-candidate" if promoted else "none"
        _json_meta(meta)
        if args.show:
            print(body)
        return 0


def _git(path: Path, argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", "-C", str(path), *argv], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "git command failed"
        raise PrivateFeedbackError("git_failed", detail[:240])
    return result


def sync_request(args: argparse.Namespace) -> int:
    """Request host publication without touching a Git checkout.

    This function runs in the tool container.  Bodies remain in the external
    writable spool and the request itself contains no body, credentials, or
    host checkout path.  The host bootstrap consumes it after the container
    command returns.
    """
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    # A valid request is the idempotency key. Repeated k/f sync commands share
    # it and never rewrite requested_at or invent another request.
    with _private_feedback_spool_lock(spool):
        reused = _ensure_sync_request(runtime)
    _json_meta(
        {
            "schema": SCHEMA,
            "status": "requested",
            "execution_plane": "agentcanon_tool_container",
            "request": "private-feedback-sync",
            "request_reused": "yes" if reused else "no",
        }
    )
    return 0


def status(args: argparse.Namespace) -> int:
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    log_root = _log_root(args.log_root)
    pending = [path.relative_to(spool).as_posix() for path in _pending_paths(spool)]
    payload: dict[str, str] = {"schema": SCHEMA, "status": "pending" if pending else "clean", "pending": str(len(pending)), "log_root": str(log_root)}
    if log_root.exists():
        payload.update({"branch": _git(log_root, ["branch", "--show-current"], check=False).stdout.strip(), "remote": _git(log_root, ["remote", "get-url", "origin"], check=False).stdout.strip()})
    _json_meta(payload)
    return 0


def capture(args: argparse.Namespace) -> int:
    # Structured runtime feedback is intentionally short and metadata-like.
    body, input_mode = _body(args)
    if len(body.encode("utf-8")) > 16 * 1024:
        raise PrivateFeedbackError("capture_too_large", "structured capture exceeds 16 KiB")
    args.text = [body]
    args.stdin = False
    return add(args, "feedback")


def capture_runtime_feedback(
    entry: str,
    *,
    runtime_root: Path | str,
    run: str = "",
    task: str = "",
) -> dict[str, str]:
    """Capture one structured closeout/runtime feedback event automatically.

    This path accepts only the already-structured feedback event.  It never
    receives a transcript, tool output, or raw dataset and returns metadata
    without the event body.
    """
    if len(entry.encode("utf-8")) > 16 * 1024 or _sensitive(entry):
        raise PrivateFeedbackError("private_data_rejected", "structured feedback is not a permitted private payload")
    runtime = _runtime_root(str(runtime_root))
    spool = _spool_root(runtime)
    topic = "runtime-feedback"
    body = entry.strip() + "\n"
    digest = _sha256(body.encode("utf-8"))
    meta = _metadata(
        kind="feedback",
        topic=topic,
        locator=f"feedback/{topic}/{digest[:16]}.md",
        digest=digest,
        run=run,
        task=task,
        input_mode="structured-log",
        status="observed",
        source_commit=_source_commit(),
    )
    with _private_feedback_spool_lock(spool):
        _write_once(spool / "feedback" / topic / f"{digest[:16]}.md", _frontmatter(meta, body))
        request_reused = _ensure_sync_request(runtime)
    meta["sync_request"] = "reused" if request_reused else "created"
    return meta


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Private AgentCanon feedback and knowledge route")
    parser.add_argument("--runtime-root")
    parser.add_argument("--log-root")
    parser.add_argument("--run", default="")
    parser.add_argument("--task", default="")
    sub = parser.add_subparsers(dest="family", required=True)
    for family in ("knowledge", "k", "feedback", "f"):
        family_parser = sub.add_parser(family)
        family_sub = family_parser.add_subparsers(dest="operation", required=True)
        if family in {"knowledge", "k"}:
            search_parser = family_sub.add_parser("search")
            search_parser.add_argument("--query", default="")
            for operation in ("status", "sync"):
                family_sub.add_parser(operation)
            read_parser = family_sub.add_parser("read")
            read_parser.add_argument("topic")
            read_parser.add_argument("--show", action="store_true")
            add_parser = family_sub.add_parser("add")
            add_parser.add_argument("topic")
            add_parser.add_argument("text", nargs="*")
            add_parser.add_argument("--stdin", action="store_true")
            capture_parser = family_sub.add_parser("capture")
            capture_parser.add_argument("text", nargs="*")
            capture_parser.add_argument("--stdin", action="store_true")
        else:
            add_parser = family_sub.add_parser("add")
            add_parser.add_argument("topic")
            add_parser.add_argument("text", nargs="*")
            add_parser.add_argument("--stdin", action="store_true")
            family_sub.add_parser("status")
            family_sub.add_parser("sync")
            capture_parser = family_sub.add_parser("capture")
            capture_parser.add_argument("text", nargs="*")
            capture_parser.add_argument("--stdin", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # Keep the short command ergonomic: scope/runtime options are accepted
    # both before and after the family operation.
    leading: list[str] = []
    remaining: list[str] = []
    index = 0
    global_options = {"--runtime-root", "--log-root", "--run", "--task"}
    while index < len(raw):
        if raw[index] in global_options and index + 1 < len(raw):
            leading.extend(raw[index : index + 2])
            index += 2
        else:
            remaining.append(raw[index])
            index += 1
    args = build_parser().parse_args(leading + remaining)
    family = str(args.family)
    operation = str(args.operation)
    if operation == "add":
        return add(args, "knowledge" if family in {"knowledge", "k"} else "feedback")
    if operation == "read":
        return read(args)
    if operation == "sync":
        return sync_request(args)
    if operation == "status":
        return status(args)
    if operation == "capture":
        return capture(args)
    if operation == "search":
        # Search is metadata-only and deliberately bounded to the private clone/spool.
        runtime = _runtime_root(args.runtime_root)
        spool = _spool_root(runtime)
        query = str(getattr(args, "query", "")).strip().lower()
        log_root = _log_root(args.log_root)
        roots = [spool / "knowledge", spool / "feedback", log_root / "knowledge", log_root / "feedback"]
        results: list[dict[str, str]] = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*.md"):
                relative = path.relative_to(spool if path.is_relative_to(spool) else log_root).as_posix()
                if query and query not in relative.lower():
                    continue
                data = path.read_bytes()
                results.append({"locator": relative, "content_digest": f"sha256:{_sha256(data)}", "status": "spooled"})
        print(json.dumps({"schema": SCHEMA, "status": "ok", "results": results}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    raise PrivateFeedbackError("operation_invalid", operation)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PrivateFeedbackError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "error", "code": exc.code, "detail": exc.detail}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
