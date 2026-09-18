"""
VIDEOCU v1 - Smart Content Analyzer Module
Gemini AI ile akıllı içerik analizi (FREE)

Özellikler:
- Metin tema çıkarma ("soğuk ay" → "mysterious, celestial")
- Duygu analizi (wonder, fear, excitement, etc.)
- Video arama keywords üretimi
- Görsel prompt engineering
- Renk paleti önerisi
"""

import google.generativeai as genai
import logging
import json
import os
from typing import Optional, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


class SmartContentAnalyzer:
    """
    Gemini ile akıllı içerik analizi

    Kullanım:
    - Makale metninden tema, duygu, anahtar kelime çıkarma
    - Video/görsel arama için optimize edilmiş keywords
    - Cinematic visual prompts üretme
    - Ken Burns efekt önerileri
    """

    # Prompt templates
    ANALYSIS_PROMPT = """
Du bist ein professioneller Content-Analyst für Video-Produktion.
Analysiere den folgenden Text und extrahiere:

TEXT:
{text}

Antworte NUR im JSON-Format:
{{
    "main_theme": "Hauptthema in 2-3 Wörtern",
    "sub_themes": ["Unterthema 1", "Unterthema 2", "Unterthema 3"],
    "emotion": "primäre Emotion (wonder, fear, excitement, curiosity, hope, sadness, joy, mystery)",
    "tone": "Ton (informative, dramatic, inspirational, serious, playful)",
    "visual_mood": "visuelle Stimmung (dark, bright, warm, cold, mystical, futuristic, natural)",
    "color_palette": ["Farbe1", "Farbe2", "Farbe3"],
    "video_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "image_keywords": ["keyword1", "keyword2", "keyword3"],
    "cinematic_style": "Filmstil (documentary, cinematic, news, nature, sci-fi)",
    "suggested_transitions": ["transition1", "transition2"],
    "ken_burns_suggestion": "zoom_in, zoom_out, pan_left, pan_right, oder kombination"
}}
"""

    VISUAL_PROMPT_TEMPLATE = """
Du bist ein professioneller Visual Prompt Engineer.
Erstelle einen cinematic visual prompt für Stock-Video-Suche basierend auf:

SZENE: {scene_text}
STIMMUNG: {mood}
EMOTION: {emotion}

Antworte NUR im JSON-Format:
{{
    "primary_prompt": "Haupt-Suchbegriffe für Video (max 5 Wörter, Englisch)",
    "alternative_prompts": ["Alternative 1", "Alternative 2"],
    "visual_elements": ["Element 1", "Element 2", "Element 3"],
    "avoid_elements": ["Zu vermeiden 1", "Zu vermeiden 2"],
    "motion_type": "static, slow_motion, timelapse, oder dynamic",
    "camera_angle": "wide, close_up, aerial, eye_level"
}}
"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Smart Content Analyzer with Gemini

        Args:
            api_key: Gemini API key (optional, from .env)
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY', '')

        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            self.enabled = True
            logger.info("✅ SmartContentAnalyzer initialized (Gemini 2.0 Flash)")
        else:
            self.model = None
            self.enabled = False
            logger.warning("⚠️ SmartContentAnalyzer disabled - no GEMINI_API_KEY")

        # Cache for repeated analysis
        self._cache = {}

    def analyze_content(self, text: str, use_cache: bool = True) -> Dict:
        """
        Analyze text content and extract themes, emotions, keywords

        Args:
            text: Article or script text to analyze
            use_cache: Use cached results for same text

        Returns:
            Analysis result dictionary
        """
        if not self.enabled:
            return self._fallback_analysis(text)

        # Check cache
        cache_key = hash(text[:500])  # Hash first 500 chars
        if use_cache and cache_key in self._cache:
            logger.info("📋 Using cached analysis")
            return self._cache[cache_key]

        try:
            # Truncate text if too long
            if len(text) > 5000:
                text = text[:5000] + "..."

            prompt = self.ANALYSIS_PROMPT.format(text=text)

            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Lower temperature for consistent analysis
                    max_output_tokens=1000
                )
            )

            # Parse JSON response
            result_text = response.text.strip()

            # Clean markdown code blocks if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]

            result = json.loads(result_text)

            # Add metadata
            result['analyzed'] = True
            result['text_length'] = len(text)

            # Cache result
            self._cache[cache_key] = result

            logger.info(f"✅ Content analyzed: theme='{result.get('main_theme')}', emotion='{result.get('emotion')}'")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing failed: {e}")
            return self._fallback_analysis(text)
        except Exception as e:
            logger.error(f"❌ Content analysis failed: {e}")
            return self._fallback_analysis(text)

    def generate_visual_prompt(self,
                                scene_text: str,
                                mood: str = 'neutral',
                                emotion: str = 'curiosity') -> Dict:
        """
        Generate optimized visual prompt for video/image search

        Args:
            scene_text: Scene description
            mood: Visual mood (dark, bright, warm, etc.)
            emotion: Primary emotion

        Returns:
            Visual prompt dictionary
        """
        if not self.enabled:
            return self._fallback_visual_prompt(scene_text)

        try:
            prompt = self.VISUAL_PROMPT_TEMPLATE.format(
                scene_text=scene_text,
                mood=mood,
                emotion=emotion
            )

            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.5,
                    max_output_tokens=500
                )
            )

            # Parse JSON
            result_text = response.text.strip()
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]

            result = json.loads(result_text)

            logger.info(f"✅ Visual prompt generated: '{result.get('primary_prompt')}'")
            return result

        except Exception as e:
            logger.error(f"❌ Visual prompt generation failed: {e}")
            return self._fallback_visual_prompt(scene_text)

    def analyze_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """
        Analyze multiple scenes and generate visual prompts

        Args:
            scenes: List of scene dictionaries with 'text' or 'visual' fields

        Returns:
            Enhanced scenes with analysis data
        """
        if not self.enabled:
            return scenes

        enhanced_scenes = []

        # First, analyze the full content for context
        full_text = ' '.join([
            s.get('text', s.get('visual', ''))
            for s in scenes
        ])
        overall_analysis = self.analyze_content(full_text)

        # Analyze each scene
        for i, scene in enumerate(scenes):
            scene_text = scene.get('text', scene.get('visual', f'Scene {i+1}'))

            # Generate visual prompt with context
            visual_prompt = self.generate_visual_prompt(
                scene_text=scene_text,
                mood=overall_analysis.get('visual_mood', 'neutral'),
                emotion=overall_analysis.get('emotion', 'curiosity')
            )

            # Enhance scene
            enhanced_scene = scene.copy()
            enhanced_scene['analysis'] = {
                'visual_prompt': visual_prompt,
                'video_keywords': visual_prompt.get('primary_prompt', scene_text),
                'alternative_keywords': visual_prompt.get('alternative_prompts', []),
                'motion_type': visual_prompt.get('motion_type', 'static'),
                'camera_angle': visual_prompt.get('camera_angle', 'wide')
            }

            enhanced_scenes.append(enhanced_scene)
            logger.info(f"   Scene {i+1}: '{visual_prompt.get('primary_prompt', 'N/A')[:30]}'")

        return enhanced_scenes

    def get_video_search_keywords(self, text: str) -> List[str]:
        """
        Extract optimized keywords for video search

        Args:
            text: Text to extract keywords from

        Returns:
            List of search keywords (English)
        """
        analysis = self.analyze_content(text)
        keywords = analysis.get('video_keywords', [])

        if not keywords:
            # Fallback: extract basic keywords
            keywords = self._extract_basic_keywords(text)

        return keywords

    def get_emotion_color_map(self, emotion: str) -> Dict:
        """
        Get color palette for emotion

        Args:
            emotion: Emotion name

        Returns:
            Color mapping dictionary
        """
        emotion_colors = {
            'wonder': {
                'primary': '#4A90A4',
                'secondary': '#7B68EE',
                'accent': '#FFD700',
                'gradient': ['#1a1a2e', '#4A90A4', '#7B68EE']
            },
            'fear': {
                'primary': '#2C3E50',
                'secondary': '#8B0000',
                'accent': '#FF4500',
                'gradient': ['#0d0d0d', '#2C3E50', '#8B0000']
            },
            'excitement': {
                'primary': '#FF6B35',
                'secondary': '#FFD700',
                'accent': '#FF1493',
                'gradient': ['#FF6B35', '#FFD700', '#FF1493']
            },
            'curiosity': {
                'primary': '#3498DB',
                'secondary': '#9B59B6',
                'accent': '#1ABC9C',
                'gradient': ['#2C3E50', '#3498DB', '#9B59B6']
            },
            'hope': {
                'primary': '#27AE60',
                'secondary': '#F1C40F',
                'accent': '#3498DB',
                'gradient': ['#1a1a2e', '#27AE60', '#F1C40F']
            },
            'sadness': {
                'primary': '#34495E',
                'secondary': '#5D6D7E',
                'accent': '#85929E',
                'gradient': ['#1a1a2e', '#34495E', '#5D6D7E']
            },
            'joy': {
                'primary': '#F39C12',
                'secondary': '#E74C3C',
                'accent': '#9B59B6',
                'gradient': ['#F39C12', '#E74C3C', '#9B59B6']
            },
            'mystery': {
                'primary': '#2C3E50',
                'secondary': '#8E44AD',
                'accent': '#1ABC9C',
                'gradient': ['#0d0d0d', '#2C3E50', '#8E44AD']
            }
        }

        return emotion_colors.get(emotion, emotion_colors['curiosity'])

    def _fallback_analysis(self, text: str) -> Dict:
        """Fallback analysis when Gemini is unavailable"""
        keywords = self._extract_basic_keywords(text)

        return {
            'analyzed': False,
            'main_theme': keywords[0] if keywords else 'general',
            'sub_themes': keywords[1:4] if len(keywords) > 1 else [],
            'emotion': 'curiosity',
            'tone': 'informative',
            'visual_mood': 'neutral',
            'color_palette': ['#3498DB', '#2C3E50', '#ECF0F1'],
            'video_keywords': keywords[:5],
            'image_keywords': keywords[:3],
            'cinematic_style': 'documentary',
            'suggested_transitions': ['fade', 'dissolve'],
            'ken_burns_suggestion': 'zoom_in',
            'text_length': len(text)
        }

    def _fallback_visual_prompt(self, scene_text: str) -> Dict:
        """Fallback visual prompt when Gemini is unavailable"""
        keywords = self._extract_basic_keywords(scene_text)

        return {
            'primary_prompt': ' '.join(keywords[:3]),
            'alternative_prompts': [' '.join(keywords[:2])],
            'visual_elements': keywords[:3],
            'avoid_elements': [],
            'motion_type': 'static',
            'camera_angle': 'wide'
        }

    def _extract_basic_keywords(self, text: str) -> List[str]:
        """Extract basic keywords without AI"""
        # German + English stop words
        stop_words = {
            'der', 'die', 'das', 'den', 'dem', 'ein', 'eine', 'einer', 'einem',
            'und', 'oder', 'aber', 'wenn', 'weil', 'dass', 'ob', 'wie', 'was',
            'ist', 'sind', 'war', 'waren', 'wird', 'werden', 'hat', 'haben',
            'the', 'a', 'an', 'and', 'or', 'but', 'if', 'because', 'that',
            'is', 'are', 'was', 'were', 'will', 'be', 'has', 'have',
            'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'of',
            'im', 'am', 'an', 'auf', 'zu', 'für', 'mit', 'von', 'bei',
            'this', 'that', 'these', 'those', 'it', 'its', 'sie', 'es',
            'nicht', 'auch', 'nur', 'noch', 'schon', 'sehr', 'mehr',
            'nach', 'über', 'unter', 'zwischen', 'durch', 'gegen'
        }

        # Clean and split
        words = text.lower()
        for char in '.,;:!?()[]{}"\'-':
            words = words.replace(char, ' ')
        words = words.split()

        # Filter
        keywords = []
        seen = set()
        for word in words:
            if len(word) > 3 and word not in stop_words and word not in seen:
                keywords.append(word)
                seen.add(word)

        return keywords[:10]

    def get_status(self) -> Dict:
        """Get analyzer status"""
        return {
            'enabled': self.enabled,
            'model': 'gemini-2.0-flash' if self.enabled else None,
            'cost': 'FREE',
            'cache_size': len(self._cache)
        }


# Test
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🧠 SMART CONTENT ANALYZER TEST")
    print("="*70)

    analyzer = SmartContentAnalyzer()

    # Show status
    print("\n📊 Analyzer Status:")
    status = analyzer.get_status()
    print(f"   Enabled: {'✅' if status['enabled'] else '❌'}")
    print(f"   Model: {status['model']}")
    print(f"   Cost: {status['cost']}")

    # Test text (German news article)
    test_text = """
    Der Dezember-Vollmond am 15. Dezember wird als Kalter Mond bezeichnet.
    Dieses beeindruckende Naturphänomen erhellt die längsten Nächte des Jahres.
    Die Native Americans nannten ihn so wegen der winterlichen Kälte.
    Der Mond erscheint besonders hell und groß am Horizont.
    Astronomen erwarten klare Sicht in weiten Teilen Deutschlands.
    """

    print("\n" + "="*70)
    print("TEST 1: Content Analysis")
    print("="*70)

    result = analyzer.analyze_content(test_text)

    print(f"\n📋 Analysis Results:")
    print(f"   Main Theme: {result.get('main_theme')}")
    print(f"   Sub Themes: {result.get('sub_themes')}")
    print(f"   Emotion: {result.get('emotion')}")
    print(f"   Visual Mood: {result.get('visual_mood')}")
    print(f"   Video Keywords: {result.get('video_keywords')}")
    print(f"   Ken Burns: {result.get('ken_burns_suggestion')}")

    # Test visual prompt
    print("\n" + "="*70)
    print("TEST 2: Visual Prompt Generation")
    print("="*70)

    visual = analyzer.generate_visual_prompt(
        scene_text="Der Vollmond steigt über den verschneiten Bergen auf",
        mood=result.get('visual_mood', 'mystical'),
        emotion=result.get('emotion', 'wonder')
    )

    print(f"\n🎬 Visual Prompt:")
    print(f"   Primary: {visual.get('primary_prompt')}")
    print(f"   Alternatives: {visual.get('alternative_prompts')}")
    print(f"   Motion: {visual.get('motion_type')}")
    print(f"   Camera: {visual.get('camera_angle')}")

    # Test emotion colors
    print("\n" + "="*70)
    print("TEST 3: Emotion Color Palette")
    print("="*70)

    colors = analyzer.get_emotion_color_map(result.get('emotion', 'wonder'))
    print(f"\n🎨 Colors for '{result.get('emotion')}':")
    print(f"   Primary: {colors['primary']}")
    print(f"   Secondary: {colors['secondary']}")
    print(f"   Accent: {colors['accent']}")

    print("\n" + "="*70)
    print("✅ SMART CONTENT ANALYZER TEST COMPLETE")
    print("="*70)
    print("\n💡 Features:")
    print("   • Theme & emotion extraction")
    print("   • Video search keyword optimization")
    print("   • Visual prompt engineering")
    print("   • Emotion-based color palettes")
    print("   • Ken Burns effect suggestions")
    print("\n")
