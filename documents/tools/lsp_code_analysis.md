<!--
@dependency-start
contract reference
responsibility Documents the canonical LSP 3.17 code-analysis command, transport boundary, and report.
upstream design ../structured-analysis/code-analysis.md structured-analysis boundary
upstream design ../design/dependency-manifest-design.md dependency evidence separation
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/lsp_code_analysis.rs owns the native API, process lifecycle, and report
downstream implementation ../../tools/analysis/search/search.py consumes selected in-memory facts
downstream implementation ../../tests/agent_tools/test_lsp_code_analysis.py verifies golden behavior
downstream test ../../tools/runtime/dispatch/agent-canon/tests/lsp_code_analysis_native.rs verifies the native provider
@dependency-end
-->

# LSP Code Analysis

`lsp_code_analysis.rs` は登録された `lsp-code-analysis` CLI と再利用可能な
library API の実装 owner です。LSP 3.17 JSON-RPC を一回の session として起動し、結果を
`agent-canon.lsp-code-analysis.v1` JSON に正規化します。index、persistent
cache、ambient PATH discovery は持ちません。

## Commands

```bash
tools/bin/agent-canon lsp-code-analysis analyze \
  --root . --files python/example.py --format json
```

`analyze` is a point LSP request and writes its report to stdout. It does not
maintain a repository-wide index or emit legacy dependency TSV rows.

## Contract

サーバーは devcontainer dependency manifest の exact command から選び、公開
`resolve_verified_executable` が absolute path、manifest version、receipt binding、
live verification を再確認した場合だけ起動します。`PATH` や `shutil.which` の
ambient discovery は使いません。`--server LANGUAGE=/absolute/executable ...` は
明示 caller override としてのみ許可され、report provenance に記録されます。
Python、C/C++、Bash、Rust はそれぞれ `pyright-langserver --stdio`、
`clangd-18`、`bash-language-server start`、`rust-analyzer` です。

JSON-RPC framing と request correlation は既存の `lsp-server` 0.10.0
`Message::read` / `Message::write` と `ReqQueue` が担当します。LSP owner はその
library を verified server child の stdin/stdout pipes に接続し、stderr drain、
request timeout、process/thread cleanup、report と root-bound result validation を維持します。

required `documentSymbolProvider` が提供されない、reader error が adapter に届く、
request timeout が発生する、または server process が異常終了する場合、report は
`status=failed` と typed error を持ち、partial facts は成功扱いになりません。
upstream reader が malformed JSON をログして破棄し、response が届かない場合は、
bounded request timeout として報告します。

位置は常に UTF-16 で、URI は root-relative POSIX path に正規化します。root 外の
位置は `path-escape` で失敗します。optional capability は capability matrix に
`supported_facts`、`supported_empty`、`unsupported` として記録されます。

push diagnostics は capability flag を仮定せず、background reader が短い
quiet/drain 区間内に受信した通知だけを `supported_empty` として記録します。pull
diagnostics は `diagnosticProvider` が広告された場合だけ `supported_facts` になります。

`--files` を省略した場合は point-analysis owner の bounded source surfaces から
対象を検出し、`--files` を値なしで明示した場合は空選択として扱います。

自動検出はこの LSP owner が管理する bounded source surface (`tools`、`agents`、
`.agents`、`documents`、`.codex`、`mcp`、`python`、`src`、`include`、`tests`) に
限定し、`workspace`、`vendor`、
`reports`、build/cache、retired legacy path、symlink、root 外 path を除外します。
明示した file argument は root 内の通常ファイルであることを検証し、symlink は
`path-escape` として拒否します。references は各 document symbol の
`selectionRange.start` ごとに問い合わせ、response の全 location を検証してから
deterministic relation に正規化します。

## Consumer boundary

Native callers use this library API for one-shot analysis and receive unfiltered facts.
The existing Python `search.py` and Git-diff language-mapper callers continue using their
current Python owner until their own native migrations close; this native command does not
provide a Python shim or fallback. A future native Search consumer owns exact-query filtering.
LSP failures remain failures, without AST heuristics or fallback to another provider.
Generic text search, the header dependency graph, and manifest evidence stay with their
respective owners; LSP edges and manifest edges remain distinct.
