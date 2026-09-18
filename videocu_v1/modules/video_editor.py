"""
VIDEOCU v1 - Video Editor Module
MoviePy + FFmpeg ile video montaj sistemi
"""

from moviepy.editor import (
    VideoFileClip, ImageClip, AudioFileClip,
    CompositeVideoClip, concatenate_videoclips,
    ColorClip
)
import moviepy.video.fx.all as vfx
import moviepy.audio.fx.all as afx
import logging
from pathlib import Path
from typing import List, Dict, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class VideoEditor:
    """MoviePy ile video montaj ve düzenleme"""

    def __init__(self,
                 resolution: tuple = (1920, 1080),
                 fps: int = 30,
                 codec: str = 'libx264'):
        """
        Args:
            resolution: Video çözünürlüğü (width, height)
            fps: Frame rate (frames per second)
            codec: Video codec (libx264 = H.264)
        """
        self.resolution = resolution
        self.fps = fps
        self.codec = codec
        logger.info(f"✅ VideoEditor initialized ({resolution[0]}x{resolution[1]}, {fps}fps)")

    def create_video_from_script(self,
                                 script_data: Dict,
                                 image_files: List[str],
                                 voiceover_path: Optional[str] = None,
                                 music_path: Optional[str] = None,
                                 output_path: str = "output.mp4") -> bool:
        """
        Script verilerinden tam video oluştur

        Args:
            script_data: ContentGenerator'dan gelen script dict
            image_files: Scene görsellerinin dosya yolları (sıralı)
            voiceover_path: Voiceover MP3 dosyası (opsiyonel)
            music_path: Arkaplan müziği MP3 (opsiyonel)
            output_path: Çıkış video dosyası

        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"🎬 Creating video: {script_data.get('title', 'Untitled')}")

            # Validate inputs
            if not image_files:
                logger.error("❌ No image files provided")
                return False

            scenes = script_data.get('scenes', [])
            if not scenes:
                logger.error("❌ No scenes in script data")
                return False

            # Calculate scene durations
            total_duration = script_data.get('metadata', {}).get('duration', 60)
            scene_duration = total_duration / len(scenes)

            logger.info(f"📊 {len(scenes)} scenes x {scene_duration:.1f}s = {total_duration}s")

            # Create video clips from images
            video_clips = []
            for i, (scene, img_path) in enumerate(zip(scenes, image_files)):
                if not Path(img_path).exists():
                    logger.warning(f"⚠️ Image not found: {img_path}, using placeholder")
                    # Create colored placeholder
                    clip = ColorClip(
                        size=self.resolution,
                        color=(30, 30, 30),
                        duration=scene_duration
                    )
                else:
                    # Create image clip
                    clip = ImageClip(img_path, duration=scene_duration)

                    # Resize to match resolution
                    clip = clip.fx(vfx.resize, self.resolution)

                # Add fade transitions
                if i == 0:
                    clip = clip.fx(vfx.fadein, 0.5)  # First scene fade in
                if i == len(scenes) - 1:
                    clip = clip.fx(vfx.fadeout, 0.5)  # Last scene fade out

                video_clips.append(clip)
                logger.info(f"   Scene {i+1}/{len(scenes)}: {scene_duration:.1f}s")

            # Concatenate all scenes
            logger.info("🔗 Combining scenes...")
            final_video = concatenate_videoclips(video_clips, method="compose")

            # Add voiceover audio
            if voiceover_path and Path(voiceover_path).exists():
                logger.info(f"🎤 Adding voiceover: {voiceover_path}")
                voiceover = AudioFileClip(voiceover_path)
                final_video = final_video.set_audio(voiceover)

            # Add background music (lower volume if voiceover exists)
            if music_path and Path(music_path).exists():
                logger.info(f"🎵 Adding background music: {music_path}")
                music = AudioFileClip(music_path)

                # Loop music to match video duration
                if music.duration < final_video.duration:
                    loops = int(final_video.duration / music.duration) + 1
                    music = music.loop(loops)

                # Trim to video duration
                music = music.subclip(0, final_video.duration)

                # Lower volume if voiceover exists
                volume = 0.15 if voiceover_path else 0.5
                music = music.volumex(volume)

                # Mix with voiceover
                if final_video.audio:
                    from moviepy.audio.AudioClip import CompositeAudioClip
                    final_audio = CompositeAudioClip([final_video.audio, music])
                    final_video = final_video.set_audio(final_audio)
                else:
                    final_video = final_video.set_audio(music)

            # Render video
            logger.info(f"🎥 Rendering video to: {output_path}")
            logger.info(f"   Duration: {final_video.duration:.1f}s")
            logger.info(f"   Resolution: {self.resolution[0]}x{self.resolution[1]}")
            logger.info(f"   FPS: {self.fps}")
            logger.info(f"   Codec: {self.codec}")

            final_video.write_videofile(
                output_path,
                fps=self.fps,
                codec=self.codec,
                audio_codec='aac',
                temp_audiofile=f'temp-audio-{datetime.now().timestamp()}.m4a',
                remove_temp=True,
                logger=None  # Suppress MoviePy logger
            )

            # Cleanup
            final_video.close()
            for clip in video_clips:
                clip.close()

            logger.info(f"✅ Video created successfully: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Video creation failed: {e}")
            return False

    def add_subtitles(self,
                     video_path: str,
                     script_data: Dict,
                     output_path: str,
                     font: str = 'Arial-Bold',
                     fontsize: int = 48,
                     color: str = 'white',
                     stroke_color: str = 'black',
                     stroke_width: int = 2) -> bool:
        """
        Video'ya altyazı ekle (FFmpeg ile SRT dosyası kullanarak)

        Args:
            video_path: Kaynak video dosyası
            script_data: Script verileri
            output_path: Çıkış dosyası
            font: Font adı (not used - requires ImageMagick)
            fontsize: Font boyutu (not used - requires ImageMagick)
            color: Yazı rengi (not used - requires ImageMagick)
            stroke_color: Kontur rengi (not used - requires ImageMagick)
            stroke_width: Kontur kalınlığı (not used - requires ImageMagick)

        Returns:
            Başarılı ise True

        Note: ImageMagick dependency removed. Subtitles via FFmpeg SRT files instead.
        """
        try:
            logger.info(f"📝 Creating SRT subtitle file for: {video_path}")

            # Create SRT file from scenes
            srt_path = str(Path(video_path).with_suffix('.srt'))
            scenes = script_data.get('scenes', [])

            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, scene in enumerate(scenes, 1):
                    # Parse time range
                    time_str = scene.get('time', '0-5s')
                    start_time, end_time = self._parse_time_range(time_str)

                    # Get text
                    text = scene.get('text', '')
                    if not text:
                        continue

                    # Truncate if too long
                    if len(text) > 100:
                        text = text[:97] + "..."

                    # Write SRT format
                    f.write(f"{i}\n")
                    f.write(f"{self._format_srt_time(start_time)} --> {self._format_srt_time(end_time)}\n")
                    f.write(f"{text}\n\n")

            logger.info(f"✅ SRT file created: {srt_path}")
            logger.info(f"   Use FFmpeg to burn subtitles if needed")
            logger.info(f"   Or YouTube will auto-sync the SRT file")
            return True

        except Exception as e:
            logger.error(f"❌ Subtitle creation failed: {e}")
            return False

    def _format_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def create_intro(self,
                    text: str,
                    duration: int = 3,
                    output_path: str = "intro.mp4",
                    background_color: tuple = (10, 10, 20),
                    text_color: str = 'white') -> bool:
        """
        Basit intro/outro oluştur (renkli arkaplan)

        Args:
            text: Gösterilecek metin (şu an kullanılmıyor - ImageMagick gereksinimi)
            duration: Süre (saniye)
            output_path: Çıkış dosyası
            background_color: Arkaplan rengi (R, G, B)
            text_color: Yazı rengi (şu an kullanılmıyor)

        Returns:
            Başarılı ise True

        Note: TextClip requires ImageMagick. Bu versiyonda sadece renkli intro.
        """
        try:
            logger.info(f"🎬 Creating intro (colored background)")

            # Background only (no text to avoid ImageMagick dependency)
            intro = ColorClip(
                size=self.resolution,
                color=background_color,
                duration=duration
            )

            # Add fade effects
            intro = intro.fx(vfx.fadein, 0.5)
            intro = intro.fx(vfx.fadeout, 0.5)

            # Render
            intro.write_videofile(
                output_path,
                fps=self.fps,
                codec=self.codec,
                logger=None
            )

            intro.close()
            logger.info(f"✅ Intro created: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Intro creation failed: {e}")
            return False

    def merge_videos(self,
                    video_paths: List[str],
                    output_path: str = "merged.mp4",
                    transition_duration: float = 0.5) -> bool:
        """
        Birden fazla videoyu birleştir (FFmpeg filter_complex ile)

        Args:
            video_paths: Birleştirilecek video dosyaları
            output_path: Çıkış dosyası
            transition_duration: Geçiş efekti süresi (not used in FFmpeg merge)

        Returns:
            Başarılı ise True
        """
        import subprocess

        try:
            logger.info(f"🔗 Merging {len(video_paths)} videos with FFmpeg...")

            # Validate paths
            valid_paths = []
            for path in video_paths:
                if Path(path).exists():
                    valid_paths.append(str(path))
                    logger.info(f"   + {Path(path).name}")
                else:
                    logger.warning(f"⚠️ Video not found: {path}")

            if not valid_paths:
                logger.error("❌ No valid video clips found")
                return False

            # Find FFmpeg path
            ffmpeg_path = r'C:\Users\cyhnsrgc\AppData\Local\Microsoft\WinGet\Links\ffmpeg.EXE'
            if not Path(ffmpeg_path).exists():
                ffmpeg_path = 'ffmpeg'

            # Build FFmpeg command with filter_complex for reliable merging
            # This approach handles different resolutions/fps automatically
            cmd = [ffmpeg_path, '-y']

            # Add input files
            for vpath in valid_paths:
                cmd.extend(['-i', vpath])

            # Build filter_complex to scale and concat all videos
            n = len(valid_paths)
            scale_filters = []
            concat_inputs = ""

            for i in range(n):
                # Scale each input to target resolution, set fps, and format
                scale_filters.append(
                    f'[{i}:v]scale={self.resolution[0]}:{self.resolution[1]}:force_original_aspect_ratio=decrease,'
                    f'pad={self.resolution[0]}:{self.resolution[1]}:(ow-iw)/2:(oh-ih)/2,'
                    f'fps={self.fps},format=yuv420p[v{i}]'
                )
                concat_inputs += f'[v{i}]'

            # Combine all filters
            filter_complex = ';'.join(scale_filters)
            filter_complex += f';{concat_inputs}concat=n={n}:v=1:a=0[outv]'

            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '[outv]',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                str(output_path)
            ])

            logger.info(f"🎥 Merging {n} videos with filter_complex...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0 and Path(output_path).exists():
                file_size = Path(output_path).stat().st_size / (1024 * 1024)
                logger.info(f"✅ Videos merged: {output_path} ({file_size:.1f} MB)")
                return True
            else:
                logger.error(f"❌ FFmpeg merge failed: {result.stderr[:500] if result.stderr else 'Unknown error'}")
                return False

        except Exception as e:
            logger.error(f"❌ Video merging failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def add_watermark(self,
                     video_path: str,
                     watermark_image: str,
                     output_path: str,
                     position: str = 'bottom-right',
                     opacity: float = 0.5,
                     scale: float = 0.1) -> bool:
        """
        Video'ya watermark ekle (görsel olarak)

        Args:
            video_path: Kaynak video
            watermark_image: Watermark görsel dosyası (PNG/JPG)
            output_path: Çıkış dosyası
            position: Pozisyon (top-left, top-right, bottom-left, bottom-right, center)
            opacity: Şeffaflık (0.0-1.0)
            scale: Watermark boyutu (video genişliğinin yüzdesi)

        Returns:
            Başarılı ise True

        Note: Text watermark requires ImageMagick. Bu versiyon image watermark kullanır.
        """
        try:
            logger.info(f"💧 Adding watermark from: {watermark_image}")

            if not Path(watermark_image).exists():
                logger.warning(f"⚠️ Watermark image not found: {watermark_image}")
                # Just copy video without watermark
                from shutil import copy2
                copy2(video_path, output_path)
                return True

            # Load video
            video = VideoFileClip(video_path)

            # Load watermark image
            watermark = ImageClip(watermark_image)
            watermark = watermark.set_opacity(opacity)
            watermark = watermark.set_duration(video.duration)

            # Scale watermark
            watermark_width = int(self.resolution[0] * scale)
            watermark = watermark.fx(vfx.resize, width=watermark_width)

            # Position watermark
            margin = 20
            positions = {
                'top-left': (margin, margin),
                'top-right': (self.resolution[0] - watermark.w - margin, margin),
                'bottom-left': (margin, self.resolution[1] - watermark.h - margin),
                'bottom-right': (self.resolution[0] - watermark.w - margin,
                                self.resolution[1] - watermark.h - margin),
                'center': 'center'
            }
            watermark = watermark.set_position(positions.get(position, 'bottom-right'))

            # Composite
            final_video = CompositeVideoClip([video, watermark])

            # Render
            logger.info(f"🎥 Rendering video with watermark...")
            final_video.write_videofile(
                output_path,
                fps=self.fps,
                codec=self.codec,
                audio_codec='aac',
                logger=None
            )

            # Cleanup
            final_video.close()
            video.close()

            logger.info(f"✅ Watermark added: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Watermark addition failed: {e}")
            return False

    def get_video_info(self, video_path: str) -> Optional[Dict]:
        """
        Video bilgilerini al

        Args:
            video_path: Video dosyası

        Returns:
            Video metadata dict
        """
        try:
            if not Path(video_path).exists():
                logger.error(f"❌ Video not found: {video_path}")
                return None

            video = VideoFileClip(video_path)

            info = {
                'path': video_path,
                'duration': video.duration,
                'fps': video.fps,
                'size': (video.w, video.h),
                'has_audio': video.audio is not None,
                'file_size_mb': Path(video_path).stat().st_size / (1024 * 1024)
            }

            video.close()

            logger.info(f"📊 Video info: {video.duration:.1f}s, {video.w}x{video.h}")
            return info

        except Exception as e:
            logger.error(f"❌ Failed to get video info: {e}")
            return None

    def _parse_time_range(self, time_str: str) -> tuple:
        """
        Parse scene time range string

        Args:
            time_str: Time string (e.g., "0-5s", "5-18s")

        Returns:
            (start_time, end_time) in seconds
        """
        try:
            # Remove 's' and split
            time_str = time_str.replace('s', '').strip()
            start, end = time_str.split('-')
            return (float(start), float(end))
        except Exception:
            logger.warning(f"⚠️ Invalid time format: {time_str}, using defaults")
            return (0.0, 5.0)

    def create_youtube_video(self,
                            script_data: Dict,
                            assets: Dict,
                            output_dir: str = "output/videos") -> Optional[str]:
        """
        YouTube için hazır video oluştur (all-in-one)

        Args:
            script_data: ContentGenerator'dan script
            assets: {
                'images': List[str],        # Scene görselleri
                'voiceover': str,           # Voiceover MP3
                'music': str,               # Arkaplan müziği (opsiyonel)
                'intro_text': str,          # Intro metni (opsiyonel)
                'watermark_image': str,     # Watermark PNG/JPG (opsiyonel)
            }
            output_dir: Çıkış klasörü

        Returns:
            Video dosya yolu veya None
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Generate filename from title
            title = script_data.get('title', 'video')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))
            safe_title = safe_title.replace(' ', '_')[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            video_file = output_path / f"{safe_title}_{timestamp}.mp4"

            logger.info(f"🎬 Creating YouTube video: {video_file.name}")

            # Step 1: Create main video
            temp_video = output_path / f"temp_main_{timestamp}.mp4"
            success = self.create_video_from_script(
                script_data=script_data,
                image_files=assets.get('images', []),
                voiceover_path=assets.get('voiceover'),
                music_path=assets.get('music'),
                output_path=str(temp_video)
            )

            if not success:
                logger.error("❌ Main video creation failed")
                return None

            # Step 2: Add intro if specified
            if assets.get('intro_text'):
                intro_file = output_path / f"temp_intro_{timestamp}.mp4"
                self.create_intro(
                    text=assets['intro_text'],
                    duration=3,
                    output_path=str(intro_file)
                )

                # Merge intro + main video
                temp_merged = output_path / f"temp_merged_{timestamp}.mp4"
                self.merge_videos(
                    video_paths=[str(intro_file), str(temp_video)],
                    output_path=str(temp_merged)
                )

                # Update temp video path
                temp_video.unlink()  # Delete old temp
                temp_video = temp_merged

            # Step 3: Add watermark if specified (requires watermark image file)
            if assets.get('watermark_image') and Path(assets['watermark_image']).exists():
                self.add_watermark(
                    video_path=str(temp_video),
                    watermark_image=assets['watermark_image'],
                    output_path=str(video_file),
                    position='bottom-right',
                    opacity=0.3
                )
                temp_video.unlink()  # Delete temp
            else:
                # Just rename temp to final
                temp_video.rename(video_file)

            # Verify output
            info = self.get_video_info(str(video_file))
            if info:
                logger.info(f"✅ YouTube video ready!")
                logger.info(f"   File: {video_file}")
                logger.info(f"   Duration: {info['duration']:.1f}s")
                logger.info(f"   Size: {info['file_size_mb']:.1f} MB")
                return str(video_file)
            else:
                return None

        except Exception as e:
            logger.error(f"❌ YouTube video creation failed: {e}")
            return None

    def extract_audio(self, video_path: str, output_path: str = "audio.mp3") -> bool:
        """
        Video'dan ses çıkar

        Args:
            video_path: Kaynak video
            output_path: Çıkış MP3 dosyası

        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"🎤 Extracting audio from: {video_path}")

            video = VideoFileClip(video_path)

            if not video.audio:
                logger.warning("⚠️ Video has no audio")
                return False

            video.audio.write_audiofile(output_path, logger=None)
            video.close()

            logger.info(f"✅ Audio extracted: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Audio extraction failed: {e}")
            return False


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

    print("\n" + "="*60)
    print("🎬 VIDEO EDITOR TEST")
    print("="*60)

    # Test with generated script
    script_file = Path("output/test_content/script.txt")

    if not script_file.exists():
        print("❌ Script file not found. Run test_content_pipeline.py first!")
        sys.exit(1)

    # Mock script data (in real use, load from ContentGenerator output)
    mock_script = {
        'title': 'Test Video',
        'description': 'Test video description',
        'hook': 'Test hook',
        'script': 'This is a test script for video editing.',
        'scenes': [
            {
                'time': '0-5s',
                'text': 'Scene 1: Introduction',
                'visual': 'Opening visual',
                'image_prompt': 'test prompt 1'
            },
            {
                'time': '5-10s',
                'text': 'Scene 2: Main content',
                'visual': 'Main visual',
                'image_prompt': 'test prompt 2'
            },
            {
                'time': '10-15s',
                'text': 'Scene 3: Conclusion',
                'visual': 'Closing visual',
                'image_prompt': 'test prompt 3'
            }
        ],
        'hashtags': ['#test'],
        'metadata': {
            'duration': 15,
            'language': 'de'
        }
    }

    # Create editor
    editor = VideoEditor(resolution=(1920, 1080), fps=30)

    # Test 1: Create intro
    print("\n📝 TEST 1: Creating intro...")
    intro_path = "output/test_content/intro.mp4"
    success = editor.create_intro(
        text="VIDEOCU v1\nAI Content Creator",
        duration=3,
        output_path=intro_path
    )

    if success:
        info = editor.get_video_info(intro_path)
        print(f"✅ Intro created: {info['duration']:.1f}s, {info['file_size_mb']:.1f} MB")

    # Test 2: Create video from images (if available)
    print("\n📝 TEST 2: Creating video from script...")
    images_dir = Path("output/test_content/images")

    if images_dir.exists():
        image_files = sorted(list(images_dir.glob("scene_*.jpg")))

        if image_files:
            print(f"✅ Found {len(image_files)} scene images")

            # Create placeholder images if we don't have enough
            while len(image_files) < len(mock_script['scenes']):
                image_files.append(str(image_files[0]))  # Duplicate first image

            test_video = "output/test_content/test_video.mp4"
            success = editor.create_video_from_script(
                script_data=mock_script,
                image_files=[str(f) for f in image_files],
                output_path=test_video
            )

            if success:
                info = editor.get_video_info(test_video)
                print(f"✅ Video created: {info['duration']:.1f}s, {info['file_size_mb']:.1f} MB")
        else:
            print("⚠️ No scene images found")
    else:
        print("⚠️ Images directory not found")

    print("\n" + "="*60)
    print("✅ VIDEO EDITOR TEST COMPLETE")
    print("="*60)
    print("\n💡 Features Ready:")
    print("   - Create video from script + images")
    print("   - Add voiceover and background music")
    print("   - Add subtitles from script")
    print("   - Create intro/outro")
    print("   - Merge multiple videos")
    print("   - Add watermarks")
    print("   - Extract audio from video")
