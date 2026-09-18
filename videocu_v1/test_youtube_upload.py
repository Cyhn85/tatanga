"""
VIDEOCU v1 - YouTube Upload Test
OAuth2 + YouTube Data API v3 video upload
"""

import sys
import logging
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from modules import YouTubeUploader

print("\n" + "="*70)
print("📺 VIDEOCU v1 - YOUTUBE UPLOAD TEST")
print("="*70)

# Check for OAuth credentials
client_secrets = Path("client_secrets.json")

if not client_secrets.exists():
    print("\n❌ client_secrets.json NOT FOUND")
    print("\n📋 SETUP INSTRUCTIONS:")
    print("="*70)
    print("\n1️⃣ Go to Google Cloud Console:")
    print("   https://console.cloud.google.com/")
    print("\n2️⃣ Select Project:")
    print("   - Select: 'kozmik oda' (or create new project)")
    print("\n3️⃣ Enable YouTube Data API v3:")
    print("   https://console.cloud.google.com/apis/library/youtube.googleapis.com")
    print("   - Click ENABLE")
    print("\n4️⃣ Create OAuth 2.0 Credentials:")
    print("   https://console.cloud.google.com/apis/credentials")
    print("   - Click: CREATE CREDENTIALS > OAuth client ID")
    print("   - Application type: Desktop app")
    print("   - Name: VIDEOCU v1")
    print("   - Click: CREATE")
    print("\n5️⃣ Download Credentials:")
    print("   - Click DOWNLOAD JSON button")
    print("   - Save as: client_secrets.json")
    print("   - Place in: c:\\Users\\cyhnsrgc\\Desktop\\CSS BOT\\videocu_v1\\")
    print("\n6️⃣ Configure OAuth Consent Screen:")
    print("   https://console.cloud.google.com/apis/credentials/consent")
    print("   - User Type: External")
    print("   - Add your email as test user")
    print("   - Scopes: YouTube Data API v3 > .../auth/youtube.upload")
    print("\n" + "="*70)
    print("\n⚠️ Cannot proceed without client_secrets.json")
    print("   Setup takes ~5 minutes")
    sys.exit(1)

print("✅ client_secrets.json found")

# Initialize uploader
print("\n🔐 Initializing YouTube API...")
print("   A browser window will open for authorization")
print("   Grant access to upload videos to your channel")

uploader = YouTubeUploader()

if not uploader.youtube:
    print("❌ YouTube API initialization failed")
    print("\n💡 Troubleshooting:")
    print("   - Check client_secrets.json format")
    print("   - Ensure YouTube Data API v3 is enabled")
    print("   - Add yourself as test user in OAuth consent screen")
    sys.exit(1)

print("✅ YouTube API authenticated!")

# Show API quota info
print("\n📊 YouTube API Quota Information:")
quota = uploader.get_upload_quota_usage()
print(f"   Daily Limit: {quota['daily_limit']:,} units")
print(f"   Upload Cost: {quota['upload_cost']:,} units per video")
print(f"   Max Daily Uploads: ~{quota['max_daily_uploads']} videos/day")
print(f"\n   💡 {quota['note']}")

# List recent videos on channel
print("\n📋 Your Recent Videos:")
videos = uploader.get_my_videos(max_results=5)

if videos:
    for i, video in enumerate(videos, 1):
        print(f"\n   {i}. {video['title'][:70]}")
        print(f"      ID: {video['video_id']}")
        print(f"      URL: https://www.youtube.com/watch?v={video['video_id']}")
        print(f"      Published: {video['published_at']}")
else:
    print("   No videos found on this channel")

# Check for test video to upload
test_video = Path("output/integration_test/final_video.mp4")

if test_video.exists():
    print(f"\n\n🎬 TEST VIDEO FOUND: {test_video}")
    print("   Ready to test upload!")
    print("\n⚠️ WARNING: This will upload a real video to your YouTube channel")
    print("   The video will be PUBLIC by default")
    print("\n   To test upload, uncomment the code below and run again:")
    print("""
    # Test upload
    upload_result = uploader.upload_video(
        video_path=str(test_video),
        title="VIDEOCU v1 Test Upload - KI 2025",
        description="Automated test upload from VIDEOCU v1 system",
        tags=["test", "ai", "automation"],
        category_id="28",  # Science & Technology
        privacy_status="private"  # Change to 'public' when ready
    )

    if upload_result:
        print(f"✅ Upload successful!")
        print(f"   Video ID: {upload_result['video_id']}")
        print(f"   URL: {upload_result['url']}")
    """)
else:
    print(f"\n⚠️ Test video not found: {test_video}")
    print("   Run: python test_full_pipeline.py first")

print("\n" + "="*70)
print("✅ YOUTUBE UPLOADER MODULE READY")
print("="*70)

print("\n🎯 Features Available:")
print("   1. upload_video() - Video yükleme")
print("   2. set_thumbnail() - Thumbnail ekleme")
print("   3. update_video() - Video bilgilerini güncelleme")
print("   4. delete_video() - Video silme")
print("   5. get_my_videos() - Kanal videolarını listeleme")
print("   6. OAuth2 authentication - Otomatik token yenileme")

print("\n📺 Next: Run test_full_pipeline.py to create uploadable video")
