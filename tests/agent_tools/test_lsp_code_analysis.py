"""Golden and protocol tests for the LSP code-analysis adapter."""

# @dependency-start
# contract test
# responsibility Tests contract and protocol checks for the LSP 3.17 code-analysis adapter.
# upstream design ../../documents/structured-analysis/code-analysis.md LSP 3.17 protocol contract and evidence policy
# upstream design ../../documents/tools/lsp_code_analysis.md tests for tool-owned implementation evidence
# upstream implementation ../../tools/agent_tools/lsp_code_analysis.py code-analysis protocol implementation
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "lsp_code_analysis.py"

if str(TOOL.parent) not in sys.path:
    sys.path.insert(0, str(TOOL.parent))

import lsp_code_analysis as lsp  # noqa: E402


def write_fake_server(
    root: Path,
    *,
    malformed: bool = False,
    outside_symbol: bool = False,
    malformed_quiet: bool = False,
) -> Path:
    """Create a minimal Content-Length LSP 3.17 fixture."""
    script = root / "fake_lsp.py"
    body = textwrap.dedent(
        f"""
        import json, sys
        def read_message():
            headers = {{}}
            while True:
                line = sys.stdin.buffer.readline()
                if not line: return None
                if line in (b'\\n', b'\\r\\n'): break
                key, value = line.decode().split(':', 1)
                headers[key.lower().strip()] = value.strip()
            data = sys.stdin.buffer.read(int(headers['content-length']))
            return json.loads(data.decode())
        def send(value):
            payload = json.dumps(value, separators=(',', ':')).encode()
            sys.stdout.buffer.write(f'Content-Length: {{len(payload)}}\\r\\n\\r\\n'.encode() + payload)
            sys.stdout.buffer.flush()
        while True:
            message = read_message()
            if message is None: break
            method = message.get('method')
            if method == 'initialize':
                send({{'jsonrpc':'2.0','id':message['id'],'result':{{'serverInfo':{{'name':'fake','version':'9.9'}},'capabilities':{{'documentSymbolProvider':True}}}}}})
            elif method == 'textDocument/documentSymbol':
                if {str(malformed)}:
                    send({{'jsonrpc':'2.0','id':message['id'],'result':[{{'name':'broken'}}]}})
                elif {str(outside_symbol)}:
                    send({{'jsonrpc':'2.0','id':message['id'],'result':[{{'name':'outside','kind':12,'location':{{'uri':'file:///tmp/outside-symbol.py','range':{{'start':{{'line':0,'character':0}},'end':{{'line':0,'character':4}}}}}}}}]}})
                else:
                    uri = message['params']['textDocument']['uri']
                    send({{'jsonrpc':'2.0','id':message['id'],'result':[{{'name':'main','kind':12,'range':{{'start':{{'line':0,'character':0}},'end':{{'line':0,'character':4}}}},'selectionRange':{{'start':{{'line':0,'character':0}},'end':{{'line':0,'character':4}}}}}}]}})
                    if {str(malformed_quiet)}:
                        sys.stdout.buffer.write(b'Content-Length: 1\\r\\n\\r\\n{{')
                        sys.stdout.buffer.flush()
            elif method == 'shutdown':
                send({{'jsonrpc':'2.0','id':message['id'],'result':None}})
            elif method == 'exit':
                break
        """
    )
    script.write_text(body, encoding="utf-8")
    return script


def write_diagnostic_server(
    root: Path,
    *,
    push: bool = False,
    malformed: bool = False,
    exit_code: int = 0,
) -> Path:
    """Create a pull/push diagnostics fixture with optional bad exit."""
    script = root / "diagnostic_lsp.py"
    capabilities = (
        {"documentSymbolProvider": True, "textDocumentSync": {"openClose": True}}
        if push
        else {"documentSymbolProvider": True, "diagnosticProvider": {"identifier": "fake"}}
    )
    diagnostic = (
        {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}, "severity": "bad", "message": "broken"}
        if malformed
        else {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}, "severity": 2, "code": "E1", "message": "warning", "source": "fake", "version": 3}
    )
    body = textwrap.dedent(
        f"""
        import json, sys
        def read_message():
            headers = {{}}
            while True:
                line = sys.stdin.buffer.readline()
                if not line: return None
                if line in (b'\\n', b'\\r\\n'): break
                key, value = line.decode().split(':', 1)
                headers[key.lower().strip()] = value.strip()
            return json.loads(sys.stdin.buffer.read(int(headers['content-length'])).decode())
        def send(value):
            payload = json.dumps(value, separators=(',', ':')).encode()
            sys.stdout.buffer.write(f'Content-Length: {{len(payload)}}\\r\\n\\r\\n'.encode() + payload)
            sys.stdout.buffer.flush()
        while True:
            message = read_message()
            if message is None: break
            method = message.get('method')
            if method == 'initialize':
                send({{'jsonrpc':'2.0','id':message['id'],'result':{{'capabilities':{capabilities!r}}}}})
            elif method == 'textDocument/didOpen' and {str(push)}:
                send({{'jsonrpc':'2.0','method':'textDocument/publishDiagnostics','params':{{'uri':message['params']['textDocument']['uri'],'diagnostics':[{json.dumps(diagnostic)}]}}}})
            elif method == 'textDocument/documentSymbol':
                send({{'jsonrpc':'2.0','id':message['id'],'result':[{{'name':'main','kind':12,'range':{{'start':{{'line':0,'character':0}},'end':{{'line':0,'character':4}}}},'selectionRange':{{'start':{{'line':0,'character':0}},'end':{{'line':0,'character':4}}}}}}]}})
            elif method == 'textDocument/diagnostic':
                send({{'jsonrpc':'2.0','id':message['id'],'result':{{'items':[{json.dumps(diagnostic)}]}}}})
            elif method == 'shutdown':
                send({{'jsonrpc':'2.0','id':message['id'],'result':None}})
                sys.exit({exit_code})
            elif method == 'exit':
                sys.exit({exit_code})
        """
    )
    script.write_text(body, encoding="utf-8")
    return script


def write_reference_server(root: Path, *, include_optional: bool = False) -> Path:
    """Create a references-capable server with non-zero symbol positions."""
    script = root / "reference_lsp.py"
    body = textwrap.dedent(
        """
        import json, sys
        positions = [(1, 2), (3, 4)]
        def read_message():
            headers = {}
            while True:
                line = sys.stdin.buffer.readline()
                if not line: return None
                if line in (b'\\n', b'\\r\\n'): break
                key, value = line.decode().split(':', 1)
                headers[key.lower().strip()] = value.strip()
            return json.loads(sys.stdin.buffer.read(int(headers['content-length'])).decode())
        def send(value):
            payload = json.dumps(value, separators=(',', ':')).encode()
            sys.stdout.buffer.write(f'Content-Length: {len(payload)}\\r\\n\\r\\n'.encode() + payload)
            sys.stdout.buffer.flush()
        while True:
            message = read_message()
            if message is None: break
            method = message.get('method')
            if method == 'initialize':
                send({'jsonrpc':'2.0','id':message['id'],'result':{'capabilities':{'documentSymbolProvider':True,'referencesProvider':True}}})
            elif method == 'textDocument/documentSymbol':
                send({'jsonrpc':'2.0','id':message['id'],'result':[
                    {'name':'first','kind':12,'range':{'start':{'line':1,'character':2},'end':{'line':1,'character':7}},'selectionRange':{'start':{'line':1,'character':2},'end':{'line':1,'character':7}}},
                    {'name':'second','kind':12,'range':{'start':{'line':3,'character':4},'end':{'line':3,'character':10}},'selectionRange':{'start':{'line':3,'character':4},'end':{'line':3,'character':10}}},
                ]})
            elif method == 'textDocument/references':
                position = message['params']['position']
                send({'jsonrpc':'2.0','id':message['id'],'result':[{'uri':message['params']['textDocument']['uri'],'range':{'start':position,'end':position}}] if (position['line'], position['character']) in positions else []})
            elif method == 'shutdown':
                send({'jsonrpc':'2.0','id':message['id'],'result':None})
            elif method == 'exit':
                break
        """
    )
    if include_optional:
        body = body.replace(
            "'documentSymbolProvider':True,'referencesProvider':True",
            "'documentSymbolProvider':True,'definitionProvider':True,'referencesProvider':True,'callHierarchyProvider':True",
        )
        body = body.replace(
            "    elif method == 'shutdown':\n",
            """    elif method == 'textDocument/definition':
        uri = message['params']['textDocument']['uri']
        send({'jsonrpc':'2.0','id':message['id'],'result':[{'uri':uri,'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':1}}}]})
    elif method == 'textDocument/prepareCallHierarchy':
        uri = message['params']['textDocument']['uri']
        position = message['params']['position']
        send({'jsonrpc':'2.0','id':message['id'],'result':[{'name':'prepared','kind':12,'uri':uri,'range':{'start':position,'end':position},'selectionRange':{'start':position,'end':position}}]})
    elif method == 'callHierarchy/incomingCalls':
        item = message['params']['item']
        send({'jsonrpc':'2.0','id':message['id'],'result':[{'from':item}]})
    elif method == 'callHierarchy/outgoingCalls':
        item = message['params']['item']
        send({'jsonrpc':'2.0','id':message['id'],'result':[{'to':item}]})
    elif method == 'shutdown':
""",
        )
    script.write_text(body, encoding="utf-8")
    return script


def write_partial_header_server(root: Path) -> Path:
    """Create a server that leaves one response header unterminated."""
    script = root / "partial_header_lsp.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys, time
            def read_message():
                while True:
                    line = sys.stdin.buffer.readline()
                    if not line: return None
                    if line in (b'\\n', b'\\r\\n'): break
                return sys.stdin.buffer.read(0)
            read_message()
            sys.stdout.buffer.write(b'Content-Length: 1')
            sys.stdout.buffer.flush()
            time.sleep(2)
            """
        ),
        encoding="utf-8",
    )
    return script


def write_oversized_header_server(root: Path) -> Path:
    """Create a server that emits an unterminated oversized header."""
    script = root / "oversized_header_lsp.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys, time
            sys.stdin.buffer.readline()
            sys.stdout.buffer.write(b'X' * (70 * 1024))
            sys.stdout.buffer.flush()
            time.sleep(2)
            """
        ),
        encoding="utf-8",
    )
    return script


def write_stderr_flood_server(root: Path) -> Path:
    """Create a server that writes beyond the stderr retention cap."""
    script = root / "stderr_flood_lsp.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, sys
            def read_message():
                headers = {}
                while True:
                    line = sys.stdin.buffer.readline()
                    if not line: return None
                    if line in (b'\\n', b'\\r\\n'): break
                    key, value = line.decode().split(':', 1)
                    headers[key.lower().strip()] = value.strip()
                return json.loads(sys.stdin.buffer.read(int(headers['content-length'])).decode())
            def send(value):
                payload = json.dumps(value, separators=(',', ':')).encode()
                sys.stdout.buffer.write(f'Content-Length: {len(payload)}\\r\\n\\r\\n'.encode() + payload)
                sys.stdout.buffer.flush()
            while True:
                message = read_message()
                if message is None: break
                method = message.get('method')
                if method == 'initialize':
                    sys.stderr.buffer.write(b'x' * (2 * 1024 * 1024))
                    sys.stderr.buffer.flush()
                    send({'jsonrpc':'2.0','id':message['id'],'result':{'capabilities':{'documentSymbolProvider':True}}})
                elif method == 'textDocument/documentSymbol':
                    send({'jsonrpc':'2.0','id':message['id'],'result':[]})
                elif method == 'shutdown':
                    send({'jsonrpc':'2.0','id':message['id'],'result':None})
                elif method == 'exit':
                    break
            """
        ),
        encoding="utf-8",
    )
    return script


class LspCodeAnalysisTest(unittest.TestCase):
    """Exercise deterministic facts and typed failures."""

    def test_manifest_language_mapping_uses_shared_record_ids(self) -> None:
        """C-family languages share the exact clangd manifest record."""
        self.assertEqual(lsp.LANGUAGE_RECORDS["cpp"], "clangd-language-server")
        self.assertEqual(lsp.LANGUAGE_RECORDS["rust"], "rust-toolchain")

    def test_fake_server_emits_schema_symbols_and_provenance(self) -> None:
        """A fake server produces stable symbols and server provenance."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            server = write_fake_server(root)
            spec = lsp.LspServerSpec(
                "python",
                (sys.executable, "-u", str(server)),
                record_id="fake-python",
                version="test",
            )
            report = lsp.analyze(root, [source], specs={"python": spec})

            self.assertEqual(report.status, "complete")
            payload = report.as_json(root)
            self.assertEqual(payload["schema_version"], lsp.SCHEMA_VERSION)
            self.assertEqual(payload["symbols"][0]["name"], "main")
            self.assertEqual(payload["symbols"][0]["uri"], "main.py")
            self.assertEqual(payload["symbols"][0]["encoding"], "utf-16")
            self.assertEqual(payload["provenance"]["python"]["record"], "fake-python")
            self.assertEqual(payload["servers"][0]["version"], "test")
            self.assertEqual(payload["capabilities"]["python"]["documentSymbolProvider"], "supported_facts")
            self.assertIn("initialize(sent)", payload["lifecycle"]["python"])
            self.assertIn("documentSymbol:main.py", payload["lifecycle"]["python"])

    def test_references_use_each_symbol_selection_position(self) -> None:
        """Reference requests cover every symbol at its UTF-16 selection start."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("\n" * 5, encoding="utf-8")
            server = write_reference_server(root)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="refs")
            report = lsp.analyze(root, [source], specs={"python": spec})
            self.assertEqual(report.status, "complete")
            references = [item for item in report.relations if item.orientation == "reference"]
            self.assertEqual(
                [item.position for item in references],
                [
                    {"line": 1, "character": 2},
                    {"line": 3, "character": 4},
                ],
            )

    def test_optional_definitions_and_call_hierarchy_are_validated(self) -> None:
        """Optional definition and call-hierarchy capabilities produce typed relations."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("import dep\n\n\n\n\n", encoding="utf-8")
            server = write_reference_server(root, include_optional=True)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="optional")
            report = lsp.analyze(root, [source], specs={"python": spec})
            self.assertEqual(report.status, "complete")
            orientations = [item.orientation for item in report.relations]
            self.assertIn("definition", orientations)
            self.assertIn("call-incoming", orientations)
            self.assertIn("call-outgoing", orientations)

    def test_partial_header_is_bounded_by_request_timeout(self) -> None:
        """An unterminated response header fails with the typed timeout."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            server = write_partial_header_server(root)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="partial")
            report = lsp.analyze(root, [source], specs={"python": spec}, timeout=0.1)
            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "request-timeout")

    def test_oversized_header_fails_with_protocol_violation(self) -> None:
        """An unterminated oversized header fails without unbounded buffering."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            server = write_oversized_header_server(root)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="oversized")
            report = lsp.analyze(root, [source], specs={"python": spec}, timeout=1.0)
            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "protocol-violation")

    def test_large_stderr_does_not_deadlock_protocol(self) -> None:
        """Stderr beyond the retention cap is drained while stdout proceeds."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            server = write_stderr_flood_server(root)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="stderr")
            report = lsp.analyze(root, [source], specs={"python": spec}, timeout=1.0)
            self.assertEqual(report.status, "complete")

    def test_outside_root_file_is_typed_path_escape(self) -> None:
        """Files outside the requested root produce a typed failure."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            outside = Path(tmp) / "outside.py"
            outside.write_text("x = 1\n", encoding="utf-8")
            report = lsp.analyze(root, [outside], specs={})
            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "path-escape")

    def test_explicit_symlink_ancestor_is_rejected(self) -> None:
        """Explicit files reached through a symlink ancestor are rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            target = root / "target"
            target.mkdir()
            source = target / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            report = lsp.analyze(root, [link / "main.py"], specs={})
            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "path-escape")

    def test_nonexistent_prefix_cannot_bypass_symlink_rejection(self) -> None:
        """A missing parent followed by ``..`` cannot hide a symlink ancestor."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            target = root / "target"
            target.mkdir()
            (target / "main.py").write_text("x = 1\n", encoding="utf-8")
            (root / "linked").symlink_to(target, target_is_directory=True)
            candidate = root / "missing" / ".." / "linked" / "main.py"
            report = lsp.analyze(root, [candidate], specs={})
            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "path-escape")

    def test_custom_server_requires_absolute_executable(self) -> None:
        """Caller overrides reject bare PATH executable names."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOL), "analyze", "--root", str(root), "--files", "main.py", "--server", "python=pyright-langserver"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("absolute path", result.stderr)

    def test_scan_failure_writes_failed_atomic_report_without_footer(self) -> None:
        """Missing verified manifest executable fails without lexical downgrade."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("import missing\n", encoding="utf-8")
            report_path = root / "analysis.json"
            result = subprocess.run(
                [sys.executable, str(TOOL), "scan-legacy", "--root", str(root), "--files", "main.py", "--analysis-json", str(report_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("CODE_DEPENDENCY_SCAN=pass", result.stdout)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")

    def test_changed_scan_with_clean_git_root_has_no_files(self) -> None:
        """Changed mode does not fall back to scanning default surfaces."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            result = subprocess.run(
                [sys.executable, str(TOOL), "scan-legacy", "--root", str(root), "--changed", "--lexical-only"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "CODE_DEPENDENCY_SCAN=pass files=0")

    def test_lexical_only_preserves_seven_columns(self) -> None:
        """Legacy lexical output retains its seven tab-separated columns."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("import package.module\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOL), "scan-legacy", "--root", str(root), "--files", "main.py", "--lexical-only", "--print-unresolved"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            row = next(line for line in result.stdout.splitlines() if line.startswith("CODE_DEPENDENCY"))
            self.assertEqual(len(row.split("\t")), 7)
            self.assertIn("CODE_DEPENDENCY_SCAN=pass", result.stdout)

    def test_lexical_candidates_resolve_local_modules_and_utf16_columns(self) -> None:
        """Lexical candidates resolve local modules and use LSP character units."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.py").write_text("value = 1\n", encoding="utf-8")
            source = root / "main.py"
            source.write_text("import package\n", encoding="utf-8")
            candidates = lsp._lexical_candidates(root, [source])
            self.assertEqual(candidates[0].target, "package.py")
            self.assertEqual(candidates[0].position["character"], 7)

    def test_python_ast_import_rows_preserve_modules_symbols_and_positions(self) -> None:
        """Python lexical projection keeps module and every imported symbol row."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (
                "pkg/__init__.py",
                "pkg/sub/__init__.py",
                "pkg/bar.py",
                "pkg/bar/__init__.py",
                "pkg/bar/baz.py",
                "pkg/a.py",
                "pkg/a/__init__.py",
                "pkg/a/x.py",
                "pkg/a/y.py",
                "pkg/foo.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            sources = {
                "pkg/sub/relative.py": "from ..bar import baz\n",
                "pkg/absolute.py": "from pkg.a import x, y\n",
                "pkg/local.py": "from . import foo\n",
            }
            source_paths: list[Path] = []
            for relative, contents in sources.items():
                path = root / relative
                path.write_text(contents, encoding="utf-8")
                source_paths.append(path)

            candidates = lsp._lexical_candidates(root, source_paths)
            observed = sorted(
                (
                    item.source,
                    item.legacy_kind,
                    item.token,
                    item.target,
                    item.position["line"] if item.position else None,
                    item.position["character"] if item.position else None,
                )
                for item in candidates
            )
            expected = sorted(
                [
                    (
                        "pkg/sub/relative.py",
                        "import",
                        "..bar",
                        "pkg/bar.py",
                        0,
                        5,
                    ),
                    (
                        "pkg/sub/relative.py",
                        "from-import-symbol",
                        "..bar.baz",
                        "pkg/bar/baz.py",
                        0,
                        18,
                    ),
                    (
                        "pkg/absolute.py",
                        "import",
                        "pkg.a",
                        "pkg/a.py",
                        0,
                        5,
                    ),
                    (
                        "pkg/absolute.py",
                        "from-import-symbol",
                        "pkg.a.x",
                        "pkg/a/x.py",
                        0,
                        18,
                    ),
                    (
                        "pkg/absolute.py",
                        "from-import-symbol",
                        "pkg.a.y",
                        "pkg/a/y.py",
                        0,
                        21,
                    ),
                    (
                        "pkg/local.py",
                        "import",
                        ".",
                        "pkg/__init__.py",
                        0,
                        5,
                    ),
                    (
                        "pkg/local.py",
                        "from-import-symbol",
                        ".foo",
                        "pkg/foo.py",
                        0,
                        14,
                    ),
                ]
            )
            self.assertEqual(observed, expected)
            self.assertNotIn("legacy_kind", candidates[0].as_json())

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "scan-legacy",
                    "--root",
                    str(root),
                    "--files",
                    *(path.relative_to(root).as_posix() for path in source_paths),
                    "--lexical-only",
                    "--print-unresolved",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows = [
                line.split("\t")
                for line in result.stdout.splitlines()
                if line.startswith("CODE_DEPENDENCY\t")
            ]
            self.assertEqual(len(rows), len(expected))
            self.assertTrue(all(len(row) == 7 for row in rows))
            self.assertEqual(
                sorted((row[3], row[2], row[4], row[5]) for row in rows),
                sorted((item[0], item[1], item[3], item[2]) for item in expected),
            )
            self.assertIn("CODE_DEPENDENCY_SCAN=pass files=3", result.stdout)

    def test_malformed_document_symbol_has_no_partial_pass(self) -> None:
        """Malformed required facts never produce a partial successful report."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            server = write_fake_server(root, malformed=True)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="fake")
            report = lsp.analyze(root, [source], specs={"python": spec})
            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "malformed-response")

    def test_outside_symbol_information_fails_as_atomic_cli_report(self) -> None:
        """A SymbolInformation outside root returns typed failure JSON, not a traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            server = write_fake_server(root, outside_symbol=True)
            report_path = root / "analysis.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "scan-legacy",
                    "--root",
                    str(root),
                    "--files",
                    "main.py",
                    "--server",
                    f"python={sys.executable} -u {server}",
                    "--analysis-json",
                    str(report_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("AGENT_SCAN=fail", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["error"]["code"], "path-escape")

    def test_malformed_quiet_frame_fails_closed(self) -> None:
        """Malformed bytes during notification drain are not treated as quiet."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("def main():\n    return 1\n", encoding="utf-8")
            server = write_fake_server(root, malformed_quiet=True)
            spec = lsp.LspServerSpec(
                "python", (sys.executable, "-u", str(server)), record_id="quiet"
            )

            report = lsp.analyze(root, [source], specs={"python": spec})

            self.assertEqual(report.status, "failed")
            self.assertEqual(report.error["code"], "malformed-response")
            self.assertEqual(report.symbols, ())

    def test_pull_diagnostics_preserve_source_and_version(self) -> None:
        """Pull diagnostics are typed and retain source/version provenance."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            server = write_diagnostic_server(root)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="pull")
            report = lsp.analyze(root, [source], specs={"python": spec})
            self.assertEqual(report.status, "complete")
            self.assertEqual(report.diagnostics[0].source, "fake")
            self.assertEqual(report.diagnostics[0].version, 3)
            self.assertEqual(report.capabilities["python"]["diagnostics"], "supported_facts")

    def test_push_diagnostics_are_classified_without_capability_flag(self) -> None:
        """Publish notifications are drained and classified as push facts."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            server = write_diagnostic_server(root, push=True)
            spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(server)), record_id="push")
            report = lsp.analyze(root, [source], specs={"python": spec})
            self.assertEqual(report.status, "complete")
            self.assertEqual(report.diagnostics[0].source, "fake")
            self.assertEqual(report.capabilities["python"]["diagnostics"], "supported_empty")

    def test_malformed_diagnostic_and_nonzero_exit_fail_closed(self) -> None:
        """Malformed diagnostics and non-zero server exits cannot pass."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "main.py"
            source.write_text("x = 1\n", encoding="utf-8")
            malformed_server = write_diagnostic_server(root, malformed=True)
            malformed_spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(malformed_server)), record_id="bad")
            malformed = lsp.analyze(root, [source], specs={"python": malformed_spec})
            self.assertEqual(malformed.status, "failed")
            self.assertEqual(malformed.error["code"], "malformed-response")
            exit_server = write_diagnostic_server(root, exit_code=7)
            exit_spec = lsp.LspServerSpec("python", (sys.executable, "-u", str(exit_server)), record_id="exit")
            exited = lsp.analyze(root, [source], specs={"python": exit_spec})
            self.assertEqual(exited.status, "failed")
            self.assertEqual(exited.error["code"], "server-exit-nonzero")


if __name__ == "__main__":
    unittest.main()
