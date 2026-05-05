#!/usr/bin/env python3
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
"""
Week 1 Implementation Verification

実装したすべてのコンポーネントが正しくセットアップされているか確認
"""

import sys
from pathlib import Path


def verify_file_structure():
    """ファイル構造を検証"""
    print("\n📁 Verifying File Structure...")
    
    required_files = [
        # Security Foundation
        "scripts/audit/audit_logger.py",
        "scripts/audit/audit_log_schema.py",
        "scripts/security/rbac_manager.py",
        "scripts/security/secrets_vault.py",
        
        # Testing
        "python/tests/test_week1_security.py",
        "scripts/run_week1_tests.py",
        
        # GitHub Actions
        ".github/workflows/week1-security.yml",
        
        # Environment Setup
        "scripts/setup_week1_env.py",
        
        # Skill 1 Checkers
        ".github/skills/01-static-check/checkers/type_checker.py",
        ".github/skills/01-static-check/checkers/test_runner.py",
        ".github/skills/01-static-check/checkers/docker_validator.py",
        ".github/skills/01-static-check/checkers/coverage_analyzer.py",
        ".github/skills/01-static-check/run-check.py",
    ]
    
    workspace_root = Path("/workspace")
    missing_files = []
    
    for file_path in required_files:
        full_path = workspace_root / file_path
        if full_path.exists():
            size_kb = full_path.stat().st_size / 1024
            print(f"  ✅ {file_path:50s} ({size_kb:6.1f} KB)")
        else:
            print(f"  ❌ {file_path}")
            missing_files.append(file_path)
    
    return len(missing_files) == 0


def verify_imports():
    """モジュールインポートを検証"""
    print("\n🔍 Verifying Module Imports...")
    
    sys.path.insert(0, "/workspace/scripts")
    sys.path.insert(0, "/workspace/.github/skills/01-static-check/checkers")
    
    tests = [
        ("Audit Logger", lambda: __import__("audit.audit_logger", fromlist=["AuditLogger"])),
        ("Audit Schema", lambda: __import__("audit.audit_log_schema", fromlist=["AuditLogEntry"])),
        ("RBAC Manager", lambda: __import__("security.rbac_manager", fromlist=["RBACManager"])),
        ("Secrets Vault", lambda: __import__("security.secrets_vault", fromlist=["SecretsVault"])),
        ("Type Checker", lambda: __import__("type_checker", fromlist=["PyrightChecker"])),
        ("Test Runner", lambda: __import__("test_runner", fromlist=["TestRunner"])),
        ("Docker Validator", lambda: __import__("docker_validator", fromlist=["DockerValidator"])),
        ("Coverage Analyzer", lambda: __import__("coverage_analyzer", fromlist=["CoverageAnalyzer"])),
    ]
    
    success = True
    for name, import_fn in tests:
        try:
            import_fn()
            print(f"  ✅ {name}")
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            success = False
        except Exception as e:
            print(f"  ⚠️  {name}: {e}")
    
    return success


def verify_dependencies():
    """依存関係を確認"""
    print("\n📦 Verifying Dependencies...")
    
    required_packages = [
        "jsonschema",
        "cryptography",
        "pydantic",
        "pyright",
        "pytest",
    ]
    
    success = True
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} (not installed)")
            success = False
    
    return success


def verify_directory_structure():
    """ディレクトリ構造を確認"""
    print("\n📂 Verifying Directory Structure...")
    
    required_dirs = [
        "reports/audit",
        "scripts/audit",
        "scripts/security",
        "scripts/security/vault",
        ".github/skills/01-static-check/checkers",
    ]
    
    workspace_root = Path("/workspace")
    all_exist = True
    
    for dir_path in required_dirs:
        full_path = workspace_root / dir_path
        if full_path.exists() and full_path.is_dir():
            print(f"  ✅ {dir_path}/")
        else:
            print(f"  ❌ {dir_path}/ (missing)")
            all_exist = False
    
    return all_exist


def main():
    """メイン検証"""
    print("\n" + "=" * 60)
    print("Week 1 Implementation Verification")
    print("=" * 60)
    
    results = {
        "File Structure": verify_file_structure(),
        "Directory Structure": verify_directory_structure(),
        "Module Imports": verify_imports(),
        "Dependencies": verify_dependencies(),
    }
    
    print("\n" + "=" * 60)
    print("Verification Results")
    print("=" * 60)
    
    all_ok = True
    for check, result in results.items():
        status = "✅ PASS" if result else "⚠️  WARN"
        print(f"{check:.<40} {status}")
        if not result:
            all_ok = False
    
    print("\n" + "=" * 60)
    if all_ok:
        print("✨ All verifications passed!")
        print("\nNext Steps:")
        print("1. Run: python3 scripts/setup_week1_env.py --init")
        print("2. Run: python3 scripts/run_week1_tests.py --verbose")
        print("3. Run: python3 .github/skills/01-static-check/run-check.py")
        print("4. Commit changes: git add -A && git commit")
        return 0
    else:
        print("⚠️  Some verifications failed. Check output above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
