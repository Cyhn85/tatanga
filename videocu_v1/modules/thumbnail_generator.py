"""
VIDEOCU v1 - Video Thumbnail Generator Module
Automatically creates professional video thumbnails/cover images

Features:
- Extract frame from video
- Add text overlay with title
- Gradient overlay for readability
- Multiple styles (news, entertainment, educational)
- Platform-specific sizes (YouTube, TikTok, Instagram)
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """
    Professional video thumbnail/cover image generator

    Creates eye-catching thumbnails with:
    - Background from video frame or stock image
    - Title text overlay (large, readable)
    - Gradient overlay for text readability
    - Optional logo/watermark
    """

    # Platform-specific sizes
    SIZES = {
        'youtube': (1280, 720),      # 16:9
        'youtube_shorts': (1080, 1920),  # 9:16
        'tiktok': (1080, 1920),      # 9:16
        'instagram_reels': (1080, 1920),  # 9:16
        'instagram_post': (1080, 1080),  # 1:1
        'twitter': (1200, 675),      # 16:9
    }

    # Style presets
    STYLES = {
        'news': {
            'gradient_colors': [(0, 0, 0, 200), (0, 0, 0, 0)],
            'text_color': (255, 255, 255),
            'text_shadow': (0, 0, 0),
            'font_weight': 'bold',
            'text_position': 'bottom'  # bottom, center, top
        },
        'entertainment': {
            'gradient_colors': [(255, 0, 100, 180), (0, 0, 0, 0)],
            'text_color': (255, 255, 255),
            'text_shadow': (255, 0, 100),
            'font_weight': 'bold',
            'text_position': 'center'
        },
        'educational': {
            'gradient_colors': [(0, 50, 100, 200), (0, 0, 0, 0)],
            'text_color': (255, 255, 255),
            'text_shadow': (0, 50, 100),
            'font_weight': 'bold',
            'text_position': 'bottom'
        },
        'minimal': {
            'gradient_colors': [(0, 0, 0, 150), (0, 0, 0, 0)],
            'text_color': (255, 255, 255),
            'text_shadow': (0, 0, 0),
            'font_weight': 'normal',
            'text_position': 'bottom'
        }
    }

    def __init__(self, ffmpeg_path: str = None):
        """
        Initialize ThumbnailGenerator

        Args:
            ffmpeg_path: Path to FFmpeg executable (auto-detected if None)
        """
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        self.fonts_dir = Path(__file__).parent.parent / 'assets' / 'fonts'

        if self.ffmpeg_path:
            logger.info(f"   ThumbnailGenerator initialized (FFmpeg: {self.ffmpeg_path})")
        else:
            logger.warning("   ThumbnailGenerator: FFmpeg not found, video frame extraction limited")

    def _find_ffmpeg(self) -> Optional[str]:
        """Find FFmpeg executable"""
        import shutil

        # Try shutil.which first
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            return ffmpeg

        # Windows common paths
        windows_paths = [
            os.path.expanduser('~\\AppData\\Local\\Microsoft\\WinGet\\Links\\ffmpeg.exe'),
            'C:\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
        ]

        for path in windows_paths:
            if os.path.exists(path):
                return path

        return None

    def generate_thumbnail(
        self,
        title: str,
        output_path: str,
        video_path: str = None,
        background_image: str = None,
        style: str = 'news',
        platform: str = 'youtube',
        frame_time_percent: float = 0.3,
        logo_path: str = None,
        subtitle: str = None
    ) -> bool:
        """
        Generate a professional thumbnail

        Args:
            title: Main title text for thumbnail
            output_path: Where to save the thumbnail
            video_path: Extract background from this video
            background_image: Use this image as background (alternative to video)
            style: Style preset (news, entertainment, educational, minimal)
            platform: Target platform for sizing
            frame_time_percent: Where to extract frame from video (0.0-1.0)
            logo_path: Optional logo to add
            subtitle: Optional subtitle text

        Returns:
            True if successful
        """
        try:
            logger.info(f"   Generating thumbnail: {title[:50]}...")

            # Get target size
            size = self.SIZES.get(platform, self.SIZES['youtube'])
            style_config = self.STYLES.get(style, self.STYLES['news'])

            # Step 1: Get background image
            if video_path and Path(video_path).exists():
                background = self._extract_video_frame(video_path, frame_time_percent, size)
            elif background_image and Path(background_image).exists():
                background = Image.open(background_image)
                background = self._resize_and_crop(background, size)
            else:
                # Create solid gradient background
                background = self._create_gradient_background(size, style_config)

            # Ensure RGBA mode
            if background.mode != 'RGBA':
                background = background.convert('RGBA')

            # Step 2: Apply gradient overlay
            background = self._apply_gradient_overlay(background, style_config)

            # Step 3: Add title text
            background = self._add_text_overlay(
                image=background,
                title=title,
                subtitle=subtitle,
                style_config=style_config,
                size=size
            )

            # Step 4: Add logo if provided
            if logo_path and Path(logo_path).exists():
                background = self._add_logo(background, logo_path)

            # Step 5: Save
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to RGB for JPEG
            if output_path.suffix.lower() in ['.jpg', '.jpeg']:
                background = background.convert('RGB')

            background.save(str(output_path), quality=95)

            file_size = output_path.stat().st_size / 1024
            logger.info(f"   Thumbnail saved: {output_path.name} ({file_size:.1f} KB)")

            return True

        except Exception as e:
            logger.error(f"   Thumbnail generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _extract_video_frame(self, video_path: str, time_percent: float, target_size: Tuple[int, int]) -> Image.Image:
        """Extract a frame from video at specified time percentage"""
        try:
            if not self.ffmpeg_path:
                raise Exception("FFmpeg not available")

            # Get video duration
            duration = self._get_video_duration(video_path)
            target_time = duration * time_percent

            # Create temp output path
            temp_frame = Path(video_path).parent / 'temp_thumbnail_frame.jpg'

            # Extract frame with FFmpeg
            cmd = [
                self.ffmpeg_path, '-y',
                '-ss', str(target_time),
                '-i', video_path,
                '-vframes', '1',
                '-q:v', '2',
                str(temp_frame)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and temp_frame.exists():
                frame = Image.open(str(temp_frame))
                frame = self._resize_and_crop(frame, target_size)

                # Clean up
                temp_frame.unlink()
                return frame
            else:
                raise Exception(f"FFmpeg frame extraction failed: {result.stderr[:200]}")

        except Exception as e:
            logger.warning(f"   Frame extraction failed: {e}, using gradient background")
            return self._create_gradient_background(target_size, self.STYLES['news'])

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds"""
        try:
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe') if self.ffmpeg_path else 'ffprobe'
            cmd = [
                ffprobe_path, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except:
            pass
        return 30.0  # Default fallback

    def _resize_and_crop(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """Resize and crop image to target size (center crop)"""
        target_w, target_h = target_size
        target_ratio = target_w / target_h

        img_w, img_h = image.size
        img_ratio = img_w / img_h

        if img_ratio > target_ratio:
            # Image is wider, crop sides
            new_w = int(img_h * target_ratio)
            left = (img_w - new_w) // 2
            image = image.crop((left, 0, left + new_w, img_h))
        else:
            # Image is taller, crop top/bottom
            new_h = int(img_w / target_ratio)
            top = (img_h - new_h) // 2
            image = image.crop((0, top, img_w, top + new_h))

        return image.resize(target_size, Image.Resampling.LANCZOS)

    def _create_gradient_background(self, size: Tuple[int, int], style_config: dict) -> Image.Image:
        """Create a gradient background"""
        width, height = size
        image = Image.new('RGBA', size, (30, 30, 50, 255))

        # Create vertical gradient
        draw = ImageDraw.Draw(image)
        for y in range(height):
            r = int(30 + (60 * y / height))
            g = int(30 + (40 * y / height))
            b = int(50 + (80 * y / height))
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        return image

    def _apply_gradient_overlay(self, image: Image.Image, style_config: dict) -> Image.Image:
        """Apply gradient overlay for text readability"""
        width, height = image.size

        # Create gradient overlay
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        gradient_colors = style_config.get('gradient_colors', [(0, 0, 0, 200), (0, 0, 0, 0)])
        text_position = style_config.get('text_position', 'bottom')

        # Apply gradient based on text position
        if text_position == 'bottom':
            # Gradient from bottom
            for y in range(height // 2, height):
                progress = (y - height // 2) / (height // 2)
                alpha = int(gradient_colors[0][3] * progress)
                draw.line([(0, y), (width, y)], fill=(gradient_colors[0][0], gradient_colors[0][1], gradient_colors[0][2], alpha))
        elif text_position == 'top':
            # Gradient from top
            for y in range(height // 2):
                progress = 1 - (y / (height // 2))
                alpha = int(gradient_colors[0][3] * progress)
                draw.line([(0, y), (width, y)], fill=(gradient_colors[0][0], gradient_colors[0][1], gradient_colors[0][2], alpha))
        else:  # center
            # Gradient from both
            for y in range(height):
                if y < height // 4 or y > height * 3 // 4:
                    alpha = int(gradient_colors[0][3] * 0.5)
                else:
                    alpha = int(gradient_colors[0][3] * 0.7)
                draw.line([(0, y), (width, y)], fill=(gradient_colors[0][0], gradient_colors[0][1], gradient_colors[0][2], alpha))

        return Image.alpha_composite(image, overlay)

    def _add_text_overlay(
        self,
        image: Image.Image,
        title: str,
        subtitle: str,
        style_config: dict,
        size: Tuple[int, int]
    ) -> Image.Image:
        """Add title and optional subtitle text"""
        draw = ImageDraw.Draw(image)
        width, height = size

        text_color = style_config.get('text_color', (255, 255, 255))
        shadow_color = style_config.get('text_shadow', (0, 0, 0))
        text_position = style_config.get('text_position', 'bottom')

        # Calculate font size based on image width
        title_font_size = int(width / 15)  # Roughly 85px for 1280 width
        subtitle_font_size = int(width / 25)

        # Try to load custom font, fallback to default
        try:
            # Try system fonts
            font_paths = [
                'C:\\Windows\\Fonts\\arialbd.ttf',
                'C:\\Windows\\Fonts\\arial.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                '/System/Library/Fonts/Helvetica.ttc',
            ]

            title_font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    title_font = ImageFont.truetype(font_path, title_font_size)
                    subtitle_font = ImageFont.truetype(font_path, subtitle_font_size)
                    break

            if not title_font:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        # Wrap title text
        max_chars = int(width / (title_font_size * 0.6))
        wrapped_title = textwrap.fill(title, width=max_chars)
        title_lines = wrapped_title.split('\n')[:3]  # Max 3 lines
        wrapped_title = '\n'.join(title_lines)

        # Calculate text position
        title_bbox = draw.textbbox((0, 0), wrapped_title, font=title_font)
        title_height = title_bbox[3] - title_bbox[1]

        padding = int(width * 0.05)

        if text_position == 'bottom':
            text_y = height - title_height - padding * 2
        elif text_position == 'top':
            text_y = padding
        else:  # center
            text_y = (height - title_height) // 2

        text_x = padding

        # Draw shadow
        shadow_offset = 3
        draw.text((text_x + shadow_offset, text_y + shadow_offset), wrapped_title, font=title_font, fill=shadow_color)

        # Draw title
        draw.text((text_x, text_y), wrapped_title, font=title_font, fill=text_color)

        # Draw subtitle if provided
        if subtitle:
            subtitle_y = text_y + title_height + int(padding * 0.5)
            draw.text((text_x + shadow_offset, subtitle_y + shadow_offset), subtitle, font=subtitle_font, fill=shadow_color)
            draw.text((text_x, subtitle_y), subtitle, font=subtitle_font, fill=text_color)

        return image

    def _add_logo(self, image: Image.Image, logo_path: str) -> Image.Image:
        """Add logo to corner of image"""
        try:
            logo = Image.open(logo_path)

            # Resize logo to ~10% of image width
            logo_width = int(image.width * 0.1)
            logo_ratio = logo.height / logo.width
            logo_height = int(logo_width * logo_ratio)
            logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

            # Position in top-right corner
            padding = int(image.width * 0.02)
            position = (image.width - logo_width - padding, padding)

            # Handle transparency
            if logo.mode == 'RGBA':
                image.paste(logo, position, logo)
            else:
                image.paste(logo, position)

            return image
        except Exception as e:
            logger.warning(f"   Logo addition failed: {e}")
            return image

    def generate_for_platforms(
        self,
        title: str,
        output_dir: str,
        video_path: str = None,
        background_image: str = None,
        style: str = 'news',
        platforms: list = None
    ) -> dict:
        """
        Generate thumbnails for multiple platforms

        Args:
            title: Main title
            output_dir: Output directory
            video_path: Source video
            background_image: Background image
            style: Style preset
            platforms: List of platforms (default: ['youtube', 'tiktok'])

        Returns:
            Dict of {platform: output_path}
        """
        if platforms is None:
            platforms = ['youtube', 'tiktok']

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        for platform in platforms:
            output_path = output_dir / f'thumbnail_{platform}.jpg'
            success = self.generate_thumbnail(
                title=title,
                output_path=str(output_path),
                video_path=video_path,
                background_image=background_image,
                style=style,
                platform=platform
            )
            if success:
                results[platform] = str(output_path)

        return results


# Test
if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*60)
    print("THUMBNAIL GENERATOR TEST")
    print("="*60)

    generator = ThumbnailGenerator()

    # Test with title only (no video)
    test_title = "Kalte Supermond 2025: Warum der letzte Vollmond des Jahres auch am hochsten steht"

    output_dir = Path(__file__).parent.parent / 'output' / 'test_thumbnails'
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate for multiple platforms
    results = generator.generate_for_platforms(
        title=test_title,
        output_dir=str(output_dir),
        style='news',
        platforms=['youtube', 'tiktok']
    )

    print(f"\nGenerated thumbnails:")
    for platform, path in results.items():
        print(f"   {platform}: {path}")

    print("\n" + "="*60)
    print("THUMBNAIL GENERATOR TEST COMPLETE")
    print("="*60)
