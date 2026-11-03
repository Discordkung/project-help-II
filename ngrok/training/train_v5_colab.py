# -*- coding: utf-8 -*-
"""LIONBOT v5 (CPT + SFT) สำหรับ Google Colab (T4)  สร้างอัตโนมัติจาก train_typhoon_lionbot_v5_cpt.ipynb

วิธีใช้: เปิด Colab ใหม่ ตั้ง Runtime = T4 GPU แล้ววางไฟล์นี้ทั้งไฟล์ลงใน cell เดียว กดรัน
  1) ตอนถึงขั้น Drive จะมีหน้าต่างขอสิทธิ์เข้าถึง Google Drive ให้กดอนุญาตเอง
  2) ตอนถึงขั้นอัปโหลด เลือกไฟล์ รวมหลักสูตร-วิศวกรรมไฟฟ้า.md และ dataset.jsonl (หรือวางไว้ใน Drive โฟลเดอร์ lionbot_v5_input)
  3) ถ้า unsloth ติดตั้งแล้ว import ไม่ผ่านหรือเวอร์ชันชน ให้ Runtime > Restart session แล้วรันใหม่ (ข้ามขั้นติดตั้งอัตโนมัติ)
"""
import subprocess, sys

def sh(cmd):
    print("$", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)


# ======================================================================
# LIONBOT v5 — Continued Pretraining (CPT) แล้วตามด้วย SFT
# ======================================================================

# ======================================================================
# 1. ติดตั้ง Unsloth + เช็ค GPU
# ======================================================================
try:
    import unsloth  # noqa: F401
    print("unsloth ติดตั้งแล้ว ข้ามขั้นติดตั้ง")
except Exception:
    sh("pip install -q unsloth")
    sh('pip install -q --force-reinstall --no-cache-dir "git+https://github.com/unslothai/unsloth.git"')

import torch
assert torch.cuda.is_available(), "ไม่มี GPU — ไปที่ Runtime > Change runtime type > T4 GPU ก่อน"
props = torch.cuda.get_device_properties(0)
print("GPU:", props.name, "| VRAM:", round(props.total_memory / 1e9, 1), "GB")
if props.total_memory < 14e9:
    print("คำเตือน: VRAM น้อยกว่า 14 GB อาจ Out of memory ตั้ง INCLUDE_EMBED = False ใน cell โหลดโมเดล")


# ======================================================================
# 2. เชื่อม Google Drive (ไว้เซฟ adapter/GGUF)
# ======================================================================
from google.colab import drive
drive.mount('/content/drive')


# ======================================================================
# 3. โหลดโมเดลฐาน + LoRA สำหรับ CPT
# ======================================================================
from unsloth import FastLanguageModel

BASE_MODEL = "scb10x/typhoon2.1-gemma3-4b"
MAX_SEQ_LENGTH = 3072

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
)

# สูตร CPT ของ Unsloth: ใส่ LoRA ที่ embed_tokens และ lm_head ด้วย (คำ/รหัสใหม่ต้องปรับ embedding)
# ถ้า Out of memory บน T4 ให้ตั้ง INCLUDE_EMBED = False แล้วรันใหม่ตั้งแต่ cell นี้
INCLUDE_EMBED = True
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
if INCLUDE_EMBED:
    TARGETS += ["embed_tokens", "lm_head"]

model = FastLanguageModel.get_peft_model(
    model,
    r=32,
    target_modules=TARGETS,
    lora_alpha=32,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
    use_rslora=True,
    loftq_config=None,
)
print("LoRA targets:", TARGETS)


# ======================================================================
# 4. อัปโหลด รวมหลักสูตร-วิศวกรรมไฟฟ้า.md + dataset.jsonl
# ======================================================================
import os, shutil

MD_FILE = "รวมหลักสูตร-วิศวกรรมไฟฟ้า.md"
SFT_FILE = "dataset.jsonl"

# ทางลัด: ถ้าวางไฟล์ทั้งสองไว้ใน Google Drive โฟลเดอร์นี้ จะดึงมาใช้เลย ไม่ต้องอัปโหลดซ้ำทุกครั้ง
DRIVE_INPUT_DIR = "/content/drive/MyDrive/lionbot_v5_input"

if all(os.path.exists(os.path.join(DRIVE_INPUT_DIR, f)) for f in (MD_FILE, SFT_FILE)):
    for f in (MD_FILE, SFT_FILE):
        shutil.copy(os.path.join(DRIVE_INPUT_DIR, f), f)
    print("ใช้ไฟล์จาก Drive:", DRIVE_INPUT_DIR)
else:
    from google.colab import files
    uploaded = files.upload()
    print(list(uploaded.keys()))
    # ชื่อไฟล์อาจมี " (1)" ต่อท้ายถ้าอัปโหลดซ้ำ — หาแล้วเปลี่ยนเป็นชื่อมาตรฐาน
    md_src = [k for k in uploaded if k.endswith(".md")]
    assert md_src, "ยังไม่ได้อัปโหลดไฟล์ รวมหลักสูตร-วิศวกรรมไฟฟ้า.md"
    if md_src[0] != MD_FILE:
        shutil.copy(md_src[0], MD_FILE)
    jsonl_src = [k for k in uploaded if k.endswith(".jsonl")]
    assert jsonl_src, "ยังไม่ได้อัปโหลด dataset.jsonl"
    if jsonl_src[0] != SFT_FILE:
        shutil.copy(jsonl_src[0], SFT_FILE)

assert os.path.getsize(MD_FILE) > 100_000, "ไฟล์ .md เล็กผิดปกติ (ควรประมาณ 170 KB)"
assert os.path.getsize(SFT_FILE) > 1_000_000, "ไฟล์ dataset.jsonl เล็กผิดปกติ (ควรประมาณ 2.3 MB)"
print("พร้อมใช้:", MD_FILE, "และ", SFT_FILE)


# ======================================================================
# 4.1 สร้างคลังข้อความ CPT จากไฟล์ .md
# ======================================================================
# -*- coding: utf-8 -*-
"""สร้างคลังข้อความสำหรับ continued pretraining (CPT) จาก รวมหลักสูตร-วิศวกรรมไฟฟ้า.md

ส่วนที่โมเดล v4 ยังไม่เคยเห็น (ตรวจเทียบกับ dataset/dataset.jsonl แล้ว):
  - วิชาในหมวดวิชาศึกษาทั่วไป ("วิชาเสรี" ตามที่ผู้ใช้เรียก) 196 วิชา  (ใน dataset มีแค่ 01999111)
  - เงื่อนไขเกรดของนิสิต (สหกิจ 2.50 / จบ 2.00 / เกียรตินิยม / พ้นสภาพ)
ส่วนที่โมเดลเคยเรียนผ่าน SFT แล้ว (คำอธิบายรายวิชา 93 วิชา) ใส่เป็น replay เล็กน้อยกันลืมของเดิม

CPT เรียนจากข้อความดิบ (ไม่ใช่คำถาม-คำตอบ) จึงเขียนข้อเท็จจริงเดียวกันหลายสำนวน ทั้งรหัส->ชื่อ และ ชื่อ->รหัส
ผลลัพธ์: dataset/cpt_corpus.jsonl (1 บรรทัด = {"text": ...}), dataset/cpt_gened.json (ข้อมูลที่ parse ได้ ใช้ตรวจ/ทำชุดวัดผล)
รัน: PYTHONUTF8=1 python build_cpt_corpus.py
"""
import io
import json
import os
import random
import re

HERE = '.'
MD = 'รวมหลักสูตร-วิศวกรรมไฟฟ้า.md'
OUT_DIR = '.'
random.seed(3407)

md = io.open(MD, encoding='utf-8').read()
assert '�' not in md, 'ไฟล์รวมยังมีตัวอักษรเสีย'

i4, i5 = md.index('# ส่วนที่ 4'), md.index('# ส่วนที่ 5')
part4, part5 = md[i4:i5], md[i5:]
cond = md[md.index('# เงื่อนไขเพิ่มเติมสำหรับนิสิต'):md.index('# ส่วนที่ 1')]

# ---------- parse หมวดวิชาศึกษาทั่วไป ----------
GROUP_NAME = {
    '1': 'อยู่ดีมีสุข', '2': 'ศาสตร์แห่งผู้ประกอบการ', '3': 'พลเมืองไทยและพลเมืองโลก',
    '4': 'ภาษากับการสื่อสาร', '5': 'สุนทรียศาสตร์',
}
GROUP_RULE = {
    '1': 'ต้องเรียนกิจกรรมพลศึกษา 1 หน่วยกิต และเลือกเรียนวิชาอื่นๆ ในกลุ่มสาระอีกไม่น้อยกว่า 2 หน่วยกิต',
    '2': 'ต้องเลือกเรียนไม่น้อยกว่า 3 หน่วยกิตตามคู่มือ (หลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ ปรับปรุง 2565 กำหนดเลือก 6 หน่วยกิต)',
    '3': 'ต้องเรียนวิชาศาสตร์แห่งแผ่นดิน 2 หน่วยกิต และเลือกเรียนวิชาอื่นๆ ในกลุ่มสาระเพิ่มเติม (หลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ ปรับปรุง 2565 กำหนดเลือกอีก 3 หน่วยกิต)',
    '4': 'ต้องเรียนรวม 13 หน่วยกิต ได้แก่ ภาษาไทย 3 หน่วยกิต ภาษาต่างประเทศ 1 ภาษา 9 หน่วยกิต และสารสนเทศหรือคอมพิวเตอร์ 1 หน่วยกิต',
    '5': 'ต้องเลือกเรียนไม่น้อยกว่า 3 หน่วยกิต',
}

courses = []   # dict(code,name,credit,total,lec,lab,self,group,sub,note)
group = sub = None
for line in part5.splitlines():
    m = re.match(r'^## (\d)\. กลุ่มสาระ(.+?) \(', line)
    if m:
        group, sub = m.group(1), None
        continue
    m = re.match(r'^### ([\d.]+) (.+)$', line)
    if m:
        sub = re.sub(r'\s*\(.*?\)\s*$', '', m.group(2)).strip()
        continue
    m = re.match(r'^\|\s*(\d{8})\s*\|\s*(.+?)\s*\|\s*(\d+)\((\d+)-(\d+)-(\d+)\)\s*\|$', line)
    if m and group:
        code, name, tot, lec, lab, selfs = m.groups()
        notes = re.findall(r'\(((?:เปิดเฉพาะ|รหัสเดิม|ชื่อเดิม)[^)]*)\)', name)
        name = re.sub(r'\s*\((?:เปิดเฉพาะ|รหัสเดิม|ชื่อเดิม)[^)]*\)', '', name).strip()
        courses.append(dict(code=code, name=name, credit=f"{tot}({lec}-{lab}-{selfs})", total=int(tot), lec=int(lec),
                            lab=int(lab), self=int(selfs), group=group, sub=sub, note='; '.join(notes)))

assert len(courses) == 196, len(courses)
assert len({c['code'] for c in courses}) == 196
by_group = {}
for c in courses:
    by_group.setdefault(c['group'], []).append(c)

SUB_FALLBACK = {'1': 'อยู่ดีมีสุข', '2': 'ศาสตร์แห่งผู้ประกอบการ', '3': 'พลเมืองไทยและพลเมืองโลก', '4': 'ภาษากับการสื่อสาร', '5': 'สุนทรียศาสตร์'}
CAMPUS = {'01': 'บางเขนและวิทยาเขตทั่วไป', '02': 'วิทยาเขตกำแพงแสน', '03': 'วิทยาเขตศรีราชา', '04': 'วิทยาเขตเฉลิมพระเกียรติ จังหวัดสกลนคร'}

docs = []   # (kind, text)


def add(kind, text):
    docs.append((kind, text.strip()))


# ---------- A) นิยามและภาพรวม ----------
add('intro', (
    "หมวดวิชาศึกษาทั่วไป (Gen Ed) ของมหาวิทยาลัยเกษตรศาสตร์ ฉบับปรับปรุง พ.ศ. 2559 แบ่งเป็น 5 กลุ่มสาระ ได้แก่ "
    "อยู่ดีมีสุข ศาสตร์แห่งผู้ประกอบการ พลเมืองไทยและพลเมืองโลก ภาษากับการสื่อสาร และสุนทรียศาสตร์ "
    "รวมทั้งหมด 195 รายวิชาตามตารางสรุปในคู่มือ (รายการที่พิมพ์ในคู่มือจริงนับได้ 196 วิชา ต่างจากตารางสรุปหนึ่งวิชาในกลุ่มพลเมืองไทยและพลเมืองโลก) "
    "นิสิตหลักสูตรวิศวกรรมศาสตรบัณฑิต สาขาวิชาวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ ปรับปรุง พ.ศ. 2565 ต้องเรียนหมวดวิชาศึกษาทั่วไปไม่น้อยกว่า 30 หน่วยกิต"))
add('intro', (
    "ในเอกสารชุดนี้ \"วิชาเสรี\" หมายถึงวิชาในหมวดวิชาศึกษาทั่วไป (Gen Ed) ซึ่งนิสิตเลือกเรียนเองตามกลุ่มสาระที่หลักสูตรกำหนด "
    "ไม่ใช่ \"หมวดวิชาเลือกเสรี\" 6 หน่วยกิตในโครงสร้างหลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ ซึ่งเป็นหมวดแยกต่างหาก"))
add('intro', (
    "จำนวนรายวิชาในแต่ละกลุ่มสาระของหมวดวิชาศึกษาทั่วไป ตามตารางสรุปของคู่มือ: อยู่ดีมีสุข 72 วิชา (กิจกรรมพลศึกษา 47 วิชา และวิชาอื่นๆ 25 วิชา), "
    "ศาสตร์แห่งผู้ประกอบการ 14 วิชา, พลเมืองไทยและพลเมืองโลก 19 วิชา, ภาษากับการสื่อสาร 75 วิชา (ภาษาไทย 6 วิชา ภาษาต่างประเทศ 61 วิชา สารสนเทศหรือคอมพิวเตอร์ 8 วิชา), "
    "สุนทรียศาสตร์ 15 วิชา รวม 195 วิชา"))
add('intro', (
    "รหัสวิชาที่ขึ้นต้นด้วย 03 เป็นวิชาของวิทยาเขตศรีราชา, 02 เป็นของวิทยาเขตกำแพงแสน, 04 เป็นของวิทยาเขตเฉลิมพระเกียรติ จังหวัดสกลนคร "
    "ส่วนรหัสขึ้นต้นด้วย 01 เป็นวิชาที่เปิดสอนทั่วไป ควรตรวจสอบว่าวิทยาเขตของตนเปิดสอนก่อนลงทะเบียน"))

# ---------- B) รายการวิชาแยกกลุ่ม/กลุ่มย่อย ----------
for g in sorted(by_group):
    subs = []
    for c in by_group[g]:
        s = c['sub'] or SUB_FALLBACK[g]
        if s not in subs:
            subs.append(s)
    for s in subs:
        items = [c for c in by_group[g] if (c['sub'] or SUB_FALLBACK[g]) == s]
        lines = "\n".join(f"- {c['code']} {c['name']} {c['credit']} หน่วยกิต" for c in items)
        add('group', (
            f"หมวดวิชาศึกษาทั่วไป กลุ่มสาระ{GROUP_NAME[g]} หัวข้อ {s} {GROUP_RULE[g]} "
            f"หัวข้อนี้มี {len(items)} รายวิชา ได้แก่\n{lines}"))

# ---------- C) รายวิชาทีละวิชา (สองสำนวน: รหัส->ชื่อ และ ชื่อ->รหัส) ----------
for c in courses:
    s = c['sub'] or SUB_FALLBACK[c['group']]
    extra = f" หมายเหตุ: {c['note']}" if c['note'] else ''
    campus = CAMPUS.get(c['code'][:2], '')
    add('course', (
        f"วิชา {c['code']} {c['name']} เป็นวิชาในหมวดวิชาศึกษาทั่วไป กลุ่มสาระ{GROUP_NAME[c['group']]} ({s}) "
        f"มี {c['total']} หน่วยกิต หน่วยกิตแบบ {c['credit']} คือบรรยาย {c['lec']} ปฏิบัติ {c['lab']} ศึกษาด้วยตนเอง {c['self']} ชั่วโมงต่อสัปดาห์.{extra}"))
    add('course', (
        f"ถามว่า {c['name']} รหัสอะไร: รหัสวิชา {c['name']} คือ {c['code']} เรียนได้ {c['total']} หน่วยกิต "
        f"นับเป็นวิชาเสรี (วิชาศึกษาทั่วไป) กลุ่มสาระ{GROUP_NAME[c['group']]}. "
        f"ถามว่ารหัส {c['code']} คือวิชาอะไร: คือ {c['name']}."))

# ---------- D) เงื่อนไขเกรดของนิสิต ----------
for k in ('2.50', '2.00', '3.50', '3.25', '3.49', '1.50', '1.75'):
    assert k in cond, k
add('rules', (
    "เงื่อนไขเกรดของนิสิตวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์: การเรียนแผนสหกิจศึกษา ต้องมีเกรดเฉลี่ยสะสมไม่ต่ำกว่า 2.50 ภายในปี 4 เทอม 1 "
    "และต้องเรียนรายวิชาตามแผนหลักสูตรให้ครบภายในปี 4 เทอม 1 จึงจะไปปฏิบัติงานสหกิจศึกษาได้ในปี 4 เทอม 2"))
add('rules', (
    "การยื่นจบการศึกษา ต้องมีเกรดเฉลี่ยสะสมไม่ต่ำกว่า 2.00. เกียรตินิยมอันดับ 1 ต้องมีเกรดเฉลี่ยไม่ต่ำกว่า 3.50. "
    "เกียรตินิยมอันดับ 2 ต้องมีเกรดเฉลี่ยไม่ต่ำกว่า 3.25 และไม่เกิน 3.49"))
add('rules', (
    "การพ้นสภาพนิสิต: ถ้าเกรดเฉลี่ยรวมต่ำกว่า 1.50 ถือว่าพ้นสภาพนิสิตทันที และถ้าเกรดเฉลี่ยรวมต่ำกว่า 1.75 ภายใน 2 เทอมการศึกษา ถือว่าพ้นสภาพนิสิต"))
add('rules', (
    "สรุปเกณฑ์เกรดเฉลี่ยของนิสิต: สหกิจศึกษา 2.50 (ภายในปี 4 เทอม 1), ยื่นจบ 2.00, เกียรตินิยมอันดับ 1 ตั้งแต่ 3.50, เกียรตินิยมอันดับ 2 ตั้งแต่ 3.25 ถึง 3.49, "
    "พ้นสภาพทันทีเมื่อต่ำกว่า 1.50, ต่ำกว่า 1.75 ภายใน 2 เทอมการศึกษาพ้นสภาพ. เกณฑ์เหล่านี้เป็นข้อกำหนดที่นิสิตระบุไว้ ไม่ได้มาจากเอกสารหลักสูตร "
    "ควรยืนยันกับประกาศของคณะหรือมหาวิทยาลัยอีกครั้ง. เกณฑ์แต้มรายวิชา: A=4, B+=3.5, B=3, C+=2.5, C=2, D+=1.5, D=1, F=0"))

# ---------- E) replay: คำอธิบายรายวิชา (โมเดลเรียนผ่าน SFT แล้ว ใส่เล็กน้อยกันลืม) ----------
replay = []
for blk in re.split(r'(?m)^### (?=\d{8})', part4)[1:]:
    head, _, body = blk.partition('\n')
    body = re.sub(r'\s+', ' ', body.replace('*', '')).strip()
    if body:
        replay.append(f"รายวิชา {head.strip()} {body}")
random.shuffle(replay)
for t in replay:
    add('replay', t)

# ---------- F) ชุดคำถาม-คำตอบเล็กๆ สำหรับรอบ SFT หลัง CPT ----------
# ถ้า SFT ต่อด้วย dataset.jsonl อย่างเดียว (ไม่มีเรื่องวิชาศึกษาทั่วไปเลย) ความรู้ที่ CPT ฉีดไว้อาจถูกทับ จึงผสมคำถามสั้นๆ เรื่องใหม่เข้าไปด้วย
SYSTEM = ("คุณคือ \"LIONBOT\" ผู้ช่วยอัจฉริยะด้านหลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์\n"
          "- บุคลิก: สุภาพ, เป็นมืออาชีพ, กระตือรือร้น\n"
          "- ตอบคำถามอย่างแม่นยำและกระชับ โดยอิงข้อมูลหลักสูตรจริงเท่านั้น")
mix = []


def qa(q, a):
    mix.append({'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': q}, {'role': 'assistant', 'content': a}]})


for c in courses:
    g = GROUP_NAME[c['group']]
    qa(random.choice([f"รหัสวิชา {c['code']} คือวิชาอะไร", f"{c['code']} คือวิชาอะไร"]),
       f"{c['code']} คือวิชา{c['name']} เป็นวิชาในหมวดวิชาศึกษาทั่วไป กลุ่มสาระ{g} มี {c['total']} หน่วยกิต ({c['credit']})")
    qa(random.choice([f"วิชา{c['name']} รหัสอะไร", f"{c['name']} รหัสวิชาอะไร"]),
       f"วิชา{c['name']} รหัส {c['code']} มี {c['total']} หน่วยกิต อยู่ในหมวดวิชาศึกษาทั่วไป กลุ่มสาระ{g}")
qa("แผนสหกิจต้องมีเกรดเฉลี่ยสะสมไม่ต่ำกว่าเท่าไร", "ต้องมีเกรดเฉลี่ยสะสมไม่ต่ำกว่า 2.50 ภายในปี 4 เทอม 1 และต้องเรียนครบตามแผนภายในเทอมนั้น")
qa("ยื่นจบการศึกษาต้องมีเกรดเฉลี่ยไม่ต่ำกว่าเท่าไร", "ต้องมีเกรดเฉลี่ยไม่ต่ำกว่า 2.00")
qa("เกียรตินิยมอันดับ 1 ต้องมีเกรดเฉลี่ยเท่าไร", "ต้องมีเกรดเฉลี่ยไม่ต่ำกว่า 3.50")
qa("เกียรตินิยมอันดับ 2 ต้องมีเกรดเฉลี่ยเท่าไร", "ต้องมีเกรดเฉลี่ยตั้งแต่ 3.25 และไม่เกิน 3.49")
qa("เกรดเฉลี่ยรวมต่ำกว่าเท่าไรพ้นสภาพนิสิตทันที", "ต่ำกว่า 1.50 ถือว่าพ้นสภาพนิสิตทันที")
qa("เกรดเฉลี่ยต่ำกว่า 1.75 ภายใน 2 เทอมเป็นอย่างไร", "ถ้าเกรดเฉลี่ยรวมต่ำกว่า 1.75 ภายใน 2 เทอมการศึกษา ถือว่าพ้นสภาพนิสิต")
qa("วิชาเสรีหมายถึงอะไร", "ในที่นี้ วิชาเสรีหมายถึงวิชาในหมวดวิชาศึกษาทั่วไป (Gen Ed) ซึ่งนิสิตเลือกเรียนเองตามกลุ่มสาระ ไม่ใช่หมวดวิชาเลือกเสรี 6 หน่วยกิต")
qa("หมวดวิชาศึกษาทั่วไปแบ่งเป็นกี่กลุ่มสาระ อะไรบ้าง", "แบ่งเป็น 5 กลุ่มสาระ ได้แก่ อยู่ดีมีสุข ศาสตร์แห่งผู้ประกอบการ พลเมืองไทยและพลเมืองโลก ภาษากับการสื่อสาร และสุนทรียศาสตร์")
random.shuffle(mix)

# ---------- เขียนไฟล์ ----------
os.makedirs(OUT_DIR, exist_ok=True)
with io.open(os.path.join(OUT_DIR, 'cpt_sft_mix.jsonl'), 'w', encoding='utf-8') as f:
    for r in mix:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print('sft mix examples', len(mix))
with io.open(os.path.join(OUT_DIR, 'cpt_corpus.jsonl'), 'w', encoding='utf-8') as f:
    for kind, t in docs:
        assert '�' not in t
        f.write(json.dumps({'text': t, 'kind': kind}, ensure_ascii=False) + '\n')
with io.open(os.path.join(OUT_DIR, 'cpt_gened.json'), 'w', encoding='utf-8') as f:
    json.dump(courses, f, ensure_ascii=False, indent=1)

kinds = {}
for k, t in docs:
    kinds.setdefault(k, [0, 0])
    kinds[k][0] += 1
    kinds[k][1] += len(t)
print('docs', len(docs), 'chars', sum(len(t) for _, t in docs), '(~tokens', sum(len(t) for _, t in docs) // 2, ')')
for k, (n, ch) in kinds.items():
    print(f'  {k:7s} docs={n:4d} chars={ch}')
print('gen-ed courses', len(courses), {g: len(v) for g, v in sorted(by_group.items())})


# ======================================================================
# 5. เตรียมข้อมูล CPT (ข้อความดิบ + EOS)
# ======================================================================
from datasets import load_dataset, concatenate_datasets

cpt = load_dataset("json", data_files="cpt_corpus.jsonl", split="train")
EOS = tokenizer.eos_token
cpt = cpt.map(lambda e: {"text": e["text"] + EOS})

# ข้อมูลใหม่ (intro/group/course/rules) ซ้ำ 2 เท่า เพราะรหัส/ตัวเลขต้องเห็นหลายรอบ, replay (คำอธิบายรายวิชาเดิม) 1 เท่า
new = cpt.filter(lambda e: e["kind"] != "replay")
rep = cpt.filter(lambda e: e["kind"] == "replay")
cpt = concatenate_datasets([new, new, rep]).shuffle(seed=3407).remove_columns(["kind"])

lens = [len(tokenizer(t)["input_ids"]) for t in cpt["text"]]
print("เอกสาร:", len(cpt), "| โทเคนรวม:", sum(lens), "| ยาวสุด:", max(lens))
assert max(lens) < MAX_SEQ_LENGTH, "มีเอกสารยาวเกิน MAX_SEQ_LENGTH"
print(cpt[0]["text"][:300])


# ======================================================================
# 6. ขั้นที่ 1: Continued Pretraining
# ======================================================================
from unsloth import UnslothTrainer, UnslothTrainingArguments, is_bfloat16_supported

trainer = UnslothTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=cpt,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_num_proc=2,
    args=UnslothTrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_ratio=0.1,
        num_train_epochs=3,
        learning_rate=1e-4,
        embedding_learning_rate=1e-5,   # embedding ใช้ LR ต่ำกว่า 5-10 เท่า (คำแนะนำของ Unsloth)
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.0,
        lr_scheduler_type="cosine",
        seed=3407,
        output_dir="outputs_cpt",
        report_to="none",
    ),
)
cpt_stats = trainer.train()
print(cpt_stats.metrics)

# เซฟจุดตรวจหลัง CPT ไว้ก่อน (ถ้าขั้น SFT พัง ไม่ต้องเริ่ม CPT ใหม่)
import shutil
model.save_pretrained("typhoon-lionbot-v5-cpt-adapter")
tokenizer.save_pretrained("typhoon-lionbot-v5-cpt-adapter")
shutil.copytree("typhoon-lionbot-v5-cpt-adapter", "/content/drive/MyDrive/typhoon-lionbot-v5-cpt-adapter", dirs_exist_ok=True)
print("เซฟ adapter หลัง CPT ไว้ที่ Drive แล้ว")


# ======================================================================
# 7. ขั้นที่ 2: SFT สอนรูปแบบแชตกลับ (ใช้ dataset เดิมของ v4 + คำถามสั้นเรื่องข้อมูลใหม่)
# ======================================================================
USE_MIX = True   # ผสมคำถามสั้นเรื่องวิชาศึกษาทั่วไป/เกณฑ์เกรด กันความรู้จาก CPT ถูก SFT ทับ

sft = load_dataset("json", data_files="dataset.jsonl", split="train")
if USE_MIX:
    mix = load_dataset("json", data_files="cpt_sft_mix.jsonl", split="train")
    sft = concatenate_datasets([sft, mix]).shuffle(seed=3407)
print("ตัวอย่าง SFT:", len(sft))

def format_chat(example):
    return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)}

sft = sft.map(format_chat)
slens = [len(tokenizer(t)["input_ids"]) for t in sft["text"]]
print("max tokens", max(slens), "mean", sum(slens) / len(slens))

from trl import SFTTrainer, SFTConfig

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=sft,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    args=SFTConfig(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=1e-4,   # ต่ำกว่า v4 (2e-4) เพราะ LoRA ชุดนี้ผ่าน CPT มาแล้ว ลดการทับความรู้เดิม
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        output_dir="outputs_sft",
        report_to="none",
    ),
)
sft_stats = trainer.train()


# ======================================================================
# 8. เซฟ adapter ลง Drive
# ======================================================================
ADAPTER_OUT = "typhoon-lionbot-v5-adapter"
model.save_pretrained(ADAPTER_OUT)
tokenizer.save_pretrained(ADAPTER_OUT)

import shutil
DRIVE_ADAPTER_DEST = f"/content/drive/MyDrive/{ADAPTER_OUT}"
shutil.copytree(ADAPTER_OUT, DRIVE_ADAPTER_DEST, dirs_exist_ok=True)
print(f"เซฟ adapter ไว้ที่ {DRIVE_ADAPTER_DEST} แล้ว")


# ======================================================================
# 9. แปลงเป็น GGUF (q4_k_m) สำหรับ Ollama
# ======================================================================
GGUF_NAME = "typhoon-lionbot-v5-gguf"
model.save_pretrained_gguf(GGUF_NAME, tokenizer, quantization_method="q4_k_m")

# path ที่ Unsloth สร้างจริงบางทีต่างจากชื่อโฟลเดอร์ที่ตั้งไว้ — ค้นด้วย glob กันพลาด
import glob, shutil, os

gguf_files = glob.glob("**/*.gguf", recursive=True)
gguf_q4 = [f for f in gguf_files if "q4_k_m" in f.lower()]
gguf_files = gguf_q4 or gguf_files
print("เจอไฟล์ GGUF:", gguf_files)
assert gguf_files, "ไม่เจอไฟล์ .gguf — เช็ค cell ก่อนหน้าว่า export สำเร็จหรือไม่"

SRC_GGUF = gguf_files[0]
DRIVE_GGUF_DIR = "/content/drive/MyDrive/typhoon-lionbot-v5-gguf"
os.makedirs(DRIVE_GGUF_DIR, exist_ok=True)
DEST_GGUF = os.path.join(DRIVE_GGUF_DIR, "typhoon-lionbot-v5.Q4_K_M.gguf")
shutil.copy(SRC_GGUF, DEST_GGUF)
print(f"คัดลอกไปที่ {DEST_GGUF} แล้ว")


# ======================================================================
# 10. หลังดาวน์โหลด GGUF (ทำบนเครื่องตัวเอง)
# ======================================================================