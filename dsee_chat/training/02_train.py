"""
เทรนโมเดล DSEE Buddy ในเครื่องตัวเอง (ย้ายมาจากขั้นตอน "4) เทรนโมเดล (LoRA)" บน Colab)

ต้องมี:
  - GPU การ์ดจอ NVIDIA ที่เพียงพอ (แนะนำ VRAM >= 12 GB เช่น RTX 3060 12GB ขึ้นไป)
  - ติดตั้ง: pip install unsloth trl peft datasets safetensors bitsandbytes

รัน:
  python 02_train.py

ผลลัพธ์:
  training/work/lora_adapter/     ← LoRA adapter ที่เทรนได้
  training/work/merged/           ← โมเดลรวม LoRA แล้ว (16-bit) ใช้ต่อในขั้น 03_export_gguf.py
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

ROLE_MAP = {"assistant": "model"}


def to_text(messages):
    # รูปแบบ Gemma3 เหมือน TEMPLATE ที่ Ollama ใช้ตอบจริงทุกตัวอักษร (system = user turn แรก)
    out = ""
    for m in messages:
        role = ROLE_MAP.get(m["role"], "user")
        out += f"<start_of_turn>{role}\n{m['content']}<end_of_turn>\n"
    return out


def build_prompt(messages):
    return to_text(messages) + "<start_of_turn>model\n"


def main():
    import torch

    if not torch.cuda.is_available():
        print("❌ ไม่พบ GPU (CUDA) ในเครื่องนี้ — การเทรนต้องใช้ GPU การ์ดจอ NVIDIA เท่านั้น")
        print("   ถ้าเครื่องนี้ไม่มี GPU ให้ใช้ Colab แทน (DSEE_Buddy_Colab.ipynb) แล้วดาวน์โหลดโมเดลที่เทรนแล้วมาใช้ในเครื่องนี้")
        sys.exit(1)

    os.makedirs(cfg.WORK_DIR, exist_ok=True)
    assert os.path.exists(cfg.DATASET_JSONL), f"ไม่พบ {cfg.DATASET_JSONL} — รัน dataset/make_dataset.py ก่อน"

    from unsloth import FastModel
    from datasets import Dataset

    print("โหลด base model:", cfg.BASE_MODEL)
    model, tokenizer = FastModel.from_pretrained(
        model_name=cfg.BASE_MODEL, max_seq_length=cfg.MAX_SEQ_LEN, load_in_4bit=True, full_finetuning=False
    )

    rank = cfg.LORA_RANK
    if cfg.TRAIN_MODE == "continue":
        import zipfile

        assert os.path.exists(cfg.OLD_LORA_ZIP), f"ไม่พบ {cfg.OLD_LORA_ZIP} (ตั้งค่า OLD_LORA_ZIP ใน config.py)"
        extract_dir = os.path.join(cfg.WORK_DIR, "old_lora")
        zipfile.ZipFile(cfg.OLD_LORA_ZIP).extractall(extract_dir)
        cfg_path = glob.glob(f"{extract_dir}/**/adapter_config.json", recursive=True)[0]
        rank = json.load(open(cfg_path))["r"]
        print("เทรนต่อจาก LoRA เดิม rank =", rank)

    model = FastModel.get_peft_model(
        model, finetune_vision_layers=False, finetune_language_layers=True,
        finetune_attention_modules=True, finetune_mlp_modules=True,
        r=rank, lora_alpha=rank, lora_dropout=0, bias="none", random_state=3407,
    )

    if cfg.TRAIN_MODE == "continue":
        from peft import set_peft_model_state_dict
        from safetensors.torch import load_file

        w = glob.glob(os.path.dirname(cfg_path) + "/adapter_model.safetensors")[0]
        print(set_peft_model_state_dict(model, load_file(w)))

    tok = getattr(tokenizer, "tokenizer", tokenizer)
    for t in ["<start_of_turn>", "<end_of_turn>"]:
        assert len(tok(t, add_special_tokens=False).input_ids) == 1, f"{t} ไม่ใช่ token เดียว"

    rows = [json.loads(line) for line in open(cfg.DATASET_JSONL, encoding="utf-8")]
    train_rows = [r for r in rows if r.get("split", "train") == "train"]
    texts = [to_text(r["messages"]) for r in train_rows]
    keep = [t for t in texts if len(tok(t).input_ids) <= cfg.MAX_SEQ_LEN]
    print(f"train {len(keep):,} ตัวอย่าง (ตัดที่ยาวเกิน {len(texts) - len(keep)})")
    train_ds = Dataset.from_list([{"text": t} for t in keep])

    from trl import SFTTrainer, SFTConfig
    from unsloth.chat_templates import train_on_responses_only

    try:
        FastModel.for_training(model)
    except Exception:
        model.train()

    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer, train_dataset=train_ds,
        args=SFTConfig(
            dataset_text_field="text", per_device_train_batch_size=4, gradient_accumulation_steps=4,
            num_train_epochs=cfg.NUM_EPOCHS, max_steps=cfg.MAX_STEPS if cfg.MAX_STEPS > 0 else -1,
            learning_rate=cfg.LEARNING_RATE, warmup_steps=10, lr_scheduler_type="cosine",
            optim="adamw_8bit", weight_decay=0.01, logging_steps=10,
            save_strategy="steps", save_steps=50, save_total_limit=2,
            seed=3407, output_dir=cfg.CKPT_DIR, report_to="none",
        ),
    )
    trainer = train_on_responses_only(
        trainer, instruction_part="<start_of_turn>user\n", response_part="<start_of_turn>model\n"
    )

    last = sorted(glob.glob(f"{cfg.CKPT_DIR}/checkpoint-*"), key=lambda p: int(p.rsplit("-", 1)[1]))
    if last:
        print("🔁 เครื่องนี้หลุด/รีสตาร์ตแล้วเทรนต่อจาก", last[-1])
    stats = trainer.train(resume_from_checkpoint=last[-1] if last else None)
    print(f"✅ เทรนเสร็จ {stats.metrics['train_runtime']/60:.0f} นาที | loss เฉลี่ย {stats.metrics['train_loss']:.4f}")

    os.makedirs(cfg.LORA_DIR, exist_ok=True)
    model.save_pretrained(cfg.LORA_DIR)
    tokenizer.save_pretrained(cfg.LORA_DIR)
    print("บันทึก LoRA adapter:", cfg.LORA_DIR)

    print("กำลังรวม LoRA เข้ากับโมเดลหลัก (16-bit) ...")
    model.save_pretrained_merged(cfg.MERGED_DIR, tokenizer, save_method="merged_16bit")
    print("✅ โมเดลรวมแล้ว:", cfg.MERGED_DIR)
    print("\nขั้นต่อไป: python 03_export_gguf.py")


if __name__ == "__main__":
    main()
