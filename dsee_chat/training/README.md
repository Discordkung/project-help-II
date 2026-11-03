# เทรนโมเดลในเครื่องตัวเอง (ทางเลือกแทน Colab)

ย้ายขั้นตอน "สร้าง dataset → เทรน LoRA → แปลง GGUF → โหลดเข้า Ollama" จาก `DSEE_Buddy_Colab.ipynb`
มาเป็นสคริปต์ที่รันในเครื่องได้โดยตรง ไม่ต้องเปิด Colab เลย

## ⚠️ ข้อจำกัดที่ต้องรู้ก่อน

**ขั้นตอน "เทรน" (`02_train.py`) ต้องมีการ์ดจอ NVIDIA (GPU, CUDA)** เท่านั้น — แนะนำ VRAM 12 GB ขึ้นไป
(การ์ดรุ่น RTX 3060 12GB, 3080, 4070 ขึ้นไป พอทำได้ ส่วนการ์ดจอออนบอร์ด/การ์ด AMD/Mac ทำไม่ได้)

เช็กว่าเครื่องมี GPU ที่ใช้ได้ไหม:
```bat
nvidia-smi
```
ถ้าขึ้นข้อมูลการ์ดจอมา = มี ถ้าขึ้น "ไม่พบคำสั่ง" / error = **ไม่มี ให้ใช้ Colab แทน** (`DSEE_Buddy_Colab.ipynb`)
แล้วดาวน์โหลดไฟล์ `.gguf` ที่เทรนเสร็จจาก Google Drive มาทำขั้น `04_create_ollama.py` ในเครื่องนี้ต่อได้เลย
(ขั้นนั้นไม่ต้องใช้ GPU)

ขั้นตอนอื่น (`01` สร้าง dataset, `03` แปลง gguf, `04` โหลดเข้า Ollama, test) ใช้ CPU ได้ปกติ ไม่ต้องมี GPU

## ติดตั้ง

```bat
pip install -r requirements.txt
```

ถ้าจะเทรน (`02_train.py`) อาจต้องติดตั้ง PyTorch รุ่นที่ตรงกับ CUDA ของการ์ดจอก่อน ดูวิธีที่
https://pytorch.org/get-started/locally/

## วิธีรัน — เลือกได้ 2 แบบ

### แบบที่ 1: รันทีละขั้น (แนะนำ จะได้เห็นว่าติดขั้นไหน)
```bat
cd ..\dataset
python make_dataset.py .          REM ขั้น 1: สร้าง dataset.jsonl ใหม่ (ไม่บังคับ ถ้าใช้ของเดิมอยู่แล้วข้ามได้)
cd ..\training
python 02_train.py                REM ขั้น 2: เทรน (ต้องมี GPU)
python 03_export_gguf.py          REM ขั้น 3: แปลงเป็น .gguf
python 04_create_ollama.py        REM ขั้น 4: โหลดเข้า Ollama
```

### แบบที่ 2: รันรวดเดียว
```bat
python pipeline.py --step all
```
หรือเลือกทำทีละขั้น: `python pipeline.py --step dataset|train|gguf|ollama|test`

## ทดสอบหลังเทรนเสร็จ

เปิดแอปในหน้าต่างหนึ่ง:
```bat
cd ..
python run.py
```
แล้วรันทดสอบ 50 ข้อในอีกหน้าต่าง (ชุดคำถามเดียวกับที่ใช้บน Colab):
```bat
cd training
python run_test50.py
```
ผลบันทึกเป็น Excel ไว้ที่ `training/work/test50_ผลทดสอบ_*.xlsx`

## ตั้งค่า

แก้ค่าได้ที่ `training/config.py` (หรือตั้ง environment variable ชื่อเดียวกัน) เช่น
`TRAIN_MODE` (`base`/`continue`), `NUM_EPOCHS`, `LORA_RANK`, `LEARNING_RATE`, `QUANT` (`q8_0`/`f16`)

## ถ้าเทรนในเครื่องไม่ไหว (ไม่มี GPU / การ์ดจอเล็กไป)

ใช้ **Colab** (`DSEE_Buddy_Colab.ipynb`) เทรนแทนได้เหมือนเดิม — โค้ดในโฟลเดอร์นี้แปลงมาจาก
ขั้นตอนเดียวกันกับที่ Colab ใช้เป๊ะ ๆ ผลลัพธ์จะเหมือนกัน ต่างกันแค่ "รันที่ไหน" เมื่อเทรนบน Colab เสร็จแล้ว
ดาวน์โหลดไฟล์ `.gguf` จาก Google Drive มาไว้ในเครื่องนี้ (เช่นที่ `training/work/`) แล้วรันแค่
`python 04_create_ollama.py` ต่อได้เลย (แก้ `GGUF_OUT` ใน `config.py` ให้ชี้ไปที่ไฟล์ที่ดาวน์โหลดมา ถ้าชื่อไม่ตรง)
