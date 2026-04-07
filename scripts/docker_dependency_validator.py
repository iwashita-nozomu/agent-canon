#!/usr/bin/env python3
"""
Docker 環境依存関係検証スクリプト。

Dockerfile ⟷ requirements.txt の同期を確認。
仮想環境（.venv, venv）の禁止を検証。
PYTHONPATH 設定を確認。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIREMENT_LINE_RE = re.compile(
    r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,.\-]+\])?(\s*(==|>=|<=|~=|!=|>|<).+)?$"
)
VENV_COMMAND_RE = re.compile(
    r"\b(python3?\s+-m\s+venv|virtualenv|conda\s+create)\b",
    re.IGNORECASE,
)


def check_requirements_format() -> list[str]:
    """requirements.txt の形式をチェック。"""
    issues = []
    req_file = Path("docker/requirements.txt")

    if not req_file.exists():
        issues.append("docker/requirements.txt not found")
        return issues

    content = req_file.read_text(encoding="utf-8")

    for line_num, line in enumerate(content.split("\n"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue

        if not REQUIREMENT_LINE_RE.match(line):
            issues.append(f"Line {line_num}: invalid requirement syntax: {line}")

    return issues


def check_dockerfile_coherence() -> list[str]:
    """Dockerfile と requirements.txt の一貫性をチェック。"""
    issues = []
    dockerfile = Path("docker/Dockerfile")
    req_file = Path("docker/requirements.txt")

    if not dockerfile.exists():
        issues.append("docker/Dockerfile not found")
        return issues

    dockerfile_content = dockerfile.read_text(encoding="utf-8")
    req_file_content = req_file.read_text(encoding="utf-8") if req_file.exists() else ""

    # 1. Dockerfile が requirements.txt を参照しているか確認
    if "requirements.txt" not in dockerfile_content:
        issues.append("Dockerfile does not reference requirements.txt")

    # 2. pip install の PATH 確認
    pip_install_match = re.search(
        r"RUN pip install.*-r\s+(\S+)", dockerfile_content
    )
    if pip_install_match:
        req_path = pip_install_match.group(1)
        if "requirements.txt" not in req_path:
            issues.append(f"Dockerfile pip install path may be incorrect: {req_path}")

    # 3. requirements.txt に listed されたパッケージが Dockerfile にも反映されているか
    req_packages = set()
    for line in req_file_content.split("\n"):
        if line.strip() and not line.startswith("#"):
            match = re.match(r"^([a-zA-Z0-9_\-]+)", line)
            if match:
                req_packages.add(match.group(1).lower())

    # Dockerfile で pip install される packages をチェック
    for package in req_packages:
        if f"pip install.*{package.lower()}" not in dockerfile_content.lower():
            # requirements.txt 経由でのインストールなので無視
            pass

    return issues


def check_venv_prohibition() -> list[str]:
    """仮想環境（.venv, venv）の禁止を確認。"""
    issues = []

    # git の対象外チェック
    for venv_dir in [".venv", "venv", "env", ".conda", "conda-env"]:
        path = Path(venv_dir)
        if path.exists():
            issues.append(f"仮想環境ディレクトリが存在: {venv_dir}")
    for path in Path(".").glob(".venv-*"):
        issues.append(f"仮想環境ディレクトリが存在: {path}")

    # .gitignore でexclude されているか確認
    gitignore = Path(".gitignore")
    if gitignore.exists():
        gitignore_content = gitignore.read_text(encoding="utf-8")
        if ".venv" not in gitignore_content and "venv/" not in gitignore_content:
            issues.append(".venv/venv not explicitly excluded in .gitignore")

    # コード内で仮想環境作成コマンドがあるか確認
    current_file = Path(__file__).resolve()
    for file in Path("scripts").rglob("*"):
        if (
            not file.is_file()
            or "__pycache__" in file.parts
            or file.suffix == ".pyc"
            or file.resolve() == current_file
        ):
            continue
        try:
            content = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if VENV_COMMAND_RE.search(content):
            issues.append(f"Found virtual-environment creation command in {file}")

    return issues


def check_pythonpath_documentation() -> list[str]:
    """PYTHONPATH の設定がドキュメント化されているか確認。"""
    issues = []

    readme_files = [
        Path("README.md"),
        Path("QUICK_START.md"),
        Path("documents/coding-conventions-project.md"),
    ]
    pythonpath_documented = False

    for readme in readme_files:
        if readme.exists():
            content = readme.read_text(encoding="utf-8")
            if "PYTHONPATH" in content and "=/workspace/python" in content:
                pythonpath_documented = True
                break

    if not pythonpath_documented:
        issues.append("PYTHONPATH=/workspace/python not documented in README/QUICK_START")

    # Docker 実行ガイドが含まれているか確認
    docker_documented = False
    for readme in readme_files:
        if readme.exists():
            content = readme.read_text(encoding="utf-8")
            if "docker run" in content.lower() or "docker build" in content.lower():
                docker_documented = True
                break

    if not docker_documented:
        issues.append("Docker execution instructions not found in README/QUICK_START")

    return issues


def main() -> int:
    """Docker 検証メイン。"""
    print("🔍 Checking Docker environment consistency...\n")

    all_issues = []

    # requirements.txt 形式チェック
    print("1️⃣ Checking requirements.txt format...")
    issues = check_requirements_format()
    for issue in issues:
        print(f"   ❌ {issue}")
        all_issues.append(issue)

    # Dockerfile ⟷ requirements.txt 一貫性
    print("\n2️⃣ Checking Dockerfile coherence...")
    issues = check_dockerfile_coherence()
    for issue in issues:
        print(f"   ⚠️ {issue}")
        all_issues.append(issue)

    # 仮想環境禁止確認
    print("\n3️⃣ Checking venv prohibition...")
    issues = check_venv_prohibition()
    for issue in issues:
        print(f"   ❌ {issue}")
        all_issues.append(issue)

    # PYTHONPATH ドキュメント
    print("\n4️⃣ Checking PYTHONPATH documentation...")
    issues = check_pythonpath_documentation()
    for issue in issues:
        print(f"   ⚠️ {issue}")
        all_issues.append(issue)

    print(f"\n📊 Summary: {len(all_issues)} issues found")
    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
