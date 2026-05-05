#!/usr/bin/env bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
set -euo pipefail

# deps.dot（実体はSVG）から、Graphvizの edge title を抽出して依存関係（src -> dst）に整形します。
#
# 使い方:
#   ./scripts/extract_deps_from_svg.sh deps.dot
#   ./scripts/extract_deps_from_svg.sh deps.dot --internal
#   ./scripts/extract_deps_from_svg.sh deps.dot --internal --prefix jax_util
#
# 出力:
#   標準出力に「src -> dst」を1行ずつ出します。
#
# 前提:
#   - 入力は pydeps の出力（Graphviz SVG）です。
#   - edge は <g class="edge"> ... <title>src&#45;&gt;dst</title> ... の形式です。

usage() {
  cat <<'USAGE'
Usage:
  extract_deps_from_svg.sh <svg_file> [--internal] [--prefix <prefix>]

Options:
  --internal          src/dst ともに prefix で始まるエッジだけを出力します。
  --prefix <prefix>   対象プレフィックス（既定: jax_util）
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" || $# -lt 1 ]]; then
  usage
  exit 1
fi

svg_file="$1"
shift

internal_only=0
prefix="jax_util"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --internal)
      internal_only=1
      shift
      ;;
    --prefix)
      prefix="${2:-}"
      if [[ -z "$prefix" ]]; then
        echo "--prefix requires a value" 1>&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "Unknown option: $1" 1>&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! -f "$svg_file" ]]; then
  echo "File not found: $svg_file" 1>&2
  exit 2
fi

/bin/python3 - "$svg_file" "$prefix" "$internal_only" <<'PY'
import re
import sys
from pathlib import Path

svg_path = Path(sys.argv[1])
prefix = sys.argv[2]
internal_only = sys.argv[3] == "1"

text = svg_path.read_text(encoding="utf-8", errors="ignore")

# Graphviz edge group: <g ... class="edge"> ... <title>src&#45;&gt;dst</title>
pattern = re.compile(r'<g id="edge\d+" class="edge">\s*<title>([^<]+)</title>')
raw_titles = pattern.findall(text)

edges: list[tuple[str, str]] = []
for title in raw_titles:
    title = title.replace("&#45;&gt;", "->")
    if "->" not in title:
        continue
    src, dst = title.split("->", 1)
    src = src.strip()
    dst = dst.strip()
    edges.append((src, dst))

# 正規化（重複除去・ソート）
edges = sorted(set(edges))

if internal_only:
    edges = [(s, d) for s, d in edges if s.startswith(prefix) and d.startswith(prefix)]
else:
    edges = [(s, d) for s, d in edges if s.startswith(prefix) or d.startswith(prefix)]

for s, d in edges:
    print(f"{s} -> {d}")
PY
