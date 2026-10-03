<!--
@dependency-start
contract reference
responsibility Documents the canonical LSP 3.17 code-analysis command and report.
upstream design ../structured-analysis/code-analysis.md structured-analysis boundary
upstream design ../design/dependency-manifest-design.md dependency evidence separation
downstream implementation ../../tools/analysis/code/lsp_code_analysis.py owns protocol and report
downstream implementation ../../tools/analysis/search/search.py consumes selected in-memory facts
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
python3 tools/analysis/code/lsp_code_analysis.py analyze \
  --root . --files python/example.py --format json
python3 tools/analysis/code/lsp_code_analysis.py scan-legacy \
  --root . --files python/example.py --analysis-json reports/code-analysis.json
```

`analyze` の stdout は canonical JSON です。`scan-legacy` は既存の
`CODE_DEPENDENCY` 7 列と pass footer を維持し、`--analysis-json FILE` を指定した
ときだけ同じ report を atomic に保存します。`--lexical-only` は server を起動せず、
既存 scanner と同じ lexical evidence だけを返します。

## Recursive Context Collection

コード編集前は、repository の既定実行経路で `analyze` に現在の対象 file を
`--files` で明示します。変更前の seed は依頼対象の symbol、既存 owner / extension
point、caller、test から選びます。`--changed` による編集後の差分収集と分けます。

`analyze` の一回の report はその呼び出しの解析結果です。関連先の本文を自動で
読み込んだ再帰的コンテキストとして扱うには、呼び出し側で次を行います。

1. report の capability / status と relation の source / target location を確認し、
   関連する定義・参照・呼び出し先の実コード、型・実装の契約、tests を読みます。
2. 新たに関連した未確認 file / symbol を次の seed にし、同じ既定経路で明示した
   `--files` を解析します。同一 snapshot の解析済み情報を再利用し、関係を再帰的に
   たどります。各 batch の上限と探索完了を区別し、未確認の関連 frontier を引き継ぎます。
3. 判断に必要な本文・契約の抜粋と revision / path / symbol / line range、関連理由を
   現在の作業コンテキストへ取り込みます。report の保存先は詳細 evidence の locator
   として残し、編集後は変化した symbol と影響する relation を再取得します。

capability matrix に含まれない関係は、その report で解析済みとは判断せず、
既存 owner の対応する LSP 操作または実コード・test の確認で補います。
unsupported / failed / partial / truncated の範囲と次の検証を記録し、補完した
source evidence と LSP evidence を区別します。root 外の対象はその repository の
owner と実行経路で扱い、既存の path / authority boundary を維持します。

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

自動検出は search/vector と共有する bounded LSP surface (`tools`、`agents`、
`.agents`、`documents`、`.codex`、`mcp`、`python`、`src`、`include`、`tests`) に
限定し、`workspace`、`vendor`、
`reports`、build/cache、retired legacy path、symlink、root 外 path を除外します。
明示した file argument は root 内の通常ファイルであることを検証し、symlink は
`path-escape` として拒否します。references は各 document symbol の
`selectionRange.start` ごとに問い合わせ、response の全 location を検証してから
deterministic relation に正規化します。

`scan_code_dependencies.sh --lexical-only --analysis-json` は Rust の `mod`/`use`
を canonical analysis-json sidecar に保存します。Rust は legacy TSV の行を生成せず、
scanner の footer では対象ファイル数だけを報告します。

## Consumer boundary

`search.py --providers code-deps` は server が使用可能な場合だけ一回限りの report
を in-memory で読む。汎用検索、header dependency graph、manifest evidence は
既存 provider のままで、LSP edge と manifest edge の意味を混同しません。
