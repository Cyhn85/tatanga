"""
VIDEOCU v1 - Unsplash Provider
High-quality stock photos from Unsplash API (FREE)

FREE API: https://unsplash.com/developers
- 50 requests/hour (demo)
- HD images
- Creative Commons Zero (CC0) - free to use
"""

import os
import logging
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional
import re

logger = logging.getLogger(__name__)


class UnsplashProvider:
    """
    Unsplash API provider for high-quality free images
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Unsplash Access Key (get from https://unsplash.com/developers)
                    If not provided, uses demo mode (limited)
        """
        self.api_key = api_key or os.getenv('UNSPLASH_API_KEY', '')

        if not self.api_key:
            logger.warning("⚠️ Unsplash API key not provided. Using demo mode (limited).")
            self.enabled = True  # Demo mode still works
            self.demo_mode = True
        else:
            self.enabled = True
            self.demo_mode = False

        self.base_url = "https://api.unsplash.com"

        # Rate limiting
        self.rate_limit = 50  # requests per hour
        self.requests_made = 0
        self.rate_limit_reset = time.time() + 3600

        # Cache directory
        self.cache_dir = Path("output/cache/unsplash")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"📷 Unsplash Provider initialized (demo: {self.demo_mode})")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        current_time = time.time()

        # Reset counter if hour has passed
        if current_time >= self.rate_limit_reset:
            self.requests_made = 0
            self.rate_limit_reset = current_time + 3600

        if self.requests_made >= self.rate_limit:
            logger.warning(f"⚠️ Unsplash rate limit reached ({self.rate_limit}/hour)")
            return False

        return True

    def _make_request(self, url: str, params: Dict = None) -> Optional[Dict]:
        """
        Make request to Unsplash API

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
            'Authorization': f'Client-ID {self.api_key}' if self.api_key else None
        }

        # Remove None header if no API key
        if not self.api_key:
            headers = {}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            self.requests_made += 1

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                logger.warning("⚠️ Unsplash rate limit hit")
                return None
            else:
                logger.error(f"❌ Unsplash API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Unsplash request failed: {e}")
            return None

    def search_photos(self,
                     query: str,
                     per_page: int = 15,
                     orientation: str = "landscape") -> List[Dict]:
        """
        Search for photos on Unsplash

        Args:
            query: Search query
            per_page: Number of results (1-30)
            orientation: landscape, portrait, or squarish

        Returns:
            List of photo objects with URLs
        """
        if not self.enabled:
            return []

        url = f"{self.base_url}/search/photos"
        params = {
            'query': query,
            'per_page': min(per_page, 30),
            'orientation': orientation
        }

        logger.info(f"🔍 Searching Unsplash photos: '{query}'")

        response = self._make_request(url, params)

        if not response or 'results' not in response:
            return []

        photos = []
        for photo in response['results']:
            photos.append({
                'id': photo['id'],
                'width': photo['width'],
                'height': photo['height'],
                'url': photo['urls'].get('regular', photo['urls']['full']),
                'url_full': photo['urls']['full'],
                'url_raw': photo['urls']['raw'],
                'description': photo.get('description', photo.get('alt_description', '')),
                'photographer': photo['user']['name'],
                'photographer_url': photo['user']['links']['html']
            })

        logger.info(f"✅ Found {len(photos)} Unsplash photos")
        return photos

    def download_photo(self, photo_url: str, output_path: str) -> bool:
        """
        Download photo from Unsplash

        Args:
            photo_url: Photo URL to download
            output_path: Path to save image

        Returns:
            True if successful
        """
        try:
            # Add quality and size parameters to URL
            if '?' not in photo_url:
                photo_url += '?w=1920&h=1080&fit=crop'

            response = requests.get(photo_url, timeout=30)

            if response.status_code == 200:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, 'wb') as f:
                    f.write(response.content)

                file_size = output_file.stat().st_size / 1024  # KB
                logger.info(f"✅ Downloaded: {output_file.name} ({file_size:.1f} KB)")
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
                           max_retries: int = 3) -> bool:
        """
        Get best matching photo for scene description

        Args:
            scene_description: Scene description/prompt
            output_path: Where to save image
            max_retries: Max search attempts

        Returns:
            True if photo downloaded successfully
        """
        try:
            # Extract keywords from scene description
            keywords = self._extract_keywords(scene_description)

            for attempt in range(max_retries):
                # Build query from keywords
                if attempt == 0:
                    # Try full keywords
                    query = ' '.join(keywords[:5])
                elif attempt == 1:
                    # Try fewer keywords
                    query = ' '.join(keywords[:3])
                else:
                    # Try main keyword only
                    query = keywords[0] if keywords else scene_description.split()[0]

                logger.info(f"   🔍 Attempt {attempt + 1}/{max_retries}: '{query}'")

                # Search photos
                photos = self.search_photos(query, per_page=5)

                if photos:
                    # Download first photo
                    photo = photos[0]
                    success = self.download_photo(photo['url'], output_path)

                    if success:
                        logger.info(f"   ✅ Unsplash photo: {photo['description'][:50]}...")
                        return True

            logger.warning(f"   ⚠️ No suitable Unsplash photo found after {max_retries} attempts")
            return False

        except Exception as e:
            logger.error(f"   ❌ Unsplash scene photo failed: {e}")
            return False

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract relevant keywords from text

        Args:
            text: Input text/prompt

        Returns:
            List of keywords
        """
        # Remove special characters
        text = re.sub(r'[^\w\s-]', ' ', text.lower())

        # Split into words
        words = text.split()

        # Filter stopwords (simple approach)
        stopwords = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
            'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
            'to', 'was', 'will', 'with', 'the', 'this', 'but', 'they', 'have',
            'had', 'what', 'when', 'where', 'who', 'which', 'why', 'how'
        }

        keywords = [w for w in words if w not in stopwords and len(w) > 2]

        # Return unique keywords
        return list(dict.fromkeys(keywords))

    def get_random_photo(self,
                        category: str = "",
                        output_path: str = "") -> bool:
        """
        Get random photo from Unsplash

        Args:
            category: Optional category/query
            output_path: Where to save image

        Returns:
            True if successful
        """
        try:
            url = f"{self.base_url}/photos/random"
            params = {}

            if category:
                params['query'] = category

            response = self._make_request(url, params)

            if response:
                photo_url = response['urls']['regular']
                return self.download_photo(photo_url, output_path)

            return False

        except Exception as e:
            logger.error(f"❌ Random photo failed: {e}")
            return False

    def get_status(self) -> Dict:
        """Get provider status"""
        return {
            'enabled': self.enabled,
            'demo_mode': self.demo_mode,
            'requests_made': self.requests_made,
            'rate_limit': self.rate_limit,
            'requests_remaining': self.rate_limit - self.requests_made
        }


# Test
if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("📷 UNSPLASH PROVIDER TEST")
    print("="*70)

    provider = UnsplashProvider()

    print(f"\nStatus: {provider.get_status()}")

    print("\n📝 TEST 1: Search Photos")
    photos = provider.search_photos("artificial intelligence technology", per_page=3)

    if photos:
        print(f"✅ Found {len(photos)} photos:")
        for i, photo in enumerate(photos, 1):
            print(f"\n   Photo {i}:")
            print(f"      ID: {photo['id']}")
            print(f"      Size: {photo['width']}x{photo['height']}")
            print(f"      Description: {photo['description'][:50]}...")
            print(f"      Photographer: {photo['photographer']}")
    else:
        print("❌ No photos found")

    print("\n" + "="*70)
    print("✅ UNSPLASH PROVIDER TEST COMPLETE")
    print("="*70)
