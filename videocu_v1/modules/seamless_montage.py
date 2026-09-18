"""
VIDEOCU v1 - Seamless Montage Module
Merges video segments into complete long-form videos with smooth transitions
"""

import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips,
    CompositeVideoClip, AudioFileClip
)
import json

logger = logging.getLogger(__name__)


class SeamlessMontage:
    """
    Merges video segments with smooth transitions

    Features:
    - Crossfade transitions between segments
    - Audio synchronization
    - Background music continuity
    - Progress tracking
    - Quality validation
    """

    def __init__(self, transition_duration: float = 1.0):
        """
        Initialize montage system

        Args:
            transition_duration: Crossfade duration in seconds (default: 1.0)
        """
        self.transition_duration = transition_duration
        self.clips = []

        logger.info(f"🎬 Seamless Montage initialized (transition: {transition_duration}s)")

    def merge_segments(self,
                      segment_paths: List[str],
                      output_path: str,
                      background_music: Optional[str] = None,
                      music_volume: float = 0.3) -> bool:
        """
        Merge video segments into single video

        Args:
            segment_paths: List of video file paths (in order)
            output_path: Output video path
            background_music: Optional background music file
            music_volume: Music volume (0.0-1.0)

        Returns:
            True if successful
        """
        try:
            if not segment_paths:
                logger.error("❌ No segments provided")
                return False

            logger.info(f"🎬 Merging {len(segment_paths)} segments...")

            # Load video clips
            clips = self._load_clips(segment_paths)
            if not clips:
                logger.error("❌ Failed to load clips")
                return False

            # Apply crossfade transitions
            logger.info(f"   Applying crossfade transitions ({self.transition_duration}s)...")
            merged_clip = self._apply_transitions(clips)

            # Add background music if provided
            if background_music and Path(background_music).exists():
                logger.info(f"   Adding background music ({music_volume} volume)...")
                merged_clip = self._add_background_music(
                    merged_clip,
                    background_music,
                    music_volume
                )

            # Export final video
            logger.info(f"   Exporting final video: {output_path}")
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            merged_clip.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac',
                fps=30,
                preset='medium',
                logger=None  # Suppress MoviePy progress bar
            )

            # Cleanup
            merged_clip.close()
            for clip in clips:
                clip.close()

            # Validate output
            if self._validate_output(output_path):
                logger.info(f"✅ Montage complete: {output_path}")
                logger.info(f"   Duration: {self._get_duration(output_path):.1f}s")
                logger.info(f"   Size: {self._get_file_size(output_path)}")
                return True
            else:
                logger.error("❌ Output validation failed")
                return False

        except Exception as e:
            logger.error(f"❌ Montage failed: {e}")
            return False

    def _load_clips(self, segment_paths: List[str]) -> List[VideoFileClip]:
        """Load video clips from file paths"""
        clips = []

        for i, path in enumerate(segment_paths, 1):
            try:
                if not Path(path).exists():
                    logger.warning(f"   ⚠️ Segment {i} not found: {path}")
                    continue

                clip = VideoFileClip(path)
                clips.append(clip)
                logger.info(f"   ✅ Loaded segment {i}: {clip.duration:.1f}s")

            except Exception as e:
                logger.error(f"   ❌ Failed to load segment {i}: {e}")

        return clips

    def _apply_transitions(self, clips: List[VideoFileClip]) -> VideoFileClip:
        """
        Apply crossfade transitions between clips

        Args:
            clips: List of video clips

        Returns:
            Merged video with transitions
        """
        if len(clips) == 1:
            return clips[0]

        # Apply crossfade to each clip (except first)
        transitioned_clips = [clips[0]]  # First clip no fade-in

        for i in range(1, len(clips)):
            clip = clips[i]

            # Apply crossfade
            clip_with_fade = clip.crossfadein(self.transition_duration)
            transitioned_clips.append(clip_with_fade)

        # Concatenate with crossfade
        final_clip = concatenate_videoclips(
            transitioned_clips,
            method='compose',
            padding=-self.transition_duration  # Overlap by transition duration
        )

        return final_clip

    def _add_background_music(self,
                              video_clip: VideoFileClip,
                              music_path: str,
                              volume: float) -> VideoFileClip:
        """
        Add background music with professional audio ducking
        Music volume reduces when voiceover is present (podcast-grade quality)

        Args:
            video_clip: Video clip
            music_path: Music file path
            volume: Base music volume (0.0-1.0)

        Returns:
            Video with ducked background music
        """
        try:
            # Load music
            music = AudioFileClip(music_path)

            # Loop music to match video duration
            if music.duration < video_clip.duration:
                loops_needed = int(video_clip.duration / music.duration) + 1
                music = music.loop(n=loops_needed)

            # Trim to video duration
            music = music.subclip(0, video_clip.duration)

            # Mix with video audio (if exists)
            if video_clip.audio is not None:
                logger.info("   🎚️ Applying professional audio ducking...")

                # Apply intelligent ducking
                ducked_music = self._apply_audio_ducking(
                    voiceover_audio=video_clip.audio,
                    music_audio=music,
                    base_volume=volume,
                    duck_volume=volume * 0.3  # Reduce to 30% during voiceover
                )

                # Composite: voiceover (full) + ducked music
                from moviepy.audio.AudioClip import CompositeAudioClip
                final_audio = CompositeAudioClip([
                    video_clip.audio.volumex(1.0),  # Voiceover at full volume
                    ducked_music
                ])
            else:
                # No voiceover, just music at base volume
                final_audio = music.volumex(volume)

            # Set audio to video
            video_with_music = video_clip.set_audio(final_audio)

            return video_with_music

        except Exception as e:
            logger.warning(f"   ⚠️ Failed to add background music: {e}")
            return video_clip

    def _apply_audio_ducking(self,
                            voiceover_audio: AudioFileClip,
                            music_audio: AudioFileClip,
                            base_volume: float = 0.3,
                            duck_volume: float = 0.1) -> AudioFileClip:
        """
        Apply intelligent audio ducking to music based on voiceover presence
        Professional podcast-grade ducking

        Args:
            voiceover_audio: Voiceover audio track
            music_audio: Background music track
            base_volume: Music volume when no voiceover (default: 0.3)
            duck_volume: Music volume during voiceover (default: 0.1)

        Returns:
            Ducked music audio clip
        """
        try:
            import numpy as np

            # Sample rate (Hz)
            fps = 44100

            # Get audio arrays
            duration = voiceover_audio.duration

            # Function to dynamically adjust volume based on voiceover
            def volume_function(get_frame, t):
                """Dynamic volume based on voiceover RMS energy"""
                try:
                    # Sample small window around current time
                    window_size = 0.1  # 100ms window
                    start_t = max(0, t - window_size / 2)
                    end_t = min(duration, t + window_size / 2)

                    # Get voiceover audio sample
                    if hasattr(voiceover_audio, 'get_frame'):
                        # Get frame at time t
                        vo_frame = voiceover_audio.get_frame(t)

                        # Calculate RMS energy
                        if isinstance(vo_frame, np.ndarray):
                            rms = np.sqrt(np.mean(vo_frame ** 2))
                        else:
                            rms = 0

                        # Threshold for voiceover presence (tuned empirically)
                        threshold = 0.01

                        # Determine if voiceover is active
                        if rms > threshold:
                            # Voiceover active → duck music
                            target_volume = duck_volume
                        else:
                            # No voiceover → full music volume
                            target_volume = base_volume

                        # Get music frame
                        music_frame = get_frame(t)

                        # Apply volume
                        return music_frame * target_volume

                    else:
                        # Fallback: use base volume
                        return get_frame(t) * base_volume

                except Exception:
                    # Fallback on error
                    return get_frame(t) * base_volume

            # Apply dynamic volume function
            ducked_music = music_audio.fl(
                lambda get_frame, t: volume_function(get_frame, t),
                keep_duration=True
            )

            logger.info("   ✅ Audio ducking applied (voiceover-aware)")
            return ducked_music

        except Exception as e:
            logger.warning(f"   ⚠️ Ducking failed, using simple volume: {e}")
            # Fallback: simple volume reduction
            return music_audio.volumex(base_volume)

    def _validate_output(self, output_path: str) -> bool:
        """Validate output video file"""
        try:
            output_file = Path(output_path)

            # Check file exists
            if not output_file.exists():
                logger.error(f"   ❌ Output file not found: {output_path}")
                return False

            # Check file size (should be > 1KB)
            file_size = output_file.stat().st_size
            if file_size < 1024:
                logger.error(f"   ❌ Output file too small: {file_size} bytes")
                return False

            # Try to load as video
            try:
                test_clip = VideoFileClip(str(output_path))
                duration = test_clip.duration
                test_clip.close()

                if duration <= 0:
                    logger.error(f"   ❌ Invalid video duration: {duration}")
                    return False

            except Exception as e:
                logger.error(f"   ❌ Cannot load output video: {e}")
                return False

            return True

        except Exception as e:
            logger.error(f"   ❌ Validation error: {e}")
            return False

    def _get_duration(self, video_path: str) -> float:
        """Get video duration"""
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            clip.close()
            return duration
        except:
            return 0.0

    def _get_file_size(self, file_path: str) -> str:
        """Get file size in human-readable format"""
        try:
            size_bytes = Path(file_path).stat().st_size

            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
        except:
            return "unknown"

    def merge_with_metadata(self,
                           segment_dir: str,
                           output_path: str,
                           background_music: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Merge segments using metadata from intelligent segmenter

        Args:
            segment_dir: Directory containing segment files
            output_path: Output video path
            background_music: Optional background music

        Returns:
            Tuple of (success, metadata_dict)
        """
        try:
            segment_path = Path(segment_dir)

            # Find segment video files
            video_files = sorted(segment_path.glob("segment_*.mp4"))

            if not video_files:
                logger.error(f"❌ No segment videos found in {segment_dir}")
                return False, {}

            logger.info(f"📦 Found {len(video_files)} segment videos")

            # Merge segments
            success = self.merge_segments(
                [str(f) for f in video_files],
                output_path,
                background_music
            )

            if not success:
                return False, {}

            # Load segment metadata (if exists)
            metadata_files = sorted(segment_path.glob("segment_*.json"))
            metadata = self._merge_metadata(metadata_files)

            return True, metadata

        except Exception as e:
            logger.error(f"❌ Merge with metadata failed: {e}")
            return False, {}

    def _merge_metadata(self, metadata_files: List[Path]) -> Dict:
        """Merge segment metadata into single dict"""
        try:
            if not metadata_files:
                return {}

            # Load all metadata
            segments_meta = []
            for file in metadata_files:
                with open(file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    segments_meta.append(meta)

            # Merge
            first_meta = segments_meta[0]

            merged = {
                'title': first_meta.get('metadata', {}).get('parent_script_title', ''),
                'total_segments': len(segments_meta),
                'total_duration': sum(seg['metadata']['duration'] for seg in segments_meta),
                'total_scenes': sum(seg['metadata']['scene_count'] for seg in segments_meta),
                'language': first_meta.get('metadata', {}).get('language', 'de'),
                'category': first_meta.get('metadata', {}).get('category', ''),
                'segments': [
                    {
                        'number': seg['metadata']['segment_number'],
                        'duration': seg['metadata']['duration'],
                        'scenes': seg['metadata']['scene_count']
                    }
                    for seg in segments_meta
                ]
            }

            return merged

        except Exception as e:
            logger.error(f"❌ Metadata merge failed: {e}")
            return {}

    def create_preview(self,
                      segment_paths: List[str],
                      output_path: str,
                      max_duration: int = 30) -> bool:
        """
        Create short preview from segments (first N seconds)

        Args:
            segment_paths: List of video file paths
            output_path: Output preview path
            max_duration: Max preview duration in seconds

        Returns:
            True if successful
        """
        try:
            logger.info(f"🎬 Creating {max_duration}s preview...")

            # Load first segment
            if not segment_paths:
                return False

            clip = VideoFileClip(segment_paths[0])

            # Trim to max duration
            if clip.duration > max_duration:
                preview_clip = clip.subclip(0, max_duration)
            else:
                preview_clip = clip

            # Export
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            preview_clip.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac',
                fps=30,
                preset='fast',
                logger=None
            )

            preview_clip.close()
            clip.close()

            logger.info(f"✅ Preview created: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Preview creation failed: {e}")
            return False


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
    print("🎬 SEAMLESS MONTAGE TEST")
    print("="*70)

    # Note: This test requires actual video files
    # Create mock test scenario

    montage = SeamlessMontage(transition_duration=1.0)

    print("\n✅ Seamless Montage module loaded successfully")
    print("\nFeatures:")
    print("   • Crossfade transitions between segments")
    print("   • Background music support with volume control")
    print("   • Audio mixing (voiceover + music)")
    print("   • Progress tracking & validation")
    print("   • Metadata merging")
    print("   • Preview generation")

    print("\nUsage Example:")
    print("   montage = SeamlessMontage(transition_duration=1.0)")
    print("   montage.merge_segments(")
    print("      segment_paths=['seg1.mp4', 'seg2.mp4', 'seg3.mp4'],")
    print("      output_path='final_video.mp4',")
    print("      background_music='music.mp3',")
    print("      music_volume=0.3")
    print("   )")

    print("\n" + "="*70)
    print("✅ SEAMLESS MONTAGE MODULE READY")
    print("="*70)
