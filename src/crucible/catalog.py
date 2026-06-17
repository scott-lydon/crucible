"""Strategy catalog — winning tactics persist across runs (SQLite). Techniques that
have worked before are prioritized in future runs, so the tool compounds."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class StrategyCatalog:
    def __init__(self, path: str = ".crucible/catalog.db"):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS wins ("
            " attack_class TEXT, technique TEXT, wins INTEGER DEFAULT 0,"
            " PRIMARY KEY (attack_class, technique))"
        )
        self._conn.commit()

    def record_win(self, attack_class: str, technique: str) -> None:
        self._conn.execute(
            "INSERT INTO wins (attack_class, technique, wins) VALUES (?, ?, 1) "
            "ON CONFLICT(attack_class, technique) DO UPDATE SET wins = wins + 1",
            (attack_class, technique),
        )
        self._conn.commit()

    def top_techniques(self, attack_class: str, limit: int = 5) -> list[str]:
        rows = self._conn.execute(
            "SELECT technique FROM wins WHERE attack_class = ? ORDER BY wins DESC LIMIT ?",
            (attack_class, limit),
        ).fetchall()
        return [r[0] for r in rows]

    def total_wins(self) -> int:
        return self._conn.execute("SELECT COALESCE(SUM(wins), 0) FROM wins").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
