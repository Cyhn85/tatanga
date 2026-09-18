"""
VIDEOCU v1 - Performance Logger
Collects performance metrics from social media platforms and stores them in Agent Memory.

This is the data backbone for the autonomous learning system (Phase 5).
"""

import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import time

from .agent_memory import AgentMemory

logger = logging.getLogger(__name__)


class PerformanceLogger:
    """
    Collects and logs performance metrics from various platforms.

    This is crucial for the self-improvement engine to learn from
    what content performs well.
    """

    def __init__(self, agent_memory: Optional[AgentMemory] = None):
        """
        Initialize Performance Logger

        Args:
            agent_memory: AgentMemory instance for storing metrics
        """
        self.agent_memory = agent_memory or AgentMemory()

        # Platform scrapers (initialized lazily)
        self._youtube_scraper = None
        self._tiktok_scraper = None
        self._instagram_scraper = None

        # Configuration
        self.collection_interval_hours = 6  # Collect metrics every 6 hours
        self.retry_attempts = 3
        self.retry_delay_seconds = 5

        logger.info("📊 Performance Logger initialized")

    @property
    def youtube_scraper(self):
        """Lazy initialization of YouTube scraper"""
        if self._youtube_scraper is None:
            from .platform_scrapers.youtube_scraper import YouTubeScraper
            self._youtube_scraper = YouTubeScraper()
        return self._youtube_scraper

    @property
    def tiktok_scraper(self):
        """Lazy initialization of TikTok scraper"""
        if self._tiktok_scraper is None:
            from .platform_scrapers.tiktok_scraper import TikTokScraper
            self._tiktok_scraper = TikTokScraper()
        return self._tiktok_scraper

    @property
    def instagram_scraper(self):
        """Lazy initialization of Instagram scraper"""
        if self._instagram_scraper is None:
            from .platform_scrapers.instagram_scraper import InstagramScraper
            self._instagram_scraper = InstagramScraper()
        return self._instagram_scraper

    def collect_all_metrics(self) -> Dict:
        """
        Collect metrics from all platforms for recent tasks

        Returns:
            Summary of collection results
        """
        logger.info("📊 Starting metric collection from all platforms...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'platforms': {},
            'total_collected': 0,
            'errors': []
        }

        # Get recent tasks that need metrics collection
        recent_tasks = self._get_tasks_needing_metrics()

        logger.info(f"   Found {len(recent_tasks)} tasks needing metric collection")

        for task in recent_tasks:
            platform = task.get('platform', 'unknown')
            task_id = task.get('task_id')
            video_id = task.get('video_id')

            if not video_id:
                logger.warning(f"   ⚠️ Task {task_id} missing video_id, skipping")
                continue

            try:
                # Collect metrics based on platform
                if platform == 'youtube':
                    metrics = self._collect_youtube_metrics(video_id, task_id)
                elif platform == 'tiktok':
                    metrics = self._collect_tiktok_metrics(video_id, task_id)
                elif platform == 'instagram':
                    metrics = self._collect_instagram_metrics(video_id, task_id)
                else:
                    logger.warning(f"   ⚠️ Unknown platform: {platform}")
                    continue

                if metrics and metrics.get('success'):
                    # Store in agent memory
                    self.agent_memory.record_metrics(
                        task_id=task_id,
                        platform=platform,
                        metrics=metrics['data']
                    )

                    results['total_collected'] += 1

                    if platform not in results['platforms']:
                        results['platforms'][platform] = 0
                    results['platforms'][platform] += 1

                    logger.info(f"   ✅ Metrics collected for {platform}/{video_id}")

            except Exception as e:
                error_msg = f"{platform}/{task_id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"   ❌ Metric collection failed: {error_msg}")

        logger.info(f"📊 Metric collection complete. Total: {results['total_collected']}")

        return results

    def _get_tasks_needing_metrics(self) -> List[Dict]:
        """
        Get tasks that need metric collection

        Returns recent completed tasks that either:
        - Have no metrics yet
        - Haven't been updated in the last 6 hours
        """
        # In production, this would query the database
        # For now, return empty list (will be implemented with real DB)

        # TODO: Query agent_memory database for:
        # SELECT * FROM tasks
        # WHERE status = 'completed'
        # AND (last_metric_collection IS NULL
        #      OR last_metric_collection < datetime('now', '-6 hours'))

        return []

    def _collect_youtube_metrics(self, video_id: str, task_id: str) -> Dict:
        """
        Collect metrics from YouTube

        Args:
            video_id: YouTube video ID
            task_id: Internal task ID

        Returns:
            Metrics dictionary
        """
        logger.info(f"      Collecting YouTube metrics for: {video_id}")

        # Initialize YouTube scraper if needed
        if not self.youtube_scraper:
            try:
                from .platform_scrapers.youtube_scraper import YouTubeScraper
                self.youtube_scraper = YouTubeScraper()
            except ImportError:
                logger.error("      ❌ YouTube scraper not available")
                return {'success': False, 'error': 'Scraper not available'}

        # Collect with retry logic
        for attempt in range(self.retry_attempts):
            try:
                metrics = self.youtube_scraper.get_video_metrics(video_id)

                if metrics:
                    return {
                        'success': True,
                        'data': {
                            'views': metrics.get('viewCount', 0),
                            'likes': metrics.get('likeCount', 0),
                            'comments': metrics.get('commentCount', 0),
                            'shares': metrics.get('shareCount', 0),
                            'ctr': self._calculate_ctr(metrics),
                            'avg_watch_time': metrics.get('averageViewDuration', 0),
                            'engagement_rate': self._calculate_engagement_rate(metrics)
                        }
                    }

            except Exception as e:
                logger.warning(f"      ⚠️ Attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay_seconds)

        return {'success': False, 'error': 'All retry attempts failed'}

    def _collect_tiktok_metrics(self, video_id: str, task_id: str) -> Dict:
        """Collect metrics from TikTok"""
        logger.info(f"      Collecting TikTok metrics for: {video_id}")

        if not self.tiktok_scraper:
            try:
                from .platform_scrapers.tiktok_scraper import TikTokScraper
                self.tiktok_scraper = TikTokScraper()
            except ImportError:
                logger.error("      ❌ TikTok scraper not available")
                return {'success': False, 'error': 'Scraper not available'}

        # Similar retry logic as YouTube
        for attempt in range(self.retry_attempts):
            try:
                metrics = self.tiktok_scraper.get_video_metrics(video_id)

                if metrics:
                    return {
                        'success': True,
                        'data': {
                            'views': metrics.get('playCount', 0),
                            'likes': metrics.get('diggCount', 0),
                            'comments': metrics.get('commentCount', 0),
                            'shares': metrics.get('shareCount', 0),
                            'engagement_rate': self._calculate_engagement_rate(metrics)
                        }
                    }

            except Exception as e:
                logger.warning(f"      ⚠️ Attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay_seconds)

        return {'success': False, 'error': 'All retry attempts failed'}

    def _collect_instagram_metrics(self, video_id: str, task_id: str) -> Dict:
        """Collect metrics from Instagram"""
        logger.info(f"      Collecting Instagram metrics for: {video_id}")

        if not self.instagram_scraper:
            try:
                from .platform_scrapers.instagram_scraper import InstagramScraper
                self.instagram_scraper = InstagramScraper()
            except ImportError:
                logger.error("      ❌ Instagram scraper not available")
                return {'success': False, 'error': 'Scraper not available'}

        for attempt in range(self.retry_attempts):
            try:
                metrics = self.instagram_scraper.get_reel_metrics(video_id)

                if metrics:
                    return {
                        'success': True,
                        'data': {
                            'views': metrics.get('play_count', 0),
                            'likes': metrics.get('like_count', 0),
                            'comments': metrics.get('comment_count', 0),
                            'shares': metrics.get('share_count', 0),
                            'engagement_rate': self._calculate_engagement_rate(metrics)
                        }
                    }

            except Exception as e:
                logger.warning(f"      ⚠️ Attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay_seconds)

        return {'success': False, 'error': 'All retry attempts failed'}

    def _calculate_ctr(self, metrics: Dict) -> float:
        """
        Calculate Click-Through Rate

        CTR = (clicks / impressions) * 100
        """
        impressions = metrics.get('impressionCount', 0)
        clicks = metrics.get('viewCount', 0)

        if impressions > 0:
            return (clicks / impressions) * 100
        return 0.0

    def _calculate_engagement_rate(self, metrics: Dict) -> float:
        """
        Calculate engagement rate

        Engagement Rate = ((likes + comments + shares) / views) * 100
        """
        views = metrics.get('viewCount') or metrics.get('playCount') or metrics.get('play_count', 0)
        likes = metrics.get('likeCount') or metrics.get('diggCount') or metrics.get('like_count', 0)
        comments = metrics.get('commentCount') or metrics.get('comment_count', 0)
        shares = metrics.get('shareCount') or metrics.get('share_count', 0)

        if views > 0:
            total_engagement = likes + comments + shares
            return (total_engagement / views) * 100
        return 0.0

    def get_performance_summary(self, platform: Optional[str] = None, days: int = 7) -> Dict:
        """
        Get performance summary for recent tasks

        Args:
            platform: Filter by platform (optional)
            days: Number of days to look back

        Returns:
            Performance summary statistics
        """
        logger.info(f"📊 Generating performance summary (last {days} days)")

        # TODO: Query agent_memory for metrics
        # This would aggregate views, CTR, engagement across all videos

        summary = {
            'period_days': days,
            'platform': platform or 'all',
            'total_videos': 0,
            'total_views': 0,
            'avg_ctr': 0.0,
            'avg_engagement_rate': 0.0,
            'top_performers': [],
            'underperformers': []
        }

        return summary


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
    print("📊 PERFORMANCE LOGGER TEST")
    print("="*70)

    logger_instance = PerformanceLogger()

    print("\n✅ Performance Logger initialized")
    print(f"   Collection interval: {logger_instance.collection_interval_hours} hours")
    print(f"   Retry attempts: {logger_instance.retry_attempts}")

    # Test metric collection (will fail gracefully without scrapers)
    print("\n📊 Testing metric collection...")
    results = logger_instance.collect_all_metrics()

    print(f"\n📊 Collection Results:")
    print(f"   Total collected: {results['total_collected']}")
    print(f"   Platforms: {results['platforms']}")
    print(f"   Errors: {len(results['errors'])}")

    print("\n" + "="*70)
    print("✅ PERFORMANCE LOGGER TEST COMPLETE")
    print("="*70 + "\n")
