# ============================================================
# Database — SQLite logging for detected plates
# ============================================================

import sqlite3
import time
import logging

log = logging.getLogger("database")
DB_PATH = "anpr.db"


class Database:
    def init(self):
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                plate     TEXT NOT NULL,
                confidence REAL,
                ts        REAL NOT NULL
            )
        """)
        con.commit()
        con.close()
        log.info("[DB] Database initialised")

    def save(self, result: dict):
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO detections (plate, confidence, ts) VALUES (?, ?, ?)",
            (result.get("plate"), result.get("confidence"), time.time())
        )
        con.commit()
        con.close()

    def recent(self, limit: int = 20) -> list[dict]:
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT plate, confidence, ts FROM detections ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        con.close()
        return [{"plate": r[0], "confidence": r[1], "ts": r[2]} for r in rows]
