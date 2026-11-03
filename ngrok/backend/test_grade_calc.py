# -*- coding: utf-8 -*-
"""ทดสอบ grade_calc.py ด้วยค่าที่คำนวณมือไว้ล่วงหน้า  รัน: PYTHONUTF8=1 python test_grade_calc.py"""
import grade_calc as g

fails = []


def check(name, cond):
    print(('PASS ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


# 1) GPA เทอมเดียว: 03601211 A(3) + 03601212 B+(3) + 03601213 B(1) = (12+10.5+3)/7 = 3.642857 -> 3.64
r = g.grade_answer("คำนวณเกรด 03601211 A, 03601212 B+, 03601213 B")
check("term GPA 3.64", "= 3.64" in r and "7 หน่วยกิต" in r)

# 2) GPAX ใหม่: (3.0*60 + 16.5)/66 = 2.977 -> 2.98
r = g.grade_answer("ได้ 03601211 B+ และ 03601332 C เกรดเฉลี่ยสะสม 3.0 หน่วยกิตสะสม 60")
check("new GPAX 2.98", "GPAX ใหม่ = 2.98" in r and "66 หน่วยกิต" in r)

# 3) วางแผน: (3.5*144 - 2.85*90)/54 = 4.58 -> เป็นไปไม่ได้
r = g.grade_answer("เกรดเฉลี่ยสะสม 2.85 หน่วยกิตสะสม 90 อยากได้เกียรตินิยมอันดับ 1")
check("honor1 impossible", "เป็นไปไม่ได้" in r and "4.58" in r and "เหลือ 54" in r)

# 4) วางแผน: (3.25*144 - 3.2*100)/44 = 3.36
r = g.grade_answer("GPAX 3.2 สะสม 100 หน่วยกิต อยากได้เกียรตินิยมอันดับ 2")
check("honor2 need 3.36", "3.36" in r and "B+" in r)

# 5) พ้นสภาพ
r = g.grade_answer("GPAX 1.40 หน่วยกิตสะสม 30")
check("dismiss <1.50", "พ้นสภาพนิสิตทันที" in r)
r = g.grade_answer("GPAX 1.60 หน่วยกิตสะสม 30")
check("warn <1.75", "ภายใน 2 เทอม" in r and "ทันที" not in r.split("เกณฑ์แต้ม")[0])

# 6) F ต้องเรียนซ้ำ
r = g.grade_answer("เกรด 03601211 F, 03601212 C")
check("F retake", "เรียนซ้ำ" in r and "03601211" in r)

# 7) ระบุหน่วยกิตเอง + ชื่อวิชา
r = g.grade_answer("คำนวณเกรด ไมโครโพรเซสเซอร์ A, วิชา 2 หน่วยกิต B")
check("name+generic credit", "= 3.60" in r)  # (12+6)/5 = 3.6

# 8) คำถามกฎเกณฑ์ทั่วไป
r = g.grade_answer("พ้นสภาพนิสิตเมื่อไหร่")
check("rules", "1.50" in r and "1.75" in r and "2.50" in r)

# 9) ไม่ยุ่งกับคำถามหลักสูตรทั่วไป
check("no hijack", g.grade_answer("วิชา 03601211 เรียนปีไหน") is None)
check("no hijack 2", g.grade_answer("ปี 3 เทอม 2 เรียนอะไรบ้าง") is None)

# 10) ข้อมูลไม่พอ ได้คำแนะนำ
check("help", "ส่งข้อมูลมาตามตัวอย่าง" in g.grade_answer("ช่วยคำนวณเกรดหน่อย"))

# 11) ไม่มีหน่วยกิตสะสมแต่ขอวางแผน
r = g.grade_answer("GPAX 3.0 อยากได้ 3.5")
check("ask credits", "หน่วยกิตสะสมด้วย" in r)

print("\nFAILED: %s" % fails if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
