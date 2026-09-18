"""
VIDEOCU v1 - Transcript Extractor Module
YouTube videolarından transkript çıkarma
"""

import logging
import re
from typing import Dict, List, Optional
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from datetime import datetime

logger = logging.getLogger(__name__)


class TranscriptExtractor:
    """YouTube videolarından transkript çıkarma"""

    LANGUAGE_PRIORITY = {
        'de': ['de', 'de-DE', 'en', 'en-US'],
        'tr': ['tr', 'tr-TR', 'en', 'en-US'],
        'en': ['en', 'en-US', 'en-GB', 'de'],
    }

    def __init__(self, preferred_language: str = 'de'):
        self.preferred_language = preferred_language
        self.cache = {}

    def extract_video_id(self, url: str) -> Optional[str]:
        """YouTube URL'den video ID çıkar"""
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:embed/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_transcript(self, video_id_or_url: str, language: str = None) -> Dict:
        """
        YouTube videosundan transkript al

        Args:
            video_id_or_url: Video ID veya tam URL
            language: Tercih edilen dil (None ise varsayılan)

        Returns:
            Dict with transcript text, language, and metadata
        """
        # Video ID çıkar
        video_id = self.extract_video_id(video_id_or_url)
        if not video_id:
            video_id = video_id_or_url

        # Cache kontrol
        cache_key = f"{video_id}_{language or self.preferred_language}"
        if cache_key in self.cache:
            logger.info(f"📋 Cache hit for {video_id}")
            return self.cache[cache_key]

        lang = language or self.preferred_language
        lang_priority = self.LANGUAGE_PRIORITY.get(lang, ['en', 'de'])

        result = {
            'video_id': video_id,
            'success': False,
            'language': None,
            'transcript_text': '',
            'segments': [],
            'duration_seconds': 0,
            'word_count': 0,
            'error': None,
            'extracted_at': datetime.now().isoformat()
        }

        try:
            logger.info(f"🔍 Fetching transcript for {video_id}...")

            segments = None
            used_lang = None

            # Tercih sırasına göre dene
            for try_lang in lang_priority:
                try:
                    segments = YouTubeTranscriptApi.get_transcript(video_id, languages=[try_lang])
                    used_lang = try_lang
                    break
                except Exception:
                    continue

            # Hiçbiri bulunamadıysa herhangi birini dene
            if not segments:
                try:
                    segments = YouTubeTranscriptApi.get_transcript(video_id)
                    used_lang = 'auto'
                except Exception:
                    pass

            if segments:
                # Metni birleştir
                full_text = ' '.join([seg['text'] for seg in segments])

                # Toplam süre
                if segments:
                    last_seg = segments[-1]
                    duration = last_seg['start'] + last_seg.get('duration', 0)
                else:
                    duration = 0

                result['success'] = True
                result['language'] = used_lang
                result['transcript_text'] = full_text
                result['segments'] = segments
                result['duration_seconds'] = int(duration)
                result['word_count'] = len(full_text.split())

                logger.info(f"✅ Transcript fetched: {result['word_count']} words, {used_lang}")

                # Cache'e ekle
                self.cache[cache_key] = result

            else:
                result['error'] = 'No transcript available in any language'
                logger.warning(f"⚠️ No transcript found for {video_id}")

        except TranscriptsDisabled:
            result['error'] = 'Transcripts are disabled for this video'
            logger.warning(f"⚠️ Transcripts disabled for {video_id}")

        except NoTranscriptFound:
            result['error'] = 'No transcript found'
            logger.warning(f"⚠️ No transcript found for {video_id}")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Error fetching transcript: {e}")

        return result

    def get_transcript_summary(self, video_id_or_url: str, max_chars: int = 500) -> str:
        """Transkriptin özetini döndür (ilk N karakter)"""
        result = self.get_transcript(video_id_or_url)

        if result['success']:
            text = result['transcript_text']
            if len(text) > max_chars:
                return text[:max_chars] + '...'
            return text
        return f"[Transcript error: {result['error']}]"

    def get_key_segments(self, video_id_or_url: str, interval_seconds: int = 30) -> List[Dict]:
        """Belirli aralıklarla önemli segmentleri döndür"""
        result = self.get_transcript(video_id_or_url)

        if not result['success']:
            return []

        key_segments = []
        current_time = 0

        for seg in result['segments']:
            if seg['start'] >= current_time:
                key_segments.append({
                    'time': seg['start'],
                    'time_formatted': self._format_time(seg['start']),
                    'text': seg['text']
                })
                current_time = seg['start'] + interval_seconds

        return key_segments

    def _format_time(self, seconds: float) -> str:
        """Saniyeyi MM:SS formatına çevir"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def batch_extract(self, video_ids: List[str], language: str = None) -> List[Dict]:
        """Birden fazla video için transkript çıkar"""
        results = []

        for vid in video_ids:
            result = self.get_transcript(vid, language)
            results.append(result)

        success_count = sum(1 for r in results if r['success'])
        logger.info(f"📊 Batch extraction: {success_count}/{len(video_ids)} successful")

        return results


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    extractor = TranscriptExtractor(preferred_language='de')

    # Test with a known video
    test_videos = [
        "https://www.youtube.com/watch?v=YFSN-NWFJrg",  # Trending video
        "https://www.youtube.com/watch?v=3oevuma-_Sk",
    ]

    for url in test_videos:
        print(f"\n{'='*50}")
        print(f"Testing: {url}")
        print('='*50)

        result = extractor.get_transcript(url)

        if result['success']:
            print(f"Language: {result['language']}")
            print(f"Words: {result['word_count']}")
            print(f"Duration: {result['duration_seconds']}s")
            print(f"\nFirst 200 chars:")
            print(result['transcript_text'][:200])
        else:
            print(f"Error: {result['error']}")
