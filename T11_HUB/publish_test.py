import sqlite3
import requests
import json
import os

DB_PATH = os.path.join("data", "hub.db")
API_URL = "http://127.0.0.1:8501/api/product/{}/publish"

def publish_test_batch():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = """
        SELECT id, title, source_platform
        FROM products 
        WHERE recommendation='buy' 
          AND condition_score>=3 
          AND gpsr_ready=1 
          AND LOWER(title) LIKE '%jacke%'
          AND status != 'published'
        LIMIT 30;
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if not rows:
        print("No products found matching criteria.")
        return
        
    print(f"Found {len(rows)} products to publish. Starting dry-run... (Wait, the script will actually publish them to the API since the instruction was 'test amacli yayinlanacak')")
    
    success_count = 0
    fail_count = 0
    
    for row in rows:
        prod_id, title, platform = row
        print(f"Publishing {prod_id} ({platform}): {title[:40]}...")
        
        try:
            payload = {
                "target": "cssberlin",
                "category_slug": "jacken & mäntel (herren)"
            }
            resp = requests.post(API_URL.format(prod_id), json=payload, timeout=60)
            if resp.status_code == 200:
                print(f"  -> SUCCESS: {resp.json()}")
                success_count += 1
            else:
                print(f"  -> FAILED: [{resp.status_code}] {resp.text}")
                fail_count += 1
        except Exception as e:
            print(f"  -> ERROR: {e}")
            fail_count += 1
            
    print(f"\nPublishing complete. Success: {success_count}, Failed: {fail_count}")

if __name__ == "__main__":
    publish_test_batch()
