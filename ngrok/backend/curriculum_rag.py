# -*- coding: utf-8 -*-
"""ดึงข้อมูลหลักสูตรจริง (curriculum_data.json) มาแนบเป็น context ให้โมเดล ลดการแต่งข้อมูลเอง"""
import json, os, re

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'curriculum_data.json')
with open(_PATH, encoding='utf-8') as f:
    _D = json.load(f)

STRUCT, DESC = _D['structure'], _D['desc']
PLANS = {'แผนปกติ': _D['plan_regular'], 'แผนสหกิจศึกษา': _D['plan_coop']}

SECTION = {
    'found_math_sci': 'วิชาเฉพาะพื้นฐาน กลุ่มพื้นฐานทางคณิตศาสตร์และวิทยาศาสตร์',
    'found_eng': 'วิชาเฉพาะพื้นฐาน กลุ่มพื้นฐานทางวิศวกรรม',
    'core': 'วิชาเฉพาะด้าน กลุ่มวิชาบังคับทางวิศวกรรม (วิชาบังคับ)',
    'elective': 'วิชาเฉพาะด้าน กลุ่มวิชาเลือกทางวิศวกรรม (วิชาเลือก)',
    None: 'หมวดวิชาศึกษาทั่วไป กลุ่มสาระพลเมืองไทยและพลเมืองโลก',
}

COURSES = {}
for c, v in DESC.items():
    COURSES[c] = dict(name_th=v['name_th'], name_en=v['name_en'], credit=v['credit'])
for c, v in STRUCT.items():
    COURSES[c] = dict(name_th=v['name_th'], name_en=v['name_en'], credit=v['credit'])

# เรียงชื่อยาวก่อน กัน "คณิตศาสตร์วิศวกรรม" ไปทับ "คณิตศาสตร์วิศวกรรมไฟฟ้า"
_NAMES = sorted({v['name_th'] for c, v in COURSES.items() if c in STRUCT and len(v['name_th']) >= 5}, key=len, reverse=True)
_NAME2CODE = {}
for c in STRUCT:
    _NAME2CODE.setdefault(COURSES[c]['name_th'], c)


def _clean(s):
    return re.sub(r'(?<=[ก-ฮ]) (?=[ะาำิีึืุูั็่้๊๋์])', '', re.sub(r'\s+', ' ', s)).strip()


def _ref(code):
    c = COURSES.get(code)
    return f"{code} {c['name_th']}" if c else code


def _where(code):
    out = []
    for pname, plan in PLANS.items():
        for key, v in plan.items():
            if any(i['code'] == code for i in v['items']):
                y, s = key.split('-')
                out.append(f"{pname} ปี {y} เทอม {s}")
    return out


def course_block(code):
    if code not in COURSES:
        return f"[รหัส {code}] ไม่พบรหัสวิชานี้ในหลักสูตร"
    c = COURSES[code]
    d = DESC.get(code)
    lines = [f"[วิชา {code}] ชื่อไทย: {c['name_th']} | ชื่ออังกฤษ: {c['name_en']} | หน่วยกิต: {c['credit']}"]
    if code in STRUCT:
        lines.append("หมวด: " + SECTION[STRUCT[code]['section']])
        w = _where(code)
        if w:
            lines.append("เรียนในแผน: " + "; ".join(w))
        elif STRUCT[code]['section'] == 'elective':
            lines.append("เป็นวิชาเลือก ไม่ได้กำหนดเทอมตายตัวในตัวอย่างแผนการศึกษา (เลือกเรียนในช่องวิชาเฉพาะเลือก)")
        else:
            lines.append("ไม่ปรากฏเป็นรายวิชาตายตัวในแผน")
    else:
        lines.append("หมวด: วิชาบริการสำหรับนิสิตนอกสาขา ไม่อยู่ในโครงสร้างวิชาบังคับ/เลือกของหลักสูตรนี้")
    if d:
        pre = d['prereq']
        if pre:
            codes = re.findall(r'\d{8}', pre)
            lines.append(f"วิชาที่ต้องเรียนมาก่อน (ข้อความต้นฉบับ): {pre} → " + ", ".join(_ref(x) for x in codes))
        else:
            lines.append("วิชาที่ต้องเรียนมาก่อน: ไม่มีวิชาที่ต้องเรียนมาก่อน (ไม่มีเงื่อนไข)")
        lines.append("คำอธิบายรายวิชา: " + _clean(d['desc_th']))
        if d['desc_en']:
            lines.append("Course description: " + re.sub(r'\s+', ' ', d['desc_en']).strip())
    deps = [x for x in STRUCT if DESC.get(x, {}).get('prereq') and code in re.findall(r'\d{8}', DESC[x]['prereq'])]
    lines.append("วิชาที่ใช้วิชานี้เป็นเงื่อนไข: " + (", ".join(_ref(x) for x in deps) if deps else "ไม่มี"))
    return "\n".join(lines)


def _fmt_items(p):
    out = []
    for i in p['items']:
        cr = re.match(r'^[\d-]+', i['credit']).group(0)
        out.append(f"- {(i['code'] + ' ') if i['code'] else ''}{i['name']} ({cr} หน่วยกิต)")
    return "\n".join(out)


def semester_block(y, s):
    key = f"{y}-{s}"
    r, c = PLANS['แผนปกติ'].get(key), PLANS['แผนสหกิจศึกษา'].get(key)
    if not r:
        return None
    if r == c:
        return f"[ปี {y} เทอม {s}] ทั้งแผนปกติและแผนสหกิจศึกษาเหมือนกัน รวม {r['total']} หน่วยกิต:\n{_fmt_items(r)}"
    return (f"[ปี {y} เทอม {s} แผนปกติ] รวม {r['total']} หน่วยกิต:\n{_fmt_items(r)}\n\n"
            f"[ปี {y} เทอม {s} แผนสหกิจศึกษา] รวม {c['total']} หน่วยกิต:\n{_fmt_items(c)}")


COMPARE_LINES = [
    "[เปรียบเทียบแผนปกติกับแผนสหกิจศึกษา] หน่วยกิตรวมตลอดหลักสูตรของสองแผน 'เท่ากัน' คือ 144 หน่วยกิตทั้งคู่ และเรียน 8 ภาคการศึกษาเท่ากัน ปี 1 ถึงปี 3 เทอม 1 เหมือนกัน ส่วนที่ต่างคือการจัดวิชาเฉพาะเลือก/เลือกเสรี/สหกิจในปี 3 เทอม 2 ถึงปี 4 เทอม 2:",
    "- ปี 3 เทอม 2: แผนปกติ 18 หน่วยกิต, แผนสหกิจเพิ่มวิชาเฉพาะเลือก 4 หน่วยกิต เป็น 22",
    "- ปี 4 เทอม 1: แผนปกติมีวิชาเฉพาะเลือก 7 + วิชาเลือกเสรี 3; แผนสหกิจมีวิชาเฉพาะเลือก 4 + วิชาเลือกเสรี 6 (รวม 19 เท่ากัน)",
    "- ปี 4 เทอม 2: แผนปกติเรียนวิชาเฉพาะเลือก 7 + วิชาเลือกเสรี 3 (10 หน่วยกิต); แผนสหกิจเรียน 03600490 สหกิจศึกษา 6 หน่วยกิตวิชาเดียว",
    "- การฝึกงานไม่น้อยกว่า 240 ชั่วโมง ยกเว้นนิสิตที่เข้าร่วมโครงการสหกิจศึกษา",
]
COMPARE = "\n".join(COMPARE_LINES)
STRUCTURE = (
    "[โครงสร้างหลักสูตร] หลักสูตรวิศวกรรมศาสตรบัณฑิต สาขาวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ ปรับปรุง พ.ศ. 2565 รวมไม่น้อยกว่า 144 หน่วยกิต:\n"
    "(1) หมวดวิชาศึกษาทั่วไป ไม่น้อยกว่า 30 (อยู่ดีมีสุข 3, ศาสตร์แห่งผู้ประกอบการ 6, ภาษากับการสื่อสาร 13, พลเมืองไทยและพลเมืองโลก 5, สุนทรียศาสตร์ 3)\n"
    "(2) หมวดวิชาเฉพาะ ไม่น้อยกว่า 108 = วิชาเฉพาะพื้นฐาน 23 (คณิต-วิทย์ 14, วิศวกรรมพื้นฐาน 9) + วิชาเฉพาะด้านไม่น้อยกว่า 85 (บังคับ 71, เลือกไม่น้อยกว่า 14 โดยเรียนปฏิบัติการอย่างน้อย 2 หน่วยกิต)\n"
    "(3) หมวดวิชาเลือกเสรี ไม่น้อยกว่า 6\n(4) ฝึกงานไม่น้อยกว่า 240 ชั่วโมง (ยกเว้นนิสิตสหกิจศึกษา)"
)

_THAI_DIGITS = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')


def retrieve(message, max_courses=4):
    """คืนข้อความอ้างอิงจากหลักสูตร หรือ '' ถ้าไม่เกี่ยวกับหลักสูตร"""
    if not message:
        return ''
    m = message.translate(_THAI_DIGITS)
    blocks, seen = [], set()

    for code in re.findall(r'(?<!\d)\d{8}(?!\d)', m):
        if code not in seen and len(seen) < max_courses:
            seen.add(code)
            blocks.append(course_block(code))

    rest = m
    for name in _NAMES:
        if name in rest:
            code = _NAME2CODE[name]
            if code not in seen and len(seen) < max_courses:
                seen.add(code)
                blocks.append(course_block(code))
            rest = rest.replace(name, ' ')  # กันชื่อสั้นที่เป็นส่วนหนึ่งของชื่อยาวซ้ำ

    # ชื่อย่อที่ผู้ใช้มักพิมพ์ (ไม่ครบชื่อเต็ม)
    if 'โครงงาน' in m and not any(c in seen for c in ('03601495', '03601499')):
        want = ['03601499'] if re.search(r'โครงงาน\s*(?:II|2|สอง)', m) else                ['03601495'] if re.search(r'โครงงาน\s*(?:I|1|หนึ่ง)(?![I\d])', m) else ['03601495', '03601499']
        for code in want:
            seen.add(code)
            blocks.append(course_block(code))

    sem = re.findall(r'ปี(?:ที่)?\s*([1-4])\s*(?:ภาคการศึกษาที่|ภาคเรียนที่|ภาค|เทอม)\s*([12])', m)
    for y, s in sem:
        b = semester_block(y, s)
        if b and b not in blocks:
            blocks.append(b)
    if not sem and not re.search(r'เทอม|ภาค', m):
        for y in sorted(set(re.findall(r'(?:ชั้นปีที่|ปีที่|ปี)\s*([1-4])(?!\d)', m))):
            for s in '12':
                b = semester_block(y, s)
                if b and b not in blocks:
                    blocks.append(b)

    if re.search(r'สหกิจ', m) and re.search(r'ปกติ|ต่าง|เปรียบเทียบ|เทียบ|ฝึกงาน', m):
        blocks.append(COMPARE)
    elif re.search(r'ฝึกงาน', m):
        blocks.append(COMPARE_LINES[-1])
    if not seen and re.search(r'โครงสร้าง|หน่วยกิตรวม|จบ.*กี่หน่วยกิต|กี่หน่วยกิต.*จบ|วิชาเลือกเสรี|ศึกษาทั่วไป|วิชาเฉพาะ|วิชาบังคับ.*กี่หน่วยกิต|วิชาเลือก.*กี่หน่วยกิต|กี่หน่วยกิต.*วิชา(?:บังคับ|เลือก)', m):
        blocks.append(STRUCTURE)

    if not blocks:
        return ''
    return ("ข้อมูลอ้างอิงจากหลักสูตรจริง (ตอบโดยอิงข้อมูลนี้เท่านั้น ห้ามเปลี่ยนรหัสวิชา ชื่อวิชา หรือตัวเลข "
            "ถ้าไม่มีในข้อมูลให้บอกว่าไม่มีข้อมูล):\n\n" + "\n\n".join(blocks))


# คำถามโครงสร้างที่ตอบตายตัวได้ (LLM เคยอ่านตัวเลขสลับกลุ่ม) pattern ต้องเจาะจงพอไม่ชนคำถามอื่น
FAQ = [
    (r'วิชาเฉพาะพื้นฐาน.*กี่หน่วยกิต|กี่หน่วยกิต.*วิชาเฉพาะพื้นฐาน',
     "วิชาเฉพาะพื้นฐานมี 23 หน่วยกิต แบ่งเป็นกลุ่มวิชาพื้นฐานทางคณิตศาสตร์และวิทยาศาสตร์ 14 หน่วยกิต และกลุ่มวิชาพื้นฐานทางวิศวกรรม 9 หน่วยกิต"),
    (r'สหกิจ.*ฝึกงาน.*(?:ไหม|หรือเปล่า|ต้อง)|ฝึกงาน.*สหกิจ.*(?:ไหม|หรือเปล่า|ต้อง)',
     "ไม่ต้องครับ หลักสูตรกำหนดให้ฝึกงานไม่น้อยกว่า 240 ชั่วโมง ยกเว้นนิสิตที่เข้าร่วมโครงการสหกิจศึกษา (สหกิจศึกษาคือวิชา 03600490 จำนวน 6 หน่วยกิต เรียนในปี 4 เทอม 2)"),
]


def direct_answer(message):
    """คำถามรายเทอมล้วนๆ ตอบจากข้อมูลตรงๆ (LLM ชอบตกหล่นวิชาตอนไล่รายการยาวๆ)"""
    m = (message or '').translate(_THAI_DIGITS)
    if re.search(r'(?<!\d)\d{8}(?!\d)', m):
        return None
    for pat, ans in FAQ:
        if re.search(pat, m):
            return ans
    if not re.search(r'เรียนอะไร|วิชาอะไร|มีวิชา|ลงวิชา|แผนการเรียน|ต้องเรียน', m):
        return None
    sem = re.findall(r'ปี(?:ที่)?\s*([1-4])\s*(?:ภาคการศึกษาที่|ภาคเรียนที่|ภาค|เทอม)\s*([12])', m)
    if len(sem) != 1 or re.search(r'ต่าง|เปรียบเทียบ|เทียบ', m):
        return None
    y, s_ = sem[0]
    key = f"{y}-{s_}"
    want_r, want_c = bool(re.search(r'ปกติ', m)), bool(re.search(r'สหกิจ', m))
    r, c = PLANS['แผนปกติ'][key], PLANS['แผนสหกิจศึกษา'][key]
    if r == c:
        return f"ปี {y} เทอม {s_} ทั้งแผนปกติและแผนสหกิจศึกษาเรียนเหมือนกัน รวม {r['total']} หน่วยกิต ดังนี้:\n{_fmt_items(r)}"
    parts = []
    if want_r or not want_c:
        parts.append(f"แผนปกติ ปี {y} เทอม {s_} รวม {r['total']} หน่วยกิต:\n{_fmt_items(r)}")
    if want_c or not want_r:
        parts.append(f"แผนสหกิจศึกษา ปี {y} เทอม {s_} รวม {c['total']} หน่วยกิต:\n{_fmt_items(c)}")
    return "\n\n".join(parts)


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    for q in sys.argv[1:]:
        print('Q:', q)
        print(retrieve(q) or '(ไม่มี context)')
        print('-' * 40)
