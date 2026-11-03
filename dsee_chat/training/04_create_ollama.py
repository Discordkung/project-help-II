"""
สร้าง Modelfile แล้วโหลดโมเดลเข้า Ollama ในเครื่อง
(ย้ายมาจากขั้นตอน "6) ติดตั้ง Ollama + โหลดโมเดล" บน Colab)

ก่อนรัน: เปิดแอป Ollama ในเครื่องให้ทำงานอยู่ก่อน (ติดตั้งจาก https://ollama.com)

รัน:
  python 04_create_ollama.py

ผลลัพธ์:
  โมเดลชื่อ dsee-typhoon (หรือค่าที่ตั้งใน config.py) พร้อมใช้งานใน Ollama
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

TEMPLATE = """{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 }}
{{- if or (eq .Role "user") (eq .Role "system") }}<start_of_turn>user
{{ .Content }}<end_of_turn>
{{ if $last }}<start_of_turn>model
{{ end }}
{{- else if eq .Role "assistant" }}<start_of_turn>model
{{ .Content }}{{ if not $last }}<end_of_turn>
{{ end }}
{{- end }}
{{- end }}"""


def main():
    assert os.path.exists(cfg.GGUF_OUT), f"ไม่พบ {cfg.GGUF_OUT} — รัน 03_export_gguf.py ก่อน"

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset")))
    import dsee_kb  # noqa: E402

    modelfile = (
        f'FROM {cfg.GGUF_OUT}\n'
        f'TEMPLATE """{TEMPLATE}"""\n'
        f'SYSTEM """{dsee_kb.SYSTEM_PROMPT}"""\n'
        'PARAMETER stop "<end_of_turn>"\n'
        'PARAMETER stop "<start_of_turn>"\n'
        'PARAMETER temperature 0.1\n'
        'PARAMETER repeat_penalty 1.1\n'
        'PARAMETER num_ctx 4096\n'
    )
    with open(cfg.MODELFILE_OUT, "w", encoding="utf-8") as f:
        f.write(modelfile)
    print("เขียน Modelfile:", cfg.MODELFILE_OUT)

    r = subprocess.run(["ollama", "create", cfg.OLLAMA_NAME, "-f", cfg.MODELFILE_OUT])
    if r.returncode != 0:
        print("❌ สร้างโมเดลไม่สำเร็จ — เช็กว่าเปิดแอป Ollama ไว้แล้วหรือยัง")
        sys.exit(r.returncode)

    print(f"\nดึงโมเดลทั่วไปเพิ่ม ({cfg.GENERAL_MODEL}) ...")
    subprocess.run(["ollama", "pull", cfg.GENERAL_MODEL])

    subprocess.run(["ollama", "list"])
    print(f"\n✅ โมเดล '{cfg.OLLAMA_NAME}' พร้อมใช้งานใน Ollama แล้ว")
    print("ไปเปิดแอปแชทได้เลย: cd .. && python run.py")


if __name__ == "__main__":
    main()
