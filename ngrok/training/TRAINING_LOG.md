# สรุปขั้นตอนการเทรน LIONBOT v2 (typhoon-gemma3 fine-tune)

## เป้าหมาย
เทรนโมเดล AI โดยใช้ base model `typhoon-gemma3` ให้มีความรู้เฉพาะทางด้าน **หลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์** (คำอธิบายรายวิชา, โครงสร้างหลักสูตร, แผนการศึกษา) แล้วนำไปใช้กับแอป LIONBOT ที่มีอยู่เดิม (React + Flask + Ollama)

## 1. รีวิวโปรเจกต์เดิม
- ตรวจสอบโครงสร้าง `my-app/` (frontend React + backend Flask + Ollama)
- พบประเด็นที่ควรแก้: ไม่มี `.gitignore` root (เสี่ยง commit ไฟล์โมเดล 4.6GB), URL ngrok hardcode, CORS เปิดกว้าง, conversation history เป็น global variable, `debug=True` ใน production

## 2. วางแผนการเทรน
ถามผู้ใช้เพื่อยืนยันรายละเอียด:
- **Dataset**: ยังไม่มี ต้องการคำแนะนำวิธีสร้าง
- **เป้าหมาย**: เพิ่มความรู้เฉพาะทาง/โดเมน (ภายหลังระบุเป็นหลักสูตรวิศวกรรมไฟฟ้าฯ)
- **Export**: GGUF สำหรับ Ollama
- **Colab**: ฟรี (T4, 16GB VRAM)
- **Base model**: ยืนยันผ่าน web search ว่า `scb10x/typhoon2.1-gemma3-4b` มีอยู่จริงบน Hugging Face และ Unsloth รองรับ QLoRA fine-tune บน T4 ฟรีได้

## 3. สร้าง Colab notebook (`train_typhoon_lionbot_v2.ipynb`)
สร้าง notebook ผ่านเบราว์เซอร์ (พิมพ์โค้ดเข้าไปทีละเซลล์) ประกอบด้วย:
1. ติดตั้ง Unsloth + เช็ค GPU
2. โหลด `scb10x/typhoon2.1-gemma3-4b` แบบ 4-bit + ตั้งค่า QLoRA (r=16, target modules ครบ)
3. อัปโหลด `dataset.jsonl` + แปลงด้วย Gemma-3 chat template
4. เทรนด้วย `SFTTrainer` (batch 2, grad accum 4, 3 epochs, lr 2e-4)
5. บันทึกและแปลงเป็น GGUF (`q4_k_m`) + ดาวน์โหลด
6. คำแนะนำสร้าง Ollama model ด้วย Modelfile

ตั้ง runtime เป็น **T4 GPU**

## 4. เตรียม dataset — ลองแนวทางแรก (ใช้ Ollama ช่วยแต่ง) แล้วยกเลิก
- ผู้ใช้ส่งเอกสาร 4 ไฟล์ PDF: คำอธิบายรายวิชา, โครงสร้างหลักสูตร, ตัวอย่างแผนการศึกษา (ปกติ/สหกิจศึกษา)
- เขียนสคริปต์ `prepare_dataset.py` ให้ดึงข้อความจากเอกสารแล้วใช้ `typhoon-gemma3` (ผ่าน Ollama ในเครื่อง) ช่วย generate คำถาม-คำตอบอัตโนมัติ
- ปัญหาที่เจอ:
  - แบ่ง chunk ผิดพลาด (841 chunks จากไฟล์เดียว เพราะ bug ของ `pypdf` กับ PDF ที่มี broken xref — สลับไปใช้ `PyMuPDF (fitz)` แก้ได้)
  - รันช้ามาก (~2.5 นาที/chunk) และ**ผู้ใช้ขอให้เปลี่ยนวิธี** ไม่ใช้ Ollama ช่วยแต่งแล้ว ให้ Claude เขียน dataset ให้โดยตรงแทน

## 5. เตรียม dataset — แนวทางที่ใช้จริง (เขียนเองจากเนื้อหาต้นฉบับ)
- อ่านเนื้อหาเต็มจากเอกสารทั้ง 4 ไฟล์ (ใช้ PyMuPDF แก้ปัญหา font-encoding ที่ผิดเพี้ยน เช่น `Ā→ห, ü→ว, ÿ→ส, ý→ศ, þ→ษ`)
- เขียนสคริปต์ `build_dataset.py` ที่มีข้อมูลโครงสร้าง (รายวิชา ~50 วิชา, โครงสร้างหลักสูตร, แผนการศึกษา 2 แบบ) แล้ว generate คำถาม-คำตอบด้วย template หลายรูปแบบ
- ได้ **`dataset.jsonl` จำนวน 240 ตัวอย่าง** ครอบคลุม:
  - คำอธิบายรายวิชา (เนื้อหา, หน่วยกิต, ชื่ออังกฤษ, วิชาบังคับก่อน)
  - โครงสร้างหลักสูตร (หน่วยกิตรวม, หมวดวิชา, ความหมายรหัสวิชา)
  - แผนการศึกษารายภาคทั้งสองแบบ + คำถามเปรียบเทียบ

## 6. รัน Colab notebook จริง
รันทีละเซลล์ผ่านเบราว์เซอร์ พร้อมแก้ปัญหาที่เจอระหว่างทาง:
1. ติดตั้ง Unsloth สำเร็จ, ยืนยัน GPU = Tesla T4
2. โหลดโมเดล + ตั้งค่า QLoRA สำเร็จ
3. อัปโหลด `dataset.jsonl` (ผู้ใช้เลือกไฟล์เอง) + format ด้วย chat template สำเร็จ (240/240)
4. เทรน 90 steps (3 epochs) — **Loss ลดจาก 4.03 → 0.254**
5. แปลงเป็น GGUF (`q4_k_m`) สำเร็จ — ใช้เวลารวม install llama.cpp + convert ~17 นาที
   - เจอ bug: path ที่โค้ดคาดไว้ (`typhoon-lionbot-gguf/`) ผิดจากโฟลเดอร์จริงที่ Unsloth สร้าง (`typhoon-lionbot-gguf_gguf/`) แก้ด้วย `glob.glob("**/*.gguf", recursive=True)`
6. ดาวน์โหลดผ่านเบราว์เซอร์ (`files.download()`) ไม่แน่ใจว่าไปถึงเครื่องจริงเพราะเป็น sandboxed browser จึง**เปลี่ยนมาเซฟลง Google Drive แทน** (mount Drive + copy ไฟล์)

## ผลลัพธ์ปัจจุบัน
✅ ไฟล์โมเดลสุดท้าย: **`typhoon2.1-gemma3-4b.Q4_K_M.gguf`**
📁 ตำแหน่ง: **Google Drive ของผู้ใช้ > My Drive > typhoon-lionbot-gguf/**

## ขั้นตอนที่เหลือ (ยังไม่ได้ทำ)
1. ดาวน์โหลดไฟล์ GGUF จาก Google Drive มาไว้ในเครื่อง (เช่น `my-app/backend/`)
2. สร้างไฟล์ `Modelfile`:
   ```
   FROM ./typhoon2.1-gemma3-4b.Q4_K_M.gguf
   PARAMETER temperature 0.7
   SYSTEM คุณคือ LIONBOT ผู้ช่วยอัจฉริยะด้านหลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์
   ```
3. รัน `ollama create typhoon-lionbot-v2 -f Modelfile`
4. เพิ่ม `"typhoon-lionbot-v2"` เข้า `AVAILABLE_MODELS` ใน `my-app/backend/server.py`
5. ทดสอบผ่านหน้าเว็บแชท

## ไฟล์ที่เกี่ยวข้องในโปรเจกต์
- `my-app/training/build_dataset.py` — สคริปต์สร้าง dataset.jsonl (ใช้งานจริง)
- `my-app/training/prepare_dataset.py` — สคริปต์แนวทางแรก (ใช้ Ollama ช่วยแต่ง, ไม่ได้ใช้งานต่อ)
- `my-app/training/dataset/dataset.jsonl` — dataset 240 ตัวอย่าง
- Colab notebook: `train_typhoon_lionbot_v2.ipynb` (อยู่ใน Google Drive/Colab ของผู้ใช้)

## เตรียมเทรน v3 (2026-09-22)
- ผู้ใช้มีไฟล์ `phakin.gguf` (`D:\Downloads\phakin.gguf`) — ตรวจสอบแล้วขนาด/เวลาแก้ไขตรงกับ `typhoon2.1-gemma3-4b.Q4_K_M.gguf` เป๊ะ คือไฟล์เดียวกัน
- **ข้อจำกัดสำคัญ:** GGUF เป็นไฟล์ที่ quantize แล้ว เทรนต่อโดยตรงด้วย Unsloth/PEFT ไม่ได้ ต้องมีเช็คพอยต์ LoRA/HF ต้นทาง (ก่อน merge + quantize) เท่านั้น
- รอบเทรน v2 ไม่แน่ใจว่าเซฟ adapter checkpoint แยกไว้ใน Drive หรือไม่ (log ระบุแค่ขั้นตอน export GGUF โดยตรง)
- เครื่องนี้ไม่มี GPU (`torch` เป็น CPU-only build) — เทรนต้องทำผ่าน Colab เหมือนเดิม
- สร้าง `train_typhoon_lionbot_v3.ipynb` ให้: ค้นหา adapter เดิมใน Drive อัตโนมัติ (glob หา `adapter_config.json`) ถ้าเจอจะเทรนต่อยอดจริง ถ้าไม่เจอจะ fallback ไปเทรนใหม่จาก `scb10x/typhoon2.1-gemma3-4b` พร้อม dataset เดิม — และ**เพิ่มขั้นตอนเซฟ adapter ลง Drive ทุกครั้งหลังเทรนเสร็จ** กันปัญหานี้เกิดซ้ำตอนเทรน v4
- ยังไม่ได้รันจริงใน Colab (ต้องให้ผู้ใช้เปิดรันเอง หรือขอให้ Claude ขับผ่านเบราว์เซอร์เหมือนตอน v2)

## 2026-10-06 — dataset v2 (curriculum-grounded)
- สร้างด้วย `build_dataset_v2.py` จากข้อความ PDF ที่ถอดรหัสแล้ว (`clean/parsed.json`) เพราะไฟล์ .md ต้นฉบับตัวอักษร ว ศ ษ ส ห เสียหาย
- ผลลัพธ์: `dataset/dataset.jsonl` = 1,910 ตัวอย่าง (ของเดิม 240 ตัวอย่างสำรองไว้ที่ `dataset/dataset_v1_240.jsonl`)
- ครอบคลุม: รายวิชา 94 วิชา (ชื่อ/รหัส/หน่วยกิต/คำอธิบาย/prerequisite/ปี-เทอม), แผนปกติ+สหกิจรายเทอม/รายปี, เปรียบเทียบสองแผน, โครงสร้างหลักสูตร, ความหมายรหัสวิชา, ตัวอย่างปฏิเสธ (ไม่มีข้อมูล/รหัสไม่มี)
- ยังไม่ได้เทรนใหม่

### v4 result (2026-10-06)
- เทรนจบ 717 steps (loss ~0.1-0.2), GGUF -> Ollama `typhoon-lionbot-v4` (ต้องใส่ TEMPLATE Gemma เองใน Modelfile เพราะ GGUF จาก Unsloth ไม่มี template)
- ทดสอบ: รูปแบบคำตอบถูก (ปฏิเสธเรื่องค่าเทอมได้) แต่ **รหัสวิชา/prerequisite/เนื้อหายังผิด แม้กับคำถามที่อยู่ใน dataset** -> fine-tune จำตัวเลข/รหัสไม่ได้
- DEFAULT_MODEL ยังเป็น v3; v4 เลือกได้ใน dropdown. แนวทางแก้: RAG (ดึงข้อมูลจาก parsed.json ใส่ prompt)

### RAG (2026-10-06)
- เพิ่ม `backend/curriculum_rag.py` + `backend/curriculum_data.json` (สำเนา clean/parsed.json): ตรวจรหัสวิชา/ชื่อวิชา/ปี-เทอม/สหกิจ-ปกติ แล้วแนบข้อมูลจริงเข้า prompt
- `server.py`: เมื่อเลือกโมเดล typhoon-lionbot* จะส่งไป `typhoon-gemma3` (โมเดลฐาน) พร้อมข้อมูลอ้างอิงแทน เพราะโมเดลที่เทรนตอบจากความจำและผิดบ่อย
- ทดสอบผ่าน /api/chat: prerequisite, แผนรายเทอม, รหัสไม่มี, เปรียบเทียบสหกิจ/ปกติ ถูกต้อง

### Eval 100 ข้อ (2026-10-06)
- v4 ไม่มี RAG 19% | RAG ก่อนแก้ 95% | RAG หลังแก้ 98%+ (เพิ่ม direct_answer: แผนรายเทอม + FAQ โครงสร้าง/ฝึกงาน-สหกิจ; ชุดย่อยที่เคยพลาด 31/31)
- สคริปต์: training/eval_100.py (ผลดิบ eval_rag.json / eval_raw.json / eval_rag_after.json)

### v5: Continued Pretraining (CPT) — เตรียมไว้ ยังไม่ได้เทรน (2026-10-20)
- **ส่วนที่ v4 ยังไม่เคยเห็น** (ตรวจเทียบ dataset.jsonl แล้ว): วิชาหมวดวิชาศึกษาทั่วไป 196 วิชา (มีใน dataset แค่ 01999111) และเงื่อนไขเกรดของนิสิต (สหกิจ 2.50 / จบ 2.00 / เกียรตินิยม 3.50, 3.25 / พ้นสภาพ 1.50, 1.75). คำอธิบายรายวิชา 93 วิชามีครบแล้ว
- `build_cpt_corpus.py` อ่าน `รวมหลักสูตร-วิศวกรรมไฟฟ้า.md` -> `dataset/cpt_corpus.jsonl` (502 เอกสาร ~78k โทเคน: intro 4, group 9, course 392 (สองสำนวนต่อวิชา), rules 4, replay คำอธิบายรายวิชา 93), `dataset/cpt_sft_mix.jsonl` (400 คำถามสั้นสำหรับ SFT หลัง CPT), `dataset/cpt_gened.json`
- `train_typhoon_lionbot_v5_cpt.ipynb` (Colab T4): อัปโหลดแค่ไฟล์ .md + dataset.jsonl แล้ว notebook สร้างคลังข้อความเอง -> CPT (UnslothTrainer, LoRA r=32 + embed_tokens/lm_head, LR 1e-4 / embedding 1e-5, 3 epochs, ข้อมูลใหม่ซ้ำ 2 เท่า) -> เซฟ adapter -> SFT (dataset.jsonl + cpt_sft_mix.jsonl, LR 1e-4) -> GGUF
- `eval_cpt_probe.py MODEL N`: ถามตรงๆ ไม่ผ่าน RAG (รหัส->ชื่อ, ชื่อ->รหัส, หน่วยกิต, เกณฑ์เกรด) ใช้เทียบ v4 กับ v5 ด้วยชุดเดียวกัน. baseline v4 (รันค้างไว้ 16 ข้อแรก (ล้วนเป็นรหัส->ชื่อ) แล้วหยุด): ถูก 0/16
- **ข้อควรระวัง:** v3/v4 จำรหัสวิชาไม่แม่นแม้เทรนด้วยข้อมูลเดียวกัน ข้อมูลชุดเล็กแบบ CPT อาจฉีดข้อเท็จจริงได้จำกัด ให้วัดด้วย eval_cpt_probe.py ก่อนใช้ v5 และคง RAG ไว้

### RAG วิชาศึกษาทั่วไป / วิชาเสรี (2026-10-20)
- เพิ่ม `backend/gened_data.json` (196 วิชา จาก รวมหลักสูตร-วิศวกรรมไฟฟ้า.md ส่วนที่ 5) + `backend/gened_rag.py`; `curriculum_rag.retrieve()` เรียกใช้: รหัส/ชื่อวิชา, รายการทั้งกลุ่มสาระ/กลุ่มย่อย, ภาพรวม "วิชาเสรี", ค้นจากหัวข้อ (เช่น ภาษาญี่ปุ่น โยคะ ดนตรี). วิชาเหล่านี้ถูกรวมเข้า `COURSES` ด้วย ตัวคำนวณเกรดจึงใช้ชื่อ/หน่วยกิตได้
- `direct_answer()`: ขอรายการทั้งกลุ่มล้วนๆ ตอบจากข้อมูลตรงๆ เพราะโมเดลตอบสุนทรียศาสตร์ครบแค่ 10/15 วิชา (และแต่งยอดหน่วยกิตรวมเอง) คำถามที่ต้องวิจารณญาณ (แนะนำ/ง่าย/เกรด) ยังส่งให้โมเดลพร้อม context
- ทดสอบ `backend/test_gened_rag.py` ผ่านทั้งหมด (ทุกรหัส/ทุกชื่อ 196 วิชา, รายการกลุ่ม 15/14/47/61, หัวข้อ, ไม่กระทบคำถามหลักสูตรเดิม); ทดสอบกับโมเดลจริง 6 ข้อ ถูก 5 + ข้อที่พลาด (รายการสุนทรียศาสตร์) แก้ด้วย direct listing
- (2026-10-20) เพิ่ม `train_v5_colab.py` = สคริปต์ชุดเดียวกับ notebook v5 วางรันใน cell เดียวของ Colab ได้ และเพิ่มทางลัดอ่านไฟล์ input จาก Drive (`MyDrive/lionbot_v5_input/`) ตรวจ syntax และจำลองขั้นสร้างข้อมูลแล้ว ยังไม่ได้รันขั้นเทรนบน GPU จริง
- (2026-10-20) **ถอด RAG วิชาศึกษาทั่วไปออกตามที่ผู้ใช้สั่ง**: ลบ `backend/gened_rag.py`, `backend/gened_data.json`, `backend/test_gened_rag.py` และถอดโค้ดที่เรียกใช้ออกจาก `curriculum_rag.py` (RAG หลักสูตรเดิม ความจำ และตัวคำนวณเกรดไม่ถูกแตะ) ข้อมูลวิชาศึกษาทั่วไปเหลือใช้ใน CPT เท่านั้น (`training/dataset/cpt_gened.json`) ผลที่ตามมา: บอตตอบเรื่องวิชาศึกษาทั่วไปด้วย RAG ไม่ได้อีก และตัวคำนวณเกรดไม่รู้จักชื่อ/หน่วยกิตวิชาเหล่านี้ (ต้องระบุหน่วยกิตเอง เช่น "วิชา 3 หน่วยกิต ได้ B")
