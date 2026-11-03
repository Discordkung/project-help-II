"""
สั่งรันทุกขั้นตอนการเทรนรวดเดียว (เทียบเท่า "Run all" บน Colab แต่รันในเครื่องตัวเอง)

ใช้:
  python pipeline.py --step all          # ทำทุกขั้นตอน: dataset -> train -> gguf -> ollama
  python pipeline.py --step dataset      # แค่สร้าง dataset.jsonl ใหม่ (ไม่ต้องมี GPU)
  python pipeline.py --step train        # แค่เทรน (ต้องมี GPU)
  python pipeline.py --step gguf         # แค่แปลงเป็น gguf
  python pipeline.py --step ollama       # แค่โหลดเข้า Ollama
  python pipeline.py --step test         # ทดสอบ 50 ข้อ ผ่าน backend ที่รันอยู่ในเครื่อง
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, cwd=HERE):
    print(f"\n=== กำลังรัน {script} ===")
    r = subprocess.run([sys.executable, script], cwd=cwd)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--step", choices=["all", "dataset", "train", "gguf", "ollama", "test"], default="all")
    args = p.parse_args()

    steps = {
        "dataset": lambda: run("make_dataset.py", cwd=os.path.join(HERE, "..", "dataset")),
        "train": lambda: run("02_train.py"),
        "gguf": lambda: run("03_export_gguf.py"),
        "ollama": lambda: run("04_create_ollama.py"),
        "test": lambda: run("run_test50.py"),
    }

    if args.step == "all":
        for name in ["dataset", "train", "gguf", "ollama"]:
            steps[name]()
        print("\n🎉 ครบทุกขั้นตอนแล้ว — เปิดแอปด้วย: cd .. && python run.py")
        print("   แล้วค่อยรัน: python pipeline.py --step test   (ทดสอบ 50 ข้อ ตอนแอปรันอยู่)")
    else:
        steps[args.step]()


if __name__ == "__main__":
    main()
