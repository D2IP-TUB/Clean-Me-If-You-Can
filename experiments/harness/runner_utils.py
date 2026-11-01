"""
runner_utils.py — shared utilities for all system runners.

Provides:
  - load_config()
  - list_effectiveness_datasets()
  - list_runtime_datasets()
  - TimedProcess context manager (wall time + peak memory via psutil)
  - purge_raha_cache()
  - run_with_timeout() — subprocess wrapper with hard time limit
  - setup_run_dir() — creates timestamped results dir per run
  - capture_logs() — captures stdout/stderr to files
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Optional

# full_10000, full_100000_distinct, full_full → 10000 / 100000 / -1
_RUNTIME_SIZE_RE = re.compile(r"_(\d+)(?:_|$)")

import psutil

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[str] = None) -> dict:
    path = config_path or os.path.join(EXPERIMENTS_DIR, "config.json")
    with open(path) as f:
        return json.load(f)


def resolve(cfg: dict, *rel_parts) -> str:
    """Resolve a path relative to EXPERIMENTS_DIR."""
    return os.path.normpath(os.path.join(EXPERIMENTS_DIR, *rel_parts))


# ---------------------------------------------------------------------------
# Dataset listing
# ---------------------------------------------------------------------------

def list_effectiveness_datasets(cfg: dict, exp_datasets_dir: str) -> list:
    """
    Return list of dicts describing every effectiveness dataset:
      { name, dirty, clean, slice, error_rate, poi }
    """
    entries = []
    eff_dir = os.path.join(exp_datasets_dir, "effectiveness")
    if not os.path.isdir(eff_dir):
        return entries

    for slice_name in sorted(os.listdir(eff_dir)):
        slice_dir = os.path.join(eff_dir, slice_name)
        if not os.path.isdir(slice_dir):
            continue
        # POI slices: dirty/clean directly inside
        dirty = os.path.join(slice_dir, "dirty.csv")
        clean = os.path.join(slice_dir, "clean.csv")
        if os.path.exists(dirty) and os.path.exists(clean):
            entries.append({
                "name": slice_name,
                "dirty": dirty,
                "clean": clean,
                "slice": slice_name,
                "error_rate": "native",
                "poi": slice_name.startswith("poi_"),
            })
            continue
        # Per-error-rate subdirectories
        for sub in sorted(os.listdir(slice_dir)):
            sub_dir = os.path.join(slice_dir, sub)
            if not os.path.isdir(sub_dir):
                continue
            dirty = os.path.join(sub_dir, "dirty.csv")
            clean = os.path.join(sub_dir, "clean.csv")
            if os.path.exists(dirty) and os.path.exists(clean):
                # Parse error rate from name like sample_full_0.05
                parts = sub.rsplit("_", 1)
                try:
                    rate = float(parts[-1])
                except ValueError:
                    rate = "native"
                entries.append({
                    "name": f"{slice_name}_{sub}",
                    "dirty": dirty,
                    "clean": clean,
                    "slice": slice_name,
                    "error_rate": rate,
                    "poi": False,
                })
    return entries


def list_runtime_datasets(cfg: dict, exp_datasets_dir: str) -> list:
    """
    Return list of dicts for runtime datasets, ordered by size ascending.
      { name, dirty, clean, n_records }
    """
    rt_dir = os.path.join(exp_datasets_dir, "runtime")
    if not os.path.isdir(rt_dir):
        return []
    entries = []
    for sub in sorted(os.listdir(rt_dir)):
        sub_dir = os.path.join(rt_dir, sub)
        dirty = os.path.join(sub_dir, "dirty.csv")
        clean = os.path.join(sub_dir, "clean.csv")
        if os.path.exists(dirty) and os.path.exists(clean):
            match = _RUNTIME_SIZE_RE.search(sub)
            n = int(match.group(1)) if match else -1  # "full" / unparseable
            entries.append({"name": sub, "dirty": dirty, "clean": clean, "n_records": n})
    entries.sort(key=lambda e: e["n_records"] if e["n_records"] >= 0 else 10**12)
    return entries


# ---------------------------------------------------------------------------
# Run directory
# ---------------------------------------------------------------------------

def setup_run_dir(results_base: str, system: str, dataset_name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(results_base, system, f"{dataset_name}_{ts}")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


# ---------------------------------------------------------------------------
# Memory + time tracking
# ---------------------------------------------------------------------------

class PeakMemoryTracker:
    """Background-thread peak RSS tracker for the current process.

    If *limit_mb* is set, sends SIGUSR1 to the process when RSS exceeds the
    limit, which (with the handler registered in __enter__) raises MemoryError
    in the main thread so callers can treat it like a time-out.
    """

    def __init__(self, interval: float = 0.2, limit_mb: Optional[float] = None):
        self.interval = interval
        self.limit_mb = limit_mb
        self.peak_mb = 0.0
        self._stop = threading.Event()
        self._proc = psutil.Process()
        self._old_sigusr1 = None

    def _run(self):
        while not self._stop.is_set():
            try:
                mem = self._proc.memory_info().rss / 1024 / 1024
                if mem > self.peak_mb:
                    self.peak_mb = mem
                if self.limit_mb is not None and mem > self.limit_mb:
                    os.kill(os.getpid(), signal.SIGUSR1)
                    break
            except Exception:
                pass
            self._stop.wait(self.interval)

    def __enter__(self):
        if self.limit_mb is not None:
            def _oom_handler(signum, frame):
                raise MemoryError(
                    f"Memory limit exceeded: {self.peak_mb:.0f} MB > {self.limit_mb:.0f} MB"
                )
            self._old_sigusr1 = signal.signal(signal.SIGUSR1, _oom_handler)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.start_time = time.time()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join(timeout=2)
        self.elapsed = time.time() - self.start_time
        if self._old_sigusr1 is not None:
            signal.signal(signal.SIGUSR1, self._old_sigusr1)
            self._old_sigusr1 = None


def track_subprocess_memory(proc: subprocess.Popen, interval: float = 0.5) -> float:
    """Poll peak memory of a subprocess (and its children). Returns peak MB."""
    peak = 0.0
    try:
        ps = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                all_procs = [ps] + ps.children(recursive=True)
                mem = sum(p.memory_info().rss for p in all_procs) / 1024 / 1024
                if mem > peak:
                    peak = mem
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(interval)
    except Exception:
        pass
    return peak


def get_memory_limit_mb(cfg: dict) -> float:
    """Return process memory limit in MB = total system RAM × memory_limit_fraction."""
    fraction = cfg.get("experiment", {}).get("memory_limit_fraction", 0.80)
    return psutil.virtual_memory().total * fraction / (1024 * 1024)


# ---------------------------------------------------------------------------
# Cache purging
# ---------------------------------------------------------------------------

def purge_raha_cache(dataset_dir: str):
    """Delete any raha-baran-results-* folders in dataset_dir (for fresh runtime runs)."""
    for entry in os.listdir(dataset_dir):
        if entry.startswith("raha-baran-results-"):
            full = os.path.join(dataset_dir, entry)
            shutil.rmtree(full, ignore_errors=True)
            print(f"  [purge] {full}")


def purge_holoclean_db(
    db_name: str = "holo",
    db_user: str = "holocleanuser",
    db_host: str = "127.0.0.1",
    db_port: str = "5432",
    db_pwd: str = "",
):
    """Reset HoloClean state by dropping all user tables in the target database.

    Prefer dropping tables over DROP DATABASE: on many installs holocleanuser can
    create objects in `holo` but does not own the database itself.
    """
    env = os.environ.copy()
    if db_pwd:
        env["PGPASSWORD"] = db_pwd
    psql = [
        "psql", "-h", db_host, "-p", str(db_port), "-U", db_user, "-d", db_name,
        "-v", "ON_ERROR_STOP=1",
    ]
    drop_sql = (
        "DO $$ DECLARE r RECORD; BEGIN "
        "FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP "
        "EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE'; "
        "END LOOP; END $$;"
    )
    try:
        subprocess.run(psql + ["-c", drop_sql], check=True, capture_output=True, env=env)
        print(f"  [purge] HoloClean DB '{db_name}' tables cleared")
    except Exception as e:
        print(f"  [warn] Could not reset HoloClean DB: {e}")
        if getattr(e, "stderr", None):
            print(f"  [warn] stderr: {e.stderr.decode(errors='replace')[:500]}")


def purge_datawig_cache(dataset_dir: str):
    """Remove DataWig model cache directories."""
    for entry in os.listdir(dataset_dir):
        if entry.startswith("datawig_models") or entry.startswith("imputation_model"):
            full = os.path.join(dataset_dir, entry)
            shutil.rmtree(full, ignore_errors=True)
            print(f"  [purge] {full}")


# ---------------------------------------------------------------------------
# Subprocess runner with hard timeout + log capture
# ---------------------------------------------------------------------------

def run_with_timeout(
    cmd: list,
    cwd: str,
    env: dict,
    time_limit: Optional[int],
    stdout_log: str,
    stderr_log: str,
    memory_limit_mb: Optional[float] = None,
) -> dict:
    """
    Run cmd as a subprocess with a hard wall-clock time limit and optional
    memory limit.  If *memory_limit_mb* is set and the subprocess RSS exceeds
    it the process is killed and ``oom`` is set in the return dict.
    Returns { returncode, runtime_seconds, peak_memory_mb, timed_out, oom }.
    stdout and stderr are streamed to log files.
    """
    start = time.time()
    timed_out = False
    mem_results = [0.0]
    oom_flag = [False]

    with open(stdout_log, "w") as fout, open(stderr_log, "w") as ferr:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=fout, stderr=ferr)

        def _track():
            peak = 0.0
            try:
                ps = psutil.Process(proc.pid)
                while proc.poll() is None:
                    try:
                        all_procs = [ps] + ps.children(recursive=True)
                        mem = sum(p.memory_info().rss for p in all_procs) / 1024 / 1024
                        if mem > peak:
                            peak = mem
                        if memory_limit_mb is not None and mem > memory_limit_mb:
                            proc.kill()
                            oom_flag[0] = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
                    time.sleep(0.5)
            except Exception:
                pass
            mem_results[0] = peak

        t = threading.Thread(target=_track, daemon=True)
        t.start()

        try:
            # None / 0 / negative: no wall-clock cap (LLM jobs).
            proc.wait(timeout=time_limit if time_limit and time_limit > 0 else None)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                proc.kill()
                proc.wait(timeout=10)
            except Exception:
                pass

        t.join(timeout=5)

    runtime = time.time() - start
    return {
        "returncode": proc.returncode,
        "runtime_seconds": runtime,
        "peak_memory_mb": mem_results[0],
        "timed_out": timed_out,
        "oom": oom_flag[0],
    }


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_log_file_handle = None  # set via init_log_file()


def init_log_file(path: str):
    """Open a log file that mirrors all log()/log_error()/log_warn() output."""
    global _log_file_handle
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _log_file_handle = open(path, "a", buffering=1, encoding="utf-8")


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    if _log_file_handle is not None:
        _log_file_handle.write(line + "\n")
        _log_file_handle.flush()


def log_error(msg: str):
    log(msg, "ERROR")


def log_warn(msg: str):
    log(msg, "WARN")
