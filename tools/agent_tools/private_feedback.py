#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the private feedback/knowledge spool adapter and the
# metadata-only promotion/readback boundary for agent-canon-log.
# upstream design ../../documents/runtime/private-feedback-knowledge.md
# upstream external-schema git@github.com:iwashita-nozomu/agent-canon-log.git@db3722b817be8574c682949db733df0fb5c2674a
# downstream implementation ../../rust/agent-canon/src/private_feedback.rs exposes the Rust CLI route
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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .log_repository_identity import stable_log_branch
except ImportError:  # pragma: no cover - direct script execution
    from log_repository_identity import stable_log_branch

SCHEMA = "agent-canon.private-feedback.v1"
LOG_REMOTE = "git@github.com:iwashita-nozomu/agent-canon-log.git"
LOG_MAIN_COMMIT = "db3722b817be8574c682949db733df0fb5c2674a"
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
REMOTE_NORMALIZE = re.compile(r"\.git$")


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


def _remote(value: str) -> str:
    return REMOTE_NORMALIZE.sub("", value.strip().rstrip("/"))


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


def _source_root(value: str | None) -> Path:
    raw = value or os.environ.get("AGENT_CANON_SOURCE_ROOT", "").strip()
    path = Path(raw).expanduser() if raw else Path.cwd()
    if not path.is_absolute():
        raise PrivateFeedbackError("source_root_invalid", "source root must be absolute")
    return path.resolve()


def _spool_root(runtime: Path) -> Path:
    path = runtime / "spool" / PRIVATE_SPOOL_NAME
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


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


def _runtime_archive_module() -> Any:
    """Load the existing archive branch resolver in package or script mode."""
    try:
        from . import runtime_log_archive_git

        return runtime_log_archive_git
    except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct script execution
        tools_root = str(Path(__file__).resolve().parent)
        if tools_root not in sys.path:
            sys.path.insert(0, tools_root)
        import runtime_log_archive_git

        return runtime_log_archive_git


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
            f"kind: knowledge-read-receipt",
            f"topic: {topic}",
            f"candidate_locator: {_candidate_locator(topic).as_posix()}",
            f"candidate_digest: sha256:{digest}",
            f"reader: agent-canon",
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
    _write_once(path, _frontmatter(meta, body))
    meta["status"] = "spooled"
    _json_meta(meta)
    return 0


def read(args: argparse.Namespace) -> int:
    topic = topic_slug(args.topic)
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    log_root = _log_root(args.log_root)
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


def ensure_clone(
    log_root: Path,
    remote: str = LOG_REMOTE,
    *,
    source_root: Path | None = None,
    runtime_root: Path | None = None,
) -> dict[str, str]:
    """Ensure the operational clone uses the canonical source-qualified branch."""
    source = (source_root or Path.cwd()).resolve()
    expected_branch = stable_log_branch(source)
    log_root.parent.mkdir(parents=True, exist_ok=True)
    if log_root.exists() and log_root.is_symlink():
        raise PrivateFeedbackError("log_clone_invalid", "private log root is a symlink")
    if log_root.exists() and not log_root.is_dir():
        raise PrivateFeedbackError("log_clone_invalid", "private log root is not a directory")
    if log_root.exists() and not (log_root / ".git").exists() and any(log_root.iterdir()):
        raise PrivateFeedbackError("log_clone_invalid", "private log root is not an empty checkout directory")
    if log_root.exists() and not (log_root / ".git").exists() and not any(log_root.iterdir()):
        # runtime_log_archive_git owns clone creation; hand it a non-existent
        # path while preserving the exact empty directory contract.
        log_root.rmdir()
    if (log_root / ".git").exists():
        configured = _git(log_root, ["remote", "get-url", "origin"]).stdout.strip()
        if _remote(configured) != _remote(remote):
            raise PrivateFeedbackError("log_remote_mismatch", "private log remote is not the configured exact remote")
    runtime_archive_git = _runtime_archive_module()
    context = runtime_archive_git.build_context(
        argparse.Namespace(
            canon_root=source,
            source_root=source,
            archive_root=log_root,
            runtime_root=runtime_root,
            remote=remote,
        )
    )
    if context.branch != expected_branch:
        raise PrivateFeedbackError("log_branch_invalid", "runtime archive branch resolver returned an unexpected branch")
    try:
        runtime_archive_git.ensure_archive(context, fetch=True, allow_branch_switch=True)
    except Exception as exc:
        detail = str(exc)
        if "local changes" in detail or "dirty" in detail:
            raise PrivateFeedbackError("log_clone_dirty", "private log checkout has retained local changes") from exc
        raise PrivateFeedbackError("git_failed", detail[:240]) from exc
    if not (log_root / ".git").exists():
        raise PrivateFeedbackError("log_clone_invalid", "private log root is not a Git checkout")
    log_root.chmod(0o700)
    configured = _git(log_root, ["remote", "get-url", "origin"]).stdout.strip()
    if _remote(configured) != _remote(remote):
        raise PrivateFeedbackError("log_remote_mismatch", "private log remote is not the configured exact remote")
    branch = _git(log_root, ["branch", "--show-current"]).stdout.strip()
    if branch != expected_branch:
        raise PrivateFeedbackError("log_branch_invalid", "private log checkout is not on the source-qualified stable branch")
    origin_branch = f"origin/{expected_branch}"
    origin_head = _git(log_root, ["rev-parse", origin_branch], check=False).stdout.strip()
    return {
        "root": str(log_root),
        "remote": configured,
        "branch": expected_branch,
        "head": _git(log_root, ["rev-parse", "HEAD"]).stdout.strip(),
        "origin_head": origin_head,
        "mode": oct(log_root.stat().st_mode & 0o777),
    }


def _legacy_runtime_clone(runtime: Path) -> Path:
    """Return the old archive clone location without creating or deleting it."""
    return runtime / "archive" / "agent-canon-log"


def _copy_pending(spool: Path, log_root: Path) -> list[Path]:
    copied: list[Path] = []
    for source in _pending_paths(spool):
        relative = source.relative_to(spool)
        if relative.parts and relative.parts[0] == "raw":
            continue
        target = log_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise PrivateFeedbackError("content_conflict", f"private log target differs: {relative.as_posix()}")
        if not target.exists():
            shutil.copyfile(source, target)
        copied.append(relative)
    return copied


def _raw_pending(spool: Path) -> bool:
    raw = spool / "raw"
    return raw.is_dir() and any(path.is_file() for path in raw.rglob("*"))


def _annex_special_remote_available(log_root: Path) -> bool:
    """Probe git-annex without reading or emitting remote configuration."""
    version = _git(log_root, ["annex", "version"], check=False)
    if version.returncode != 0:
        return False
    info = _git(log_root, ["annex", "info", "--json"], check=False)
    if info.returncode != 0:
        return False
    try:
        payload = json.loads(info.stdout)
    except json.JSONDecodeError:
        return False
    remotes = payload.get("trusted repositories") if isinstance(payload, dict) else None
    return isinstance(remotes, list) and len(remotes) > 1


def _copy_raw_for_annex(spool: Path, log_root: Path) -> list[Path]:
    copied: list[Path] = []
    root = spool / "raw"
    for source in (path for path in root.rglob("*") if path.is_file()):
        relative = source.relative_to(spool)
        target = log_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_symlink():
            copied.append(relative)
            continue
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise PrivateFeedbackError("content_conflict", f"raw annex target differs: {relative.as_posix()}")
        if not target.exists():
            shutil.copyfile(source, target)
        copied.append(relative)
    if copied:
        _git(log_root, ["annex", "add", "--", *[path.as_posix() for path in copied]])
        _git(log_root, ["annex", "sync", "--no-content"])
    return copied


def sync_request(args: argparse.Namespace) -> int:
    """Request host publication without touching a Git checkout.

    This function runs in the tool container.  Bodies remain in the external
    writable spool and the request itself contains no body, credentials, or
    host checkout path.  The host bootstrap consumes it after the container
    command returns.
    """
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    request_path = _sync_request_path(spool)
    reused = request_path.exists() or request_path.is_symlink()
    if reused:
        # A valid request is the idempotency key.  Repeated k/f sync commands
        # share it and never rewrite requested_at or invent another request.
        _read_sync_request(request_path)
    else:
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


def host_sync(args: argparse.Namespace) -> int:
    """Consume one container request and publish it from the host plane."""
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    request_path = _sync_request_path(spool)
    if not request_path.is_file() or request_path.is_symlink():
        raise PrivateFeedbackError("sync_request_missing", "private feedback sync request is unavailable")
    _read_sync_request(request_path)
    log_root = _log_root(args.log_root)
    remote = str(args.remote or os.environ.get("AGENT_CANON_LOG_REMOTE", LOG_REMOTE))
    source_root = _source_root(args.source_root)
    legacy = _legacy_runtime_clone(runtime)
    migration = "not-needed"
    if not log_root.exists() and legacy.is_dir() and (legacy / ".git").exists():
        # Read the old clone's remote head before creating the operational
        # checkout.  The old clone is retained; bootstrap owns its later
        # removal only after the new clone has published and read back.
        old_remote_head = _git(legacy, ["rev-parse", f"origin/{stable_log_branch(source_root)}"], check=False).stdout.strip()
        if old_remote_head:
            migration = "legacy-readback-observed"
    info = ensure_clone(log_root, remote, source_root=source_root, runtime_root=runtime)
    branch = info["branch"]
    expected = info["origin_head"]
    pending_raw = _raw_pending(spool)
    annex_raw: list[Path] = []
    if pending_raw and _annex_special_remote_available(log_root):
        annex_raw = _copy_raw_for_annex(spool, log_root)
        pending_raw = False
    normal_copied = _copy_pending(spool, log_root)
    copied = normal_copied + annex_raw
    if pending_raw:
        meta = {"schema": SCHEMA, "status": "pending", "execution_plane": "host_archive_adapter", "reason": "annex-special-remote-required", "clone": str(log_root), "branch": branch, "copied": len(copied), "migration": migration}
        _json_meta({k: str(v) for k, v in meta.items()})
        return 1
    if normal_copied:
        _git(log_root, ["add", "--", *[path.as_posix() for path in normal_copied]])
    staged = _git(log_root, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode != 0:
        _git(log_root, ["commit", "-m", "Append private feedback and knowledge"])
    current = _git(log_root, ["rev-parse", "HEAD"]).stdout.strip()
    if current != expected:
        push = _git(log_root, ["push", "origin", f"HEAD:refs/heads/{branch}"], check=False)
        if push.returncode != 0:
            raise PrivateFeedbackError("sync_conflict", "private log remote changed; local spool and clone retained")
    _git(log_root, ["fetch", "--no-tags", "origin", branch])
    remote_head = _git(log_root, ["rev-parse", f"origin/{branch}"]).stdout.strip()
    remote_tree = _git(log_root, ["rev-parse", f"origin/{branch}^{{tree}}"]).stdout.strip()
    if copied and remote_head != current:
        raise PrivateFeedbackError("sync_readback_failed", "private log remote head readback differs")
    for relative in copied:
        source = spool / relative
        if source.exists():
            source.unlink()
    for directory in sorted((path for path in spool.rglob("*") if path.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if directory != spool:
            try:
                directory.rmdir()
            except OSError:
                pass
    request_path.unlink()
    _json_meta({"schema": SCHEMA, "status": "synced", "execution_plane": "host_archive_adapter", "clone": str(log_root), "branch": branch, "commit": remote_head, "tree": remote_tree, "copied": str(len(copied)), "migration": migration})
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
    _write_once(spool / "feedback" / topic / f"{digest[:16]}.md", _frontmatter(meta, body))
    return meta


def migrate_memory(args: argparse.Namespace) -> int:
    source = Path(args.root).resolve()
    records = source / "memory" / "records"
    if not records.is_dir():
        raise PrivateFeedbackError("memory_root_missing", "memory/records is unavailable")
    runtime = _runtime_root(args.runtime_root)
    spool = _spool_root(runtime)
    count = 0
    for record in sorted(records.glob("*.md")):
        topic = topic_slug(record.stem.replace("--", "-"))
        body = record.read_text(encoding="utf-8")
        if _sensitive(body):
            continue
        digest = _sha256(body.encode("utf-8"))
        meta = _metadata(kind="knowledge-candidate", topic=topic, locator=_candidate_locator(topic).as_posix(), digest=digest, run="memory-migration", task="", input_mode="structured-log", status="candidate", source_commit=_source_commit(source))
        _write_once(spool / _candidate_locator(topic), _frontmatter(meta, body))
        count += 1
    _json_meta({"schema": SCHEMA, "status": "spooled", "migration": "memory", "records": str(count), "source": str(source)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Private AgentCanon feedback and knowledge route")
    parser.add_argument("--runtime-root")
    parser.add_argument("--log-root")
    parser.add_argument("--source-root")
    parser.add_argument("--run", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--remote", default="")
    sub = parser.add_subparsers(dest="family", required=True)
    sub.add_parser("host-sync")
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
            migrate = family_sub.add_parser("migrate-memory")
            migrate.add_argument("--root", required=True)
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
    global_options = {"--runtime-root", "--log-root", "--source-root", "--run", "--task", "--remote"}
    while index < len(raw):
        if raw[index] in global_options and index + 1 < len(raw):
            leading.extend(raw[index : index + 2])
            index += 2
        else:
            remaining.append(raw[index])
            index += 1
    args = build_parser().parse_args(leading + remaining)
    family = str(args.family)
    if family == "host-sync":
        return host_sync(args)
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
    if operation == "migrate-memory":
        return migrate_memory(args)
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
