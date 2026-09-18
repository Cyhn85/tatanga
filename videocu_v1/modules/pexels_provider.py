"""
VIDEOCU v1 - Pexels Provider
High-quality stock photos and videos from Pexels API

FREE API: https://www.pexels.com/api/
- 200 requests/hour
- HD/4K images
- HD/4K video clips
- No attribution required for most content
"""

import os
import logging
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class PexelsProvider:
    """
    Pexels API provider for high-quality images and videos
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Pexels API key (get from https://www.pexels.com/api/)
        """
        self.api_key = api_key or os.getenv('PEXELS_API_KEY', '')

        if not self.api_key:
            logger.warning("⚠️ Pexels API key not provided. Provider will be unavailable.")
            self.enabled = False
        else:
            self.enabled = True

        self.base_url = "https://api.pexels.com/v1"
        self.video_base_url = "https://api.pexels.com/videos"

        # Rate limiting
        self.rate_limit = 200  # requests per hour
        self.requests_made = 0
        self.rate_limit_reset = time.time() + 3600

        # Cache directory
        self.cache_dir = Path("output/cache/pexels")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"🖼️ Pexels Provider initialized (enabled: {self.enabled})")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        current_time = time.time()

        # Reset counter if hour has passed
        if current_time >= self.rate_limit_reset:
            self.requests_made = 0
            self.rate_limit_reset = current_time + 3600

        if self.requests_made >= self.rate_limit:
            logger.warning(f"⚠️ Pexels rate limit reached ({self.rate_limit}/hour)")
            return False

        return True

    def _make_request(self, url: str, params: Dict = None) -> Optional[Dict]:
        """
        Make authenticated request to Pexels API

        Args:
            url: API endpoint URL
            params: Query parameters

        Returns:
            JSON response or None if failed
        """
        if not self.enabled:
            return None

        if not self._check_rate_limit():
            return None

        headers = {
            'Authorization': self.api_key
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            self.requests_made += 1

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("⚠️ Pexels rate limit hit")
                return None
            else:
                logger.error(f"❌ Pexels API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Pexels request failed: {e}")
            return None

    def search_photos(self,
                     query: str,
                     per_page: int = 15,
                     orientation: str = "landscape",
                     size: str = "large") -> List[Dict]:
        """
        Search for photos on Pexels

        Args:
            query: Search query
            per_page: Number of results (1-80)
            orientation: landscape, portrait, or square
            size: large, medium, small

        Returns:
            List of photo objects with URLs
        """
        if not self.enabled:
            return []

        url = f"{self.base_url}/search"
        params = {
            'query': query,
            'per_page': min(per_page, 80),
            'orientation': orientation
        }

        logger.info(f"🔍 Searching Pexels photos: '{query}'")

        response = self._make_request(url, params)

        if not response or 'photos' not in response:
            return []

        photos = []
        for photo in response['photos']:
            photos.append({
                'id': photo['id'],
                'width': photo['width'],
                'height': photo['height'],
                'url': photo['src'].get(size, photo['src']['large']),
                'url_original': photo['src']['original'],
                'url_large2x': photo['src'].get('large2x', photo['src']['large']),
                'photographer': photo['photographer'],
                'photographer_url': photo['photographer_url'],
                'alt': photo.get('alt', query)
            })

        logger.info(f"✅ Found {len(photos)} Pexels photos")
        return photos

    def search_videos(self,
                     query: str,
                     per_page: int = 10,
                     orientation: str = "landscape",
                     min_duration: int = 5,
                     max_duration: int = 30) -> List[Dict]:
        """
        Search for videos on Pexels

        Args:
            query: Search query
            per_page: Number of results (1-80)
            orientation: landscape, portrait, or square
            min_duration: Minimum duration in seconds
            max_duration: Maximum duration in seconds

        Returns:
            List of video objects with URLs
        """
        if not self.enabled:
            return []

        url = f"{self.video_base_url}/search"
        params = {
            'query': query,
            'per_page': min(per_page, 80),
            'orientation': orientation
        }

        logger.info(f"🔍 Searching Pexels videos: '{query}'")

        response = self._make_request(url, params)

        if not response or 'videos' not in response:
            return []

        videos = []
        for video in response['videos']:
            # Filter by duration
            duration = video.get('duration', 0)
            if duration < min_duration or duration > max_duration:
                continue

            # Get best quality video file
            video_files = video.get('video_files', [])
            if not video_files:
                continue

            # Sort by quality (width * height)
            video_files.sort(
                key=lambda x: x.get('width', 0) * x.get('height', 0),
                reverse=True
            )

            # Prefer HD (1920x1080) or best available
            hd_file = None
            for vf in video_files:
                if vf.get('width') == 1920 and vf.get('height') == 1080:
                    hd_file = vf
                    break

            best_file = hd_file or video_files[0]

            videos.append({
                'id': video['id'],
                'width': best_file['width'],
                'height': best_file['height'],
                'duration': duration,
                'url': best_file['link'],
                'file_type': best_file.get('file_type', 'video/mp4'),
                'quality': best_file.get('quality', 'hd'),
                'fps': video.get('fps', 30),
                'user': video['user']['name'],
                'user_url': video['user']['url']
            })

        logger.info(f"✅ Found {len(videos)} Pexels videos")
        return videos

    def download_photo(self, photo: Dict, output_path: str) -> bool:
        """
        Download a photo from Pexels

        Args:
            photo: Photo object from search_photos()
            output_path: Path to save the image

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use large2x for best quality, fallback to url
            url = photo.get('url_large2x', photo.get('url'))

            logger.info(f"⬇️ Downloading Pexels photo {photo['id']}")

            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.content)

                logger.info(f"✅ Downloaded: {output_path}")
                return True
            else:
                logger.error(f"❌ Download failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Download error: {e}")
            return False

    def download_video(self, video: Dict, output_path: str) -> bool:
        """
        Download a video from Pexels

        Args:
            video: Video object from search_videos()
            output_path: Path to save the video

        Returns:
            True if successful, False otherwise
        """
        try:
            url = video['url']

            logger.info(f"⬇️ Downloading Pexels video {video['id']} ({video['duration']}s)")

            response = requests.get(url, timeout=60, stream=True)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                logger.info(f"✅ Downloaded: {output_path}")
                return True
            else:
                logger.error(f"❌ Download failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Download error: {e}")
            return False

    def get_photo_for_scene(self,
                           scene_description: str,
                           output_path: str,
                           orientation: str = "landscape",
                           max_retries: int = 2) -> bool:
        """
        Get best photo for a scene description and download it

        Args:
            scene_description: Description of the scene
            output_path: Path to save the image
            orientation: landscape, portrait, or square
            max_retries: Number of retry attempts with simplified query

        Returns:
            True if successful, False otherwise
        """
        # Extract keywords from scene description
        keywords = scene_description.lower()

        # Remove common words
        stop_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for']
        query_words = [w for w in keywords.split() if w not in stop_words]

        # Try with decreasing number of keywords
        for attempt in range(max_retries + 1):
            # Use fewer keywords on each retry
            num_keywords = max(1, 5 - attempt)
            query = ' '.join(query_words[:num_keywords])

            if not query:
                query = "abstract background"

            logger.info(f"🎨 Getting photo for: '{scene_description[:50]}' → query: '{query}' (attempt {attempt + 1})")

            photos = self.search_photos(query=query, per_page=5, orientation=orientation)

            if photos:
                # Download first (best) photo
                if self.download_photo(photos[0], output_path):
                    return True

            if attempt < max_retries:
                logger.info(f"   ⚠️ No photos found, retrying with simpler query...")

        logger.warning(f"⚠️ No photos found after {max_retries + 1} attempts")
        return False

    def get_video_for_scene(self,
                           scene_description: str,
                           output_path: str,
                           duration: int = 5) -> bool:
        """
        Get best video clip for a scene and download it

        Args:
            scene_description: Description of the scene
            output_path: Path to save the video
            duration: Desired duration in seconds

        Returns:
            True if successful, False otherwise
        """
        # Extract keywords
        keywords = scene_description.lower()
        stop_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for']
        query_words = [w for w in keywords.split() if w not in stop_words]
        query = ' '.join(query_words[:5])

        logger.info(f"🎬 Getting video for: '{scene_description}' → query: '{query}'")

        videos = self.search_videos(
            query=query,
            per_page=5,
            min_duration=duration - 2,
            max_duration=duration + 5
        )

        if not videos:
            logger.warning(f"⚠️ No videos found for: {query}")
            return False

        # Download first (best) video
        return self.download_video(videos[0], output_path)

    def get_status(self) -> Dict:
        """Get provider status and stats"""
        return {
            'provider': 'pexels',
            'enabled': self.enabled,
            'rate_limit': f"{self.requests_made}/{self.rate_limit}",
            'api_key_present': bool(self.api_key),
            'endpoints': {
                'photos': f"{self.base_url}/search",
                'videos': f"{self.video_base_url}/search"
            }
        }


# Test
if __name__ == "__main__":
    import sys

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
    print("🖼️ PEXELS PROVIDER TEST")
    print("="*70)

    provider = PexelsProvider()

    print("\n📊 Status:")
    status = provider.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")

    if not provider.enabled:
        print("\n⚠️ Pexels API key not found!")
        print("   Set PEXELS_API_KEY in .env or get one at:")
        print("   https://www.pexels.com/api/")
        sys.exit(1)

    # Test photo search
    print("\n" + "="*70)
    print("TEST 1: Photo Search")
    print("="*70)

    photos = provider.search_photos("artificial intelligence technology", per_page=3)
    print(f"\n📸 Found {len(photos)} photos:")
    for i, photo in enumerate(photos, 1):
        print(f"\n   {i}. Photo ID: {photo['id']}")
        print(f"      Size: {photo['width']}x{photo['height']}")
        print(f"      Photographer: {photo['photographer']}")
        print(f"      URL: {photo['url'][:60]}...")

    # Test video search
    print("\n" + "="*70)
    print("TEST 2: Video Search")
    print("="*70)

    videos = provider.search_videos("technology computers", per_page=3)
    print(f"\n🎬 Found {len(videos)} videos:")
    for i, video in enumerate(videos, 1):
        print(f"\n   {i}. Video ID: {video['id']}")
        print(f"      Size: {video['width']}x{video['height']}")
        print(f"      Duration: {video['duration']}s")
        print(f"      Quality: {video['quality']}")
        print(f"      User: {video['user']}")

    # Test download
    if photos:
        print("\n" + "="*70)
        print("TEST 3: Download Photo")
        print("="*70)

        test_output = "output/cache/pexels/test_photo.jpg"
        success = provider.download_photo(photos[0], test_output)

        if success:
            print(f"✅ Photo downloaded to: {test_output}")
        else:
            print("❌ Photo download failed")

    print("\n" + "="*70)
    print("✅ PEXELS PROVIDER TEST COMPLETE")
    print("="*70)
    print(f"\n📊 API Usage: {provider.requests_made}/{provider.rate_limit} requests")
    print("\n")
