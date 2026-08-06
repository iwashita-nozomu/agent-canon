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
