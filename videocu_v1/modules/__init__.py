"""
VIDEOCU v1 - Modules Package
"""

from .trend_analyzer import TrendAnalyzer, YOUTUBE_CATEGORIES, YOUTUBE_CATEGORIES_DE
from .social_trend_analyzer import SocialTrendAnalyzer
from .cross_analyzer import CrossAnalyzer
from .content_generator import ContentGenerator
from .voice_generator import VoiceGenerator, UnifiedVoiceGenerator
from .edge_tts_generator import EdgeTTSGenerator
from .google_tts_generator import GoogleTTSGenerator
from .image_generator import ImageGenerator
from .pexels_provider import PexelsProvider
from .unsplash_provider import UnsplashProvider
from .music_library import MusicLibrary
from .video_editor import VideoEditor
from .youtube_uploader import YouTubeUploader
from .orchestrator import VideoProducer
from .intelligent_segmenter import IntelligentSegmenter
from .scene_continuity import SceneContinuityManager
from .ken_burns import KenBurnsEffect
from .seamless_montage import SeamlessMontage
from .photo_handler import PhotoHandler

__all__ = [
    'TrendAnalyzer',
    'SocialTrendAnalyzer',
    'CrossAnalyzer',
    'ContentGenerator',
    'VoiceGenerator',
    'UnifiedVoiceGenerator',
    'EdgeTTSGenerator',
    'GoogleTTSGenerator',
    'ImageGenerator',
    'PexelsProvider',
    'UnsplashProvider',
    'MusicLibrary',
    'VideoEditor',
    'YouTubeUploader',
    'VideoProducer',
    'IntelligentSegmenter',
    'SceneContinuityManager',
    'KenBurnsEffect',
    'SeamlessMontage',
    'PhotoHandler',
    'YOUTUBE_CATEGORIES',
    'YOUTUBE_CATEGORIES_DE'
]
