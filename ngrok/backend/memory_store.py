# -*- coding: utf-8 -*-
"""ความจำของ LIONBOT: เรียนรู้จากทุกแชตแล้วใช้ทันทีในรอบต่อไป (ไม่เทรนโมเดลใหม่)

หลักการ
  - หลังตอบจบแต่ละรอบ ให้โมเดลสกัด "ข้อมูลที่ผู้ใช้บอกเอง" ที่ควรจำ (ชั้นปี แผนที่เรียน เป้าหมาย ความชอบ คำแก้ที่บอตตอบผิด)
    เก็บเป็นประโยคสั้นๆ ใน SQLite (ตาราง memories) ทำเบื้องหลัง ไม่ทำให้ตอบช้าลง
  - รอบต่อไปดึงความจำที่เกี่ยวข้องมาแนบ prompt ถ้าขัดกับข้อมูลหลักสูตรจริง ให้ยึดข้อมูลหลักสูตร
  - ไม่จำรหัสวิชา (ข้อมูลหลักสูตรมาจาก RAG ที่ตรวจแล้วเท่านั้น) และไม่จำคำตอบของบอตเอง
  - ใช้ทันทีโดยอัตโนมัติ (ผู้ใช้เลือกแบบนี้) จึงมีปุ่มดู/ลบความจำใน frontend (/api/memories)
"""
import json
import re
import threading
from datetime import datetime, timezone

import requests

MAX_MEMORIES = 200      # เกินแล้วลบอันที่เก่าและถูกใช้น้อยที่สุด
MAX_IN_PROMPT = 8
MIN_LEN, MAX_LEN = 6, 160
_CODE_RE = re.compile(r'\d{8}')
# มีสัญญาณว่าผู้ใช้เล่าเรื่องตัวเอง/สั่งให้จำ/แก้บอต ถึงเรียกโมเดลสกัด (ลดภาระเครื่อง ไม่ต้องสกัดทุกคำถามล้วนๆ)
CUE_RE = re.compile(r'จำ|ผม|ฉัน|หนู|เรียนอยู่|ชอบ|ไม่ชอบ|ผิด|ไม่ใช่|แก้|จริงๆ|จริง ๆ|อยากได้|ต้องการ|เป้าหมาย|เกรดของ', re.I)

EXTRACT_SYSTEM = (
    "คุณเป็นตัวสกัดความจำสำหรับแชตบอตหลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ "
    "จากบทสนทนาหนึ่งรอบ ให้สกัดเฉพาะข้อมูลที่ควรจำระยะยาวและผู้ใช้เป็นคนบอกเอง ได้แก่ "
    "(1) ข้อมูลเกี่ยวกับผู้ใช้ เช่น ชั้นปี แผนที่เรียน เกรดสะสม เป้าหมาย "
    "(2) ความชอบหรือวิธีตอบที่ผู้ใช้ต้องการ "
    "(3) คำแก้ไขที่ผู้ใช้บอกว่าบอตตอบผิด "
    "ถ้าผู้ใช้แค่ถามคำถาม (แม้พูดถึงชั้นปีหรือแผน) โดยไม่ได้บอกว่าตัวเองอยู่ชั้นปีหรือแผนไหน ห้ามเดา ให้ตอบ notes ว่าง "
    "ห้ามสกัดสิ่งที่บอตเป็นคนตอบ ห้ามใส่รหัสวิชา ห้ามจดว่าผู้ใช้ถามหรืออยากรู้อะไร เขียนเป็นประโยคสั้นภาษาไทยในมุมมองบุคคลที่สาม "
    "เช่น \"ผู้ใช้เรียนปี 3 แผนสหกิจ\" ถ้าไม่มีอะไรควรจำให้ตอบ {\"notes\": []}"
)
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"notes": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
    "required": ["notes"],
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def ensure_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            uses INTEGER NOT NULL DEFAULT 0
        )
    ''')


def _norm(s):
    return re.sub(r'\s+', '', s).lower()


def _bigrams(s):
    s = _norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def list_memories(conn):
    rows = conn.execute('SELECT id, text, created_at, uses FROM memories ORDER BY id DESC').fetchall()
    return [{"id": r["id"], "text": r["text"], "createdAt": r["created_at"], "uses": r["uses"]} for r in rows]


def delete_memory(conn, mem_id=None):
    if mem_id is None:
        conn.execute('DELETE FROM memories')
    else:
        conn.execute('DELETE FROM memories WHERE id = ?', (mem_id,))
    conn.commit()


def add_notes(conn, notes):
    """เพิ่มความจำที่ผ่านตัวกรอง คืนรายการข้อความที่เพิ่มจริง"""
    existing = [_norm(r["text"]) for r in conn.execute('SELECT text FROM memories').fetchall()]
    added = []
    for n in notes or []:
        if not isinstance(n, str):
            continue
        n = re.sub(r'\s+', ' ', n).strip()
        if not (MIN_LEN <= len(n) <= MAX_LEN) or _CODE_RE.search(n):
            continue
        key = _norm(n)
        if any(key in e or e in key for e in existing):
            continue
        conn.execute('INSERT INTO memories (text, created_at) VALUES (?, ?)', (n, _now()))
        existing.append(key)
        added.append(n)
    total = conn.execute('SELECT COUNT(*) FROM memories').fetchone()[0]
    if total > MAX_MEMORIES:
        conn.execute('DELETE FROM memories WHERE id IN (SELECT id FROM memories ORDER BY uses ASC, id ASC LIMIT ?)', (total - MAX_MEMORIES,))
    conn.commit()
    return added


def context_block(conn, message):
    """ความจำที่เกี่ยวกับข้อความนี้ (ข้อความสำหรับแนบ prompt) หรือ '' ถ้าไม่มี"""
    rows = conn.execute('SELECT id, text FROM memories ORDER BY id DESC').fetchall()
    if not rows:
        return ''
    if len(rows) <= MAX_IN_PROMPT:
        picked = list(rows)
    else:
        q = _bigrams(message or '')
        scored = sorted(rows, key=lambda r: len(q & _bigrams(r["text"])), reverse=True)
        picked = []
        for r in scored[:5] + list(rows[:3]):  # ที่เกี่ยวข้องที่สุด 5 + ล่าสุด 3
            if r not in picked:
                picked.append(r)
        picked = picked[:MAX_IN_PROMPT]
    ids = [r["id"] for r in picked]
    conn.execute(f'UPDATE memories SET uses = uses + 1, last_used_at = ? WHERE id IN ({",".join("?" * len(ids))})', [_now(), *ids])
    conn.commit()
    return ("ความจำจากการคุยกับผู้ใช้ก่อนหน้า (ผู้ใช้เป็นคนบอกเอง ยังไม่ผ่านการตรวจสอบ ใช้เพื่อปรับคำตอบให้เหมาะกับผู้ใช้ "
            "ถ้าขัดกับข้อมูลหลักสูตรจริงให้ยึดข้อมูลหลักสูตร):\n" + "\n".join(f"- {r['text']}" for r in picked))


def should_extract(message):
    return bool(message) and len(message.strip()) >= 6 and bool(CUE_RE.search(message))


def extract_notes(ollama_chat_url, model, user_text, bot_text, timeout=120):
    payload = {
        "model": model,
        "stream": False,
        "format": EXTRACT_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": f"ผู้ใช้: {user_text}\nบอต: {(bot_text or '')[:600]}"},
        ],
    }
    r = requests.post(ollama_chat_url, json=payload, timeout=timeout)
    r.raise_for_status()
    content = r.json().get("message", {}).get("content", "")
    data = json.loads(content)
    return data.get("notes", []) if isinstance(data, dict) else []


def learn_async(get_db, ollama_chat_url, model, user_text, bot_text):
    """สกัดและบันทึกความจำเบื้องหลัง (ไม่บล็อกการตอบ) เงียบถ้าล้มเหลว"""
    if not should_extract(user_text):
        return None

    def work():
        try:
            notes = extract_notes(ollama_chat_url, model, user_text, bot_text)
            conn = get_db()
            try:
                add_notes(conn, notes)
            finally:
                conn.close()
        except Exception as e:  # ความจำเป็นของเสริม ห้ามกระทบแชตหลัก
            print(f"[memory] extract failed: {e}")

    t = threading.Thread(target=work, daemon=True)
    t.start()
    return t
