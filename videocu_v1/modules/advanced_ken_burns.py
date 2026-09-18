"""
VIDEOCU v1 - Advanced Ken Burns Effect Module
FFmpeg ile profesyonel animasyon efektleri (FREE)

Efektler:
- Zoom In/Out: Yavaş zoom
- Pan: Sol/sağ/yukarı/aşağı kayma
- Cinematic Drift: Çapraz hareket
- Parallax: Derinlik hissi
- Rotation: Hafif dönüş
- Kombinasyonlar: zoom + pan
"""

import subprocess
import logging
import random
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import shutil
import os

logger = logging.getLogger(__name__)


class AdvancedKenBurns:
    """
    FFmpeg ile gelişmiş Ken Burns efektleri

    Features:
    - 8+ farklı efekt türü
    - Akıllı efekt dizisi (tekrar etmeyen)
    - Smooth easing (ease-in-out)
    - Custom duration ve intensity
    - Batch processing
    """

    # Available effects with their FFmpeg parameters
    EFFECTS = {
        'zoom_in': {
            'name': 'Zoom In',
            'description': 'Yavaşça yakınlaştırma',
            'start_scale': 1.0,
            'end_scale': 1.3
        },
        'zoom_out': {
            'name': 'Zoom Out',
            'description': 'Yavaşça uzaklaştırma',
            'start_scale': 1.3,
            'end_scale': 1.0
        },
        'pan_left': {
            'name': 'Pan Left',
            'description': 'Sola kayma',
            'start_x': 0.1,
            'end_x': -0.1,
            'start_y': 0,
            'end_y': 0
        },
        'pan_right': {
            'name': 'Pan Right',
            'description': 'Sağa kayma',
            'start_x': -0.1,
            'end_x': 0.1,
            'start_y': 0,
            'end_y': 0
        },
        'pan_up': {
            'name': 'Pan Up',
            'description': 'Yukarı kayma',
            'start_x': 0,
            'end_x': 0,
            'start_y': 0.1,
            'end_y': -0.1
        },
        'pan_down': {
            'name': 'Pan Down',
            'description': 'Aşağı kayma',
            'start_x': 0,
            'end_x': 0,
            'start_y': -0.1,
            'end_y': 0.1
        },
        'drift_diagonal': {
            'name': 'Diagonal Drift',
            'description': 'Çapraz kayma + hafif zoom',
            'start_scale': 1.0,
            'end_scale': 1.15,
            'start_x': -0.05,
            'end_x': 0.05,
            'start_y': -0.05,
            'end_y': 0.05
        },
        'cinematic_push': {
            'name': 'Cinematic Push',
            'description': 'Sinematik yaklaşma',
            'start_scale': 1.0,
            'end_scale': 1.25,
            'start_x': 0,
            'end_x': 0,
            'start_y': 0.05,
            'end_y': -0.05
        },
        'slow_reveal': {
            'name': 'Slow Reveal',
            'description': 'Yavaş açılma',
            'start_scale': 1.4,
            'end_scale': 1.0,
            'start_x': 0.1,
            'end_x': 0,
            'start_y': 0,
            'end_y': 0
        },
        'focus_center': {
            'name': 'Focus Center',
            'description': 'Merkeze odaklanma',
            'start_scale': 1.1,
            'end_scale': 1.2,
            'start_x': 0,
            'end_x': 0,
            'start_y': 0,
            'end_y': 0
        }
    }

    # Effect sequences (to avoid repetition)
    SMART_SEQUENCES = [
        ['zoom_in', 'pan_right', 'zoom_out', 'drift_diagonal', 'cinematic_push'],
        ['slow_reveal', 'pan_left', 'zoom_in', 'pan_up', 'focus_center'],
        ['cinematic_push', 'zoom_out', 'pan_right', 'slow_reveal', 'pan_down'],
        ['drift_diagonal', 'zoom_in', 'pan_left', 'cinematic_push', 'zoom_out'],
        ['focus_center', 'pan_down', 'drift_diagonal', 'zoom_in', 'slow_reveal']
    ]

    def __init__(self,
                 output_resolution: Tuple[int, int] = (1920, 1080),
                 fps: int = 30,
                 default_duration: float = 5.0):
        """
        Initialize Advanced Ken Burns

        Args:
            output_resolution: Output video resolution (width, height)
            fps: Frames per second
            default_duration: Default clip duration in seconds
        """
        self.width, self.height = output_resolution
        self.fps = fps
        self.default_duration = default_duration

        # Check FFmpeg availability
        self.ffmpeg_available = self._check_ffmpeg()
        if self.ffmpeg_available:
            logger.info(f"✅ AdvancedKenBurns initialized ({self.width}x{self.height}, {fps}fps)")
        else:
            logger.warning("⚠️ FFmpeg not found! Ken Burns effects will be limited.")

        # Track used effects for smart sequencing
        self._effect_index = 0
        self._current_sequence = random.choice(self.SMART_SEQUENCES)

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        # First try shutil.which
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            self.ffmpeg_path = ffmpeg_path
            return True

        # Try common Windows paths (winget, chocolatey, manual install)
        windows_paths = [
            os.path.expanduser('~\\AppData\\Local\\Microsoft\\WinGet\\Links\\ffmpeg.exe'),
            'C:\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe',
        ]

        for path in windows_paths:
            if os.path.exists(path):
                try:
                    result = subprocess.run(
                        [path, '-version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        self.ffmpeg_path = path
                        logger.info(f"   Found FFmpeg at: {path}")
                        return True
                except Exception:
                    continue

        # Fallback: try 'ffmpeg' directly
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.ffmpeg_path = 'ffmpeg'
                return True
        except Exception:
            pass

        self.ffmpeg_path = None
        return False

    def apply_effect(self,
                     input_path: str,
                     output_path: str,
                     effect: str = 'auto',
                     duration: Optional[float] = None,
                     intensity: float = 1.0,
                     easing: str = 'smooth') -> bool:
        """
        Apply Ken Burns effect to image

        Args:
            input_path: Input image file
            output_path: Output video file
            effect: Effect name or 'auto' for smart selection
            duration: Clip duration in seconds
            intensity: Effect intensity (0.5 to 2.0)
            easing: Easing type ('smooth', 'linear', 'ease_in', 'ease_out')

        Returns:
            True if successful
        """
        if not self.ffmpeg_available:
            logger.error("❌ FFmpeg not available")
            return False

        if not Path(input_path).exists():
            logger.error(f"❌ Input file not found: {input_path}")
            return False

        # Auto-select effect
        if effect == 'auto':
            effect = self._get_next_effect()

        # Get effect parameters
        effect_params = self.EFFECTS.get(effect, self.EFFECTS['zoom_in'])

        # Duration
        clip_duration = duration or self.default_duration

        # Build FFmpeg filter
        filter_complex = self._build_filter(
            effect_params=effect_params,
            duration=clip_duration,
            intensity=intensity,
            easing=easing
        )

        try:
            # Create output directory
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # Build FFmpeg command
            cmd = [
                self.ffmpeg_path, '-y',
                '-loop', '1',
                '-i', input_path,
                '-filter_complex', filter_complex,
                '-t', str(clip_duration),
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-r', str(self.fps),
                output_path
            ]

            logger.info(f"🎬 Applying '{effect}' effect ({clip_duration}s)")

            # Execute
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                file_size = Path(output_path).stat().st_size / (1024 * 1024)
                logger.info(f"✅ Effect applied: {Path(output_path).name} ({file_size:.1f} MB)")
                return True
            else:
                logger.error(f"❌ FFmpeg error: {result.stderr[:200]}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("❌ FFmpeg timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Ken Burns effect failed: {e}")
            return False

    def _build_filter(self,
                      effect_params: Dict,
                      duration: float,
                      intensity: float,
                      easing: str) -> str:
        """Build FFmpeg filter_complex string"""
        total_frames = int(duration * self.fps)

        # Get scale parameters
        start_scale = effect_params.get('start_scale', 1.0)
        end_scale = effect_params.get('end_scale', 1.0)

        # Apply intensity
        scale_diff = (end_scale - start_scale) * intensity
        end_scale = start_scale + scale_diff

        # Get pan parameters
        start_x = effect_params.get('start_x', 0) * intensity
        end_x = effect_params.get('end_x', 0) * intensity
        start_y = effect_params.get('start_y', 0) * intensity
        end_y = effect_params.get('end_y', 0) * intensity

        # Calculate center offsets
        center_x = self.width / 2
        center_y = self.height / 2

        # Build easing expression
        if easing == 'smooth':
            # Smooth ease-in-out using sine
            t_expr = f"(1-cos(PI*n/{total_frames}))/2"
        elif easing == 'ease_in':
            t_expr = f"pow(n/{total_frames},2)"
        elif easing == 'ease_out':
            t_expr = f"1-pow(1-n/{total_frames},2)"
        else:  # linear
            t_expr = f"n/{total_frames}"

        # Calculate dynamic scale and position
        scale_expr = f"({start_scale}+({end_scale}-{start_scale})*{t_expr})"
        x_offset_expr = f"({start_x}+({end_x}-{start_x})*{t_expr})*{self.width}"
        y_offset_expr = f"({start_y}+({end_y}-{start_y})*{t_expr})*{self.height}"

        # Build zoompan filter
        # zoompan=z='1.0+0.3*n/fps':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1
        filter_str = (
            f"scale=8000:-1,"  # Scale up for better quality
            f"zoompan="
            f"z='{scale_expr}':"
            f"x='iw/2-(iw/zoom/2)+{x_offset_expr}':"
            f"y='ih/2-(ih/zoom/2)+{y_offset_expr}':"
            f"d={total_frames}:"
            f"s={self.width}x{self.height}:"
            f"fps={self.fps}"
        )

        return filter_str

    def _get_next_effect(self) -> str:
        """Get next effect from smart sequence"""
        effect = self._current_sequence[self._effect_index % len(self._current_sequence)]
        self._effect_index += 1

        # Switch to new sequence after completing one
        if self._effect_index % len(self._current_sequence) == 0:
            self._current_sequence = random.choice(self.SMART_SEQUENCES)

        return effect

    def process_images(self,
                       image_paths: List[str],
                       output_dir: str,
                       durations: Optional[List[float]] = None,
                       effects: Optional[List[str]] = None) -> List[str]:
        """
        Process multiple images with Ken Burns effects

        Args:
            image_paths: List of input image paths
            output_dir: Output directory for video clips
            durations: List of durations (or None for default)
            effects: List of effects (or None for auto)

        Returns:
            List of output video paths
        """
        output_videos = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Reset effect sequence
        self._effect_index = 0
        self._current_sequence = random.choice(self.SMART_SEQUENCES)

        for i, img_path in enumerate(image_paths):
            # Get duration
            duration = durations[i] if durations and i < len(durations) else self.default_duration

            # Get effect
            effect = effects[i] if effects and i < len(effects) else 'auto'

            # Output path
            video_path = output_path / f"scene_{i+1:03d}.mp4"

            logger.info(f"📽️ Processing image {i+1}/{len(image_paths)}")

            success = self.apply_effect(
                input_path=img_path,
                output_path=str(video_path),
                effect=effect,
                duration=duration
            )

            if success:
                output_videos.append(str(video_path))
            else:
                output_videos.append(None)

        valid_count = len([v for v in output_videos if v])
        logger.info(f"✅ Processed {valid_count}/{len(image_paths)} images")

        return output_videos

    def create_transition(self,
                          clip1_path: str,
                          clip2_path: str,
                          output_path: str,
                          transition_type: str = 'fade',
                          duration: float = 0.5) -> bool:
        """
        Create transition between two video clips

        Args:
            clip1_path: First video clip
            clip2_path: Second video clip
            output_path: Output merged video
            transition_type: 'fade', 'dissolve', 'wipe', 'slide'
            duration: Transition duration

        Returns:
            True if successful
        """
        if not self.ffmpeg_available:
            return False

        try:
            # Get clip durations
            duration1 = self._get_video_duration(clip1_path)
            duration2 = self._get_video_duration(clip2_path)

            if not duration1 or not duration2:
                logger.error("❌ Could not get video durations")
                return False

            # Build transition filter based on type
            if transition_type == 'fade':
                filter_complex = self._build_fade_transition(duration1, duration)
            elif transition_type == 'dissolve':
                filter_complex = self._build_dissolve_transition(duration1, duration)
            elif transition_type == 'slide':
                filter_complex = self._build_slide_transition(duration1, duration)
            else:
                filter_complex = self._build_fade_transition(duration1, duration)

            cmd = [
                self.ffmpeg_path, '-y',
                '-i', clip1_path,
                '-i', clip2_path,
                '-filter_complex', filter_complex,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                logger.info(f"✅ Transition created: {transition_type}")
                return True
            else:
                logger.error(f"❌ Transition failed: {result.stderr[:200]}")
                return False

        except Exception as e:
            logger.error(f"❌ Transition creation failed: {e}")
            return False

    def _build_fade_transition(self, clip1_duration: float, transition_duration: float) -> str:
        """Build fade/crossfade transition filter"""
        offset = clip1_duration - transition_duration
        return (
            f"[0:v]format=pix_fmts=yuva420p,fade=t=out:st={offset}:d={transition_duration}:alpha=1[v0];"
            f"[1:v]format=pix_fmts=yuva420p,fade=t=in:st=0:d={transition_duration}:alpha=1[v1];"
            f"[v0][v1]overlay=format=yuv420[outv]"
        )

    def _build_dissolve_transition(self, clip1_duration: float, transition_duration: float) -> str:
        """Build dissolve transition filter"""
        offset = clip1_duration - transition_duration
        return (
            f"[0:v][1:v]xfade=transition=dissolve:duration={transition_duration}:offset={offset}[outv]"
        )

    def _build_slide_transition(self, clip1_duration: float, transition_duration: float) -> str:
        """Build slide transition filter"""
        offset = clip1_duration - transition_duration
        return (
            f"[0:v][1:v]xfade=transition=slideleft:duration={transition_duration}:offset={offset}[outv]"
        )

    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """Get video duration using FFprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None

    def get_available_effects(self) -> Dict[str, str]:
        """Get list of available effects"""
        return {name: params['description'] for name, params in self.EFFECTS.items()}

    def get_status(self) -> Dict:
        """Get module status"""
        return {
            'ffmpeg_available': self.ffmpeg_available,
            'resolution': f"{self.width}x{self.height}",
            'fps': self.fps,
            'available_effects': len(self.EFFECTS),
            'default_duration': self.default_duration
        }


# Test
if __name__ == "__main__":
    import sys
    from PIL import Image

    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎬 ADVANCED KEN BURNS EFFECT TEST")
    print("="*70)

    ken_burns = AdvancedKenBurns()

    # Show status
    print("\n📊 Module Status:")
    status = ken_burns.get_status()
    print(f"   FFmpeg: {'✅' if status['ffmpeg_available'] else '❌'}")
    print(f"   Resolution: {status['resolution']}")
    print(f"   FPS: {status['fps']}")
    print(f"   Effects: {status['available_effects']}")

    # Show available effects
    print("\n🎭 Available Effects:")
    effects = ken_burns.get_available_effects()
    for name, desc in effects.items():
        print(f"   • {name}: {desc}")

    if not status['ffmpeg_available']:
        print("\n⚠️ FFmpeg not found! Install FFmpeg to use Ken Burns effects.")
        sys.exit(0)

    # Create test image
    print("\n" + "="*70)
    print("TEST 1: Single Image Effect")
    print("="*70)

    test_dir = Path("output/ken_burns_test")
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create a simple test image
    test_image = test_dir / "test_image.jpg"
    if not test_image.exists():
        print("   Creating test image...")
        img = Image.new('RGB', (1920, 1080), color=(30, 60, 90))
        # Add some gradient
        for y in range(1080):
            for x in range(0, 1920, 10):
                r = int(30 + (x / 1920) * 100)
                g = int(60 + (y / 1080) * 80)
                b = int(90 + ((x + y) / 3000) * 100)
                for dx in range(10):
                    if x + dx < 1920:
                        img.putpixel((x + dx, y), (r, g, b))
        img.save(test_image, quality=95)
        print(f"   ✅ Test image created: {test_image}")

    # Apply zoom_in effect
    output_video = test_dir / "test_zoom_in.mp4"
    success = ken_burns.apply_effect(
        input_path=str(test_image),
        output_path=str(output_video),
        effect='zoom_in',
        duration=5.0
    )

    if success:
        print(f"   ✅ Video created: {output_video}")

    # Test multiple effects
    print("\n" + "="*70)
    print("TEST 2: Multiple Effects (Auto Sequence)")
    print("="*70)

    # Create multiple test images
    test_images = []
    for i in range(3):
        img_path = test_dir / f"test_image_{i+1}.jpg"
        if not img_path.exists():
            colors = [(50, 80, 120), (80, 50, 120), (120, 80, 50)]
            img = Image.new('RGB', (1920, 1080), color=colors[i])
            img.save(img_path, quality=95)
        test_images.append(str(img_path))

    output_videos = ken_burns.process_images(
        image_paths=test_images,
        output_dir=str(test_dir / "clips"),
        durations=[4.0, 5.0, 4.0]
    )

    print(f"\n   Created {len([v for v in output_videos if v])} video clips")

    print("\n" + "="*70)
    print("✅ ADVANCED KEN BURNS TEST COMPLETE")
    print("="*70)
    print("\n💡 Features:")
    print("   • 10 different effect types")
    print("   • Smart non-repeating sequences")
    print("   • Smooth easing animations")
    print("   • Transition effects (fade, dissolve, slide)")
    print("   • Batch processing")
    print("\n")
