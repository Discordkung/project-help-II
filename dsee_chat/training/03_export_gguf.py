"""
แปลงโมเดลที่เทรนแล้ว (training/work/merged) เป็นไฟล์ .gguf สำหรับ Ollama
(ย้ายมาจากขั้นตอน "5) วัดผล + แปลงเป็น GGUF" บน Colab)

ต้องมี:
  - git, python3 (มีอยู่แล้วแน่นอนถ้ารันไฟล์นี้ได้)
  - เนื้อที่ดิสก์ว่างอีก ~10 GB (โคลน llama.cpp + ไฟล์ gguf)

รัน:
  python 03_export_gguf.py

ผลลัพธ์:
  training/work/<ชื่อไฟล์>.gguf  ← เอาไปใช้ในขั้น 04_create_ollama.py
"""
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

# chat template เดียวกับตอนเทรน (Gemma3 style) — ถ้าไม่แก้ Ollama จะใช้ template ของ Typhoon เดิมแล้วตอบว่างเปล่า
JINJA = (
    "{% for m in messages %}<start_of_turn>{% if m['role'] == 'assistant' %}model{% else %}user{% endif %}\n"
    "{{ m['content'] }}<end_of_turn>\n{% endfor %}{% if add_generation_prompt %}<start_of_turn>model\n{% endif %}"
)


def run(cmd, **kw):
    print("$", " ".join(cmd))
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        sys.exit(r.returncode)
    return r


def main():
    assert os.path.isdir(cfg.MERGED_DIR), f"ไม่พบ {cfg.MERGED_DIR} — รัน 02_train.py ให้เสร็จก่อน"
    os.makedirs(cfg.WORK_DIR, exist_ok=True)

    if not os.path.isdir(cfg.LLAMACPP_DIR):
        run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", cfg.LLAMACPP_DIR])
    run([sys.executable, "-m", "pip", "install", "-q", os.path.join(cfg.LLAMACPP_DIR, "gguf-py")])

    raw_gguf = os.path.join(cfg.WORK_DIR, "raw.gguf")
    run([
        sys.executable, os.path.join(cfg.LLAMACPP_DIR, "convert_hf_to_gguf.py"),
        cfg.MERGED_DIR, "--outfile", raw_gguf, "--outtype", cfg.QUANT,
    ])

    script = sorted(glob.glob(f"{cfg.LLAMACPP_DIR}/gguf-py/**/gguf_new_metadata.py", recursive=True))[0]
    run([
        sys.executable, script, raw_gguf, cfg.GGUF_OUT,
        "--chat-template", JINJA, "--force",
    ])
    os.remove(raw_gguf)
    shutil.rmtree(cfg.MERGED_DIR, ignore_errors=True)

    size_gb = os.path.getsize(cfg.GGUF_OUT) / 1e9
    print(f"✅ GGUF พร้อมแล้ว: {cfg.GGUF_OUT} ({size_gb:.2f} GB)")
    print("\nขั้นต่อไป: python 04_create_ollama.py")


if __name__ == "__main__":
    main()
