"""
VIDEOCU v1 - Main Orchestrator
Tüm modülleri koordine eden ana kontrol sistemi
"""

import logging
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import json

from .content_generator import ContentGenerator
from .image_generator import ImageGenerator
from .voice_generator import VoiceGenerator, UnifiedVoiceGenerator
from .video_editor import VideoEditor
from .youtube_uploader import YouTubeUploader
from .trend_analyzer import TrendAnalyzer
from .music_library import MusicLibrary
from .intelligent_segmenter import IntelligentSegmenter
from .scene_continuity import SceneContinuityManager
from .seamless_montage import SeamlessMontage
from .photo_handler import PhotoHandler

logger = logging.getLogger(__name__)


class VideoProducer:
    """
    End-to-end video production orchestrator
    Trend → Script → Images → Voice → Video → Upload
    """

    def __init__(self, config: Dict):
        """
        Args:
            config: {
                'gemini_api_key': str,
                'elevenlabs_api_key': str (optional),
                'google_tts_credentials': str (optional),
                'tts_provider': str (optional, default: 'edge-tts'),
                'youtube_client_secrets': str (optional),
                'output_dir': str (optional)
            }
        """
        self.config = config
        self.output_dir = Path(config.get('output_dir', 'output/production'))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize modules
        logger.info("🚀 Initializing VIDEOCU v1 Production System...")

        self.content_gen = ContentGenerator(
            api_key=config['gemini_api_key']
        )

        self.image_gen = ImageGenerator()

        # Initialize Multi-Provider TTS
        self.voice_gen = UnifiedVoiceGenerator(
            provider=config.get('tts_provider', 'edge-tts'),
            elevenlabs_key=config.get('elevenlabs_api_key'),
            google_credentials=config.get('google_tts_credentials', 'google_tts_credentials.json'),
            fallback_order=['edge-tts', 'google-cloud', 'elevenlabs']
        )
        logger.info(f"🎤 TTS Provider: {config.get('tts_provider', 'edge-tts')} (with fallback)")

        self.video_editor = VideoEditor(
            resolution=(1920, 1080),
            fps=30
        )

        self.youtube_uploader = None
        if config.get('youtube_client_secrets'):
            try:
                self.youtube_uploader = YouTubeUploader(
                    client_secrets_file=config['youtube_client_secrets']
                )
            except Exception as e:
                logger.warning(f"⚠️ YouTube uploader not available: {e}")

        self.trend_analyzer = TrendAnalyzer(
            youtube_api_key=config.get('youtube_api_key', '')
        )

        # Initialize new modules
        self.music_library = MusicLibrary()
        self.segmenter = IntelligentSegmenter(max_segment_duration=120)
        self.continuity_manager = SceneContinuityManager()
        self.montage = SeamlessMontage(transition_duration=1.0)
        self.photo_handler = PhotoHandler()

        logger.info("✅ VideoProducer initialized (with segmentation & photo support)")

    def produce_video(self,
                     topic: str,
                     duration: int = 60,
                     language: str = 'de',
                     style: str = 'informativ',
                     upload_to_youtube: bool = False,
                     privacy_status: str = 'public') -> Optional[Dict]:
        """
        Tam video production pipeline

        Args:
            topic: Video konusu
            duration: Video süresi (saniye)
            language: Dil (de, en, tr)
            style: Video stili (informativ, unterhaltsam, dramatisch, humorvoll)
            upload_to_youtube: YouTube'a otomatik yükle
            privacy_status: YouTube privacy (public, private, unlisted)

        Returns:
            Production metadata dict
        """
        try:
            logger.info(f"🎬 Starting video production: '{topic}'")

            production_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            production_dir = self.output_dir / production_id
            production_dir.mkdir(exist_ok=True)

            result = {
                'production_id': production_id,
                'topic': topic,
                'status': 'in_progress',
                'started_at': datetime.now().isoformat(),
                'files': {}
            }

            # =====================================================================
            # PHASE 1: GENERATE SCRIPT
            # =====================================================================
            logger.info("📝 PHASE 1: Generating script...")

            script = self.content_gen.generate_video_script(
                topic=topic,
                duration=duration,
                language=language,
                style=style
            )

            if 'error' in script.get('metadata', {}):
                logger.error("❌ Script generation failed")
                result['status'] = 'failed'
                result['error'] = 'script_generation_failed'
                return result

            # Save script
            script_file = production_dir / "script.json"
            with open(script_file, 'w', encoding='utf-8') as f:
                json.dump(script, f, indent=2, ensure_ascii=False)

            result['script'] = script
            result['files']['script_json'] = str(script_file)

            logger.info(f"✅ Script generated: {script['title']}")

            # =====================================================================
            # PHASE 2: GENERATE IMAGES
            # =====================================================================
            logger.info("🎨 PHASE 2: Generating scene images...")

            images_dir = production_dir / "images"
            images_dir.mkdir(exist_ok=True)

            image_files = []
            for i, scene in enumerate(script['scenes'], 1):
                output_path = str(images_dir / f"scene_{i:03d}.jpg")

                success = self.image_gen.generate_image(
                    prompt=scene['image_prompt'],
                    output_path=output_path,
                    width=1920,
                    height=1080,
                    enhance=True
                )

                if success:
                    image_files.append(output_path)
                    logger.info(f"   ✅ Scene {i}/{len(script['scenes'])}")
                else:
                    # Placeholder
                    logger.warning(f"   ⚠️ Scene {i} timeout - using placeholder")
                    from PIL import Image
                    placeholder = Image.new('RGB', (1920, 1080), color=(30, 30, 40))
                    placeholder.save(output_path)
                    image_files.append(output_path)

            result['files']['images'] = image_files
            logger.info(f"✅ Images ready: {len(image_files)}/{len(script['scenes'])}")

            # Generate thumbnail
            thumbnail_path = production_dir / "thumbnail.jpg"
            self.image_gen.create_thumbnail(
                prompt=f"{script['title']}, YouTube thumbnail, professional",
                output_path=str(thumbnail_path),
                style="clickbait"
            )
            result['files']['thumbnail'] = str(thumbnail_path)

            # =====================================================================
            # PHASE 3: GENERATE VOICE (Multi-Provider TTS)
            # =====================================================================
            voiceover_path = None
            logger.info("🎤 PHASE 3: Generating voiceover...")

            voiceover_file = production_dir / "voiceover.mp3"

            # Auto-select voice based on language
            voice_config = {}
            if language == 'de':
                voice_config = {
                    'edge-tts': 'katja',      # Female German
                    'google-cloud': 'wavenet_a',
                    'elevenlabs': 'EXAVITQu4vr4xnSDxMaL'  # Bella
                }
            elif language == 'en':
                voice_config = {
                    'edge-tts': 'aria',
                    'google-cloud': 'wavenet_a',
                    'elevenlabs': 'pNInz6obpgDQGcFmaJgB'  # Adam
                }

            success = self.voice_gen.generate_speech(
                text=script['script'],
                output_path=str(voiceover_file),
                language=language,
                **voice_config
            )

            if success:
                voiceover_path = str(voiceover_file)
                result['files']['voiceover'] = voiceover_path
                provider_info = self.voice_gen.get_provider_info()
                logger.info(f"✅ Voiceover generated with {provider_info['active_provider']}")
            else:
                logger.warning("⚠️ All TTS providers failed, continuing without audio")

            # =====================================================================
            # PHASE 4: SELECT BACKGROUND MUSIC
            # =====================================================================
            music_path = None
            logger.info("🎵 PHASE 4: Selecting background music...")

            music_path = self.music_library.get_music_for_topic(topic)
            if music_path:
                logger.info(f"✅ Music selected: {Path(music_path).name}")
            else:
                logger.warning("⚠️ No music available")

            # =====================================================================
            # PHASE 5: CREATE VIDEO
            # =====================================================================
            logger.info("🎥 PHASE 5: Creating final video...")

            video_file = production_dir / "final_video.mp4"

            success = self.video_editor.create_video_from_script(
                script_data=script,
                image_files=image_files,
                voiceover_path=voiceover_path,
                music_path=music_path,
                output_path=str(video_file)
            )

            if not success:
                logger.error("❌ Video creation failed")
                result['status'] = 'failed'
                result['error'] = 'video_creation_failed'
                return result

            result['files']['video'] = str(video_file)

            # Create SRT subtitles
            srt_file = video_file.with_suffix('.srt')
            self.video_editor.add_subtitles(
                video_path=str(video_file),
                script_data=script,
                output_path=str(srt_file)
            )
            result['files']['subtitles'] = str(srt_file)

            # Get video info
            video_info = self.video_editor.get_video_info(str(video_file))
            result['video_info'] = video_info

            logger.info(f"✅ Video created: {video_info['duration']:.1f}s, {video_info['file_size_mb']:.2f} MB")

            # =====================================================================
            # PHASE 6: UPLOAD TO YOUTUBE (Optional)
            # =====================================================================
            if upload_to_youtube and self.youtube_uploader:
                logger.info("📺 PHASE 6: Uploading to YouTube...")

                upload_result = self.youtube_uploader.upload_video(
                    video_path=str(video_file),
                    title=script['title'],
                    description=script['description'],
                    tags=script.get('hashtags', []) + script.get('keywords', []),
                    category_id="28",  # Science & Technology
                    privacy_status=privacy_status,
                    thumbnail_path=str(thumbnail_path) if thumbnail_path.exists() else None
                )

                if upload_result:
                    result['youtube'] = upload_result
                    logger.info(f"✅ Uploaded to YouTube: {upload_result['url']}")
                else:
                    logger.warning("⚠️ YouTube upload failed")
            else:
                logger.info("⏭️ PHASE 6: Skipping YouTube upload")

            # =====================================================================
            # COMPLETE
            # =====================================================================
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()

            # Save production metadata
            metadata_file = production_dir / "production_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)

            result['files']['metadata'] = str(metadata_file)

            logger.info(f"✅ Production complete: {production_id}")
            return result

        except Exception as e:
            logger.error(f"❌ Production failed: {e}")
            result['status'] = 'failed'
            result['error'] = str(e)
            return result

    def produce_from_trend(self,
                          region: str = 'DE',
                          category: str = 'Science & Technology',
                          max_videos: int = 1,
                          upload_to_youtube: bool = False) -> List[Dict]:
        """
        Trending konulardan otomatik video üret

        Args:
            region: Bölge kodu (DE, US, TR)
            category: YouTube kategorisi
            max_videos: Maksimum video sayısı
            upload_to_youtube: YouTube'a otomatik yükle

        Returns:
            Production results listesi
        """
        try:
            logger.info(f"🔥 Fetching trending topics: {region} - {category}")

            # Get trends
            trends = self.trend_analyzer.get_trending_videos(
                region_code=region,
                category=category,
                max_results=10
            )

            if not trends:
                logger.warning("⚠️ No trends found")
                return []

            logger.info(f"✅ Found {len(trends)} trending topics")

            # Produce videos
            results = []
            for i, trend in enumerate(trends[:max_videos], 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"VIDEO {i}/{max_videos}: {trend['title']}")
                logger.info(f"{'='*60}")

                # Use trend title as topic
                result = self.produce_video(
                    topic=trend['title'],
                    duration=60,
                    language='de',
                    style='informativ',
                    upload_to_youtube=upload_to_youtube,
                    privacy_status='public'
                )

                if result and result['status'] == 'completed':
                    results.append(result)
                    logger.info(f"✅ Video {i} completed")
                else:
                    logger.warning(f"⚠️ Video {i} failed")

            logger.info(f"\n✅ Batch production complete: {len(results)}/{max_videos} successful")
            return results

        except Exception as e:
            logger.error(f"❌ Batch production failed: {e}")
            return []

    def produce_long_form_video(self,
                               topic: str,
                               target_duration: int = 900,  # 15 minutes default
                               language: str = 'de',
                               style: str = 'informativ',
                               upload_to_youtube: bool = False) -> Optional[Dict]:
        """
        Produce long-form video (15+ minutes) with intelligent segmentation

        Args:
            topic: Video topic
            target_duration: Target duration in seconds (default: 900 = 15 min)
            language: Language code
            style: Video style
            upload_to_youtube: Auto-upload to YouTube

        Returns:
            Production metadata dict
        """
        try:
            logger.info(f"🎬 Starting LONG-FORM video production: '{topic}' ({target_duration}s)")

            production_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_longform"
            production_dir = self.output_dir / production_id
            production_dir.mkdir(exist_ok=True)

            result = {
                'production_id': production_id,
                'topic': topic,
                'status': 'in_progress',
                'type': 'long_form',
                'target_duration': target_duration,
                'started_at': datetime.now().isoformat(),
                'files': {}
            }

            # STEP 1: Generate long-form script
            logger.info("📝 STEP 1: Generating long-form script...")
            script = self.content_gen.generate_video_script(
                topic=topic,
                duration=target_duration,
                language=language,
                style=style
            )

            if 'error' in script.get('metadata', {}):
                logger.error("❌ Script generation failed")
                result['status'] = 'failed'
                return result

            # STEP 2: Split into segments
            logger.info("✂️ STEP 2: Splitting into segments (max 120s each)...")
            segments = self.segmenter.split_script(script)

            if not segments:
                logger.error("❌ Segmentation failed")
                result['status'] = 'failed'
                return result

            logger.info(f"✅ Created {len(segments)} segments")

            # STEP 3: Extract style profile from first segment
            logger.info("🎨 STEP 3: Extracting style profile...")
            self.continuity_manager.extract_style_from_script(segments[0])

            # STEP 4: Process each segment
            logger.info(f"🎬 STEP 4: Processing {len(segments)} segments...")
            segment_videos = []

            for i, segment in enumerate(segments, 1):
                logger.info(f"\n  📹 Processing segment {i}/{len(segments)}...")

                # Apply style continuity
                if i > 1:
                    segment['scenes'] = self.continuity_manager.apply_to_segment(segment['scenes'])

                # Generate images for segment
                images_dir = production_dir / f"segment_{i:03d}_images"
                images_dir.mkdir(exist_ok=True)

                image_files = []
                for j, scene in enumerate(segment['scenes'], 1):
                    output_path = str(images_dir / f"scene_{j:03d}.jpg")
                    success = self.image_gen.generate_image(
                        prompt=scene['image_prompt'],
                        output_path=output_path,
                        use_stock=True
                    )
                    if success:
                        image_files.append(output_path)

                # Generate voiceover for segment
                voiceover_file = production_dir / f"segment_{i:03d}_voice.mp3"
                self.voice_gen.generate_speech(
                    text=segment['script'],
                    output_path=str(voiceover_file),
                    language=language
                )

                # Create segment video
                segment_video = production_dir / f"segment_{i:03d}.mp4"
                self.video_editor.create_video_from_script(
                    script_data=segment,
                    image_files=image_files,
                    voiceover_path=str(voiceover_file),
                    music_path=None,  # Music added in montage
                    output_path=str(segment_video)
                )

                segment_videos.append(str(segment_video))
                logger.info(f"  ✅ Segment {i} complete")

            # STEP 5: Merge segments with seamless montage
            logger.info("🎞️ STEP 5: Merging segments with seamless transitions...")

            final_video = production_dir / "final_longform_video.mp4"
            music_path = self.music_library.get_music_for_topic(topic)

            success = self.montage.merge_segments(
                segment_paths=segment_videos,
                output_path=str(final_video),
                background_music=music_path,
                music_volume=0.25
            )

            if not success:
                logger.error("❌ Montage failed")
                result['status'] = 'failed'
                return result

            result['files']['video'] = str(final_video)

            # STEP 6: Upload to YouTube (optional)
            if upload_to_youtube and self.youtube_uploader:
                logger.info("📺 STEP 6: Uploading to YouTube...")

                thumbnail_path = production_dir / "thumbnail.jpg"
                self.image_gen.create_thumbnail(
                    prompt=f"{script['title']}, YouTube thumbnail",
                    output_path=str(thumbnail_path)
                )

                upload_result = self.youtube_uploader.upload_video(
                    video_path=str(final_video),
                    title=script['title'],
                    description=script['description'],
                    tags=script.get('hashtags', []),
                    category_id="28",
                    privacy_status='public',
                    thumbnail_path=str(thumbnail_path)
                )

                if upload_result:
                    result['youtube'] = upload_result
                    logger.info(f"✅ Uploaded: {upload_result['url']}")

            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()
            result['segments_created'] = len(segments)

            logger.info(f"✅ Long-form production complete: {len(segments)} segments merged")
            return result

        except Exception as e:
            logger.error(f"❌ Long-form production failed: {e}")
            result['status'] = 'failed'
            result['error'] = str(e)
            return result

    def produce_from_photos(self,
                           photo_paths: List[str],
                           title: str,
                           description: str = "",
                           duration_per_photo: float = 5.0,
                           upload_to_youtube: bool = False) -> Optional[Dict]:
        """
        Produce video from user-uploaded photos

        Args:
            photo_paths: List of photo file paths
            title: Video title
            description: Video description
            duration_per_photo: Seconds per photo
            upload_to_youtube: Auto-upload to YouTube

        Returns:
            Production metadata dict
        """
        try:
            logger.info(f"📸 Starting photo video production: '{title}' ({len(photo_paths)} photos)")

            production_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_photos"
            production_dir = self.output_dir / production_id
            production_dir.mkdir(exist_ok=True)

            result = {
                'production_id': production_id,
                'title': title,
                'status': 'in_progress',
                'type': 'photo_video',
                'photo_count': len(photo_paths),
                'started_at': datetime.now().isoformat(),
                'files': {}
            }

            # Create video from photos
            logger.info("🎬 Creating video from photos...")

            video_file = production_dir / "photo_video.mp4"
            music_path = self.music_library.get_music_for_mood('upbeat')

            success = self.photo_handler.create_video_from_photos(
                photo_paths=photo_paths,
                output_path=str(video_file),
                duration_per_photo=duration_per_photo,
                background_music=music_path,
                music_volume=0.4
            )

            if not success:
                logger.error("❌ Photo video creation failed")
                result['status'] = 'failed'
                return result

            result['files']['video'] = str(video_file)

            # Upload to YouTube (optional)
            if upload_to_youtube and self.youtube_uploader:
                logger.info("📺 Uploading to YouTube...")

                upload_result = self.youtube_uploader.upload_video(
                    video_path=str(video_file),
                    title=title,
                    description=description or f"Video created from {len(photo_paths)} photos",
                    tags=['photos', 'memories', 'slideshow'],
                    category_id="22",  # People & Blogs
                    privacy_status='public'
                )

                if upload_result:
                    result['youtube'] = upload_result
                    logger.info(f"✅ Uploaded: {upload_result['url']}")

            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()

            logger.info(f"✅ Photo video production complete")
            return result

        except Exception as e:
            logger.error(f"❌ Photo video production failed: {e}")
            result['status'] = 'failed'
            result['error'] = str(e)
            return result

    def get_production_stats(self) -> Dict:
        """
        Production istatistikleri

        Returns:
            Stats dict
        """
        try:
            # Count productions
            productions = list(self.output_dir.glob("*/production_metadata.json"))

            total = len(productions)
            successful = 0
            failed = 0
            uploaded = 0

            for metadata_file in productions:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data.get('status') == 'completed':
                    successful += 1
                else:
                    failed += 1

                if 'youtube' in data:
                    uploaded += 1

            return {
                'total_productions': total,
                'successful': successful,
                'failed': failed,
                'youtube_uploads': uploaded,
                'success_rate': f"{(successful/total*100):.1f}%" if total > 0 else "0%"
            }

        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {}


# Test
if __name__ == "__main__":
    import sys
    import os
    from dotenv import load_dotenv

    # Set UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    load_dotenv()

    print("\n" + "="*70)
    print("🚀 VIDEOCU v1 - ORCHESTRATOR TEST")
    print("="*70)

    # Check API keys
    gemini_key = os.getenv('GEMINI_API_KEY')
    elevenlabs_key = os.getenv('ELEVENLABS_API_KEY')
    youtube_key = os.getenv('YOUTUBE_API_KEY')

    print("\n📋 API Keys Status:")
    print(f"   {'✅' if gemini_key else '❌'} Gemini AI")
    print(f"   {'✅' if elevenlabs_key else '❌'} ElevenLabs")
    print(f"   {'✅' if youtube_key else '❌'} YouTube Data API")

    if not gemini_key:
        print("\n❌ Gemini API key required!")
        sys.exit(1)

    # Initialize producer
    config = {
        'gemini_api_key': gemini_key,
        'elevenlabs_api_key': elevenlabs_key,
        'youtube_api_key': youtube_key,
        'youtube_client_secrets': 'client_secrets.json',
        'output_dir': 'output/orchestrator_test'
    }

    producer = VideoProducer(config)

    # Test production
    print("\n" + "="*70)
    print("TEST: SINGLE VIDEO PRODUCTION")
    print("="*70)

    test_topic = "ChatGPT vs Gemini - Welche KI ist besser 2025?"

    print(f"\n📝 Topic: {test_topic}")
    print(f"⏱️  Duration: 60s")
    print(f"🌍 Language: Deutsch")
    print(f"🎨 Style: Informativ")
    print(f"📺 Upload: No (local test only)")

    print("\n🚀 Starting production...")

    result = producer.produce_video(
        topic=test_topic,
        duration=60,
        language='de',
        style='informativ',
        upload_to_youtube=False
    )

    if result and result['status'] == 'completed':
        print("\n" + "="*70)
        print("✅ PRODUCTION SUCCESSFUL!")
        print("="*70)

        print(f"\n📊 Production Details:")
        print(f"   ID: {result['production_id']}")
        print(f"   Topic: {result['topic']}")
        print(f"   Started: {result['started_at']}")
        print(f"   Completed: {result['completed_at']}")

        print(f"\n📁 Generated Files:")
        for file_type, file_path in result['files'].items():
            if isinstance(file_path, list):
                print(f"   {file_type}: {len(file_path)} files")
            else:
                print(f"   {file_type}: {Path(file_path).name}")

        if result.get('video_info'):
            info = result['video_info']
            print(f"\n🎬 Video Info:")
            print(f"   Duration: {info['duration']:.1f}s")
            print(f"   Resolution: {info['size'][0]}x{info['size'][1]}")
            print(f"   Size: {info['file_size_mb']:.2f} MB")
            print(f"   Audio: {'Yes' if info['has_audio'] else 'No'}")

        print(f"\n📺 YouTube Ready:")
        print(f"   Title: {result['script']['title']}")
        print(f"   Description: {result['script']['description'][:100]}...")
        print(f"   Hashtags: {', '.join(result['script']['hashtags'][:5])}")

    else:
        print("\n❌ Production failed!")
        if result:
            print(f"   Error: {result.get('error', 'Unknown')}")

    # Show stats
    print("\n" + "="*70)
    print("📊 PRODUCTION STATISTICS")
    print("="*70)

    stats = producer.get_production_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n" + "="*70)
    print("✅ ORCHESTRATOR TEST COMPLETE")
    print("="*70)
