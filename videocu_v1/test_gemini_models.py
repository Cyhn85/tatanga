"""
Test Gemini API and list available models
"""

import google.generativeai as genai
import os
import sys
from dotenv import load_dotenv

# Set UTF-8 encoding
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
print(f"API Key: {api_key[:20]}...")

try:
    genai.configure(api_key=api_key)
    print("\n[OK] API configured successfully")

    print("\n[LIST] Listing available models...")
    for model in genai.list_models():
        if 'generateContent' in model.supported_generation_methods:
            print(f"   - {model.name}")
            print(f"     Display: {model.display_name}")
            print(f"     Methods: {model.supported_generation_methods}")
            print()

except Exception as e:
    print(f"\n[ERROR] Error: {e}")
    print("\n[SOLUTION]:")
    print("   1. Go to: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com")
    print("   2. Select project: kozmik oda")
    print("   3. Click 'ENABLE'")
