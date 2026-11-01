"""SQLite connections for dump indexes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["connect_sqlite"]


def connect_sqlite(
    path: Path | str, *, read_only: bool = False, replace: bool = False
) -> sqlite3.Connection:
    path = Path(path)
    if replace:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        for suffix in ("-wal", "-shm"):
            side = Path(str(path) + suffix)
            if side.exists():
                side.unlink()
    if read_only:
        return sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA cache_size=-2000000")
    con.execute("PRAGMA mmap_size=8589934592")
    con.execute("PRAGMA locking_mode=EXCLUSIVE")
    con.execute("PRAGMA busy_timeout=60000")
    return con
