# pre_review.sh スクリプト — 使用ガイド
<!--
@dependency-start
@dependency-end
-->


**ファイル**: `/workspace/tools/ci/pre_review.sh`
**作成日**: 2026-03-21
**用途**: PR 前の自動 QA チェック

---

## 📋 概要

`pre_review.sh` は以下の 4 つの QA チェックを自動実行します：

1. **Type Checking** — Pyright (strict mode)
2. **Test Execution** — pytest
3. **Docstring Validation** — pydocstyle
4. **Code Quality** — Ruff (E, F, I, D, UP)

---

## 🚀 使用方法

### 基本的な実行

```bash
tools/ci/pre_review.sh
```

### 実行例

```bash
$ cd /workspace
$ tools/ci/pre_review.sh

==========================================
PRE-REVIEW QA CHECKS
==========================================

1️⃣  Type Checking (Pyright strict mode)...
✅ Type checking passed

2️⃣  Running pytest...
✅ All tests passed

3️⃣  Docstring validation (pydocstyle)...
✅ Docstring validation passed

4️⃣  Code quality checks (Ruff)...
✅ Code quality checks passed

==========================================
✅ PRE-REVIEW CHECKS COMPLETE
==========================================

Next: Commit changes and open PR
```

---

## ⚙️ 環境要件

### 必須パッケージ

```bash
python3 -m pip install pyright pytest pydocstyle ruff
```

### またはコンテナで実行

```bash
# Docker イメージをビルド（既存）
docker build docker -t project-template:latest

# コンテナ内で実行
docker run -it -v /workspace:/workspace project-template:latest /workspace/tools/ci/pre_review.sh
```

---

## ✅ チェック項目の詳細

### 1. Type Checking (Pyright)

```bash
python3 -m pyright
```

**対象**: `pyproject.toml` の `[tool.pyright]` に含めた Python ファイル
**基準**: Pyright strict mode （pyproject.toml 設定）
**失敗時の対応**: コードを修正して再実行

**主なエラー例**:
- 型注釈なし関数
- 型不一致
- 未定義変数

---

### 2. Test Execution (pytest)

```bash
python3 -m pytest tests/ -q --tb=short
```

**対象**: `tests/` 内の全テスト
**基準**: 全テスト通過
**失敗時の対応**: テストまたは実装を修正して再実行

---

### 3. Docstring Validation (pydocstyle)

```bash
python3 -m pydocstyle python tests
```

**対象**: `python/` 配下の全 Python ファイル
**基準**: pyproject.toml の pydocstyle 設定に準拠
**許容**:

- D104: パッケージ docstring
- D105: プライベートメソッド
- D107: マジックメソッド

**失敗時の対応**: docstring を追加または修正

---

### 4. Code Quality (Ruff)

```bash
python3 -m ruff check python tests --select E,F,I,D,UP
```

**対象**: `python/` 配下の全 Python ファイル
**チェック**:

- **E**: PEP8 エラー
- **F**: Pyflakes（未定義、未使用）
- **I**: isort（import 順序）
- **D**: docstring チェック
- **UP**: pyupgrade（最新構文へ upgrade）

**失敗時の対応**: スタイル or import 順序を修正

---

## 🔄 ワークフロー

### 開発時の手順

```text
1. コード修正
   ↓
2. tools/ci/pre_review.sh 実行
   ↓
3. 全チェック通過?
   ├─ YES: コミット + PR 作成
   └─ NO: エラー修正 → 2 に戻る
```

### 推奨: 毎回実行

```bash
# ブランチ作成時
git checkout -b work/my-feature

# 実装 → 定期的に実行
tools/ci/pre_review.sh

# PR 直前に最終確認
tools/ci/pre_review.sh
```

`vendor/agent-canon/` を触った PR では、`pre_review.sh` だけでは足りません。次を追加します。

```bash
make agent-canon-pr-check
```

---

## 📊 出力例

### 成功ケース

```text
==========================================
PRE-REVIEW QA CHECKS
==========================================

1️⃣  Type Checking (Pyright strict mode)...
✅ Type checking passed

2️⃣  Running pytest...
✅ All tests passed

3️⃣  Docstring validation (pydocstyle)...
✅ Docstring validation passed

4️⃣  Code quality checks (Ruff)...
✅ Code quality checks passed

==========================================
✅ PRE-REVIEW CHECKS COMPLETE
==========================================

Next: Commit changes and open PR
```

### 失敗ケース

```text
==========================================
PRE-REVIEW QA CHECKS
==========================================

1️⃣  Type Checking (Pyright strict mode)...
❌ Type errors found. Review code.

[Pyright の詳細エラー出力...]

tools/ci/pre_review.sh: line 29: exit 1
```

→ 型エラーを修正して再実行

---

## 🛠️ トラブルシューティング

### 問題: "command not found: tools/ci/pre_review.sh"

**原因**: 実行権限がない or パスが間違っている

**対策**:
```bash
# 1. 実行権限確認
ls -l tools/ci/pre_review.sh

# 2. 実行権限がなければ追加
chmod +x tools/ci/pre_review.sh

# 3. フルパスで実行
/workspace/tools/ci/pre_review.sh
```

---

## 問題: "ModuleNotFoundError: No module named 'pyright'"

**原因**: 必須パッケージがインストールされていない

**対策**:
```bash
python3 -m pip install pyright pytest pydocstyle ruff
```

---

## 問題: 特定チェックだけ実行したい

**対策**: スクリプトを編集するか、個別実行

```bash
# Type checking のみ
python3 -m pyright

# pytest のみ
python3 -m pytest tests/ -q

# Ruff のみ
python3 -m ruff check python tests --select E,F,I,D,UP
```

---

## 📈 CI / GitHub Actions との統合

### .github/workflows/ci.yml に統合

```yaml
- name: Run pre-review checks
  run: tools/ci/pre_review.sh
```

### または個別実行

```yaml
- name: Type checking
  run: python3 -m pyright

- name: Run tests
  run: python3 -m pytest tests/ -q

- name: Docstring validation
  run: python3 -m pydocstyle python tests

- name: Code quality
  run: python3 -m ruff check python tests --select E,F,I,D,UP
```

---

## 📝 スクリプトの維持・更新

### 新しいチェック追加時

```bash
# 例: import cycle 検出を追加する場合

# 1. スクリプト編集
nano tools/ci/pre_review.sh

# 2. 新チェック セクション追加
# 5. Import cycle check
echo ""
echo -e "${BLUE}5️⃣  Checking for import cycles...${NC}"
python3 -m pylint --rcfile=.pylintrc python/ 2>/dev/null || true

# 3. テスト
tools/ci/pre_review.sh

# 4. 必要に応じて README 更新
```

---

## ✨ まとめ

| 項目 | 詳細 |
|---|---|
| **作成日** | 2026-03-21 |
| **用途** | PR 前の自動 QA |
| **所要時間** | ~30 秒～2 分 |
| **失敗時の対応** | エラー箇所を修正して再実行 |
| **推奨実行頻度** | 開発時随時 + PR 直前 |

---

**次のステップ**: base テスト JSON ログ統一 → Phase 1 完了へ
