#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Creates a starter design document under documents/design.
# upstream design ../README.md shared tool index
# downstream design ../../documents/design/README.md documents design placement
# @dependency-end
"""
create_design_template.py

Create a design template under `documents/design/<submodule>/template.md`.

Usage: python3 scripts/tools/create_design_template.py <submodule> [--force]
"""
import sys
from pathlib import Path

ROOT = Path('.').resolve()
DESIGN_DIR = ROOT / 'documents' / 'design'


TEMPLATE = """
# <Submodule> 詳細設計テンプレート

## 概要

（一段落で機能と目的を記述）

## 対象コードパス

（例）: `python/jax_util/<submodule>/`

## 公開 API

- 関数 / クラス一覧と説明

## データフロー / シーケンス図

（必要に応じて図や JSON を添付）

## 非機能要件

（性能、メモリ、セキュリティ）

## テスト / 検証計画

（単体・統合・E2E の観点）

## マイグレーション / リリース手順

## 担当者

（名前・連絡先）

"""


def main():
    if len(sys.argv) < 2:
        print("usage: create_design_template.py <submodule> [--force]")
        raise SystemExit(2)
    sub = sys.argv[1]
    force = '--force' in sys.argv
    target_dir = DESIGN_DIR / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / 'template.md'
    if target.exists() and not force:
        print(f"template already exists: {target}")
        return
    target.write_text(TEMPLATE.replace('<Submodule>', sub), encoding='utf-8')
    print('Created', target)


if __name__ == '__main__':
    main()
