#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs one-shot LSP 3.17 code analysis and emits deterministic code facts.
# upstream design ../../documents/structured-analysis/code-analysis.md code-analysis boundary
# upstream design ../../documents/tools/lsp_code_analysis.md LSP adapter contract
# upstream implementation ./vector_search.py owns bounded LSP discovery and language mapping
# downstream implementation ../../tests/agent_tools/test_lsp_code_analysis.py verifies protocol and report behavior
# downstream implementation ./search.py consumes in-memory code-deps facts
# @dependency-end
"""Small, dependency-free LSP 3.17 code-analysis adapter.

The adapter intentionally owns only a single analysis request.  It does not
maintain an index or discover servers from the host PATH: callers provide an
exact command (or use the language map installed by the devcontainer
manifest).  The wire implementation is deliberately boring so fake servers
can exercise it in unit tests.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import select
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.agent_tools import vector_search

SCHEMA_VERSION = "agent-canon.lsp-code-analysis.v1"
LSP_VERSION = "3.17"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_FRAME_BYTES = 16 * 1024 * 1024
DEFAULT_STDERR_BYTES = 64 * 1024
DEFAULT_MAX_HEADER_BYTES = 64 * 1024
IMAGE_RECEIPT_ROOT = Path(
    "/usr/local/share/agent-canon/image-dependencies/receipts"
)


class LspAnalysisError(RuntimeError):
    """Base class for typed analysis failures."""

    error_code = "analysis-error"


class ServerUnavailable(LspAnalysisError):
    """The exact language server could not be started."""

    error_code = "server-unavailable"


class ProtocolViolation(LspAnalysisError):
    """The server violated JSON-RPC framing or response semantics."""

    error_code = "protocol-violation"


class RequestTimeout(LspAnalysisError):
    """A server request exceeded its bounded timeout."""

    error_code = "request-timeout"


class MalformedResponse(LspAnalysisError):
    """The server returned a malformed LSP payload or fact."""

    error_code = "malformed-response"


class CapabilityUnavailable(LspAnalysisError):
    """A required LSP capability was not advertised."""

    error_code = "capability-unavailable"


class PathEscape(LspAnalysisError):
    """A server location escaped the requested analysis root."""

    error_code = "path-escape"


class NoPartialFacts(LspAnalysisError):
    """A required fact failed after a partial response was observed."""

    error_code = "NoPartialFacts"


class ServerExitNonzero(LspAnalysisError):
    """The language server exited with a non-zero status."""

    error_code = "server-exit-nonzero"


LANGUAGE_COMMANDS: Mapping[str, tuple[str, ...]] = {
    "python": ("pyright-langserver", "--stdio"),
    "c": ("clangd-18",),
    "cpp": ("clangd-18",),
    "shellscript": ("bash-language-server", "start"),
    "rust": ("rust-analyzer",),
}
LANGUAGE_RECORDS: Mapping[str, str] = {
    "python": "pyright-language-server",
    "c": "clangd-language-server",
    "cpp": "clangd-language-server",
    "shellscript": "bash-language-server",
    "rust": "rust-toolchain",
}


def _position(value: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise MalformedResponse("position must be an object")
    line = value.get("line")
    character = value.get("character")
    if (
        not isinstance(line, int)
        or isinstance(line, bool)
        or not isinstance(character, int)
        or isinstance(character, bool)
        or line < 0
        or character < 0
    ):
        raise MalformedResponse("invalid UTF-16 position")
    return {"line": line, "character": character}


def _range(value: Mapping[str, Any] | None) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        raise MalformedResponse("range must be an object")
    start = _position(value.get("start"))
    end = _position(value.get("end"))
    if (end["line"], end["character"]) < (start["line"], start["character"]):
        raise MalformedResponse("range end precedes range start")
    return {"start": start, "end": end}


def _uri_path(root: Path, uri: str) -> str:
    """Normalize an LSP URI to a root-relative POSIX locator."""
    from urllib.parse import unquote, urlparse

    parsed = urlparse(uri)
    if parsed.scheme not in ("", "file"):
        return f"external:unknown:{uri}"
    raw = unquote(parsed.path if parsed.scheme else uri)
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        relative = path.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise PathEscape(f"URI outside analysis root: {uri}") from exc
    return PurePosixPath(relative.as_posix()).as_posix()


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _sort_key(item: Mapping[str, Any]) -> tuple[str, str, int, int]:
    location = item.get("range") or item.get("selection_range") or {}
    start = location.get("start", {}) if isinstance(location, Mapping) else {}
    return (
        str(item.get("uri", item.get("path", ""))),
        str(item.get("name", item.get("source", ""))),
        int(start.get("line", 0)),
        int(start.get("character", 0)),
    )


@dataclass(frozen=True)
class LspServerSpec:
    """Exact executable metadata for one language server."""

    language_id: str
    command: tuple[str, ...]
    record_id: str = ""
    version: str = ""
    executable: str = ""
    resolution: str = "manifest"
    verification_output: str = ""

    def __post_init__(self) -> None:
        """Reject an empty command before any process is created."""
        if not self.command:
            raise ValueError("LspServerSpec.command must not be empty")

    @classmethod
    def for_language(
        cls,
        language_id: str,
        *,
        root: Path | None = None,
        vendor_root: Path | None = None,
        receipts: Path | None = None,
    ) -> LspServerSpec:
        """Resolve a manifest executable through its verified receipt."""
        command = LANGUAGE_COMMANDS.get(language_id)
        if command is None:
            raise ServerUnavailable(f"no manifest server for language {language_id}")
        if root is None:
            raise ServerUnavailable("manifest executable resolution requires an analysis root")
        try:
            repo_root = Path(__file__).resolve().parents[2]
            if str(repo_root) not in sys.path:
                sys.path.insert(0, str(repo_root))
            from tools.agent_tools.devcontainer_dependencies import (
                DependencyError,
                resolve_verified_executable,
            )
        except ImportError as exc:  # pragma: no cover - direct isolated invocation
            raise ServerUnavailable("manifest dependency resolver is unavailable") from exc
        workspace = root.resolve()
        vendor = vendor_root or (workspace / "vendor" / "agent-canon")
        if receipts is not None:
            receipt_root = receipts
        elif IMAGE_RECEIPT_ROOT.is_dir():
            receipt_root = IMAGE_RECEIPT_ROOT
        else:
            receipt_root = workspace / ".agent-canon" / "dependency-receipts"
        try:
            verified = resolve_verified_executable(
                workspace,
                vendor if vendor.is_dir() else None,
                receipt_root,
                LANGUAGE_RECORDS[language_id],
                command[0],
            )
        except (DependencyError, OSError, ValueError) as exc:
            raise ServerUnavailable(
                f"manifest executable verification failed for {language_id}: {exc}"
            ) from exc
        return cls(
            language_id=language_id,
            command=(verified.absolute_path, *command[1:]),
            record_id=LANGUAGE_RECORDS[language_id],
            version=verified.manifest_version,
            executable=verified.absolute_path,
            verification_output=verified.verification_output,
        )

    def as_json(self) -> dict[str, Any]:
        """Return stable machine-readable server metadata."""
        return {
            "languageId": self.language_id,
            "record": self.record_id,
            "command": list(self.command),
            "version": self.version,
            "executable": self.executable or self.command[0],
            "resolution": self.resolution,
            "verificationOutput": self.verification_output,
        }


@dataclass(frozen=True)
class LspCapabilityMatrix:
    """Required and optional capability coverage for one server."""

    document_symbols: str = "unsupported"
    definitions: str = "unsupported"
    references: str = "unsupported"
    call_hierarchy: str = "unsupported"
    diagnostics: str = "unsupported"

    def as_json(self) -> dict[str, str]:
        """Return capability states using the canonical coverage vocabulary."""
        return {
            "documentSymbolProvider": self.document_symbols,
            "definitionProvider": self.definitions,
            "referencesProvider": self.references,
            "callHierarchyProvider": self.call_hierarchy,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_initialize(cls, capabilities: Mapping[str, Any]) -> LspCapabilityMatrix:
        """Normalize initialize capabilities without fabricating support."""
        def coverage(name: str, *, required: bool = False) -> str:
            value = capabilities.get(name)
            if value:
                return "supported_facts"
            return "unsupported" if not required else "unsupported"

        diagnostics = "supported_facts" if capabilities.get("diagnosticProvider") else "unsupported"
        return cls(
            document_symbols=coverage("documentSymbolProvider", required=True),
            definitions=coverage("definitionProvider"),
            references=coverage("referencesProvider"),
            call_hierarchy=coverage("callHierarchyProvider"),
            diagnostics=diagnostics,
        )


@dataclass(frozen=True)
class CodeSymbol:
    """Normalized document symbol with UTF-16 ranges."""

    uri: str
    name: str
    kind: int | str
    range: Mapping[str, Any]
    selection_range: Mapping[str, Any]
    container: str | None = None

    def as_json(self, root: Path) -> dict[str, Any]:
        """Serialize a symbol with a root-relative URI locator."""
        return {
            "uri": _uri_path(root, self.uri),
            "name": self.name,
            "kind": self.kind,
            "range": dict(self.range),
            "selectionRange": dict(self.selection_range),
            "container": self.container,
            "encoding": "utf-16",
        }


@dataclass(frozen=True)
class CodeRelation:
    """Explicitly oriented definition, reference, or call relation."""

    orientation: str
    source: str
    target: str
    position: Mapping[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        """Serialize a relation while retaining its orientation."""
        return {
            "orientation": self.orientation,
            "source": self.source,
            "target": self.target,
            "position": dict(self.position) if self.position else None,
            "encoding": "utf-16",
        }


@dataclass(frozen=True)
class CodeDiagnostic:
    """Normalized pull or publish diagnostic."""

    uri: str
    range: Mapping[str, Any]
    severity: int | None
    code: str | int | None
    message: str
    source: str | None
    version: int | None

    def as_json(self, root: Path) -> dict[str, Any]:
        """Serialize a diagnostic with source and document version fields."""
        return {
            "uri": _uri_path(root, self.uri),
            "range": dict(self.range),
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source": self.source,
            "version": self.version,
            "encoding": "utf-16",
        }


@dataclass(frozen=True)
class LexicalDependencyCandidate:
    """Best-effort candidate; ``legacy_kind`` is internal projection metadata."""

    source: str
    token: str
    target: str
    position: Mapping[str, Any] | None = None
    legacy_kind: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Serialize a candidate for legacy and search projections."""
        return {
            "source": self.source,
            "token": self.token,
            "target": self.target,
            "position": dict(self.position) if self.position else None,
            "encoding": "utf-16",
        }


@dataclass(frozen=True)
class CodeAnalysisReport:
    """Canonical deterministic analysis output."""

    root: str
    files: tuple[str, ...]
    servers: tuple[Mapping[str, Any], ...]
    capabilities: Mapping[str, Mapping[str, str]]
    symbols: tuple[CodeSymbol, ...] = ()
    relations: tuple[CodeRelation, ...] = ()
    diagnostics: tuple[CodeDiagnostic, ...] = ()
    lexical_candidates: tuple[LexicalDependencyCandidate, ...] = ()
    lifecycle: Mapping[str, Any] = field(default_factory=dict)
    status: str = "complete"
    provenance: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None

    def as_json(self, root_path: Path | None = None) -> dict[str, Any]:
        """Serialize the canonical report in deterministic field order."""
        root_path = root_path or Path(self.root)
        return {
            "schema_version": SCHEMA_VERSION,
            "root": self.root,
            "files": list(self.files),
            "servers": [dict(item) for item in self.servers],
            "capabilities": {key: dict(value) for key, value in sorted(self.capabilities.items())},
            "symbols": [item.as_json(root_path) for item in self.symbols],
            "relations": [item.as_json() for item in self.relations],
            "diagnostics": [item.as_json(root_path) for item in self.diagnostics],
            "lexical_candidates": [item.as_json() for item in self.lexical_candidates],
            "lifecycle": dict(self.lifecycle),
            "status": self.status,
            "provenance": dict(self.provenance),
            "error": dict(self.error) if self.error else None,
        }


class LspProcessSession:
    """Content-Length JSON-RPC transport and lifecycle owner."""

    def __init__(
        self,
        spec: LspServerSpec,
        root: Path,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES,
    ) -> None:
        """Configure one bounded stdlib subprocess session."""
        self.spec = spec
        self.root = root.resolve()
        self.timeout = timeout
        self.max_frame_bytes = max_frame_bytes
        self.process: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._stderr = bytearray()
        self._stderr_thread: threading.Thread | None = None
        self._stdout_buffer = bytearray()
        self.lifecycle: list[str] = []
        self.published_diagnostics: list[Mapping[str, Any]] = []

    def start(self) -> None:
        """Start the exact server command in the analysis root."""
        try:
            self.process = subprocess.Popen(
                list(self.spec.command),
                cwd=self.root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as exc:
            raise ServerUnavailable(f"unable to start {self.spec.command[0]}") from exc
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self.lifecycle.append("created")

    def _drain_stderr(self) -> None:
        """Drain bounded server stderr so protocol output cannot deadlock."""
        stream = self.process.stderr if self.process is not None else None
        if stream is None:
            return
        while True:
            try:
                chunk = stream.read(4096)
            except OSError:
                return
            if not chunk:
                return
            remaining = DEFAULT_STDERR_BYTES - len(self._stderr)
            if remaining > 0:
                self._stderr.extend(chunk[:remaining])

    def _readline_timeout(
        self,
        stream: Any,
        deadline: float,
        max_bytes: int,
    ) -> bytes:
        """Read one header line without blocking on a partial line."""
        while True:
            if time.monotonic() >= deadline:
                raise RequestTimeout("LSP frame header timed out")
            newline = self._stdout_buffer.find(b"\n")
            if newline >= 0:
                if newline + 1 > max_bytes:
                    raise ProtocolViolation("LSP header exceeds configured limit")
                line = bytes(self._stdout_buffer[: newline + 1])
                del self._stdout_buffer[: newline + 1]
                return line
            if len(self._stdout_buffer) >= max_bytes:
                raise ProtocolViolation("LSP header exceeds configured limit")
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                raise RequestTimeout("LSP frame header timed out")
            try:
                ready, _, _ = select.select([stream.fileno()], [], [], remaining)
            except (OSError, ValueError) as exc:
                raise ProtocolViolation("LSP stdout is not selectable") from exc
            if not ready:
                raise RequestTimeout("LSP frame header timed out")
            try:
                read_size = min(4096, max_bytes - len(self._stdout_buffer))
                if read_size <= 0:
                    raise ProtocolViolation("LSP header exceeds configured limit")
                chunk = stream.read(read_size)
            except OSError as exc:  # pragma: no cover - platform I/O
                raise ProtocolViolation("LSP frame header read failed") from exc
            if not chunk:
                raise ProtocolViolation("LSP server closed stdout")
            self._stdout_buffer.extend(chunk)

    def _read_payload_timeout(self, stream: Any, length: int, deadline: float) -> bytes:
        """Read one bounded body without allowing a stalled server to hang."""
        if time.monotonic() >= deadline:
            raise RequestTimeout("LSP frame payload timed out")
        payload = bytearray()
        if self._stdout_buffer:
            take = min(length, len(self._stdout_buffer))
            payload.extend(self._stdout_buffer[:take])
            del self._stdout_buffer[:take]
        while len(payload) < length:
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                raise RequestTimeout("LSP frame payload timed out")
            try:
                ready, _, _ = select.select([stream.fileno()], [], [], remaining)
            except (OSError, ValueError) as exc:
                raise ProtocolViolation("LSP stdout is not selectable") from exc
            if not ready:
                raise RequestTimeout("LSP frame payload timed out")
            chunk = stream.read(length - len(payload))
            if not chunk:
                raise ProtocolViolation("truncated LSP payload")
            payload.extend(chunk)
        return payload

    def _read_message(self, deadline: float | None = None) -> Mapping[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise ProtocolViolation("LSP process is not running")
        deadline = deadline if deadline is not None else time.monotonic() + self.timeout
        headers: dict[str, str] = {}
        header_bytes = 0
        while True:
            remaining_header = DEFAULT_MAX_HEADER_BYTES - header_bytes
            if remaining_header <= 0:
                raise ProtocolViolation("LSP headers exceed configured limit")
            line = self._readline_timeout(self.process.stdout, deadline, remaining_header)
            header_bytes += len(line)
            if not line:
                raise ProtocolViolation("LSP server closed stdout")
            if line in (b"\r\n", b"\n"):
                break
            try:
                key, value = line.decode("ascii").split(":", 1)
            except (UnicodeDecodeError, ValueError) as exc:
                raise ProtocolViolation("malformed LSP header") from exc
            normalized_key = key.lower().strip()
            if normalized_key in headers:
                raise ProtocolViolation("duplicate LSP header")
            headers[normalized_key] = value.strip()
        try:
            raw_length = headers["content-length"]
            if re.fullmatch(r"[0-9]+", raw_length) is None:
                raise ValueError("non-numeric content length")
            length = int(raw_length)
        except (KeyError, ValueError) as exc:
            raise ProtocolViolation("missing Content-Length") from exc
        if length < 0 or length > self.max_frame_bytes:
            raise ProtocolViolation("LSP frame exceeds configured limit")
        payload = self._read_payload_timeout(self.process.stdout, length, deadline)
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MalformedResponse("invalid LSP JSON payload") from exc
        if not isinstance(value, Mapping):
            raise MalformedResponse("LSP payload must be an object")
        return value

    def _send(self, message: Mapping[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise ProtocolViolation("LSP process is not running")
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > self.max_frame_bytes:
            raise ProtocolViolation("outbound LSP frame exceeds configured limit")
        try:
            self.process.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
            self.process.stdin.write(payload)
            self.process.stdin.flush()
        except OSError as exc:
            raise ProtocolViolation("LSP stdin write failed") from exc

    def _respond_to_server_request(self, message: Mapping[str, Any]) -> bool:
        if "method" not in message or "id" not in message:
            return False
        method = str(message["method"])
        params = message.get("params")
        if method in {"client/registerCapability", "client/unregisterCapability", "$/progress", "window/workDoneProgress/create"}:
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": None})
        elif method == "workspace/configuration":
            items = params.get("items", []) if isinstance(params, Mapping) else []
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": [None] * len(items)})
        elif method == "workspace/workspaceFolders":
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": [{"uri": _file_uri(self.root), "name": self.root.name}]})
        else:
            self._send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method not found"}})
        return True

    def _consume_notification(self, message: Mapping[str, Any]) -> None:
        """Store push diagnostics while ignoring unrelated notifications."""
        if message.get("method") == "textDocument/publishDiagnostics":
            params = message.get("params")
            if not isinstance(params, Mapping):
                raise MalformedResponse("publishDiagnostics params must be an object")
            if not isinstance(params.get("uri"), str):
                raise MalformedResponse("publishDiagnostics URI must be a string")
            diagnostics = params.get("diagnostics")
            if not isinstance(diagnostics, list) or any(
                not isinstance(item, Mapping) for item in diagnostics
            ):
                raise MalformedResponse("publishDiagnostics diagnostics must be an object list")
            self.published_diagnostics.append(params)

    def drain_notifications(self, quiet_seconds: float = 0.05) -> None:
        """Drain asynchronous notifications until a bounded quiet interval."""
        previous_timeout = self.timeout
        self.timeout = quiet_seconds
        try:
            while True:
                try:
                    message = self._read_message(time.monotonic() + quiet_seconds)
                except RequestTimeout:
                    break
                if self._respond_to_server_request(message):
                    continue
                if "method" in message:
                    self._consume_notification(message)
        finally:
            self.timeout = previous_timeout

    def request(self, method: str, params: Any) -> Any:
        """Send one request and service server-initiated requests."""
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            if time.monotonic() > deadline:
                raise RequestTimeout(f"LSP request timed out: {method}")
            message = self._read_message(deadline)
            if self._respond_to_server_request(message):
                continue
            # Publish-diagnostics is a notification.  Keep it available to
            # the caller without making notifications part of request order.
            if message.get("method") == "textDocument/publishDiagnostics":
                self._consume_notification(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise ProtocolViolation(f"LSP {method} failed: {error}")
            return message.get("result")

    def notify(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification without allocating a request ID."""
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self, *, failed: bool = False) -> None:
        """Shutdown cleanly or terminate/kill after a typed failure."""
        if self.process is None:
            return
        try:
            if not failed and self.process.poll() is None:
                try:
                    self.request("shutdown", None)
                    self.lifecycle.append("shutdown")
                except LspAnalysisError:
                    failed = True
                if self.process.poll() is None:
                    self.notify("exit", None)
            if self.process.poll() is None:
                try:
                    self.process.wait(timeout=min(1.0, self.timeout))
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=1.0)
            self.lifecycle.append("exit")
        finally:
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=0.2)
            if not failed and self.process.returncode not in (None, 0):
                raise ServerExitNonzero(
                    f"{self.spec.language_id} server exited with {self.process.returncode}"
                )

    def __enter__(self) -> LspProcessSession:
        """Start the session for a context-manager scope."""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close the session and preserve failure semantics."""
        self.close(failed=exc is not None)


def language_for_path(path: Path) -> str | None:
    """Map a source suffix to its manifest language identifier."""
    return vector_search.language_for_path(path)


def _contains_symlink(path: Path, root: Path) -> bool:
    """Return whether an input path is noncanonical or has a symlink ancestor."""
    try:
        relative = path.absolute().relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        if part == "..":
            return True
        if part in ("", "."):
            continue
        current /= part
        if current.is_symlink():
            return True
    return False


def _symbol_from(raw: Mapping[str, Any], uri: str) -> CodeSymbol:
    name = raw.get("name")
    if not isinstance(name, str):
        raise MalformedResponse("symbol name must be a string")
    kind = raw.get("kind")
    if not isinstance(kind, int) or isinstance(kind, bool) or not 1 <= kind <= 26:
        raise MalformedResponse("symbol kind must be an LSP SymbolKind integer")
    selection = raw.get("selectionRange")
    if not isinstance(selection, Mapping):
        selection = raw.get("range")
    container_name = raw.get("containerName", raw.get("container"))
    if container_name is not None and not isinstance(container_name, str):
        raise MalformedResponse("symbol container must be a string")
    return CodeSymbol(
        uri=uri,
        name=name,
        kind=kind,
        range=_range(raw.get("range")),
        selection_range=_range(selection),
        container=container_name,
    )


def _flatten_symbols(raw: Any, uri: str) -> list[CodeSymbol]:
    if not isinstance(raw, list):
        raise MalformedResponse("documentSymbol response must be a list")
    result: list[CodeSymbol] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise MalformedResponse("documentSymbol response contains a non-object")
        if "location" in item and isinstance(item["location"], Mapping):
            loc = item["location"]
            symbol = dict(item)
            symbol["range"] = loc.get("range")
            symbol["selectionRange"] = loc.get("range")
            result.append(_symbol_from(symbol, str(loc.get("uri", uri))))
        else:
            result.append(_symbol_from(item, uri))
            result.extend(_flatten_symbols(item.get("children", []), uri))
    return result


def _location(value: Mapping[str, Any], root: Path) -> tuple[str, dict[str, int] | None]:
    uri = value.get("uri")
    if not uri and isinstance(value.get("targetUri"), str):
        uri = value["targetUri"]
    if not isinstance(uri, str):
        raise MalformedResponse("location has no URI")
    path = _uri_path(root, uri)
    range_value = value.get("range") or value.get("targetSelectionRange")
    if not isinstance(range_value, Mapping):
        raise MalformedResponse("location has no range")
    pos = _position(range_value.get("start"))
    return path, pos


def _lexical_candidates(root: Path, files: Sequence[Path]) -> list[LexicalDependencyCandidate]:
    """Extract bounded lexical candidates with AST precision for Python."""
    patterns = (
        re.compile(r"^\s*from\s+([.]+)\s+import\s+([A-Za-z_]\w*)"),
        re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)"),
        re.compile(r"^\s*(?:source|\.)\s+([^\s#]+)"),
        re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]'),
        re.compile(r"^\s*(?:mod|use)\s+([A-Za-z_][\w:]*)"),
    )
    results: list[LexicalDependencyCandidate] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        source = path.resolve().relative_to(root.resolve()).as_posix()
        lines = text.splitlines()
        if language_for_path(path) == "python":
            try:
                tree = ast.parse(text, filename=source)
            except SyntaxError:
                tree = None
            if tree is not None:
                results.extend(_python_ast_candidates(root, path, source, lines, tree))
                continue
        for line_no, line in enumerate(lines):
            for pattern in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                token = (
                    f"{match.group(1)}{match.group(2)}"
                    if match.lastindex == 2
                    else match.group(1)
                )
                target = token
                language = language_for_path(path) or "unknown"
                if token.startswith("/") or (
                    token.startswith(".") and language != "python"
                ):
                    candidate = (path.parent / token).resolve(strict=False)
                    try:
                        target = candidate.relative_to(root.resolve()).as_posix()
                    except ValueError:
                        target = f"external:unknown:{token}"
                else:
                    target = _resolve_lexical_target(root, path, language, token)
                prefix = line[: max(line.find(token), 0)]
                results.append(
                    LexicalDependencyCandidate(
                        source=source,
                        token=token,
                        target=target,
                        position={"line": line_no, "character": len(prefix.encode("utf-16-le")) // 2},
                    )
                )
                break
    unique: dict[str, LexicalDependencyCandidate] = {}
    for item in results:
        key = json.dumps(item.as_json(), sort_keys=True, ensure_ascii=False)
        unique.setdefault(key, item)
    return sorted(unique.values(), key=lambda item: (item.source, json.dumps(item.position, sort_keys=True), item.token, item.target))


def _utf16_position(lines: Sequence[str], line_no: int, byte_offset: int) -> dict[str, int]:
    """Convert an AST UTF-8 byte offset to an LSP UTF-16 position."""
    line = lines[line_no] if 0 <= line_no < len(lines) else ""
    prefix = line.encode("utf-8")[:byte_offset].decode("utf-8", errors="ignore")
    return {"line": line_no, "character": len(prefix.encode("utf-16-le")) // 2}


def _python_ast_candidates(
    root: Path,
    path: Path,
    source: str,
    lines: Sequence[str],
    tree: ast.AST,
) -> list[LexicalDependencyCandidate]:
    """Return module and per-symbol candidates for parsed Python imports."""
    results: list[LexicalDependencyCandidate] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                token = alias.name
                position = _utf16_position(lines, alias.lineno - 1, alias.col_offset)
                results.append(
                    LexicalDependencyCandidate(
                        source=source,
                        token=token,
                        target=_resolve_lexical_target(root, path, "python", token),
                        position=position,
                        legacy_kind="import",
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level <= 0 and node.module is None:
                continue
            module_token = "." * node.level + (node.module or "")
            module_line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
            from_start = module_line.find("from")
            module_column = module_line.find(module_token, max(from_start + 4, 0))
            if module_column < 0:
                module_column = node.col_offset
            module_position = _utf16_position(
                lines,
                node.lineno - 1,
                len(module_line[:module_column].encode("utf-8")),
            )
            results.append(
                LexicalDependencyCandidate(
                    source=source,
                    token=module_token,
                    target=_resolve_lexical_target(root, path, "python", module_token),
                    position=module_position,
                    legacy_kind="import",
                )
            )
            for alias in node.names:
                if alias.name == "*":
                    continue
                if module_token:
                    separator = "" if module_token.endswith(".") else "."
                    token = f"{module_token}{separator}{alias.name}"
                else:
                    token = alias.name
                results.append(
                    LexicalDependencyCandidate(
                        source=source,
                        token=token,
                        target=_resolve_lexical_target(root, path, "python", token),
                        position=_utf16_position(lines, alias.lineno - 1, alias.col_offset),
                        legacy_kind="from-import-symbol",
                    )
                )
    return results


def _resolve_lexical_target(root: Path, source: Path, language: str, token: str) -> str:
    """Resolve obvious local module/include targets before externalizing."""
    candidates: list[Path] = []
    if language == "python":
        module = token.lstrip(".").replace(".", "/")
        base = source.parent if token.startswith(".") else root
        if token.startswith("."):
            for _ in range(max(len(token) - len(token.lstrip(".")) - 1, 0)):
                base = base.parent
        candidates.extend((base / f"{module}.py", base / module / "__init__.py"))
    elif language in {"c", "cpp"}:
        candidates.append(source.parent / token)
        candidates.append(root / token)
    elif language == "rust":
        module = token.split("::", 1)[0]
        candidates.extend((source.parent / f"{module}.rs", source.parent / module / "mod.rs", root / f"{module}.rs"))
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                break
    return f"external:{language}:{token}"


def _diagnostic(raw: Mapping[str, Any], uri: str) -> CodeDiagnostic:
    severity_value = raw.get("severity")
    if severity_value is not None and (
        not isinstance(severity_value, int)
        or isinstance(severity_value, bool)
        or not 1 <= severity_value <= 4
    ):
        raise MalformedResponse("diagnostic severity must be an LSP integer 1..4")
    code_value = raw.get("code")
    if code_value is not None and (
        not isinstance(code_value, (str, int)) or isinstance(code_value, bool)
    ):
        raise MalformedResponse("diagnostic code must be a string or integer")
    source_value = raw.get("source")
    if source_value is not None and not isinstance(source_value, str):
        raise MalformedResponse("diagnostic source must be a string")
    version_value = raw.get("version")
    if version_value is not None and (
        not isinstance(version_value, int)
        or isinstance(version_value, bool)
        or version_value < 0
    ):
        raise MalformedResponse("diagnostic version must be a non-negative integer")
    message_value = raw.get("message")
    if not isinstance(message_value, str):
        raise MalformedResponse("diagnostic message must be a string")
    return CodeDiagnostic(
        uri=uri,
        range=_range(raw.get("range")),
        severity=severity_value,
        code=code_value,
        message=message_value,
        source=source_value,
        version=version_value,
    )


def _unique_symbols(items: Iterable[CodeSymbol]) -> tuple[CodeSymbol, ...]:
    """Deduplicate symbols without hashing their mapping-valued fields."""
    seen: set[str] = set()
    result: list[CodeSymbol] = []
    for item in items:
        key = json.dumps(
            {
                "uri": item.uri,
                "name": item.name,
                "kind": item.kind,
                "range": item.range,
                "selectionRange": item.selection_range,
                "container": item.container,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(sorted(result, key=lambda item: (item.uri, item.name, item.range["start"]["line"], item.range["start"]["character"])))


def _unique_relations(items: Iterable[CodeRelation]) -> tuple[CodeRelation, ...]:
    seen: set[str] = set()
    result: list[CodeRelation] = []
    for item in items:
        key = json.dumps(item.as_json(), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(sorted(result, key=lambda item: (item.orientation, item.source, item.target, json.dumps(item.position, sort_keys=True))))


def _unique_diagnostics(items: Iterable[CodeDiagnostic]) -> tuple[CodeDiagnostic, ...]:
    seen: set[str] = set()
    result: list[CodeDiagnostic] = []
    for item in items:
        key = json.dumps(item.as_json(Path("/")), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(sorted(result, key=lambda item: (item.uri, item.range["start"]["line"], item.range["start"]["character"], item.message)))


def analyze(
    root: Path,
    files: Sequence[Path | str],
    *,
    specs: Mapping[str, LspServerSpec] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES,
) -> CodeAnalysisReport:
    """Analyze files and return a complete report or a typed failure report."""
    root = root.resolve()
    resolved_files: list[Path] = []
    for value in files:
        raw_path = Path(value)
        candidate = raw_path if raw_path.is_absolute() else root / raw_path
        if candidate.is_symlink() or _contains_symlink(candidate, root):
            return _failed_report(root, (), PathEscape(f"noncanonical or symlink file path is not allowed: {candidate}"), {})
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return _failed_report(root, (), PathEscape(str(path)), {})
        if not path.is_file():
            return _failed_report(root, (), ServerUnavailable(f"file not found: {path}"), {})
        resolved_files.append(path)
    resolved_files = sorted(set(resolved_files), key=lambda path: path.relative_to(root).as_posix())
    file_locators = tuple(path.relative_to(root).as_posix() for path in resolved_files)
    specs = specs or {}
    all_symbols: list[CodeSymbol] = []
    all_relations: list[CodeRelation] = []
    all_diagnostics: list[CodeDiagnostic] = []
    all_caps: dict[str, Mapping[str, str]] = {}
    servers: list[Mapping[str, Any]] = []
    lifecycle: dict[str, Any] = {"state": "created", "encoding": "utf-16", "protocol": LSP_VERSION}
    provenance: dict[str, Any] = {"schema": SCHEMA_VERSION, "protocol": LSP_VERSION, "files": list(file_locators)}
    try:
        for language in sorted({language_for_path(path) for path in resolved_files} - {None}):
            language_files = [path for path in resolved_files if language_for_path(path) == language]
            spec = specs.get(language) or LspServerSpec.for_language(language, root=root)
            server_json = spec.as_json()
            servers.append(server_json)
            with LspProcessSession(spec, root, timeout=timeout, max_frame_bytes=max_frame_bytes) as session:
                session.lifecycle.append("initialize(sent)")
                initialize = session.request(
                    "initialize",
                    {
                        "processId": os.getpid(),
                        "rootUri": _file_uri(root),
                        "workspaceFolders": [{"uri": _file_uri(root), "name": root.name}],
                        "capabilities": {},
                        "clientInfo": {"name": "agent-canon", "version": SCHEMA_VERSION},
                    },
                )
                if not isinstance(initialize, Mapping):
                    raise MalformedResponse("initialize result is not an object")
                caps = initialize.get("capabilities", {})
                if not isinstance(caps, Mapping):
                    raise MalformedResponse("initialize capabilities is not an object")
                server_info = initialize.get("serverInfo", {})
                if isinstance(server_info, Mapping):
                    server_json["version"] = spec.version or str(server_info.get("version", ""))
                matrix = LspCapabilityMatrix.from_initialize(caps)
                if matrix.document_symbols == "unsupported":
                    raise CapabilityUnavailable(f"{language} server lacks documentSymbolProvider")
                all_caps[language] = matrix.as_json()
                session.notify("initialized", {})
                session.lifecycle.append("initialized")
                for path in language_files:
                    uri = _file_uri(path)
                    try:
                        text = path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError) as exc:
                        raise MalformedResponse(
                            f"unable to read source file {path.relative_to(root).as_posix()}"
                        ) from exc
                    open_close = bool(caps.get("textDocumentSync", {}).get("openClose", False)) if isinstance(caps.get("textDocumentSync"), Mapping) else False
                    if open_close:
                        session.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": language, "version": 1, "text": text}})
                        session.lifecycle.append(f"didOpen:{path.relative_to(root).as_posix()}")
                    raw_symbols = session.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
                    session.lifecycle.append(f"documentSymbol:{path.relative_to(root).as_posix()}")
                    symbols = _flatten_symbols(raw_symbols, uri)
                    for symbol in symbols:
                        _uri_path(root, symbol.uri)
                    all_symbols.extend(symbols)
                    if matrix.definitions == "supported_facts":
                        for candidate in _lexical_candidates(root, [path]):
                            raw_definition = session.request("textDocument/definition", {"textDocument": {"uri": uri}, "position": candidate.position or {"line": 0, "character": 0}})
                            if raw_definition is None:
                                raw_definition = []
                            if isinstance(raw_definition, Mapping):
                                raw_definition = [raw_definition]
                            if not isinstance(raw_definition, list):
                                raise MalformedResponse("definition response must be a location list")
                            for location in raw_definition:
                                if not isinstance(location, Mapping):
                                    raise MalformedResponse("definition response contains a non-object")
                                target, position = _location(location, root)
                                all_relations.append(CodeRelation("definition", candidate.source, target, position))
                    if matrix.references == "supported_facts":
                        for symbol in symbols:
                            selection_start = symbol.selection_range.get(
                                "start", {"line": 0, "character": 0}
                            )
                            raw_refs = session.request(
                                "textDocument/references",
                                {
                                    "textDocument": {"uri": uri},
                                    "position": _position(selection_start),
                                    "context": {"includeDeclaration": True},
                                },
                            )
                            if raw_refs is None:
                                raw_refs = []
                            if not isinstance(raw_refs, list):
                                raise MalformedResponse("references response must be a location list")
                            for location in raw_refs:
                                if not isinstance(location, Mapping):
                                    raise MalformedResponse("references response contains a non-object")
                                target, position = _location(location, root)
                                all_relations.append(
                                    CodeRelation(
                                        "reference",
                                        path.relative_to(root).as_posix(),
                                        target,
                                        position,
                                    )
                                )
                    session.drain_notifications()
                    if matrix.diagnostics == "supported_facts" and caps.get("diagnosticProvider"):
                        raw_diag = session.request("textDocument/diagnostic", {"textDocument": {"uri": uri}})
                        if not isinstance(raw_diag, Mapping) or not isinstance(raw_diag.get("items"), list):
                            raise MalformedResponse("pull diagnostics result must contain an items list")
                        items = raw_diag["items"]
                        if any(not isinstance(item, Mapping) for item in items):
                            raise MalformedResponse("pull diagnostics contains a non-object")
                        all_diagnostics.extend(_diagnostic(item, uri) for item in items)
                    elif session.published_diagnostics:
                        all_caps[language]["diagnostics"] = "supported_empty"
                        for published in session.published_diagnostics:
                            if not isinstance(published, Mapping) or published.get("uri") != uri:
                                continue
                            items = published.get("diagnostics", [])
                            if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
                                raise MalformedResponse("push diagnostics must contain an object list")
                            all_diagnostics.extend(_diagnostic(item, uri) for item in items)
                    if matrix.call_hierarchy == "supported_facts":
                        for symbol in [item for item in all_symbols if item.uri == uri]:
                            start = symbol.selection_range.get("start", {"line": 0, "character": 0})
                            prepared = session.request("textDocument/prepareCallHierarchy", {"textDocument": {"uri": uri}, "position": start})
                            if prepared is None:
                                prepared = []
                            if not isinstance(prepared, list):
                                raise MalformedResponse("call hierarchy prepare response must be a list")
                            for item in prepared:
                                if (
                                    not isinstance(item, Mapping)
                                    or not isinstance(item.get("name"), str)
                                ):
                                    raise MalformedResponse("call hierarchy item is malformed")
                                item_uri_value = item.get("uri", uri)
                                if not isinstance(item_uri_value, str):
                                    raise MalformedResponse("call hierarchy item URI is malformed")
                                item_uri = item_uri_value
                                item_start = item.get("selectionRange", {}).get("start", start) if isinstance(item.get("selectionRange"), Mapping) else start
                                if not isinstance(item_start, Mapping):
                                    raise MalformedResponse("call hierarchy selection range is malformed")
                                item_start = _position(item_start)
                                for method, orientation in (("callHierarchy/incomingCalls", "call-incoming"), ("callHierarchy/outgoingCalls", "call-outgoing")):
                                    calls = session.request(method, {"item": item})
                                    if calls is None:
                                        calls = []
                                    if not isinstance(calls, list):
                                        raise MalformedResponse("call hierarchy response must be a list")
                                    for call in calls:
                                        if not isinstance(call, Mapping):
                                            raise MalformedResponse("call hierarchy call is malformed")
                                        other = call.get("from") if orientation == "call-incoming" else call.get("to")
                                        if not isinstance(other, Mapping):
                                            raise MalformedResponse("call hierarchy endpoint is malformed")
                                        other_uri = other.get("uri", uri)
                                        if not isinstance(other_uri, str):
                                            raise MalformedResponse("call hierarchy endpoint URI is malformed")
                                        source = _uri_path(root, item_uri)
                                        target = _uri_path(root, other_uri)
                                        if orientation == "call-incoming":
                                            source, target = target, source
                                        all_relations.append(CodeRelation(orientation, source, target, _position(item_start)))
                    if open_close:
                        session.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
                        session.lifecycle.append(f"didClose:{path.relative_to(root).as_posix()}")
                lifecycle[language] = list(session.lifecycle)
                provenance[language] = {
                    "record": spec.record_id,
                    "command": list(spec.command),
                    "version": spec.version,
                    "resolution": spec.resolution,
                    "verificationOutput": spec.verification_output,
                    "requestIds": session._next_id - 1,
                }
        lifecycle["state"] = "complete"
    except LspAnalysisError as exc:
        return _failed_report(root, file_locators, exc, all_caps, servers=servers, provenance=provenance, lifecycle=lifecycle)
    lexical = tuple(_lexical_candidates(root, resolved_files))
    return CodeAnalysisReport(root=root.as_posix(), files=file_locators, servers=tuple(servers), capabilities=all_caps, symbols=_unique_symbols(all_symbols), relations=_unique_relations(all_relations), diagnostics=_unique_diagnostics(all_diagnostics), lexical_candidates=lexical, lifecycle=lifecycle, status="complete", provenance=provenance)


def _failed_report(root: Path, files: Sequence[str], error: LspAnalysisError, capabilities: Mapping[str, Mapping[str, str]], *, servers: Sequence[Mapping[str, Any]] = (), provenance: Mapping[str, Any] | None = None, lifecycle: Mapping[str, Any] | None = None) -> CodeAnalysisReport:
    failed_lifecycle = dict(lifecycle or {})
    failed_lifecycle["state"] = "failed"
    return CodeAnalysisReport(root=root.as_posix(), files=tuple(files), servers=tuple(servers), capabilities=capabilities, lifecycle=failed_lifecycle, status="failed", provenance=dict(provenance or {}), error={"code": error.error_code, "message": str(error)})


def _parse_server_specs(values: Sequence[str]) -> dict[str, LspServerSpec]:
    specs: dict[str, LspServerSpec] = {}
    for value in values:
        try:
            language, command = value.split("=", 1)
        except ValueError as exc:
            raise ValueError("--server must be LANGUAGE=COMMAND") from exc
        argv = tuple(shlex.split(command))
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("custom --server executable must be an absolute path")
        specs[language] = LspServerSpec(
            language,
            argv,
            record_id=f"{language}-custom",
            executable=argv[0],
            resolution="caller-override",
        )
    return specs


def _files_from_args(root: Path, values: Sequence[str] | None) -> list[Path]:
    if values is not None:
        return [Path(value) for value in values]
    return list(vector_search.discover_lsp_files(root))


def _legacy_lines(report: CodeAnalysisReport, root: Path, *, print_unresolved: bool = False) -> list[str]:
    lines: list[str] = []
    for candidate in report.lexical_candidates:
        if candidate.target.startswith("external:") and not print_unresolved:
            continue
        source_path = root / candidate.source
        language = language_for_path(source_path) or "unknown"
        if language in {"c", "cpp"}:
            output_language, kind = "c-family", "include"
        elif language == "shellscript":
            output_language, kind = "shell", "source"
        elif language == "python":
            output_language = "python"
            try:
                source_line = source_path.read_text(encoding="utf-8").splitlines()[candidate.position.get("line", 0) if candidate.position else 0]
            except (OSError, UnicodeDecodeError, IndexError):
                source_line = candidate.token
            kind = candidate.legacy_kind or (
                "from-import-symbol" if source_line.lstrip().startswith("from ") else "import"
            )
        else:
            output_language, kind = language, "lexical"
        try:
            raw = source_path.read_text(encoding="utf-8").splitlines()[candidate.position.get("line", 0) if candidate.position else 0]
        except (OSError, UnicodeDecodeError, IndexError):
            raw = candidate.token
        lines.append(f"CODE_DEPENDENCY\t{output_language}\t{kind}\t{candidate.source}\t{candidate.target}\t{candidate.token}\t{raw}")
    for relation in report.relations:
        lines.append(f"CODE_DEPENDENCY\tlsp\t{relation.orientation}\t{relation.source}\t{relation.target}\t\t")
    return lines


def _write_report_atomic(report: CodeAnalysisReport, root: Path, destination: Path) -> None:
    """Persist either complete or failed report before emitting legacy status."""
    destination = destination if destination.is_absolute() else root / destination
    destination = destination.resolve(strict=False)
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise PathEscape(
            f"analysis report destination escapes selected root: {destination}"
        ) from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(report.as_json(root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _lexical_only_report(root: Path, files: Sequence[Path]) -> CodeAnalysisReport:
    """Build a validated lexical report without starting a language server."""
    root = root.resolve()
    resolved: list[Path] = []
    for path in files:
        raw_path = path
        candidate_path = raw_path if raw_path.is_absolute() else root / raw_path
        if candidate_path.is_symlink() or _contains_symlink(candidate_path, root):
            return _failed_report(root, (), PathEscape(f"noncanonical or symlink file path is not allowed: {candidate_path}"), {})
        candidate = candidate_path.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return _failed_report(root, (), PathEscape(str(candidate)), {})
        if not candidate.is_file():
            return _failed_report(root, (), ServerUnavailable(f"file not found: {candidate}"), {})
        resolved.append(candidate)
    resolved = sorted(set(resolved), key=lambda item: item.relative_to(root).as_posix())
    locators = tuple(item.relative_to(root).as_posix() for item in resolved)
    return CodeAnalysisReport(
        root=root.as_posix(),
        files=locators,
        servers=(),
        capabilities={},
        lexical_candidates=tuple(_lexical_candidates(root, resolved)),
        lifecycle={"state": "lexical-only"},
        status="complete",
        provenance={"schema": SCHEMA_VERSION, "protocol": LSP_VERSION},
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the analyze and legacy command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "scan-legacy"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--root", type=Path, default=Path.cwd())
        sub.add_argument("--files", nargs="*", default=None)
        sub.add_argument("--server", action="append", default=[], metavar="LANGUAGE=COMMAND")
        sub.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
        sub.add_argument("--format", choices=("json", "text"), default="json")
        if name == "scan-legacy":
            sub.add_argument("--changed", action="store_true", help="Analyze changed and untracked paths.")
            sub.add_argument("--print-unresolved", action="store_true", help="Retained legacy flag; unresolved candidates are emitted.")
            sub.add_argument("--paths-file", type=Path, default=None)
            sub.add_argument("--analysis-json", type=Path, default=None)
            sub.add_argument("--lexical-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected analysis command and return its status."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    files: list[Path]
    if args.command == "scan-legacy" and args.paths_file is not None:
        if args.files or args.changed:
            print("scan-legacy: --paths-file cannot be combined with --changed or --files", file=sys.stderr)
            return 2
        try:
            files = [Path(line.strip()) for line in args.paths_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeDecodeError) as exc:
            print(f"scan-legacy: unable to read --paths-file: {exc}", file=sys.stderr)
            return 2
    elif args.command == "scan-legacy" and args.changed:
        try:
            changed = subprocess.run(["git", "diff", "--name-only", "HEAD", "--"], cwd=root, check=False, capture_output=True, text=True).stdout.splitlines()
            untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root, check=False, capture_output=True, text=True).stdout.splitlines()
            candidates = tuple(value for value in [*changed, *untracked] if value)
            files = list(vector_search.discover_lsp_files(root, candidates)) if candidates else []
        except OSError:
            files = []
    else:
        files = _files_from_args(root, args.files)
    files = [path if path.is_absolute() else root / path for path in files]
    try:
        specs = _parse_server_specs(args.server)
    except ValueError as exc:
        print(f"LSP_ANALYSIS=fail\nLSP_ANALYSIS_ERROR={exc}", file=sys.stderr)
        return 2
    try:
        report = (
            _lexical_only_report(root, files)
            if args.command == "scan-legacy" and args.lexical_only
            else analyze(root, files, specs=specs, timeout=args.timeout)
        )
    except (LspAnalysisError, ValueError) as exc:
        error = exc if isinstance(exc, LspAnalysisError) else LspAnalysisError(str(exc))
        report = _failed_report(root, (), error, {})
    if args.command == "scan-legacy":
        if args.analysis_json is not None:
            _write_report_atomic(report, root, args.analysis_json)
        lines = _legacy_lines(report, root, print_unresolved=bool(args.print_unresolved))
        if report.status != "complete":
            print(f"AGENT_SCAN=fail\t{report.error or {}}", file=sys.stderr)
            return 1
        output = "\n".join(lines)
        if output:
            print(output)
        print(f"CODE_DEPENDENCY_SCAN=pass files={len(report.files)}")
        return 0
    payload = report.as_json(root)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"AGENT_ANALYSIS={report.status}")
        if report.error:
            print(f"AGENT_ANALYSIS_ERROR={report.error['code']}:{report.error['message']}")
    return 0 if report.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
