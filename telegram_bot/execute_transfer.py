#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Execute Transfer
Kleinanzeigen'den Vinted'e direkt transfer
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from store_transfer_handler import StoreTransferHandler
from shared.config.credentials import KLEINANZEIGEN, VINTED, TELEGRAM

def main():
    print("=" * 60)
    print("TATANGA - DIREKT TRANSFER")
    print("=" * 60)
    print()

    source_email = KLEINANZEIGEN['accounts'][0]['email']
    target_email = VINTED['accounts'][0]['email']
    chat_id = TELEGRAM['channels']['store_transfer']

    print(f"Kaynak: Kleinanzeigen ({source_email})")
    print(f"Hedef: Vinted ({target_email})")
    print(f"Telegram grubu: {chat_id}")
    print()
    print("Transfer baslatiliyor...")
    print()

    print("[DEBUG] Handler olusturuluyor...")
    handler = StoreTransferHandler()
    print("[DEBUG] Handler olusturuldu, transfer baslatiliyor...")
    handler.execute_transfer(source_email, 'vinted', target_email, chat_id)
    print("[DEBUG] Transfer fonksiyonu tamamlandi")

    print()
    print("=" * 60)
    print("TRANSFER TAMAMLANDI")
    print("=" * 60)

if __name__ == "__main__":
    main()
