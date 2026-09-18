#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vinted Upload Form Analizi - Form elementlerini tespit et
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import VINTED
from store_transfer_handler import StoreTransferHandler

def analyze_upload_form():
    """Vinted urun ekleme formunu analiz et"""
    print("=" * 60)
    print("VINTED UPLOAD FORM ANALIZI")
    print("=" * 60)

    handler = StoreTransferHandler()
    account = VINTED['accounts'][0]

    # Login
    print("\nLogin yapiliyor...")
    if not handler.login_to_vinted(account):
        print("Login basarisiz!")
        return False

    print("Login basarili!")
    time.sleep(2)

    # Urun ekleme sayfasina git
    print("\nUrun ekleme sayfasina gidiliyor...")
    handler.driver.get("https://www.vinted.de/items/new")
    time.sleep(5)

    # Screenshot al
    screenshot_path = Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp" / "vinted_upload_form.png"
    handler.driver.save_screenshot(str(screenshot_path))
    print(f"Screenshot: {screenshot_path}")

    # Form elementlerini analiz et
    print("\n" + "=" * 60)
    print("FORM ELEMENTLERI ANALIZI")
    print("=" * 60)

    # Input elementleri
    print("\n--- INPUT ELEMENTLERI ---")
    inputs = handler.driver.find_elements("css selector", "input")
    for i, inp in enumerate(inputs[:20]):
        try:
            name = inp.get_attribute("name") or ""
            type_ = inp.get_attribute("type") or ""
            placeholder = inp.get_attribute("placeholder") or ""
            testid = inp.get_attribute("data-testid") or ""
            visible = inp.is_displayed()
            if visible and (name or placeholder or testid):
                print(f"  {i+1}. name='{name}' type='{type_}' placeholder='{placeholder[:30]}' testid='{testid}'")
        except:
            pass

    # Textarea elementleri
    print("\n--- TEXTAREA ELEMENTLERI ---")
    textareas = handler.driver.find_elements("css selector", "textarea")
    for i, ta in enumerate(textareas):
        try:
            name = ta.get_attribute("name") or ""
            placeholder = ta.get_attribute("placeholder") or ""
            testid = ta.get_attribute("data-testid") or ""
            visible = ta.is_displayed()
            if visible:
                print(f"  {i+1}. name='{name}' placeholder='{placeholder[:30]}' testid='{testid}'")
        except:
            pass

    # Button elementleri
    print("\n--- BUTTON ELEMENTLERI ---")
    buttons = handler.driver.find_elements("css selector", "button")
    for i, btn in enumerate(buttons[:15]):
        try:
            text = btn.text.strip()[:30]
            type_ = btn.get_attribute("type") or ""
            testid = btn.get_attribute("data-testid") or ""
            visible = btn.is_displayed()
            if visible and text:
                print(f"  {i+1}. text='{text}' type='{type_}' testid='{testid}'")
        except:
            pass

    # data-testid iceren elementler
    print("\n--- DATA-TESTID ELEMENTLERI ---")
    testid_elements = handler.driver.find_elements("css selector", "[data-testid]")
    for i, elem in enumerate(testid_elements[:30]):
        try:
            testid = elem.get_attribute("data-testid") or ""
            tag = elem.tag_name
            visible = elem.is_displayed()
            if visible and testid:
                print(f"  {i+1}. <{tag}> testid='{testid}'")
        except:
            pass

    # File input (resim yukleme)
    print("\n--- FILE INPUT ---")
    file_inputs = handler.driver.find_elements("css selector", "input[type='file']")
    for i, fi in enumerate(file_inputs):
        try:
            name = fi.get_attribute("name") or ""
            accept = fi.get_attribute("accept") or ""
            multiple = fi.get_attribute("multiple")
            print(f"  {i+1}. name='{name}' accept='{accept}' multiple={multiple}")
        except:
            pass

    # Clickable alanlar (kategori, durum vb)
    print("\n--- SELECT/DROPDOWN ELEMENTLERI ---")
    selects = handler.driver.find_elements("css selector", "select, [role='listbox'], [role='combobox']")
    for i, sel in enumerate(selects):
        try:
            name = sel.get_attribute("name") or ""
            testid = sel.get_attribute("data-testid") or ""
            role = sel.get_attribute("role") or ""
            visible = sel.is_displayed()
            if visible:
                print(f"  {i+1}. name='{name}' testid='{testid}' role='{role}'")
        except:
            pass

    print("\n" + "=" * 60)
    print("Analiz tamamlandi!")
    print("=" * 60)

    # Driver kapat
    try:
        handler.driver.quit()
    except:
        pass

    return True

if __name__ == "__main__":
    analyze_upload_form()
