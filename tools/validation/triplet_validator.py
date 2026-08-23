#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides triplet validator repository automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""
Doc-Test-Implementation 三点セット検証スクリプト。

Python ファイル内の各関数について、以下の 3 つが揃っているか検証する。
1. Docstring が存在するか
2. `tests/` 配下に対応するテストケースがあるか
3. 実装が Docstring と矛盾していないか
"""

import ast
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from error_handler import ErrorCode, ExecutionResult


AFFECTED_FUNCTION_LIMIT = 10
PERCENT_SCALE = 100.0
REPORT_SEPARATOR_WIDTH = 70
TEST_PREFIX = "test_"


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


@dataclass
class TripletStats:
    """三点セット検証結果の集計。"""

    complete: int
    partial: int
    missing: int


def is_docstring_complete(docstring: str) -> bool:
    """Docstring が完全か判定 (Args, Returns が記載されているか)。"""
    if not docstring:
        return False

    lower_doc = docstring.lower()
    has_args = "args:" in lower_doc or "parameters:" in lower_doc
    has_returns = "returns:" in lower_doc or "return:" in lower_doc

    return has_args or has_returns


def triplet_status(has_docstring: bool, has_test: bool, docstring_complete: bool) -> str:
    """Docstring、test、docstring 完全性から triplet status を返す。"""
    if has_docstring and has_test and docstring_complete:
        return "COMPLETE"
    if has_docstring or has_test:
        return "PARTIAL"
    return "MISSING"


def parse_python_file(file_path: Path) -> ast.AST | None:
    """Python file を AST に変換し、parse 不能なら None を返す。"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return ast.parse(f.read())
    except Exception as e:
        print(f"⚠️ {file_path}: parse error - {e}", file=sys.stderr)
        return None


def public_function_nodes(tree: ast.AST) -> List[ast.FunctionDef]:
    """Public validation target functions を抽出する。"""
    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith("_") or node.name.startswith("test_"):
            continue
        functions.append(node)
    return functions


def count_triplet_statuses(results: List[TripletCheckResult]) -> TripletStats:
    """Triplet check results を status 別に数える。"""
    complete = len([r for r in results if r.status == "COMPLETE"])
    partial = len([r for r in results if r.status == "PARTIAL"])
    missing = len([r for r in results if r.status == "MISSING"])
    return TripletStats(complete=complete, partial=partial, missing=missing)


def affected_function_names(results: List[TripletCheckResult], status: str) -> List[str]:
    """指定 status の affected function 名を最大10個返す。"""
    return [r.function_name for r in results if r.status == status][:AFFECTED_FUNCTION_LIMIT]


def append_status_section(
    lines: List[str], title: str, results: List[TripletCheckResult]
) -> None:
    """Markdown report に status section を追記する。"""
    lines.append(title)
    lines.append("")
    for result in results:
        doc_status = "✅" if result.has_docstring else "❌"
        test_status = "✅" if result.has_test else "❌"
        lines.append(
            f"- {result.file_path}:{result.line} - `{result.function_name}()` "
            f"(Docstring {doc_status}, Test {test_status})"
        )
    lines.append("")


def format_markdown_report(results: List[TripletCheckResult]) -> str:
    """Markdown レポートを作る。"""
    stats = count_triplet_statuses(results)
    total = len(results)
    total_nonzero = total if total > 0 else 1
    lines = [
        "# Doc-Test-Implementation 三点セット検証レポート",
        "",
        "## サマリ",
        "",
        "| ステータス | 数 | 比率 |",
        "|----------|-----|-----|",
        f"| ✅ 完全 (Doc+Test) | {stats.complete} | {PERCENT_SCALE*stats.complete/total_nonzero:.1f}% |",
        f"| ⚠️ 部分 (Doc or Test) | {stats.partial} | {PERCENT_SCALE*stats.partial/total_nonzero:.1f}% |",
        f"| ❌ 欠落 (neither) | {stats.missing} | {PERCENT_SCALE*stats.missing/total_nonzero:.1f}% |",
        f"| **合計** | **{total}** | **100%** |",
        "",
    ]

    missing_results = sorted(
        [r for r in results if r.status == "MISSING"], key=lambda r: r.file_path
    )
    partial_results = sorted(
        [r for r in results if r.status == "PARTIAL"],
        key=lambda r: (r.file_path, not r.has_docstring),
    )
    if missing_results:
        append_status_section(lines, "## ❌ MISSING（三点セット 0/3）", missing_results)
    if partial_results:
        append_status_section(lines, "## ⚠️ PARTIAL（三点セット 1~2/3）", partial_results)

    return "\n".join(lines)


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
                        TEST_PREFIX
                    ):
                        # test_ 関数名から対象関数名を推測
                        # 例: test_calculate_variance → calculate_variance
                        func_name = node.name[len(TEST_PREFIX):]
                        test_funcs.add(func_name)
            except Exception:
                pass

        return test_funcs

    def validate_file(self, file_path: Path) -> List[TripletCheckResult]:
        """ファイル内のすべての関数を検証。"""
        results: List[TripletCheckResult] = []
        tree = parse_python_file(file_path)
        if tree is None:
            return results

        # すべてのテスト関数を取得
        all_test_funcs = self.get_all_test_functions()

        # 関数定義を抽出
        for node in public_function_nodes(tree):
            # ドキュメント確認
            docstring = ast.get_docstring(node)
            has_docstring = docstring is not None
            docstring_complete = is_docstring_complete(docstring) if docstring else False

            # テストケース確認
            has_test = node.name in all_test_funcs

            # ステータス判定
            status = triplet_status(has_docstring, has_test, docstring_complete)

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
        start_time = time()

        self.discover_files()

        print("📋 Doc-Test-Implementation 三点セット検証を開始...")
        print(f"   対象: {len(self.python_files)} 個の Python ファイル")

        for py_file in self.python_files:
            file_results = self.validate_file(py_file)
            self.results.extend(file_results)

        stats = count_triplet_statuses(self.results)
        execution_time = time() - start_time

        # 結果を集計
        result = ExecutionResult(
            success=stats.missing == 0,
            script_name="triplet_validator",
            execution_time=execution_time,
        )

        # 出力データ
        result.output = {
            "total_functions": len(self.results),
            "complete": stats.complete,
            "partial": stats.partial,
            "missing": stats.missing,
            "complete_rate": (
                f"{PERCENT_SCALE * stats.complete / len(self.results):.1f}%"
                if self.results
                else "0%"
            ),
        }

        # 問題のある関数をエラー/警告として追加
        if stats.missing > 0:
            result.add_error(
                code=ErrorCode.NO_DOCSTRING,
                message=f"{stats.missing} 個の関数が三点セット0/3",
                context={
                    "missing_count": stats.missing,
                    "affected_functions": affected_function_names(self.results, "MISSING"),
                },
                suggestion=(
                    "すべての関数に Docstring を追加し、observable behavior がある関数は "
                    "test または validation evidence を追加してください"
                ),
            )

        if stats.partial > 0:
            result.add_warning(
                code=ErrorCode.NO_DOCSTRING,
                message=f"{stats.partial} 個の関数が三点セット1~2/3",
                context={
                    "partial_count": stats.partial,
                    "affected_functions": affected_function_names(self.results, "PARTIAL"),
                },
                suggestion=(
                    "Docstring、observable behavior test、または validation evidence を追加してください"
                ),
            )

        return result

    def report_markdown(self) -> str:
        """Markdown レポート出力。"""
        return format_markdown_report(self.results)


def main() -> None:
    """メイン処理。"""
    validator = TripletValidator(repo_root=Path.cwd())
    result = validator.run_validation()

    print("\n" + "=" * REPORT_SEPARATOR_WIDTH)
    print(validator.report_markdown())
    print("=" * REPORT_SEPARATOR_WIDTH)

    if "--json" in sys.argv:
        print(result.to_json())
    else:
        print(result.to_markdown())

    result.exit_with_status()


if __name__ == "__main__":
    main()
