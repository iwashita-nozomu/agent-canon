<!--
@dependency-start
contract reference
responsibility Documents the canonical LSP 3.17 code-analysis command and report.
upstream design ../structured-analysis/code-analysis.md structured-analysis boundary
upstream design ../design/dependency-manifest-design.md dependency evidence separation
downstream implementation ../../tools/agent_tools/lsp_code_analysis.py owns protocol and report
downstream implementation ../../tools/agent_tools/search.py consumes selected in-memory facts
downstream implementation ../../tests/agent_tools/test_lsp_code_analysis.py verifies golden behavior
@dependency-end
-->

# LSP Code Analysis

`lsp_code_analysis.py` は AgentCanon の code analysis 実行正本です。LSP 3.17
JSON-RPC を一回の session として起動し、結果を
`agent-canon.lsp-code-analysis.v1` JSON に正規化します。index、persistent
cache、ambient PATH discovery は持ちません。

## Commands

```bash
python3 tools/agent_tools/lsp_code_analysis.py analyze \
  --root . --files python/example.py --format json
python3 tools/agent_tools/lsp_code_analysis.py scan-legacy \
  --root . --files python/example.py --analysis-json reports/code-analysis.json
```

`analyze` の stdout は canonical JSON です。`scan-legacy` は既存の
`CODE_DEPENDENCY` 7 列と pass footer を維持し、`--analysis-json FILE` を指定した
ときだけ同じ report を atomic に保存します。`--lexical-only` は server を起動せず、
既存 scanner と同じ lexical evidence だけを返します。

## Contract

サーバーは devcontainer dependency manifest の exact command から選び、公開
`resolve_verified_executable` が absolute path、manifest version、receipt binding、
live verification を再確認した場合だけ起動します。`PATH` や `shutil.which` の
ambient discovery は使いません。`--server LANGUAGE=/absolute/executable ...` は
明示 caller override としてのみ許可され、report provenance に記録されます。
Python、C/C++、Bash、Rust はそれぞれ `pyright-langserver --stdio`、
`clangd-18`、`bash-language-server start`、`rust-analyzer` です。
required `documentSymbolProvider` が提供されない、protocol framing が壊れる、
timeout が発生する、または process が終了する場合、report は `status=failed` と
typed error を持ち、partial facts は成功扱いになりません。

位置は常に UTF-16 で、URI は root-relative POSIX path に正規化します。root 外の
位置は `path-escape` で失敗します。optional capability は capability matrix に
`supported_facts`、`supported_empty`、`unsupported` として記録されます。

push diagnostics は capability flag を仮定せず、短い quiet/drain 区間で受信した
通知だけを `supported_empty` として記録します。pull diagnostics は
`diagnosticProvider` が広告された場合だけ `supported_facts` になります。

`scan-legacy --analysis-json FILE` は complete/failed のどちらでも atomic JSON を
先に書きます。LSP failure は rc=1 と fail stderr で終了し、legacy pass footer や
自動 lexical downgrade は行いません。server を使わない互換出力は、明示した
`--lexical-only` の場合だけ成功します。`--files` を省略した場合は自動検出し、
`--files` を値なしで明示した場合は空選択として扱います。

`scan_code_dependencies.sh --lexical-only --analysis-json` は Rust の `mod`/`use`
を canonical analysis-json sidecar に保存します。Rust は legacy TSV の行を生成せず、
scanner の footer では対象ファイル数だけを報告します。

## Consumer boundary

`search.py --providers code-deps` は server が使用可能な場合だけ一回限りの report
を in-memory で読む。汎用検索、header dependency graph、manifest evidence は
既存 provider のままで、LSP edge と manifest edge の意味を混同しません。
