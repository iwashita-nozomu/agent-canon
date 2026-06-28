<!--
@dependency-start
contract policy
responsibility Documents ログ/デバッグ出力の規約（共通） for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
downstream design ./result-log-retention-and-visualization.md defines retention and visualization
@dependency-end
-->

# ログ/デバッグ出力の規約（共通）

この文書は、数値計算およびテストのログ出力を対象にします。

## この文書の読み方

- この文書は、ログ/デバッグ出力の対象、JSON key、保存方針、directory 名、
  禁止事項、JAX 注意点、検証を定めます。
- 主な順路は、対象と目的、基本方針、JSON キー規約、保存方針、
  ディレクトリ名規約、禁止事項、JAX 向けの注意、検証です。
- 数値計算、テスト、HLO 解析のログ形式や保存先を決める前に読みます。
- 境界: retention、summary、可視化 artifact は
  `result-log-retention-and-visualization.md` が正本です。

## 1. 対象と目的

- 対象は、数値計算・テスト・HLO 解析のログ出力です。
- 目的は、標準出力と保存ログの形式を揃え、再現と比較をしやすくすることです。
- 保存期間、配置、summary、可視化 artifact の扱いは
  [result-log-retention-and-visualization.md](result-log-retention-and-visualization.md)
  を正本にします。

## 2. 基本方針

- 数値計算のログは **1 行 1 レコード** を基本とします。
- 出力方法は **標準出力を基本**とし、必要に応じて標準出力を転送します。
- 出力形式は **JSONL（1 行 1 JSON）** を採用し、**バイナリは使いません**。
- ログは **実行ごとにディレクトリを分けて保存**します。
- ログを書き出す、emit する、保存する、整形する helper 関数は Python では `_log` から始めます。
  例: `_log_case_record`、`_log_jsonl_line`、`_log_runtime_event`。
- `write_log_*`、`append_log_*`、`emit_log_*`、`record_log_*`、`format_log_*` のような helper 名は使いません。
  ログ helper であることと private helper であることを同時に示すため、`_log...` へ寄せます。

## 3. JSON キー規約

- `source_file`: ログを出すファイル名（例: `kkt_solver.py`）。
- `func`: 関数名（例: `kkt_block_solver`）。
- `iter`: 反復回数（数値）。
- 変数の種類を示す接頭辞を使います（例: `res_norm`, `rel_err`, `step_size`）。
- 変数名と一致させる場合は **スネークケース**で統一します。

### 3.1 HLO 解析ログ

- HLO 解析は **重い処理**になり得るため、既定で無効にします。有効化はフラグ指定時だけ許可します。
- 形式は通常ログと同様に **JSONL（1 行 1 JSON）** とします。
- 推奨キー例:
  - `case`: `"hlo"`
  - `tag`: 解析対象の識別子
  - `dialect`: `"stablehlo"` / `"hlo"`
  - `hlo`: HLO 文字列

## 4. 保存方針

- 実装時は標準出力で出力し、必要に応じて **標準出力の転送**で保存します。
- ログ保存用ディレクトリは `tests/logs/` を推奨し、**`.gitignore` に登録**します。
- 実行ごとにサブディレクトリを作り、**その中へログを保存**します。
- テスト実行ログは **生ログ**と **JSONL** を分離して保存します。
  - `pytest.raw.txt`: 進捗や例外を含む生ログ
  - `pytest.jsonl`: JSON オブジェクトのみ（1 行 1 JSON）
  - `exit_code.txt`: 終了コード（数値のみ）
- 実験や benchmark の raw result は `experiments/<topic>/result/<run-id>/` に置き、
  human-readable report は `experiments/report/<run-id>.md` に置きます。
- user-facing claim の根拠になる run は、raw log だけでなく `summary.json`、
  Markdown report、または compact JSONL summary を残します。

## 5. ディレクトリ名規約（ログ）

- 形式: `tests/logs/[YYYYMMDD]-[HHMMSS]`
- 角括弧 `[]` を **必ず**入れます。

## 6. 禁止事項

- バイナリ形式でのログ出力は禁止します。
- 1 行に複数レコードを詰めないでください。
- `pytest.jsonl` に **JSON 以外の行を混ぜない**でください。
- ログ用 helper 関数を `_log` 以外の prefix で定義してはいけません。

## 7. JAX 向けの注意

- JAX では `jax.debug.print` を使い、`DEBUG` ガードで制御します。

## 8. 検証

```bash
python3 tools/agent_tools/check_log_helper_names.py --changed --exclude vendor --exclude reports
```

結果ログと可視化 helper:

```bash
python3 tools/data/jsonl_to_md.py <input.jsonl> <output.md>
python3 tools/hlo/summarize_hlo_jsonl.py <hlo.jsonl> > summary.json
dot -V
```
