"""
VIDEOCU v1 - Local Music Library Manager
Manages royalty-free background music from local filesystem

Music Sources (CC0/Public Domain):
- FreePD: https://freepd.com/
- Incompetech (Kevin MacLeod): https://incompetech.com/music/royalty-free/
- YouTube Audio Library: https://www.youtube.com/audiolibrary
- Bensound: https://www.bensound.com/
"""

import os
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)


class MusicLibrary:
    """
    Local music library manager for royalty-free background music
    """

    # Mood categories
    MOODS = ['upbeat', 'calm', 'dramatic', 'corporate', 'funny', 'romantic', 'sad']

    # Mood aliases for better topic matching
    MOOD_ALIASES = {
        # Positive/Energetic
        'happy': 'upbeat',
        'energetic': 'upbeat',
        'inspiring': 'upbeat',
        'motivational': 'upbeat',
        'cheerful': 'upbeat',
        'exciting': 'upbeat',

        # Calm/Peaceful
        'relaxing': 'calm',
        'peaceful': 'calm',
        'ambient': 'calm',
        'meditation': 'calm',
        'chill': 'calm',
        'soft': 'calm',

        # Dramatic/Epic
        'epic': 'dramatic',
        'cinematic': 'dramatic',
        'intense': 'dramatic',
        'powerful': 'dramatic',
        'action': 'dramatic',

        # Dark/Mysterious
        'dark': 'dramatic',
        'mysterious': 'dramatic',
        'suspenseful': 'dramatic',

        # Corporate/Tech
        'business': 'corporate',
        'technology': 'corporate',
        'tech': 'corporate',
        'professional': 'corporate',

        # Funny/Quirky
        'comedy': 'funny',
        'quirky': 'funny',
        'playful': 'funny',

        # Romantic
        'love': 'romantic',
        'emotional': 'romantic',

        # Sad/Melancholic
        'melancholic': 'sad',
        'tragic': 'sad',
    }

    def __init__(self, music_dir: str = "assets/music"):
        """
        Args:
            music_dir: Path to music library directory
        """
        self.music_dir = Path(music_dir)
        self.music_dir.mkdir(parents=True, exist_ok=True)

        # Create mood subdirectories
        for mood in self.MOODS:
            (self.music_dir / mood).mkdir(parents=True, exist_ok=True)

        # Music index cache
        self.index_file = self.music_dir / "music_index.json"
        self.music_index = self._load_index()

        logger.info(f"🎵 Music Library initialized: {self.music_dir}")
        self._scan_library()

    def _load_index(self) -> Dict:
        """Load music index from cache file"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load music index: {e}")
                return {}
        return {}

    def _save_index(self):
        """Save music index to cache file"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.music_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save music index: {e}")

    def _scan_library(self):
        """Scan music directory and update index"""
        total_tracks = 0

        for mood in self.MOODS:
            mood_dir = self.music_dir / mood
            tracks = []

            # Scan for music files
            for ext in ['*.mp3', '*.wav', '*.m4a', '*.ogg']:
                for file_path in mood_dir.glob(ext):
                    tracks.append({
                        'filename': file_path.name,
                        'path': str(file_path),
                        'size_mb': file_path.stat().st_size / (1024 * 1024),
                        'mood': mood
                    })

            self.music_index[mood] = tracks
            total_tracks += len(tracks)

        self._save_index()
        logger.info(f"📊 Music Library: {total_tracks} tracks in {len(self.MOODS)} moods")

        # Log counts per mood
        for mood in self.MOODS:
            count = len(self.music_index.get(mood, []))
            status = "✅" if count > 0 else "⚠️"
            logger.info(f"   {status} {mood}: {count} tracks")

    def get_music_for_mood(self,
                          mood: str,
                          duration_seconds: Optional[int] = None,
                          random_selection: bool = True) -> Optional[str]:
        """
        Get music track for a specific mood

        Args:
            mood: Mood category (upbeat, calm, dramatic, etc.)
            duration_seconds: Desired duration (not used yet, for future filtering)
            random_selection: Random vs sequential selection

        Returns:
            Path to music file or None if not available
        """
        # Normalize mood
        mood_normalized = mood.lower()
        if mood_normalized in self.MOOD_ALIASES:
            mood_normalized = self.MOOD_ALIASES[mood_normalized]

        if mood_normalized not in self.MOODS:
            logger.warning(f"Unknown mood: {mood}, using 'upbeat' as fallback")
            mood_normalized = 'upbeat'

        # Get tracks for mood
        tracks = self.music_index.get(mood_normalized, [])

        if not tracks:
            logger.warning(f"⚠️ No music found for mood: {mood_normalized}")
            # Try fallback to upbeat
            if mood_normalized != 'upbeat':
                tracks = self.music_index.get('upbeat', [])
                if tracks:
                    logger.info(f"   Using 'upbeat' as fallback")

        if not tracks:
            logger.error(f"❌ No music available in library")
            return None

        # Select track
        if random_selection:
            track = random.choice(tracks)
        else:
            track = tracks[0]

        logger.info(f"🎵 Selected: {track['filename']} ({mood_normalized})")
        return track['path']

    def get_music_for_topic(self,
                           topic: str,
                           duration_seconds: int = 60,
                           random_selection: bool = True) -> Optional[str]:
        """
        Auto-detect mood from video topic and get music

        Args:
            topic: Video topic/title
            duration_seconds: Desired duration (for future filtering)
            random_selection: Random vs sequential selection

        Returns:
            Path to music file or None
        """
        mood = self._detect_mood_from_topic(topic)
        logger.info(f"🎵 Topic: '{topic}' → Mood: '{mood}'")

        return self.get_music_for_mood(
            mood=mood,
            duration_seconds=duration_seconds,
            random_selection=random_selection
        )

    def _detect_mood_from_topic(self, topic: str) -> str:
        """
        Auto-detect mood from video topic

        Args:
            topic: Video topic/title

        Returns:
            Detected mood category
        """
        topic_lower = topic.lower()

        # Check for mood keywords in topic
        for keyword, mood in self.MOOD_ALIASES.items():
            if keyword in topic_lower:
                return mood

        # Topic-based detection
        if any(word in topic_lower for word in ['news', 'facts', 'science', 'technology', 'ai', 'tech', 'business']):
            return 'corporate'
        elif any(word in topic_lower for word in ['success', 'motivation', 'inspire', 'achieve', 'win']):
            return 'upbeat'
        elif any(word in topic_lower for word in ['relax', 'sleep', 'meditation', 'calm', 'nature']):
            return 'calm'
        elif any(word in topic_lower for word in ['action', 'adventure', 'epic', 'battle', 'hero']):
            return 'dramatic'
        elif any(word in topic_lower for word in ['mystery', 'crime', 'thriller', 'detective']):
            return 'dramatic'
        elif any(word in topic_lower for word in ['happy', 'fun', 'joy', 'celebration', 'party']):
            return 'upbeat'
        elif any(word in topic_lower for word in ['sad', 'tragic', 'loss', 'death']):
            return 'sad'
        elif any(word in topic_lower for word in ['funny', 'comedy', 'laugh', 'humor', 'joke']):
            return 'funny'
        elif any(word in topic_lower for word in ['love', 'romance', 'wedding', 'relationship']):
            return 'romantic'
        else:
            # Default to upbeat for general content
            return 'upbeat'

    def add_track(self,
                 source_path: str,
                 mood: str,
                 filename: Optional[str] = None) -> bool:
        """
        Add a track to the library

        Args:
            source_path: Path to source audio file
            mood: Mood category
            filename: Custom filename (optional)

        Returns:
            True if successful
        """
        try:
            source = Path(source_path)
            if not source.exists():
                logger.error(f"Source file not found: {source_path}")
                return False

            # Normalize mood
            mood_normalized = mood.lower()
            if mood_normalized in self.MOOD_ALIASES:
                mood_normalized = self.MOOD_ALIASES[mood_normalized]

            if mood_normalized not in self.MOODS:
                logger.error(f"Invalid mood: {mood}")
                return False

            # Copy to library
            dest_filename = filename if filename else source.name
            dest_path = self.music_dir / mood_normalized / dest_filename

            import shutil
            shutil.copy2(source, dest_path)

            logger.info(f"✅ Added track: {dest_filename} → {mood_normalized}")

            # Rescan library
            self._scan_library()
            return True

        except Exception as e:
            logger.error(f"Failed to add track: {e}")
            return False

    def get_library_stats(self) -> Dict:
        """Get library statistics"""
        total_tracks = sum(len(tracks) for tracks in self.music_index.values())
        total_size_mb = sum(
            sum(track['size_mb'] for track in tracks)
            for tracks in self.music_index.values()
        )

        mood_stats = {
            mood: {
                'count': len(tracks),
                'size_mb': sum(track['size_mb'] for track in tracks)
            }
            for mood, tracks in self.music_index.items()
        }

        return {
            'total_tracks': total_tracks,
            'total_size_mb': round(total_size_mb, 2),
            'moods': mood_stats,
            'library_path': str(self.music_dir)
        }

    def get_all_tracks(self) -> List[Dict]:
        """Get list of all tracks"""
        all_tracks = []
        for mood, tracks in self.music_index.items():
            all_tracks.extend(tracks)
        return all_tracks


# Test
if __name__ == "__main__":
    import sys

    # Set UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎵 LOCAL MUSIC LIBRARY TEST")
    print("="*70)

    library = MusicLibrary()

    # Show library stats
    print("\n📊 Library Statistics:")
    stats = library.get_library_stats()
    print(f"   Total Tracks: {stats['total_tracks']}")
    print(f"   Total Size: {stats['total_size_mb']} MB")
    print(f"   Library Path: {stats['library_path']}")

    print("\n📂 Mood Breakdown:")
    for mood, mood_stats in stats['moods'].items():
        status = "✅" if mood_stats['count'] > 0 else "⚠️"
        print(f"   {status} {mood}: {mood_stats['count']} tracks ({mood_stats['size_mb']:.1f} MB)")

    if stats['total_tracks'] == 0:
        print("\n" + "="*70)
        print("⚠️ NO MUSIC FOUND IN LIBRARY")
        print("="*70)
        print("\n📥 Download FREE royalty-free music from:")
        print("   1. FreePD: https://freepd.com/")
        print("   2. Incompetech: https://incompetech.com/music/royalty-free/")
        print("   3. YouTube Audio Library: https://www.youtube.com/audiolibrary")
        print("   4. Bensound: https://www.bensound.com/")
        print("\n📁 Place music files in:")
        print(f"   {stats['library_path']}/[mood]/")
        print("\n   Example:")
        print(f"   {stats['library_path']}/upbeat/happy-song.mp3")
        print(f"   {stats['library_path']}/calm/ambient-music.mp3")
        print(f"   {stats['library_path']}/dramatic/epic-trailer.mp3")
    else:
        # Test mood detection
        print("\n" + "="*70)
        print("TEST 1: Auto-Detect Mood from Topic")
        print("="*70)

        test_topics = [
            "Top 10 AI Technologies in 2025",
            "Relaxing Nature Sounds for Sleep",
            "Epic Movie Trailer Moments",
            "Funny Cat Compilation"
        ]

        for topic in test_topics:
            music_path = library.get_music_for_topic(topic)
            if music_path:
                print(f"\n✅ Topic: '{topic}'")
                print(f"   Music: {Path(music_path).name}")

        # Test specific mood
        print("\n" + "="*70)
        print("TEST 2: Get Music for Specific Mood")
        print("="*70)

        for mood in ['upbeat', 'calm', 'dramatic']:
            music_path = library.get_music_for_mood(mood)
            if music_path:
                print(f"\n✅ Mood: {mood}")
                print(f"   Music: {Path(music_path).name}")

    print("\n" + "="*70)
    print("✅ LOCAL MUSIC LIBRARY TEST COMPLETE")
    print("="*70)
    print("\n💡 Benefits:")
    print("   • 100% FREE - no API costs")
    print("   • FAST - local files, no network delay")
    print("   • RELIABLE - no rate limits or API failures")
    print("   • QUALITY CONTROL - you choose the music")
    print("\n")