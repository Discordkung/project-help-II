# -*- coding: utf-8 -*-
"""
Backend ของ DSEE Buddy (Flask)
  GET  /                 -> หน้าเว็บ (frontend/index.html)
  GET  /api/health       -> สถานะเซิร์ฟเวอร์ + โมเดลที่ใช้
  POST /api/chat         -> แชท (ตอบแบบสตรีม)  body: {message, history:[{role,content}], file_text, file_name}
  POST /api/upload       -> อ่านไฟล์ .pdf .docx .xlsx .pptx .txt แล้วคืนข้อความ
รันตรงๆ ได้ด้วย  python backend/server.py   (หรือใช้ run.py เพื่อเปิด trycloudflare ให้ใช้บนมือถือ)
"""
import io
import json
import os
import queue
import sys
import threading
import time

import requests
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsee_core as core  # noqa: E402
import db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
DSEE_MODEL = os.environ.get("DSEE_MODEL", "dsee-typhoon")
GENERAL_MODEL = os.environ.get("GENERAL_MODEL", "hf.co/typhoon-ai/typhoon2.1-gemma3-4b-gguf:Q4_K_M")
APP_PIN = os.environ.get("APP_PIN", "").strip()
PORT = int(os.environ.get("PORT", "8000"))
ONE_MODEL_AT_A_TIME = os.environ.get("ONE_MODEL_AT_A_TIME", "1") != "0"  # ตั้งเป็น 0 ถ้าเครื่อง RAM เยอะ (16GB+)
MAX_FILE_CHARS = 12000
MAX_HISTORY = 8

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


# ------------------------------------------------------------------ helpers
HEARTBEAT = "\u200b"          # ตัวอักษรล่องหน ส่งเป็นระยะกัน Cloudflare ตัดสาย (HTTP 524) ระหว่างรอโมเดล
HEARTBEAT_EVERY = 8           # วินาที
MODEL_LOCK = threading.Lock()  # ให้โมเดลทำงานทีละคำถาม (กันแย่งหน่วยความจำ / ปิดโมเดลที่อีกคนกำลังใช้)
_models_cache = {"t": 0.0, "models": None}


def _refresh_models_forever():
    """อัปเดตรายชื่อโมเดลในเบื้องหลังทุก 60 วิ — คำถามของผู้ใช้จะไม่ต้องรอ Ollama ตอบรายชื่อ"""
    while True:
        try:
            r = requests.get(f"{OLLAMA}/api/tags", timeout=30)
            _models_cache.update(t=time.time(), models={m["name"] for m in r.json().get("models", [])})
        except Exception:
            pass
        time.sleep(60)


def installed_models(timeout=None):
    return _models_cache["models"]


def ollama_up():
    try:
        requests.get(f"{OLLAMA}/api/version", timeout=3)
        return True
    except Exception:
        return False


def _has(models, name):
    return name in models or f"{name}:latest" in models


def pick_models(timeout=15):
    models = installed_models(timeout)
    if models is None:                       # ยังไม่รู้ (Ollama ยุ่ง) -> ใช้ชื่อที่ตั้งไว้ไปก่อน
        return DSEE_MODEL, GENERAL_MODEL, ollama_up()
    dsee = DSEE_MODEL if _has(models, DSEE_MODEL) else None
    general = GENERAL_MODEL if _has(models, GENERAL_MODEL) else dsee
    return dsee, general, True


def pin_ok():
    return (not APP_PIN) or request.headers.get("X-App-Pin", "") == APP_PIN


def free_other_models(model):
    """เครื่อง RAM น้อยเปิดได้ทีละโมเดล -> ปิดโมเดลอื่นที่ค้างอยู่ก่อนโหลดตัวใหม่"""
    try:
        loaded = requests.get(f"{OLLAMA}/api/ps", timeout=10).json().get("models", [])
        for m in loaded:
            name = m.get("name") or m.get("model")
            if name and name not in (model, f"{model}:latest"):
                requests.post(f"{OLLAMA}/api/generate", json={"model": name, "keep_alive": 0}, timeout=60)
    except Exception:
        pass


def _friendly_error(err):
    e = str(err)
    if "allocate" in e or "memory" in e.lower():
        return "⚠️ หน่วยความจำ (RAM) ในคอมไม่พอโหลดโมเดล ลองปิดโปรแกรมอื่นแล้วถามใหม่อีกครั้งนะ"
    if "not found" in e and "model" in e:
        return "⚠️ ไม่พบโมเดลใน Ollama — เช็กด้วยคำสั่ง  ollama list"
    return f"⚠️ Ollama แจ้งข้อผิดพลาด: {e}"


def _ollama_worker(model, messages, options, q, stop):
    """คุยกับ Ollama ในเธรดแยก ส่งผลกลับทางคิว (ลองใหม่อัตโนมัติ 1 ครั้งถ้าการเชื่อมต่อหลุด)"""
    payload = {"model": model, "messages": messages, "stream": True, "keep_alive": "30m", "options": options}
    with MODEL_LOCK:
        if stop.is_set():
            return q.put(None)
        if ONE_MODEL_AT_A_TIME:
            free_other_models(model)
        for attempt in (1, 2):
            got_text = False
            try:
                with requests.post(f"{OLLAMA}/api/chat", json=payload, stream=True, timeout=(10, 900)) as r:
                    for line in r.iter_lines():
                        if stop.is_set():
                            return q.put(None)
                        if not line:
                            continue
                        body = json.loads(line.decode("utf-8"))
                        if "error" in body:
                            err = body["error"]
                            retryable = any(k in err for k in ("closed", "terminated", "EOF", "connection"))
                            if attempt == 1 and retryable and not got_text:
                                raise requests.exceptions.ConnectionError(err)
                            q.put(_friendly_error(err))
                            return q.put(None)
                        chunk = body.get("message", {}).get("content", "")
                        if chunk:
                            got_text = True
                            q.put(chunk)
                return q.put(None)
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                if attempt == 1 and not got_text:
                    time.sleep(3)              # Ollama อาจกำลังโหลดโมเดล/รีสตาร์ต -> รอแล้วลองใหม่
                    continue
                q.put("⚠️ ต่อ Ollama ไม่ได้ — เช็กว่าแอป Ollama ในคอมยังเปิดอยู่ แล้วลองใหม่อีกครั้งนะ"
                      if not got_text else f"\n⚠️ การเชื่อมต่อกับโมเดลหลุดกลางทาง ({e.__class__.__name__})")
                return q.put(None)
            except Exception as e:  # pragma: no cover
                q.put(f"\n⚠️ เกิดข้อผิดพลาด: {e}")
                return q.put(None)


def stream_ollama(model, messages, options):
    q, stop = queue.Queue(), threading.Event()
    threading.Thread(target=_ollama_worker, args=(model, messages, options, q, stop), daemon=True).start()
    text = ""
    yield HEARTBEAT                              # ส่งไบต์แรกทันที -> Cloudflare ไม่รอจน timeout
    try:
        while True:
            try:
                chunk = q.get(timeout=HEARTBEAT_EVERY)
            except queue.Empty:
                yield HEARTBEAT                  # ยังรอโมเดลอยู่ (คิว/โหลดโมเดล/คิดคำตอบ)
                continue
            if chunk is None:
                return
            text += chunk
            yield chunk
            # กันโมเดลพูดวนซ้ำไม่จบ (เช่น รายชื่อวิชายาวๆ) -> หยุดเอง
            if len(text) > 300 and text.count(text[-40:]) >= 3:
                yield ("\n\n⚠️ ขอหยุดตรงนี้ก่อนนะ คำตอบเริ่มวนซ้ำ ลองถามให้เจาะจงขึ้น เช่น ระบุชื่อ/รหัสวิชา "
                       "หรือ 'ปี 2 เทอม 1 เรียนอะไร' จะได้คำตอบที่แม่นกว่า")
                return
    finally:
        stop.set()                               # ผู้ใช้กดหยุด/ปิดหน้าเว็บ -> ปล่อยโมเดลให้คนถัดไป


def clean_history(history):
    out = []
    for m in (history or [])[-MAX_HISTORY:]:
        role = m.get("role")
        content = str(m.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def stream_response(gen, route, model=""):
    headers = {"X-Route": route, "X-Model": model, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    # text/event-stream ทำให้ Cloudflare ไม่พักข้อมูลไว้ -> ตัวอักษรไหลขึ้นทีละนิดบนมือถือ
    return Response(stream_with_context(gen), mimetype="text/event-stream", headers=headers)


# ------------------------------------------------------------------ routes
@app.route("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND, path)


@app.route("/api/ping")
def ping():
    return jsonify({"ok": True})


@app.route("/api/health")
def health():
    dsee, general, ollama_up = pick_models(timeout=4)
    return jsonify({"ok": True, "ollama": ollama_up, "dsee_model": dsee, "general_model": general,
                    "pin_required": bool(APP_PIN), "db": db.stats()})


def device_id():
    d = request.headers.get("X-Device-Id", "").strip()
    return d if db.valid_device(d) else None


def saving_stream(gen, conversation_id, route):
    """ส่งคำตอบแบบสตรีม แล้วบันทึกลงฐานข้อมูลเมื่อจบ (หรือเมื่อผู้ใช้กดหยุด/ปิดหน้า)"""
    parts = []
    try:
        for chunk in gen:
            parts.append(chunk)
            yield chunk
    finally:
        text = "".join(parts).replace(HEARTBEAT, "").strip()
        if text:
            try:
                db.add_message(conversation_id, "assistant", text, route)
            except Exception as e:  # pragma: no cover
                print("บันทึกคำตอบไม่สำเร็จ:", e)


def chat_response(gen, route, cid, model=""):
    r = stream_response(saving_stream(gen, cid, route), route, model)
    r.headers["X-Conversation-Id"] = cid
    return r


@app.route("/api/chat", methods=["POST"])
def chat():
    if not pin_ok():
        return jsonify({"error": "PIN ไม่ถูกต้อง"}), 401
    dev = device_id()
    if not dev:
        return jsonify({"error": "ไม่พบรหัสเครื่อง (X-Device-Id) — รีเฟรชหน้าเว็บแล้วลองใหม่"}), 400
    data = request.get_json(force=True, silent=True) or {}
    q = str(data.get("message", "")).strip()[:2000]
    if not q:
        return jsonify({"error": "ข้อความว่าง"}), 400
    file_text = str(data.get("file_text", ""))[:MAX_FILE_CHARS]
    file_name = str(data.get("file_name", ""))[:200]

    cid = db.get_or_create_conversation(dev, data.get("conversation_id"), q)
    history = clean_history(db.history(cid, MAX_HISTORY))          # ประวัติจากฐานข้อมูล (ไม่เชื่อข้อมูลจากเบราว์เซอร์)
    prev_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    db.add_message(cid, "user", (f"📎 {file_name}\n" if file_text else "") + q)

    # 1) ถามเรื่องไฟล์ที่แนบ -> โมเดลทั่วไป
    if file_text:
        _, general, _ = pick_models()
        if not general:
            return chat_response(iter(["⚠️ ยังไม่มีโมเดลใน Ollama"]), "error", cid)
        user = f"ข้อมูลจากไฟล์ '{file_name}':\n\"\"\"\n{file_text}\n\"\"\"\n\nคำถาม/คำสั่ง: {q}"
        msgs = [{"role": "system", "content": core.GENERAL_SYSTEM}] + history + [{"role": "user", "content": user}]
        return chat_response(stream_ollama(general, msgs, {"temperature": 0.4, "num_ctx": 8192}), "file", cid, general)

    # 2) ตอบจากข้อมูลหลักสูตรโดยตรง (แม่นยำ 100%)
    ans = core.rule_answer(q, prev_user)
    if ans:
        return chat_response(iter([ans]), "rule", cid)

    dsee, general, _ = pick_models()

    # 3) คำถามหลักสูตรอื่นๆ -> dsee-typhoon + ข้อมูลที่ค้นมา + บทสนทนาล่าสุด (รูปแบบเดียวกับตอนเทรน)
    if core.is_curriculum(q) and dsee:
        follow = not (core.mentioned_courses(q) or core.sem_from_question(q)) and prev_user
        rq = f"{prev_user} {q}" if follow else q
        recent = [m for m in history if m["content"] and not m["content"].startswith("⚠️")][-4:] if follow else []
        msgs = [{"role": "system", "content": core.curriculum_system_prompt(rq)}] + recent + \
               [{"role": "user", "content": q}]
        opts = {"temperature": 0.1, "num_ctx": 4096, "num_predict": 500, "repeat_penalty": 1.15}

        def gen():
            yield core.friendly_prefix()
            yield from stream_ollama(dsee, msgs, opts)
        return chat_response(gen(), "curriculum", cid, dsee)

    # 4) เรื่องทั่วไป / โค้ด / นอกหลักสูตร -> โมเดลทั่วไป คุยแบบเป็นกันเอง จำบทสนทนาได้
    if not general:
        return chat_response(iter(["⚠️ ยังไม่มีโมเดลใน Ollama"]), "error", cid)
    msgs = [{"role": "system", "content": core.GENERAL_SYSTEM}] + history + [{"role": "user", "content": q}]
    return chat_response(stream_ollama(general, msgs, {"temperature": 0.6, "num_ctx": 4096, "num_predict": 1500}),
                         "general", cid, general)


# ------------------------------------------------------------------ ประวัติแชท
@app.route("/api/conversations", methods=["GET"])
def conversations():
    if not pin_ok():
        return jsonify({"error": "PIN ไม่ถูกต้อง"}), 401
    dev = device_id()
    return jsonify({"conversations": db.list_conversations(dev) if dev else []})


@app.route("/api/conversations/<cid>", methods=["GET", "DELETE", "PATCH"])
def conversation(cid):
    if not pin_ok():
        return jsonify({"error": "PIN ไม่ถูกต้อง"}), 401
    dev = device_id()
    if not dev:
        return jsonify({"error": "ไม่พบรหัสเครื่อง"}), 400
    if request.method == "DELETE":
        return jsonify({"ok": db.delete_conversation(dev, cid)})
    if request.method == "PATCH":
        title = str((request.get_json(silent=True) or {}).get("title", "")).strip()
        return jsonify({"ok": bool(title) and db.rename_conversation(dev, cid, title)})
    msgs = db.get_messages(dev, cid)
    if msgs is None:
        return jsonify({"error": "ไม่พบบทสนทนานี้"}), 404
    return jsonify({"id": cid, "messages": msgs})


@app.route("/api/upload", methods=["POST"])
def upload():
    if not pin_ok():
        return jsonify({"success": False, "error": "PIN ไม่ถูกต้อง"}), 401
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"success": False, "error": "ไม่ได้เลือกไฟล์"})
    ext = f.filename.rsplit(".", 1)[-1].lower()
    buf = io.BytesIO(f.read())  # อ่านในหน่วยความจำ ไม่เขียนไฟล์ลงดิสก์
    text = ""
    try:
        if ext == "pdf":
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(buf).pages)
        elif ext == "docx":
            from docx import Document
            text = "\n".join(p.text for p in Document(buf).paragraphs)
        elif ext == "xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(buf, data_only=True, read_only=True)
            for ws in wb.worksheets:
                text += f"--- Sheet: {ws.title} ---\n"
                for row in ws.iter_rows(values_only=True):
                    if any(c is not None for c in row):
                        text += "\t".join("" if c is None else str(c) for c in row) + "\n"
        elif ext == "pptx":
            from pptx import Presentation
            for i, slide in enumerate(Presentation(buf).slides, 1):
                text += f"--- สไลด์ {i} ---\n"
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        text += "\n".join(p.text for p in shape.text_frame.paragraphs) + "\n"
        elif ext in ("txt", "md", "csv", "py", "js", "html", "css", "c", "cpp", "java", "json"):
            text = buf.getvalue().decode("utf-8", errors="ignore")
        else:
            return jsonify({"success": False, "error": "ยังไม่รองรับไฟล์นามสกุลนี้"})
    except Exception as e:
        return jsonify({"success": False, "error": f"อ่านไฟล์ไม่สำเร็จ: {e}"})
    text = text.strip()
    if not text:
        return jsonify({"success": False, "error": "ไม่พบข้อความในไฟล์ (ถ้าเป็น PDF แบบสแกน ระบบยังอ่านไม่ได้)"})
    return jsonify({"success": True, "content": text[:MAX_FILE_CHARS], "truncated": len(text) > MAX_FILE_CHARS,
                    "chars": len(text)})


db.init()
threading.Thread(target=_refresh_models_forever, daemon=True).start()

if __name__ == "__main__":
    print(f"Ollama: {'พร้อม' if ollama_up() else 'ยังไม่เปิด! (เปิดแอป Ollama ก่อน)'} | "
          f"โมเดลหลักสูตร: {DSEE_MODEL} | โมเดลทั่วไป: {GENERAL_MODEL}")
    print(f"เปิดในเครื่องนี้ได้ที่ http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)
