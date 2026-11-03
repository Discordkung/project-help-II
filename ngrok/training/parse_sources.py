# -*- coding: utf-8 -*-
"""Parse decoded PDF text (training/clean/*.txt) into structured data."""
import re, json, collections

def norm(l):
    return ' '.join(l.split())

CODE_LINE = re.compile(r'^(\d{8})\s+(.+?)\s+(\d+\(\s*[\d\- ]+\s*\)|\d+(?:-\d+)?|\d+\(\s*-\s*-\s*\))\s*$')

def parse_structure(path='clean/structure.txt'):
    """Return ordered list of dict(code,name_th,credit,name_en,section) for curriculum courses."""
    lines = [norm(l) for l in open(path, encoding='utf-8').read().split('\n') if l.strip()]
    courses = collections.OrderedDict()
    section = None
    i = 0
    while i < len(lines):
        l = lines[i]
        if 'วิชาเฉพาะพื้นฐาน' in l and 'หน่วยกิต' in l: section = 'foundation'
        if 'กลุ่มวิชาพื้นฐานทางคณิตศาสตร์และวิทยาศาสตร์' in l: section = 'found_math_sci'
        if 'กลุ่มวิชาพื้นฐานทางวิศวกรรม' in l and 'หน่วยกิต' in l: section = 'found_eng'
        if 'กลุ่มวิชาบังคับทางวิศวกรรม' in l: section = 'core'
        if 'กลุ่มวิชาเลือกทางวิศวกรรม' in l: section = 'elective'
        m = CODE_LINE.match(l)
        if m and m.group(1)[:3] != '011' and not m.group(1).endswith('xxx'):
            code, name, cred = m.group(1), m.group(2), m.group(3)
            en = None
            if i+1 < len(lines) and lines[i+1].startswith('(') and lines[i+1].endswith(')'):
                en = lines[i+1][1:-1]
            if code not in courses:
                courses[code] = dict(code=code, name_th=name.strip(), credit=re.sub(r'\s+','',cred), name_en=en, section=section)
        i += 1
    return courses

def parse_desc(path='clean/desc.txt'):
    lines = [norm(l) for l in open(path, encoding='utf-8').read().split('\n')]
    idx = [i for i,l in enumerate(lines) if re.match(r'^\d{8} \S', l) and CODE_LINE.match(l)]
    entries = collections.OrderedDict()
    for n,i in enumerate(idx):
        end = idx[n+1] if n+1 < len(idx) else len(lines)
        m = CODE_LINE.match(lines[i])
        code = m.group(1)
        block = [l for l in lines[i+1:end]]
        # drop page numbers / blanks
        block = [l for l in block if l and not re.fullmatch(r'\d{1,3}', l)]
        en_name = None
        if block and block[0].startswith('('):
            # English name may span multiple lines until ')'
            buf = block[0]; k = 1
            while not buf.endswith(')') and k < len(block):
                buf += ' ' + block[k]; k += 1
            en_name = buf[1:-1] if buf.endswith(')') else buf[1:]
            block = block[k:]
        prereq = None
        while block and (block[0].startswith('วิชาที่ต้อง')):
            prereq = (prereq + ' ' if prereq else '') + block[0]
            block = block[1:]
        # split Thai / English description
        thai, eng = [], []
        for l in block:
            if re.search(r'[\u0e00-\u0e7f]', l): 
                if eng: # thai after english -> likely next header junk
                    break
                thai.append(l)
            else:
                eng.append(l)
        rec = dict(code=code, name_th=m.group(2).strip(), credit=re.sub(r'\s+','',m.group(3)), name_en=en_name,
                   prereq=prereq, desc_th=' '.join(thai), desc_en=' '.join(eng))
        # keep the longest version of duplicates
        if code not in entries or len(rec['desc_th'])+len(rec['desc_en']) > len(entries[code]['desc_th'])+len(entries[code]['desc_en']):
            entries[code] = rec
    return entries

def parse_plan(path):
    lines = [norm(l) for l in open(path, encoding='utf-8').read().split('\n') if l.strip()]
    plan = collections.OrderedDict()
    cur = None
    for l in lines:
        m = re.match(r'^ปีที่ (\d) ภาคการศึกษาที่ (\d)$', l)
        if m:
            cur = (int(m.group(1)), int(m.group(2)))
            if cur not in plan: plan[cur] = dict(items=[], total=None); seen = set()
            else: cur = None  # duplicate page, skip
            continue
        if cur is None: continue
        if l.startswith('จำนวนหน่วยกิต (ชม.'): continue
        m = re.match(r'^รวม\s*(\d+)', l)
        if m:
            plan[cur]['total'] = int(m.group(1)); cur = None; continue
        m = re.match(r'^(\d{8}|\d{5}xxx)\s+(.+?)\s+(\d+(?:\(\s*[\d\- ]*\s*\))?)$', l)
        if m:
            plan[cur]['items'].append(dict(code=m.group(1), name=m.group(2), credit=re.sub(r'\s+','',m.group(3))))
            continue
        m = re.match(r'^(.+?)\s+(\d+\(\s*-\s*-\s*\)|\d+)$', l)
        if m and not l.startswith('ตัวอย่าง'):
            plan[cur]['items'].append(dict(code=None, name=m.group(1), credit=re.sub(r'\s+','',m.group(2))))
    return plan

if __name__ == '__main__':
    s = parse_structure(); d = parse_desc()
    pr = parse_plan('clean/plan_regular.txt'); pc = parse_plan('clean/plan_coop.txt')
    json.dump(dict(structure=s, desc=d, plan_regular={f'{k[0]}-{k[1]}':v for k,v in pr.items()}, plan_coop={f'{k[0]}-{k[1]}':v for k,v in pc.items()}),
              open('clean/parsed.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
    print('structure courses', len(s), 'desc entries', len(d))
    missing = [c for c in s if c not in d]
    print('structure courses without description:', missing)
    print('plan semesters regular', len(pr), 'coop', len(pc))
    for k,v in pr.items(): print('R',k,v['total'], sum(1 for _ in v['items']))
    for k,v in pc.items(): print('C',k,v['total'], sum(1 for _ in v['items']))
