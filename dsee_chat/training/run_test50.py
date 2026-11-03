"""
ทดสอบความแม่นยำ 50 ข้อ ผ่าน backend ที่รันอยู่ในเครื่อง (เหมือนผู้ใช้จริงคุยผ่านหน้าเว็บ)
(ย้ายมาจากขั้นตอน "8) ทดสอบ 50 ข้อ" บน Colab — ใช้ชุดคำถามเดียวกันจาก dataset/test50.py)

ก่อนรัน: เปิดแอปไว้ก่อนในอีกหน้าต่าง/เทอร์มินัล
  cd .. && python run.py

แล้วรัน (เทอร์มินัลอีกอัน):
  python run_test50.py
"""
import datetime
import os
import secrets
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset")))
from test50 import TEST50  # noqa: E402

BASE_URL = os.environ.get("DSEE_APP_URL", "http://127.0.0.1:8000")
PIN = os.environ.get("APP_PIN", "")  # ใส่ให้ตรงกับที่ run.py แสดงไว้ ถ้าเปิด PIN


def main():
    headers = {"X-Device-Id": "selftest-" + secrets.token_hex(4), "X-App-Pin": PIN}
    out, cid = [], None
    for i, (cat, q, must) in enumerate(TEST50, 1):
        t0 = time.time()
        try:
            r = requests.post(
                f"{BASE_URL}/api/chat", json={"message": q, "conversation_id": cid},
                headers=headers, timeout=600,
            )
            cid = r.headers.get("X-Conversation-Id", cid)
            ans = r.text.replace("​", "").strip()
            if r.status_code != 200 or not ans or ans.startswith("⚠️"):
                status = "ตอบไม่ได้/error"
            else:
                status = "ตอบถูก" if (not must or any(m in ans for m in must)) else "ตอบผิด"
            route = r.headers.get("X-Route", "")
        except Exception as e:
            ans, status, route = f"{type(e).__name__}: {e}", "ตอบไม่ได้/error", ""
        sec = round(time.time() - t0, 1)
        out.append({
            "ข้อ": i, "หมวด": cat, "คำถาม": q, "ผล": status, "วิธีตอบ": route, "วินาที": sec,
            "คำที่ต้องมี": ", ".join(must), "คำตอบ": ans,
        })
        print(f"{i:02d} {status:<14} {route:<11} {sec:>6}s  {q[:50]}")

    df = pd.DataFrame(out)
    summary = df["ผล"].value_counts().reindex(["ตอบถูก", "ตอบผิด", "ตอบไม่ได้/error"], fill_value=0)
    print("\n===== สรุป =====")
    for k, v in summary.items():
        print(f"{k:<16} {v:>3} ข้อ ({v*2}%)")
    print("\nแยกตามหมวด:\n", pd.crosstab(df["หมวด"], df["ผล"]).to_string())
    print("\nเวลาเฉลี่ยต่อข้อ:", round(df["วินาที"].mean(), 1), "วินาที")

    out_dir = os.path.join(os.path.dirname(__file__), "work")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"test50_ผลทดสอบ_{datetime.datetime.now():%Y%m%d_%H%M}.xlsx")
    with pd.ExcelWriter(path) as xw:
        df.to_excel(xw, sheet_name="รายข้อ", index=False)
        summary.rename("จำนวนข้อ").to_frame().to_excel(xw, sheet_name="สรุป")
        pd.crosstab(df["หมวด"], df["ผล"]).to_excel(xw, sheet_name="แยกตามหมวด")
    print("\nบันทึกผล:", path)


if __name__ == "__main__":
    main()
