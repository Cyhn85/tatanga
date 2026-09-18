"""
Quick test for YouTube API integration
"""

import sys
import logging

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from modules.trend_analyzer import TrendAnalyzer
import config

print("\n" + "="*60)
print("🧪 YOUTUBE API TEST")
print("="*60)

# Check if API key is configured
youtube_key = config.get_api_key("youtube")
if not youtube_key:
    print("❌ ERROR: YouTube API key not configured in .env")
    sys.exit(1)

print(f"✅ YouTube API key found: {youtube_key[:20]}...")

# Initialize TrendAnalyzer
print("\n🔄 Initializing TrendAnalyzer...")
analyzer = TrendAnalyzer(youtube_api_key=youtube_key)

# Test 1: Get trending videos from Germany
print("\n📊 TEST 1: Fetching trending videos from Germany...")
try:
    videos = analyzer.get_youtube_trending_videos(region_code='DE', max_results=5)

    if videos:
        print(f"✅ SUCCESS: Retrieved {len(videos)} trending videos")
        print("\nTop 3 Trending Videos:")
        for i, video in enumerate(videos[:3], 1):
            print(f"\n{i}. {video['title']}")
            print(f"   Channel: {video['channel']}")
            print(f"   Views: {video['views']:,}")
            print(f"   Likes: {video['likes']:,}")
            print(f"   URL: {video['url']}")
    else:
        print("⚠️ WARNING: No videos returned (might be API quota issue)")

except Exception as e:
    print(f"❌ ERROR: {e}")
    sys.exit(1)

# Test 2: Get trending by category (Gaming)
print("\n📊 TEST 2: Fetching Gaming category trending...")
try:
    gaming_videos = analyzer.get_youtube_trending_by_category(
        category_id='20',  # Gaming
        region_code='DE',
        max_results=3
    )

    if gaming_videos:
        print(f"✅ SUCCESS: Retrieved {len(gaming_videos)} gaming videos")
        print("\nTop Gaming Video:")
        video = gaming_videos[0]
        print(f"   {video['title']}")
        print(f"   Views: {video['views']:,}")
        print(f"   Score: {video['score']:,}")
    else:
        print("⚠️ WARNING: No gaming videos returned")

except Exception as e:
    print(f"❌ ERROR: {e}")

print("\n" + "="*60)
print("✅ YOUTUBE API TEST COMPLETE")
print("="*60)
