"""
VIDEOCU v1 - Pixabay Music Provider
Royalty-free background music from Pixabay API

FREE API: https://pixabay.com/api/docs/
- 5000 requests/hour
- Royalty-free music
- No attribution required
- Multiple genres & moods
"""

import os
import logging
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class PixabayMusicProvider:
    """
    Pixabay API provider for royalty-free background music
    """

    # Mood to music category mapping
    MOOD_MAPPING = {
        # Positive moods
        'happy': 'happyinspirational',
        'upbeat': 'happyinspirational',
        'energetic': 'happyinspirational',
        'inspiring': 'happyinspirational',
        'motivational': 'happyinspirational',
        'cheerful': 'happyinspirational',

        # Calm moods
        'calm': 'calm',
        'relaxing': 'calm',
        'peaceful': 'calm',
        'ambient': 'calm',
        'meditation': 'calm',
        'chill': 'calm',

        # Dramatic moods
        'dramatic': 'dramatic',
        'epic': 'dramatic',
        'cinematic': 'dramatic',
        'intense': 'dramatic',
        'powerful': 'dramatic',

        # Dark moods
        'dark': 'dark',
        'mysterious': 'dark',
        'suspenseful': 'dark',
        'horror': 'dark',

        # Sad moods
        'sad': 'sad',
        'melancholic': 'sad',
        'emotional': 'sad',

        # Funny moods
        'funny': 'funny',
        'comedy': 'funny',
        'quirky': 'funny',

        # Romantic moods
        'romantic': 'romantic',
        'love': 'romantic',

        # Corporate/Tech moods
        'corporate': 'corporate',
        'business': 'corporate',
        'technology': 'corporate',
        'tech': 'corporate',
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Pixabay API key (get from https://pixabay.com/api/docs/)
        """
        self.api_key = api_key or os.getenv('PIXABAY_API_KEY', '')

        if not self.api_key:
            logger.warning("⚠️ Pixabay API key not provided. Provider will be unavailable.")
            self.enabled = False
        else:
            self.enabled = True

        self.base_url = "https://pixabay.com/api/"

        # Rate limiting
        self.rate_limit = 5000  # requests per hour
        self.requests_made = 0
        self.rate_limit_reset = time.time() + 3600

        # Cache directory
        self.cache_dir = Path("output/cache/pixabay_music")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"🎵 Pixabay Music Provider initialized (enabled: {self.enabled})")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        current_time = time.time()

        # Reset counter if hour has passed
        if current_time >= self.rate_limit_reset:
            self.requests_made = 0
            self.rate_limit_reset = current_time + 3600

        if self.requests_made >= self.rate_limit:
            logger.warning(f"⚠️ Pixabay rate limit reached ({self.rate_limit}/hour)")
            return False

        return True

    def _make_request(self, params: Dict) -> Optional[Dict]:
        """
        Make authenticated request to Pixabay API

        Args:
            params: Query parameters

        Returns:
            JSON response or None if failed
        """
        if not self.enabled:
            return None

        if not self._check_rate_limit():
            return None

        # Add API key to params
        params['key'] = self.api_key

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            self.requests_made += 1

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("⚠️ Pixabay rate limit hit")
                return None
            else:
                logger.error(f"❌ Pixabay API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Pixabay request failed: {e}")
            return None

    def search_music(self,
                    query: str = "",
                    mood: str = "",
                    per_page: int = 20,
                    min_duration: int = 30,
                    max_duration: int = 180) -> List[Dict]:
        """
        Search for music on Pixabay

        Args:
            query: Search query (optional)
            mood: Mood/category (happy, calm, dramatic, etc.)
            per_page: Number of results (max 200)
            min_duration: Minimum duration in seconds
            max_duration: Maximum duration in seconds

        Returns:
            List of music objects with URLs and metadata
        """
        if not self.enabled:
            return []

        # Map mood to Pixabay category
        category = ""
        if mood:
            mood_lower = mood.lower()
            category = self.MOOD_MAPPING.get(mood_lower, "")

        params = {
            'audio_type': 'music',
            'per_page': min(per_page, 200),
        }

        if query:
            params['q'] = query

        if category:
            params['category'] = category

        logger.info(f"🔍 Searching Pixabay music: query='{query}', mood='{mood}', category='{category}'")

        response = self._make_request(params)

        if not response or 'hits' not in response:
            return []

        music_list = []
        for track in response['hits']:
            # Filter by duration
            duration = track.get('duration', 0)
            if duration < min_duration or duration > max_duration:
                continue

            # Get preview and download URLs
            preview_url = track.get('previewURL', '')
            download_url = ''

            # Pixabay provides different quality downloads
            downloads = track.get('downloads', {})
            if downloads:
                # Prefer high quality MP3
                download_url = downloads.get('mp3', {}).get('url', '')

            if not download_url:
                # Fallback to preview URL
                download_url = preview_url

            music_list.append({
                'id': track['id'],
                'name': track.get('name', f"Track {track['id']}"),
                'tags': track.get('tags', ''),
                'duration': duration,
                'bpm': track.get('bpm', 0),
                'preview_url': preview_url,
                'download_url': download_url,
                'user': track.get('user', 'Unknown'),
                'user_id': track.get('user_id', 0)
            })

        logger.info(f"✅ Found {len(music_list)} Pixabay music tracks")
        return music_list

    def download_music(self, track: Dict, output_path: str) -> bool:
        """
        Download a music track from Pixabay

        Args:
            track: Track object from search_music()
            output_path: Path to save the audio file

        Returns:
            True if successful, False otherwise
        """
        try:
            url = track.get('download_url', track.get('preview_url', ''))

            if not url:
                logger.error("❌ No download URL available")
                return False

            logger.info(f"⬇️ Downloading Pixabay music: {track['name']} ({track['duration']}s)")

            response = requests.get(url, timeout=60, stream=True)
            if response.status_code == 200:
                # Create output directory
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                file_size = Path(output_path).stat().st_size / 1024  # KB
                logger.info(f"✅ Downloaded: {output_path} ({file_size:.1f} KB)")
                return True
            else:
                logger.error(f"❌ Download failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Download error: {e}")
            return False

    def get_music_for_topic(self,
                           topic: str,
                           duration_seconds: int = 60,
                           output_path: Optional[str] = None) -> Optional[str]:
        """
        Get best music track for a video topic/mood and download it

        Args:
            topic: Video topic or mood description
            duration_seconds: Desired duration (will find close match)
            output_path: Path to save (auto-generated if None)

        Returns:
            Path to downloaded file or None if failed
        """
        # Auto-detect mood from topic
        mood = self._detect_mood_from_topic(topic)

        logger.info(f"🎵 Getting music for topic: '{topic}' → mood: '{mood}'")

        # Search with flexible duration range
        min_dur = max(30, duration_seconds - 30)
        max_dur = duration_seconds + 60

        tracks = self.search_music(
            query="",
            mood=mood,
            per_page=10,
            min_duration=min_dur,
            max_duration=max_dur
        )

        if not tracks:
            logger.warning(f"⚠️ No music found for topic: {topic}")
            return None

        # Find track with closest duration match
        best_track = min(tracks, key=lambda t: abs(t['duration'] - duration_seconds))

        # Generate output path if not provided
        if not output_path:
            output_path = str(self.cache_dir / f"music_{best_track['id']}.mp3")

        # Download track
        success = self.download_music(best_track, output_path)

        if success:
            logger.info(f"✅ Music selected: '{best_track['name']}' ({best_track['duration']}s)")
            return output_path
        else:
            return None

    def _detect_mood_from_topic(self, topic: str) -> str:
        """
        Auto-detect mood from video topic

        Args:
            topic: Video topic/title

        Returns:
            Detected mood category
        """
        topic_lower = topic.lower()

        # Check for mood keywords in topic
        for mood, category in self.MOOD_MAPPING.items():
            if mood in topic_lower:
                return mood

        # Topic-based detection
        if any(word in topic_lower for word in ['news', 'facts', 'science', 'technology', 'ai', 'tech']):
            return 'corporate'
        elif any(word in topic_lower for word in ['success', 'motivation', 'inspire', 'achieve']):
            return 'inspiring'
        elif any(word in topic_lower for word in ['relax', 'sleep', 'meditation', 'calm']):
            return 'calm'
        elif any(word in topic_lower for word in ['action', 'adventure', 'epic', 'battle']):
            return 'dramatic'
        elif any(word in topic_lower for word in ['mystery', 'crime', 'thriller']):
            return 'mysterious'
        elif any(word in topic_lower for word in ['happy', 'fun', 'joy', 'celebration']):
            return 'happy'
        elif any(word in topic_lower for word in ['sad', 'tragic', 'loss']):
            return 'sad'
        else:
            # Default to upbeat for general content
            return 'upbeat'

    def get_status(self) -> Dict:
        """Get provider status and stats"""
        return {
            'provider': 'pixabay_music',
            'enabled': self.enabled,
            'rate_limit': f"{self.requests_made}/{self.rate_limit}",
            'api_key_present': bool(self.api_key),
            'supported_moods': list(set(self.MOOD_MAPPING.values())),
            'cache_dir': str(self.cache_dir)
        }


# Test
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    # Load .env
    load_dotenv()

    # Set UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎵 PIXABAY MUSIC PROVIDER TEST")
    print("="*70)

    provider = PixabayMusicProvider()

    print("\n📊 Status:")
    status = provider.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")

    if not provider.enabled:
        print("\n⚠️ Pixabay API key not found!")
        print("   Set PIXABAY_API_KEY in .env or get one at:")
        print("   https://pixabay.com/api/docs/")
        sys.exit(1)

    # Test 1: Search music by mood
    print("\n" + "="*70)
    print("TEST 1: Search Music by Mood")
    print("="*70)

    moods_to_test = ['upbeat', 'calm', 'dramatic']

    for mood in moods_to_test:
        print(f"\n🎵 Searching for '{mood}' music...")
        tracks = provider.search_music(mood=mood, per_page=3)

        print(f"   Found {len(tracks)} tracks:")
        for i, track in enumerate(tracks, 1):
            print(f"\n   {i}. {track['name']}")
            print(f"      Duration: {track['duration']}s")
            print(f"      BPM: {track['bpm']}")
            print(f"      Tags: {track['tags']}")

    # Test 2: Auto-detect mood from topic
    print("\n" + "="*70)
    print("TEST 2: Auto-Detect Mood from Topic")
    print("="*70)

    test_topics = [
        "Top 10 AI Technologies in 2025",
        "Relaxing Nature Sounds for Sleep",
        "Epic Movie Trailer Moments",
        "Funny Cat Compilation"
    ]

    for topic in test_topics:
        mood = provider._detect_mood_from_topic(topic)
        print(f"\n   📝 Topic: '{topic}'")
        print(f"   🎵 Detected Mood: {mood}")

    # Test 3: Get music for topic
    print("\n" + "="*70)
    print("TEST 3: Get Music for Topic & Download")
    print("="*70)

    test_topic = "AI Technology Explained"
    output_file = provider.get_music_for_topic(
        topic=test_topic,
        duration_seconds=60
    )

    if output_file:
        print(f"\n✅ Music downloaded for topic: '{test_topic}'")
        print(f"   File: {output_file}")

        # Check file exists
        if Path(output_file).exists():
            file_size = Path(output_file).stat().st_size / 1024
            print(f"   Size: {file_size:.1f} KB")
    else:
        print(f"\n❌ Failed to get music for topic: '{test_topic}'")

    print("\n" + "="*70)
    print("✅ PIXABAY MUSIC PROVIDER TEST COMPLETE")
    print("="*70)
    print(f"\n📊 API Usage: {provider.requests_made}/{provider.rate_limit} requests")
    print("\n💡 Benefits:")
    print("   • 5000 requests/hour (vs Pexels 200/hour)")
    print("   • Royalty-free music")
    print("   • No attribution required")
    print("   • Auto mood detection from video topic")
    print("\n")
