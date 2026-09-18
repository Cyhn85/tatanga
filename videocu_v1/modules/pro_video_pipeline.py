"""
VIDEOCU v1 - Professional Video Pipeline
Tüm yeni modülleri birleştiren üst düzey video üretim sistemi

Features:
- Smart Content Analysis (Gemini)
- Stock Video Integration (Pixabay + Pexels)
- Advanced Ken Burns Effects
- Professional Transitions
- Edge-TTS Voice Generation
- Article Image Integration
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)


class ProVideoPipeline:
    """
    Professional Video Production Pipeline

    Akış:
    1. İçerik Analizi (SmartContentAnalyzer)
       - Tema çıkarma
       - Duygu analizi
       - Video keywords üretimi

    2. Görsel Kaynaklar (Hybrid)
       - Makale görselleri (öncelik)
       - Stock video clips (Pixabay/Pexels)
       - Stock photos + Ken Burns
       - AI generated (fallback)

    3. Ses Üretimi (Edge-TTS)
       - Düzeltilmiş async işlem
       - Almanca/İngilizce/Türkçe

    4. Video Montaj
       - Advanced Ken Burns
       - Professional transitions
       - Ses senkronizasyonu
    """

    def __init__(self,
                 gemini_api_key: Optional[str] = None,
                 pixabay_api_key: Optional[str] = None,
                 pexels_api_key: Optional[str] = None,
                 output_resolution: tuple = (1920, 1080),
                 fps: int = 30):
        """
        Initialize Pro Video Pipeline

        Args:
            gemini_api_key: For SmartContentAnalyzer
            pixabay_api_key: For stock videos
            pexels_api_key: For stock videos/photos
            output_resolution: Video resolution
            fps: Frames per second
        """
        self.gemini_key = gemini_api_key or os.getenv('GEMINI_API_KEY', '')
        self.pixabay_key = pixabay_api_key or os.getenv('PIXABAY_API_KEY', '')
        self.pexels_key = pexels_api_key or os.getenv('PEXELS_API_KEY', '')

        self.resolution = output_resolution
        self.fps = fps

        # Initialize modules
        self._init_modules()

        logger.info("✅ ProVideoPipeline initialized")
        logger.info(f"   Resolution: {output_resolution[0]}x{output_resolution[1]}")
        logger.info(f"   Modules: {self._get_active_modules()}")

    def _init_modules(self):
        """Initialize all sub-modules"""
        # Smart Content Analyzer
        self.content_analyzer = None
        try:
            from .smart_content_analyzer import SmartContentAnalyzer
            self.content_analyzer = SmartContentAnalyzer(api_key=self.gemini_key)
            if self.content_analyzer.enabled:
                logger.info("   ✅ SmartContentAnalyzer ready")
        except Exception as e:
            logger.warning(f"   ⚠️ SmartContentAnalyzer not available: {e}")

        # Video Provider (Stock Videos)
        self.video_provider = None
        try:
            from .video_provider import VideoProvider
            self.video_provider = VideoProvider(
                pixabay_api_key=self.pixabay_key,
                pexels_api_key=self.pexels_key
            )
            logger.info("   ✅ VideoProvider ready")
        except Exception as e:
            logger.warning(f"   ⚠️ VideoProvider not available: {e}")

        # Image Generator (Stock Photos + AI)
        self.image_generator = None
        try:
            from .image_generator import ImageGenerator
            self.image_generator = ImageGenerator(
                pexels_api_key=self.pexels_key
            )
            logger.info("   ✅ ImageGenerator ready")
        except Exception as e:
            logger.warning(f"   ⚠️ ImageGenerator not available: {e}")

        # Advanced Ken Burns
        self.ken_burns = None
        try:
            from .advanced_ken_burns import AdvancedKenBurns
            self.ken_burns = AdvancedKenBurns(
                output_resolution=self.resolution,
                fps=self.fps
            )
            if self.ken_burns.ffmpeg_available:
                logger.info("   ✅ AdvancedKenBurns ready")
            else:
                logger.warning("   ⚠️ AdvancedKenBurns limited (no FFmpeg)")
        except Exception as e:
            logger.warning(f"   ⚠️ AdvancedKenBurns not available: {e}")

        # Edge TTS
        self.tts = None
        try:
            from .edge_tts_generator import EdgeTTSGenerator
            self.tts = EdgeTTSGenerator(default_voice='conrad')
            logger.info("   ✅ EdgeTTS ready")
        except Exception as e:
            logger.warning(f"   ⚠️ EdgeTTS not available: {e}")

        # Video Editor (for final assembly)
        self.video_editor = None
        try:
            from .video_editor import VideoEditor
            self.video_editor = VideoEditor(
                resolution=self.resolution,
                fps=self.fps
            )
            logger.info("   ✅ VideoEditor ready")
        except Exception as e:
            logger.warning(f"   ⚠️ VideoEditor not available: {e}")

        # Thumbnail Generator
        self.thumbnail_generator = None
        try:
            from .thumbnail_generator import ThumbnailGenerator
            self.thumbnail_generator = ThumbnailGenerator()
            logger.info("   ✅ ThumbnailGenerator ready")
        except Exception as e:
            logger.warning(f"   ⚠️ ThumbnailGenerator not available: {e}")

    def _get_active_modules(self) -> str:
        """Get list of active modules"""
        modules = []
        if self.content_analyzer and self.content_analyzer.enabled:
            modules.append("Analyzer")
        if self.video_provider:
            modules.append("StockVideo")
        if self.image_generator:
            modules.append("Images")
        if self.ken_burns and self.ken_burns.ffmpeg_available:
            modules.append("KenBurns")
        if self.tts:
            modules.append("TTS")
        if self.video_editor:
            modules.append("Editor")
        if self.thumbnail_generator:
            modules.append("Thumbnail")
        return ', '.join(modules) if modules else "None"

    def produce_video_from_article(self,
                                    article_data: Dict,
                                    output_dir: str,
                                    language: str = 'de',
                                    duration: int = 60,
                                    use_article_images: bool = True,
                                    use_stock_videos: bool = True,
                                    voice_style: str = 'professional',
                                    add_subtitles: bool = False,
                                    voice_provider: str = 'edge-tts',
                                    category: str = 'auto') -> Dict:
        """
        Produce professional video from article data

        Args:
            article_data: {
                'title': str,
                'text': str,
                'images': List[str],  # URLs or paths
                'video_script': {
                    'intro': str,
                    'main_points': List[str],
                    'outro': str
                }
            }
            output_dir: Output directory
            language: Output language (de, en, tr)
            duration: Target duration in seconds
            use_article_images: Use images from the article
            use_stock_videos: Try to find stock videos
            voice_style: TTS voice style
            add_subtitles: Generate SRT subtitles from voiceover
            voice_provider: TTS provider (edge-tts, openai, elevenlabs)
            category: Content category for better video search

        Returns:
            Production result dictionary
        """
        production_start = datetime.now()
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        result = {
            'success': False,
            'production_id': production_start.strftime("%Y%m%d_%H%M%S"),
            'output_dir': str(output_path),
            'phases': {},
            'files': {}
        }

        try:
            # ================================================================
            # PHASE 1: CONTENT ANALYSIS
            # ================================================================
            logger.info("📊 PHASE 1: Content Analysis")
            result['phases']['analysis'] = {'status': 'in_progress'}

            analysis = self._analyze_content(article_data)
            result['phases']['analysis'] = {
                'status': 'completed',
                'theme': analysis.get('main_theme', 'unknown'),
                'emotion': analysis.get('emotion', 'neutral'),
                'keywords': analysis.get('video_keywords', [])
            }

            # ================================================================
            # PHASE 2: SCENE PLANNING
            # ================================================================
            logger.info("📋 PHASE 2: Scene Planning")
            result['phases']['planning'] = {'status': 'in_progress'}

            scenes = self._plan_scenes(article_data, analysis, duration)
            result['phases']['planning'] = {
                'status': 'completed',
                'scene_count': len(scenes)
            }

            # ================================================================
            # PHASE 3: VISUAL ASSETS
            # ================================================================
            logger.info("🎨 PHASE 3: Visual Assets")
            result['phases']['visuals'] = {'status': 'in_progress'}

            visual_assets = self._gather_visuals(
                scenes=scenes,
                article_images=article_data.get('images', []) if use_article_images else [],
                analysis=analysis,
                output_dir=output_path / 'visuals',
                use_stock_videos=use_stock_videos,
                target_duration=float(duration)  # Pass target duration for content sufficiency check
            )
            result['phases']['visuals'] = {
                'status': 'completed',
                'asset_count': len(visual_assets),
                'types': self._count_asset_types(visual_assets)
            }

            # ================================================================
            # PHASE 4: VOICE GENERATION
            # ================================================================
            logger.info("🎤 PHASE 4: Voice Generation")
            result['phases']['voice'] = {'status': 'in_progress'}

            voiceover_path = self._generate_voiceover(
                scenes=scenes,
                output_dir=output_path / 'audio',
                language=language,
                style=voice_style
            )

            if voiceover_path:
                result['phases']['voice'] = {
                    'status': 'completed',
                    'file': str(voiceover_path)
                }
                result['files']['voiceover'] = str(voiceover_path)
            else:
                result['phases']['voice'] = {
                    'status': 'failed',
                    'error': 'Voice generation failed'
                }

            # ================================================================
            # PHASE 5: VIDEO ASSEMBLY
            # ================================================================
            logger.info("🎬 PHASE 5: Video Assembly")
            result['phases']['assembly'] = {'status': 'in_progress'}

            final_video = self._assemble_video(
                visual_assets=visual_assets,
                scenes=scenes,
                voiceover_path=voiceover_path,
                output_path=output_path / 'final_video.mp4',
                analysis=analysis,
                target_duration=float(duration)  # Pass target duration for fallback
            )

            if final_video:
                result['phases']['assembly'] = {
                    'status': 'completed',
                    'file': str(final_video)
                }
                result['files']['video'] = str(final_video)
                result['success'] = True
            else:
                result['phases']['assembly'] = {
                    'status': 'failed',
                    'error': 'Video assembly failed'
                }

            # ================================================================
            # PHASE 6: THUMBNAIL GENERATION
            # ================================================================
            logger.info("🖼️ PHASE 6: Thumbnail Generation")
            result['phases']['thumbnail'] = {'status': 'in_progress'}

            thumbnail_path = self._generate_thumbnail(
                video_path=final_video,
                title=article_data.get('title', 'Video'),
                output_dir=output_path,
                analysis=analysis
            )

            if thumbnail_path:
                result['phases']['thumbnail'] = {
                    'status': 'completed',
                    'file': str(thumbnail_path)
                }
                result['files']['thumbnail'] = str(thumbnail_path)
            else:
                result['phases']['thumbnail'] = {
                    'status': 'failed',
                    'error': 'Thumbnail generation failed'
                }

            # ================================================================
            # PHASE 7: SUBTITLE GENERATION (if requested)
            # ================================================================
            if add_subtitles and voiceover_path:
                logger.info("📝 PHASE 7: Subtitle Generation")
                result['phases']['subtitles'] = {'status': 'in_progress'}

                subtitle_path = self._generate_subtitles(
                    voiceover_path=voiceover_path,
                    output_dir=output_path,
                    language=language
                )

                if subtitle_path:
                    result['phases']['subtitles'] = {
                        'status': 'completed',
                        'file': str(subtitle_path)
                    }
                    result['files']['subtitles'] = str(subtitle_path)
                else:
                    result['phases']['subtitles'] = {
                        'status': 'failed',
                        'error': 'Subtitle generation failed'
                    }

            # ================================================================
            # FINALIZE
            # ================================================================
            production_time = (datetime.now() - production_start).total_seconds()
            result['production_time_seconds'] = production_time
            result['completed_at'] = datetime.now().isoformat()

            # Save metadata
            metadata_file = output_path / 'production_metadata.json'
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ Production completed in {production_time:.1f}s")
            logger.info(f"   Output: {final_video}")

            return result

        except Exception as e:
            logger.error(f"❌ Production failed: {e}")
            result['error'] = str(e)
            return result

    def _analyze_content(self, article_data: Dict) -> Dict:
        """Analyze article content"""
        if self.content_analyzer and self.content_analyzer.enabled:
            # Combine title and text for analysis
            full_text = f"{article_data.get('title', '')}\n\n{article_data.get('text', '')}"
            return self.content_analyzer.analyze_content(full_text)
        else:
            # Fallback: basic analysis
            return {
                'main_theme': 'general',
                'emotion': 'neutral',
                'visual_mood': 'neutral',
                'video_keywords': article_data.get('title', '').split()[:5],
                'ken_burns_suggestion': 'zoom_in'
            }

    def _plan_scenes(self, article_data: Dict, analysis: Dict, duration: int) -> List[Dict]:
        """Plan video scenes from article"""
        scenes = []
        script = article_data.get('video_script', {})

        # Get script parts
        intro = script.get('intro', '')
        main_points = script.get('main_points', [])
        outro = script.get('outro', '')

        # Calculate scene durations
        total_parts = 1 + len(main_points) + (1 if outro else 0)
        scene_duration = duration / max(total_parts, 1)

        # Intro scene
        if intro:
            # Generate English search terms for better Pexels results
            intro_prompt = self._generate_english_search_prompt(
                analysis.get('main_theme', ''),
                analysis.get('keywords', []),
                'intro'
            )
            scenes.append({
                'type': 'intro',
                'text': intro,
                'duration': min(scene_duration, 10),
                'visual_prompt': intro_prompt,
                'effect': 'slow_reveal'
            })

        # Main point scenes
        for i, point in enumerate(main_points):
            scenes.append({
                'type': 'main',
                'text': point,
                'duration': scene_duration,
                'visual_prompt': self._get_scene_visual_prompt(point, analysis),
                'effect': 'auto'
            })

        # Outro scene
        if outro:
            # Generate English search terms for better Pexels results
            outro_prompt = self._generate_english_search_prompt(
                analysis.get('main_theme', ''),
                analysis.get('keywords', []),
                'outro'
            )
            scenes.append({
                'type': 'outro',
                'text': outro,
                'duration': min(scene_duration, 8),
                'visual_prompt': outro_prompt,
                'effect': 'zoom_out'
            })

        return scenes

    def _generate_english_search_prompt(self, theme: str, keywords: List[str], scene_type: str) -> str:
        """
        Generate English search prompt for Pexels API.
        Translates common German words and builds relevant search terms.
        """
        # Common German to English translations for video search
        de_to_en = {
            # Celestial/Space
            'mond': 'moon', 'supermond': 'supermoon', 'sonne': 'sun', 'stern': 'star',
            'sterne': 'stars', 'himmel': 'sky', 'nacht': 'night', 'nachthimmel': 'night sky',
            'astronomie': 'astronomy', 'weltraum': 'space',
            # Cities/Places
            'berlin': 'berlin', 'deutschland': 'germany', 'stadt': 'city',
            # Nature
            'wetter': 'weather', 'regen': 'rain', 'schnee': 'snow', 'wolken': 'clouds',
            'meer': 'sea', 'ozean': 'ocean', 'berg': 'mountain', 'wald': 'forest',
            # Technology
            'technologie': 'technology', 'computer': 'computer', 'internet': 'internet',
            'kuenstliche intelligenz': 'artificial intelligence', 'ki': 'AI',
            'roboter': 'robot', 'innovation': 'innovation', 'digital': 'digital',
            # People/Society
            'menschen': 'people', 'person': 'person', 'familie': 'family',
            'arbeit': 'work', 'buero': 'office', 'schule': 'school',
            # News/Events
            'ereignis': 'event', 'spektakel': 'spectacle', 'feier': 'celebration',
            'nachrichten': 'news', 'bericht': 'report',
            # General
            'neu': 'new', 'alt': 'old', 'gross': 'big', 'klein': 'small',
            'wichtig': 'important', 'zukunft': 'future', 'entwicklung': 'development'
        }

        # Build search terms from theme and keywords
        search_terms = []

        # Process theme - split and translate each word
        theme_lower = theme.lower()
        for de_word, en_word in de_to_en.items():
            if de_word in theme_lower:
                search_terms.append(en_word)

        # Add keywords (assuming they might already be English from analyzer)
        for kw in keywords[:3]:  # Top 3 keywords
            kw_lower = kw.lower()
            # Check if it's a German word
            if kw_lower in de_to_en:
                search_terms.append(de_to_en[kw_lower])
            elif kw_lower.isalpha() and len(kw_lower) > 2:
                search_terms.append(kw_lower)

        # Add scene type context
        if scene_type == 'intro':
            if not search_terms:
                search_terms = ['opening', 'beginning']
        elif scene_type == 'outro':
            if not search_terms:
                search_terms = ['ending', 'conclusion']

        # If still empty, use generic terms
        if not search_terms:
            search_terms = ['news', 'report', 'documentary']

        # Limit to 4 terms for better search results
        search_terms = list(dict.fromkeys(search_terms))[:4]  # Remove duplicates, keep order

        result = ' '.join(search_terms)
        logger.debug(f"Generated English search prompt: '{result}' from theme: '{theme}'")
        return result

    def _get_scene_visual_prompt(self, scene_text: str, analysis: Dict) -> str:
        """Generate visual search prompt for scene"""
        if self.content_analyzer and self.content_analyzer.enabled:
            result = self.content_analyzer.generate_visual_prompt(
                scene_text=scene_text,
                mood=analysis.get('visual_mood', 'neutral'),
                emotion=analysis.get('emotion', 'curiosity')
            )
            return result.get('primary_prompt', scene_text[:50])
        else:
            # Fallback: extract first few words
            words = scene_text.split()[:5]
            return ' '.join(words)

    def _gather_visuals(self,
                        scenes: List[Dict],
                        article_images: List[str],
                        analysis: Dict,
                        output_dir: Path,
                        use_stock_videos: bool,
                        target_duration: float = 30.0) -> List[Dict]:
        """
        Gather visual assets for all scenes.
        NEW: Ensures enough content to fill target duration.

        Args:
            scenes: List of scene dictionaries
            article_images: URLs/paths of article images
            analysis: Content analysis results
            output_dir: Directory to save downloaded assets
            use_stock_videos: Whether to try stock videos
            target_duration: Target video duration in seconds
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        assets = []
        total_video_duration = 0.0

        # Track available article images
        available_images = list(article_images)

        # Get keywords from analysis for better searches
        keywords = analysis.get('video_keywords', [])
        main_theme = analysis.get('main_theme', 'abstract')

        # Enhanced search terms - combine scene prompts with analysis keywords
        def get_search_terms(scene_prompt: str) -> List[str]:
            """Generate multiple search terms for better results"""
            terms = [scene_prompt]
            # Add main theme
            if main_theme and main_theme != 'general':
                terms.append(main_theme)
            # Add top keywords
            for kw in keywords[:3]:
                if kw not in scene_prompt.lower():
                    terms.append(kw)
            # Add generic fallbacks
            terms.extend(['professional', 'business', 'technology', 'nature', 'city'])
            return terms

        for i, scene in enumerate(scenes):
            asset = {
                'scene_index': i,
                'type': None,
                'path': None,
                'source': None,
                'duration': scene.get('duration', 5.0)
            }

            scene_prompt = scene.get('visual_prompt', '')
            search_terms = get_search_terms(scene_prompt)
            found = False

            # Priority 1: Article images
            if available_images:
                img_url = available_images.pop(0)
                local_path = self._download_image(img_url, output_dir / f"article_img_{i}.jpg")
                if local_path:
                    asset['type'] = 'image'
                    asset['path'] = str(local_path)
                    asset['source'] = 'article'
                    assets.append(asset)
                    total_video_duration += asset['duration']
                    logger.info(f"   ✅ Scene {i}: Article image")
                    continue

            # Priority 2: Stock videos - TRY MULTIPLE SEARCH TERMS
            if use_stock_videos and self.video_provider:
                for term in search_terms[:5]:  # Try up to 5 different terms
                    video_path = output_dir / f"stock_video_{i}.mp4"
                    try:
                        success = self.video_provider.get_video_for_scene(
                            scene_description=term,
                            output_path=str(video_path),
                            min_duration=3,
                            max_duration=20
                        )
                        if success and video_path.exists():
                            # Get actual video duration
                            vid_duration = self._get_video_duration(str(video_path))
                            asset['type'] = 'video'
                            asset['path'] = str(video_path)
                            asset['source'] = 'stock_video'
                            asset['duration'] = vid_duration
                            assets.append(asset)
                            total_video_duration += vid_duration
                            logger.info(f"   ✅ Scene {i}: Stock video ({vid_duration:.1f}s) - '{term}'")
                            found = True
                            break
                    except Exception as e:
                        logger.debug(f"   Video search '{term}' failed: {e}")
                        continue

                if found:
                    continue

            # Priority 3: Stock photos + Ken Burns - TRY MULTIPLE SEARCH TERMS
            if self.image_generator:
                for term in search_terms[:5]:
                    img_path = output_dir / f"stock_img_{i}.jpg"
                    try:
                        success = self.image_generator.generate_image(
                            prompt=term,
                            output_path=str(img_path),
                            use_stock=True
                        )
                        if success and img_path.exists():
                            asset['type'] = 'image'
                            asset['path'] = str(img_path)
                            asset['source'] = 'stock_photo'
                            assets.append(asset)
                            total_video_duration += asset['duration']
                            logger.info(f"   ✅ Scene {i}: Stock photo - '{term}'")
                            found = True
                            break
                    except Exception as e:
                        logger.debug(f"   Image search '{term}' failed: {e}")
                        continue

                if found:
                    continue

            # Priority 4: Placeholder (last resort)
            asset['type'] = 'placeholder'
            asset['path'] = None
            asset['source'] = 'none'
            assets.append(asset)
            logger.warning(f"   ⚠️ Scene {i}: No visual found (placeholder)")

        # Check if we have enough content for target duration
        logger.info(f"   📊 Total visual content: {total_video_duration:.1f}s (target: {target_duration:.1f}s)")

        # If not enough content, try to get more generic videos/images
        if total_video_duration < target_duration * 0.8:  # Less than 80% of target
            logger.info(f"   ⚠️ Not enough content, fetching additional assets...")
            self._fetch_additional_assets(
                assets=assets,
                target_duration=target_duration,
                current_duration=total_video_duration,
                output_dir=output_dir,
                keywords=keywords,
                main_theme=main_theme,
                use_stock_videos=use_stock_videos
            )

        return assets

    def _fetch_additional_assets(self,
                                  assets: List[Dict],
                                  target_duration: float,
                                  current_duration: float,
                                  output_dir: Path,
                                  keywords: List[str],
                                  main_theme: str,
                                  use_stock_videos: bool):
        """Fetch additional assets to fill target duration"""
        needed_duration = target_duration - current_duration
        logger.info(f"   Need {needed_duration:.1f}s more content")

        # Generic search terms that usually return results
        generic_terms = [
            main_theme,
            'abstract background',
            'motion graphics',
            'nature landscape',
            'city skyline',
            'technology',
            'business office',
            'sunrise sunset',
            'clouds sky',
            'water ocean'
        ]

        # Add keywords
        generic_terms = keywords[:3] + generic_terms

        additional_index = len(assets)

        for term in generic_terms:
            if current_duration >= target_duration:
                break

            if use_stock_videos and self.video_provider:
                video_path = output_dir / f"additional_video_{additional_index}.mp4"
                try:
                    success = self.video_provider.get_video_for_scene(
                        scene_description=term,
                        output_path=str(video_path),
                        min_duration=5,
                        max_duration=30
                    )
                    if success and video_path.exists():
                        vid_duration = self._get_video_duration(str(video_path))
                        assets.append({
                            'scene_index': additional_index,
                            'type': 'video',
                            'path': str(video_path),
                            'source': 'stock_video_additional',
                            'duration': vid_duration
                        })
                        current_duration += vid_duration
                        additional_index += 1
                        logger.info(f"   ✅ Additional video: {vid_duration:.1f}s - '{term}'")
                        continue
                except Exception:
                    pass

            # Try image if video failed
            if self.image_generator:
                img_path = output_dir / f"additional_img_{additional_index}.jpg"
                try:
                    success = self.image_generator.generate_image(
                        prompt=term,
                        output_path=str(img_path),
                        use_stock=True
                    )
                    if success and img_path.exists():
                        duration = min(8.0, needed_duration)  # Ken Burns images ~8s each
                        assets.append({
                            'scene_index': additional_index,
                            'type': 'image',
                            'path': str(img_path),
                            'source': 'stock_photo_additional',
                            'duration': duration
                        })
                        current_duration += duration
                        additional_index += 1
                        logger.info(f"   ✅ Additional image: {duration:.1f}s - '{term}'")
                except Exception:
                    pass

        logger.info(f"   📊 Final content duration: {current_duration:.1f}s")

    def _download_image(self, url: str, output_path: Path) -> Optional[Path]:
        """Download image from URL"""
        try:
            import requests

            # Skip if already local file
            if not url.startswith('http'):
                if Path(url).exists():
                    return Path(url)
                return None

            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                return output_path
        except Exception as e:
            logger.warning(f"⚠️ Image download failed: {e}")
        return None

    def _count_asset_types(self, assets: List[Dict]) -> Dict:
        """Count asset types"""
        counts = {'video': 0, 'image': 0, 'placeholder': 0}
        for asset in assets:
            asset_type = asset.get('type', 'placeholder')
            counts[asset_type] = counts.get(asset_type, 0) + 1
        return counts

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio file duration in seconds using FFprobe"""
        try:
            ffprobe_path = self.ken_burns.ffmpeg_path.replace('ffmpeg', 'ffprobe') if self.ken_burns else 'ffprobe'
            cmd = [
                ffprobe_path, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(audio_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                logger.info(f"   Audio duration: {duration:.1f}s")
                return duration
        except Exception as e:
            logger.warning(f"⚠️ Could not get audio duration: {e}")
        # Fallback: estimate from file size (rough)
        return 30.0

    def _get_video_duration(self, video_path: str) -> float:
        """Get video file duration in seconds"""
        try:
            ffprobe_path = self.ken_burns.ffmpeg_path.replace('ffmpeg', 'ffprobe') if self.ken_burns else 'ffprobe'
            cmd = [
                ffprobe_path, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"⚠️ Could not get video duration: {e}")
        return 10.0

    def _detect_sentence_boundaries(self, text: str) -> List[str]:
        """
        Detect sentence boundaries in text.
        Returns list of sentences.
        """
        import re
        # Split on sentence-ending punctuation followed by space or end
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _calculate_sentence_times(self, sentences: List[str], total_duration: float) -> List[float]:
        """
        Calculate approximate end time for each sentence based on character count.
        Assumes roughly equal reading speed throughout.

        Returns:
            List of end times for each sentence
        """
        if not sentences:
            return [total_duration]

        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            return [total_duration]

        end_times = []
        cumulative_chars = 0

        for sentence in sentences:
            cumulative_chars += len(sentence)
            # Proportional time based on character count
            end_time = (cumulative_chars / total_chars) * total_duration
            end_times.append(end_time)

        return end_times

    def _find_best_cut_point(self, sentence_times: List[float], target: float) -> float:
        """
        Find the best sentence boundary to cut at.
        Prefers cutting at a complete sentence, even if slightly longer than target.

        Args:
            sentence_times: End times of each sentence
            target: Target duration

        Returns:
            Best cut point (may be slightly longer than target)
        """
        if not sentence_times:
            return target

        # Find sentence endings >= target (complete sentences)
        valid_points = [t for t in sentence_times if t >= target]

        if valid_points:
            # Return the smallest one that completes a sentence past target
            return min(valid_points)

        # If no sentence ends after target, return the last sentence end
        return max(sentence_times)

    def _smart_trim_to_sentence(self,
                                 video_path: Path,
                                 voiceover_path: Path,
                                 script_text: str,
                                 target_duration: float,
                                 output_video: Path,
                                 output_audio: Path = None) -> tuple:
        """
        Smart trim video and audio at sentence boundary.
        Video will be slightly longer than target if needed to complete a sentence.

        Args:
            video_path: Input video
            voiceover_path: Input voiceover audio
            script_text: Full script text for sentence detection
            target_duration: Desired duration
            output_video: Output video path
            output_audio: Output audio path (optional)

        Returns:
            Tuple of (video_path, audio_path, actual_duration)
        """
        try:
            # Get actual voiceover duration
            voiceover_duration = self._get_audio_duration(voiceover_path)

            # If voiceover is shorter than or equal to target, no trimming needed
            if voiceover_duration <= target_duration:
                logger.info(f"   Voiceover ({voiceover_duration:.1f}s) <= target ({target_duration:.1f}s), no smart trim needed")
                return video_path, voiceover_path, voiceover_duration

            # Detect sentences and calculate times
            sentences = self._detect_sentence_boundaries(script_text)
            sentence_times = self._calculate_sentence_times(sentences, voiceover_duration)

            logger.info(f"   Found {len(sentences)} sentences in script")
            logger.info(f"   Sentence end times: {[f'{t:.1f}s' for t in sentence_times]}")

            # Find best cut point (at sentence boundary, may exceed target)
            cut_point = self._find_best_cut_point(sentence_times, target_duration)
            logger.info(f"   Smart cut point: {cut_point:.1f}s (target was {target_duration:.1f}s)")

            ffmpeg_path = self.ken_burns.ffmpeg_path if self.ken_burns else 'ffmpeg'

            # Trim video to cut point
            video_cmd = [
                ffmpeg_path, '-y',
                '-i', str(video_path),
                '-t', str(cut_point),
                '-c:v', 'copy',
                '-an',
                str(output_video)
            ]
            subprocess.run(video_cmd, capture_output=True, text=True, timeout=120)

            # Trim audio to cut point if output path provided
            trimmed_audio = voiceover_path
            if output_audio:
                audio_cmd = [
                    ffmpeg_path, '-y',
                    '-i', str(voiceover_path),
                    '-t', str(cut_point),
                    '-c:a', 'copy',
                    str(output_audio)
                ]
                subprocess.run(audio_cmd, capture_output=True, text=True, timeout=60)
                trimmed_audio = output_audio

            if output_video.exists():
                logger.info(f"   ✅ Smart trimmed to {cut_point:.1f}s at sentence boundary")
                return output_video, trimmed_audio, cut_point

        except Exception as e:
            logger.error(f"❌ Smart trim error: {e}")

        return video_path, voiceover_path, target_duration

    def _extend_video_to_duration(self, video_path: Path, target_duration: float, output_path: Path) -> Path:
        """
        Extend video to match target duration by looping if needed.
        If video is longer than target, it will be trimmed.
        """
        try:
            current_duration = self._get_video_duration(str(video_path))
            logger.info(f"   Video duration: {current_duration:.1f}s, target: {target_duration:.1f}s")

            ffmpeg_path = self.ken_burns.ffmpeg_path if self.ken_burns else 'ffmpeg'

            if current_duration >= target_duration:
                # Video is long enough, just trim it
                cmd = [
                    ffmpeg_path, '-y',
                    '-i', str(video_path),
                    '-t', str(target_duration),
                    '-c:v', 'copy',
                    '-an',  # Remove any existing audio
                    str(output_path)
                ]
            else:
                # Need to loop video to reach target duration
                loop_count = int(target_duration / current_duration) + 1
                cmd = [
                    ffmpeg_path, '-y',
                    '-stream_loop', str(loop_count),
                    '-i', str(video_path),
                    '-t', str(target_duration),
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '23',
                    '-an',  # Remove any existing audio
                    str(output_path)
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and output_path.exists():
                logger.info(f"   ✅ Video extended/trimmed to {target_duration:.1f}s")
                return output_path
            else:
                logger.warning(f"⚠️ Video extend failed: {result.stderr[:200]}")
        except Exception as e:
            logger.error(f"❌ Video extend error: {e}")

        return video_path  # Return original if extension fails

    def _generate_voiceover(self,
                            scenes: List[Dict],
                            output_dir: Path,
                            language: str,
                            style: str) -> Optional[Path]:
        """Generate voiceover for all scenes"""
        if not self.tts:
            logger.warning("⚠️ TTS not available")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        # Combine all scene texts
        full_text = ' '.join([scene.get('text', '') for scene in scenes])

        # Validate text is not empty
        full_text = full_text.strip()
        if not full_text or len(full_text) < 10:
            logger.warning(f"⚠️ Script text too short or empty: '{full_text[:50]}...'")
            return None

        logger.info(f"   Script text ({len(full_text)} chars): '{full_text[:100]}...'")

        # Select voice based on language
        voice_map = {
            'de': 'conrad',  # Professional German male
            'en': 'en-US-GuyNeural',  # Placeholder - would need different TTS
            'tr': 'tr-TR-AhmetNeural'  # Placeholder
        }

        output_path = output_dir / 'voiceover.mp3'

        try:
            success = self.tts.generate_speech(
                text=full_text,
                output_path=str(output_path),
                voice=voice_map.get(language, 'conrad'),
                rate='+0%'
            )

            if success and output_path.exists():
                file_size = output_path.stat().st_size
                if file_size > 1000:  # At least 1KB
                    logger.info(f"✅ Voiceover created: {file_size/1024:.1f} KB")
                    return output_path
                else:
                    logger.warning(f"⚠️ Voiceover file too small: {file_size} bytes")
        except Exception as e:
            logger.error(f"❌ Voice generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return None

    def _assemble_video(self,
                        visual_assets: List[Dict],
                        scenes: List[Dict],
                        voiceover_path: Optional[Path],
                        output_path: Path,
                        analysis: Dict,
                        target_duration: float = 30.0) -> Optional[Path]:
        """Assemble final video from assets - VOICEOVER-FIRST approach"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temp_clips = []

            # Get voiceover duration FIRST - this determines video length
            has_voiceover = voiceover_path and voiceover_path.exists()
            if has_voiceover:
                voiceover_duration = self._get_audio_duration(voiceover_path)
                logger.info(f"🎤 Voiceover duration: {voiceover_duration:.1f}s - video will match this")
            else:
                voiceover_duration = target_duration
                logger.warning(f"⚠️ No voiceover - using target duration: {voiceover_duration:.1f}s")

            # Process ALL assets (including additional ones fetched to fill duration)
            for i, asset in enumerate(visual_assets):
                clip_path = output_path.parent / f"temp_clip_{i}.mp4"

                # Get scene info if available, otherwise use defaults
                scene = scenes[i] if i < len(scenes) else {
                    'duration': asset.get('duration', 8.0),
                    'effect': 'auto'
                }

                if asset['type'] == 'video':
                    # Use stock video directly (maybe trim)
                    if asset.get('path') and Path(asset['path']).exists():
                        temp_clips.append(asset['path'])

                elif asset['type'] == 'image' and self.ken_burns:
                    # Apply Ken Burns effect to image
                    if asset.get('path') and Path(asset['path']).exists():
                        effect = scene.get('effect', 'auto')
                        duration = asset.get('duration', scene.get('duration', 5))
                        success = self.ken_burns.apply_effect(
                            input_path=asset['path'],
                            output_path=str(clip_path),
                            effect=effect,
                            duration=duration
                        )
                        if success:
                            temp_clips.append(str(clip_path))

                elif asset['type'] == 'image':
                    # Fallback: use VideoEditor for simple image clip
                    if asset.get('path') and Path(asset['path']).exists():
                        temp_clips.append(asset['path'])

            logger.info(f"📹 Processing {len(temp_clips)} video clips")

            # Merge all clips
            if temp_clips and self.video_editor:
                # First merge to temp file
                temp_merged = output_path.parent / 'temp_merged_video.mp4'
                success = self.video_editor.merge_videos(
                    video_paths=temp_clips,
                    output_path=str(temp_merged),
                    transition_duration=0.5
                )

                if success and temp_merged.exists():
                    # STEP 1: Extend/trim video to match target duration
                    temp_extended = output_path.parent / 'temp_extended_video.mp4'
                    extended_video = self._extend_video_to_duration(
                        video_path=temp_merged,
                        target_duration=voiceover_duration,
                        output_path=temp_extended
                    )

                    # STEP 2: Add voiceover if available
                    if has_voiceover:
                        logger.info(f"🎤 Adding voiceover to video...")

                        # Merge extended video with voiceover (NO -shortest!)
                        try:
                            ffmpeg_path = self.ken_burns.ffmpeg_path if self.ken_burns else 'ffmpeg'
                            ffmpeg_cmd = [
                                ffmpeg_path, '-y',
                                '-i', str(extended_video),   # Extended/trimmed video
                                '-i', str(voiceover_path),   # Voiceover audio
                                '-c:v', 'copy',              # Copy video stream
                                '-c:a', 'aac',               # AAC audio codec
                                '-b:a', '192k',              # Audio bitrate
                                '-map', '0:v:0',             # Take video from first input
                                '-map', '1:a:0',             # Take audio from second input
                                str(output_path)
                            ]

                            result = subprocess.run(
                                ffmpeg_cmd,
                                capture_output=True,
                                text=True,
                                timeout=180
                            )

                            # Clean up temp files
                            for temp_file in [temp_merged, temp_extended]:
                                if temp_file.exists():
                                    try:
                                        temp_file.unlink()
                                    except:
                                        pass

                            if result.returncode == 0 and output_path.exists():
                                # Verify final video has audio
                                final_duration = self._get_video_duration(str(output_path))
                                logger.info(f"✅ Video with voiceover created! Duration: {final_duration:.1f}s")
                                return output_path
                            else:
                                logger.warning(f"⚠️ FFmpeg audio merge failed: {result.stderr[:300]}")
                                # Fallback: use extended video without audio
                                if extended_video.exists():
                                    import shutil
                                    shutil.copy2(str(extended_video), str(output_path))
                                    final_duration = self._get_video_duration(str(output_path))
                                    logger.info(f"✅ Video created (no audio): {final_duration:.1f}s")
                                    return output_path

                        except Exception as audio_err:
                            logger.error(f"❌ Audio merge error: {audio_err}")
                            # Fallback: use extended video without audio
                            if extended_video.exists():
                                import shutil
                                shutil.copy2(str(extended_video), str(output_path))
                                return output_path
                    else:
                        # No voiceover - use extended video as final output
                        logger.info(f"📹 Creating video without voiceover...")
                        if extended_video.exists():
                            import shutil
                            shutil.copy2(str(extended_video), str(output_path))
                            final_duration = self._get_video_duration(str(output_path))
                            logger.info(f"✅ Silent video created: {final_duration:.1f}s")
                            # Clean up
                            for temp_file in [temp_merged, temp_extended]:
                                if temp_file.exists():
                                    try:
                                        temp_file.unlink()
                                    except:
                                        pass
                            return output_path

        except Exception as e:
            logger.error(f"❌ Video assembly failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return None

    def _generate_thumbnail(self,
                            video_path: Optional[Path],
                            title: str,
                            output_dir: Path,
                            analysis: Dict) -> Optional[Path]:
        """
        Generate thumbnail for video

        Args:
            video_path: Path to the video file
            title: Video title for overlay
            output_dir: Output directory
            analysis: Content analysis results

        Returns:
            Path to generated thumbnail or None
        """
        if not self.thumbnail_generator:
            logger.warning("⚠️ ThumbnailGenerator not available")
            return None

        try:
            # Determine style based on content analysis
            emotion = analysis.get('emotion', 'neutral')
            style_map = {
                'excitement': 'entertainment',
                'curiosity': 'news',
                'inspiration': 'educational',
                'urgency': 'breaking',
                'neutral': 'news'
            }
            style = style_map.get(emotion, 'news')

            thumbnail_path = output_dir / 'thumbnail.jpg'

            # Generate thumbnail from video
            success = self.thumbnail_generator.generate_thumbnail(
                title=title,
                output_path=str(thumbnail_path),
                video_path=str(video_path) if video_path else None,
                style=style,
                platform='youtube',  # Default to YouTube format
                frame_time_percent=0.3  # Extract frame at 30% of video
            )

            if success and thumbnail_path.exists():
                logger.info(f"✅ Thumbnail generated: {thumbnail_path}")
                return thumbnail_path
            else:
                logger.warning("⚠️ Thumbnail generation returned False")

        except Exception as e:
            logger.error(f"❌ Thumbnail generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return None

    def _generate_subtitles(self,
                            voiceover_path: Path,
                            output_dir: Path,
                            language: str = 'de') -> Optional[Path]:
        """
        Generate SRT subtitles from voiceover using Whisper

        Args:
            voiceover_path: Path to voiceover MP3 file
            output_dir: Output directory
            language: Language code (de, en, tr)

        Returns:
            Path to SRT file if successful, None otherwise
        """
        try:
            srt_path = output_dir / 'subtitles.srt'
            logger.info(f"📝 Generating subtitles from voiceover...")

            # Try faster-whisper first (local, free)
            try:
                from faster_whisper import WhisperModel

                # Use small model for speed
                model = WhisperModel("small", device="cpu", compute_type="int8")

                segments, info = model.transcribe(
                    str(voiceover_path),
                    language=language,
                    word_timestamps=True
                )

                # Generate SRT format
                with open(srt_path, 'w', encoding='utf-8') as f:
                    for i, segment in enumerate(segments, 1):
                        start_time = self._format_srt_time(segment.start)
                        end_time = self._format_srt_time(segment.end)
                        text = segment.text.strip()

                        f.write(f"{i}\n")
                        f.write(f"{start_time} --> {end_time}\n")
                        f.write(f"{text}\n\n")

                logger.info(f"✅ Subtitles generated with faster-whisper: {srt_path}")
                return srt_path

            except ImportError:
                logger.info("   faster-whisper not available, trying OpenAI Whisper API...")

            # Fallback to OpenAI Whisper API
            try:
                import openai

                openai_key = os.getenv('OPENAI_API_KEY')
                if not openai_key:
                    logger.warning("⚠️ OPENAI_API_KEY not set for Whisper API")
                    return None

                client = openai.OpenAI(api_key=openai_key)

                with open(voiceover_path, 'rb') as audio_file:
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language,
                        response_format="srt"
                    )

                # Save SRT content
                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(response)

                logger.info(f"✅ Subtitles generated with OpenAI Whisper: {srt_path}")
                return srt_path

            except Exception as e:
                logger.warning(f"⚠️ OpenAI Whisper failed: {e}")

            # Last fallback: Simple script-based SRT (from scenes)
            logger.info("   Using fallback script-based subtitles...")
            return self._generate_script_based_subtitles(voiceover_path, output_dir)

        except Exception as e:
            logger.error(f"❌ Subtitle generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _format_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _generate_script_based_subtitles(self,
                                          voiceover_path: Path,
                                          output_dir: Path) -> Optional[Path]:
        """Generate simple subtitles based on estimated timing"""
        try:
            srt_path = output_dir / 'subtitles.srt'

            # Get voiceover duration
            duration = self._get_audio_duration(voiceover_path)
            if not duration:
                return None

            # This is a simple placeholder - splits by estimated word timing
            # In a real implementation, you'd use actual speech recognition
            logger.info(f"   Creating placeholder subtitles for {duration:.1f}s audio")

            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write("1\n")
                f.write(f"00:00:00,000 --> {self._format_srt_time(duration)}\n")
                f.write("[Altyazı için Whisper kurulumu gerekli]\n")
                f.write("[Install: pip install faster-whisper]\n\n")

            logger.info(f"⚠️ Placeholder subtitles created: {srt_path}")
            return srt_path

        except Exception as e:
            logger.error(f"❌ Script-based subtitles failed: {e}")
            return None

    def get_status(self) -> Dict:
        """Get pipeline status"""
        return {
            'analyzer': self.content_analyzer.enabled if self.content_analyzer else False,
            'video_provider': bool(self.video_provider),
            'image_generator': bool(self.image_generator),
            'ken_burns': self.ken_burns.ffmpeg_available if self.ken_burns else False,
            'tts': bool(self.tts),
            'video_editor': bool(self.video_editor),
            'thumbnail_generator': bool(self.thumbnail_generator),
            'resolution': f"{self.resolution[0]}x{self.resolution[1]}",
            'fps': self.fps
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
    print("🎬 PRO VIDEO PIPELINE TEST")
    print("="*70)

    pipeline = ProVideoPipeline()

    # Show status
    print("\n📊 Pipeline Status:")
    status = pipeline.get_status()
    for module, available in status.items():
        if isinstance(available, bool):
            icon = "✅" if available else "❌"
            print(f"   {icon} {module}")
        else:
            print(f"   ℹ️ {module}: {available}")

    print("\n" + "="*70)
    print("✅ PRO VIDEO PIPELINE READY")
    print("="*70)
    print("\n💡 Usage:")
    print("   from modules.pro_video_pipeline import ProVideoPipeline")
    print("   pipeline = ProVideoPipeline()")
    print("   result = pipeline.produce_video_from_article(article_data, output_dir)")
    print("\n")
