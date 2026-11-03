"""
แปลงเอกสาร (PDF/Word/Excel/txt) เป็น dataset คำถาม-คำตอบ (JSONL) สำหรับเทรน typhoon-gemma3
ใช้ Ollama ที่รันอยู่ในเครื่อง (เช่น typhoon-gemma3 หรือ gemma3) ช่วยแต่งคำถาม-คำตอบจากเนื้อหาจริง

วิธีใช้:
    python prepare_dataset.py --input "C:\\path\\to\\doc1.pdf" "C:\\path\\to\\doc2.pdf" ...
    python prepare_dataset.py --input-dir "C:\\path\\to\\folder"

ต้องเปิดแอป Ollama ไว้ก่อนรัน (ollama serve หรือเปิดแอป Ollama ค้างไว้)
"""

import argparse
import glob
import io
import json
import os
import re
import sys

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_URL}/api/chat"

SYSTEM_PERSONA = (
    "คุณคือ \"LIONBOT\" ผู้ช่วยอัจฉริยะด้านหลักสูตรและการศึกษา\n"
    "- บุคลิก: สุภาพ, เป็นมืออาชีพ, กระตือรือร้น\n"
    "- ตอบคำถามอย่างแม่นยำและกระชับ โดยอิงข้อมูลหลักสูตรจริง"
)

QA_GEN_PROMPT = """คุณคือผู้ช่วยสร้างชุดข้อมูลฝึกสอน AI
จากเนื้อหาด้านล่าง ให้สร้างคำถาม-คำตอบภาษาไทยจำนวน {n} คู่ ที่:
- คำถามเป็นคำถามที่คนทั่วไป (เช่น นิสิต/นักศึกษา) น่าจะถามเกี่ยวกับเนื้อหานี้
- คำตอบต้องถูกต้องตรงตามเนื้อหาที่ให้มาเท่านั้น ห้ามเดาหรือแต่งข้อมูลเพิ่ม
- คำตอบกระชับ ชัดเจน เป็นภาษาไทย

ตอบกลับเป็น JSON array เท่านั้น ห้ามมีข้อความอื่นนอกเหนือจาก JSON เช่น:
[{{"question": "...", "answer": "..."}}, {{"question": "...", "answer": "..."}}]

เนื้อหา:
\"\"\"
{chunk}
\"\"\"
"""


def read_pdf(path):
    import fitz  # PyMuPDF - more robust than pypdf against malformed PDFs

    doc = fitz.open(path)
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    return "\n".join(pages)


def read_docx(path):
    from docx import Document

    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def read_xlsx(path):
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def read_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return read_pdf(path)
    if ext in (".docx", ".doc"):
        return read_docx(path)
    if ext in (".xlsx", ".xls"):
        return read_xlsx(path)
    if ext == ".txt":
        return read_txt(path)
    raise ValueError(f"ไม่รองรับไฟล์ประเภท: {ext}")


def chunk_text(text, chunk_size=1500, overlap=200):
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if len(chunk) > 100:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def call_ollama(model, prompt, timeout=180):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def parse_qa_json(raw_text):
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    pairs = []
    for item in data:
        q = str(item.get("question", "")).strip()
        a = str(item.get("answer", "")).strip()
        if len(q) > 5 and len(a) > 5:
            pairs.append((q, a))
    return pairs


def generate_dataset(paths, model, questions_per_chunk, chunk_size, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    seen_questions = set()
    total_rows = 0

    # เปิดไฟล์แบบ append เพื่อให้เขียนผลลัพธ์ทันทีทีละ chunk (กันข้อมูลหายถ้าโปรแกรมถูกหยุดกลางทาง)
    with open(out_path, "a", encoding="utf-8") as out_f:
        for path in paths:
            print(f"[อ่านไฟล์] {os.path.basename(path)}", flush=True)
            try:
                text = extract_text(path)
            except Exception as e:
                print(f"  ข้ามไฟล์ (อ่านไม่ได้): {e}", flush=True)
                continue

            chunks = chunk_text(text, chunk_size=chunk_size)
            print(f"  แบ่งได้ {len(chunks)} chunk", flush=True)

            for i, chunk in enumerate(chunks):
                prompt = QA_GEN_PROMPT.format(n=questions_per_chunk, chunk=chunk)
                try:
                    raw = call_ollama(model, prompt)
                except requests.exceptions.ConnectionError:
                    print("  เชื่อมต่อ Ollama ไม่ได้ กรุณาเปิดแอป Ollama ค้างไว้แล้วลองใหม่", flush=True)
                    sys.exit(1)
                except Exception as e:
                    print(f"  chunk {i}: เรียก Ollama ไม่สำเร็จ ({e}) ข้าม", flush=True)
                    continue

                pairs = parse_qa_json(raw)
                new_count = 0
                for q, a in pairs:
                    if q in seen_questions:
                        continue
                    seen_questions.add(q)
                    row = {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PERSONA},
                            {"role": "user", "content": q},
                            {"role": "assistant", "content": a},
                        ]
                    }
                    out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    new_count += 1
                out_f.flush()
                total_rows += new_count
                print(f"  chunk {i+1}/{len(chunks)}: ได้ {new_count} คู่คำถาม-คำตอบ (สะสม {total_rows})", flush=True)

    print(f"\nเสร็จแล้ว: {total_rows} ตัวอย่าง -> {out_path}", flush=True)


def collect_paths(args):
    paths = list(args.input or [])
    if args.input_dir:
        for ext in ("*.pdf", "*.docx", "*.xlsx", "*.txt"):
            paths.extend(glob.glob(os.path.join(args.input_dir, ext)))
    return [p for p in paths if os.path.isfile(p)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="*", help="รายชื่อไฟล์เอกสาร (PDF/Word/Excel/txt)")
    parser.add_argument("--input-dir", help="โฟลเดอร์ที่มีเอกสารทั้งหมด")
    parser.add_argument("--model", default="typhoon-gemma3:latest", help="ชื่อโมเดล Ollama ที่ใช้แต่งคำถาม-คำตอบ")
    parser.add_argument("--questions-per-chunk", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=1500)
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "dataset", "dataset.jsonl"))
    args = parser.parse_args()

    paths = collect_paths(args)
    if not paths:
        print("ไม่พบไฟล์เอกสาร ระบุ --input หรือ --input-dir")
        sys.exit(1)

    generate_dataset(paths, args.model, args.questions_per_chunk, args.chunk_size, args.out)


if __name__ == "__main__":
    main()
