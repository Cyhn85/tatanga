"""
VIDEOCU v1 - Voice Generator Module
ElevenLabs Text-to-Speech integration
"""

import requests
import logging
from typing import Optional, Dict, List
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class VoiceGenerator:
    """ElevenLabs ile ses üretimi"""

    # ElevenLabs API endpoint
    API_URL = "https://api.elevenlabs.io/v1"

    # Voice settings for optimal quality
    DEFAULT_VOICE_SETTINGS = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True
    }

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        self.available_voices = {}
        self._init_voices()

    def _init_voices(self):
        """Mevcut sesleri yükle"""
        try:
            response = requests.get(
                f"{self.API_URL}/voices",
                headers={"xi-api-key": self.api_key}
            )

            if response.status_code == 200:
                voices_data = response.json()
                self.available_voices = {
                    voice['voice_id']: voice['name']
                    for voice in voices_data.get('voices', [])
                }
                logger.info(f"✅ Loaded {len(self.available_voices)} ElevenLabs voices")
            else:
                logger.warning(f"⚠️ Could not load voices: {response.status_code}")
                # Use default voices
                self.available_voices = {
                    "EXAVITQu4vr4xnSDxMaL": "Bella (German Female)",
                    "pNInz6obpgDQGcFmaJgB": "Adam (English Male)"
                }

        except Exception as e:
            logger.error(f"❌ Voice initialization failed: {e}")
            # Fallback to default voices
            self.available_voices = {
                "EXAVITQu4vr4xnSDxMaL": "Bella (German Female)",
                "pNInz6obpgDQGcFmaJgB": "Adam (English Male)"
            }

    def generate_speech(self,
                       text: str,
                       voice_id: str = "EXAVITQu4vr4xnSDxMaL",
                       output_path: str = "output.mp3",
                       voice_settings: Optional[Dict] = None) -> bool:
        """
        Text'i sese çevir ve dosyaya kaydet

        Args:
            text: Seslendirilecek metin
            voice_id: ElevenLabs voice ID (default: Bella - German Female)
            output_path: Çıktı dosya yolu
            voice_settings: Voice ayarları (optional)

        Returns:
            True if successful, False otherwise
        """
        if not self.api_key:
            logger.error("❌ ElevenLabs API key not configured")
            return False

        try:
            logger.info(f"🎤 Generating speech for {len(text)} characters...")

            # Voice settings
            settings = voice_settings or self.DEFAULT_VOICE_SETTINGS

            # API request
            url = f"{self.API_URL}/text-to-speech/{voice_id}"
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": settings
            }

            response = requests.post(url, json=payload, headers=self.headers)

            if response.status_code == 200:
                # Dosyaya kaydet
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, 'wb') as f:
                    f.write(response.content)

                file_size = output_file.stat().st_size / 1024  # KB
                logger.info(f"✅ Speech generated: {output_file} ({file_size:.1f} KB)")
                return True

            else:
                logger.error(f"❌ ElevenLabs API error: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Speech generation failed: {e}")
            return False

    def generate_speech_chunked(self,
                                text: str,
                                voice_id: str = "EXAVITQu4vr4xnSDxMaL",
                                output_dir: str = "output",
                                chunk_size: int = 5000) -> List[str]:
        """
        Uzun metinleri parçalara böl ve her parçayı ayrı dosya olarak oluştur

        Args:
            text: Seslendirilecek metin
            voice_id: Voice ID
            output_dir: Çıktı dizini
            chunk_size: Her parçadaki maksimum karakter sayısı

        Returns:
            Oluşturulan dosya yolları listesi
        """
        output_files = []

        # Metni cümlelere böl
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) < chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "

        if current_chunk:
            chunks.append(current_chunk.strip())

        logger.info(f"📝 Split into {len(chunks)} chunks")

        # Her chunk için ses oluştur
        for i, chunk in enumerate(chunks, 1):
            output_path = f"{output_dir}/chunk_{i:03d}.mp3"

            success = self.generate_speech(
                text=chunk,
                voice_id=voice_id,
                output_path=output_path
            )

            if success:
                output_files.append(output_path)
            else:
                logger.warning(f"⚠️ Failed to generate chunk {i}")

            # Rate limiting
            time.sleep(0.5)

        return output_files

    def get_available_voices(self) -> Dict[str, str]:
        """Mevcut sesleri döndür"""
        return self.available_voices

    def get_voice_info(self, voice_id: str) -> Optional[Dict]:
        """Belirli bir ses hakkında detaylı bilgi al"""
        try:
            response = requests.get(
                f"{self.API_URL}/voices/{voice_id}",
                headers={"xi-api-key": self.api_key}
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"⚠️ Could not get voice info: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Voice info request failed: {e}")
            return None

    def get_usage_info(self) -> Optional[Dict]:
        """API kullanım bilgilerini al (quota, character count)"""
        try:
            response = requests.get(
                f"{self.API_URL}/user",
                headers={"xi-api-key": self.api_key}
            )

            if response.status_code == 200:
                user_data = response.json()

                subscription = user_data.get('subscription', {})
                usage = {
                    'character_count': subscription.get('character_count', 0),
                    'character_limit': subscription.get('character_limit', 0),
                    'can_use_instant_voice_cloning': subscription.get('can_use_instant_voice_cloning', False),
                    'tier': subscription.get('tier', 'free')
                }

                logger.info(f"📊 ElevenLabs Usage: {usage['character_count']}/{usage['character_limit']} characters")
                return usage

            else:
                logger.warning(f"⚠️ Could not get usage info: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Usage info request failed: {e}")
            return None

    def estimate_cost(self, text: str) -> Dict:
        """
        Metin için tahmini karakter sayısı ve maliyet hesapla

        Returns:
            Dict with character_count and estimated_cost
        """
        char_count = len(text)

        # ElevenLabs pricing (approximate)
        # Free: 10,000 chars/month
        # Starter: $5/month = 30,000 chars
        # Creator: $22/month = 100,000 chars

        return {
            'character_count': char_count,
            'estimated_minutes': char_count / 1000,  # Rough estimate
            'free_tier_sufficient': char_count <= 10000
        }


# Test
if __name__ == "__main__":
    import sys
    import os

    # Set UTF-8 encoding
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Load API key from env
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv('ELEVENLABS_API_KEY')
    if not api_key:
        print("⚠️ ELEVENLABS_API_KEY not found in .env")
        print("   Voice generation will not work until you add your API key")
        print("   Get your key from: https://elevenlabs.io")
        sys.exit(0)

    print("\n" + "="*60)
    print("🎤 VOICE GENERATOR TEST")
    print("="*60)

    generator = VoiceGenerator(api_key=api_key)

    # Test 1: List available voices
    print("\n📋 Available Voices:")
    voices = generator.get_available_voices()
    for voice_id, voice_name in list(voices.items())[:5]:
        print(f"   - {voice_name} ({voice_id})")

    # Test 2: Get usage info
    print("\n📊 API Usage:")
    usage = generator.get_usage_info()
    if usage:
        print(f"   Characters used: {usage['character_count']:,} / {usage['character_limit']:,}")
        print(f"   Tier: {usage['tier']}")

    # Test 3: Generate speech
    print("\n🎤 Generating test speech...")
    test_text = "Hallo! Dies ist ein Test der Sprachgenerierung mit ElevenLabs. Die KI-Technologie ermöglicht es uns, natürlich klingende Stimmen zu erzeugen."

    success = generator.generate_speech(
        text=test_text,
        voice_id="EXAVITQu4vr4xnSDxMaL",  # Bella (German)
        output_path="output/test_voice.mp3"
    )

    if success:
        print("   ✅ Test speech generated successfully!")
        print("   📁 Output: output/test_voice.mp3")
    else:
        print("   ❌ Speech generation failed")

    # Test 4: Estimate cost
    print("\n💰 Cost Estimation:")
    cost_info = generator.estimate_cost(test_text)
    print(f"   Characters: {cost_info['character_count']}")
    print(f"   Estimated duration: {cost_info['estimated_minutes']:.1f} minutes")
    print(f"   Free tier OK: {'✅ Yes' if cost_info['free_tier_sufficient'] else '❌ No'}")

    print("\n" + "="*60)
    print("✅ VOICE GENERATOR TEST COMPLETE")
    print("="*60)


# ==============================================================================
# UNIFIED VOICE GENERATOR - Multi-Provider Support
# ==============================================================================

class UnifiedVoiceGenerator:
    """
    Unified interface for multiple TTS providers

    Supports:
    - edge-tts (Microsoft Edge TTS) - FREE, unlimited
    - google-cloud (Google Cloud TTS) - Premium, 4M chars/month free
    - elevenlabs (ElevenLabs) - Premium, 10K free or Pro trial

    Usage:
        generator = UnifiedVoiceGenerator(
            provider='edge-tts',  # or 'google-cloud', 'elevenlabs'
            elevenlabs_key='sk_...',
            google_credentials='google_tts_credentials.json'
        )

        generator.generate_speech(
            text="Hello world",
            output_path="output.mp3"
        )
    """

    SUPPORTED_PROVIDERS = ['edge-tts', 'openai', 'google-cloud', 'elevenlabs']

    def __init__(self,
                 provider: str = 'edge-tts',
                 elevenlabs_key: Optional[str] = None,
                 google_credentials: Optional[str] = None,
                 openai_key: Optional[str] = None,
                 fallback_order: Optional[List[str]] = None):
        """
        Args:
            provider: Primary TTS provider ('edge-tts', 'openai', 'google-cloud', 'elevenlabs')
            elevenlabs_key: ElevenLabs API key (optional)
            google_credentials: Google Cloud credentials JSON path (optional)
            openai_key: OpenAI API key (optional)
            fallback_order: Provider fallback order (e.g., ['edge-tts', 'openai'])
        """
        self.provider = provider
        self.fallback_order = fallback_order or ['edge-tts', 'openai', 'google-cloud', 'elevenlabs']

        # Initialize providers
        self.providers = {}
        self._init_providers(elevenlabs_key, google_credentials, openai_key)

        logger.info(f"✅ UnifiedVoiceGenerator initialized (primary: {provider})")

    def _init_providers(self, elevenlabs_key, google_credentials, openai_key=None):
        """Initialize all available providers"""
        import os

        # Edge TTS (always available, no key needed)
        try:
            from .edge_tts_generator import EdgeTTSGenerator
            self.providers['edge-tts'] = EdgeTTSGenerator()
            logger.info("   ✅ Edge TTS available")
        except Exception as e:
            logger.warning(f"   ⚠️ Edge TTS not available: {e}")

        # OpenAI TTS
        openai_api_key = openai_key or os.getenv('OPENAI_API_KEY')
        if openai_api_key:
            try:
                openai_tts = OpenAITTSGenerator(api_key=openai_api_key)
                if openai_tts.client:
                    self.providers['openai'] = openai_tts
                    logger.info("   ✅ OpenAI TTS available")
            except Exception as e:
                logger.warning(f"   ⚠️ OpenAI TTS not available: {e}")

        # Google Cloud TTS
        if google_credentials:
            try:
                from .google_tts_generator import GoogleTTSGenerator
                self.providers['google-cloud'] = GoogleTTSGenerator(google_credentials)
                if self.providers['google-cloud'].client:
                    logger.info("   ✅ Google Cloud TTS available")
                else:
                    del self.providers['google-cloud']
            except Exception as e:
                logger.warning(f"   ⚠️ Google Cloud TTS not available: {e}")

        # ElevenLabs
        elevenlabs_api_key = elevenlabs_key or os.getenv('ELEVENLABS_API_KEY')
        if elevenlabs_api_key:
            try:
                self.providers['elevenlabs'] = VoiceGenerator(elevenlabs_api_key)
                logger.info("   ✅ ElevenLabs available")
            except Exception as e:
                logger.warning(f"   ⚠️ ElevenLabs not available: {e}")

    def generate_speech(self,
                       text: str,
                       output_path: str,
                       provider: Optional[str] = None,
                       **kwargs) -> bool:
        """
        Generate speech using specified provider (or fallback)

        Args:
            text: Text to synthesize
            output_path: Output MP3 file path
            provider: Override primary provider (optional)
            **kwargs: Provider-specific arguments

        Returns:
            True if successful
        """
        # Determine provider order
        primary_provider = provider or self.provider

        if primary_provider in self.providers:
            providers_to_try = [primary_provider]
        else:
            providers_to_try = []

        # Add fallbacks
        for fallback in self.fallback_order:
            if fallback not in providers_to_try and fallback in self.providers:
                providers_to_try.append(fallback)

        # Try each provider
        for prov in providers_to_try:
            try:
                logger.info(f"🎤 Attempting TTS with {prov}...")

                success = self._generate_with_provider(
                    prov, text, output_path, **kwargs
                )

                if success:
                    logger.info(f"✅ Speech generated with {prov}")
                    return True
                else:
                    logger.warning(f"⚠️ {prov} failed, trying next...")

            except Exception as e:
                logger.error(f"❌ {prov} error: {e}")
                continue

        logger.error("❌ All TTS providers failed")
        return False

    def _generate_with_provider(self,
                                provider: str,
                                text: str,
                                output_path: str,
                                **kwargs) -> bool:
        """Generate speech with specific provider"""
        gen = self.providers[provider]

        if provider == 'edge-tts':
            return gen.generate_speech(
                text=text,
                output_path=output_path,
                voice=kwargs.get('voice', 'katja'),
                rate=kwargs.get('rate', '+0%')
            )

        elif provider == 'google-cloud':
            return gen.generate_speech(
                text=text,
                output_path=output_path,
                voice=kwargs.get('voice', 'wavenet_c'),
                speaking_rate=kwargs.get('speaking_rate', 1.0)
            )

        elif provider == 'elevenlabs':
            return gen.generate_speech(
                text=text,
                output_path=output_path,
                voice_id=kwargs.get('voice_id', 'EXAVITQu4vr4xnSDxMaL')
            )

        elif provider == 'openai':
            return gen.generate_speech(
                text=text,
                output_path=output_path,
                voice=kwargs.get('voice', 'nova'),
                speed=kwargs.get('speed', 1.0)
            )

        return False

    def get_provider_info(self, provider: Optional[str] = None) -> Dict:
        """Get info about a specific provider"""
        prov = provider or self.provider

        if prov not in self.providers:
            return {'error': f'Provider {prov} not available'}

        gen = self.providers[prov]
        if hasattr(gen, 'get_provider_info'):
            return gen.get_provider_info()

        return {'provider': prov, 'available': True}

    def list_available_providers(self) -> List[str]:
        """List all initialized providers"""
        return list(self.providers.keys())

    def estimate_cost(self, text: str, provider: Optional[str] = None) -> Dict:
        """Estimate cost for specific provider"""
        prov = provider or self.provider

        if prov not in self.providers:
            return {'error': f'Provider {prov} not available'}

        gen = self.providers[prov]
        if hasattr(gen, 'estimate_cost'):
            return gen.estimate_cost(text)

        return {
            'character_count': len(text),
            'provider': prov,
            'cost_available': False
        }


# ==============================================================================
# OpenAI TTS Generator
# ==============================================================================

class OpenAITTSGenerator:
    """
    OpenAI Text-to-Speech Generator

    Features:
    - Natural sounding voices
    - 6 voice options: alloy, echo, fable, onyx, nova, shimmer
    - Two models: tts-1 ($0.015/1K chars) and tts-1-hd ($0.030/1K chars)
    - Supports multiple languages

    Usage:
        generator = OpenAITTSGenerator(api_key='sk-...')
        generator.generate_speech(
            text="Hello world",
            output_path="output.mp3",
            voice="nova"
        )
    """

    # Available voices
    VOICES = {
        'alloy': 'Neutral, balanced voice',
        'echo': 'Male, warm tone',
        'fable': 'Expressive, narrative style',
        'onyx': 'Deep male voice',
        'nova': 'Female, friendly and natural',
        'shimmer': 'Female, warm and clear'
    }

    # Model options
    MODELS = {
        'tts-1': {'cost_per_1k': 0.015, 'quality': 'standard'},
        'tts-1-hd': {'cost_per_1k': 0.030, 'quality': 'high'}
    }

    def __init__(self, api_key: str = None, model: str = 'tts-1'):
        """
        Initialize OpenAI TTS Generator

        Args:
            api_key: OpenAI API key (or uses OPENAI_API_KEY env var)
            model: Model to use ('tts-1' or 'tts-1-hd')
        """
        import os
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model
        self.client = None

        if self.api_key:
            try:
                import openai
                self.client = openai.OpenAI(api_key=self.api_key)
                logger.info(f"✅ OpenAI TTS initialized (model: {model})")
            except ImportError:
                logger.warning("⚠️ openai package not installed")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI TTS init failed: {e}")
        else:
            logger.warning("⚠️ OPENAI_API_KEY not set")

    def generate_speech(self,
                       text: str,
                       output_path: str,
                       voice: str = 'nova',
                       model: str = None,
                       speed: float = 1.0) -> bool:
        """
        Generate speech from text

        Args:
            text: Text to synthesize
            output_path: Output MP3 file path
            voice: Voice name (alloy, echo, fable, onyx, nova, shimmer)
            model: Override default model
            speed: Speech speed (0.25 to 4.0)

        Returns:
            True if successful
        """
        if not self.client:
            logger.error("❌ OpenAI client not initialized")
            return False

        try:
            logger.info(f"🎤 Generating speech with OpenAI TTS ({voice})...")
            logger.info(f"   Text length: {len(text)} chars")

            use_model = model or self.model
            response = self.client.audio.speech.create(
                model=use_model,
                voice=voice,
                input=text,
                speed=speed
            )

            # Save to file
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            response.stream_to_file(str(output_file))

            if output_file.exists():
                file_size = output_file.stat().st_size / 1024
                logger.info(f"✅ OpenAI speech generated: {file_size:.1f} KB")
                return True
            else:
                logger.error("❌ Output file not created")
                return False

        except Exception as e:
            logger.error(f"❌ OpenAI TTS generation failed: {e}")
            return False

    def get_available_voices(self) -> Dict[str, str]:
        """Get available voices"""
        return self.VOICES.copy()

    def estimate_cost(self, text: str) -> Dict:
        """Estimate cost for text"""
        char_count = len(text)
        model_info = self.MODELS.get(self.model, self.MODELS['tts-1'])
        cost = (char_count / 1000) * model_info['cost_per_1k']

        return {
            'character_count': char_count,
            'model': self.model,
            'quality': model_info['quality'],
            'estimated_cost_usd': round(cost, 4),
            'cost_per_1k_chars': model_info['cost_per_1k']
        }

    def get_provider_info(self) -> Dict:
        """Get provider information"""
        return {
            'provider': 'openai',
            'name': 'OpenAI TTS',
            'cost': self.MODELS[self.model]['cost_per_1k'],
            'model': self.model,
            'quality': 'Natural (Very High)',
            'voices': list(self.VOICES.keys()),
            'api_key_required': True,
            'official_api': True,
            'pros': [
                'Very natural sounding',
                'Multiple voice options',
                'Fast generation',
                'Consistent quality'
            ],
            'cons': [
                'Costs money ($0.015-0.030/1K chars)',
                'Requires API key',
                'Internet required'
            ]
        }
