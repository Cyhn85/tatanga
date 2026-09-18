#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA Hub - Masaustu Baslatici
System Tray'de calisir, sunucuyu otonom yonetir.
.pyw uzantisi konsol penceresi acmadan calisir.
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
import signal
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
APP_FILE = BASE_DIR / "app.py"
PYTHON = sys.executable
PORT = 8501
URL = f"http://localhost:{PORT}"

# Global
server_process = None
server_running = False


def check_port(port):
    """Port kullaniliyor mu kontrol et"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0


def start_server():
    """Uvicorn sunucusunu baslat"""
    global server_process, server_running

    if check_port(PORT):
        server_running = True
        print(f"[TATANGA] Sunucu zaten calisiyor: {URL}")
        return True

    try:
        server_process = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", str(PORT)],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )

        # Sunucunun baslamasini bekle
        for _ in range(30):
            time.sleep(1)
            if check_port(PORT):
                server_running = True
                print(f"[TATANGA] Sunucu baslatildi: {URL}")
                return True

        print("[TATANGA] Sunucu baslatilamadi!")
        return False

    except Exception as e:
        print(f"[TATANGA] Hata: {e}")
        return False


def stop_server():
    """Sunucuyu durdur"""
    global server_process, server_running

    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except:
            server_process.kill()
        server_process = None

    server_running = False
    print("[TATANGA] Sunucu durduruldu")


def open_browser():
    """Tarayicida dashboard'u ac"""
    webbrowser.open(URL)


def run_tray():
    """System tray ikonu ile calistir"""
    try:
        import pystray
        from PIL import Image

        # Logo'yu tray ikonu olarak kullan
        logo_path = BASE_DIR / "static" / "img" / "css_berlin_logo.png"
        if logo_path.exists():
            icon_image = Image.open(str(logo_path)).resize((64, 64))
        else:
            # Fallback: basit yesil ikon
            icon_image = Image.new('RGB', (64, 64), (45, 100, 45))

        def on_open(icon, item):
            open_browser()

        def on_restart(icon, item):
            stop_server()
            time.sleep(2)
            start_server()

        def on_quit(icon, item):
            stop_server()
            icon.stop()
            sys.exit(0)

        def get_status(item):
            return f"{'Calisiyor' if server_running else 'Durdu'} - Port {PORT}"

        menu = pystray.Menu(
            pystray.MenuItem("TATANGA Hub", None, enabled=False),
            pystray.MenuItem(lambda text: f"Durum: {'Aktif' if server_running else 'Kapalı'}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Dashboard'u Ac", on_open, default=True),
            pystray.MenuItem("Sunucuyu Yeniden Baslat", on_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Kapat", on_quit),
        )

        icon = pystray.Icon("tatanga_hub", icon_image, "TATANGA Hub", menu)

        # Sunucuyu arka planda baslat
        threading.Thread(target=start_server, daemon=True).start()

        # 3 sn sonra tarayiciyi ac
        def delayed_open():
            time.sleep(4)
            if server_running:
                open_browser()
        threading.Thread(target=delayed_open, daemon=True).start()

        print("[TATANGA] System tray baslatildi")
        icon.run()

    except ImportError:
        # pystray yoksa sadece sunucu + tarayici ac
        print("[TATANGA] pystray bulunamadi, basit modda calistiriliyor...")
        run_simple()


def run_simple():
    """System tray olmadan basit mod"""
    print(f"""
    ╔══════════════════════════════════════════════╗
    ║        TATANGA T11_HUB - Komuta Merkezi      ║
    ║        {URL:<38} ║
    ║                                              ║
    ║   Kapatmak icin: Ctrl+C                      ║
    ╚══════════════════════════════════════════════╝
    """)

    if not start_server():
        print("[HATA] Sunucu baslatilamadi!")
        input("Devam etmek icin Enter'a basin...")
        sys.exit(1)

    # Tarayiciyi ac
    time.sleep(2)
    open_browser()

    # Ctrl+C ile kapatilana kadar bekle
    try:
        while True:
            time.sleep(1)
            if server_process and server_process.poll() is not None:
                print("[TATANGA] Sunucu kapandi, yeniden baslatiliyor...")
                start_server()
    except KeyboardInterrupt:
        print("\n[TATANGA] Kapatiliyor...")
        stop_server()


if __name__ == "__main__":
    run_tray()
