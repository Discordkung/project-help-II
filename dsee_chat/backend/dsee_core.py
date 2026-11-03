# -*- coding: utf-8 -*-
"""
สมองของแชท DSEE — ตัดสินใจว่าคำถามแต่ละข้อควรตอบด้วยวิธีไหน

  1. rule        : ตอบจากข้อมูลหลักสูตรโดยตรง (แผนการเรียนรายเทอม, หน่วยกิต, วิชาที่ต้องเรียนก่อน,
                   ช่วงที่เรียน, คำอธิบายรายวิชา, รหัสวิชาที่ไม่มีจริง) → ถูกต้อง 100% และเร็ว
  2. curriculum  : คำถามหลักสูตรแบบอื่น → ค้นข้อมูลที่เกี่ยวข้องแล้วให้โมเดล dsee-typhoon ตอบ
  3. general     : เรื่องนอกหลักสูตร / โค้ด / ไฟล์ที่อัปโหลด → โมเดล Typhoon ทั่วไปตอบแบบเป็นกันเอง
"""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = json.load(open(os.path.join(HERE, "rag_index.json"), encoding="utf-8"))
COURSES = INDEX["courses"]
BY_CODE = {d["code"]: d for d in COURSES}


# ------------------------------------------------------------------ ค้นข้อมูล (RAG)
def _norm(s):
    return re.sub(r"\s+", "", str(s).lower())


def _bigrams(s):
    s = _norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def sem_from_question(q):
    """ดึง (ปี, เทอม) จากคำถาม เช่น 'ปี 2 เทอม 1', 'ปี3ภาคปลาย', 'year 2 semester 1'"""
    n = _norm(q)
    y = re.search(r"(?:ปี(?:ที่)?|year)(\d)", n)
    if not y:
        return []
    y = int(y.group(1))
    s = re.search(r"(?:เทอม|ภาค(?:การศึกษา)?(?:ที่)?|semester)(\d)", n)
    if s:
        return [(y, int(s.group(1)))]
    if "ภาคต้น" in n or "เทอมต้น" in n:
        return [(y, 1)]
    if "ภาคปลาย" in n or "เทอมปลาย" in n:
        return [(y, 2)]
    return [(y, 1), (y, 2)]


def _course_scores(q):
    nq, qb = _norm(q), _bigrams(q)
    out = []
    for d in COURSES:
        sc = 0.0
        if d["code"] in nq:
            sc += 100
        th, en = _norm(d["name_th"]), _norm(d["name_en"])
        if th and th in nq:
            sc += 50 + len(th) / 10
        if en and en in nq:
            sc += 50
        nb = _bigrams(d["name_th"])
        if nb:
            sc += 30 * len(nb & qb) / len(nb)
        out.append((sc, d))
    out.sort(key=lambda x: -x[0])
    return out


def retrieve(q, k_courses=5, k_overview=2):
    qb = _bigrams(q)
    cards = [d["text"] for s, d in _course_scores(q)[:k_courses] if s >= 12]
    sems = [INDEX["semesters"][f"{y}-{s}"] for (y, s) in sem_from_question(q) if f"{y}-{s}" in INDEX["semesters"]]
    core = INDEX["overview"][:2]
    rest = sorted(INDEX["overview"][2:], key=lambda t: -len(_bigrams(t) & qb) / (len(_bigrams(t)) ** 0.5))
    return cards + sems + core + rest[:k_overview]


def curriculum_system_prompt(q):
    # รูปแบบเดียวกับตอนเทรนโมเดล dsee-typhoon ทุกตัวอักษร (อย่าแก้ ไม่อย่างนั้นความแม่นจะลดลง)
    return INDEX["system_prompt"] + "\n\n[ข้อมูลอ้างอิงบางส่วน]\n" + "\n".join(retrieve(q))


# ------------------------------------------------------------------ แยกข้อมูลในบัตรรายวิชา
def parse_card(d):
    parts = d["text"].lstrip("- ").split(" | ")
    m = re.search(r"หน่วยกิต (\S+)$", parts[0])
    return {
        "credit": m.group(1) if m else "",
        "group": parts[1] if len(parts) > 1 else "",
        "when": parts[2] if len(parts) > 2 else "",
        "prereq": parts[3] if len(parts) > 3 else "",
        "desc": parts[4].replace("คำอธิบาย: ", "", 1) if len(parts) > 4 else "",
    }


# วิชาต่อเนื่อง I -> II (คำอธิบายรายวิชาไม่ได้บังคับ แต่แผนการเรียนเรียงไว้ต่อกัน)
SEQUEL_OF = {}
for _d in COURSES:
    if _d["name_th"].endswith(" II"):
        _base = _d["name_th"][:-3] + " I"
        for _o in COURSES:
            if _o["name_th"] == _base:
                SEQUEL_OF[_d["code"]] = _o


def mentioned_courses(q):
    """วิชาที่ถูกเอ่ยถึงชัดๆ (ด้วยรหัส หรือชื่อเต็มไทย/อังกฤษ)"""
    nq = _norm(q)
    codes_in_q = set(re.findall(r"\b0\d{7}\b", q))
    found = {}
    for d in COURSES:
        th, en = _norm(d["name_th"]), _norm(d["name_en"])
        if d["code"] in codes_in_q or (th and th in nq) or (len(en) > 6 and en in nq):
            found[d["code"]] = d
    result = []
    for c, d in found.items():
        if c in codes_in_q:
            result.append(d)
            continue
        th, en = _norm(d["name_th"]), _norm(d["name_en"])
        shadowed = any(
            o is not d and o["code"] not in codes_in_q and (
                (th in _norm(o["name_th"]) and th != _norm(o["name_th"])) or
                (en in _norm(o["name_en"]) and en != _norm(o["name_en"])))
            for o in found.values())
        if not shadowed:
            result.append(d)
    return result


# ------------------------------------------------------------------ คำตอบแบบกำหนดตายตัว (แม่นยำ 100%)
PREREQ_KW = ["ก่อน", "prerequisite", "prereq", "ต้องผ่าน", "เรียนต่อจาก", "ต่อจากวิชา", "พร้อมกัน", "หลังวิชา", "เรียนหลัง"]
CREDIT_KW = ["หน่วยกิต", "เครดิต", "credit", "ชั่วโมง"]
WHEN_KW = ["ปีไหน", "เทอมไหน", "ตอนไหน", "ปีอะไร", "ปีกี่", "ภาคไหน", "ลงได้ตอน", "เรียนตอน", "when"]
DESC_KW = ["คืออะไร", "เกี่ยวกับอะไร", "เรียนเกี่ยวกับ", "สอนอะไร", "เนื้อหา", "อธิบาย", "เรียนอะไร", "about", "what is"]
YESNO_KW = ["ใช่ไหม", "ใช่มั้ย", "ใช่หรือไม่", "ใช่ป่ะ", "ใช่รึเปล่า", "ใช่หรือเปล่า"]
COMPARE_KW = ["แตกต่าง", "เปรียบเทียบ", "ต่างกันอย่างไร", "ต่างกันยังไง"]
SEM_WORDS = re.compile(r"(เทอม|ภาค)\s*(ที่)?\s*\d|ภาคต้น|ภาคปลาย|เทอมต้น|เทอมปลาย")

OPENERS = ["ได้เลย! ", "โอเคเลย~ ", "จัดให้ครับ ", "มาดูกันครับ 👇 ", ""]


def _hours(credit):
    m = re.match(r"(\d+)\((\d+)-(\d+)-(\d+)\)", credit)
    if not m:
        return ""
    n, a, b, s = m.groups()
    return f" (บรรยาย {a} ชม. / ปฏิบัติ {b} ชม. / ศึกษาด้วยตนเอง {s} ชม. ต่อสัปดาห์)"


def _format_semester(y, s):
    text = INDEX["semesters"].get(f"{y}-{s}")
    if not text:
        return None
    head, body = text.lstrip("- ").split(": ", 1)
    items, total = body.rsplit(" — ", 1)
    lines = [f"📅 **แผนการเรียน{head}**"] + [f"• {x.strip()}" for x in items.split("; ")] + [f"**{total}**"]
    return "\n".join(lines)


def _course_rule(d, q, inherited=False):
    nq = _norm(q)
    if any(k in nq for k in COMPARE_KW):
        return None  # คำถามเปรียบเทียบ/แตกต่าง -> ให้โมเดลตอบแบบเปิดกว้าง ไม่ใช่การ์ดวิชาเดียว
    if d["code"].startswith("03610") and "รหัส" in nq and any(k in nq for k in ["ความหมาย", "หมายถึง", "หลัก", "แปล"]):
        return random.choice(OPENERS) + _decode_code(d)
    info = parse_card(d)
    want_pre = any(k in nq for k in PREREQ_KW)
    want_credit = any(k in nq for k in CREDIT_KW)
    want_when = any(k in nq for k in WHEN_KW)
    desc_kw = [k for k in DESC_KW if not (want_pre and k == "เรียนอะไร")]  # "ต้องเรียนอะไรก่อน" = ถามวิชาที่ต้องเรียนก่อน
    want_desc = any(k in nq for k in desc_kw)
    only_name = (not inherited) and len(_norm(q)) <= len(_norm(d["name_th"])) + 12  # พิมพ์มาแค่ชื่อ/รหัสวิชา
    if not (want_pre or want_credit or want_when or want_desc or only_name):
        return None

    title = f"**{d['code']} {d['name_th']}** ({d['name_en']})"
    out = []
    if want_pre:
        p = info["prereq"]
        if p.startswith("ไม่มี"):
            line = "✅ วิชาที่ต้องเรียนมาก่อน: **ไม่มี** ลงเรียนได้ตามแผนเลย"
            seq = SEQUEL_OF.get(d["code"])
            if seq:
                line += (f"\n   แต่วิชานี้เป็นภาคต่อของ **{seq['code']} {seq['name_th']}** "
                         f"({parse_card(seq)['when']}) เลยแนะนำให้เรียนตัวนั้นก่อนนะ")
            out.append(line)
        else:
            pre = p.replace("วิชาที่ต้องเรียนมาก่อนคือ ", "")
            line = f"📌 วิชาที่ต้องเรียนมาก่อน: **{pre}**"
            codes = re.findall(r"\b0\d{7}\b", pre)
            if len(codes) == 1 and codes[0] in BY_CODE:
                pc = BY_CODE[codes[0]]
                line += f" — {pc['name_th']} ({parse_card(pc)['when']})"
            out.append(line)
    if want_credit:
        n = info["credit"].split("(")[0]
        out.append(f"🎯 หน่วยกิต: **{n} หน่วยกิต** [{info['credit']}]{_hours(info['credit'])}")
    if want_when:
        out.append(f"🗓️ ช่วงที่เรียน: {info['when']}")
    if want_desc or (only_name and not out):
        if info["desc"] and not info["desc"].startswith("เอกสารคำอธิบาย"):
            out.append(f"📖 เรียนเกี่ยวกับ: {info['desc']}")
        else:
            out.append("📖 เอกสารคำอธิบายรายวิชาที่มีไม่ได้ระบุเนื้อหาของวิชานี้ ลองถามฝ่ายวิชาการของคณะดูนะ")
        if only_name and not (want_pre or want_credit or want_when):
            out.append(f"🎯 หน่วยกิต: {info['credit']} · 🗓️ {info['when']}")
            out.append(f"📌 {info['prereq']}")
    return random.choice(OPENERS) + title + "\n" + "\n".join(out)


# ------------------------------------------------------------------ คำนวณเกรดเฉลี่ย (GPA)
GRADE_POINTS = {"A": 4.0, "B+": 3.5, "B": 3.0, "C+": 2.5, "C": 2.0, "D+": 1.5, "D": 1.0, "F": 0.0}
GPA_TRIGGER = ["คำนวณเกรด", "คำนวณจีพีเอ", "คิดเกรด", "gpa", "gpax"]  # ไม่ใส่ "เกรดเฉลี่ย" เดี่ยวๆ เพราะชนกับคำถามเรื่องเกณฑ์พ้นสภาพ ฯลฯ
# หมายเหตุ: ใช้ (?![A-Za-z]) แทน \b ท้าย group เพราะ \b ใช้ไม่ได้หลัง "+" (ไม่ใช่ word char) ทำให้ "B+" ตัดเหลือแค่ "B"
_GPA_PAIR_RE = re.compile(r"(0\d{7})\s*[:\-–—]?\s*(A|B\+|B|C\+|C|D\+|D|F)(?![A-Za-z])", re.IGNORECASE)
_GPA_EXAMPLE = ("พิมพ์รูปแบบนี้มาได้เลยครับ (รหัสวิชาคู่กับเกรดที่ได้ จะกี่วิชาก็ได้ "
                "คั่นด้วยคอมมาหรือขึ้นบรรทัดใหม่):\n\n**คำนวณเกรด: 03610111 A, 03610211 B+, 03601214 C**")
_GRADE_TABLE = "**ตารางแต้มเกรด (ระบบ 8 ระดับ)**\nA = 4.0 · B+ = 3.5 · B = 3.0 · C+ = 2.5 · C = 2.0 · D+ = 1.5 · D = 1.0 · F = 0.0"


def _gpa_pairs(q):
    out, seen = [], set()
    for code, g in _GPA_PAIR_RE.findall(q):
        if code in seen:
            continue
        seen.add(code)
        out.append((code, g.upper()))
    return out


def _course_credit(d):
    """คืนจำนวนหน่วยกิตเป็นตัวเลข หรือ None ถ้าเป็นหน่วยกิตไม่คงที่ (เช่น วิชาปัญหาพิเศษ 1-3 หน่วยกิต)"""
    raw = parse_card(d)["credit"].split("(")[0].strip()
    try:
        return int(raw)
    except ValueError:
        return None


def gpa_answer(q):
    """'คำนวณเกรด: รหัส1 เกรด1, รหัส2 เกรด2, ...' -> คำนวณเกรดเฉลี่ยถ่วงน้ำหนักหน่วยกิต (คำถามอื่นคืน None)"""
    nq = _norm(q)
    if not any(_norm(k) in nq for k in GPA_TRIGGER):
        return None
    pairs = _gpa_pairs(q)
    if not pairs:
        return random.choice(OPENERS) + _GRADE_TABLE + "\n\n" + _GPA_EXAMPLE
    rows, not_found, var_credit = [], [], []
    total_credit = total_point = 0.0
    for code, g in pairs:
        d = BY_CODE.get(code)
        if not d:
            not_found.append(code)
            continue
        credit = _course_credit(d)
        if credit is None:
            var_credit.append(code)
            continue
        gp = GRADE_POINTS[g]
        total_credit += credit
        total_point += credit * gp
        rows.append(f"- {code} {d['name_th']}: เกรด **{g}** ({credit} หน่วยกิต × {gp:.1f} = {credit * gp:.1f})")
    if not rows:
        return random.choice(OPENERS) + "ไม่เจอรหัสวิชาที่คำนวณได้เลยครับ ลองเช็กรหัสวิชาอีกทีนะ\n\n" + _GPA_EXAMPLE
    gpa = total_point / total_credit if total_credit else 0
    msg = (random.choice(OPENERS) + "📊 **คำนวณเกรดเฉลี่ย (GPA)**\n" + "\n".join(rows) +
           f"\n\nรวม **{total_credit:.0f} หน่วยกิต** | คะแนนรวม {total_point:.1f}"
           f"\n🎯 **เกรดเฉลี่ย = {gpa:.2f}**")
    notes = []
    if not_found:
        notes.append(f"⚠️ ไม่พบรหัสวิชา: {', '.join(not_found)} ในหลักสูตร (ไม่ได้รวมในการคำนวณ)")
    if var_credit:
        notes.append(f"⚠️ วิชา {', '.join(var_credit)} เป็นหน่วยกิตไม่คงที่ (เช่น ปัญหาพิเศษ) "
                      "ไม่ได้รวมอัตโนมัติ — ถ้าอยากรวมด้วย บอกจำนวนหน่วยกิตที่ลงจริงมาแทนได้เลยครับ")
    if notes:
        msg += "\n\n" + "\n".join(notes)
    return msg


def rule_answer(q, prev_user=None):
    """ตอบทันทีถ้าตอบจากข้อมูลได้ตรงๆ ไม่อย่างนั้นคืน None"""
    nq = _norm(q)
    g = gpa_answer(q)
    if g:
        return g
    if any(k in nq for k in YESNO_KW):
        return _yesno_prereq(q)
    # 1) รหัสวิชาที่ไม่มีจริง
    for code in re.findall(r"\b0\d{7}\b", q):
        if code not in BY_CODE:
            return (f"อืม… ไม่เจอรหัสวิชา **{code}** ในหลักสูตรวิศวกรรมดิจิทัลและอิเล็กทรอนิกส์อัจฉริยะ พ.ศ. 2566 เลยนะ 🤔\n"
                    "ลองเช็กรหัสอีกทีได้ไหม หรือถ้าเป็นวิชานอกสาขา แนะนำสอบถามฝ่ายวิชาการของคณะนะครับ")
    # 1.2) เรื่องที่เอกสารหลักสูตรไม่มีแน่นอน -> ปฏิเสธสุภาพ (ไม่ให้โมเดลเดาตัวเลข)
    if not mentioned_courses(q):
        for k, label in OUT_OF_SCOPE:
            if k in nq:
                return (f"ขออภัยครับ ในเอกสารหลักสูตรที่มีอยู่ไม่มีข้อมูลเรื่อง{label} 🙏\n"
                        "แนะนำให้ติดต่อฝ่ายวิชาการของคณะวิศวกรรมศาสตร์ศรีราชา หรืออาจารย์ที่ปรึกษาเพื่อข้อมูลที่ถูกต้องนะครับ")
    # 1.5) แผนสหกิจ vs แผนปกติ
    if "สหกิจ" in nq and any(k in nq for k in ["แผน", "ต่าง", "ปกติ", "ไม่ไป", "ไม่ทำ", "ไม่ลง", "แทน", "บังคับ",
                                                 "เลือกได้", "ต้องไป", "จำเป็น", "ไม่อยาก"]):
        return random.choice(OPENERS) + COOP_ANSWER
    # 2) วิชาเดียวที่เอ่ยถึงชัดเจน
    courses = mentioned_courses(q)
    inherited = False
    if not courses and prev_user and len(nq) <= 40 and not sem_from_question(q) and "หลักสูตร" not in nq:
        prev_courses = mentioned_courses(prev_user)      # คำถามต่อเนื่อง เช่น "แล้วกี่หน่วยกิต"
        if len(prev_courses) == 1:
            courses, inherited = prev_courses, True
    if len(courses) == 1:
        ans = _course_rule(courses[0], q, inherited)
        if ans:
            return ans
    if courses:
        return None
    # 3) แผนการเรียนรายเทอม
    sems = sem_from_question(q)
    if not sems and prev_user and SEM_WORDS.search(q):   # "แล้วเทอม 2 ล่ะ"
        py = sem_from_question(prev_user)
        s = re.search(r"(?:เทอม|ภาค)\s*(?:ที่)?\s*(\d)", q)
        if py:
            sem_no = int(s.group(1)) if s else (1 if ("ต้น" in q) else 2)
            sems = [(py[0][0], sem_no)]
    if sems:
        parts = [p for p in (_format_semester(y, s) for (y, s) in sems) if p]
        if parts:
            tail = "\n\nอยากรู้รายละเอียดวิชาไหนเพิ่ม พิมพ์ชื่อหรือรหัสวิชามาถามต่อได้เลยนะ 😊"
            return random.choice(OPENERS) + "\n\n".join(parts) + tail
    # 4) คำถามภาพรวมหลักสูตร (รหัสวิชา, หน่วยกิตรวม, ศึกษาทั่วไป ฯลฯ) -> ข้อความจากเอกสารโดยตรง
    ov = overview_answer(q)
    if ov:
        return ov
    # 5) ขอวิชาตามความสนใจ (AI, พลังงาน, EV ...) แล้วค่อยขอรายชื่อวิชาทั้งหมด
    tp = topic_answer(q)
    if tp:
        return tp
    # 6) ขอรายชื่อวิชาหลายวิชา (ให้โมเดลเขียนรายการยาวๆ จะวนซ้ำ/แต่งรหัส จึงตอบจากข้อมูลตรงๆ)
    if is_list_question(nq):
        return _list_answer(nq)
    return None


LIST_KW = ["รายวิชา", "วิชาอะไรบ้าง", "มีวิชาอะไร", "รายชื่อวิชา", "วิชาทั้งหมด", "ทุกวิชา", "listวิชา",
           "วิชาในสาขา", "วิชาที่ต้องเรียน", "เรียนวิชาอะไร", "courselist", "allcourses"]


def is_list_question(nq):
    if any(k in nq for k in PREREQ_KW + CREDIT_KW):
        return False
    if any(k in nq for k in LIST_KW):
        return True
    return "วิชา" in nq and any(k in nq for k in ["อะไรบ้าง", "ทั้งหมด", "มีอะไร", "รายชื่อ", "ไหนบ้าง"])


def _list_answer(nq):
    if "เลือก" in nq and "เสรี" not in nq:
        picked, title = [d for d in COURSES if "เลือกทางวิศวกรรม" in parse_card(d)["group"]], \
            "วิชาเลือกทางวิศวกรรม (ต้องเลือกเรียนไม่น้อยกว่า 6 หน่วยกิต)"
    elif "บังคับ" in nq:
        picked, title = [d for d in COURSES if "บังคับทางวิศวกรรม" in parse_card(d)["group"]], \
            "กลุ่มวิชาบังคับทางวิศวกรรม (62 หน่วยกิต)"
    elif "พื้นฐาน" in nq:
        picked, title = [d for d in COURSES if "เฉพาะพื้นฐาน" in parse_card(d)["group"]], "วิชาเฉพาะพื้นฐาน (23 หน่วยกิต)"
    else:
        picked, title = COURSES, "รายวิชาทั้งหมดในหลักสูตร (47 วิชาที่มีรหัส)"
    groups = {}
    for d in picked:
        groups.setdefault(parse_card(d)["group"], []).append(d)
    lines = [f"📚 **{title}**", "_หลักสูตรวิศวกรรมดิจิทัลและอิเล็กทรอนิกส์อัจฉริยะ พ.ศ. 2566_"]
    for g, ds in groups.items():
        lines.append(f"\n**{g}**")
        lines += [f"• {d['code']} {d['name_th']} {parse_card(d)['credit']}" for d in ds]
    if picked is COURSES:
        lines.append("\nนอกจากนี้ยังมีวิชาศึกษาทั่วไป (30 หน่วยกิต) และวิชาเลือกเสรี (6 หน่วยกิต) ที่เลือกเรียนได้จากคณะอื่น")
    lines.append("\nอยากรู้รายละเอียดวิชาไหน พิมพ์ชื่อหรือรหัสวิชามาถามต่อได้เลยนะ 😊")
    return random.choice(OPENERS) + "\n".join(lines)


# ------------------------------------------------------------------ แยกประเภทคำถาม
CURRICULUM_KW = ["หลักสูตร", "หน่วยกิต", "เทอม", "ภาคการศึกษา", "แผนการเรียน", "สหกิจ", "โครงงาน", "รหัสวิชา",
                 "วิชาเลือก", "วิชาบังคับ", "ศึกษาทั่วไป", "เลือกเสรี", "จบการศึกษา", "เรียนจบ", "ลงวิชา",
                 "ลงทะเบียน", "prerequisite", "ค่าเทอม", "สาขา", "dsee", "ดิจิทัลและอิเล็กทรอนิกส์", "สัมมนา",
                 "ต้องเรียนก่อน", "เรียนมาก่อน"]


def is_curriculum(q):
    nq = _norm(q)
    if mentioned_courses(q) or sem_from_question(q):
        return True
    if any(k in nq for k in CURRICULUM_KW):
        return True
    top = _course_scores(q)[0][0]
    return top >= 20


def friendly_prefix():
    return random.choice(["", "โอเค ", "ได้เลยครับ "])


GENERAL_SYSTEM = (
    "คุณชื่อ 'DSEE Buddy' เป็นรุ่นพี่ใจดีที่คอยช่วยนิสิตสาขาวิศวกรรมดิจิทัลและอิเล็กทรอนิกส์อัจฉริยะ "
    "คณะวิศวกรรมศาสตร์ศรีราชา มหาวิทยาลัยเกษตรศาสตร์ วิทยาเขตศรีราชา "
    "พูดภาษาไทยแบบเป็นกันเอง สุภาพ อบอุ่น ใช้คำลงท้าย 'ครับ' ได้ อธิบายให้เข้าใจง่ายเหมือนรุ่นพี่สอนน้อง "
    "ตอบได้ทุกเรื่อง ทั้งเรื่องเรียน การเขียนโปรแกรม ชีวิตมหาวิทยาลัย และความรู้ทั่วไป "
    "เวลาตอบเรื่องโค้ด ให้ใส่โค้ดใน ```ภาษา ... ``` พร้อมอธิบายสั้นๆ "
    "ถ้าไม่แน่ใจข้อมูล ให้บอกตรงๆ ว่าไม่แน่ใจ ห้ามแต่งตัวเลขหรือข้อเท็จจริงขึ้นเอง "
    "ถ้าถูกถามรายละเอียดหลักสูตร DSEE (รหัสวิชา หน่วยกิต แผนการเรียน) ที่ไม่มีข้อมูลในบทสนทนา "
    "ให้แนะนำให้พิมพ์ชื่อหรือรหัสวิชามาถามตรงๆ แทนการเดา "
    "ห้ามแสดงกระบวนการคิดภายใน ตอบคำตอบสุดท้ายเลย"
)


# ------------------------------------------------------------------ คำถามภาพรวมหลักสูตร
OV = {}
for _t in INDEX["overview"]:
    _topic, _text = _t.lstrip("- ").split(": ", 1)
    OV[_topic] = _text

GROUP_DIGIT = {"0": "กลุ่มวิชาทั่วไปสำหรับนิสิตนอกสาขาวิชา",
               "1": "กลุ่มวิชาวิศวกรรมข้อมูล ระบบปัญญาประดิษฐ์ และอิเล็กทรอนิกส์อัจฉริยะ",
               "2": "กลุ่มวิชาพื้นฐานทางวิศวกรรมไฟฟ้าและคอมพิวเตอร์", "3": "กลุ่มวิชาพลังงาน",
               "4": "กลุ่มวิชาการขับเคลื่อนด้วยไฟฟ้า",
               "9": "กลุ่มวิชาสหกิจศึกษา เรื่องเฉพาะทาง สัมมนา ปัญหาพิเศษ และโครงงานวิศวกรรมดิจิทัลและอิเล็กทรอนิกส์อัจฉริยะ"}


def _code_meaning_answer():
    lines = ["🔢 **ความหมายของรหัสวิชา (8 หลัก)** — ใช้กับรหัสของสาขาที่ขึ้นต้นด้วย 03610",
             "• หลักที่ 1–2 **03** = วิทยาเขตศรีราชา",
             "• หลักที่ 3–5 **610** = สาขาวิชาวิศวกรรมดิจิทัลและอิเล็กทรอนิกส์อัจฉริยะ",
             "• หลักที่ 6 = ระดับชั้นปี",
             "• หลักที่ 7 = กลุ่มวิชา"]
    lines += [f"   – {k} = {v}" for k, v in GROUP_DIGIT.items()]
    lines.append("• หลักที่ 8 = ลำดับวิชาในแต่ละกลุ่ม")
    lines.append("ตัวอย่าง: **03610331** → ปี 3 · กลุ่ม 3 (พลังงาน) · วิชาลำดับที่ 1 = เทคโนโลยีพลังงานสีเขียวอัจฉริยะ")
    outside = [d for d in COURSES if not d["code"].startswith("03610") and d["code"] != "01999111"]
    lines.append("\n📎 **วิชาในหลักสูตรที่ใช้รหัสนอกหลักสูตร** (รหัสของสาขา/ภาควิชาอื่นที่ต้องเรียน):")
    lines += [f"• {d['code']} {d['name_th']}" for d in outside]
    lines.append("• 01999111 ศาสตร์แห่งแผ่นดิน (วิชาศึกษาทั่วไปบังคับ)")
    lines.append("\nถ้าเจอรหัสไหนที่ไม่แน่ใจ พิมพ์รหัสมาถามได้เลย เดี๋ยวบอกให้ว่าเป็นวิชาอะไร 😊")
    return "\n".join(lines)


def _decode_code(d):
    c = d["code"]
    return (f"🔢 **{c} {d['name_th']}**\n• 03 = วิทยาเขตศรีราชา\n• 610 = สาขาวิศวกรรมดิจิทัลและอิเล็กทรอนิกส์อัจฉริยะ\n"
            f"• หลักที่ 6 = **{c[5]}** → ระดับชั้นปีที่ {c[5]}\n• หลักที่ 7 = **{c[6]}** → {GROUP_DIGIT.get(c[6], '-')}\n"
            f"• หลักที่ 8 = **{c[7]}** → ลำดับวิชาในกลุ่ม")


def overview_answer(q):
    nq = _norm(q)
    op = random.choice(OPENERS)
    if "รหัส" in nq and any(k in nq for k in ["ความหมาย", "หมายถึง", "หลัก", "เลข", "แปล", "อ่าน", "ไม่รู้",
                                               "เกี่ยวกับรหัส", "นอกหลักสูตร", "นอกสาขา", "ไม่ใช่ของสาขา"]):
        return op + _code_meaning_answer()
    if any(k in nq for k in ["อักษรย่อ", "แบบบันทึก", "ฤดูร้อน", "t/g"]) or re.search(r"\bfe\b", q.lower()):
        return op + "📝 **แบบบันทึกผลการเรียน**\n" + OV["แบบบันทึกผลการเรียน"]
    if re.search(r"\d\(\d-\d-\d\)", q) or "ตัวเลขในวงเล็บ" in nq:
        return op + "🧮 **ความหมายของตัวเลขหน่วยกิต**\n" + OV["ความหมายของตัวเลขหน่วยกิต"]
    if "ศึกษาทั่วไป" in nq or re.search(r"\bge\b", q.lower()):
        return op + "📗 **หมวดวิชาศึกษาทั่วไป**\n" + OV["หมวดวิชาศึกษาทั่วไป"].replace("; ", "\n• ").replace(": ", ":\n• ", 1)
    if "เลือกเสรี" in nq:
        return op + "🆓 **หมวดวิชาเลือกเสรี**\n" + OV["หมวดวิชาเลือกเสรี"]
    if "วิชาเลือก" in nq and any(k in nq for k in ["หน่วยกิต", "กี่ตัว", "กี่วิชา", "ต้องเลือก"]):
        return (op + "🎯 ต้องเรียน**กลุ่มวิชาเลือกทางวิศวกรรมไม่น้อยกว่า 6 หน่วยกิต** (ส่วนใหญ่วิชาละ 3 หน่วยกิต = ประมาณ 2 วิชา) "
                "ตามแผนอยู่ในช่อง 'วิชาเฉพาะเลือก' ปี 3 เทอม 2 และปี 4 เทอม 1\n"
                "พิมพ์ 'มีวิชาเลือกอะไรบ้าง' เพื่อดูรายชื่อทั้งหมดได้นะ")
    if any(k in nq for k in ["ชื่อหลักสูตร", "ชื่อปริญญา", "ได้ปริญญา", "วุฒิอะไร", "ชื่อสาขา"]):
        return op + "🎓 " + OV["ชื่อหลักสูตร"]
    if ("หน่วยกิต" in nq or "เครดิต" in nq or "โครงสร้าง" in nq) and \
            any(k in nq for k in ["จบ", "ทั้งหมด", "รวม", "ตลอดหลักสูตร", "โครงสร้าง", "หมวด"]) and \
            not any(k in nq for k in ["เทอม", "ภาค", "ปี"]):
        t = OV["โครงสร้างหลักสูตรและหน่วยกิตรวม"]
        return (op + "📊 **โครงสร้างหลักสูตร**\n" + t.replace(" 1) ", "\n1) ").replace(" 2) ", "\n2) ").replace(" 3) ", "\n3) "))
    if any(k in nq for k in ["แต่ละเทอม", "ต่อเทอม", "ต่อภาค", "แต่ละภาค"]) and "หน่วยกิต" in nq:
        return op + "🗓️ **หน่วยกิตต่อภาคการศึกษา**\n" + OV["หน่วยกิตต่อภาคการศึกษา"].replace(", ", "\n• ")
    return None


COOP_ANSWER = (
    "🏢 **เรื่องสหกิจศึกษา ตามเอกสารหลักสูตร DSEE 2566**\n"
    "• เอกสารที่มีระบุ **แผนการศึกษาไว้แผนเดียว** และสหกิจศึกษารวมอยู่ในแผนนั้น ไม่มีแผนปกติ (แบบไม่ไปสหกิจ) แยกออกมา\n"
    "• **03600490 สหกิจศึกษา 6 หน่วยกิต** อยู่ใน *กลุ่มวิชาบังคับทางวิศวกรรม* (62 หน่วยกิต) จึงเป็นวิชาบังคับ ไม่ใช่วิชาเลือก\n"
    "• ตามแผนไปสหกิจใน **ปีที่ 4 ภาคการศึกษาที่ 2** ซึ่งเป็นวิชาเดียวของเทอมนั้น (รวม 6 หน่วยกิต)\n"
    "• เนื้อหาวิชา: ปฏิบัติงานในลักษณะพนักงานชั่วคราวตามโครงงานที่ได้รับมอบหมาย พร้อมจัดทำรายงานและนำเสนอ\n"
    "• ก่อนหน้านั้น ปี 4 เทอม 1 จะเรียน 12 หน่วยกิต (03610431, 03610497 สัมมนา, 03610499 โครงงาน II, วิชาเฉพาะเลือก, วิชาเลือกเสรี)\n\n"
    "ถ้ามีเหตุจำเป็นที่ไปสหกิจไม่ได้ หรืออยากรู้ว่ามีวิชาทดแทนไหม เอกสารหลักสูตรไม่ได้ระบุไว้ "
    "แนะนำให้ปรึกษาอาจารย์ที่ปรึกษาหรือฝ่ายวิชาการของคณะนะครับ 🙏"
)


# ------------------------------------------------------------------ วิชาตามความสนใจ (ตรงกับ dataset ที่ใช้เทรน)
TOPICS = [
    ("AI / machine learning", r"\bai\b|ปัญญาประดิษฐ์|machine ?learning|deep ?learning|\bml\b|เอไอ",
     ["03603462", "03607332", "03610412", "03607331", "03610111", "03610312"]),
    ("พลังงานไฟฟ้า / พลังงานทดแทน", r"พลังงาน|energy|โซลาร์|solar",
     ["03610331", "03610431", "03610332", "03610333", "03610432"]),
    ("ยานยนต์ไฟฟ้า (EV)", r"\bev\b|ยานยนต์ไฟฟ้า|รถยนต์ไฟฟ้า|รถไฟฟ้า|แบตเตอรี่|สถานีชาร์จ",
     ["03601479", "03608445", "03610441", "03610341"]),
    ("หุ่นยนต์และระบบอัตโนมัติ", r"หุ่นยนต์|robot|ระบบอัตโนมัติ|automation", ["03607332", "03607422", "03601364", "03607331"]),
    ("การเขียนโปรแกรม", r"เขียนโปรแกรม|โปรแกรมมิ่ง|programming|coding|โค้ด", ["03603111", "03603112", "03610333", "03603435"]),
    ("วงจรอิเล็กทรอนิกส์", r"วงจร|circuit", ["03610121", "03610225", "03601232", "03601332", "03610341"]),
    ("IoT / ระบบสมองกลฝังตัว", r"\biot\b|ฝังตัว|embedded|อินเทอร์เน็ตของสรรพสิ่ง", ["03610224", "03607422", "03601332", "03610411"]),
]
ASK_WORDS = ["อะไร", "ไหน", "บ้าง", "แนะนำ", "ควร", "สนใจ", "อยากเรียน", "มีไหม", "เกี่ยวกับ"]


def topic_answer(q):
    low = q.lower()
    nq = _norm(q)
    if "วิชา" not in nq or not any(w in nq for w in ASK_WORDS):
        return None
    for title, pattern, codes in TOPICS:
        if re.search(pattern, low):
            lines = [f"🧭 **วิชาที่เกี่ยวกับ{title}**"]
            for c in codes:
                d = BY_CODE.get(c)
                if not d:
                    continue
                info = parse_card(d)
                tag = "วิชาเลือก" if "เลือก" in info["group"] else info["when"].replace("เรียนใน", "บังคับ ").replace(" ตามแผนการเรียน", "")
                lines.append(f"• {d['code']} {d['name_th']} {info['credit']} — {tag}")
            lines.append("\nอยากรู้รายละเอียดวิชาไหน พิมพ์ชื่อหรือรหัสวิชามาถามต่อได้เลยนะ 😊")
            return random.choice(OPENERS) + "\n".join(lines)
    return None


OUT_OF_SCOPE = [("ค่าเทอม", "ค่าเทอม"), ("ค่าธรรมเนียม", "ค่าธรรมเนียมการศึกษา"), ("ค่าหอ", "ค่าหอพัก"), ("หอพัก", "หอพัก"),
                ("ทุนการศึกษา", "ทุนการศึกษา"), ("พ้นสภาพ", "เกณฑ์การพ้นสภาพนิสิต"), ("เกียรตินิยม", "เกณฑ์เกียรตินิยม"),
                ("tcas", "การรับสมัคร"), ("รับสมัคร", "การรับสมัคร"), ("ตารางสอบ", "ตารางสอบ"), ("วันสอบ", "วันสอบ"),
                ("ข้อสอบเก่า", "ข้อสอบเก่า"), ("เงินเดือน", "เงินเดือนหลังจบ"), ("วันเปิดเทอม", "วันเปิดภาคเรียน"),
                ("ย้ายสาขา", "การย้ายสาขา"), ("เทียบโอน", "การเทียบโอนหน่วยกิต"), ("ลาพัก", "การลาพักการศึกษา"),
                ("ชื่ออาจารย์", "รายชื่ออาจารย์ผู้สอน"), ("เบอร์โทร", "เบอร์โทรติดต่อ"), ("ที่จอดรถ", "ที่จอดรถ")]


def _yesno_prereq(q):
    """'ต้องผ่าน A ก่อนลง B ใช่ไหม' -> ตอบใช่/ไม่ใช่จากข้อมูลจริง (คำถามใช่ไหมแบบอื่นให้โมเดลตอบ)"""
    nq = _norm(q)
    cs = mentioned_courses(q)
    if len(cs) != 2 or not any(k in nq for k in PREREQ_KW):
        return None
    def pos(d):
        i = nq.find(d["code"])
        return i if i >= 0 else nq.find(_norm(d["name_th"]))
    a, b = sorted(cs, key=pos)               # a = วิชาที่ถามว่าต้องผ่านก่อน, b = วิชาที่จะลง
    pre = parse_card(b)["prereq"]
    title = f"**{b['code']} {b['name_th']}**"
    if a["code"] in pre:
        return random.choice(OPENERS) + f"✅ **ใช่ครับ** {title} — {pre}"
    seq = SEQUEL_OF.get(b["code"])
    if seq and seq["code"] == a["code"]:
        return (random.choice(OPENERS) + f"ไม่ได้บังคับตามคำอธิบายรายวิชาครับ ({pre}) "
                f"แต่ {title} เป็นภาคต่อของ **{a['code']} {a['name_th']}** จึงควรเรียนตัวนั้นก่อนตามแผนนะ")
    return random.choice(OPENERS) + f"❌ **ไม่ใช่ครับ** {title} — {pre}"
