"""
VIDEOCU v1 - YouTube Scraper
Collects video metrics from YouTube using API + fallback scraping

Uses YouTube Data API v3 primarily, with fallback to web scraping if needed.
"""

import logging
import os
import re
from typing import Dict, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class YouTubeScraper:
    """
    YouTube metrics collector with API and scraping fallback
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize YouTube scraper

        Args:
            api_key: YouTube Data API v3 key
        """
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY', '')
        self.api_enabled = bool(self.api_key)

        # API endpoints
        self.api_base_url = "https://www.googleapis.com/youtube/v3"

        # Rate limiting
        self.requests_per_day = 10000  # YouTube API quota
        self.requests_today = 0

        logger.info(f"🎥 YouTube Scraper initialized (API: {'✅' if self.api_enabled else '❌'})")

    def get_video_metrics(self, video_id: str) -> Optional[Dict]:
        """
        Get metrics for a YouTube video

        Args:
            video_id: YouTube video ID

        Returns:
            Metrics dictionary or None if failed
        """
        # Try API first
        if self.api_enabled and self.requests_today < self.requests_per_day:
            try:
                return self._get_metrics_via_api(video_id)
            except Exception as e:
                logger.warning(f"   ⚠️ API failed, trying scraping: {e}")

        # Fallback to scraping
        return self._get_metrics_via_scraping(video_id)

    def _get_metrics_via_api(self, video_id: str) -> Optional[Dict]:
        """
        Get metrics using YouTube Data API v3

        Args:
            video_id: YouTube video ID

        Returns:
            Metrics dictionary
        """
        logger.info(f"      Using YouTube Data API for: {video_id}")

        # Build API request
        url = f"{self.api_base_url}/videos"
        params = {
            'key': self.api_key,
            'id': video_id,
            'part': 'statistics,contentDetails,snippet'
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if not data.get('items'):
                logger.warning(f"      ⚠️ Video not found: {video_id}")
                return None

            video_data = data['items'][0]
            statistics = video_data.get('statistics', {})
            content_details = video_data.get('contentDetails', {})
            snippet = video_data.get('snippet', {})

            # Calculate CTR from impressions (if available in analytics)
            # Note: Detailed analytics require OAuth and Analytics API
            impressions = statistics.get('viewCount', 0)  # Approximation

            metrics = {
                'video_id': video_id,
                'viewCount': int(statistics.get('viewCount', 0)),
                'likeCount': int(statistics.get('likeCount', 0)),
                'commentCount': int(statistics.get('commentCount', 0)),
                'favoriteCount': int(statistics.get('favoriteCount', 0)),
                'duration': content_details.get('duration', ''),
                'publishedAt': snippet.get('publishedAt', ''),
                'title': snippet.get('title', ''),
                'impressionCount': int(impressions),  # Approximation
                'collected_at': datetime.now().isoformat()
            }

            self.requests_today += 1
            logger.info(f"      ✅ API metrics collected: {metrics['viewCount']} views")

            return metrics

        except requests.exceptions.RequestException as e:
            logger.error(f"      ❌ API request failed: {e}")
            return None

    def _get_metrics_via_scraping(self, video_id: str) -> Optional[Dict]:
        """
        Get metrics by scraping YouTube web page (fallback)

        Args:
            video_id: YouTube video ID

        Returns:
            Metrics dictionary
        """
        logger.info(f"      Using web scraping for: {video_id}")

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            # Use requests with proper headers to avoid blocks
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            html = response.text

            # Extract metrics using regex (YouTube embeds data in page)
            metrics = {
                'video_id': video_id,
                'viewCount': self._extract_view_count(html),
                'likeCount': self._extract_like_count(html),
                'commentCount': self._extract_comment_count(html),
                'title': self._extract_title(html),
                'collected_at': datetime.now().isoformat()
            }

            logger.info(f"      ✅ Scraping metrics collected: {metrics['viewCount']} views")

            return metrics

        except Exception as e:
            logger.error(f"      ❌ Scraping failed: {e}")
            return None

    def _extract_view_count(self, html: str) -> int:
        """Extract view count from HTML"""
        try:
            # YouTube embeds view count in various formats
            patterns = [
                r'"viewCount":"(\d+)"',
                r'"views":{"simpleText":"([\d,]+) views"}',
                r'(\d+(?:,\d+)*)\s+views'
            ]

            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    view_str = match.group(1).replace(',', '')
                    return int(view_str)

            return 0

        except Exception as e:
            logger.warning(f"      ⚠️ View count extraction failed: {e}")
            return 0

    def _extract_like_count(self, html: str) -> int:
        """Extract like count from HTML"""
        try:
            patterns = [
                r'"likeCount":(\d+)',
                r'"label":"([\d,]+) likes"'
            ]

            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    like_str = match.group(1).replace(',', '')
                    return int(like_str)

            return 0

        except Exception as e:
            logger.warning(f"      ⚠️ Like count extraction failed: {e}")
            return 0

    def _extract_comment_count(self, html: str) -> int:
        """Extract comment count from HTML"""
        try:
            patterns = [
                r'"commentCount":"(\d+)"',
                r'(\d+(?:,\d+)*)\s+Comments'
            ]

            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    comment_str = match.group(1).replace(',', '')
                    return int(comment_str)

            return 0

        except Exception as e:
            logger.warning(f"      ⚠️ Comment count extraction failed: {e}")
            return 0

    def _extract_title(self, html: str) -> str:
        """Extract video title from HTML"""
        try:
            match = re.search(r'<title>(.+?)</title>', html)
            if match:
                title = match.group(1)
                # Remove " - YouTube" suffix
                return title.replace(' - YouTube', '').strip()
            return ''

        except Exception as e:
            logger.warning(f"      ⚠️ Title extraction failed: {e}")
            return ''

    def get_channel_metrics(self, channel_id: str) -> Optional[Dict]:
        """
        Get metrics for a YouTube channel

        Args:
            channel_id: YouTube channel ID

        Returns:
            Channel metrics dictionary
        """
        if not self.api_enabled:
            logger.warning("   ⚠️ Channel metrics require API")
            return None

        url = f"{self.api_base_url}/channels"
        params = {
            'key': self.api_key,
            'id': channel_id,
            'part': 'statistics,snippet'
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if not data.get('items'):
                return None

            channel_data = data['items'][0]
            statistics = channel_data.get('statistics', {})

            metrics = {
                'channel_id': channel_id,
                'subscriberCount': int(statistics.get('subscriberCount', 0)),
                'videoCount': int(statistics.get('videoCount', 0)),
                'viewCount': int(statistics.get('viewCount', 0)),
                'collected_at': datetime.now().isoformat()
            }

            self.requests_today += 1
            return metrics

        except Exception as e:
            logger.error(f"   ❌ Channel metrics failed: {e}")
            return None


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
    print("🎥 YOUTUBE SCRAPER TEST")
    print("="*70)

    scraper = YouTubeScraper()

    # Test with a known YouTube video
    # Using a popular video ID for testing
    test_video_id = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

    print(f"\n📊 Testing metrics collection for video: {test_video_id}")
    metrics = scraper.get_video_metrics(test_video_id)

    if metrics:
        print(f"\n✅ Metrics collected successfully:")
        print(f"   Title: {metrics.get('title', 'N/A')}")
        print(f"   Views: {metrics.get('viewCount', 0):,}")
        print(f"   Likes: {metrics.get('likeCount', 0):,}")
        print(f"   Comments: {metrics.get('commentCount', 0):,}")
    else:
        print("\n⚠️ Metrics collection failed (API key may be needed)")

    print("\n" + "="*70)
    print("✅ YOUTUBE SCRAPER TEST COMPLETE")
    print("="*70 + "\n")
