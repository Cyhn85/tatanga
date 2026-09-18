"""
VIDEOCU v1 - Cross-Platform Trend Analysis
Google Trends, YouTube, TikTok ve Instagram verilerini birleştirerek potansiyel trendleri tespit eder
"""

import logging
from typing import List, Dict, Optional
from collections import Counter
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class CrossAnalyzer:
    """Çoklu platform trend analizi"""

    def __init__(self):
        pass

    def analyze_cross_platform_trends(self,
                                     google_trends: List[Dict],
                                     youtube_videos: List[Dict],
                                     tiktok_videos: List[Dict],
                                     instagram_reels: List[Dict]) -> Dict:
        """
        Tüm platformlardan gelen verileri analiz et ve kesişimleri bul

        Args:
            google_trends: Google Trends sonuçları
            youtube_videos: YouTube trending videoları
            tiktok_videos: TikTok trending videoları
            instagram_reels: Instagram Reels

        Returns:
            Cross-analysis sonuçları
        """
        logger.info("🔥 Starting cross-platform trend analysis...")

        # Extract keywords from all sources
        google_keywords = self._extract_google_keywords(google_trends)
        youtube_keywords = self._extract_video_keywords(youtube_videos)
        tiktok_keywords = self._extract_video_keywords(tiktok_videos)
        instagram_keywords = self._extract_video_keywords(instagram_reels)

        # Find intersections
        all_keywords = (
            google_keywords +
            youtube_keywords +
            tiktok_keywords +
            instagram_keywords
        )

        # Count keyword frequencies across platforms
        keyword_counter = Counter(all_keywords)

        # Find keywords appearing in multiple platforms
        cross_platform_keywords = []
        for keyword, count in keyword_counter.most_common(50):
            platforms = []
            if keyword.lower() in [k.lower() for k in google_keywords]:
                platforms.append('google')
            if keyword.lower() in [k.lower() for k in youtube_keywords]:
                platforms.append('youtube')
            if keyword.lower() in [k.lower() for k in tiktok_keywords]:
                platforms.append('tiktok')
            if keyword.lower() in [k.lower() for k in instagram_keywords]:
                platforms.append('instagram')

            if len(platforms) >= 2:  # Appears in at least 2 platforms
                cross_platform_keywords.append({
                    'keyword': keyword,
                    'platforms': platforms,
                    'platform_count': len(platforms),
                    'frequency': count,
                    'score': count * len(platforms) * 10  # Higher score for more platforms
                })

        # Sort by score
        cross_platform_keywords.sort(key=lambda x: x['score'], reverse=True)

        # Identify potential viral content
        potential_trends = self._identify_potential_trends(
            youtube_videos,
            tiktok_videos,
            instagram_reels,
            cross_platform_keywords
        )

        result = {
            'cross_platform_keywords': cross_platform_keywords[:20],
            'potential_trends': potential_trends,
            'platform_stats': {
                'google_trends': len(google_trends),
                'youtube_videos': len(youtube_videos),
                'tiktok_videos': len(tiktok_videos),
                'instagram_reels': len(instagram_reels),
                'total_content': len(youtube_videos) + len(tiktok_videos) + len(instagram_reels)
            },
            'top_trending_topic': cross_platform_keywords[0]['keyword'] if cross_platform_keywords else None
        }

        logger.info(f"✅ Cross-analysis complete: {len(cross_platform_keywords)} cross-platform keywords found")
        return result

    def _extract_google_keywords(self, trends: List[Dict]) -> List[str]:
        """Google Trends'den keyword'leri çıkar"""
        keywords = []
        for trend in trends:
            keyword = trend.get('keyword', '')
            if keyword:
                keywords.append(keyword)
        return keywords

    def _extract_video_keywords(self, videos: List[Dict]) -> List[str]:
        """Video başlık ve açıklamalarından keyword'leri çıkar"""
        keywords = []
        for video in videos:
            title = video.get('title', '')

            # Extract hashtags
            hashtags = re.findall(r'#(\w+)', title)
            keywords.extend(hashtags)

            # Extract significant words (4+ characters)
            words = re.findall(r'\b[a-zA-ZäöüßÄÖÜ]{4,}\b', title.lower())
            keywords.extend(words)

        return keywords

    def _identify_potential_trends(self,
                                  youtube_videos: List[Dict],
                                  tiktok_videos: List[Dict],
                                  instagram_reels: List[Dict],
                                  cross_keywords: List[Dict]) -> List[Dict]:
        """
        Potansiyel viral olabilecek içerikleri tespit et

        Kriterler:
        - Yüksek engagement rate
        - Çoklu platformda görünme
        - Yükselen momentum
        """
        potential = []

        # Combine all videos
        all_content = []
        for video in youtube_videos:
            video_copy = video.copy()
            video_copy['platform'] = 'youtube'
            all_content.append(video_copy)

        for video in tiktok_videos:
            video_copy = video.copy()
            video_copy['platform'] = 'tiktok'
            all_content.append(video_copy)

        for reel in instagram_reels:
            reel_copy = reel.copy()
            reel_copy['platform'] = 'instagram'
            all_content.append(reel_copy)

        # Analyze each content
        for content in all_content:
            title = content.get('title', '').lower()

            # Check if content matches cross-platform keywords
            matches = []
            for kw in cross_keywords[:10]:  # Top 10 cross-platform keywords
                if kw['keyword'].lower() in title:
                    matches.append(kw['keyword'])

            if matches and len(matches) > 0:
                # Calculate potential score
                engagement_score = content.get('score', 0)
                keyword_score = sum([kw['score'] for kw in cross_keywords if kw['keyword'] in matches])

                potential.append({
                    'platform': content['platform'],
                    'title': content.get('title', '')[:100],
                    'url': content.get('url', ''),
                    'views': content.get('views', 0),
                    'likes': content.get('likes', 0),
                    'comments': content.get('comments', 0),
                    'matched_keywords': matches,
                    'engagement_score': engagement_score,
                    'keyword_score': keyword_score,
                    'total_score': engagement_score + keyword_score,
                    'author': content.get('author', '') or content.get('channel', '')
                })

        # Sort by total score
        potential.sort(key=lambda x: x['total_score'], reverse=True)

        logger.info(f"  💎 Identified {len(potential[:20])} potential viral trends")
        return potential[:20]  # Top 20

    def get_platform_comparison(self,
                               youtube_videos: List[Dict],
                               tiktok_videos: List[Dict],
                               instagram_reels: List[Dict]) -> Dict:
        """
        Platform bazlı karşılaştırma

        Returns:
            Platform statistics and comparison
        """
        logger.info("📊 Generating platform comparison...")

        def calc_avg(items, key):
            if not items:
                return 0
            return sum([item.get(key, 0) for item in items]) / len(items)

        youtube_stats = {
            'total_videos': len(youtube_videos),
            'avg_views': calc_avg(youtube_videos, 'views'),
            'avg_likes': calc_avg(youtube_videos, 'likes'),
            'avg_comments': calc_avg(youtube_videos, 'comments'),
            'total_engagement': sum([v.get('score', 0) for v in youtube_videos])
        }

        tiktok_stats = {
            'total_videos': len(tiktok_videos),
            'avg_views': calc_avg(tiktok_videos, 'views'),
            'avg_likes': calc_avg(tiktok_videos, 'likes'),
            'avg_comments': calc_avg(tiktok_videos, 'comments'),
            'total_engagement': sum([v.get('score', 0) for v in tiktok_videos])
        }

        instagram_stats = {
            'total_reels': len(instagram_reels),
            'avg_views': calc_avg(instagram_reels, 'views'),
            'avg_likes': calc_avg(instagram_reels, 'likes'),
            'avg_comments': calc_avg(instagram_reels, 'comments'),
            'total_engagement': sum([v.get('score', 0) for v in instagram_reels])
        }

        # Determine best platform
        engagements = [
            ('youtube', youtube_stats['total_engagement']),
            ('tiktok', tiktok_stats['total_engagement']),
            ('instagram', instagram_stats['total_engagement'])
        ]
        best_platform = max(engagements, key=lambda x: x[1])[0]

        comparison = {
            'youtube': youtube_stats,
            'tiktok': tiktok_stats,
            'instagram': instagram_stats,
            'best_platform': best_platform,
            'total_content_analyzed': len(youtube_videos) + len(tiktok_videos) + len(instagram_reels)
        }

        logger.info(f"✅ Platform comparison complete. Best platform: {best_platform}")
        return comparison

    def find_emerging_trends(self,
                           google_trends: List[Dict],
                           youtube_videos: List[Dict],
                           tiktok_videos: List[Dict],
                           instagram_reels: List[Dict]) -> List[Dict]:
        """
        Yükselen trendleri tespit et

        Kriterler:
        - Google Trends'de yükselen
        - Henüz çok fazla içerik yok (erken keşif)
        - Yüksek engagement potansiyeli
        """
        logger.info("🚀 Searching for emerging trends...")

        emerging = []

        # Google Trends'deki yükselen konular
        for trend in google_trends:
            keyword = trend.get('keyword', '')
            trend_direction = trend.get('trend_direction', 'unknown')

            # Only rising trends
            if 'rising' not in trend_direction.lower():
                continue

            # Count how many videos exist for this keyword
            youtube_count = sum([1 for v in youtube_videos if keyword.lower() in v.get('title', '').lower()])
            tiktok_count = sum([1 for v in tiktok_videos if keyword.lower() in v.get('title', '').lower()])
            instagram_count = sum([1 for v in instagram_reels if keyword.lower() in v.get('title', '').lower()])

            total_count = youtube_count + tiktok_count + instagram_count

            # Emerging criteria: Few videos but high search interest
            if total_count < 5 and trend.get('score', 0) > 50:
                emerging.append({
                    'keyword': keyword,
                    'google_score': trend.get('score', 0),
                    'existing_videos': total_count,
                    'youtube_count': youtube_count,
                    'tiktok_count': tiktok_count,
                    'instagram_count': instagram_count,
                    'opportunity_score': trend.get('score', 0) / max(total_count, 1) * 10,
                    'recommendation': 'HIGH OPPORTUNITY - Create content NOW!'
                })

        # Sort by opportunity score
        emerging.sort(key=lambda x: x['opportunity_score'], reverse=True)

        logger.info(f"✅ Found {len(emerging)} emerging trend opportunities")
        return emerging[:10]  # Top 10 opportunities


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Mock data for testing
    google_trends = [
        {'keyword': 'AI trends 2025', 'score': 85, 'trend_direction': 'rising'},
        {'keyword': 'Deutschland Fußball', 'score': 92, 'trend_direction': 'rising'},
    ]

    youtube_videos = [
        {'title': 'AI trends 2025 explained', 'views': 50000, 'likes': 2000, 'comments': 100, 'score': 5000},
        {'title': 'Deutschland Fußball highlights', 'views': 100000, 'likes': 5000, 'comments': 300, 'score': 10000}
    ]

    tiktok_videos = [
        {'title': '#AI #trends #2025', 'views': 200000, 'likes': 10000, 'comments': 500, 'score': 20000}
    ]

    instagram_reels = [
        {'title': 'Deutschland Fußball ⚽', 'views': 80000, 'likes': 4000, 'comments': 200, 'score': 8000}
    ]

    analyzer = CrossAnalyzer()

    print("\n" + "="*60)
    print("CROSS-PLATFORM ANALYSIS")
    print("="*60)

    result = analyzer.analyze_cross_platform_trends(
        google_trends, youtube_videos, tiktok_videos, instagram_reels
    )

    print(f"\n📊 Cross-Platform Keywords:")
    for kw in result['cross_platform_keywords'][:5]:
        print(f"  {kw['keyword']} - {kw['platform_count']} platforms (Score: {kw['score']})")

    print(f"\n💎 Potential Viral Trends:")
    for trend in result['potential_trends'][:3]:
        print(f"  [{trend['platform'].upper()}] {trend['title'][:50]} (Score: {trend['total_score']:,})")

    print(f"\n🚀 Emerging Opportunities:")
    emerging = analyzer.find_emerging_trends(
        google_trends, youtube_videos, tiktok_videos, instagram_reels
    )
    for opp in emerging[:3]:
        print(f"  {opp['keyword']} - Opportunity Score: {opp['opportunity_score']:.1f}")
        print(f"    {opp['recommendation']}")
