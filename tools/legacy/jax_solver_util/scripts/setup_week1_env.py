#!/usr/bin/env python3
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
"""
Week 1 Environment Setup Script

GitHub Secrets と環境変数を初期化するテンプレート。
setup.sh または Makefile から呼び出す想定。

使用方法:
  python3 scripts/setup_week1_env.py --init
  python3 scripts/setup_week1_env.py --verify
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class EnvVar:
    """環境変数定義"""
    name: str
    description: str
    required: bool = True
    default: Optional[str] = None
    secret: bool = False


# 必須環境変数
REQUIRED_ENV_VARS = [
    # Audit
    EnvVar(
        name="AUDIT_LOG_DIR",
        description="監査ログディレクトリ",
        default="reports/audit",
    ),
    
    # RBAC
    EnvVar(
        name="RBAC_CONFIG_DIR",
        description="RBAC 設定ディレクトリ",
        default="scripts/security",
    ),
    
    # Secrets
    EnvVar(
        name="SECRETS_VAULT_DIR",
        description="シークレットボルトディレクトリ",
        default="scripts/security/vault",
    ),
    
    # GitHub API（本番環境用）
    EnvVar(
        name="GITHUB_TOKEN",
        description="GitHub API token",
        required=False,
        secret=True,
    ),
    
    # Database（将来用）
    EnvVar(
        name="DATABASE_URL",
        description="Database connection string",
        required=False,
        secret=True,
    ),
    
    # Python
    EnvVar(
        name="PYTHONPATH",
        description="Python import path",
        default="/workspace/python",
    ),
]


def init_directories() -> bool:
    """必要なディレクトリを初期化"""
    print("\n📁 Initializing Directories...")
    
    dirs_to_create = [
        Path("reports/audit"),
        Path("scripts/security/vault"),
        Path(".github/logs"),
    ]
    
    for dir_path in dirs_to_create:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ {dir_path}/")
        except Exception as e:
            print(f"  ❌ Failed to create {dir_path}: {e}")
            return False
    
    return True


def init_env_file() -> bool:
    """`.env.example` ファイルを初期化"""
    print("\n📝 Creating .env.example...")
    
    env_content = "# Week 1 Environment Variables\n"
    env_content += "# .env.example - DO NOT COMMIT SECRETS\n\n"
    
    for var in REQUIRED_ENV_VARS:
        if var.secret:
            env_content += f"# SECRET (setup via GitHub Secrets)\n"
            env_content += f"{var.name}=YOUR_{var.name}_HERE\n"
        else:
            default = var.default or "value"
            env_content += f"# {var.description}\n"
            env_content += f"{var.name}={default}\n"
        env_content += f"# Description: {var.description}\n\n"
    
    try:
        with open(".env.example", "w", encoding="utf-8") as f:
            f.write(env_content)
        print("  ✅ .env.example created")
        return True
    except Exception as e:
        print(f"  ❌ Failed to create .env.example: {e}")
        return False


def init_env_vars() -> bool:
    """環境変数を OS に設定"""
    print("\n🔧 Setting Environment Variables...")
    
    for var in REQUIRED_ENV_VARS:
        if var.secret:
            print(f"  ⏭️  Skipping secret: {var.name} (set via GitHub Secrets)")
            continue
        
        value = os.getenv(var.name) or var.default
        if value:
            os.environ[var.name] = value
            print(f"  ✅ {var.name}={value}")
        elif var.required:
            print(f"  ⚠️  {var.name} not set (required)")
    
    return True


def verify_env() -> bool:
    """環境変数をバリデーション"""
    print("\n✓ Verifying Environment...")
    
    all_ok = True
    
    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var.name)
        
        if value:
            display_value = "***" if var.secret else value
            print(f"  ✅ {var.name}: {display_value}")
        elif var.required and not var.secret:
            print(f"  ❌ {var.name}: NOT SET (required)")
            all_ok = False
        else:
            print(f"  ⚠️  {var.name}: optional or secret")
    
    return all_ok


def init_github_secrets_guide() -> None:
    """GitHub Secrets 設定ガイドを出力"""
    print("\n📖 GitHub Secrets Setup Guide")
    print("=" * 60)
    print("""
To set up GitHub Secrets:
1. Go to: https://github.com/your-repo/settings/secrets/actions
2. Click "New repository secret"
3. Add the following secrets:

Secret Name             | Description
------------------------+----------------------------------------
GITHUB_TOKEN            | GitHub API token (PAT) for automation
DATABASE_URL            | Database connection string
BUILD_WEBHOOK_SECRET    | Webhook secret for CI/CD
""")
    
    print("\nOr use GitHub CLI:")
    print("  gh secret set GITHUB_TOKEN --body 'token_value'")
    print("  gh secret set DATABASE_URL --body 'connection_string'")


def generate_report() -> Dict:
    """セットアップレポートを生成"""
    report = {
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "directories": {
            "audit": Path("reports/audit").exists(),
            "rbac": Path("scripts/security").exists(),
            "vault": Path("scripts/security/vault").exists(),
        },
        "environment": {},
        "files": {
            ".env.example": Path(".env.example").exists(),
        },
    }
    
    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var.name)
        report["environment"][var.name] = {
            "set": value is not None,
            "description": var.description,
            "secret": var.secret,
        }
    
    return report


def main():
    """メイン"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Week 1 Environment Setup")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize directories and environment",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify environment setup",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate setup report",
    )
    parser.add_argument(
        "--secrets-guide",
        action="store_true",
        help="Show GitHub Secrets setup guide",
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("Week 1 Environment Setup Tool")
    print("=" * 60)
    
    success = True
    
    if args.init:
        success = (
            init_directories() and
            init_env_file() and
            init_env_vars()
        )
    
    if args.verify or (not args.init and not args.secrets_guide and not args.report):
        success = verify_env() and success
    
    if args.secrets_guide:
        init_github_secrets_guide()
    
    if args.report:
        report = generate_report()
        print("\n📊 Setup Report:")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    if success:
        print("✅ Setup completed successfully")
        return 0
    else:
        print("⚠️  Setup completed with warnings")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
