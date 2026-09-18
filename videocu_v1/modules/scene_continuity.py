"""
VIDEOCU v1 - Scene Continuity Manager
Maintains visual consistency across video segments (like old cartoon studios!)
"""

import logging
from typing import Dict, List, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class SceneContinuityManager:
    """
    Görsel bütünlüğü korur - eski çizgi film stüdyosu mantığı!

    Özellikler:
    - Karakter tutarlılığı (aynı kıyafet, stil)
    - Arka plan tutarlılığı
    - Renk paleti senkronizasyonu
    - Mood & lighting consistency
    """

    def __init__(self):
        """Initialize continuity manager"""
        self.style_profile = {}
        self.character_profile = {}
        self.background_profile = {}
        self.color_palette = []

        logger.info("🎬 Scene Continuity Manager initialized")

    def extract_style_from_script(self, script: Dict) -> Dict:
        """
        Senaryodan stil profilini çıkar

        Args:
            script: ContentGenerator'dan gelen script dict

        Returns:
            Style profile dict
        """
        try:
            # İlk sahneyi baz al
            first_scene = script.get('scenes', [{}])[0]

            # Karakter & arka plan bilgilerini çıkar
            visual_desc = first_scene.get('visual', '')
            image_prompt = first_scene.get('image_prompt', '')

            # Stil profili oluştur
            self.style_profile = {
                'base_prompt': image_prompt,
                'visual_description': visual_desc,
                'title': script.get('title', ''),
                'category': script.get('metadata', {}).get('category', ''),
                'mood': self._detect_mood(script),
                'timestamp': script.get('metadata', {}).get('created_at', '')
            }

            # Karakter profili (basit çıkarım)
            self.character_profile = self._extract_character_info(image_prompt)

            # Arka plan profili
            self.background_profile = self._extract_background_info(visual_desc)

            # Renk paleti (mood'dan)
            self.color_palette = self._get_color_palette(self.style_profile['mood'])

            logger.info(f"✅ Style profile extracted: {self.style_profile['mood']} mood")
            return self.style_profile

        except Exception as e:
            logger.error(f"❌ Style extraction failed: {e}")
            return {}

    def apply_to_segment(self, segment_scenes: List[Dict]) -> List[Dict]:
        """
        Stil profilini yeni segmente uygula

        Args:
            segment_scenes: Yeni segment'in sahneleri

        Returns:
            Updated scenes with consistent style
        """
        try:
            if not self.style_profile:
                logger.warning("⚠️ No style profile - extract first!")
                return segment_scenes

            updated_scenes = []

            for scene in segment_scenes:
                # Mevcut image_prompt'a stil profilini ekle
                original_prompt = scene.get('image_prompt', '')

                # Stil tutarlılığı ekle
                enhanced_prompt = self._enhance_prompt_with_style(
                    original_prompt,
                    self.style_profile
                )

                # Scene'i güncelle
                updated_scene = scene.copy()
                updated_scene['image_prompt'] = enhanced_prompt
                updated_scene['_style_consistent'] = True

                updated_scenes.append(updated_scene)

            logger.info(f"✅ Applied style to {len(updated_scenes)} scenes")
            return updated_scenes

        except Exception as e:
            logger.error(f"❌ Style application failed: {e}")
            return segment_scenes

    def _enhance_prompt_with_style(self, prompt: str, style: Dict) -> str:
        """
        Prompt'a stil tutarlılığı ekle

        Args:
            prompt: Orijinal image prompt
            style: Style profile dict

        Returns:
            Enhanced prompt with style consistency
        """
        # Karakter bilgisi ekle
        character_desc = self.character_profile.get('description', '')

        # Arka plan bilgisi ekle
        background_desc = self.background_profile.get('description', '')

        # Renk paleti ekle
        color_desc = ', '.join(self.color_palette[:3]) if self.color_palette else ''

        # Mood ekle
        mood = style.get('mood', 'neutral')

        # Birleştir
        enhanced = f"{prompt}"

        if character_desc:
            enhanced += f", {character_desc}"

        if background_desc:
            enhanced += f", {background_desc}"

        if color_desc:
            enhanced += f", color palette: {color_desc}"

        enhanced += f", {mood} mood, consistent style"

        return enhanced

    def _extract_character_info(self, prompt: str) -> Dict:
        """
        Prompt'tan karakter bilgisi çıkar
        """
        # Basit keyword extraction
        # Gelişmiş: LLM ile analiz edilebilir

        character_keywords = [
            'person', 'man', 'woman', 'child', 'boy', 'girl',
            'character', 'figure', 'people'
        ]

        found = [kw for kw in character_keywords if kw in prompt.lower()]

        if found:
            return {
                'type': found[0],
                'description': prompt.split(',')[0] if ',' in prompt else prompt[:50],
                'present': True
            }

        return {'present': False}

    def _extract_background_info(self, visual_desc: str) -> Dict:
        """
        Görsel açıklamadan arka plan bilgisi çıkar
        """
        background_keywords = [
            'office', 'room', 'outdoor', 'street', 'building',
            'landscape', 'city', 'nature', 'interior', 'exterior'
        ]

        found = [kw for kw in background_keywords if kw in visual_desc.lower()]

        if found:
            return {
                'type': found[0],
                'description': f"consistent {found[0]} background",
                'present': True
            }

        return {'present': False}

    def _detect_mood(self, script: Dict) -> str:
        """
        Senaryodan mood tespit et
        """
        title = script.get('title', '').lower()
        category = script.get('metadata', {}).get('category', '').lower()

        # Mood mapping
        if any(word in title + category for word in ['tech', 'ai', 'science', 'business']):
            return 'professional'
        elif any(word in title + category for word in ['fun', 'comedy', 'funny', 'laugh']):
            return 'playful'
        elif any(word in title + category for word in ['drama', 'serious', 'news']):
            return 'dramatic'
        elif any(word in title + category for word in ['relax', 'calm', 'peaceful']):
            return 'calm'
        else:
            return 'neutral'

    def _get_color_palette(self, mood: str) -> List[str]:
        """
        Mood'a göre renk paleti
        """
        palettes = {
            'professional': ['blue tones', 'white', 'gray', 'clean colors'],
            'playful': ['vibrant colors', 'warm tones', 'bright', 'colorful'],
            'dramatic': ['dark tones', 'high contrast', 'moody lighting'],
            'calm': ['soft colors', 'pastel tones', 'natural light'],
            'neutral': ['balanced colors', 'natural tones']
        }

        return palettes.get(mood, palettes['neutral'])

    def save_profile(self, output_path: str) -> bool:
        """
        Stil profilini kaydet (segment'ler arası kullanım için)

        Args:
            output_path: JSON dosya yolu

        Returns:
            True if successful
        """
        try:
            profile_data = {
                'style_profile': self.style_profile,
                'character_profile': self.character_profile,
                'background_profile': self.background_profile,
                'color_palette': self.color_palette
            }

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ Style profile saved: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Profile save failed: {e}")
            return False

    def load_profile(self, profile_path: str) -> bool:
        """
        Kaydedilmiş stil profilini yükle

        Args:
            profile_path: JSON dosya yolu

        Returns:
            True if successful
        """
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)

            self.style_profile = profile_data.get('style_profile', {})
            self.character_profile = profile_data.get('character_profile', {})
            self.background_profile = profile_data.get('background_profile', {})
            self.color_palette = profile_data.get('color_palette', [])

            logger.info(f"✅ Style profile loaded: {profile_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Profile load failed: {e}")
            return False

    def get_consistency_score(self, scene1: Dict, scene2: Dict) -> float:
        """
        İki sahne arasındaki stil tutarlılığını skorla (0.0-1.0)

        Args:
            scene1: İlk sahne
            scene2: İkinci sahne

        Returns:
            Consistency score (1.0 = perfect match)
        """
        # Basit similarity check
        # Gelişmiş: Image embedding comparison

        prompt1 = scene1.get('image_prompt', '').lower()
        prompt2 = scene2.get('image_prompt', '').lower()

        # Ortak kelimeler
        words1 = set(prompt1.split())
        words2 = set(prompt2.split())

        if not words1 or not words2:
            return 0.0

        common = words1.intersection(words2)
        total = words1.union(words2)

        score = len(common) / len(total) if total else 0.0

        return score

    def get_status(self) -> Dict:
        """Get current status"""
        return {
            'has_profile': bool(self.style_profile),
            'mood': self.style_profile.get('mood', 'unknown'),
            'character_present': self.character_profile.get('present', False),
            'background_present': self.background_profile.get('present', False),
            'color_palette_size': len(self.color_palette)
        }


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
    print("🎬 SCENE CONTINUITY MANAGER TEST")
    print("="*70)

    manager = SceneContinuityManager()

    # Mock script
    mock_script = {
        'title': 'AI Technology in 2025',
        'scenes': [
            {
                'image_prompt': 'modern office, professional woman, blue jacket, technology',
                'visual': 'Clean modern office with computers'
            },
            {
                'image_prompt': 'cityscape, technology, futuristic',
                'visual': 'City view with tech elements'
            }
        ],
        'metadata': {
            'category': 'technology'
        }
    }

    # Extract style
    print("\n📝 TEST 1: Extract Style Profile")
    style = manager.extract_style_from_script(mock_script)
    print(f"   Mood: {style.get('mood')}")
    print(f"   Character: {manager.character_profile}")
    print(f"   Colors: {manager.color_palette}")

    # Apply to new segment
    print("\n📝 TEST 2: Apply Style to New Segment")
    new_scenes = [
        {'image_prompt': 'new scene, different content'},
        {'image_prompt': 'another scene'}
    ]

    updated = manager.apply_to_segment(new_scenes)
    for i, scene in enumerate(updated, 1):
        print(f"\n   Scene {i}:")
        print(f"      {scene['image_prompt'][:80]}...")

    # Save & load profile
    print("\n📝 TEST 3: Save & Load Profile")
    manager.save_profile("output/test_style_profile.json")

    new_manager = SceneContinuityManager()
    new_manager.load_profile("output/test_style_profile.json")
    print(f"   Loaded mood: {new_manager.style_profile.get('mood')}")

    print("\n" + "="*70)
    print("✅ SCENE CONTINUITY MANAGER TEST COMPLETE")
    print("="*70)
