# -*- coding: utf-8 -*-
"""
ฐานข้อมูลประวัติแชท (SQLite) — แยกผู้ใช้ตามเครื่อง (device_id ที่เบราว์เซอร์สร้างให้เอง ไม่ต้องล็อกอิน)

ตาราง
  conversations(id, device_id, title, created_at, updated_at)
  messages(id, conversation_id, role, content, route, created_at)

สำรองข้อมูล: ถ้าตั้ง DB_BACKUP_PATH (เช่น ไฟล์ใน Google Drive) จะคัดลอกฐานข้อมูลไปที่นั่นทุก ~2 นาที
และตอนเปิดเซิร์ฟเวอร์ ถ้ายังไม่มีไฟล์ฐานข้อมูล จะกู้คืนจากไฟล์สำรองให้อัตโนมัติ
(ไม่เปิด SQLite บน Google Drive ตรงๆ เพราะ Drive ล็อกไฟล์ไม่ได้ อาจทำให้ฐานข้อมูลเสีย)
"""
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat.db"))
DB_BACKUP_PATH = os.environ.get("DB_BACKUP_PATH", "").strip()
_lock = threading.Lock()
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    device_id   TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT 'แชทใหม่',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_device ON conversations(device_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    route            TEXT NOT NULL DEFAULT '',
    created_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
"""


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    if not os.path.exists(DB_PATH) and DB_BACKUP_PATH and os.path.exists(DB_BACKUP_PATH):
        shutil.copyfile(DB_BACKUP_PATH, DB_PATH)
        print(f"กู้คืนประวัติแชทจาก {DB_BACKUP_PATH}")
    with _lock, _connect() as con:
        con.executescript(SCHEMA)
    if DB_BACKUP_PATH:
        threading.Thread(target=_backup_forever, daemon=True).start()


def backup_now():
    if not DB_BACKUP_PATH:
        return
    os.makedirs(os.path.dirname(DB_BACKUP_PATH) or ".", exist_ok=True)
    tmp = DB_BACKUP_PATH + ".tmp"
    with _lock:
        src = _connect()
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        dst.close()
        src.close()
    os.replace(tmp, DB_BACKUP_PATH)


def _backup_forever():
    while True:
        time.sleep(120)
        try:
            backup_now()
        except Exception as e:  # pragma: no cover
            print("สำรองฐานข้อมูลไม่สำเร็จ:", e)


def valid_device(device_id):
    return bool(device_id) and bool(DEVICE_RE.match(device_id))


def _make_title(text):
    t = re.sub(r"\s+", " ", text).strip()
    return (t[:40] + "…") if len(t) > 40 else (t or "แชทใหม่")


def get_or_create_conversation(device_id, conversation_id=None, first_message=""):
    now = time.time()
    with _lock, _connect() as con:
        if conversation_id:
            row = con.execute("SELECT id FROM conversations WHERE id=? AND device_id=?",
                              (conversation_id, device_id)).fetchone()
            if row:
                return row["id"]
        cid = uuid.uuid4().hex
        con.execute("INSERT INTO conversations(id, device_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (cid, device_id, _make_title(first_message), now, now))
        return cid


def add_message(conversation_id, role, content, route=""):
    now = time.time()
    with _lock, _connect() as con:
        con.execute("INSERT INTO messages(conversation_id, role, content, route, created_at) VALUES (?,?,?,?,?)",
                    (conversation_id, role, content, route, now))
        con.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))


def history(conversation_id, limit=8):
    with _lock, _connect() as con:
        rows = con.execute("SELECT role, content, route FROM messages WHERE conversation_id=? "
                           "ORDER BY id DESC LIMIT ?", (conversation_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def list_conversations(device_id, limit=100):
    with _lock, _connect() as con:
        rows = con.execute(
            "SELECT c.id, c.title, c.updated_at, COUNT(m.id) AS n FROM conversations c "
            "LEFT JOIN messages m ON m.conversation_id = c.id WHERE c.device_id=? "
            "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?", (device_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_messages(device_id, conversation_id):
    with _lock, _connect() as con:
        ok = con.execute("SELECT 1 FROM conversations WHERE id=? AND device_id=?",
                         (conversation_id, device_id)).fetchone()
        if not ok:
            return None
        rows = con.execute("SELECT role, content, route, created_at FROM messages WHERE conversation_id=? ORDER BY id",
                           (conversation_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_conversation(device_id, conversation_id):
    with _lock, _connect() as con:
        cur = con.execute("DELETE FROM conversations WHERE id=? AND device_id=?", (conversation_id, device_id))
        return cur.rowcount > 0


def rename_conversation(device_id, conversation_id, title):
    with _lock, _connect() as con:
        cur = con.execute("UPDATE conversations SET title=? WHERE id=? AND device_id=?",
                          (_make_title(title), conversation_id, device_id))
        return cur.rowcount > 0


def stats():
    with _lock, _connect() as con:
        return {"conversations": con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
                "messages": con.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "devices": con.execute("SELECT COUNT(DISTINCT device_id) FROM conversations").fetchone()[0]}
