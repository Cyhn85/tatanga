"""
VIDEOCU v1 - Intelligent Segmenter
Akıllı video bölümleme sistemi - uzun senaryoları mantıklı noktalarda böler
"""

import logging
from typing import Dict, List, Tuple
from pathlib import Path
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class IntelligentSegmenter:
    """
    Uzun senaryoları akıllıca böler

    Özellikler:
    - Maximum duration limitleri
    - Mantıklı kesme noktaları (sahne sonları)
    - Segment metadata yönetimi
    - Continuity preservation
    """

    def __init__(self, max_segment_duration: int = 120):
        """
        Initialize segmenter

        Args:
            max_segment_duration: Max segment duration in seconds (default: 120 = 2 min)
        """
        self.max_segment_duration = max_segment_duration
        self.segments = []

        logger.info(f"🎬 Intelligent Segmenter initialized (max {max_segment_duration}s per segment)")

    def split_script(self, script: Dict) -> List[Dict]:
        """
        Senaryoyu akıllıca böl

        Args:
            script: ContentGenerator'dan gelen script dict

        Returns:
            List of segment dicts
        """
        try:
            scenes = script.get('scenes', [])
            total_duration = script.get('metadata', {}).get('duration', 0)

            if not scenes:
                logger.error("❌ No scenes in script")
                return []

            logger.info(f"📊 Splitting script: {len(scenes)} scenes, {total_duration}s total")

            # Tek segment yeterli mi?
            if total_duration <= self.max_segment_duration:
                logger.info(f"✅ Single segment sufficient ({total_duration}s <= {self.max_segment_duration}s)")
                return [self._create_segment(script, scenes, 1, 1)]

            # Çoklu segment gerekli
            segments = self._split_into_segments(script, scenes)

            logger.info(f"✅ Split into {len(segments)} segments")
            return segments

        except Exception as e:
            logger.error(f"❌ Script splitting failed: {e}")
            return []

    def _split_into_segments(self, script: Dict, scenes: List[Dict]) -> List[Dict]:
        """
        Sahneleri segmentlere böl
        """
        segments = []
        current_scenes = []
        current_duration = 0.0
        segment_number = 1

        for i, scene in enumerate(scenes):
            # Scene duration hesapla
            scene_duration = self._calculate_scene_duration(scene, script)

            # Bu sahneyi eklersek limit aşılır mı?
            if current_duration + scene_duration > self.max_segment_duration:
                # Mevcut segmenti kaydet (eğer boş değilse)
                if current_scenes:
                    segment = self._create_segment(
                        script,
                        current_scenes,
                        segment_number,
                        -1  # Total count henüz bilinmiyor
                    )
                    segments.append(segment)
                    segment_number += 1

                # Yeni segment başlat
                current_scenes = [scene]
                current_duration = scene_duration

                logger.info(f"   Segment {segment_number - 1}: {len(current_scenes)} scenes ({current_duration:.1f}s)")

            else:
                # Sahneyi mevcut segmente ekle
                current_scenes.append(scene)
                current_duration += scene_duration

        # Son segmenti ekle
        if current_scenes:
            segment = self._create_segment(
                script,
                current_scenes,
                segment_number,
                -1
            )
            segments.append(segment)
            logger.info(f"   Segment {segment_number}: {len(current_scenes)} scenes ({current_duration:.1f}s)")

        # Total count güncelle
        total_segments = len(segments)
        for seg in segments:
            seg['metadata']['total_segments'] = total_segments

        return segments

    def _create_segment(self,
                       original_script: Dict,
                       segment_scenes: List[Dict],
                       segment_number: int,
                       total_segments: int) -> Dict:
        """
        Segment dict oluştur
        """
        # Duration hesapla
        segment_duration = sum(
            self._calculate_scene_duration(scene, original_script)
            for scene in segment_scenes
        )

        # Segment metadata
        segment = {
            'title': f"{original_script.get('title', 'Video')} - Part {segment_number}",
            'description': original_script.get('description', ''),
            'hook': original_script.get('hook', ''),
            'script': self._generate_segment_script(segment_scenes),
            'scenes': segment_scenes,
            'hashtags': original_script.get('hashtags', []),
            'metadata': {
                'segment_number': segment_number,
                'total_segments': total_segments,
                'duration': segment_duration,
                'scene_count': len(segment_scenes),
                'language': original_script.get('metadata', {}).get('language', 'de'),
                'category': original_script.get('metadata', {}).get('category', ''),
                'created_at': datetime.now().isoformat(),
                'parent_script_title': original_script.get('title', '')
            }
        }

        return segment

    def _calculate_scene_duration(self, scene: Dict, script: Dict) -> float:
        """
        Sahne süresini hesapla
        """
        # Time string parse et (örn: "0-5s" → 5.0 saniye)
        time_str = scene.get('time', '0-5s')

        try:
            # "0-5s" formatı
            if '-' in time_str and 's' in time_str:
                time_str = time_str.replace('s', '').strip()
                start, end = time_str.split('-')
                return float(end) - float(start)

            # Fallback: script total duration / scene count
            total_duration = script.get('metadata', {}).get('duration', 60)
            scene_count = len(script.get('scenes', []))

            return total_duration / scene_count if scene_count > 0 else 5.0

        except Exception:
            # Default: 5 saniye
            return 5.0

    def _generate_segment_script(self, scenes: List[Dict]) -> str:
        """
        Segment için script metni oluştur
        """
        # Scene text'lerini birleştir
        script_parts = []

        for scene in scenes:
            text = scene.get('text', '')
            if text:
                script_parts.append(text)

        return ' '.join(script_parts)

    def merge_segments_metadata(self, segments: List[Dict]) -> Dict:
        """
        Segment metadata'larını birleştir (final video için)

        Args:
            segments: List of segment dicts

        Returns:
            Merged metadata dict
        """
        if not segments:
            return {}

        first_segment = segments[0]
        total_duration = sum(seg['metadata']['duration'] for seg in segments)
        total_scenes = sum(seg['metadata']['scene_count'] for seg in segments)

        merged = {
            'title': first_segment['metadata'].get('parent_script_title', ''),
            'total_segments': len(segments),
            'total_duration': total_duration,
            'total_scenes': total_scenes,
            'language': first_segment['metadata'].get('language', 'de'),
            'category': first_segment['metadata'].get('category', ''),
            'segments': [
                {
                    'number': seg['metadata']['segment_number'],
                    'duration': seg['metadata']['duration'],
                    'scenes': seg['metadata']['scene_count']
                }
                for seg in segments
            ]
        }

        return merged

    def save_segments(self, segments: List[Dict], output_dir: str) -> List[str]:
        """
        Segmentleri dosyalara kaydet

        Args:
            segments: Segment list
            output_dir: Output directory

        Returns:
            List of saved file paths
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            saved_files = []

            for segment in segments:
                segment_num = segment['metadata']['segment_number']
                filename = f"segment_{segment_num:03d}.json"
                file_path = output_path / filename

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(segment, f, indent=2, ensure_ascii=False)

                saved_files.append(str(file_path))
                logger.info(f"   ✅ Saved: {filename}")

            logger.info(f"✅ Saved {len(saved_files)} segment files")
            return saved_files

        except Exception as e:
            logger.error(f"❌ Segment save failed: {e}")
            return []

    def load_segments(self, segment_dir: str) -> List[Dict]:
        """
        Kaydedilmiş segmentleri yükle

        Args:
            segment_dir: Directory with segment JSON files

        Returns:
            List of segment dicts
        """
        try:
            segment_path = Path(segment_dir)

            if not segment_path.exists():
                logger.error(f"❌ Segment directory not found: {segment_dir}")
                return []

            # JSON dosyalarını bul
            segment_files = sorted(segment_path.glob("segment_*.json"))

            segments = []
            for file_path in segment_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    segment = json.load(f)
                    segments.append(segment)

            logger.info(f"✅ Loaded {len(segments)} segments")
            return segments

        except Exception as e:
            logger.error(f"❌ Segment load failed: {e}")
            return []

    def get_stats(self, segments: List[Dict]) -> Dict:
        """Get segmentation statistics"""
        if not segments:
            return {}

        total_duration = sum(seg['metadata']['duration'] for seg in segments)
        avg_duration = total_duration / len(segments) if segments else 0

        return {
            'total_segments': len(segments),
            'total_duration': total_duration,
            'avg_segment_duration': avg_duration,
            'max_segment_duration': self.max_segment_duration,
            'total_scenes': sum(seg['metadata']['scene_count'] for seg in segments)
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
    print("🎬 INTELLIGENT SEGMENTER TEST")
    print("="*70)

    segmenter = IntelligentSegmenter(max_segment_duration=120)

    # Mock long script (5 minutes)
    mock_script = {
        'title': 'AI Technology Deep Dive 2025',
        'description': 'Comprehensive guide to AI',
        'hook': 'Discover the future of AI',
        'scenes': [
            {'time': f'{i*10}-{(i+1)*10}s', 'text': f'Scene {i+1} content', 'image_prompt': f'scene {i+1}'}
            for i in range(30)  # 30 scenes x 10s = 300s = 5 min
        ],
        'hashtags': ['#AI', '#Technology'],
        'metadata': {
            'duration': 300,
            'language': 'de',
            'category': 'technology'
        }
    }

    # Test 1: Split script
    print("\n📝 TEST 1: Split 5-Minute Script")
    segments = segmenter.split_script(mock_script)

    for i, seg in enumerate(segments, 1):
        meta = seg['metadata']
        print(f"\n   Segment {i}/{meta['total_segments']}:")
        print(f"      Duration: {meta['duration']:.1f}s")
        print(f"      Scenes: {meta['scene_count']}")
        print(f"      Title: {seg['title']}")

    # Test 2: Stats
    print("\n📝 TEST 2: Segmentation Stats")
    stats = segmenter.get_stats(segments)
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Test 3: Save & Load
    print("\n📝 TEST 3: Save & Load Segments")
    saved = segmenter.save_segments(segments, "output/test_segments")
    print(f"   Saved {len(saved)} files")

    loaded = segmenter.load_segments("output/test_segments")
    print(f"   Loaded {len(loaded)} segments")

    # Test 4: Merge metadata
    print("\n📝 TEST 4: Merge Metadata")
    merged = segmenter.merge_segments_metadata(segments)
    print(f"   Title: {merged['title']}")
    print(f"   Total Duration: {merged['total_duration']}s")
    print(f"   Segments: {merged['total_segments']}")

    print("\n" + "="*70)
    print("✅ INTELLIGENT SEGMENTER TEST COMPLETE")
    print("="*70)
