from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import requests
import io
import base64
import os
import json
import sqlite3
import uuid
from curriculum_rag import retrieve as retrieve_curriculum, direct_answer as direct_answer_curriculum
from grade_calc import grade_answer, grade_context
import memory_store
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_BUILD = os.path.join(BASE_DIR, '..', 'frontend', 'build')
DB_PATH = os.path.join(BASE_DIR, 'lionbot.db')

app = Flask(__name__, static_folder=FRONTEND_BUILD, static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
CORS(app)

INITIAL_BOT_TEXT = 'สวัสดีครับ ผม LIONBOT 🦁\nมีอะไรให้ช่วย หรือต้องการให้วิเคราะห์เอกสาร/รูปภาพ ส่งมาได้เลยครับ'
MAX_HISTORY_MESSAGES = 20  # จำกัดจำนวนข้อความย้อนหลังที่ส่งเข้าโมเดล กัน context ยาวเกินไป


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            file_names TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    ''')
    memory_store.ensure_table(conn)
    conn.commit()
    conn.close()


def serialize_message(row):
    return {
        "id": row["id"],
        "role": row["role"],
        "text": row["text"],
        "fileNames": json.loads(row["file_names"]) if row["file_names"] else [],
        "createdAt": row["created_at"],
    }


def create_conversation_row(conn, title=None):
    conv_id = str(uuid.uuid4())
    created = now_iso()
    conn.execute(
        'INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)',
        (conv_id, title or 'บทสนทนาใหม่', created)
    )
    conn.execute(
        'INSERT INTO messages (conversation_id, role, text, file_names, created_at) VALUES (?, ?, ?, ?, ?)',
        (conv_id, 'bot', INITIAL_BOT_TEXT, None, created)
    )
    return conv_id, title or 'บทสนทนาใหม่', created


init_db()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_URL}/api/chat"

AVAILABLE_MODELS = {
    "gemma3": "Gemma 3",
    "gemma3:latest": "Gemma 3",
    "typhoon-gemma3": "Typhoon Gemma 3",
    "typhoon-gemma3:latest": "Typhoon Gemma 3",
    "typhoon-lionbot": "Typhoon LIONBOT (Fine-Tuned)",
    "typhoon-lionbot-v2": "Typhoon LIONBOT v2 (Fine-Tuned)",
    "typhoon-lionbot-v3": "Typhoon LIONBOT v3 (Fine-Tuned)",
    "typhoon-lionbot-v4": "Typhoon LIONBOT v4 (Fine-Tuned)",  # <--- โมเดลรอบเทรนล่าสุด
}
DEFAULT_MODEL = "typhoon-lionbot-v3"
RAG_MODEL = "typhoon-gemma3"  # ใช้เรียบเรียงคำตอบเมื่อมีข้อมูลหลักสูตรแนบ
FINETUNED_MODELS = {m for m in AVAILABLE_MODELS if m.startswith("typhoon-lionbot")}

BOT_PERSONA = """
คุณคือ "LIONBOT" ผู้ช่วยอัจฉริยะ
- บุคลิก: สุภาพ, เป็นมืออาชีพ, กระตือรือร้น
- ความสามารถพิเศษ: สามารถอ่านเอกสาร PDF, Word, Excel และรูปภาพที่แนบมาได้
- คำแนะนำ:
  1. หากเป็น Excel ให้วิเคราะห์ข้อมูลตัวเลข สรุปแนวโน้ม หรือตอบคำถามจากตาราง
  2. หากเป็น Word ให้สรุปสาระสำคัญ หรือดึงข้อมูลตามที่ถาม
  3. ตอบคำถามอย่างแม่นยำและกระชับ
""".strip()

def read_excel_as_text(file_stream):
    from openpyxl import load_workbook
    wb = load_workbook(file_stream, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        if any(cell is not None and str(cell).strip() for cell in row):
            rows.append([str(cell) if cell is not None else "" for cell in row])

    if not rows:
        return ""

    col_count = max(len(row) for row in rows)
    normalized = [row + [""] * (col_count - len(row)) for row in rows]
    header = normalized[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * col_count) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)

def extract_text_from_file(mime_type, base64_data):
    try:
        file_bytes = base64.b64decode(base64_data)
        file_stream = io.BytesIO(file_bytes)

        if "sheet" in mime_type or "excel" in mime_type:
            try:
                text_data = read_excel_as_text(file_stream)
                return f"--- ข้อมูลจากไฟล์ Excel ---\n{text_data}\n------------------------------"
            except Exception as e:
                return f"[Error อ่าน Excel: {str(e)}]"

        elif "word" in mime_type or "officedocument" in mime_type:
            try:
                from docx import Document
                doc = Document(file_stream)
                full_text = [para.text for para in doc.paragraphs]
                return f"--- ข้อมูลจากไฟล์ Word ---\n{'\n'.join(full_text)}\n-----------------------------"
            except Exception as e:
                return f"[Error อ่าน Word: {str(e)}]"

        elif "pdf" in mime_type:
            try:
                from pypdf import PdfReader
                reader = PdfReader(file_stream)
                pages = [page.extract_text() or "" for page in reader.pages]
                text = "\n".join(pages).strip()
                if text:
                    return f"--- ข้อมูลจากไฟล์ PDF ---\n{text}\n-----------------------------"
                return "[PDF ไม่มีข้อความที่อ่านได้]"
            except Exception as e:
                return f"[Error อ่าน PDF: {str(e)}]"

        return None
    except Exception as e:
        print(f"Extraction Error: {e}")
        return None

def build_user_message(message, files_list):
    text_parts = []
    images = []

    for f in files_list:
        mime_type = f.get('mimeType', f.get('type', '')).lower()
        base64_data = f.get('data', '')

        if "image" in mime_type:
            images.append(base64_data)
        else:
            extracted_text = extract_text_from_file(mime_type, base64_data)
            if extracted_text:
                text_parts.append(extracted_text)

    if message:
        text_parts.append(message)

    if not text_parts and not images:
        return None

    content = "\n\n".join(text_parts) if text_parts else "กรุณาวิเคราะห์รูปภาพที่แนบมา"
    user_msg = {"role": "user", "content": content}
    if images:
        user_msg["images"] = images

    return user_msg

@app.route('/api/models', methods=['GET'])
def list_models():
    return jsonify({
        "models": [
            {"id": model_id, "label": label}
            for model_id, label in AVAILABLE_MODELS.items()
        ],
        "default": DEFAULT_MODEL
    })


@app.route('/api/conversations', methods=['GET'])
def list_conversations():
    conn = get_db()
    rows = conn.execute('SELECT id, title, created_at FROM conversations ORDER BY created_at ASC').fetchall()
    conn.close()
    return jsonify([{"id": r["id"], "title": r["title"], "createdAt": r["created_at"]} for r in rows])


@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    body = request.json or {}
    conn = get_db()
    conv_id, title, created = create_conversation_row(conn, body.get('title'))
    conn.commit()
    messages = conn.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC', (conv_id,)).fetchall()
    conn.close()
    return jsonify({
        "id": conv_id,
        "title": title,
        "createdAt": created,
        "messages": [serialize_message(m) for m in messages]
    })


@app.route('/api/conversations/<conv_id>/messages', methods=['GET'])
def get_conversation_messages(conv_id):
    conn = get_db()
    rows = conn.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC', (conv_id,)).fetchall()
    conn.close()
    return jsonify([serialize_message(r) for r in rows])


@app.route('/api/memories', methods=['GET'])
def list_memories_route():
    conn = get_db()
    try:
        return jsonify(memory_store.list_memories(conn))
    finally:
        conn.close()


@app.route('/api/memories', methods=['DELETE'])
def clear_memories_route():
    conn = get_db()
    try:
        memory_store.delete_memory(conn)
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route('/api/memories/<int:mem_id>', methods=['DELETE'])
def delete_memory_route(mem_id):
    conn = get_db()
    try:
        memory_store.delete_memory(conn, mem_id)
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route('/api/conversations/<conv_id>/truncate', methods=['POST'])
def truncate_conversation(conv_id):
    """LION EDIT: ลบข้อความตั้งแต่ตำแหน่ง index เป็นต้นไป (ตำแหน่งต้องเป็นข้อความผู้ใช้ และข้อความต้องตรงกับที่หน้าเว็บส่งมา)"""
    body = request.json or {}
    index = body.get('index')
    expected = body.get('expectedText', '')
    if not isinstance(index, int) or index < 0:
        return jsonify({"error": "index ไม่ถูกต้อง"}), 400
    conn = get_db()
    rows = conn.execute('SELECT id, role, text FROM messages WHERE conversation_id = ? ORDER BY id ASC', (conv_id,)).fetchall()
    if index >= len(rows):
        conn.close()
        return jsonify({"error": "ไม่พบข้อความตำแหน่งนี้"}), 404
    target = rows[index]
    if target['role'] != 'user' or target['text'] != (expected or "[ส่งไฟล์แนบ]"):
        conn.close()
        return jsonify({"error": "ข้อความในฐานข้อมูลไม่ตรงกับหน้าเว็บ"}), 409
    conn.execute('DELETE FROM messages WHERE conversation_id = ? AND id >= ?', (conv_id, target['id']))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "deleted": len(rows) - index})


@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    conn = get_db()
    conn.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        body = request.json
        message = body.get('message', '')
        model = body.get('model', DEFAULT_MODEL)
        files_list = body.get('files', [])
        conversation_id = body.get('conversation_id')

        if model not in AVAILABLE_MODELS:
            return jsonify({"reply": f"โมเดลไม่รองรับ: {model}"}), 400

        user_msg = build_user_message(message, files_list)
        if not user_msg:
            return jsonify({"reply": "กรุณาส่งข้อความหรือไฟล์แนบครับ"}), 400

        conn = get_db()
        conv_row = conn.execute('SELECT id FROM conversations WHERE id = ?', (conversation_id,)).fetchone() if conversation_id else None
        if not conv_row:
            conversation_id, _, _ = create_conversation_row(conn)
            conn.commit()

        history_rows = conn.execute(
            'SELECT role, text FROM messages WHERE conversation_id = ? ORDER BY id ASC', (conversation_id,)
        ).fetchall()
        is_first_user_message = not any(r['role'] == 'user' for r in history_rows)
        conn.close()

        messages = [{"role": "system", "content": BOT_PERSONA}]
        for r in history_rows[-MAX_HISTORY_MESSAGES:]:
            role = 'assistant' if r['role'] == 'bot' else 'user'
            messages.append({"role": role, "content": r['text']})
        # RAG: แนบข้อมูลหลักสูตรจริงที่เกี่ยวกับคำถามนี้ (โมเดลจำรหัสวิชา/ตัวเลขไม่แม่น)
        # เรื่องเกรด: ระบบคำนวณตัวเลขด้วยสูตร (โมเดลเล็กคิดเลขไม่แม่น) แล้วส่งให้โมเดลวิเคราะห์/อธิบาย/แนะนำเอง
        # ตั้ง LIONBOT_GRADE_DIRECT=1 ถ้าอยากให้ตอบจากสูตรตรงๆ ไม่ผ่านโมเดล
        grade_ctx = grade_context(message) if (message and not files_list) else None
        if grade_ctx and os.environ.get('LIONBOT_GRADE_DIRECT') == '1':
            direct_reply = grade_answer(message)
        elif grade_ctx:
            direct_reply = None
        else:
            direct_reply = direct_answer_curriculum(message) if not files_list else None
        context = retrieve_curriculum(message)
        if grade_ctx and not direct_reply:
            context = grade_ctx + ("\n\n" + context if context else "")
        if context:
            user_msg = dict(user_msg)
            user_msg["content"] = f"{context}\n\nคำถาม: {user_msg['content']}"
        elif model in FINETUNED_MODELS and message:
            user_msg = dict(user_msg)
            user_msg["content"] = ("(ไม่มีข้อมูลหลักสูตรที่ตรงกับคำถามนี้ ถ้าถามข้อมูลเฉพาะ เช่น ค่าเทอม อาจารย์ รหัสวิชา "
                                   "ให้ตอบว่าไม่มีข้อมูลและแนะนำให้สอบถามสาขาวิชา ห้ามเดา)\n\nคำถาม: " + user_msg["content"])
        # ความจำที่เรียนรู้จากแชตก่อนหน้า (ใช้ทันที) แนบเฉพาะรอบที่ให้โมเดลตอบ
        if not direct_reply and message:
            mem_conn = get_db()
            try:
                mem_ctx = memory_store.context_block(mem_conn, message)
            finally:
                mem_conn.close()
            if mem_ctx:
                user_msg = dict(user_msg)
                user_msg["content"] = f"{mem_ctx}\n\n{user_msg['content']}"
        # โมเดลที่เทรนเองจะตอบจากความจำ (รหัสวิชา/ตัวเลขผิดบ่อย) จึงใช้โมเดลฐานเรียบเรียงคำตอบจากข้อมูลจริงแทน
        if model in FINETUNED_MODELS:
            model = RAG_MODEL
        messages.append(user_msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }

        def generate():
            full_reply = ""
            try:
                if direct_reply:
                    # คำถามรายเทอมตอบจากข้อมูลตรงๆ ไม่ผ่านโมเดล (กันตกหล่นวิชา)
                    full_reply = direct_reply
                    yield f"data: {json.dumps({'content': direct_reply}, ensure_ascii=False)}\n\n"
                else:
                  with requests.post(OLLAMA_CHAT_URL, json=payload, timeout=300, stream=True) as r:
                    if r.status_code != 200:
                        yield f"data: {json.dumps({'error': f'Ollama status {r.status_code}'})}\n\n"
                        return

                    for line in r.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8').strip()
                            if not decoded_line:
                                continue
                            chunk = json.loads(decoded_line)
                            content = chunk.get("message", {}).get("content", "")
                            full_reply += content
                            yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

            except requests.exceptions.ConnectionError:
                yield f"data: {json.dumps({'error': 'ไม่สามารถเชื่อมต่อ Ollama ได้ กรุณาเปิดแอป Ollama ค้างไว้'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # บันทึกทุกรอบ (รวมรอบที่ผู้ใช้กดหยุดหรือเกิด error) เพื่อให้ลำดับข้อความใน DB ตรงกับหน้าเว็บ
                # ฟีเจอร์ LION EDIT ใช้ลำดับนี้ในการตัดข้อความตั้งแต่จุดที่แก้เป็นต้นไป
                history_user_content = message if message else "[ส่งไฟล์แนบ]"
                file_names = [f.get('name') for f in files_list if f.get('name')]
                file_names_json = json.dumps(file_names, ensure_ascii=False) if file_names else None

                write_conn = get_db()
                write_conn.execute(
                    'INSERT INTO messages (conversation_id, role, text, file_names, created_at) VALUES (?, ?, ?, ?, ?)',
                    (conversation_id, 'user', history_user_content, file_names_json, now_iso())
                )
                write_conn.execute(
                    'INSERT INTO messages (conversation_id, role, text, file_names, created_at) VALUES (?, ?, ?, ?, ?)',
                    (conversation_id, 'bot', full_reply, None, now_iso())
                )
                if is_first_user_message and message.strip():
                    title = message.strip()[:28] + ('…' if len(message.strip()) > 28 else '')
                    write_conn.execute('UPDATE conversations SET title = ? WHERE id = ?', (title, conversation_id))
                write_conn.commit()
                write_conn.close()
                # เรียนรู้จากรอบนี้เบื้องหลัง (ไม่ทำให้ตอบช้าลง) แล้วใช้ในรอบถัดไปทันที
                if message and full_reply and not files_list:
                    memory_store.learn_async(get_db, OLLAMA_CHAT_URL, RAG_MODEL, message, full_reply)

        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        })

    except Exception as e:
        return jsonify({"reply": f"เกิดข้อผิดพลาดภายในเซิร์ฟเวอร์: {str(e)}"}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path.startswith('api/'):
        return jsonify({"error": "Not found"}), 404

    if path and os.path.exists(os.path.join(FRONTEND_BUILD, path)):
        return send_from_directory(FRONTEND_BUILD, path)

    index_path = os.path.join(FRONTEND_BUILD, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(FRONTEND_BUILD, 'index.html')

    return jsonify({"error": "Frontend not built. Run: cd frontend && npm run build"}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True, threaded=True)