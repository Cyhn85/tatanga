"""
VIDEOCU v1 - Content Generator Module
Gemini AI ile video script oluşturma
"""

import google.generativeai as genai
import logging
from typing import Dict, Optional, List
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)


class ContentGenerator:
    """Gemini AI ile içerik üretimi"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = None
        self._init_gemini()

    def _init_gemini(self):
        """Gemini API'yi başlat"""
        try:
            genai.configure(api_key=self.api_key)
            # Use Gemini 2.5 Flash - Latest fast model (FREE)
            self.model = genai.GenerativeModel('models/gemini-2.5-flash')
            logger.info("✅ Gemini AI initialized (gemini-2.5-flash)")
        except Exception as e:
            logger.error(f"❌ Gemini initialization failed: {e}")
            self.model = None

    def generate_video_script(self,
                            topic: str,
                            duration: int = 60,
                            language: str = 'de',
                            style: str = 'informativ') -> Dict:
        """
        Trend konusuna göre video scripti oluştur

        Args:
            topic: Video konusu (trending topic)
            duration: Video süresi (saniye)
            language: Dil (de, en, tr)
            style: Video stili (informativ, unterhaltsam, dramatisch, humorvoll)

        Returns:
            Video script içeriği (title, description, script, scenes, hashtags)
        """
        if not self.model:
            logger.error("❌ Gemini model not initialized")
            return self._create_error_response()

        try:
            logger.info(f"📝 Generating script for: '{topic}' ({duration}s, {language}, {style})")

            # Prompt oluştur
            prompt = self._create_script_prompt(topic, duration, language, style)

            # Gemini'ye sor
            response = self.model.generate_content(prompt)

            if not response or not response.text:
                logger.error("❌ No response from Gemini")
                return self._create_error_response()

            # Response'u parse et
            script_data = self._parse_script_response(response.text)

            # Metadata ekle
            script_data['metadata'] = {
                'topic': topic,
                'duration': duration,
                'language': language,
                'style': style,
                'generated_at': datetime.now().isoformat(),
                'model': 'gemini-2.5-flash'
            }

            logger.info(f"✅ Script generated: {script_data['title']}")
            return script_data

        except Exception as e:
            logger.error(f"❌ Script generation failed: {e}")
            return self._create_error_response()

    def _create_script_prompt(self, topic: str, duration: int,
                             language: str, style: str) -> str:
        """Gemini için prompt oluştur"""

        lang_names = {
            'de': 'Deutsch',
            'en': 'English',
            'tr': 'Türkçe'
        }

        style_descriptions = {
            'informativ': 'informativ und sachlich',
            'unterhaltsam': 'unterhaltsam und locker',
            'dramatisch': 'dramatisch und spannend',
            'humorvoll': 'humorvoll und witzig'
        }

        words_per_second = 2.5  # Durchschnittlich
        word_count = int(duration * words_per_second)

        prompt = f"""Du bist ein professioneller YouTube Content Creator für den deutschen Markt.

AUFGABE:
Erstelle ein vollständiges Video-Skript für ein {duration}-Sekunden YouTube-Video über das Thema: "{topic}"

ANFORDERUNGEN:
- Sprache: {lang_names.get(language, 'Deutsch')}
- Stil: {style_descriptions.get(style, 'informativ')}
- Zielgruppe: Deutsches YouTube-Publikum (18-35 Jahre)
- Wortanzahl: ca. {word_count} Wörter
- Trending-optimiert für maximale Reichweite

STRUKTUR:
Erstelle die Antwort GENAU in diesem JSON-Format:

{{
  "title": "Eingängiger Video-Titel (max 60 Zeichen, clickbait aber seriös)",
  "description": "YouTube Video-Beschreibung (150-200 Wörter mit Keywords)",
  "hook": "Starker Einstieg in den ersten 3 Sekunden (1 Satz)",
  "script": "Komplettes Voiceover-Skript ({word_count} Wörter)",
  "scenes": [
    {{
      "time": "0-5s",
      "text": "Was in dieser Szene gesprochen wird",
      "visual": "Beschreibung was visuell gezeigt werden soll",
      "image_prompt": "Kurzer Prompt für AI Bildgenerierung"
    }},
    ... (5-8 Szenen für {duration} Sekunden)
  ],
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3", "#hashtag4", "#hashtag5"],
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}

WICHTIG:
- Verwende aktuelles, trendendes Vokabular
- Hook muss in 3 Sekunden Aufmerksamkeit fesseln
- Script soll natürlich und fließend klingen
- Jede Szene braucht klare visuelle Anweisungen
- Hashtags müssen trending-relevant sein
- Antworte NUR mit dem JSON, keine zusätzlichen Erklärungen

Beginne jetzt mit der Content-Erstellung:"""

        return prompt

    def _parse_script_response(self, response_text: str) -> Dict:
        """Parse Gemini response als JSON"""
        try:
            # Entferne mögliche Markdown code blocks
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            # Parse JSON
            data = json.loads(cleaned)

            # Validiere required fields
            required_fields = ['title', 'description', 'hook', 'script', 'scenes', 'hashtags']
            for field in required_fields:
                if field not in data:
                    logger.warning(f"⚠️ Missing field: {field}")
                    data[field] = self._get_default_value(field)

            return data

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")

            # Fallback: Erstelle basic structure
            return {
                'title': 'Generated Video Title',
                'description': response_text[:200],
                'hook': response_text[:100],
                'script': response_text,
                'scenes': self._create_default_scenes(response_text, 60),
                'hashtags': ['#trending', '#viral', '#deutschland'],
                'keywords': []
            }

    def _get_default_value(self, field: str):
        """Default Werte für fehlende Felder"""
        defaults = {
            'title': 'Untitled Video',
            'description': 'Video description not available',
            'hook': 'Watch this video!',
            'script': 'Script not available',
            'scenes': [],
            'hashtags': ['#video', '#content'],
            'keywords': []
        }
        return defaults.get(field, '')

    def _create_default_scenes(self, text: str, duration: int) -> List[Dict]:
        """Erstelle default Szenen aus Text"""
        words = text.split()
        words_per_scene = len(words) // 5  # 5 Szenen
        scenes = []

        for i in range(5):
            start_time = int((duration / 5) * i)
            end_time = int((duration / 5) * (i + 1))
            scene_words = words[i * words_per_scene:(i + 1) * words_per_scene]
            scene_text = ' '.join(scene_words)

            scenes.append({
                'time': f'{start_time}-{end_time}s',
                'text': scene_text,
                'visual': 'Visual content',
                'image_prompt': scene_text[:100]
            })

        return scenes

    def _create_error_response(self) -> Dict:
        """Error response struktur"""
        return {
            'title': 'Error',
            'description': 'Failed to generate content',
            'hook': '',
            'script': '',
            'scenes': [],
            'hashtags': [],
            'keywords': [],
            'metadata': {
                'error': True,
                'generated_at': datetime.now().isoformat()
            }
        }

    def improve_script(self, original_script: str, feedback: str) -> str:
        """
        Mevcut scripti feedback'e göre iyileştir

        Args:
            original_script: Orijinal script
            feedback: İyileştirme talebi

        Returns:
            İyileştirilmiş script
        """
        if not self.model:
            logger.error("❌ Gemini model not initialized")
            return original_script

        try:
            prompt = f"""Du bist ein Content Editor. Verbessere den folgenden Video-Script basierend auf dem Feedback:

ORIGINAL SCRIPT:
{original_script}

FEEDBACK:
{feedback}

AUFGABE:
Erstelle eine verbesserte Version des Scripts. Behalte die grundlegende Struktur, aber implementiere das Feedback.
Antworte NUR mit dem verbesserten Script, keine Erklärungen.
"""

            response = self.model.generate_content(prompt)
            improved = response.text.strip()

            logger.info("✅ Script improved")
            return improved

        except Exception as e:
            logger.error(f"❌ Script improvement failed: {e}")
            return original_script

    def generate_variations(self, topic: str, count: int = 3) -> List[str]:
        """
        Bir konu için birden fazla title variation oluştur

        Args:
            topic: Ana konu
            count: Variation sayısı

        Returns:
            Title listesi
        """
        if not self.model:
            logger.error("❌ Gemini model not initialized")
            return []

        try:
            prompt = f"""Erstelle {count} verschiedene YouTube Video-Titel für das Thema: "{topic}"

ANFORDERUNGEN:
- Max 60 Zeichen pro Titel
- Clickbait aber seriös
- SEO-optimiert
- Trending-relevant
- Deutsch

Antworte NUR mit den Titeln, einer pro Zeile, keine Nummerierung."""

            response = self.model.generate_content(prompt)
            titles = [line.strip() for line in response.text.strip().split('\n') if line.strip()]

            logger.info(f"✅ Generated {len(titles)} title variations")
            return titles[:count]

        except Exception as e:
            logger.error(f"❌ Variation generation failed: {e}")
            return []


# Test
if __name__ == "__main__":
    import sys
    import os

    # Set UTF-8 encoding
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Load API key from env
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in .env")
        sys.exit(1)

    print("\n" + "="*60)
    print("🤖 CONTENT GENERATOR TEST")
    print("="*60)

    generator = ContentGenerator(api_key=api_key)

    # Test 1: Generate script
    print("\n📝 TEST 1: Generating video script...")
    script = generator.generate_video_script(
        topic="KI Trends 2025 in Deutschland",
        duration=60,
        language='de',
        style='informativ'
    )

    print(f"\n✅ Title: {script['title']}")
    print(f"📝 Hook: {script['hook']}")
    print(f"📊 Scenes: {len(script.get('scenes', []))}")
    print(f"🏷️ Hashtags: {', '.join(script.get('hashtags', []))}")
    print(f"\n📜 Script Preview:")
    print(f"   {script['script'][:200]}...")

    # Test 2: Generate variations
    print("\n📝 TEST 2: Generating title variations...")
    variations = generator.generate_variations("Künstliche Intelligenz", count=3)
    for i, title in enumerate(variations, 1):
        print(f"   {i}. {title}")

    print("\n" + "="*60)
    print("✅ CONTENT GENERATOR TEST COMPLETE")
    print("="*60)
