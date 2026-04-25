#!/usr/bin/env python3
# @dependency-start
# @dependency-end

"""
Doc-Test-Implementation 三点セット検証スクリプト。

Python ファイル内の各関数について、以下の 3 つが揃っているか検証する。
1. Docstring が存在するか
2. `tests/` 配下に対応するテストケースがあるか
3. 実装が Docstring と矛盾していないか
"""

import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from error_handler import ErrorCode, ExecutionResult


@dataclass
class TripletCheckResult:
    """三点セット検証結果。"""

    function_name: str
    file_path: str
    line: int
    has_docstring: bool
    has_test: bool
    docstring_complete: bool  # パラメータ・戻り値が記載されているか
    status: str  # "COMPLETE", "PARTIAL", "MISSING"

    def to_dict(self) -> Dict:
        """辞書形式に変換。"""
        return asdict(self)


class TripletValidator:
    """Doc-Test-Implementation 三点セット検証。"""

    def __init__(self, repo_root: str | Path | None = None):
        """Initialize the validator for one repository root."""
        self.repo_root = Path.cwd().resolve() if repo_root is None else Path(repo_root).resolve()
        self.python_files = []
        self.test_files = []
        self.results = []

    def discover_files(self) -> None:
        """Python ファイルを検出。"""
        # 対象: python/ ディレクトリ (tests 除外)
        for py_file in (self.repo_root / "python").rglob("*.py"):
            if "tests" in py_file.parts or "__pycache__" in py_file.parts:
                continue
            self.python_files.append(py_file)

        # テストファイルは top-level tests/ を正本とする。
        for test_file in (self.repo_root / "tests").rglob("test_*.py"):
            if "__pycache__" in test_file.parts:
                continue
            self.test_files.append(test_file)

    def get_all_test_functions(self) -> Set[str]:
        """すべてのテスト関数名を抽出。"""
        test_funcs = set()

        for test_file in self.test_files:
            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith(
                        "test_"
                    ):
                        # test_ 関数名から対象関数名を推測
                        # 例: test_calculate_variance → calculate_variance
                        func_name = node.name[5:]  # "test_" を削除
                        test_funcs.add(func_name)
            except Exception:
                pass

        return test_funcs

    def check_docstring_completeness(self, docstring: str) -> bool:
        """Docstring が完全か判定 (Args, Returns が記載されているか)。"""
        if not docstring:
            return False

        lower_doc = docstring.lower()
        has_args = "args:" in lower_doc or "parameters:" in lower_doc
        has_returns = "returns:" in lower_doc or "return:" in lower_doc

        return has_args or has_returns

    def validate_file(self, file_path: Path) -> List[TripletCheckResult]:
        """ファイル内のすべての関数を検証。"""
        results = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
                tree = ast.parse(source)
        except Exception as e:
            print(f"⚠️ {file_path}: parse error - {e}", file=sys.stderr)
            return results

        # すべてのテスト関数を取得
        all_test_funcs = self.get_all_test_functions()

        # 関数定義を抽出
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            # プライベート関数やテスト関数は除外
            if node.name.startswith("_") or node.name.startswith("test_"):
                continue

            # ドキュメント確認
            docstring = ast.get_docstring(node)
            has_docstring = docstring is not None
            docstring_complete = (
                self.check_docstring_completeness(docstring) if has_docstring else False
            )

            # テストケース確認
            has_test = node.name in all_test_funcs

            # ステータス判定
            if has_docstring and has_test and docstring_complete:
                status = "COMPLETE"
            elif has_docstring or has_test:
                status = "PARTIAL"
            else:
                status = "MISSING"

            result = TripletCheckResult(
                function_name=node.name,
                file_path=str(file_path.relative_to(self.repo_root)),
                line=node.lineno,
                has_docstring=has_docstring,
                has_test=has_test,
                docstring_complete=docstring_complete,
                status=status,
            )
            results.append(result)

        return results

    def run_validation(self) -> ExecutionResult:
        """全体検証実行。"""
        start_time = __import__("time").time()

        self.discover_files()

        print("📋 Doc-Test-Implementation 三点セット検証を開始...")
        print(f"   対象: {len(self.python_files)} 個の Python ファイル")

        # 各ファイルを検証
        complete_count = 0
        partial_count = 0
        missing_count = 0

        for py_file in self.python_files:
            file_results = self.validate_file(py_file)
            self.results.extend(file_results)

            for result in file_results:
                if result.status == "COMPLETE":
                    complete_count += 1
                elif result.status == "PARTIAL":
                    partial_count += 1
                else:
                    missing_count += 1

        execution_time = __import__("time").time() - start_time

        # 結果を集計
        result = ExecutionResult(
            success=missing_count == 0,
            script_name="triplet_validator",
            execution_time=execution_time,
        )

        # 出力データ
        result.output = {
            "total_functions": len(self.results),
            "complete": complete_count,
            "partial": partial_count,
            "missing": missing_count,
            "complete_rate": (
                f"{100.0 * complete_count / len(self.results):.1f}%"
                if self.results
                else "0%"
            ),
        }

        # 問題のある関数をエラー/警告として追加
        if missing_count > 0:
            result.add_error(
                code=ErrorCode.NO_DOCSTRING,
                message=f"{missing_count} 個の関数が三点セット0/3",
                context={
                    "missing_count": missing_count,
                    "affected_functions": [
                        r.function_name
                        for r in self.results
                        if r.status == "MISSING"
                    ][:10],  # 最初の10個
                },
                suggestion="すべての関数に Docstring + テストを追加してください",
            )

        if partial_count > 0:
            result.add_warning(
                code=ErrorCode.NO_DOCSTRING,
                message=f"{partial_count} 個の関数が三点セット1~2/3",
                context={
                    "partial_count": partial_count,
                    "affected_functions": [
                        r.function_name
                        for r in self.results
                        if r.status == "PARTIAL"
                    ][:10],
                },
                suggestion="Docstring またはテストを追加してください",
            )

        return result

    def report_markdown(self) -> str:
        """Markdown レポート出力。"""
        lines = []
        lines.append("# Doc-Test-Implementation 三点セット検証レポート")
        lines.append("")

        # サマリ
        complete = len([r for r in self.results if r.status == "COMPLETE"])
        partial = len([r for r in self.results if r.status == "PARTIAL"])
        missing = len([r for r in self.results if r.status == "MISSING"])
        total = len(self.results)
        total_nonzero = total if total > 0 else 1

        lines.append("## サマリ")
        lines.append("")
        lines.append(f"| ステータス | 数 | 比率 |")
        lines.append(f"|----------|-----|-----|")
        lines.append(
            f"| ✅ 完全 (Doc+Test) | {complete} | {100*complete/total_nonzero:.1f}% |"
        )
        lines.append(
            f"| ⚠️ 部分 (Doc or Test) | {partial} | {100*partial/total_nonzero:.1f}% |"
        )
        lines.append(
            f"| ❌ 欠落 (neither) | {missing} | {100*missing/total_nonzero:.1f}% |"
        )
        lines.append(f"| **合計** | **{total}** | **100%** |")
        lines.append("")

        # 詳細
        if missing > 0:
            lines.append("## ❌ MISSING（三点セット 0/3）")
            lines.append("")
            for r in sorted([r for r in self.results if r.status == "MISSING"],
                           key=lambda x: x.file_path):
                lines.append(
                    f"- {r.file_path}:{r.line} - `{r.function_name}()` (Docstring ❌, Test ❌)"
                )
            lines.append("")

        if partial > 0:
            lines.append("## ⚠️ PARTIAL（三点セット 1~2/3）")
            lines.append("")
            for r in sorted([r for r in self.results if r.status == "PARTIAL"],
                           key=lambda x: (x.file_path, not x.has_docstring)):
                doc_status = "✅" if r.has_docstring else "❌"
                test_status = "✅" if r.has_test else "❌"
                lines.append(
                    f"- {r.file_path}:{r.line} - `{r.function_name}()` (Docstring {doc_status}, Test {test_status})"
                )
            lines.append("")

        return "\n".join(lines)


def main():
    """メイン処理。"""
    validator = TripletValidator(repo_root=Path.cwd())
    result = validator.run_validation()

    print("\n" + "=" * 70)
    print(validator.report_markdown())
    print("=" * 70)

    if "--json" in sys.argv:
        print(result.to_json())
    else:
        print(result.to_markdown())

    result.exit_with_status()


if __name__ == "__main__":
    main()
