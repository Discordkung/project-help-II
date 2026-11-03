# -*- coding: utf-8 -*-
"""คำนวณ วิเคราะห์ และวางแผนเกรด ตอบจากสูตรตรงๆ ไม่ผ่านโมเดล (โมเดลเล็กคิดเลขไม่แม่น)

ทำ 3 อย่าง
  1) คำนวณ GPA เทอมนี้ / GPAX ใหม่ จากเกรดรายวิชา (หน่วยกิตดึงจากหลักสูตร หรือระบุเองว่า "3 หน่วยกิต")
  2) วิเคราะห์สถานะตามเงื่อนไขของนิสิต (สหกิจ 2.50, ยื่นจบ 2.00, เกียรตินิยม 3.50/3.25, พ้นสภาพ 1.50/1.75)
  3) วางแผนว่าหน่วยกิตที่เหลือต้องได้เกรดเฉลี่ยเท่าไรจึงถึงเป้า
เกณฑ์แต้ม: A=4, B+=3.5, B=3, C+=2.5, C=2, D+=1.5, D=1, F=0
"""
import re
from decimal import Decimal, ROUND_HALF_UP

from curriculum_rag import COURSES

GRADE_POINTS = {'A': 4.0, 'B+': 3.5, 'B': 3.0, 'C+': 2.5, 'C': 2.0, 'D+': 1.5, 'D': 1.0, 'F': 0.0}
TOTAL_CREDITS = 144

# เงื่อนไขที่นิสิตกำหนด (ไม่ได้มาจากเอกสารหลักสูตร)
COOP_MIN = 2.50
GRAD_MIN = 2.00
HONOR1_MIN = 3.50
HONOR2_MIN = 3.25
DISMISS_NOW = 1.50
DISMISS_WARN = 1.75
RULE_NOTE = "(เงื่อนไขนี้เป็นเกณฑ์ที่กำหนดไว้ในระบบ ไม่ได้มาจากเอกสารหลักสูตร ควรยืนยันกับประกาศของคณะ/มหาวิทยาลัยอีกครั้ง)"

_THAI_DIGITS = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
_GRADE_RE = re.compile(r'(?<![A-Za-z0-9])([ABCDF]\+?)(?![A-Za-z0-9+])', re.I)
_CODE_RE = re.compile(r'(?<!\d)\d{8}(?!\d)')
_GENERIC_CREDIT_RE = re.compile(r'(?<![\d.])(\d)\s*หน่วยกิต')
_SKIP_GENERIC = re.compile(r'เหลือ|สะสม|มาแล้ว|ไปแล้ว|ทั้งหมด|รวม')

_NAMES = sorted({v['name_th'] for v in COURSES.values() if len(v['name_th']) >= 4}, key=len, reverse=True)
_NAME2CODE = {}
for _c, _v in COURSES.items():
    _NAME2CODE.setdefault(_v['name_th'], _c)

INTENT_RE = re.compile(r'เกรด|GPA|เกียรตินิยม|พ้นสภาพ|รอดไหม|ตกไหม|แต้มเฉลี่ย', re.I)
HELP = (
    "ผมคำนวณเกรดให้ได้ครับ ส่งข้อมูลมาตามตัวอย่างนี้:\n"
    "1) คำนวณเกรดเทอมนี้: \"03601211 A, 03601212 B+, 03601213 B\" (ใช้รหัสวิชาหรือชื่อวิชา ผมดึงหน่วยกิตจากหลักสูตรให้) "
    "ถ้าเป็นวิชาที่ไม่อยู่ในหลักสูตร ให้ระบุเอง เช่น \"วิชา 3 หน่วยกิต ได้ B\"\n"
    "2) รวมกับเกรดสะสม: เติมว่า \"เกรดเฉลี่ยสะสม 2.85 หน่วยกิตสะสม 90\" เพื่อให้ได้ GPAX ใหม่\n"
    "3) วิเคราะห์สถานะ: \"GPAX 2.40 หน่วยกิตสะสม 100 สถานะเป็นยังไง\"\n"
    "4) วางแผนเกรด: \"GPAX 2.85 หน่วยกิตสะสม 90 อยากได้เกียรตินิยมอันดับ 1\" หรือ \"อยากได้ 3.50\"\n"
    f"เกณฑ์แต้ม: A=4, B+=3.5, B=3, C+=2.5, C=2, D+=1.5, D=1, F=0"
)


def _r2(x):
    return Decimal(str(round(x, 6))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _fmt(x):
    return f"{_r2(x):.2f}"


def _credit_of(code):
    c = COURSES.get(code)
    if not c:
        return None
    m = re.match(r'^(\d+)(?:\(|$)', c['credit'])
    return int(m.group(1)) if m else None  # เช่น "1-3" (ปัญหาพิเศษ) หน่วยกิตไม่ตายตัว


def _course_items(seg):
    """คืน [(ตำแหน่ง, label, หน่วยกิต)] ของวิชาที่พบในข้อความช่วงนี้"""
    items, taken = [], []

    def free(a, b):
        return all(b <= x or a >= y for x, y in taken)

    for m in _CODE_RE.finditer(seg):
        code = m.group(0)
        c = COURSES.get(code)
        label = f"{code} {c['name_th']}" if c else code
        items.append((m.start(), label, _credit_of(code) if c else None, code))
        taken.append((m.start(), m.end()))
    for name in _NAMES:
        start = 0
        while True:
            i = seg.find(name, start)
            if i < 0:
                break
            if free(i, i + len(name)):
                code = _NAME2CODE[name]
                items.append((i, f"{code} {name}", _credit_of(code), code))
                taken.append((i, i + len(name)))
            start = i + len(name)
    if not items and not _SKIP_GENERIC.search(seg):
        for m in _GENERIC_CREDIT_RE.finditer(seg):
            items.append((m.start(), f"วิชา {m.group(1)} หน่วยกิต", int(m.group(1)), None))
    return sorted(items)


def parse_grades(text):
    """คืน (รายการ [(label, credit, grade)], ข้อความเตือน)"""
    pairs, notes = [], []
    for seg in re.split(r'[,;\n]|\sและ\s', text):
        grades = [(m.start(), m.group(1).upper()) for m in _GRADE_RE.finditer(seg)]
        if not grades:
            continue
        courses = _course_items(seg)
        if not courses:
            continue
        if len(courses) != len(grades):
            notes.append(f"ข้อความ \"{seg.strip()[:40]}\" จับคู่วิชากับเกรดไม่ได้ (พบ {len(courses)} วิชา {len(grades)} เกรด) จึงข้ามไป")
            continue
        for (cp, label, credit, code), (gp, g) in zip(courses, grades):
            if credit is None:
                notes.append(f"{label} ไม่ทราบหน่วยกิตแน่ชัด จึงข้ามไป (ระบุเองได้ เช่น \"{code or 'วิชานี้'} 3 หน่วยกิต B\")")
                continue
            pairs.append((label, credit, g))
    return pairs, notes


def _find_target(m):
    """หา GPAX เป้าหมายจากข้อความ คืน (ค่า หรือ None, ข้อความตัดส่วนเป้าหมายออก)"""
    targets = []
    if 'เกียรตินิยม' in m:
        if re.search(r'อันดับ\s*(?:1|หนึ่ง)', m):
            targets.append(HONOR1_MIN)
        if re.search(r'อันดับ\s*(?:2|สอง)', m):
            targets.append(HONOR2_MIN)
        if not targets:
            targets = [HONOR2_MIN, HONOR1_MIN]
    rest = m
    for mm in re.finditer(r'(?:อยากได้|อยากให้|ต้องการ|เป้าหมาย|ให้ถึง|ให้ได้|ถึง)\s*(?:GPAX|GPA|เกรดเฉลี่ย(?:สะสม|รวม)?)?\s*(?:ให้ได้|เป็น)?\s*(\d\.\d{1,2})', m, re.I):
        targets.append(float(mm.group(1)))
        rest = rest.replace(mm.group(0), ' ')
    if re.search(r'สหกิจ', m) and re.search(r'วางแผน|ต้องได้|ผ่านเกณฑ์|ถึง', m) and COOP_MIN not in targets:
        targets.append(COOP_MIN)
    return sorted(set(targets)), rest


def _find_prior(rest):
    gpax = None
    mm = re.search(r'(?:GPAX|GPA|เกรดเฉลี่ย(?:สะสม|รวม)?|เกรดสะสม|เกรดรวม|เกรด)\s*(?:ตอนนี้|ปัจจุบัน|อยู่ที่|ได้|เป็น|เดิม|เก่า|=|:)?\s*(\d\.\d{1,2})', rest, re.I)
    if mm:
        gpax = float(mm.group(1))
        rest = rest.replace(mm.group(0), ' ')  # กัน "สะสม 2.85" ถูกอ่านเป็นหน่วยกิตสะสม
    earned = None
    mm = (re.search(r'(?:หน่วยกิตสะสม|สะสม(?:ไปแล้ว)?|เรียนมาแล้ว|ผ่านมาแล้ว|เรียนไปแล้ว|เก็บมาแล้ว)\s*(\d{1,3})(?![\d.])\s*(?:หน่วยกิต)?', rest)
          or re.search(r'(?<![\d.])(\d{1,3})\s*หน่วยกิต\s*(?:สะสม|แล้ว)', rest))
    if mm:
        earned = int(mm.group(1))
    remain = None
    mm = re.search(r'เหลือ(?:อีก)?\s*(\d{1,3})\s*หน่วยกิต', rest)
    if mm:
        remain = int(mm.group(1))
    return gpax, earned, remain


def _grade_hint(need):
    for g in ('D', 'D+', 'C', 'C+', 'B', 'B+', 'A'):
        if GRADE_POINTS[g] >= need - 1e-9:
            return g
    return None


def status_lines(gpax):
    out = []
    if gpax < DISMISS_NOW:
        out.append(f"- เกรดเฉลี่ยรวม {_fmt(gpax)} ต่ำกว่า {DISMISS_NOW:.2f} เข้าเกณฑ์พ้นสภาพนิสิตทันที")
    elif gpax < DISMISS_WARN:
        out.append(f"- เกรดเฉลี่ยรวม {_fmt(gpax)} ต่ำกว่า {DISMISS_WARN:.2f} ถ้าอยู่ระดับนี้ภายใน 2 เทอมการศึกษาจะพ้นสภาพนิสิต ต้องรีบเพิ่มเกรดเฉลี่ย")
    if gpax < GRAD_MIN:
        out.append(f"- ยังต่ำกว่าเกณฑ์ยื่นจบ {GRAD_MIN:.2f} อีก {_fmt(GRAD_MIN - gpax)}")
    else:
        out.append(f"- ผ่านเกณฑ์ขั้นต่ำสำหรับยื่นจบ ({GRAD_MIN:.2f})")
    if gpax >= COOP_MIN:
        out.append(f"- ผ่านเกณฑ์เรียนแผนสหกิจศึกษา ({COOP_MIN:.2f}) แต่ต้องรักษาให้ไม่ต่ำกว่านี้ภายในปี 4 เทอม 1 และเรียนครบตามแผน")
    else:
        out.append(f"- ยังไม่ถึงเกณฑ์แผนสหกิจศึกษา ({COOP_MIN:.2f}) ขาดอีก {_fmt(COOP_MIN - gpax)} ต้องทำให้ได้ภายในปี 4 เทอม 1")
    if gpax >= HONOR1_MIN:
        out.append(f"- เข้าเกณฑ์เกียรตินิยมอันดับ 1 (ไม่ต่ำกว่า {HONOR1_MIN:.2f})")
    elif gpax >= HONOR2_MIN:
        out.append(f"- เข้าเกณฑ์เกียรตินิยมอันดับ 2 ({HONOR2_MIN:.2f}-3.49) ถ้าจะขึ้นอันดับ 1 ต้องเพิ่มอีก {_fmt(HONOR1_MIN - gpax)}")
    else:
        out.append(f"- ยังไม่ถึงเกณฑ์เกียรตินิยม ขาดอีก {_fmt(HONOR2_MIN - gpax)} สำหรับอันดับ 2")
    return out


def plan_lines(gpax, earned, remain, targets):
    if remain is None:
        remain = max(TOTAL_CREDITS - earned, 0)
    total = earned + remain
    names = {GRAD_MIN: 'ยื่นจบ', COOP_MIN: 'แผนสหกิจ', HONOR2_MIN: 'เกียรตินิยมอันดับ 2', HONOR1_MIN: 'เกียรตินิยมอันดับ 1'}
    out = [f"วางแผนเกรด: ตอนนี้ GPAX {_fmt(gpax)} สะสม {earned} หน่วยกิต เหลือ {remain} หน่วยกิต (รวมตลอดหลักสูตร {total} หน่วยกิต สมมติทุกวิชาคิดเกรด)"]
    if remain <= 0:
        out.append("- ไม่เหลือหน่วยกิตให้เพิ่มเกรดแล้ว GPAX จึงเป็นค่าปัจจุบัน")
        return out
    for t in targets:
        need = (t * total - gpax * earned) / remain
        label = f"เป้า {_fmt(t)}" + (f" ({names[t]})" if t in names else "")
        if need > 4.0 + 1e-9:
            out.append(f"- {label}: เป็นไปไม่ได้แล้ว ต้องได้เกรดเฉลี่ย {_fmt(need)} ในหน่วยกิตที่เหลือ ซึ่งเกิน 4.00")
        elif need <= 0:
            out.append(f"- {label}: ถึงเป้าแล้ว แม้หน่วยกิตที่เหลือจะได้ 0 ทั้งหมดก็ยังถึง")
        else:
            hint = _grade_hint(need)
            out.append(f"- {label}: ต้องได้เกรดเฉลี่ยอย่างน้อย {_fmt(need)} ใน {remain} หน่วยกิตที่เหลือ (ประมาณ {hint} ขึ้นไปเฉลี่ย)")
    return out


def rules_text():
    return (
        "เงื่อนไขเรื่องเกรดของนิสิต:\n"
        f"- แผนสหกิจศึกษา: เกรดเฉลี่ยสะสมต้องไม่ต่ำกว่า {COOP_MIN:.2f} ภายในปี 4 เทอม 1 และต้องเรียนครบตามแผนภายในเทอมนั้น\n"
        f"- ยื่นจบ: เกรดเฉลี่ยไม่ต่ำกว่า {GRAD_MIN:.2f}\n"
        f"- เกียรตินิยมอันดับ 1: ไม่ต่ำกว่า {HONOR1_MIN:.2f}; อันดับ 2: ตั้งแต่ {HONOR2_MIN:.2f} ถึง 3.49\n"
        f"- เกรดเฉลี่ยรวมต่ำกว่า {DISMISS_NOW:.2f} พ้นสภาพนิสิตทันที; ต่ำกว่า {DISMISS_WARN:.2f} ภายใน 2 เทอมการศึกษา พ้นสภาพนิสิต\n"
        + RULE_NOTE
    )


def grade_answer(message):
    """ตอบเรื่องเกรด หรือ None ถ้าข้อความไม่เกี่ยวกับเกรด"""
    if not message:
        return None
    m = message.translate(_THAI_DIGITS)
    if not INTENT_RE.search(m):
        return None

    pairs, notes = parse_grades(m)
    targets, rest = _find_target(m)
    gpax, earned, remain = _find_prior(rest)
    blocks = []

    if pairs:
        pts = sum(GRADE_POINTS[g] * c for _, c, g in pairs)
        cr = sum(c for _, c, _ in pairs)
        gpa = pts / cr
        rows = [f"- {label} | {c} หน่วยกิต | {g} | แต้ม {GRADE_POINTS[g] * c:.2f}" for label, c, g in pairs]
        blocks.append("คำนวณเกรดภาคเรียนนี้:\n" + "\n".join(rows) +
                      f"\nรวม {cr} หน่วยกิต แต้มรวม {pts:.2f} → GPA ภาคเรียนนี้ = {_fmt(gpa)}")
        final = gpa
        if gpax is not None and earned:
            new_gpax = (gpax * earned + pts) / (earned + cr)
            blocks.append(f"รวมกับเกรดสะสมเดิม (GPAX {_fmt(gpax)}, {earned} หน่วยกิต) → GPAX ใหม่ = {_fmt(new_gpax)} ({earned + cr} หน่วยกิต)")
            final = new_gpax
            earned += cr
            gpax = new_gpax
        elif gpax is not None:
            blocks.append("ถ้าบอกหน่วยกิตสะสมด้วย ผมจะคำนวณ GPAX ใหม่ให้ครับ")
        fails = [label for label, _, g in pairs if g == 'F']
        if fails:
            blocks.append("วิชาที่ได้ F ต้องลงเรียนซ้ำ: " + ", ".join(fails))
        head = "สถานะตามเกรดเฉลี่ยสะสม:" if (gpax is not None and earned) else "สถานะ (ใช้ GPA เทอมนี้เป็นตัวอย่าง ถ้าจะดูตามเกรดเฉลี่ยสะสมจริง ให้บอก GPAX และหน่วยกิตสะสมด้วย):"
        blocks.append(head + "\n" + "\n".join(status_lines(final)))
    elif gpax is not None:
        blocks.append(f"วิเคราะห์สถานะจากเกรดเฉลี่ย {_fmt(gpax)}:\n" + "\n".join(status_lines(gpax)))

    if gpax is not None and (targets or re.search(r'วางแผน|ต้องได้|อยากได้|เหลือ', m)):
        if earned is None:
            blocks.append("จะวางแผนเกรดที่ต้องได้ ผมต้องรู้หน่วยกิตสะสมด้วยครับ เช่น \"หน่วยกิตสะสม 90\" (หรือ \"เหลืออีก 54 หน่วยกิต\")")
        else:
            blocks.append("\n".join(plan_lines(gpax, earned, remain, targets or [GRAD_MIN, COOP_MIN, HONOR2_MIN, HONOR1_MIN])))

    if not blocks:
        if re.search(r'เงื่อนไข|เกณฑ์|พ้นสภาพ|เกียรตินิยม|ขั้นต่ำ|สหกิจ|จบ', m) and not _CODE_RE.search(m):
            return rules_text()
        return HELP

    if notes:
        blocks.append("หมายเหตุ: " + " ".join(notes))
    blocks.append("เกณฑ์แต้ม: A=4, B+=3.5, B=3, C+=2.5, C=2, D+=1.5, D=1, F=0 " + RULE_NOTE)
    return "\n\n".join(blocks)


CONTEXT_HEADER = (
    "ข้อมูลเกรดที่ระบบคำนวณและตรวจแล้ว (ตัวเลขทุกตัวถูกต้อง ห้ามคำนวณใหม่หรือเปลี่ยนตัวเลข): "
    "ให้คุณวิเคราะห์ อธิบาย และแนะนำแนวทางให้นิสิตเป็นภาษาไทยที่เป็นกันเอง โดยอ้างอิงตัวเลขเหล่านี้ "
    "ห้ามคิดตัวเลขใหม่เอง เช่น สมมติเกรดแล้วคำนวณ GPAX ให้ใหม่ ให้ใช้เฉพาะตัวเลขที่ให้ไว้ด้านล่างเท่านั้น "
    "ตอบเฉพาะสิ่งที่นิสิตถาม กระชับ ไม่ต้องคัดลอกทั้งหมดซ้ำ ถ้าข้อมูลไม่พอให้ถามนิสิตเพิ่ม"
)


def grade_context(message):
    """ข้อมูลเกรดที่คำนวณแล้ว เป็น context ให้โมเดลเรียบเรียง/วิเคราะห์เอง (None ถ้าไม่เกี่ยวกับเกรด)"""
    text = grade_answer(message)
    return (CONTEXT_HEADER + "\n\n" + text) if text else None


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    for q in sys.argv[1:]:
        print('Q:', q)
        print(grade_answer(q) or '(ไม่เกี่ยวกับเกรด)')
        print('-' * 40)
