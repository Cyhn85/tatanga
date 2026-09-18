"""
VIDEOCU v1 - Social Media Trend Analyzer Module
TikTok ve Instagram Reels için GERÇEK trend analizi
Web scraper fallback ile Instagram IP bloğunu aşar
"""

from TikTokApi import TikTokApi
from instagrapi import Client
from instagrapi.exceptions import LoginRequired
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import os
import time

logger = logging.getLogger(__name__)


class SocialTrendAnalyzer:
    """TikTok ve Instagram Reels trend analizi"""

    def __init__(self,
                 tiktok_ms_token: str = None,
                 instagram_username: str = None,
                 instagram_password: str = None):
        self.tiktok_ms_token = tiktok_ms_token or os.getenv("MS_TOKEN")
        self.instagram_username = instagram_username or os.getenv("INSTAGRAM_USERNAME")
        self.instagram_password = instagram_password or os.getenv("INSTAGRAM_PASSWORD")

        self.instagram_client = None
        self.use_web_scraper = False  # API başarısız olursa True yapılır
        self._init_instagram()

    def _init_instagram(self):
        """Instagram client'ı başlat - başarısız olursa web scraper kullanılacak"""
        if self.instagram_username and self.instagram_password:
            try:
                self.instagram_client = Client()
                self.instagram_client.login(self.instagram_username, self.instagram_password)
                logger.info("✅ Instagram client initialized")
            except LoginRequired as e:
                logger.error(f"❌ Instagram login required: {e}")
                self.instagram_client = None
                self.use_web_scraper = True
                logger.info("📱 Web scraper will be used for Instagram")
            except Exception as e:
                logger.error(f"❌ Instagram login failed: {e}")
                self.instagram_client = None
                self.use_web_scraper = True
                logger.info("📱 Web scraper will be used for Instagram")
        else:
            logger.warning("⚠️ Instagram credentials not provided")
            self.use_web_scraper = True

    async def get_tiktok_trending(self, count: int = 30, region: str = 'DE') -> List[Dict]:
        """
        TikTok'tan trending videolar al

        Args:
            count: Video sayısı
            region: Region code (Not: Gerçek filtreleme için proxy gerekir)

        Returns:
            Trending video listesi
        """
        try:
            logger.info(f"🔍 Fetching {count} trending TikTok videos...")

            results = []
            async with TikTokApi() as api:
                await api.create_sessions(
                    ms_tokens=[self.tiktok_ms_token] if self.tiktok_ms_token else [],
                    num_sessions=1,
                    sleep_after=3,
                    browser="chromium"
                )

                try:
                    async for video in api.trending.videos(count=count):
                        try:
                            video_data = video.as_dict

                            video_id = video_data.get('id', '')
                            author_data = video_data.get('author', {})
                            stats = video_data.get('stats', {})

                            results.append({
                                'platform': 'tiktok',
                                'video_id': video_id,
                                'title': video_data.get('desc', '')[:200],
                                'author': author_data.get('uniqueId', 'Unknown'),
                                'views': stats.get('playCount', 0),
                                'likes': stats.get('diggCount', 0),
                                'comments': stats.get('commentCount', 0),
                                'shares': stats.get('shareCount', 0),
                                'url': f"https://www.tiktok.com/@{author_data.get('uniqueId', '')}/video/{video_id}",
                                'created_at': datetime.fromtimestamp(video_data.get('createTime', 0)) if video_data.get('createTime') else datetime.now(),
                                'region': region,
                                'score': self._calculate_engagement_score(
                                    stats.get('playCount', 0),
                                    stats.get('diggCount', 0),
                                    stats.get('commentCount', 0),
                                    stats.get('shareCount', 0)
                                )
                            })
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to process video: {e}")
                            continue

                except Exception as e:
                    logger.error(f"❌ Error iterating TikTok videos: {e}")

            # Sort by score
            results.sort(key=lambda x: x['score'], reverse=True)

            logger.info(f"✅ Found {len(results)} TikTok trending videos")
            return results

        except Exception as e:
            logger.error(f"❌ TikTok trending fetch error: {e}")
            return []

    def get_instagram_trending_by_hashtags(self,
                                          hashtags: List[str],
                                          amount_per_tag: int = 20) -> List[Dict]:
        """
        Instagram Reels'i hashtag'lerden al
        API başarısız olursa web scraper kullanır

        Args:
            hashtags: Hashtag listesi
            amount_per_tag: Her hashtag için reel sayısı

        Returns:
            Trending reel listesi
        """
        # API kullanılamıyorsa web scraper'a geç
        if not self.instagram_client or self.use_web_scraper:
            logger.info("📱 Using web scraper for Instagram...")
            return self._scrape_instagram_hashtags(hashtags, amount_per_tag)

        try:
            logger.info(f"🔍 Fetching Instagram Reels from {len(hashtags)} hashtags...")

            all_reels = []

            for hashtag in hashtags:
                try:
                    logger.info(f"  Fetching #{hashtag}...")
                    medias = self.instagram_client.hashtag_medias_recent(
                        hashtag,
                        amount=amount_per_tag
                    )

                    for media in medias:
                        # Only Reels
                        if media.product_type == "clips":
                            all_reels.append({
                                'platform': 'instagram',
                                'media_id': str(media.pk),
                                'title': media.caption_text[:200] if media.caption_text else '',
                                'author': media.user.username,
                                'views': getattr(media, 'view_count', 0),
                                'likes': media.like_count,
                                'comments': media.comment_count,
                                'shares': 0,  # Instagram doesn't expose share count
                                'url': f"https://www.instagram.com/p/{media.code}/",
                                'thumbnail': str(media.thumbnail_url) if media.thumbnail_url else '',
                                'created_at': media.taken_at,
                                'region': 'DE',
                                'hashtag': hashtag,
                                'score': self._calculate_engagement_score(
                                    getattr(media, 'view_count', 0),
                                    media.like_count,
                                    media.comment_count,
                                    0
                                )
                            })

                    logger.info(f"  ✓ Processed #{hashtag}: {len([m for m in medias if m.product_type == 'clips'])} reels")
                    time.sleep(2)  # Rate limiting

                except Exception as e:
                    logger.warning(f"  ⚠ Failed to process #{hashtag}: {e}")
                    continue

            # Remove duplicates and sort by score
            unique_reels = {reel['media_id']: reel for reel in all_reels}.values()
            sorted_reels = sorted(unique_reels, key=lambda x: x['score'], reverse=True)

            logger.info(f"✅ Found {len(sorted_reels)} unique Instagram Reels")
            return list(sorted_reels)

        except Exception as e:
            logger.error(f"❌ Instagram fetch error: {e}")
            return []

    def _scrape_instagram_hashtags(self, hashtags: List[str], amount_per_tag: int = 20) -> List[Dict]:
        """
        Web scraper ile Instagram hashtag'lerinden reel'leri al
        API başarısız olduğunda fallback olarak kullanılır

        Args:
            hashtags: Hashtag listesi
            amount_per_tag: Her hashtag için reel sayısı

        Returns:
            Reel listesi
        """
        try:
            from .web_scraper import InstagramScraper

            logger.info(f"🌐 Starting Instagram web scraper for {len(hashtags)} hashtags...")

            scraper = InstagramScraper(headless=True)

            try:
                # Scraper ile hashtag'leri tara
                all_reels = scraper.scrape_instagram_explore(
                    hashtags=hashtags,
                    limit=amount_per_tag * len(hashtags)
                )

                # Engagement score ekle
                for reel in all_reels:
                    reel['score'] = self._calculate_engagement_score(
                        reel.get('views', 0),
                        reel.get('likes', 0),
                        reel.get('comments', 0),
                        reel.get('shares', 0)
                    )

                # Score'a göre sırala
                all_reels.sort(key=lambda x: x.get('score', 0), reverse=True)

                logger.info(f"✅ Web scraper found {len(all_reels)} Instagram reels")
                return all_reels

            finally:
                scraper.close()

        except ImportError as e:
            logger.error(f"❌ Web scraper module not found: {e}")
            logger.info("💡 Install: pip install undetected-chromedriver selenium fake-useragent")
            return []
        except Exception as e:
            logger.error(f"❌ Instagram web scraper error: {e}")
            return []

    def _calculate_engagement_score(self, views: int, likes: int,
                                   comments: int, shares: int) -> int:
        """
        Engagement score hesapla (ranking için)

        Formula: (likes * 2) + (comments * 5) + (shares * 3) + (views * 0.01)
        """
        return int(
            (likes * 2) +
            (comments * 5) +
            (shares * 3) +
            (views * 0.01)
        )

    async def get_combined_trending(self,
                                   tiktok_count: int = 30,
                                   instagram_hashtags: List[str] = None,
                                   top_n: int = 50) -> List[Dict]:
        """
        Her iki platformdan trending içerik al (combined)

        Args:
            tiktok_count: TikTok video sayısı
            instagram_hashtags: Instagram hashtag'leri
            top_n: Top N sonuç döndür

        Returns:
            Birleştirilmiş ve sıralanmış trending liste
        """
        if instagram_hashtags is None:
            instagram_hashtags = [
                "reelsdeutschland",
                "deutschland",
                "viral",
                "trending"
            ]

        logger.info("🔥 Starting combined trending analysis...")

        # Fetch from both platforms
        tiktok_results = await self.get_tiktok_trending(count=tiktok_count)
        instagram_results = self.get_instagram_trending_by_hashtags(
            hashtags=instagram_hashtags,
            amount_per_tag=15
        )

        # Combine results
        all_results = tiktok_results + instagram_results

        # Sort by score
        all_results.sort(key=lambda x: x['score'], reverse=True)

        logger.info(f"✅ Combined: {len(tiktok_results)} TikTok + {len(instagram_results)} Instagram = {len(all_results)} total")

        return all_results[:top_n]

    def get_trending_keywords_from_content(self, content_list: List[Dict]) -> List[Dict]:
        """
        İçeriklerden trending keyword'leri çıkar

        Args:
            content_list: Video/reel listesi

        Returns:
            Keyword frequency listesi
        """
        from collections import Counter
        import re

        keywords = []

        for content in content_list:
            title = content.get('title', '')
            # Extract hashtags
            hashtags = re.findall(r'#(\w+)', title)
            keywords.extend(hashtags)

            # Extract common words (simple approach)
            words = re.findall(r'\b\w{4,}\b', title.lower())
            keywords.extend(words)

        # Count frequencies
        keyword_counts = Counter(keywords)

        # Return top keywords
        trending_keywords = [
            {
                'keyword': keyword,
                'frequency': count,
                'score': count
            }
            for keyword, count in keyword_counts.most_common(20)
        ]

        return trending_keywords


# Test
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test():
        analyzer = SocialTrendAnalyzer()

        # Test TikTok
        print("\n" + "="*60)
        print("TIKTOK TRENDING")
        print("="*60)
        tiktok_trends = await analyzer.get_tiktok_trending(count=10)
        for i, trend in enumerate(tiktok_trends[:5], 1):
            print(f"{i}. {trend['title'][:50]} - {trend['views']:,} views (Score: {trend['score']:,})")

        # Test Instagram
        print("\n" + "="*60)
        print("INSTAGRAM REELS TRENDING")
        print("="*60)
        instagram_trends = analyzer.get_instagram_trending_by_hashtags(
            hashtags=["trending", "viral"],
            amount_per_tag=10
        )
        for i, trend in enumerate(instagram_trends[:5], 1):
            print(f"{i}. {trend['title'][:50]} - {trend['likes']:,} likes (Score: {trend['score']:,})")

        # Combined
        print("\n" + "="*60)
        print("COMBINED TOP TRENDS")
        print("="*60)
        combined = await analyzer.get_combined_trending(
            tiktok_count=20,
            instagram_hashtags=["deutschland", "viral"],
            top_n=10
        )
        for i, trend in enumerate(combined, 1):
            print(f"{i}. [{trend['platform'].upper()}] {trend['title'][:40]} (Score: {trend['score']:,})")

        # Trending keywords
        print("\n" + "="*60)
        print("TRENDING KEYWORDS")
        print("="*60)
        keywords = analyzer.get_trending_keywords_from_content(combined)
        for i, kw in enumerate(keywords[:10], 1):
            print(f"{i}. #{kw['keyword']} ({kw['frequency']} times)")

    # Run async test
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(test())
