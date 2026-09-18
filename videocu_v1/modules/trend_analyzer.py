"""
VIDEOCU v1 - Trend Analyzer Module
Google Trends ve YouTube Data API ile GERÇEK trend analizi
"""

from pytrends.request import TrendReq
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
import requests
from xml.etree import ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


# YouTube Official Categories (44 categories)
YOUTUBE_CATEGORIES = {
    '1': 'Film & Animation',
    '2': 'Autos & Vehicles',
    '10': 'Music',
    '15': 'Pets & Animals',
    '17': 'Sports',
    '19': 'Travel & Events',
    '20': 'Gaming',
    '22': 'People & Blogs',
    '23': 'Comedy',
    '24': 'Entertainment',
    '25': 'News & Politics',
    '26': 'Howto & Style',
    '27': 'Education',
    '28': 'Science & Technology',
    '29': 'Nonprofits & Activism',
}

# German translations for display
YOUTUBE_CATEGORIES_DE = {
    '1': 'Film & Animation',
    '2': 'Autos & Fahrzeuge',
    '10': 'Musik',
    '15': 'Haustiere & Tiere',
    '17': 'Sport',
    '19': 'Reisen & Events',
    '20': 'Gaming',
    '22': 'People & Blogs',
    '23': 'Komödie',
    '24': 'Unterhaltung',
    '25': 'Nachrichten & Politik',
    '26': 'Howto & Style',
    '27': 'Bildung',
    '28': 'Wissenschaft & Technik',
    '29': 'Nonprofits & Aktivismus',
}

# Tarih aralığı seçenekleri
TIME_RANGES = {
    'now': {'label': 'Anlık', 'pytrends': 'now 1-H', 'days': 0},
    '24h': {'label': 'Son 24 Saat', 'pytrends': 'now 1-d', 'days': 1},
    '7d': {'label': 'Son 7 Gün', 'pytrends': 'now 7-d', 'days': 7},
    '30d': {'label': 'Son 1 Ay', 'pytrends': 'today 1-m', 'days': 30},
    '90d': {'label': 'Son 3 Ay', 'pytrends': 'today 3-m', 'days': 90},
}


class TrendAnalyzer:
    """Google Trends ve YouTube API ile trend analizi"""

    def __init__(self, youtube_api_key: str = None):
        self.youtube_api_key = youtube_api_key
        self.pytrends = None
        self.youtube = None
        self._init_apis()

    def _init_apis(self):
        """API'leri başlat"""
        try:
            # Google Trends (API key gerekmez)
            self.pytrends = TrendReq(hl='de-DE', tz=60)
            logger.info("✅ Google Trends initialized")
        except Exception as e:
            logger.error(f"❌ Google Trends initialization failed: {e}")

        # YouTube Data API (isteğe bağlı)
        if self.youtube_api_key:
            try:
                self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
                logger.info("✅ YouTube Data API initialized")
            except Exception as e:
                logger.error(f"❌ YouTube API initialization failed: {e}")

    def get_trending_searches_germany(self, limit: int = 10) -> List[Dict]:
        """
        Almanya'dan trending aramalar (Google Trends)
        Önce pytrends dener, başarısız olursa RSS fallback kullanır

        Returns:
            List of trending topics with metadata
        """
        # Önce RSS'i dene (daha güvenilir)
        results = self._get_trends_via_rss(limit)
        if results:
            return results

        # RSS başarısız olursa pytrends dene
        try:
            logger.info("🔍 Fetching trending searches from Germany via pytrends...")

            # Google Trends - Germany
            trending_df = self.pytrends.trending_searches(pn='germany')

            results = []
            for i, keyword in enumerate(trending_df[0].head(limit).tolist()):
                trend = {
                    'keyword': keyword,
                    'rank': i + 1,
                    'region': 'DE',
                    'score': 100 - (i * 5),  # Simulated score
                    'discovered_at': datetime.now().isoformat()
                }

                # Get interest over time
                try:
                    self.pytrends.build_payload([keyword], timeframe='now 7-d', geo='DE')
                    interest_df = self.pytrends.interest_over_time()

                    if not interest_df.empty:
                        avg_interest = int(interest_df[keyword].mean())
                        trend['avg_interest'] = avg_interest
                        trend['score'] = avg_interest

                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.warning(f"Could not get interest for {keyword}: {e}")

                results.append(trend)
                logger.info(f"  {i+1}. {keyword} (Score: {trend['score']})")

            logger.info(f"✅ Found {len(results)} trending topics")
            return results

        except Exception as e:
            logger.error(f"❌ Error fetching trends via pytrends: {e}")
            return []

    def _get_trends_via_rss(self, limit: int = 20) -> List[Dict]:
        """
        Google Trends RSS feed üzerinden trending aramaları al
        Pytrends'e göre daha güvenilir çalışır
        """
        try:
            logger.info("🔍 Fetching trending searches from Germany via RSS...")

            rss_url = "https://trends.google.de/trending/rss?geo=DE"

            response = requests.get(rss_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'de-DE,de;q=0.9'
            }, timeout=15)

            if response.status_code != 200:
                logger.warning(f"RSS feed returned status {response.status_code}")
                return []

            root = ET.fromstring(response.content)
            items = root.findall('.//item')

            results = []
            ns = {'ht': 'https://trends.google.com/trending/rss'}

            # Önce tüm item'ları oku
            for item in items:
                title = item.find('title')
                traffic = item.find('ht:approx_traffic', ns)
                link = item.find('link')
                picture = item.find('ht:picture', ns)
                news_item = item.find('ht:news_item', ns)

                if title is not None:
                    keyword = title.text
                    score = self._parse_traffic(traffic.text if traffic is not None else '')

                    # Haber URL'sini al
                    news_url = ''
                    news_title = ''
                    if news_item is not None:
                        news_url_elem = news_item.find('ht:news_item_url', ns)
                        news_title_elem = news_item.find('ht:news_item_title', ns)
                        if news_url_elem is not None:
                            news_url = news_url_elem.text
                        if news_title_elem is not None:
                            news_title = news_title_elem.text

                    trend = {
                        'keyword': keyword,
                        'region': 'DE',
                        'score': score,
                        'traffic_raw': traffic.text if traffic is not None else '0',
                        'source': 'google_trends_rss',
                        'link': link.text if link is not None else '',
                        'thumbnail': picture.text if picture is not None else '',
                        'news_url': news_url,
                        'news_title': news_title,
                        'discovered_at': datetime.now().isoformat()
                    }
                    results.append(trend)

            # Score'a (traffic) göre sırala - en yüksek önce
            results.sort(key=lambda x: x['score'], reverse=True)

            # Sıralamadan sonra rank ata ve limit uygula
            for i, trend in enumerate(results[:limit]):
                trend['rank'] = i + 1
                logger.info(f"  {i+1}. {trend['keyword']} (Traffic: {trend['traffic_raw']})")

            logger.info(f"✅ Found {len(results[:limit])} trending topics via RSS (sorted by popularity)")
            return results[:limit]

        except Exception as e:
            logger.error(f"❌ RSS feed error: {e}")
            return []

    def _parse_traffic(self, traffic_str: str) -> int:
        """Traffic string'ini sayıya çevir (örn: '100K+' -> 100000)"""
        if not traffic_str:
            return 0

        traffic_str = traffic_str.replace('+', '').replace(',', '').strip()

        multipliers = {'K': 1000, 'M': 1000000, 'B': 1000000000}

        for suffix, multiplier in multipliers.items():
            if suffix in traffic_str.upper():
                try:
                    num = float(traffic_str.upper().replace(suffix, ''))
                    return int(num * multiplier)
                except ValueError:
                    pass

        try:
            return int(traffic_str)
        except ValueError:
            return 0

    def get_youtube_trending_videos(self, region_code: str = 'DE',
                                   category_id: str = None,
                                   max_results: int = 10) -> List[Dict]:
        """
        YouTube'dan trending videolar

        Args:
            region_code: Country code (DE, US, GB, TR, etc.)
            category_id: YouTube category ID (optional)
            max_results: Number of results

        Returns:
            List of trending videos with metadata
        """
        if not self.youtube:
            logger.warning("⚠️ YouTube API not initialized")
            return []

        try:
            logger.info(f"🔍 Fetching YouTube trending videos from {region_code}...")

            request_params = {
                'part': 'snippet,statistics,contentDetails',
                'chart': 'mostPopular',
                'regionCode': region_code,
                'maxResults': max_results
            }

            if category_id:
                request_params['videoCategoryId'] = category_id

            request = self.youtube.videos().list(**request_params)
            response = request.execute()

            results = []
            for item in response.get('items', []):
                snippet = item['snippet']
                stats = item['statistics']

                video = {
                    'video_id': item['id'],
                    'title': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'description': snippet['description'][:200],
                    'published_at': snippet['publishedAt'],
                    'thumbnail': snippet['thumbnails']['high']['url'],
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                    'url': f"https://www.youtube.com/watch?v={item['id']}",
                    'region': region_code
                }

                results.append(video)
                logger.info(f"  📹 {video['title']} ({video['views']:,} views)")

            logger.info(f"✅ Found {len(results)} trending videos")
            return results

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching YouTube trends: {e}")
            return []

    def search_youtube_by_keyword(self, keyword: str, region_code: str = 'DE',
                                  max_results: int = 5) -> List[Dict]:
        """
        YouTube'da keyword araması

        Args:
            keyword: Search term
            region_code: Country code
            max_results: Number of results

        Returns:
            List of search results
        """
        if not self.youtube:
            logger.warning("⚠️ YouTube API not initialized")
            return []

        try:
            logger.info(f"🔍 Searching YouTube for '{keyword}' in {region_code}...")

            request = self.youtube.search().list(
                part='snippet',
                q=keyword,
                type='video',
                regionCode=region_code,
                maxResults=max_results,
                order='viewCount'
            )

            response = request.execute()

            results = []
            for item in response.get('items', []):
                snippet = item['snippet']

                video = {
                    'video_id': item['id']['videoId'],
                    'title': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'description': snippet['description'][:200],
                    'published_at': snippet['publishedAt'],
                    'thumbnail': snippet['thumbnails']['high']['url'],
                    'url': f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                }

                results.append(video)

            logger.info(f"✅ Found {len(results)} videos for '{keyword}'")
            return results

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error searching YouTube: {e}")
            return []

    def get_youtube_trending_by_category(self, category_id: str,
                                        region_code: str = 'DE',
                                        max_results: int = 10) -> List[Dict]:
        """
        YouTube'dan kategori bazlı trending videolar

        Args:
            category_id: YouTube category ID ('1'-'29')
            region_code: Country code (DE, US, GB, etc.)
            max_results: Number of results (max 50)

        Returns:
            List of trending videos for the category
        """
        if not self.youtube:
            logger.warning("⚠️ YouTube API not initialized")
            return []

        try:
            category_name = YOUTUBE_CATEGORIES_DE.get(category_id, f"Category {category_id}")
            logger.info(f"🔍 Fetching trending videos for {category_name} in {region_code}...")

            request = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                chart='mostPopular',
                regionCode=region_code,
                videoCategoryId=category_id,
                maxResults=min(max_results, 50)  # YouTube API max is 50
            )

            response = request.execute()

            results = []
            for item in response.get('items', []):
                snippet = item['snippet']
                stats = item['statistics']

                video = {
                    'platform': 'youtube',
                    'video_id': item['id'],
                    'title': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'description': snippet['description'][:200],
                    'published_at': snippet['publishedAt'],
                    'thumbnail': snippet['thumbnails']['high']['url'],
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                    'url': f"https://www.youtube.com/watch?v={item['id']}",
                    'region': region_code,
                    'category_id': category_id,
                    'category': category_name,
                    'score': self._calculate_video_score(
                        int(stats.get('viewCount', 0)),
                        int(stats.get('likeCount', 0)),
                        int(stats.get('commentCount', 0))
                    )
                }

                results.append(video)

            # Sort by score
            results.sort(key=lambda x: x['score'], reverse=True)

            logger.info(f"✅ Found {len(results)} trending videos for {category_name}")
            return results

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching category trends: {e}")
            return []

    def _calculate_video_score(self, views: int, likes: int, comments: int) -> int:
        """
        Calculate engagement score for YouTube video

        Formula: (views * 0.01) + (likes * 2) + (comments * 5)
        """
        return int((views * 0.01) + (likes * 2) + (comments * 5))

    def get_all_categories_trending(self, region_code: str = 'DE',
                                   videos_per_category: int = 5) -> Dict[str, List[Dict]]:
        """
        Tüm kategorilerden trending videolar al

        Args:
            region_code: Country code
            videos_per_category: Videos per category

        Returns:
            Dictionary with category_id as key and video list as value
        """
        if not self.youtube:
            logger.warning("⚠️ YouTube API not initialized")
            return {}

        logger.info(f"🔍 Fetching trending videos from all categories...")

        results = {}
        for category_id, category_name in YOUTUBE_CATEGORIES_DE.items():
            try:
                videos = self.get_youtube_trending_by_category(
                    category_id=category_id,
                    region_code=region_code,
                    max_results=videos_per_category
                )
                if videos:
                    results[category_id] = videos
                    logger.info(f"  ✓ {category_name}: {len(videos)} videos")

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.warning(f"  ⚠ Failed to fetch {category_name}: {e}")
                continue

        logger.info(f"✅ Fetched trending from {len(results)}/{len(YOUTUBE_CATEGORIES_DE)} categories")
        return results

    def get_related_queries(self, keyword: str, region: str = 'DE') -> Dict:
        """
        İlgili aramalar (Google Trends)

        Args:
            keyword: Main keyword
            region: Country code

        Returns:
            Related queries (rising and top)
        """
        try:
            logger.info(f"🔍 Getting related queries for '{keyword}'...")

            self.pytrends.build_payload([keyword], timeframe='now 7-d', geo=region)
            related = self.pytrends.related_queries()

            result = {
                'keyword': keyword,
                'rising': [],
                'top': []
            }

            if keyword in related:
                # Rising queries
                if related[keyword]['rising'] is not None:
                    rising_df = related[keyword]['rising'].head(5)
                    result['rising'] = rising_df['query'].tolist()

                # Top queries
                if related[keyword]['top'] is not None:
                    top_df = related[keyword]['top'].head(5)
                    result['top'] = top_df['query'].tolist()

            logger.info(f"✅ Found {len(result['rising'])} rising and {len(result['top'])} top queries")
            return result

        except Exception as e:
            logger.error(f"❌ Error getting related queries: {e}")
            return {'keyword': keyword, 'rising': [], 'top': []}

    def get_trends_by_timerange(self, keywords: List[str], time_range: str = '7d',
                                  region: str = 'DE') -> List[Dict]:
        """
        Belirli tarih aralığında trend analizi (Google Trends)

        Args:
            keywords: Aranacak keywordler (boş ise trending topics)
            time_range: Tarih aralığı ('now', '24h', '7d', '30d', '90d')
            region: Ülke kodu

        Returns:
            Trend listesi ile interest verileri
        """
        try:
            time_config = TIME_RANGES.get(time_range, TIME_RANGES['7d'])
            timeframe = time_config['pytrends']

            logger.info(f"🔍 Fetching trends for {time_config['label']} in {region}...")

            results = []

            # Eğer keyword listesi boş ise, trending searches al
            if not keywords:
                keywords = [t['keyword'] for t in self.get_trending_searches_germany(limit=10)]

            for keyword in keywords[:10]:  # Max 10 keyword (rate limiting)
                try:
                    self.pytrends.build_payload([keyword], timeframe=timeframe, geo=region)
                    interest_df = self.pytrends.interest_over_time()

                    trend_data = {
                        'keyword': keyword,
                        'platform': 'google',
                        'time_range': time_range,
                        'region': region,
                        'score': 0,
                        'avg_interest': 0,
                        'peak_interest': 0,
                        'current_interest': 0,
                        'trend_direction': 'unknown',
                        'data_points': []
                    }

                    if not interest_df.empty and keyword in interest_df.columns:
                        values = interest_df[keyword].values
                        trend_data['avg_interest'] = int(values.mean())
                        trend_data['peak_interest'] = int(values.max())
                        trend_data['current_interest'] = int(values[-1])
                        trend_data['score'] = trend_data['avg_interest']

                        # Trend yönü
                        if len(values) > 1:
                            change = values[-1] - values[0]
                            if change > 10:
                                trend_data['trend_direction'] = 'rising'
                            elif change < -10:
                                trend_data['trend_direction'] = 'falling'
                            else:
                                trend_data['trend_direction'] = 'stable'

                        # Grafik için data points
                        trend_data['data_points'] = values.tolist()[-30:]  # Son 30 nokta

                    results.append(trend_data)
                    time.sleep(0.3)  # Rate limiting

                except Exception as e:
                    logger.warning(f"   Skipped '{keyword}': {e}")
                    continue

            # Score'a göre sırala
            results.sort(key=lambda x: x['score'], reverse=True)
            logger.info(f"✅ Analyzed {len(results)} keywords for {time_config['label']}")
            return results

        except Exception as e:
            logger.error(f"❌ Error in time-range trends: {e}")
            return []

    def search_youtube_by_timerange(self, query: str = None, time_range: str = '7d',
                                     region_code: str = 'DE', max_results: int = 10,
                                     order: str = 'viewCount') -> List[Dict]:
        """
        YouTube'da tarih filtreli arama

        Args:
            query: Arama terimi (None ise genel trending)
            time_range: Tarih aralığı ('24h', '7d', '30d', '90d')
            region_code: Ülke kodu
            max_results: Sonuç sayısı
            order: Sıralama (viewCount, date, rating, relevance)

        Returns:
            Video listesi
        """
        if not self.youtube:
            logger.warning("⚠️ YouTube API not initialized")
            return []

        try:
            time_config = TIME_RANGES.get(time_range, TIME_RANGES['7d'])
            days = time_config['days']

            # Tarih hesapla
            if days > 0:
                published_after = (datetime.utcnow() - timedelta(days=days)).isoformat() + 'Z'
            else:
                published_after = (datetime.utcnow() - timedelta(hours=24)).isoformat() + 'Z'

            logger.info(f"🔍 Searching YouTube ({time_config['label']}) in {region_code}...")

            search_params = {
                'part': 'snippet',
                'type': 'video',
                'regionCode': region_code,
                'maxResults': min(max_results, 50),
                'order': order,
                'publishedAfter': published_after
            }

            if query:
                search_params['q'] = query

            request = self.youtube.search().list(**search_params)
            response = request.execute()

            # Video ID'lerini topla
            video_ids = [item['id']['videoId'] for item in response.get('items', [])]

            if not video_ids:
                return []

            # Video detaylarını al (statistics için)
            videos_request = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                id=','.join(video_ids)
            )
            videos_response = videos_request.execute()

            results = []
            for item in videos_response.get('items', []):
                snippet = item['snippet']
                stats = item['statistics']

                video = {
                    'platform': 'youtube',
                    'video_id': item['id'],
                    'title': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'author': snippet['channelTitle'],
                    'description': snippet['description'][:200],
                    'published_at': snippet['publishedAt'],
                    'thumbnail': snippet['thumbnails']['high']['url'],
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                    'url': f"https://www.youtube.com/watch?v={item['id']}",
                    'region': region_code,
                    'time_range': time_range,
                    'score': self._calculate_video_score(
                        int(stats.get('viewCount', 0)),
                        int(stats.get('likeCount', 0)),
                        int(stats.get('commentCount', 0))
                    )
                }
                results.append(video)

            # Score'a göre sırala
            results.sort(key=lambda x: x['score'], reverse=True)
            logger.info(f"✅ Found {len(results)} videos for {time_config['label']}")
            return results

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error in YouTube time-range search: {e}")
            return []

    def analyze_trend_potential(self, keyword: str, region: str = 'DE') -> Dict:
        """
        Trend potansiyelini analiz et

        Args:
            keyword: Keyword to analyze
            region: Country code

        Returns:
            Analysis with score and recommendations
        """
        try:
            logger.info(f"📊 Analyzing trend potential for '{keyword}'...")

            # Get interest over time
            self.pytrends.build_payload([keyword], timeframe='now 7-d', geo=region)
            interest_df = self.pytrends.interest_over_time()

            analysis = {
                'keyword': keyword,
                'region': region,
                'score': 0,
                'trend_direction': 'unknown',
                'recommendation': 'insufficient_data'
            }

            if not interest_df.empty and keyword in interest_df.columns:
                values = interest_df[keyword].values

                # Calculate metrics
                avg_interest = int(values.mean())
                current_interest = int(values[-1])
                max_interest = int(values.max())

                # Trend direction
                if len(values) > 1:
                    trend = values[-1] - values[0]
                    if trend > 10:
                        analysis['trend_direction'] = 'rising'
                    elif trend < -10:
                        analysis['trend_direction'] = 'falling'
                    else:
                        analysis['trend_direction'] = 'stable'

                # Score (0-100)
                score = min(100, int((avg_interest + current_interest) / 2))
                analysis['score'] = score

                # Recommendation
                if score >= 70 and analysis['trend_direction'] == 'rising':
                    analysis['recommendation'] = 'excellent'
                elif score >= 50:
                    analysis['recommendation'] = 'good'
                elif score >= 30:
                    analysis['recommendation'] = 'moderate'
                else:
                    analysis['recommendation'] = 'low'

                analysis['metrics'] = {
                    'avg_interest': avg_interest,
                    'current_interest': current_interest,
                    'max_interest': max_interest
                }

                logger.info(f"✅ Score: {score}/100, Direction: {analysis['trend_direction']}, Recommendation: {analysis['recommendation']}")

            return analysis

        except Exception as e:
            logger.error(f"❌ Error analyzing trend: {e}")
            return analysis


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    analyzer = TrendAnalyzer()

    # Test 1: Germany trending searches
    print("\n" + "="*50)
    print("TEST 1: Germany Trending Searches")
    print("="*50)
    trends = analyzer.get_trending_searches_germany(limit=5)
    for trend in trends:
        print(f"{trend['rank']}. {trend['keyword']} (Score: {trend['score']})")

    # Test 2: Analyze first trend
    if trends:
        print("\n" + "="*50)
        print(f"TEST 2: Analyze '{trends[0]['keyword']}'")
        print("="*50)
        analysis = analyzer.analyze_trend_potential(trends[0]['keyword'])
        print(f"Score: {analysis['score']}/100")
        print(f"Direction: {analysis['trend_direction']}")
        print(f"Recommendation: {analysis['recommendation']}")
