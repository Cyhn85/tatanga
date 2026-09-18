#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Ana Baslangic Modulu
2. El Urun Arbitraj ve Satis Otomasyon Sistemi
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
TATANGA_ROOT = Path(__file__).parent

# Modul bilgileri
MODULES = {
    "T1": {
        "name": "Trend Hunter",
        "path": "T1_TREND_HUNTER/scanner.py",
        "description": "Trend urun tarama ve analiz"
    },
    "T2": {
        "name": "Price Scanner",
        "path": "T2_PRICE_SCANNER/vinted_scraper.py",
        "description": "Platform fiyat tarama"
    },
    "T3": {
        "name": "Arbitrage Engine",
        "path": "T3_ARBITRAGE_ENGINE/arbitrage.py",
        "description": "Arbitraj firsati bulma"
    },
    "T4": {
        "name": "Stock Manager",
        "path": "T4_STOCK_MANAGER/processor.py",
        "description": "Stoklu urun girisi"
    },
    "T5": {
        "name": "Image Processor",
        "path": "T5_IMAGE_PROCESSOR/processor.py",
        "description": "Resim isleme"
    },
    "T6": {
        "name": "Listing Engine",
        "path": "T6_LISTING_ENGINE/listing_generator.py",
        "description": "Ilan olusturma"
    },
    "bot": {
        "name": "Telegram Bot",
        "path": "telegram_bot/bot.py",
        "description": "Telegram bot"
    }
}

# ============================================
# HELPERS
# ============================================
def print_banner():
    """Banner goster"""
    banner = """
====================================================

  TATANGA - 2. El Urun Arbitraj ve Satis Sistemi

====================================================
    """
    print(banner)

def print_status():
    """Sistem durumunu goster"""
    print("\n" + "=" * 50)
    print("SISTEM DURUMU")
    print("=" * 50)

    for module_id, module in MODULES.items():
        module_path = TATANGA_ROOT / module["path"]
        status = "OK" if module_path.exists() else "EKSIK"
        print(f"  [{module_id}] {module['name']}: {status}")

    print("\n" + "=" * 50)

def run_module(module_id, args=[]):
    """Modul calistir"""
    if module_id not in MODULES:
        print(f"[-] Bilinmeyen modul: {module_id}")
        return

    module = MODULES[module_id]
    module_path = TATANGA_ROOT / module["path"]

    if not module_path.exists():
        print(f"[-] Modul bulunamadi: {module_path}")
        return

    print(f"\n[*] {module['name']} baslatiliyor...")
    print(f"    {module['description']}")
    print("-" * 40)

    # Python yorumlayici
    python_exe = TATANGA_ROOT / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = "python"

    # Calistir
    cmd = [str(python_exe), str(module_path)] + args
    subprocess.run(cmd)

def interactive_menu():
    """Interaktif menu"""
    while True:
        print("\n" + "=" * 50)
        print("TATANGA - ANA MENU")
        print("=" * 50)
        print("\n1. Trend Tarama (T1)")
        print("2. Fiyat Tarama (T2)")
        print("3. Arbitraj Analizi (T3)")
        print("4. Stok Girisi (T4)")
        print("5. Resim Isleme (T5)")
        print("6. Ilan Olusturma (T6)")
        print("7. Telegram Bot (bot)")
        print("8. Sistem Durumu")
        print("0. Cikis")
        print("")

        choice = input("Seciminiz: ").strip()

        if choice == "1":
            run_module("T1", ["--notify"])
        elif choice == "2":
            profile = input("Vinted Member ID (bos = varsayilan): ").strip()
            if profile:
                run_module("T2", [profile])
            else:
                run_module("T2")
        elif choice == "3":
            run_module("T3")
        elif choice == "4":
            run_module("T4")
        elif choice == "5":
            run_module("T5", ["--batch"])
        elif choice == "6":
            run_module("T6", ["--batch", "--telegram"])
        elif choice == "7":
            run_module("bot")
        elif choice == "8":
            print_status()
        elif choice == "0":
            print("\nGorüsmek üzere!")
            break
        else:
            print("Gecersiz secim!")

# ============================================
# MAIN
# ============================================
def main():
    parser = argparse.ArgumentParser(
        description='TATANGA - 2. El Urun Arbitraj ve Satis Otomasyon Sistemi'
    )
    parser.add_argument('--module', '-m', type=str, help='Modul calistir (T1, T2, T3, T4, T5, T6, bot)')
    parser.add_argument('--status', '-s', action='store_true', help='Sistem durumu')
    parser.add_argument('--menu', action='store_true', help='Interaktif menu')
    parser.add_argument('args', nargs='*', help='Modul argumanlari')

    args = parser.parse_args()

    print_banner()

    if args.status:
        print_status()

    elif args.module:
        run_module(args.module, args.args)

    elif args.menu:
        interactive_menu()

    else:
        # Varsayilan: Menu
        interactive_menu()

if __name__ == "__main__":
    main()
