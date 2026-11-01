#!/usr/bin/env bash
# run_all_experiments.sh — master orchestrator for the address data cleaning benchmark.
#
# Runs all systems through all experiment phases and collects results.
#
# Usage:
#   bash run_all_experiments.sh [--config config.json] [--datasets-dir ./experiment_datasets]
#                               [--results-dir ./results] [--skip-prepare] [--effectiveness-only]
#                               [--runtime-only] [--system SYSTEM] [--dry-run]
#
# Phase 1: prepare_rules.py      — Horizon FD index + UniClean rules
# Phase 2: prepare_datasets.py   — sample and inject errors into datasets
# Phase 3: build Horizon         — compile Java sources
# Phase 4: effectiveness runs    — all systems × all datasets
# Phase 5: runtime runs          — all systems × all sizes (3 repeats each)
# Phase 6: collect_results.py    — write manuscript CSVs

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (override via CLI or environment)
# ---------------------------------------------------------------------------
CONFIG="$(dirname "$0")/config.json"
DATASETS_DIR="$(dirname "$0")/experiment_datasets"
RESULTS_DIR="$(dirname "$0")/results"
LOG_DIR="$(dirname "$0")/logs"
SKIP_PREPARE=0
EFFECTIVENESS_ONLY=0
RUNTIME_ONLY=0
SYSTEM_FILTER=""
DRY_RUN=0
N_RUNTIME_RUNS=3   # default; overridden from config if parseable

# ---------------------------------------------------------------------------
# Parse CLI args
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)         CONFIG="$2";          shift 2 ;;
        --datasets-dir)   DATASETS_DIR="$2";    shift 2 ;;
        --results-dir)    RESULTS_DIR="$2";     shift 2 ;;
        --skip-prepare)   SKIP_PREPARE=1;       shift ;;
        --effectiveness-only) EFFECTIVENESS_ONLY=1; shift ;;
        --runtime-only)   RUNTIME_ONLY=1;       shift ;;
        --system)         SYSTEM_FILTER="$2";   shift 2 ;;
        --dry-run)        DRY_RUN=1;            shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "$RESULTS_DIR" "$LOG_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/run_all.log"
}

run_cmd() {
    local label="$1"; shift
    local logfile="$LOG_DIR/${label}.log"
    log "START: $label"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY RUN: $*"
        return 0
    fi
    if "$@" >> "$logfile" 2>&1; then
        log "OK:    $label"
    else
        log "FAIL:  $label (exit $?)"
        return 1
    fi
}

system_enabled() {
    local sys="$1"
    # If SYSTEM_FILTER is set, only run that system
    [[ -z "$SYSTEM_FILTER" || "$SYSTEM_FILTER" == "$sys" ]]
}

# Try to extract n_runtime_runs and n_effectiveness_runs from config.json
if command -v python3 &>/dev/null; then
    N_RUNTIME_RUNS=$(python3 -c "
import json, sys
try:
    with open('$CONFIG') as f:
        c = json.load(f)
    print(c.get('experiment', {}).get('n_runtime_runs', 3))
except Exception:
    print(3)
" 2>/dev/null || echo 3)
    N_EFF_RUNS=$(python3 -c "
import json, sys
try:
    with open('$CONFIG') as f:
        c = json.load(f)
    print(c.get('experiment', {}).get('n_effectiveness_runs', 3))
except Exception:
    print(3)
" 2>/dev/null || echo 3)
fi

# ---------------------------------------------------------------------------
# Phase 1 & 2: Prepare
# ---------------------------------------------------------------------------
if [[ $SKIP_PREPARE -eq 0 && $RUNTIME_ONLY -eq 0 ]] || [[ $SKIP_PREPARE -eq 0 && $RUNTIME_ONLY -eq 1 ]]; then
    # Datasets must be prepared BEFORE rules (prepare_rules reads experiment_datasets/)
    run_cmd "prepare_datasets" \
        python3 prepare_datasets.py --config "$CONFIG" --out "$DATASETS_DIR"

    run_cmd "prepare_rules" \
        python3 prepare_rules.py --config "$CONFIG" \
            --out-dir "$DATASETS_DIR/fds" \
            --datasets-dir "$DATASETS_DIR"
fi

# ---------------------------------------------------------------------------
# Phase 3: Build Horizon
# ---------------------------------------------------------------------------
if system_enabled "horizon"; then
    log "Building Horizon Java sources..."
    if [[ $DRY_RUN -eq 0 ]]; then
        HORIZON_DIR="$(dirname "$0")/../baselines/horizon"
        BUILD_DIR="$(dirname "$0")/horizon_build"
        JAR="$HORIZON_DIR/commons-collections4-4.3.jar"
        STAMP="$BUILD_DIR/.compiled"
        mkdir -p "$BUILD_DIR"

        NEED_COMPILE=1
        if [[ -f "$STAMP" ]]; then
            NEW_SOURCES=$(find "$HORIZON_DIR/src" -name "*.java" -newer "$STAMP" 2>/dev/null | wc -l)
            [[ $NEW_SOURCES -eq 0 ]] && NEED_COMPILE=0
        fi

        if [[ $NEED_COMPILE -eq 1 ]]; then
            SOURCES=$(find "$HORIZON_DIR/src" -name "*.java" | tr '\n' ' ')
            # shellcheck disable=SC2086
            if javac -cp "$JAR" -d "$BUILD_DIR" $SOURCES >> "$LOG_DIR/build_horizon.log" 2>&1; then
                touch "$STAMP"
                log "Horizon compiled OK"
            else
                log "FAIL: Horizon compilation — check $LOG_DIR/build_horizon.log"
                # Continue without Horizon if desired
            fi
        else
            log "Horizon already compiled, skipping"
        fi
    else
        log "DRY RUN: javac Horizon sources"
    fi
fi

# ---------------------------------------------------------------------------
# Phase 4: Effectiveness experiments
# ---------------------------------------------------------------------------
if [[ $RUNTIME_ONLY -eq 0 ]]; then
    log "=== EFFECTIVENESS EXPERIMENTS (${N_EFF_RUNS} repeats) ==="

    # Raha/Baran are handled separately (shared runner); all others have run_{sys}.py
    EFF_SYSTEMS=(datawig holoclean horizon glocks uniclean katara)

    for run_i in $(seq 1 "$N_EFF_RUNS"); do
        log "--- Effectiveness repeat ${run_i}/${N_EFF_RUNS} ---"

        for sys in "${EFF_SYSTEMS[@]}"; do
            system_enabled "$sys" || continue
            run_cmd "effectiveness_${sys}_r${run_i}" \
                python3 "run_${sys}.py" \
                    --mode effectiveness \
                    --config "$CONFIG" \
                    --datasets-dir "$DATASETS_DIR" \
                    --results-dir "$RESULTS_DIR" \
                    || log "WARN: ${sys} effectiveness run ${run_i} had errors, continuing..."
        done

        # Raha and Baran share one runner
        if system_enabled "raha" || system_enabled "baran"; then
            SYS_ARG="both"
            if system_enabled "raha" && ! system_enabled "baran"; then SYS_ARG="raha"; fi
            if system_enabled "baran" && ! system_enabled "raha"; then SYS_ARG="baran"; fi
            run_cmd "effectiveness_raha_baran_r${run_i}" \
                python3 run_raha_baran.py \
                    --mode effectiveness \
                    --system "$SYS_ARG" \
                    --config "$CONFIG" \
                    --datasets-dir "$DATASETS_DIR" \
                    --results-dir "$RESULTS_DIR" \
                    || log "WARN: raha/baran effectiveness run ${run_i} had errors, continuing..."
        fi
    done
fi

# ---------------------------------------------------------------------------
# Phase 5: Runtime experiments (N_RUNTIME_RUNS repeats)
# ---------------------------------------------------------------------------
if [[ $EFFECTIVENESS_ONLY -eq 0 ]]; then
    log "=== RUNTIME EXPERIMENTS (${N_RUNTIME_RUNS} repeats) ==="

    RT_SYSTEMS=(datawig holoclean horizon glocks uniclean katara)
    for run_i in $(seq 1 "$N_RUNTIME_RUNS"); do
        log "--- Runtime repeat ${run_i}/${N_RUNTIME_RUNS} ---"

        # Raha + Baran
        if system_enabled "raha" || system_enabled "baran"; then
            SYS_ARG="both"
            if system_enabled "raha" && ! system_enabled "baran"; then SYS_ARG="raha"; fi
            if system_enabled "baran" && ! system_enabled "raha"; then SYS_ARG="baran"; fi
            run_cmd "runtime_raha_baran_r${run_i}" \
                python3 run_raha_baran.py \
                    --mode runtime \
                    --system "$SYS_ARG" \
                    --config "$CONFIG" \
                    --datasets-dir "$DATASETS_DIR" \
                    --results-dir "$RESULTS_DIR" \
                || log "WARN: raha/baran runtime run ${run_i} had errors"
        fi

        for sys in "${RT_SYSTEMS[@]}"; do
            system_enabled "$sys" || continue
            run_cmd "runtime_${sys}_r${run_i}" \
                python3 "run_${sys}.py" \
                    --mode runtime \
                    --config "$CONFIG" \
                    --datasets-dir "$DATASETS_DIR" \
                    --results-dir "$RESULTS_DIR" \
                || log "WARN: ${sys} runtime run ${run_i} had errors"
        done
    done
fi

# ---------------------------------------------------------------------------
# Phase 6: Collect results into manuscript CSVs
# ---------------------------------------------------------------------------
log "=== COLLECTING RESULTS ==="
run_cmd "collect_results" \
    python3 collect_results.py \
        --config "$CONFIG" \
        --results-dir "$RESULTS_DIR"

log "=== ALL DONE ==="
log "Results in:    $RESULTS_DIR"
log "Manuscript in: $(python3 -c "import json; c=json.load(open('$CONFIG')); print(c['paths']['manuscript_results_dir'])" 2>/dev/null || echo '(see config)')"
