# -*- coding: utf-8 -*-
"""ยิงคำถาม 100 ข้อ ตรวจคำตอบอัตโนมัติ (คำตอบอ้างอิงมาจาก parsed.json)
ระบบทดสอบ 2 แบบ:  rag = ผ่าน backend /api/chat (RAG) | raw = typhoon-lionbot-v4 ตรงๆ ไม่มี RAG
รัน:  python eval_100.py [rag|raw|both]
"""
import json, random, re, sys, time, urllib.request, os

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'clean', 'parsed.json'), encoding='utf-8'))
S, DESC, PR, PC = D['structure'], D['desc'], D['plan_regular'], D['plan_coop']
rng = random.Random(77)


def cn(c):
    return re.match(r'^[\d-]+', c).group(0)


def where(code, plan):
    for k, v in plan.items():
        if any(i['code'] == code for i in v['items']):
            return k.split('-')
    return None


core = [c for c, v in S.items() if v['section'] == 'core' and c.startswith('03601')]
planned = [c for c in S if where(c, PR)]
with_pre = [c for c in S if DESC.get(c, {}).get('prereq')]
no_pre = [c for c in S if c in DESC and not DESC[c]['prereq'] and c.startswith('03601')]
allc = [c for c in S if c.startswith('03601') and c in DESC]

Q = []  # (หมวด, คำถาม, [ต้องมีทุกคำ], [ห้ามมี], [ต้องมีอย่างน้อยหนึ่ง])


def add(cat, q, must=(), forbid=(), anyof=()):
    Q.append((cat, q, list(must), list(forbid), list(anyof)))


# 1) รหัส -> ชื่อ (15)
for c in rng.sample(allc, 15):
    add('รหัส→ชื่อ', rng.choice([f'รหัสวิชา {c} คือวิชาอะไร', f'{c} คือวิชาอะไร']), [S[c]['name_th']])
# 2) ชื่อ -> รหัส (10)
for c in rng.sample(allc, 10):
    add('ชื่อ→รหัส', rng.choice([f'วิชา{S[c]["name_th"]} รหัสอะไร', f'{S[c]["name_th"]} รหัสวิชาอะไร']), [c])
# 3) หน่วยกิต (10)
for c in rng.sample(allc, 10):
    add('หน่วยกิต', f'วิชา {c} กี่หน่วยกิต', [f'{cn(S[c]["credit"])} หน่วยกิต'], anyof=[])
# 4) วิชาบังคับก่อน มี (12)
for c in rng.sample(with_pre, 12):
    codes = re.findall(r'\d{8}', DESC[c]['prereq'])
    add('prereq(มี)', rng.choice([f'วิชา {c} ต้องเรียนอะไรมาก่อน', f'{S[c]["name_th"]}มีวิชาบังคับก่อนไหม']), codes)
# 5) วิชาบังคับก่อน ไม่มี (8)
for c in rng.sample(no_pre, 8):
    others = [x for x in re.findall(r'03\d{6}', '') ]
    add('prereq(ไม่มี)', f'วิชา {c} มีวิชาบังคับก่อนไหม', [], anyof=['ไม่มี'])
# 6) แผนรายเทอม (12)
keys = [(y, s) for y in range(1, 5) for s in (1, 2)]
for y, s in rng.sample(keys, 6):
    items = [i for i in PR[f'{y}-{s}']['items'] if i['code'] and i['code'].isdigit()]
    add('แผนปกติรายเทอม', f'แผนปกติ ปี {y} เทอม {s} เรียนอะไรบ้าง', [i['code'] for i in items] + ([f'{PR[f"{y}-{s}"]["total"]} หน่วยกิต'] if True else []))
for y, s in rng.sample(keys, 6):
    items = [i for i in PC[f'{y}-{s}']['items'] if i['code'] and i['code'].isdigit()]
    add('แผนสหกิจรายเทอม', f'แผนสหกิจ ปี {y} เทอม {s} เรียนอะไรบ้าง', [i['code'] for i in items] + [f'{PC[f"{y}-{s}"]["total"]} หน่วยกิต'])
# 7) วิชานี้เรียนปีไหนเทอมไหน (8)
for c in rng.sample([c for c in planned if c.startswith('03601')], 8):
    y, s = where(c, PR)
    add('ปี/เทอมของวิชา', f'วิชา {c} เรียนปีไหน เทอมไหน', [f'ปี {y}', f'เทอม {s}'])
# 8) ภาพรวมหลักสูตร / เปรียบเทียบ (14)
add('โครงสร้าง', 'หลักสูตรนี้ต้องเรียนกี่หน่วยกิตถึงจะจบ', ['144'])
add('โครงสร้าง', 'ฝึกงานต้องกี่ชั่วโมง', ['240'])
add('โครงสร้าง', 'วิชาบังคับทางวิศวกรรมกี่หน่วยกิต', ['71'])
add('โครงสร้าง', 'วิชาเฉพาะพื้นฐานมีกี่หน่วยกิต', ['23'])
add('โครงสร้าง', 'วิชาเลือกเสรีต้องเรียนกี่หน่วยกิต', ['6'])
add('โครงสร้าง', 'หมวดวิชาศึกษาทั่วไปกี่หน่วยกิต', ['30'])
add('สหกิจ vs ปกติ', 'สหกิจศึกษาเรียนปีไหน เทอมไหน', ['ปี 4', 'เทอม 2'])
add('สหกิจ vs ปกติ', 'วิชาสหกิจศึกษารหัสอะไร กี่หน่วยกิต', ['03600490', '6'])
add('สหกิจ vs ปกติ', 'แผนปกติกับแผนสหกิจหน่วยกิตรวมต่างกันไหม', ['144'], anyof=['ไม่ต่าง', 'เท่ากัน', 'เหมือนกัน'])
add('สหกิจ vs ปกติ', 'ปี 4 เทอม 2 แผนสหกิจเรียนอะไร', ['03600490'])
add('สหกิจ vs ปกติ', 'ปี 4 เทอม 2 ของแผนปกติรวมกี่หน่วยกิต', ['10'])
add('สหกิจ vs ปกติ', 'นิสิตสหกิจต้องฝึกงาน 240 ชั่วโมงไหม', [], anyof=['ไม่ต้อง', 'ยกเว้น', 'ได้รับการยกเว้น'])
add('สหกิจ vs ปกติ', 'ปี 3 เทอม 2 แผนสหกิจรวมกี่หน่วยกิต', ['22'])
add('สหกิจ vs ปกติ', 'ปี 3 เทอม 2 แผนปกติรวมกี่หน่วยกิต', ['18'])
# 9) ไม่มีข้อมูล / ไม่มีรหัสนี้ (11) — ต้องปฏิเสธ ไม่แต่ง
NEG = ['ไม่พบ', 'ไม่มีข้อมูล', 'ไม่มีรหัส', 'ไม่ทราบ', 'ไม่สามารถ', 'สอบถาม', 'ไม่ได้ระบุ']
for c in ['03601999', '03601500', '03601123', '03605101', '03601888', '03601777']:
    add('รหัสไม่มีจริง', f'รหัสวิชา {c} คือวิชาอะไร', [], anyof=NEG)
for q in ['ค่าเทอมเท่าไหร่', 'อาจารย์ที่สอนวงจรไฟฟ้าชื่ออะไร', 'ตารางสอบกลางภาคเมื่อไหร่', 'เงินเดือนวิศวกรไฟฟ้าจบใหม่เท่าไหร่', 'หอพักนิสิตอยู่ตรงไหน']:
    add('นอกขอบเขต', q, [], anyof=NEG)

assert len(Q) == 100, len(Q)


def ask_rag(q):
    r = urllib.request.Request('http://localhost:8000/api/chat', json.dumps({'message': q, 'model': 'typhoon-lionbot-v3'}).encode(), {'Content-Type': 'application/json'})
    out = ''
    for line in urllib.request.urlopen(r, timeout=600):
        line = line.decode().strip()
        if line.startswith('data:'):
            out += json.loads(line[5:]).get('content', '')
    return out


def ask_raw(q):
    r = urllib.request.Request('http://localhost:11434/api/chat', json.dumps({'model': 'typhoon-lionbot-v4', 'stream': False, 'think': False, 'options': {'temperature': 0.1}, 'messages': [{'role': 'user', 'content': q}]}).encode(), {'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(r, timeout=600))['message']['content'] or ''


def judge(ans, must, forbid, anyof):
    a = ans.translate(str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789'))
    ok = all(m in a for m in must) and not any(f in a for f in forbid) and (not anyof or any(x in a for x in anyof))
    return ok


def run(mode):
    fn = ask_rag if mode == 'rag' else ask_raw
    res = []
    t0 = time.time()
    for i, (cat, q, must, forbid, anyof) in enumerate(Q, 1):
        try:
            ans = fn(q)
        except Exception as e:
            ans = f'ERROR {e}'
        ok = judge(ans, must, forbid, anyof)
        res.append(dict(i=i, cat=cat, q=q, ok=ok, ans=ans, must=must, anyof=anyof, forbid=forbid))
        print(f'[{mode}] {i:3d}/100 {"✓" if ok else "✗"} {cat}: {q}  ({time.time()-t0:.0f}s)', flush=True)
        json.dump(res, open(os.path.join(HERE, f'eval_{mode}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return res


def report(mode, res):
    tot = sum(r['ok'] for r in res)
    print(f'\n=== {mode.upper()}: {tot}/100 = {tot}% ===')
    cats = {}
    for r in res:
        cats.setdefault(r['cat'], []).append(r['ok'])
    for c, v in cats.items():
        print(f'  {c:18s} {sum(v):2d}/{len(v):2d} = {100*sum(v)/len(v):5.1f}%')


if __name__ == '__main__':
    modes = ['rag', 'raw'] if (len(sys.argv) < 2 or sys.argv[1] == 'both') else [sys.argv[1]]
    for m in modes:
        report(m, run(m))
