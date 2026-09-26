"""SQLite event history and checkpoints for one or more episodes.

The event log is append-only. A checkpoint is a small JSON document (budget
counters, attempt number, number of events visible to the agent) written after
every tool result, so a restarted harness can resume without resetting its
budgets or forgetting a pending write.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class EventStore:
    def __init__(self, path: str | Path, episode_id: str):
        self.path = str(path)
        self.episode_id = episode_id
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                episode_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, sim_ms INTEGER, wall_ts REAL,
                PRIMARY KEY (episode_id, seq));
            CREATE TABLE IF NOT EXISTS checkpoints (
                episode_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, data TEXT NOT NULL);
            """
        )
        self.conn.commit()

    def append(self, kind: str, payload: dict[str, Any], sim_ms: int | None = None) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE episode_id = ?", (self.episode_id,)
        ).fetchone()
        seq = row[0]
        self.conn.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (self.episode_id, seq, kind, json.dumps(payload, default=str), sim_ms, time.time()),
        )
        self.conn.commit()
        return seq

    def events(self, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT seq, kind, payload, sim_ms FROM events WHERE episode_id = ? ORDER BY seq", (self.episode_id,)
        ).fetchall()
        out = [{"seq": s, "kind": k, "sim_ms": ms, **json.loads(p)} for s, k, p, ms in rows]
        return [e for e in out if kinds is None or e["kind"] in kinds]

    def save_checkpoint(self, data: dict[str, Any]) -> None:
        seq = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM events WHERE episode_id = ?", (self.episode_id,)
        ).fetchone()[0]
        self.conn.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?, ?, ?)", (self.episode_id, seq, json.dumps(data))
        )
        self.conn.commit()

    def load_checkpoint(self) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT data FROM checkpoints WHERE episode_id = ?", (self.episode_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def pending_writes(self) -> list[dict[str, Any]]:
        """Write intents with no recorded outcome (the crash window)."""
        resolved = {e["intent_seq"] for e in self.events(("write_resolved",))}
        return [e for e in self.events(("write_intent",)) if e["seq"] not in resolved]

    def close(self) -> None:
        self.conn.close()
