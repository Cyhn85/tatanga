"""
VIDEOCU v1 - Image Generator Module (Multi-Provider with 4-Layer Fallback)
Priority: Pexels → Unsplash → Pollinations.ai → Placeholder
"""

import requests
import logging
from typing import Optional, List, Dict
from pathlib import Path
import urllib.parse
import time
from PIL import Image
import io
import os

logger = logging.getLogger(__name__)


class ImageGenerator:
    """
    Multi-Provider Image Generator with 4-Layer Fallback
    Priority: 1. Pexels (HD stock) → 2. Unsplash (HD stock) → 3. Pollinations.ai (AI) → 4. Placeholder
    """

    # Pollinations.ai endpoints (FREE - No API key needed!)
    POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"

    # Image settings
    DEFAULT_WIDTH = 1920
    DEFAULT_HEIGHT = 1080
    DEFAULT_SEED = -1  # Random
    DEFAULT_MODEL = "flux"  # flux, turbo, or flux-realism

    def __init__(self,
                 pexels_api_key: Optional[str] = None,
                 unsplash_api_key: Optional[str] = None):
        """
        Initialize multi-provider image generator with 4-layer fallback

        Args:
            pexels_api_key: Pexels API key (optional, from .env)
            unsplash_api_key: Unsplash API key (optional, from .env)
        """
        self.pexels_api_key = pexels_api_key or os.getenv('PEXELS_API_KEY', '')
        self.unsplash_api_key = unsplash_api_key or os.getenv('UNSPLASH_API_KEY', '')

        # Initialize Pexels provider
        self.pexels_provider = None
        if self.pexels_api_key:
            try:
                from .pexels_provider import PexelsProvider
                self.pexels_provider = PexelsProvider(api_key=self.pexels_api_key)
                logger.info("✅ Pexels provider enabled")
            except Exception as e:
                logger.warning(f"⚠️ Pexels provider init failed: {e}")

        # Initialize Unsplash provider
        self.unsplash_provider = None
        if self.unsplash_api_key:
            try:
                from .unsplash_provider import UnsplashProvider
                self.unsplash_provider = UnsplashProvider(api_key=self.unsplash_api_key)
                logger.info("✅ Unsplash provider enabled")
            except Exception as e:
                logger.warning(f"⚠️ Unsplash provider init failed: {e}")

        # Log active providers
        active_providers = []
        if self.pexels_provider and self.pexels_provider.enabled:
            active_providers.append("Pexels")
        if self.unsplash_provider and self.unsplash_provider.enabled:
            active_providers.append("Unsplash")
        active_providers.append("Pollinations.ai")
        active_providers.append("Placeholder")

        logger.info(f"✅ Image Generator initialized: {' → '.join(active_providers)}")

    def generate_image(self,
                      prompt: str,
                      output_path: str,
                      width: int = DEFAULT_WIDTH,
                      height: int = DEFAULT_HEIGHT,
                      model: str = DEFAULT_MODEL,
                      seed: int = DEFAULT_SEED,
                      enhance: bool = True,
                      use_stock: bool = True) -> bool:
        """
        Generate or fetch image with 4-layer fallback
        Pexels → Unsplash → Pollinations.ai → Placeholder

        Args:
            prompt: Image description (English)
            output_path: Output file path
            width: Width (default: 1920)
            height: Height (default: 1080)
            model: AI model (flux, turbo, flux-realism)
            seed: Random seed (-1 for random)
            enhance: Prompt enhancement
            use_stock: Try stock photos first (Pexels + Unsplash)

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"🎨 Generating/fetching image: '{prompt[:50]}...'")

        # LAYER 1: Try Pexels stock photos first (HD, 200 req/hr)
        if use_stock and self.pexels_provider and self.pexels_provider.enabled:
            logger.info("   📸 Layer 1: Trying Pexels stock photos...")

            success = self.pexels_provider.get_photo_for_scene(
                scene_description=prompt,
                output_path=output_path,
                max_retries=2
            )

            if success:
                logger.info("   ✅ Image from Pexels (HD stock)")
                return True
            else:
                logger.info("   ⚠️ Pexels failed, trying Unsplash...")

        # LAYER 2: Try Unsplash stock photos (HD, 50 req/hr)
        if use_stock and self.unsplash_provider and self.unsplash_provider.enabled:
            logger.info("   📷 Layer 2: Trying Unsplash stock photos...")

            success = self.unsplash_provider.get_photo_for_scene(
                scene_description=prompt,
                output_path=output_path,
                max_retries=2
            )

            if success:
                logger.info("   ✅ Image from Unsplash (HD stock)")
                return True
            else:
                logger.info("   ⚠️ Unsplash failed, trying AI generation...")

        # LAYER 3: Fallback to Pollinations.ai (AI generation, slower)
        logger.info("   🤖 Layer 3: Using Pollinations.ai (AI generation)...")
        return self._generate_with_pollinations(
            prompt=prompt,
            output_path=output_path,
            width=width,
            height=height,
            model=model,
            seed=seed,
            enhance=enhance
        )

    def _generate_with_pollinations(self,
                                   prompt: str,
                                   output_path: str,
                                   width: int,
                                   height: int,
                                   model: str,
                                   seed: int,
                                   enhance: bool) -> bool:
        """Generate image with Pollinations.ai"""
        try:
            # URL encode prompt
            encoded_prompt = urllib.parse.quote(prompt)

            # Build URL with parameters
            url = f"{self.POLLINATIONS_BASE_URL}/{encoded_prompt}"
            params = {
                "width": width,
                "height": height,
                "model": model,
                "nologo": "true",  # Remove watermark
                "enhance": "true" if enhance else "false"
            }

            if seed >= 0:
                params["seed"] = seed

            # Request image
            response = requests.get(url, params=params, timeout=60)

            if response.status_code == 200:
                # Save image
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, 'wb') as f:
                    f.write(response.content)

                file_size = output_file.stat().st_size / 1024  # KB
                logger.info(f"   ✅ AI image generated: {output_file} ({file_size:.1f} KB)")
                return True

            else:
                logger.error(f"   ❌ Pollinations.ai failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"   ❌ Pollinations.ai error: {e}")
            return False

    def generate_images_batch(self,
                             prompts: List[str],
                             output_dir: str,
                             width: int = DEFAULT_WIDTH,
                             height: int = DEFAULT_HEIGHT,
                             model: str = DEFAULT_MODEL,
                             use_stock: bool = True) -> List[str]:
        """
        Generate/fetch multiple images

        Args:
            prompts: List of image descriptions
            output_dir: Output directory
            width: Width
            height: Height
            model: AI model
            use_stock: Try stock photos first

        Returns:
            List of generated file paths
        """
        output_files = []
        total = len(prompts)

        logger.info(f"🎨 Generating {total} images (Pexels + Pollinations)...")

        for i, prompt in enumerate(prompts, 1):
            output_path = f"{output_dir}/scene_{i:03d}.jpg"

            logger.info(f"  [{i}/{total}] '{prompt[:40]}...'")

            success = self.generate_image(
                prompt=prompt,
                output_path=output_path,
                width=width,
                height=height,
                model=model,
                use_stock=use_stock
            )

            if success:
                output_files.append(output_path)
            else:
                logger.warning(f"  ⚠️ Failed to generate image {i}")
                # Create placeholder
                self._create_placeholder(output_path, width, height)
                output_files.append(output_path)

            # Rate limiting - be nice to APIs
            time.sleep(1)

        logger.info(f"✅ Generated/fetched {len(output_files)}/{total} images")
        return output_files

    def generate_from_scenes(self,
                            scenes: List[Dict],
                            output_dir: str,
                            width: int = DEFAULT_WIDTH,
                            height: int = DEFAULT_HEIGHT,
                            use_stock: bool = True) -> List[str]:
        """
        Generate images from video scenes list

        Args:
            scenes: Scene dictionary list (with 'image_prompt' field)
            output_dir: Output directory
            width: Width
            height: Height
            use_stock: Try stock photos first

        Returns:
            List of generated file paths
        """
        prompts = []

        for scene in scenes:
            # Get image prompt from scene
            image_prompt = scene.get('image_prompt', '')
            if not image_prompt:
                # Fallback to visual description
                image_prompt = scene.get('visual', 'abstract background')

            # Enhance prompt for better results
            enhanced_prompt = self._enhance_prompt(image_prompt)
            prompts.append(enhanced_prompt)

        return self.generate_images_batch(
            prompts=prompts,
            output_dir=output_dir,
            width=width,
            height=height,
            use_stock=use_stock
        )

    def _enhance_prompt(self, prompt: str) -> str:
        """
        Optimize prompt for better image quality

        Args:
            prompt: Original prompt

        Returns:
            Enhanced prompt
        """
        # Add quality enhancers
        enhancements = [
            "high quality",
            "detailed",
            "professional",
            "cinematic lighting",
            "8k resolution"
        ]

        # Check if already has quality keywords
        prompt_lower = prompt.lower()
        has_quality = any(word in prompt_lower for word in ['quality', 'detailed', 'professional', '8k', '4k'])

        if not has_quality:
            enhanced = f"{prompt}, {', '.join(enhancements)}"
        else:
            enhanced = prompt

        return enhanced

    def create_thumbnail(self,
                        prompt: str,
                        output_path: str,
                        style: str = "clickbait") -> bool:
        """
        Create YouTube thumbnail

        Args:
            prompt: Thumbnail description
            output_path: Output file path
            style: Thumbnail style (clickbait, professional, minimal)

        Returns:
            True if successful
        """
        # Thumbnail-specific enhancements
        style_prompts = {
            "clickbait": "bold text overlay, vibrant colors, high contrast, eye-catching, youtube thumbnail style",
            "professional": "clean design, corporate look, modern typography, professional youtube thumbnail",
            "minimal": "minimalist design, simple composition, clean typography, elegant"
        }

        enhanced_prompt = f"{prompt}, {style_prompts.get(style, '')}, 16:9 aspect ratio, youtube thumbnail"

        # Thumbnails: prefer AI generation for text overlay
        return self.generate_image(
            prompt=enhanced_prompt,
            output_path=output_path,
            width=1920,
            height=1080,
            model="flux",  # Use flux for best quality
            use_stock=False  # Don't use stock photos for thumbnails
        )

    def _create_placeholder(self, output_path: str, width: int, height: int) -> bool:
        """
        Create placeholder image when generation fails

        Args:
            output_path: Output file path
            width: Width
            height: Height

        Returns:
            True if successful
        """
        try:
            # Create solid color placeholder
            placeholder = Image.new('RGB', (width, height), color=(30, 30, 40))

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            placeholder.save(output_file, quality=95)

            logger.info(f"   📦 Placeholder created: {output_path}")
            return True

        except Exception as e:
            logger.error(f"   ❌ Placeholder creation failed: {e}")
            return False

    def resize_image(self,
                    input_path: str,
                    output_path: str,
                    width: int,
                    height: int) -> bool:
        """
        Resize image

        Args:
            input_path: Source file
            output_path: Target file
            width: New width
            height: New height

        Returns:
            True if successful
        """
        try:
            img = Image.open(input_path)
            resized = img.resize((width, height), Image.Resampling.LANCZOS)

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            resized.save(output_file, quality=95)

            logger.info(f"✅ Image resized: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Image resize failed: {e}")
            return False

    def get_image_info(self, image_path: str) -> Optional[Dict]:
        """
        Get image metadata

        Args:
            image_path: Image file path

        Returns:
            Image metadata dict
        """
        try:
            img = Image.open(image_path)

            return {
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'mode': img.mode,
                'size_kb': Path(image_path).stat().st_size / 1024
            }

        except Exception as e:
            logger.error(f"❌ Could not read image info: {e}")
            return None

    def get_provider_status(self) -> Dict:
        """Get provider availability status"""
        status = {
            'pollinations': {
                'enabled': True,
                'cost': 'FREE',
                'type': 'AI generation'
            }
        }

        if self.pexels_provider:
            pexels_status = self.pexels_provider.get_status()
            status['pexels'] = {
                'enabled': pexels_status['enabled'],
                'cost': 'FREE (200 req/hour)',
                'type': 'Stock photos',
                'rate_limit': pexels_status.get('rate_limit', 'N/A')
            }
        else:
            status['pexels'] = {
                'enabled': False,
                'cost': 'FREE',
                'type': 'Stock photos',
                'note': 'API key not configured'
            }

        return status


# Test
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    # Load .env
    load_dotenv()

    # Set UTF-8 encoding
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎨 MULTI-PROVIDER IMAGE GENERATOR TEST")
    print("="*70)

    generator = ImageGenerator()

    # Show provider status
    print("\n📊 Provider Status:")
    status = generator.get_provider_status()
    for provider, info in status.items():
        enabled = "✅" if info['enabled'] else "❌"
        print(f"   {enabled} {provider}: {info['type']} ({info['cost']})")

    # Test 1: Generate with Pexels fallback
    print("\n" + "="*70)
    print("TEST 1: Image with Pexels Fallback")
    print("="*70)

    success = generator.generate_image(
        prompt="modern artificial intelligence technology, futuristic computer chips",
        output_path="output/test_pexels_image.jpg",
        width=1920,
        height=1080,
        use_stock=True
    )

    if success:
        print("   ✅ Image generated/fetched successfully!")
        info = generator.get_image_info("output/test_pexels_image.jpg")
        if info:
            print(f"   📊 Size: {info['width']}x{info['height']} ({info['size_kb']:.1f} KB)")

    # Test 2: Generate thumbnail (AI only)
    print("\n" + "="*70)
    print("TEST 2: YouTube Thumbnail (AI Generation)")
    print("="*70)

    success = generator.create_thumbnail(
        prompt="AI Technology 2025, modern design, bold text",
        output_path="output/test_thumbnail.jpg",
        style="clickbait"
    )

    if success:
        print("   ✅ Thumbnail generated!")

    # Test 3: Batch generation
    print("\n" + "="*70)
    print("TEST 3: Batch Generation (Mix of Pexels + AI)")
    print("="*70)

    prompts = [
        "office workspace with computers",
        "robotic assistant in modern lab",
        "data visualization holographic display"
    ]

    files = generator.generate_images_batch(
        prompts=prompts,
        output_dir="output/batch",
        width=1920,
        height=1080,
        use_stock=True
    )

    print(f"\n   ✅ Generated {len(files)} images:")
    for file in files:
        print(f"      - {Path(file).name}")

    print("\n" + "="*70)
    print("✅ MULTI-PROVIDER IMAGE GENERATOR TEST COMPLETE")
    print("="*70)
    print("\n💡 Benefits:")
    print("   • Pexels: HD stock photos (fastest, best quality)")
    print("   • Pollinations.ai: AI generation (creative, custom)")
    print("   • Both are FREE!")
    print("\n")
