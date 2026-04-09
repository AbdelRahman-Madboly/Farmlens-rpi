"""
FarmLens Logger
================
SQLite cycle history + JPEG path helpers.
WAL mode enabled for concurrent read/write from API and main loop.
"""
import sqlite3
import json
import os
import logging

from config import DB_PATH, LOG_IMAGE_DIR

log = logging.getLogger("farmlens.logger")


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS cycles (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id  TEXT UNIQUE,
            ts        INTEGER,
            data_json TEXT,
            has_image INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()
    log.info("SQLite ready: %s", DB_PATH)


def save_cycle(data: dict):
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            "INSERT OR REPLACE INTO cycles (cycle_id, ts, data_json, has_image) "
            "VALUES (?,?,?,?)",
            (data["cycle_id"], data["ts"],
             json.dumps(data), int(data.get("has_image", False)))
        )
        con.commit()
        con.close()
    except Exception as e:
        log.error("save_cycle: %s", e)


def get_logs(limit: int = 50) -> list:
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT data_json FROM cycles ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return [json.loads(r["data_json"]) for r in rows]
    except Exception as e:
        log.error("get_logs: %s", e)
        return []


def image_path(cycle_id: str) -> str:
    return os.path.join(LOG_IMAGE_DIR, f"{cycle_id}.jpg")


def image_exists(cycle_id: str) -> bool:
    return os.path.isfile(image_path(cycle_id))
