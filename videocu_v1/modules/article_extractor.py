"""
VIDEOCU v1 - Article Extractor Module
URL'den makale metni çıkarma - header/footer/reklam olmadan sadece içerik
"""

import logging
import re
from typing import Dict, Optional
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ArticleExtractor:
    """Web URL'lerinden makale metni çıkarma"""

    def __init__(self):
        self.cache = {}

    def extract(self, url: str) -> Dict:
        """
        URL'den makale içeriğini çıkar

        Args:
            url: Makale URL'si

        Returns:
            Dict with title, text, author, date, images
        """
        # Cache kontrol
        if url in self.cache:
            logger.info(f"📋 Cache hit for {url}")
            return self.cache[url]

        result = {
            'url': url,
            'success': False,
            'title': '',
            'text': '',
            'summary': '',
            'author': '',
            'publish_date': '',
            'top_image': '',
            'images': [],
            'word_count': 0,
            'language': '',
            'source': '',
            'error': None,
            'extracted_at': datetime.now().isoformat()
        }

        try:
            # Domain bilgisi
            parsed = urlparse(url)
            result['source'] = parsed.netloc

            # Önce trafilatura dene (en iyi sonuç)
            extracted = self._extract_with_trafilatura(url)
            if extracted and extracted.get('text'):
                result.update(extracted)
                result['success'] = True
                logger.info(f"✅ Trafilatura ile çıkarıldı: {result['word_count']} kelime")
            else:
                # Newspaper3k ile dene
                extracted = self._extract_with_newspaper(url)
                if extracted and extracted.get('text'):
                    result.update(extracted)
                    result['success'] = True
                    logger.info(f"✅ Newspaper ile çıkarıldı: {result['word_count']} kelime")
                else:
                    result['error'] = 'Makale metni çıkarılamadı'
                    logger.warning(f"⚠️ Makale çıkarılamadı: {url}")

            # Cache'e ekle
            if result['success']:
                self.cache[url] = result

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Article extraction error: {e}")

        return result

    def _extract_with_trafilatura(self, url: str) -> Optional[Dict]:
        """Trafilatura ile makale çıkar"""
        try:
            import trafilatura

            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None

            # Metin çıkar
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=True
            )

            if not text:
                return None

            # Metadata çıkar
            metadata = trafilatura.extract_metadata(downloaded)

            title = ''
            author = ''
            date = ''

            if metadata:
                title = metadata.title or ''
                author = metadata.author or ''
                date = metadata.date or ''

            return {
                'title': title,
                'text': self._clean_text(text),
                'author': author,
                'publish_date': date,
                'word_count': len(text.split()),
                'extraction_method': 'trafilatura'
            }

        except ImportError:
            logger.warning("trafilatura not installed")
            return None
        except Exception as e:
            logger.warning(f"Trafilatura error: {e}")
            return None

    def _extract_with_newspaper(self, url: str) -> Optional[Dict]:
        """Newspaper3k ile makale çıkar"""
        try:
            from newspaper import Article

            article = Article(url, language='de')
            article.download()
            article.parse()

            if not article.text:
                return None

            return {
                'title': article.title or '',
                'text': self._clean_text(article.text),
                'author': ', '.join(article.authors) if article.authors else '',
                'publish_date': str(article.publish_date) if article.publish_date else '',
                'top_image': article.top_image or '',
                'images': list(article.images)[:5] if article.images else [],
                'word_count': len(article.text.split()),
                'extraction_method': 'newspaper3k'
            }

        except ImportError:
            logger.warning("newspaper3k not installed")
            return None
        except Exception as e:
            logger.warning(f"Newspaper error: {e}")
            return None

    def _clean_text(self, text: str) -> str:
        """Metni temizle - gereksiz boşluklar ve karakterleri kaldır"""
        if not text:
            return ''

        # Birden fazla boşluğu tek boşluğa çevir
        text = re.sub(r'\s+', ' ', text)

        # Satır başı/sonu boşlukları temizle
        text = '\n'.join(line.strip() for line in text.split('\n'))

        # Birden fazla yeni satırı iki satıra indir
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def get_summary(self, url: str, max_sentences: int = 5) -> str:
        """URL'den kısa özet çıkar"""
        result = self.extract(url)

        if not result['success']:
            return f"[Hata: {result['error']}]"

        text = result['text']
        sentences = re.split(r'[.!?]\s+', text)

        summary = '. '.join(sentences[:max_sentences])
        if not summary.endswith('.'):
            summary += '.'

        return summary

    def extract_for_video(self, url: str) -> Dict:
        """
        Video üretimi için optimize edilmiş çıkarma
        - Kısa paragraflar
        - Ana fikirler
        - Görsel önerileri
        """
        result = self.extract(url)

        if not result['success']:
            return result

        text = result['text']

        # Paragrafları ayır
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        # Her paragrafı kısalt (video için max 5 cümle)
        short_paragraphs = []
        for para in paragraphs[:20]:  # Max 20 paragraf (uzun makaleler için)
            sentences = re.split(r'[.!?]\s+', para)
            short = '. '.join(sentences[:5])  # Max 5 cümle
            if short and not short.endswith('.'):
                short += '.'
            if len(short) > 50:  # Çok kısa olanları atla
                short_paragraphs.append(short)

        # Video için script oluştur
        result['video_script'] = {
            'intro': short_paragraphs[0] if short_paragraphs else '',
            'main_points': short_paragraphs[1:4] if len(short_paragraphs) > 1 else [],
            'conclusion': short_paragraphs[-1] if len(short_paragraphs) > 4 else '',
            'total_segments': len(short_paragraphs)
        }

        # Görsel önerileri için anahtar kelimeler
        keywords = self._extract_keywords(text)
        result['suggested_visuals'] = keywords[:5]

        return result

    def _extract_keywords(self, text: str) -> list:
        """Metinden anahtar kelimeler çıkar"""
        # Basit kelime frekansı analizi
        words = re.findall(r'\b[A-Za-zÄÖÜäöüß]{4,}\b', text.lower())

        # Stop words (Almanca + İngilizce)
        stop_words = {
            'aber', 'alle', 'allem', 'allen', 'aller', 'alles', 'also', 'andere',
            'anderem', 'anderen', 'anderer', 'anderes', 'anders', 'auch', 'dein',
            'deine', 'deinem', 'deinen', 'deiner', 'deines', 'denn', 'deren',
            'dessen', 'diese', 'dieselbe', 'dieselben', 'diesem', 'diesen',
            'dieser', 'dieses', 'dort', 'durch', 'eine', 'einem', 'einen',
            'einer', 'eines', 'etwa', 'etwas', 'euer', 'eure', 'eurem', 'euren',
            'eurer', 'eures', 'fest', 'gegen', 'haben', 'hier', 'ihre', 'ihrem',
            'ihren', 'ihrer', 'ihres', 'jede', 'jedem', 'jeden', 'jeder', 'jedes',
            'jene', 'jenem', 'jenen', 'jener', 'jenes', 'kann', 'keine', 'keinem',
            'keinen', 'keiner', 'keines', 'manche', 'manchem', 'manchen',
            'mancher', 'manches', 'mehr', 'mein', 'meine', 'meinem', 'meinen',
            'meiner', 'meines', 'mich', 'nach', 'nicht', 'noch', 'oder', 'ohne',
            'sehr', 'sein', 'seine', 'seinem', 'seinen', 'seiner', 'seines',
            'selbst', 'sich', 'sind', 'solch', 'solche', 'solchem', 'solchen',
            'solcher', 'solches', 'sondern', 'über', 'unter', 'viel', 'viele',
            'vielem', 'vielen', 'vielleicht', 'wenn', 'werden', 'wird', 'wir',
            'würde', 'würden', 'während', 'würde', 'zwischen',
            'the', 'and', 'for', 'that', 'with', 'this', 'from', 'have', 'been',
            'will', 'which', 'when', 'what', 'where', 'who', 'how', 'can', 'also'
        }

        # Frekans sayımı
        word_freq = {}
        for word in words:
            if word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

        # En sık kullanılan kelimeleri döndür
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:10]]


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    extractor = ArticleExtractor()

    # Test URL
    test_url = "https://www.tagesschau.de"

    print(f"\n{'='*50}")
    print(f"Testing: {test_url}")
    print('='*50)

    result = extractor.extract(test_url)

    if result['success']:
        print(f"Title: {result['title']}")
        print(f"Author: {result['author']}")
        print(f"Words: {result['word_count']}")
        print(f"\nFirst 500 chars:")
        print(result['text'][:500])
    else:
        print(f"Error: {result['error']}")
