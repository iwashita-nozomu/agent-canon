#!/usr/bin/env python3
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
"""
Week 1 Test Runner — セキュリティ基盤の検証

実行方法:
  python3 scripts/run_week1_tests.py --verbose
  
実行環境:
  - Docker コンテナ内推奨
  - PYTHONPATH=/workspace/python
"""

import sys
import subprocess
import json
from pathlib import Path
from typing import Tuple


def run_test(test_name: str, test_script: Path) -> Tuple[bool, str]:
    """テストを実行
    
    Args:
        test_name: テスト名
        test_script: テストスクリプトパス
    
    Returns:
        (成功/失敗, 出力)
    """
    print(f"\n▶️  Running: {test_name}")
    print("-" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"✅ {test_name} PASSED")
            return True, result.stdout
        else:
            print(f"❌ {test_name} FAILED")
            if result.stderr:
                print(f"Error output:\n{result.stderr}")
            return False, result.stderr
    
    except subprocess.TimeoutExpired:
        msg = f"❌ {test_name} TIMEOUT"
        print(msg)
        return False, msg
    except Exception as e:
        msg = f"❌ {test_name} ERROR: {e}"
        print(msg)
        return False, msg


def main():
    """メイン テストランナー"""
    print("\n" + "=" * 60)
    print("Week 1 Security Integration Test Suite")
    print("=" * 60)
    
    workspace_root = Path(__file__).parent.parent
    test_dir = workspace_root / "python" / "tests"
    
    # テスト一覧
    tests = [
        ("Security Integration Tests", test_dir / "test_week1_security.py"),
    ]
    
    results = {
        "total": len(tests),
        "passed": 0,
        "failed": 0,
        "tests": [],
    }
    
    # テスト実行
    for test_name, test_script in tests:
        if not test_script.exists():
            print(f"\n⚠️  Test script not found: {test_script}")
            results["tests"].append({
                "name": test_name,
                "status": "skipped",
                "reason": "script not found",
            })
            continue
        
        success, output = run_test(test_name, test_script)
        
        if success:
            results["passed"] += 1
            results["tests"].append({
                "name": test_name,
                "status": "passed",
            })
        else:
            results["failed"] += 1
            results["tests"].append({
                "name": test_name,
                "status": "failed",
                "error": output[:200],
            })
    
    # 結果サマリー
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total:  {results['total']}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    
    if "--json" in sys.argv:
        print("\n" + json.dumps(results, indent=2, ensure_ascii=False))
    
    # 終了コード
    if results['failed'] == 0:
        print("\n🎉 All Week 1 tests passed!")
        return 0
    else:
        print(f"\n⚠️  {results['failed']} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
