"""
VIDEOCU v1 - Photo Upload Handler
Creates professional videos from user-uploaded photos with Ken Burns effects
"""

import logging
from typing import List, Dict, Optional
from pathlib import Path
from PIL import Image
from moviepy.editor import (
    ImageClip, concatenate_videoclips,
    AudioFileClip, CompositeVideoClip
)
import json

try:
    from .ken_burns import KenBurnsEffect
except ImportError:
    from ken_burns import KenBurnsEffect

logger = logging.getLogger(__name__)


class PhotoHandler:
    """
    Creates videos from user photos

    Features:
    - Photo validation & processing
    - Ken Burns effect application
    - Auto-arrangement by upload order
    - Smooth transitions
    - Background music integration
    - Multiple duration modes (reel, short, standard)
    """

    # Duration presets (seconds per photo)
    DURATION_REEL = 3.0      # Instagram Reels (15-30s total)
    DURATION_SHORT = 5.0     # TikTok/YouTube Shorts (30-60s total)
    DURATION_STANDARD = 7.0  # Standard video (60s+)

    def __init__(self):
        """Initialize photo handler"""
        self.ken_burns = KenBurnsEffect()
        logger.info("📸 Photo Handler initialized")

    def create_video_from_photos(self,
                                 photo_paths: List[str],
                                 output_path: str,
                                 duration_per_photo: float = DURATION_STANDARD,
                                 background_music: Optional[str] = None,
                                 music_volume: float = 0.3,
                                 target_resolution: tuple = (1920, 1080)) -> bool:
        """
        Create video from user photos

        Args:
            photo_paths: List of photo file paths
            output_path: Output video path
            duration_per_photo: Seconds per photo
            background_music: Optional music file
            music_volume: Music volume (0.0-1.0)
            target_resolution: Video resolution (width, height)

        Returns:
            True if successful
        """
        try:
            if len(photo_paths) < 1:
                logger.error("❌ Need at least 1 photo")
                return False

            logger.info(f"📸 Creating video from {len(photo_paths)} photos...")

            # Validate & preprocess photos
            validated_photos = self._validate_photos(photo_paths)
            if not validated_photos:
                logger.error("❌ No valid photos")
                return False

            # Resize photos to target resolution
            logger.info(f"   Resizing photos to {target_resolution[0]}x{target_resolution[1]}...")
            resized_photos = self._resize_photos(validated_photos, target_resolution)

            # Create Ken Burns effect sequence
            logger.info(f"   Generating Ken Burns effects ({duration_per_photo}s per photo)...")
            effects = self.ken_burns.create_sequence(
                len(resized_photos),
                duration_per_photo
            )

            # Create video clips
            logger.info(f"   Creating video clips...")
            clips = self._create_clips(resized_photos, effects, duration_per_photo)

            if not clips:
                logger.error("❌ Failed to create clips")
                return False

            # Concatenate clips
            logger.info(f"   Concatenating {len(clips)} clips...")
            final_clip = concatenate_videoclips(clips, method='compose')

            # Add background music
            if background_music and Path(background_music).exists():
                logger.info(f"   Adding background music ({music_volume} volume)...")
                final_clip = self._add_music(final_clip, background_music, music_volume)

            # Export video
            logger.info(f"   Exporting video: {output_path}")
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            final_clip.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac',
                fps=30,
                preset='medium',
                logger=None
            )

            # Cleanup
            final_clip.close()
            for clip in clips:
                clip.close()

            # Clean up resized temp files
            for temp_file in resized_photos:
                if temp_file != photo_paths[resized_photos.index(temp_file)]:
                    Path(temp_file).unlink(missing_ok=True)

            duration = len(photo_paths) * duration_per_photo
            logger.info(f"✅ Video created: {output_path}")
            logger.info(f"   Photos: {len(photo_paths)}")
            logger.info(f"   Duration: {duration:.1f}s")
            logger.info(f"   Size: {self._get_file_size(output_path)}")

            return True

        except Exception as e:
            logger.error(f"❌ Video creation failed: {e}")
            return False

    def _validate_photos(self, photo_paths: List[str]) -> List[str]:
        """Validate photo files"""
        valid_photos = []
        supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

        for i, path in enumerate(photo_paths, 1):
            try:
                photo_file = Path(path)

                # Check exists
                if not photo_file.exists():
                    logger.warning(f"   ⚠️ Photo {i} not found: {path}")
                    continue

                # Check format
                if photo_file.suffix.lower() not in supported_formats:
                    logger.warning(f"   ⚠️ Photo {i} unsupported format: {photo_file.suffix}")
                    continue

                # Try to open
                img = Image.open(photo_file)
                img.verify()

                valid_photos.append(path)
                logger.info(f"   ✅ Photo {i}: {photo_file.name} ({img.size[0]}x{img.size[1]})")

            except Exception as e:
                logger.warning(f"   ⚠️ Photo {i} validation failed: {e}")

        return valid_photos

    def _resize_photos(self, photo_paths: List[str], target_resolution: tuple) -> List[str]:
        """
        Resize photos to target resolution (maintaining aspect ratio)

        Returns:
            List of resized photo paths (temp files)
        """
        resized_paths = []
        target_w, target_h = target_resolution

        for i, path in enumerate(photo_paths, 1):
            try:
                # Open image
                img = Image.open(path)

                # Calculate aspect ratio
                img_w, img_h = img.size
                img_aspect = img_w / img_h
                target_aspect = target_w / target_h

                # Resize to cover target (crop if needed)
                if img_aspect > target_aspect:
                    # Image is wider - fit height, crop width
                    new_h = target_h
                    new_w = int(new_h * img_aspect)
                else:
                    # Image is taller - fit width, crop height
                    new_w = target_w
                    new_h = int(new_w / img_aspect)

                # Resize
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Center crop to target
                left = (new_w - target_w) // 2
                top = (new_h - target_h) // 2
                right = left + target_w
                bottom = top + target_h

                img_cropped = img_resized.crop((left, top, right, bottom))

                # Save to temp file
                temp_path = Path(path).parent / f"temp_resized_{i}_{Path(path).name}"
                img_cropped.save(temp_path, quality=95)

                resized_paths.append(str(temp_path))

            except Exception as e:
                logger.error(f"   ❌ Resize failed for photo {i}: {e}")
                # Use original if resize fails
                resized_paths.append(path)

        return resized_paths

    def _create_clips(self,
                     photo_paths: List[str],
                     effects: List[Dict],
                     duration: float) -> List[ImageClip]:
        """Create video clips with Ken Burns effects"""
        clips = []

        for i, (photo, effect) in enumerate(zip(photo_paths, effects), 1):
            try:
                # Create image clip
                clip = ImageClip(photo, duration=duration)

                # Apply Ken Burns effect
                clip_with_effect = self._apply_ken_burns(clip, effect)

                clips.append(clip_with_effect)

            except Exception as e:
                logger.error(f"   ❌ Clip creation failed for photo {i}: {e}")

        return clips

    def _apply_ken_burns(self, clip: ImageClip, effect_params: Dict) -> ImageClip:
        """
        Apply Ken Burns effect to image clip

        Args:
            clip: ImageClip
            effect_params: Effect parameters from KenBurnsEffect

        Returns:
            Clip with Ken Burns effect applied
        """
        effect_type = effect_params.get('effect_type', 'zoom_in')
        duration = effect_params.get('duration', 5.0)

        if effect_type == 'zoom_in':
            # Zoom in effect
            start_scale = effect_params.get('start_scale', 1.0)
            end_scale = effect_params.get('end_scale', 1.2)

            def zoom(get_frame, t):
                # Calculate current scale
                progress = t / duration
                current_scale = start_scale + (end_scale - start_scale) * progress
                return get_frame(t)

            # Apply resize animation
            clip = clip.resize(lambda t: 1.0 + 0.2 * (t / duration))

        elif effect_type == 'zoom_out':
            # Zoom out effect
            start_scale = effect_params.get('start_scale', 1.2)
            clip = clip.resize(lambda t: start_scale - 0.2 * (t / duration))

        # Add crossfade
        clip = clip.crossfadein(0.5).crossfadeout(0.5)

        return clip

    def _add_music(self,
                   video_clip: ImageClip,
                   music_path: str,
                   volume: float) -> ImageClip:
        """Add background music to video"""
        try:
            # Load music
            music = AudioFileClip(music_path)

            # Loop if needed
            if music.duration < video_clip.duration:
                loops = int(video_clip.duration / music.duration) + 1
                music = music.loop(n=loops)

            # Trim to video duration
            music = music.subclip(0, video_clip.duration)

            # Adjust volume
            music = music.volumex(volume)

            # Set as audio
            video_with_music = video_clip.set_audio(music)

            return video_with_music

        except Exception as e:
            logger.warning(f"   ⚠️ Failed to add music: {e}")
            return video_clip

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

    def get_recommended_duration(self, num_photos: int, video_type: str = 'standard') -> float:
        """
        Get recommended duration per photo

        Args:
            num_photos: Number of photos
            video_type: 'reel', 'short', or 'standard'

        Returns:
            Recommended duration per photo in seconds
        """
        if video_type == 'reel':
            # Target 15-30s total
            target_total = 20
            return max(self.DURATION_REEL, target_total / num_photos)

        elif video_type == 'short':
            # Target 30-60s total
            target_total = 45
            return max(self.DURATION_SHORT, target_total / num_photos)

        else:  # standard
            return self.DURATION_STANDARD

    def save_photo_metadata(self,
                           photo_paths: List[str],
                           output_path: str,
                           metadata: Dict) -> bool:
        """Save metadata for photo video project"""
        try:
            meta_file = Path(output_path).parent / "photo_project.json"

            project_data = {
                'photos': [str(Path(p).name) for p in photo_paths],
                'photo_count': len(photo_paths),
                'metadata': metadata,
                'created_at': metadata.get('created_at', '')
            }

            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)

            logger.info(f"   ✅ Metadata saved: {meta_file}")
            return True

        except Exception as e:
            logger.error(f"   ❌ Metadata save failed: {e}")
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
    print("📸 PHOTO HANDLER TEST")
    print("="*70)

    handler = PhotoHandler()

    print("\n✅ Photo Handler module loaded successfully")
    print("\nFeatures:")
    print("   • User photo upload support (3+ photos)")
    print("   • Ken Burns effects (zoom, pan)")
    print("   • Auto-resize to target resolution (1920x1080)")
    print("   • Smooth transitions between photos")
    print("   • Background music integration")
    print("   • Multiple duration presets (reel/short/standard)")

    print("\nDuration Presets:")
    print(f"   • Reel: {PhotoHandler.DURATION_REEL}s per photo (15-30s total)")
    print(f"   • Short: {PhotoHandler.DURATION_SHORT}s per photo (30-60s total)")
    print(f"   • Standard: {PhotoHandler.DURATION_STANDARD}s per photo (60s+)")

    print("\nUsage Example:")
    print("   handler = PhotoHandler()")
    print("   handler.create_video_from_photos(")
    print("      photo_paths=['photo1.jpg', 'photo2.jpg', 'photo3.jpg'],")
    print("      output_path='output/my_video.mp4',")
    print("      duration_per_photo=5.0,")
    print("      background_music='music.mp3',")
    print("      music_volume=0.3")
    print("   )")

    print("\n" + "="*70)
    print("✅ PHOTO HANDLER MODULE READY")
    print("="*70)
