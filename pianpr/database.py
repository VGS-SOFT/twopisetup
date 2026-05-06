"""
database.py

SQLite async database for plate detection log.
Stores every detected plate with timestamp and confidence.
"""

import aiosqlite
import logging

logger = logging.getLogger(__name__)

DB_PATH = "anpr_log.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate TEXT NOT NULL,
                confidence REAL,
                timestamp TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info("[DB] Database initialised.")


async def log_plate(plate: str, confidence: float):
    import time
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO detections (plate, confidence, timestamp) VALUES (?, ?, ?)",
            (plate, confidence, ts)
        )
        await db.commit()


async def get_recent(limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT plate, confidence, timestamp FROM detections ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"plate": r[0], "confidence": r[1], "timestamp": r[2]} for r in rows]
