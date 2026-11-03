# -*- coding: utf-8 -*-
"""วัดว่าโมเดลจำข้อมูลที่ฉีดด้วย CPT ได้จริงไหม (ถามตรงๆ ไม่ผ่าน RAG/ความจำ)

ชุดคำถามสุ่มแบบคงที่ (seed 3407) จาก dataset/cpt_gened.json: รหัส->ชื่อ, ชื่อ->รหัส, หน่วยกิต, และเงื่อนไขเกรด
ใช้เทียบ v4 (ก่อน CPT) กับ v5 (หลัง CPT) ด้วยชุดเดียวกัน
รัน: PYTHONUTF8=1 python eval_cpt_probe.py typhoon-lionbot-v4 [จำนวนต่อหมวด]
"""
import io
import json
import os
import random
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OLLAMA = os.getenv('OLLAMA_URL', 'http://localhost:11434') + '/api/chat'
model = sys.argv[1] if len(sys.argv) > 1 else 'typhoon-lionbot-v4'
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30

courses = json.load(io.open(os.path.join(HERE, 'dataset', 'cpt_gened.json'), encoding='utf-8'))
rnd = random.Random(3407)
pick = lambda k: rnd.sample(courses, k)


def norm(s):
    return re.sub(r'\s+', '', s)


probes = []
for c in pick(N):
    probes.append(('code->name', f"รหัสวิชา {c['code']} คือวิชาอะไร", lambda a, c=c: norm(c['name']) in norm(a)))
for c in pick(N):
    probes.append(('name->code', f"วิชา {c['name']} รหัสวิชาอะไร", lambda a, c=c: c['code'] in a))
for c in pick(N // 2):
    probes.append(('credit', f"วิชา {c['name']} ในหมวดวิชาศึกษาทั่วไป กี่หน่วยกิต",
                   lambda a, c=c: bool(re.search(rf"{c['total']}\s*(?:\(|หน่วยกิต)", a))))
RULES = [
    ("แผนสหกิจต้องมีเกรดเฉลี่ยสะสมไม่ต่ำกว่าเท่าไร", lambda a: '2.50' in a or '2.5' in a),
    ("ยื่นจบการศึกษาต้องมีเกรดเฉลี่ยไม่ต่ำกว่าเท่าไร", lambda a: '2.00' in a or re.search(r'(?<![\d.])2(?:\.0)?(?![\d.])', a)),
    ("เกียรตินิยมอันดับ 1 ต้องมีเกรดเฉลี่ยเท่าไร", lambda a: '3.50' in a or '3.5' in a),
    ("เกียรตินิยมอันดับ 2 ต้องมีเกรดเฉลี่ยเท่าไร", lambda a: '3.25' in a),
    ("เกรดเฉลี่ยรวมต่ำกว่าเท่าไรพ้นสภาพนิสิตทันที", lambda a: '1.50' in a or '1.5' in a),
    ("เกรดเฉลี่ยต่ำกว่าเท่าไรภายใน 2 เทอมถึงพ้นสภาพนิสิต", lambda a: '1.75' in a),
    ("วิชาเสรีในที่นี้หมายถึงวิชาอะไร", lambda a: 'ศึกษาทั่วไป' in a),
    ("หมวดวิชาศึกษาทั่วไปแบ่งเป็นกี่กลุ่มสาระ", lambda a: '5' in a or 'ห้า' in a),
]
for q, f in RULES:
    probes.append(('rules', q, f))

SYSTEM = "คุณคือ LIONBOT ผู้ช่วยตอบคำถามหลักสูตรวิศวกรรมไฟฟ้าและอิเล็กทรอนิกส์ ตอบสั้นและตรงคำถาม"
stats, rows = {}, []
t0 = time.time()
for i, (cat, q, check) in enumerate(probes, 1):
    try:
        r = requests.post(OLLAMA, json={
            'model': model, 'stream': False, 'options': {'temperature': 0, 'num_predict': 120},
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': q}]}, timeout=300)
        ans = r.json().get('message', {}).get('content', '')
    except Exception as e:  # noqa: BLE001
        ans = f'[error {e}]'
    ok = bool(check(ans))
    s = stats.setdefault(cat, [0, 0])
    s[0] += ok
    s[1] += 1
    rows.append({'cat': cat, 'q': q, 'ok': ok, 'answer': ans})
    print(f"[{i}/{len(probes)}] {cat:10s} {'OK ' if ok else 'ERR'} {q[:50]}", flush=True)

print(f"\nmodel={model}  time={time.time() - t0:.0f}s")
tot_ok = sum(v[0] for v in stats.values())
tot = sum(v[1] for v in stats.values())
for k, (a, b) in stats.items():
    print(f"  {k:10s} {a}/{b} = {100 * a / b:.0f}%")
print(f"  {'รวม':10s} {tot_ok}/{tot} = {100 * tot_ok / tot:.0f}%")
out = os.path.join(HERE, f"eval_cpt_probe_{model.replace(':', '_')}.json")
json.dump({'model': model, 'stats': stats, 'rows': rows}, io.open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('saved', out)
