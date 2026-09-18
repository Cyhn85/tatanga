"""
VIDEOCU v1 - Stock Video Provider Module
Pixabay Video API (5000 req/hour) + Pexels Video API (200 req/hour)
FREE stock video clips for professional video production
"""

import requests
import logging
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import os
import time
import random

logger = logging.getLogger(__name__)


class VideoProvider:
    """
    Multi-Provider Stock Video API

    Providers:
    - Pixabay: 5000 req/hour, FREE, 4K available
    - Pexels: 200 req/hour, FREE, HD/4K available

    Both provide:
    - Multiple resolutions (360p to 4K)
    - Various durations
    - Commercial use OK
    - No attribution required (but appreciated)
    """

    # API Endpoints
    PIXABAY_API_URL = "https://pixabay.com/api/videos/"
    PEXELS_API_URL = "https://api.pexels.com/videos/search"

    # Video quality preferences
    QUALITY_PRIORITY = ['large', 'medium', 'small', 'tiny']  # Pixabay
    PEXELS_QUALITY = ['hd', 'sd']  # Pexels: hd=1920x1080, sd=960x540

    def __init__(self,
                 pixabay_api_key: Optional[str] = None,
                 pexels_api_key: Optional[str] = None):
        """
        Initialize video providers

        Args:
            pixabay_api_key: Pixabay API key (from .env or direct)
            pexels_api_key: Pexels API key (from .env or direct)
        """
        self.pixabay_key = pixabay_api_key or os.getenv('PIXABAY_API_KEY', '')
        self.pexels_key = pexels_api_key or os.getenv('PEXELS_API_KEY', '')

        # Track API availability
        self.pixabay_enabled = bool(self.pixabay_key)
        self.pexels_enabled = bool(self.pexels_key)

        if self.pixabay_enabled:
            logger.info("✅ Pixabay Video API enabled (5000 req/hour)")
        if self.pexels_enabled:
            logger.info("✅ Pexels Video API enabled (200 req/hour)")

        if not self.pixabay_enabled and not self.pexels_enabled:
            logger.warning("⚠️ No video API keys configured!")
            logger.warning("   Add PIXABAY_API_KEY or PEXELS_API_KEY to .env")

    def search_videos(self,
                      query: str,
                      provider: str = 'auto',
                      min_duration: int = 5,
                      max_duration: int = 60,
                      orientation: str = 'horizontal',
                      per_page: int = 10) -> List[Dict]:
        """
        Search for stock videos

        Args:
            query: Search query (English keywords)
            provider: 'pixabay', 'pexels', or 'auto' (tries both)
            min_duration: Minimum video duration in seconds
            max_duration: Maximum video duration in seconds
            orientation: 'horizontal', 'vertical', or 'all'
            per_page: Number of results

        Returns:
            List of video metadata dicts
        """
        results = []

        if provider == 'auto':
            # Try Pixabay first (higher rate limit)
            if self.pixabay_enabled:
                results = self._search_pixabay(query, min_duration, max_duration, per_page)

            # Fallback to Pexels if no results
            if not results and self.pexels_enabled:
                results = self._search_pexels(query, orientation, per_page)

        elif provider == 'pixabay' and self.pixabay_enabled:
            results = self._search_pixabay(query, min_duration, max_duration, per_page)

        elif provider == 'pexels' and self.pexels_enabled:
            results = self._search_pexels(query, orientation, per_page)

        logger.info(f"🎬 Found {len(results)} videos for '{query}'")
        return results

    def _search_pixabay(self,
                        query: str,
                        min_duration: int,
                        max_duration: int,
                        per_page: int) -> List[Dict]:
        """Search Pixabay Video API"""
        try:
            params = {
                'key': self.pixabay_key,
                'q': query,
                'video_type': 'all',  # film, animation, all
                'per_page': per_page,
                'safesearch': 'true',
                'lang': 'en'
            }

            response = requests.get(self.PIXABAY_API_URL, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                videos = []

                for hit in data.get('hits', []):
                    duration = hit.get('duration', 0)

                    # Filter by duration
                    if min_duration <= duration <= max_duration:
                        # Get best quality video URL
                        video_files = hit.get('videos', {})
                        video_url, resolution = self._get_best_pixabay_quality(video_files)

                        if video_url:
                            videos.append({
                                'id': str(hit.get('id')),
                                'provider': 'pixabay',
                                'url': video_url,
                                'preview_url': hit.get('userImageURL', ''),
                                'duration': duration,
                                'resolution': resolution,
                                'width': video_files.get('large', {}).get('width', 1920),
                                'height': video_files.get('large', {}).get('height', 1080),
                                'tags': hit.get('tags', ''),
                                'user': hit.get('user', ''),
                                'page_url': hit.get('pageURL', '')
                            })

                return videos

            else:
                logger.error(f"❌ Pixabay API error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"❌ Pixabay search failed: {e}")
            return []

    def _search_pexels(self,
                       query: str,
                       orientation: str,
                       per_page: int) -> List[Dict]:
        """Search Pexels Video API"""
        try:
            headers = {
                'Authorization': self.pexels_key
            }

            params = {
                'query': query,
                'per_page': per_page,
                'orientation': orientation if orientation != 'all' else 'landscape'
            }

            response = requests.get(
                self.PEXELS_API_URL,
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                videos = []

                for video in data.get('videos', []):
                    # Get video files
                    video_files = video.get('video_files', [])
                    video_url, resolution, width, height = self._get_best_pexels_quality(video_files)

                    if video_url:
                        videos.append({
                            'id': str(video.get('id')),
                            'provider': 'pexels',
                            'url': video_url,
                            'preview_url': video.get('image', ''),
                            'duration': video.get('duration', 0),
                            'resolution': resolution,
                            'width': width,
                            'height': height,
                            'user': video.get('user', {}).get('name', ''),
                            'page_url': video.get('url', '')
                        })

                return videos

            else:
                logger.error(f"❌ Pexels API error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"❌ Pexels search failed: {e}")
            return []

    def _get_best_pixabay_quality(self, video_files: Dict) -> Tuple[str, str]:
        """Get highest quality Pixabay video URL"""
        for quality in self.QUALITY_PRIORITY:
            if quality in video_files:
                url = video_files[quality].get('url', '')
                if url:
                    return url, quality
        return '', ''

    def _get_best_pexels_quality(self, video_files: List[Dict]) -> Tuple[str, str, int, int]:
        """Get highest quality Pexels video URL"""
        # Sort by resolution (width * height)
        sorted_files = sorted(
            video_files,
            key=lambda x: x.get('width', 0) * x.get('height', 0),
            reverse=True
        )

        for vf in sorted_files:
            url = vf.get('link', '')
            quality = vf.get('quality', 'sd')
            width = vf.get('width', 1920)
            height = vf.get('height', 1080)

            # Prefer HD or higher
            if url and width >= 1280:
                return url, quality, width, height

        # Return first available if no HD
        if sorted_files:
            vf = sorted_files[0]
            return vf.get('link', ''), vf.get('quality', 'sd'), vf.get('width', 960), vf.get('height', 540)

        return '', '', 0, 0

    def download_video(self,
                       video_url: str,
                       output_path: str,
                       timeout: int = 120) -> bool:
        """
        Download video file

        Args:
            video_url: Direct video URL
            output_path: Output file path
            timeout: Download timeout in seconds

        Returns:
            True if successful
        """
        try:
            logger.info(f"📥 Downloading video: {Path(output_path).name}")

            response = requests.get(video_url, stream=True, timeout=timeout)

            if response.status_code == 200:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(output_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                file_size_mb = output_file.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Video downloaded: {file_size_mb:.1f} MB")
                return True

            else:
                logger.error(f"❌ Download failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Video download failed: {e}")
            return False

    def get_video_for_scene(self,
                            scene_description: str,
                            output_path: str,
                            min_duration: int = 5,
                            max_duration: int = 30,
                            max_retries: int = 3) -> bool:
        """
        Get a stock video clip for a scene description

        Args:
            scene_description: Scene text (will be converted to keywords)
            output_path: Output file path
            min_duration: Minimum clip duration
            max_duration: Maximum clip duration
            max_retries: Number of search retries with different keywords

        Returns:
            True if video downloaded successfully
        """
        # Extract keywords from description
        keywords = self._extract_keywords(scene_description)

        for attempt in range(max_retries):
            # Use different keywords on each attempt
            if attempt == 0:
                query = ' '.join(keywords[:3])  # First 3 keywords
            elif attempt == 1:
                query = ' '.join(keywords[:2])  # First 2 keywords
            else:
                query = keywords[0] if keywords else scene_description.split()[0]

            logger.info(f"🔍 Searching videos: '{query}' (attempt {attempt + 1}/{max_retries})")

            # Search for videos
            videos = self.search_videos(
                query=query,
                provider='auto',
                min_duration=min_duration,
                max_duration=max_duration,
                per_page=5
            )

            if videos:
                # Pick the BEST matching video (not random!)
                video = self._select_best_video(videos, scene_description)

                # Download
                success = self.download_video(
                    video_url=video['url'],
                    output_path=output_path
                )

                if success:
                    logger.info(f"✅ Got video from {video['provider']}: {video['duration']}s")
                    return True

            # Wait before retry
            if attempt < max_retries - 1:
                time.sleep(0.5)

        logger.warning(f"⚠️ No video found for: {scene_description[:50]}")
        return False

    def get_videos_for_scenes(self,
                              scenes: List[Dict],
                              output_dir: str,
                              min_duration: int = 5,
                              max_duration: int = 15) -> List[str]:
        """
        Get stock videos for multiple scenes

        Args:
            scenes: List of scene dictionaries with 'text' or 'visual' fields
            output_dir: Output directory
            min_duration: Minimum clip duration per scene
            max_duration: Maximum clip duration per scene

        Returns:
            List of downloaded video file paths
        """
        output_files = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for i, scene in enumerate(scenes, 1):
            # Get scene description
            description = scene.get('visual', scene.get('text', f'scene {i}'))

            video_file = output_path / f"scene_{i:03d}.mp4"

            logger.info(f"📽️ Getting video for scene {i}/{len(scenes)}")

            success = self.get_video_for_scene(
                scene_description=description,
                output_path=str(video_file),
                min_duration=min_duration,
                max_duration=max_duration
            )

            if success:
                output_files.append(str(video_file))
            else:
                # Will need image fallback
                output_files.append(None)

            # Rate limiting
            time.sleep(0.5)

        valid_count = len([f for f in output_files if f])
        logger.info(f"✅ Downloaded {valid_count}/{len(scenes)} video clips")

        return output_files

    def _select_best_video(self, videos: List[Dict], scene_description: str) -> Dict:
        """
        Select the most relevant video from search results.
        Uses keyword matching instead of random selection.

        Args:
            videos: List of video metadata dicts
            scene_description: Original scene description for relevance matching

        Returns:
            Best matching video dict
        """
        if not videos:
            return videos[0] if videos else {}

        if len(videos) == 1:
            return videos[0]

        # Extract keywords from scene description
        keywords = self._extract_keywords(scene_description)
        keywords_lower = [k.lower() for k in keywords]

        best_video = videos[0]
        best_score = 0

        for video in videos:
            score = 0

            # Check video URL for keywords (Pexels URLs often contain descriptive words)
            video_url = video.get('url', '').lower()
            page_url = video.get('page_url', '').lower()

            for kw in keywords_lower:
                if kw in video_url or kw in page_url:
                    score += 2  # URL match is strong signal

            # Prefer higher resolution
            width = video.get('width', 0)
            if width >= 1920:
                score += 1

            # Prefer videos with moderate duration (5-20s ideal)
            duration = video.get('duration', 0)
            if 5 <= duration <= 20:
                score += 1

            if score > best_score:
                best_score = score
                best_video = video

        return best_video

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract search keywords from text

        Args:
            text: Scene description text

        Returns:
            List of keywords
        """
        # Remove common stop words (German + English)
        stop_words = {
            'der', 'die', 'das', 'den', 'dem', 'ein', 'eine', 'einer', 'einem',
            'und', 'oder', 'aber', 'wenn', 'weil', 'dass', 'ob', 'wie', 'was',
            'ist', 'sind', 'war', 'waren', 'wird', 'werden', 'hat', 'haben',
            'the', 'a', 'an', 'and', 'or', 'but', 'if', 'because', 'that',
            'is', 'are', 'was', 'were', 'will', 'be', 'has', 'have',
            'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'of',
            'im', 'am', 'an', 'auf', 'zu', 'für', 'mit', 'von', 'bei',
            'this', 'that', 'these', 'those', 'it', 'its', 'sie', 'es'
        }

        # Clean and split
        words = text.lower().replace(',', ' ').replace('.', ' ').split()

        # Filter and dedupe
        keywords = []
        seen = set()

        for word in words:
            # Clean word
            word = ''.join(c for c in word if c.isalnum())

            # Skip short words and stop words
            if len(word) > 2 and word not in stop_words and word not in seen:
                keywords.append(word)
                seen.add(word)

        return keywords[:5]  # Max 5 keywords

    def get_status(self) -> Dict:
        """Get provider status"""
        return {
            'pixabay': {
                'enabled': self.pixabay_enabled,
                'rate_limit': '5000 req/hour',
                'quality': 'up to 4K'
            },
            'pexels': {
                'enabled': self.pexels_enabled,
                'rate_limit': '200 req/hour',
                'quality': 'up to 4K'
            }
        }


# Test
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    # Load .env
    load_dotenv()

    # Set UTF-8 encoding
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎬 STOCK VIDEO PROVIDER TEST")
    print("="*70)

    provider = VideoProvider()

    # Show status
    print("\n📊 Provider Status:")
    status = provider.get_status()
    for name, info in status.items():
        enabled = "✅" if info['enabled'] else "❌"
        print(f"   {enabled} {name}: {info['rate_limit']}, {info['quality']}")

    if not provider.pixabay_enabled and not provider.pexels_enabled:
        print("\n⚠️ No API keys configured!")
        print("   Add PIXABAY_API_KEY or PEXELS_API_KEY to .env file")
        sys.exit(0)

    # Test search
    print("\n" + "="*70)
    print("TEST 1: Video Search")
    print("="*70)

    videos = provider.search_videos(
        query="technology artificial intelligence",
        min_duration=5,
        max_duration=30,
        per_page=5
    )

    print(f"\n📽️ Found {len(videos)} videos:")
    for v in videos[:3]:
        print(f"   - [{v['provider']}] {v['duration']}s, {v['resolution']}, ID: {v['id']}")

    # Test download
    if videos:
        print("\n" + "="*70)
        print("TEST 2: Video Download")
        print("="*70)

        video = videos[0]
        output_file = "output/test_stock_video.mp4"

        success = provider.download_video(
            video_url=video['url'],
            output_path=output_file
        )

        if success:
            file_size = Path(output_file).stat().st_size / (1024 * 1024)
            print(f"   ✅ Downloaded: {output_file} ({file_size:.1f} MB)")

    # Test scene-based search
    print("\n" + "="*70)
    print("TEST 3: Scene-Based Video Search")
    print("="*70)

    success = provider.get_video_for_scene(
        scene_description="Künstliche Intelligenz revolutioniert die moderne Industrie",
        output_path="output/test_scene_video.mp4",
        min_duration=5,
        max_duration=20
    )

    if success:
        print("   ✅ Scene video downloaded!")

    print("\n" + "="*70)
    print("✅ STOCK VIDEO PROVIDER TEST COMPLETE")
    print("="*70)
    print("\n💡 Benefits:")
    print("   • Pixabay: 5000 req/hour, FREE, 4K videos")
    print("   • Pexels: 200 req/hour, FREE, HD videos")
    print("   • Both: Commercial use OK, no attribution required")
    print("\n")
