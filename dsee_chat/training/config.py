"""
ตั้งค่าการเทรนโมเดล (เทียบเท่าเซลล์ #@param ใน Colab)
แก้ค่าที่นี่ หรือส่งผ่าน environment variable ชื่อเดียวกัน (ตัวพิมพ์ใหญ่) ก็ได้
"""
import os

TRAIN_MODE = os.environ.get("TRAIN_MODE", "base")        # "base" = เทรนใหม่ | "continue" = เทรนต่อจาก LoRA เดิม
BASE_MODEL = os.environ.get("BASE_MODEL", "scb10x/typhoon2.1-gemma3-4b")
OLD_LORA_ZIP = os.environ.get("OLD_LORA_ZIP", "./lora_adapter_old.zip")  # ใช้เมื่อ TRAIN_MODE=continue
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "2"))
LORA_RANK = int(os.environ.get("LORA_RANK", "32"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "2e-4"))
MAX_STEPS = int(os.environ.get("MAX_STEPS", "0"))         # 0 = เทรนครบตาม epochs
MAX_SEQ_LEN = int(os.environ.get("MAX_SEQ_LEN", "2048"))
QUANT = os.environ.get("QUANT", "q8_0")                    # "q8_0" (แนะนำ) หรือ "f16"

GGUF_NAME = f"dsee-typhoon.{QUANT}.gguf"
OLLAMA_NAME = os.environ.get("OLLAMA_NAME", "dsee-typhoon")
GENERAL_MODEL = os.environ.get("GENERAL_MODEL", "hf.co/typhoon-ai/typhoon2.1-gemma3-4b-gguf:Q4_K_M")

# โฟลเดอร์งาน (อยู่ในเครื่องทั้งหมด ไม่ใช้ Google Drive)
WORK_DIR = os.environ.get("WORK_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "work")))
DATASET_JSONL = os.environ.get(
    "DATASET_JSONL",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset", "dataset.jsonl")),
)
CKPT_DIR = os.path.join(WORK_DIR, f"checkpoints_{TRAIN_MODE}")
LORA_DIR = os.path.join(WORK_DIR, "lora_adapter")
MERGED_DIR = os.path.join(WORK_DIR, "merged")
LLAMACPP_DIR = os.environ.get("LLAMACPP_DIR", os.path.join(WORK_DIR, "llama.cpp"))
GGUF_OUT = os.path.join(WORK_DIR, GGUF_NAME)
MODELFILE_OUT = os.path.join(WORK_DIR, "Modelfile")
