# -*- coding: utf-8 -*-
"""
เปิด DSEE Buddy ทั้งระบบในคำสั่งเดียว
  python run.py              -> เปิดเซิร์ฟเวอร์ + ลิงก์ trycloudflare สำหรับมือถือ (มี PIN กันคนอื่นใช้)
  python run.py --no-tunnel  -> ใช้เฉพาะในเครื่อง/วง Wi-Fi เดียวกัน
  python run.py --no-pin     -> ไม่ต้องใส่ PIN (ไม่แนะนำเมื่อเปิด tunnel)
"""
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def find_cloudflared():
    for name in ("cloudflared", "cloudflared.exe"):
        p = shutil.which(name)
        if p:
            return p
        local = os.path.join(ROOT, name)
        if os.path.exists(local):
            return local
    return None


def print_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        print("(ติดตั้ง qrcode ด้วย  pip install qrcode  เพื่อแสดง QR code ให้สแกนจากมือถือ)")


def keep_awake():
    """กันคอม (Windows) เข้าโหมดสลีประหว่างเปิดให้มือถือใช้ — สลีปแล้วลิงก์จะขึ้น HTTP 530/502"""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            print("💡 ตั้งค่าไม่ให้คอมสลีประหว่างเปิดโปรแกรมนี้แล้ว (หน้าจอดับได้ แต่เครื่องยังทำงาน)")
        except Exception:
            pass


def wait_server(timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    args = sys.argv[1:]
    use_tunnel = "--no-tunnel" not in args
    pin = os.environ.get("APP_PIN") or ("" if "--no-pin" in args else f"{secrets.randbelow(900000) + 100000}")
    env = dict(os.environ, APP_PIN=pin, PORT=str(PORT), PYTHONIOENCODING="utf-8")

    keep_awake()
    server_cmd = [sys.executable, os.path.join(ROOT, "backend", "server.py")]
    server = subprocess.Popen(server_cmd, env=env)
    procs = [server]
    if not wait_server():
        print("❌ เปิดเซิร์ฟเวอร์ไม่สำเร็จ ดูข้อความ error ด้านบน")
        server.terminate()
        return

    print("\n" + "=" * 60)
    print(f"✅ DSEE Buddy พร้อมแล้ว!")
    print(f"   ในเครื่องนี้ :  http://localhost:{PORT}")
    ip = lan_ip()
    if ip:
        print(f"   Wi-Fi เดียวกัน: http://{ip}:{PORT}")
    if pin:
        print(f"   🔑 PIN เข้าใช้งาน: {pin}")
    print("=" * 60)

    if use_tunnel:
        cf = find_cloudflared()
        if not cf:
            print("\n⚠️ ไม่พบ cloudflared — ติดตั้งก่อนเพื่อใช้บนมือถือผ่านอินเทอร์เน็ต:")
            print("   winget install --id Cloudflare.cloudflared")
            print("   (หรือดาวน์โหลด cloudflared-windows-amd64.exe มาวางในโฟลเดอร์นี้ แล้วเปลี่ยนชื่อเป็น cloudflared.exe)")
        else:
            print("\n🌐 กำลังเปิดลิงก์ trycloudflare สำหรับมือถือ…")
            tunnel = subprocess.Popen([cf, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                      encoding="utf-8", errors="ignore")
            procs.append(tunnel)

            def watch():
                shown = False
                for line in tunnel.stdout:
                    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                    if m and not shown:
                        shown = True
                        url = m.group(0)
                        print("\n" + "=" * 60)
                        print(f"📱 เปิดบนมือถือ: {url}")
                        if pin:
                            print(f"🔑 PIN: {pin}")
                        print("   (ลิงก์ใช้ได้จนกว่าจะปิดโปรแกรมนี้ · เปิดใหม่จะได้ลิงก์ใหม่)")
                        print("=" * 60)
                        print_qr(url)
            threading.Thread(target=watch, daemon=True).start()

            def tunnel_guard():
                tunnel.wait()
                print("\n⚠️ ลิงก์ trycloudflare หลุด (เน็ตหลุด/คอมสลีป) — ปิดหน้าต่างนี้แล้วเปิด start.bat ใหม่เพื่อรับลิงก์ใหม่")
            threading.Thread(target=tunnel_guard, daemon=True).start()

    print("\nกด Ctrl+C เพื่อปิดทั้งหมด\n")
    try:
        while True:                      # ถ้าเซิร์ฟเวอร์ล่ม -> เปิดใหม่อัตโนมัติ (ลิงก์มือถือ + PIN เดิมยังใช้ได้)
            code = procs[0].wait()
            print(f"\n⚠️ เซิร์ฟเวอร์หยุดทำงาน (code {code}) กำลังเปิดใหม่…")
            time.sleep(2)
            procs[0] = subprocess.Popen(server_cmd, env=env)
            if wait_server():
                print("✅ เซิร์ฟเวอร์กลับมาทำงานแล้ว")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        print("ปิดแล้ว 👋")


if __name__ == "__main__":
    main()
