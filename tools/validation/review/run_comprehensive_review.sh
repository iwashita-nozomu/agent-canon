#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides run comprehensive review repository automation.
# upstream design ../../README.md shared automation index
# @dependency-end

#
# 統合コードレビューチェック実行スクリプト（v2.0）
# スキルファイル section 12 の自動化スクリプトを一括実行
# 
# 用法:
#   ./tools/validation/review/run_comprehensive_review.sh [--parallel] [--report]
#
# オプション:
#   --parallel     ツールを並行実行（高速化）
#   --report       実行後、JSON レポート生成
#   --verbose      詳細ログを出力
#

set -euo pipefail

# Do this before importing the runtime-boundary helper. A review must not
# compile its own Python modules into the AgentCanon source checkout.
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "python3 or python is required" >&2
        exit 127
    fi
fi

export PYTHONPATH="${PROJECT_ROOT}/python:${PYTHONPATH:-}"
export JAX_PLATFORMS="${JAX_PLATFORMS:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"

# ファラメータ解析
RUN_PARALLEL=false
GENERATE_REPORT=false
VERBOSE=false
RUNTIME_ROOT_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --parallel) RUN_PARALLEL=true; shift ;;
        --report) GENERATE_REPORT=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --runtime-root)
            [[ $# -ge 2 ]] || { echo "--runtime-root requires a path" >&2; exit 2; }
            RUNTIME_ROOT_ARG="$2"
            shift 2
            ;;
        --help)
            cat <<'EOF'
Usage: ./tools/validation/review/run_comprehensive_review.sh [--parallel] [--report] [--verbose]
       [--runtime-root PATH]

Runs static checks, tests, and workflow validators used in the comprehensive
review flow. Logs and optional reports are written under the external runtime
root (AGENT_CANON_RUNTIME_ROOT or --runtime-root).
EOF
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

RUNTIME_ROOT_VALUE="${RUNTIME_ROOT_ARG:-${AGENT_CANON_RUNTIME_ROOT:-}}"
RUN_DIR="$({
  ROOT_DIR="${PROJECT_ROOT}" AGENT_CANON_RUNTIME_ROOT="${RUNTIME_ROOT_VALUE}" \
    "${PYTHON_BIN}" - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.environ["ROOT_DIR"])
from tools.runtime.artifacts.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactError,
    runtime_artifact_boundary,
)

try:
    boundary = runtime_artifact_boundary(
        Path(os.environ["ROOT_DIR"]),
        os.environ.get("AGENT_CANON_RUNTIME_ROOT"),
        create=True,
    )
    parent = boundary.ensure_directory(Path("tasks") / "comprehensive-review")
    print(tempfile.mkdtemp(prefix="run-", dir=str(parent)))
except RuntimeArtifactError as exc:
    print(f"runtime_root_error: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
} )"
LOG_DIR="${RUN_DIR}/logs"
REPORT_DIR="${RUN_DIR}/reports"
TMP_DIR="${RUN_DIR}/tmp"
XDG_CACHE_DIR="${RUN_DIR}/xdg-cache"
mkdir -p "${LOG_DIR}" "${TMP_DIR}" "${XDG_CACHE_DIR}"
export RUFF_CACHE_DIR="${RUN_DIR}/ruff-cache"
export TMPDIR="${TMP_DIR}"
export TMP="${TMP_DIR}"
export TEMP="${TMP_DIR}"
export XDG_CACHE_HOME="${XDG_CACHE_DIR}"

# All commands below are AgentCanon checks. Anchor their cwd to this source
# checkout instead of inheriting a caller's parent-repository cwd.
cd "${PROJECT_ROOT}"

# タイムスタンプ
START_TIME=$(date +%s)
START_DATE=$(date '+%Y-%m-%d %H:%M:%S')

SUCCESS_COUNT=0
FAILURE_COUNT=0

# ロギング関数
log_info() {
    echo "[$(date '+%H:%M:%S')] ℹ️  $*" | tee -a "$LOG_DIR/comprehensive_review.log"
}

log_success() {
    echo "[$(date '+%H:%M:%S')] ✅ $*" | tee -a "$LOG_DIR/comprehensive_review.log"
    ((SUCCESS_COUNT+=1))
}

log_error() {
    echo "[$(date '+%H:%M:%S')] ❌ $*" | tee -a "$LOG_DIR/comprehensive_review.log"
    ((FAILURE_COUNT+=1))
}

log_info "================================================"
log_info "🚀 Comprehensive Code Review Checks v2.0"
log_info "Start time: $START_DATE"
log_info "Python interpreter: $PYTHON_BIN"
log_info "JAX test platform: $JAX_PLATFORMS"
log_info "Parallel mode: $RUN_PARALLEL"
log_info "================================================"

# ===== Python Checks =====
log_info ""
log_info "【Python Checks】"

# Pyright
log_info "1/4️⃣ Type checking with pyright..."
if "$PYTHON_BIN" -m pyright > "$LOG_DIR/pyright.log" 2>&1; then
    log_success "pyright: OK"
else
    log_error "pyright: FAILED (see $LOG_DIR/pyright.log)"
fi

# Ruff
log_info ""
log_info "2/4️⃣ Style check with ruff..."
if "$PYTHON_BIN" -m ruff check python tests > "$LOG_DIR/ruff.log" 2>&1; then
    log_success "ruff: OK"
else
    log_error "ruff: FAILED (see $LOG_DIR/ruff.log)"
fi

# Pytest
log_info ""
log_info "3/4️⃣ Test execution..."
if "$PYTHON_BIN" -m pytest tests/ -v --tb=short \
    -o "cache_dir=${RUN_DIR}/pytest-cache" > "$LOG_DIR/pytest.log" 2>&1; then
    log_success "pytest: OK"
else
    log_error "pytest: FAILED (see $LOG_DIR/pytest.log)"
fi

# ===== Extended Skill Checks =====
log_info ""
log_info "【Extended Skill Checks】"

if [ "$RUN_PARALLEL" = true ]; then
    log_info "Running tools in parallel mode..."
    
    # Background jobs
    "$PYTHON_BIN" "$SCRIPT_DIR/validation/triplet_validator.py" > "$LOG_DIR/triplet_check.log" 2>&1 &
    PID_TRIPLET=$!
    
    "$PYTHON_BIN" "$SCRIPT_DIR/check_convention_consistency.py" > "$LOG_DIR/convention_check.log" 2>&1 &
    PID_CONVENTION=$!
    
    bash "$SCRIPT_DIR/docker_dependency_validator.sh" > "$LOG_DIR/docker_check.log" 2>&1 &
    PID_DOCKER=$!
    
    
    # Wait for all background jobs
    if wait $PID_TRIPLET 2>/dev/null; then
        log_success "triplet check: OK"
    else
        log_error "triplet check: FAILED"
    fi
    
    if wait $PID_CONVENTION 2>/dev/null; then
        log_success "convention check: OK"
    else
        log_error "convention check: FAILED"
    fi
    
    if wait $PID_DOCKER 2>/dev/null; then
        log_success "docker check: OK"
    else
        log_error "docker check: FAILED"
    fi
    
    
else
    # Sequential execution
    log_info ""
    log_info "4/4️⃣ Doc-Test-Code Triplet Check..."
    if "$PYTHON_BIN" "$SCRIPT_DIR/validation/triplet_validator.py" > "$LOG_DIR/triplet_check.log" 2>&1; then
        log_success "triplet check: OK"
    else
        log_error "triplet check: FAILED"
    fi
    
    log_info ""
    log_info "5️⃣/6️⃣ Convention Consistency Check..."
    if "$PYTHON_BIN" "$SCRIPT_DIR/check_convention_consistency.py" > "$LOG_DIR/convention_check.log" 2>&1; then
        log_success "convention check: OK"
    else
        log_error "convention check: FAILED"
    fi
    
    log_info ""
    log_info "6️⃣/7️⃣ Docker Dependency Validation..."
    if bash "$SCRIPT_DIR/docker_dependency_validator.sh" > "$LOG_DIR/docker_check.log" 2>&1; then
        log_success "docker check: OK"
    else
        log_error "docker check: FAILED"
    fi
    
fi

# ===== Document Checks =====
log_info ""
log_info "【Document Checks】"

log_info ""
log_info "8️⃣ Documentation checks..."
if "$SCRIPT_DIR/bin/agent-canon" docs check > "$LOG_DIR/docs_check.log" 2>&1; then
    log_success "docs-check: OK"
else
    log_error "docs-check: FAILED (see $LOG_DIR/docs_check.log)"
fi

# ===== Summary =====
END_TIME=$(date +%s)
END_DATE=$(date '+%Y-%m-%d %H:%M:%S')
ELAPSED=$((END_TIME - START_TIME))

log_info ""
log_info "================================================"
log_info "✅ Review Complete!"
log_info "================================================"
log_info "Passed: $SUCCESS_COUNT"
log_info "Failed: $FAILURE_COUNT"
log_info "Elapsed: ${ELAPSED}s"
log_info "End time: $END_DATE"
log_info ""

# Generate JSON report
if [ "$GENERATE_REPORT" = true ]; then
    mkdir -p "$REPORT_DIR"
    REPORT_FILE="$REPORT_DIR/comprehensive_review_$(date +%Y%m%d_%H%M%S).json"
    TOTAL_COUNT=$((SUCCESS_COUNT + FAILURE_COUNT))
    PASS_RATE=$(
        "$PYTHON_BIN" - <<PY
total = ${TOTAL_COUNT}
passed = ${SUCCESS_COUNT}
print(f"{(passed * 100 / total):.2f}" if total else "0.00")
PY
    )
    
    cat > "$REPORT_FILE" << EOF
{
  "metadata": {
    "title": "Comprehensive Code Review",
    "start_time": "$START_DATE",
    "end_time": "$END_DATE",
    "elapsed_seconds": $ELAPSED,
    "parallel_mode": $RUN_PARALLEL
  },
  "summary": {
    "total": ${TOTAL_COUNT},
    "passed": $SUCCESS_COUNT,
    "failed": $FAILURE_COUNT,
    "pass_rate": "${PASS_RATE}%"
  },
  "log_dir": "$LOG_DIR",
  "report_file": "$REPORT_FILE"
}
EOF
    
    log_info "Report generated: $REPORT_FILE"
fi

log_info "Log directory: $LOG_DIR"

# Exit with failure if any check failed
if [ $FAILURE_COUNT -gt 0 ]; then
    exit 1
else
    exit 0
fi
