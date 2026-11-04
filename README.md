 🦁 LIONBOT — แชตบอตผู้ช่วยตอบคำถามหลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์
![React](https://img.shields.io/badge/Frontend-React_18-61DAFB?style=for-the-badge&logo=react)
![Flask](https://img.shields.io/badge/Backend-Flask-000000?style=for-the-badge&logo=flask)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite)
![Ollama](https://img.shields.io/badge/LLM-Ollama-000000?style=for-the-badge&logo=ollama)
![Typhoon](https://img.shields.io/badge/Base_Model-Typhoon_2.1_Gemma3_4B-FF6B6B?style=for-the-badge)
[![Accuracy](https://img.shields.io/badge/RAG_Accuracy-98%25%2B-brightgreen?style=for-the-badge)]()
> **LIONBOT** คือระบบ AI แชตบอตสำหรับให้ข้อมูลหลักสูตร **วิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ (วศ.บ. ปรับปรุง พ.ศ. 2565 มหาวิทยาลัยเกษตรศาสตร์ วิทยาเขตศรีราชา)** โดยใช้สถาปัตยกรรม **RAG (Retrieval-Augmented Generation)** ร่วมกับโมเดลประมวลผลภาษาไทย ให้ความแม่นยำสูงกว่า 98% ในการตอบข้อมูลรายวิชา แผนการเรียนปกติ/สหกิจศึกษา และโครงสร้างหลักสูตร
---
📌 สารบัญ (Table of Contents)
✨ คุณสมบัติเด่น (Features)
🏗️ สถาปัตยกรรมระบบ (Architecture)
🛠️ เทคโนโลยีที่ใช้ (Tech Stack)
📁 โครงสร้างโปรเจกต์ (Project Structure)
📊 ผลการทดสอบประสิทธิภาพ (Evaluation Benchmark)
🚀 วิธีการติดตั้งและรันระบบ (Quick Start)
💡 ข้อค้นพบและบทเรียนสำคัญ (Key Insights)
🔮 ข้อจำกัดและงานที่จะพัฒนาต่อ (Limitations & Future Work)
---
✨ คุณสมบัติเด่น (Features)
UI สไตล์ Futuristic ธีมแดง-ดำ: ดีไซน์หน้าเว็บทันสมัย พร้อมอนิเมชัน Ripple effect บนปุ่ม, จุดขยับขณะรอโมเดลตอบ และระบบลบประวัติแบบยืนยันสองชั้น (Double Confirmation)
Real-time Streaming Response: รองรับการส่งคำตอบแบบ Stream (SSE) ตอบสนองรวดเร็วโดยไม่ต้องรอจนจบประโยค และสามารถกดหยุดตอบ (Abort Request) ได้ทันที
RAG & Direct Answer Pipeline: ค้นหาและแนบข้อมูลจริงจากโครงสร้างหลักสูตรเพื่อป้องกันปัญหา AI แต่งตัวเลขหรือรหัสวิชาขึ้นมาเอง (Hallucination)
รองรับทั้งแผนปกติและสหกิจศึกษา: สามารถเปรียบเทียบ แนะนำ และสรุปรายวิชาของทั้งสองแผน (144 หน่วยกิต) รายปีและรายเทอมได้อย่างแม่นยำ
ระบบจัดการบทสนทนา: บันทึกประวัติการสนทนาลงฐานข้อมูล SQLite อัตโนมัติ พร้อมรองรับการแนบไฟล์/รูปภาพประกอบคำถาม
---
🏗️ สถาปัตยกรรมระบบ (Architecture)
```text
 ┌──────────────────────────────────────────────────────────┐
 │                   หน้าเว็บ React (Port 3000)              │
 └────────────────────────────┬─────────────────────────────┘
                              │ POST /api/chat (SSE Stream)
                              ▼
 ┌──────────────────────────────────────────────────────────┐
 │                   Flask Backend (Port 8000)              │
 │ ───────────── DB: SQLite (conversations / messages)      │
 └──────────────┬────────────────────────────┬──────────────┘
                │                            │
   [ Direct Answer Match ]        [ Retrieval Match ]
   ตอบตรงสำหรับ FAQ / รายเทอม        ดึง Context รายวิชา / โครงสร้าง
                │                            │
                └──────────────┬─────────────┘
                               ▼
 ┌──────────────────────────────────────────────────────────┐
 │                    Ollama (Port 11434)                   │
 │           (โมเดลฐาน: typhoon-gemma3 / Fine-tuned)          │
 └──────────────────────────────────────────────────────────┘
```
---
🛠️ เทคโนโลยีที่ใช้ (Tech Stack)
ส่วนประกอบ	เทคโนโลยีที่เลือกใช้
Frontend	React, CSS3 (Custom Dark Futuristic Theme), Fetch API
Backend	Python 3, Flask, flask-cors, SQLite3
LLM Engine	Ollama, Typhoon 2.1 Gemma3 4B
Fine-Tuning & Pipeline	Unsloth (QLoRA 4-bit), PyTorch, Google Colab (T4 GPU), llama.cpp / GGUF
Dataset & Parser	Custom Python Parsers (`parse_sources.py`), JSONL (1,910 ตัวอย่าง)
---
📁 โครงสร้างโปรเจกต์ (Project Structure)
```text
my-app/
├── backend/
│   ├── server.py               # API Backend หลัก, การจัดการ DB และ Ollama Integration
│   ├── curriculum_rag.py        # Logic สำหรับ RAG และ Direct Answer Pipeline
│   ├── curriculum_data.json     # ข้อมูลหลักสูตรฉบับ Clean (Parsed จาก PDF)
│   ├── Modelfile.txt            # ไฟล์คอนฟิกสร้างโมเดล Ollama (Gemma Template)
│   └── lionbot.db               # ฐานข้อมูลประวัติแชต (SQLite)
├── frontend/
│   └── src/
│       └── components/
│           ├── bot.js           # คอมโพเนนต์หลักของ React Chat Interface
│           └── bot.css          # สไตล์ Futuristic Red-Black Theme
└── training/
    ├── parse_sources.py         # สคริปต์สกัดและแก้อักขระภาษาไทยจาก PDF ต้นฉบับ
    ├── build_dataset_v2.py      # สคริปต์สร้าง Dataset 1,910 ตัวอย่าง
    ├── train_typhoon_lionbot_v4.ipynb  # Notebook เทรน QLoRA บน Colab
    ├── eval_100.py              # สคริปต์ทดสอบความแม่นยำอัตโนมัติ 100 ข้อ
    └── dataset/
        ├── dataset.jsonl        # Dataset ฉบับสมบูรณ์ (1,910 ตัวอย่าง)
        └── dataset_v1_240.jsonl  # Dataset ฉบับเริ่มต้น (240 ตัวอย่าง)
```
---
📊 ผลการทดสอบประสิทธิภาพ (Evaluation Benchmark)
ทดสอบประเมินผลระบบด้วยชุดคำถามอัตโนมัติจำนวน 100 ข้อ ครอบคลุม 12 หมวดหมู่ เปรียบเทียบระหว่างโมเดล Fine-tuned (v4) เดี่ยว ๆ กับการใช้งานร่วมกับระบบ RAG:
หมวดหมู่การทดสอบ	จำนวนข้อ	Fine-tuned v4 (ไม่มี RAG)	RAG System (หลังปรับปรุง)
1. ค้นหารายวิชาจากรหัส 8 หลัก	15	0%	100%
2. ค้นหารหัสวิชาจากชื่อรายวิชา	10	0%	100%
3. ตรวจสอบจำนวนหน่วยกิตรายวิชา	10	0%	100%
4. วิชาบังคับก่อน (มี Prerequisites)	12	8%	100%
5. วิชาบังคับก่อน (ไม่มี Prerequisites)	8	88%	100%
6. รายวิชาตามแผนปกติรายเทอม	6	0%	100%
7. รายวิชาตามแผนสหกิจรายเทอม	6	0%	100%
8. ระดับชั้นปีและเทอมของวิชา	8	38%	100%
9. โครงสร้างและหมวดหมู่หลักสูตร	6	33%	100%
10. เปรียบเทียบแผนปกติ vs สหกิจ	8	0%	100%
11. ตรวจสอบรหัสวิชาที่ไม่มีในจริง	6	17%	100%
12. คำถามนอกขอบเขตหลักสูตร	5	100%	100%
คะแนนรวมทั้งหมด	100	19%	98%+
---
🚀 วิธีการติดตั้งและรันระบบ (Quick Start)
1. การเตรียมระบบ (Prerequisites)
ติดตั้ง Python 3.10+
ติดตั้ง Node.js (v18+) & npm
ติดตั้ง Ollama และดาวน์โหลด Base Model:
```bash
  ollama run typhoon-gemma3
  ```
2. การรัน Backend
```bash
cd my-app/backend

# ตั้งค่า Encoding สำหรับภาษาไทยบน Windows
set PYTHONUTF8=1       # สำหรับ Windows CMD
# export PYTHONUTF8=1     # สำหรับ Linux / macOS / Bash

python server.py       # เริ่มทำงานที่ Port 8000
```
3. การรัน Frontend
```bash
cd my-app/frontend
npm install            # ติดตั้ง Dependencies (ทำเฉพาะครั้งแรก)
npm start              # เริ่มทำงานที่ Port 3000
```
4. การรันชุดทดสอบความแม่นยำ (Evaluation Test)
```bash
cd my-app/training
set PYTHONUTF8=1
python eval_100.py rag   # ทดสอบโหมด RAG (ใช้เวลาประมาณ 25 นาที)
```
---
💡 ข้อค้นพบและบทเรียนสำคัญ (Key Insights)
Fine-Tuning สอนรูปแบบภาษา แต่ไม่ได้จำตัวเลขข้อเท็จจริง: โมเดล LLM ขนาดเล็ก (4B) แม้จะ Fine-tune ด้วย Dataset คุณภาพสูง (1,910 ตัวอย่าง) ก็ยังคงแต่งรหัสวิชา 8 หลัก หรือจำจำนวนหน่วยกิตผิดพลาด (Accuracy เพียง 19%)
RAG คือหัวใจสำคัญของความแม่นยำ: การดึงข้อมูลจริงจาก DB/JSON แล้วนำมาแนบเป็น Context ให้ LLM ทำหน้าที่เพียงเรียบเรียงภาษา ช่วยเพิ่มความแม่นยำขึ้นสูงถึง 98%+
Direct Answer สำหรับข้อมูลรายการยาว: การสอบถามรายวิชาทั้งเทอม LLM มักข้ามหรือตกหล่นบางวิชา การใช้สคริปต์ตอบตรงจากข้อมูลดิบโดยไม่ผ่าน LLM ช่วยให้ได้ข้อมูลที่ครบถ้วน 100%
Data Cleansing จาก PDF ภาษาไทย: ไฟล์ PDF ภาษาไทยมักมีปัญหาอักขระหายหรือเพี้ยน (เช่น ว ศ ษ ส ห) ต้องสร้างตาราง Decoded Mapping เพื่อแปลงข้อมูลให้ถูกต้องตั้งแต่ขั้นตอนการเตรียมข้อมูล
---
🔮 ข้อจำกัดและงานที่จะพัฒนาต่อ (Limitations & Future Work)
[ ] สุ่มตรวจทานข้อมูลกับ PDF ต้นฉบับ: สุ่มเทียบข้อมูลดิบกับเอกสารจริงด้วยตาเปล่าเพื่อย้อนเช็กความถูกต้องของการ Parse ข้อมูล
[ ] ขยายขอบเขตข้อมูล: เพิ่มข้อมูลเกี่ยวกับค่าธรรมเนียมการศึกษา รายนามอาจารย์ผู้สอน และตารางสอบ
[ ] Vector Search RAG: พัฒนาระบบ RAG จาก Keyword Match เป็น Vector Embedding Search เพื่อรองรับคำถามในรูปแบบสำนวนภาษาพูดที่หลากหลายยิ่งขึ้น
[ ] เตรียมพร้อมสำหรับ Production: ปิด Flask Debug Mode, กำหนด CORS Policy ให้รัดกุม และเพิ่มระบบ ยืนยันตัวตน (Authentication)
---
<p align="center">
  พัฒนาโดยทีมงาน <b>LIONBOT</b> | หลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ มก. ศรีราชา
</p>
