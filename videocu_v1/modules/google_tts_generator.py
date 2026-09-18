"""
VIDEOCU v1 - Google Cloud TTS Generator Module
Google Cloud Text-to-Speech with WaveNet (Premium Quality)
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List
import os

try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class GoogleTTSGenerator:
    """
    Google Cloud TTS ile ses üretimi

    Avantajlar:
    - Premium WaveNet quality (en yüksek kalite)
    - 4 million chars/month FREE
    - Official Google API
    - Çok dilli destek

    Dezavantajlar:
    - Google Cloud hesap gerekli (billing setup)
    - Service account JSON credentials gerekli
    - Limit sonrası ücretli ($16/million chars)
    """

    # German WaveNet voices (Premium quality)
    GERMAN_VOICES = {
        'wavenet_a': {
            'name': 'de-DE-Wavenet-A',
            'gender': 'FEMALE',
            'description': 'Female, professional, clear'
        },
        'wavenet_b': {
            'name': 'de-DE-Wavenet-B',
            'gender': 'MALE',
            'description': 'Male, authoritative, deep'
        },
        'wavenet_c': {
            'name': 'de-DE-Wavenet-C',
            'gender': 'FEMALE',
            'description': 'Female, warm, friendly'
        },
        'wavenet_d': {
            'name': 'de-DE-Wavenet-D',
            'gender': 'MALE',
            'description': 'Male, natural, versatile'
        },
        'wavenet_e': {
            'name': 'de-DE-Wavenet-E',
            'gender': 'MALE',
            'description': 'Male, young, energetic'
        },
        'wavenet_f': {
            'name': 'de-DE-Wavenet-F',
            'gender': 'FEMALE',
            'description': 'Female, mature, expressive'
        }
    }

    def __init__(self, credentials_json: Optional[str] = None):
        """
        Args:
            credentials_json: Path to Google Cloud service account JSON file
        """
        if not GOOGLE_TTS_AVAILABLE:
            logger.error("❌ google-cloud-texttospeech not installed!")
            logger.info("   Install: pip install google-cloud-texttospeech")
            self.client = None
            return

        self.credentials_path = credentials_json
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Google Cloud TTS client"""
        try:
            # Set credentials environment variable if provided
            if self.credentials_path and Path(self.credentials_path).exists():
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(Path(self.credentials_path).absolute())
                logger.info(f"🔑 Using credentials: {self.credentials_path}")

            # Initialize client
            self.client = texttospeech.TextToSpeechClient()
            logger.info("✅ Google Cloud TTS initialized")

        except Exception as e:
            logger.error(f"❌ Google Cloud TTS initialization failed: {e}")
            logger.info("💡 Setup instructions:")
            logger.info("   1. Go to: https://console.cloud.google.com/")
            logger.info("   2. Select project: kozmik oda")
            logger.info("   3. Enable Cloud Text-to-Speech API")
            logger.info("   4. Create Service Account → Download JSON")
            logger.info("   5. Save JSON as: google_tts_credentials.json")
            logger.info("   6. Set path in .env: GOOGLE_TTS_CREDENTIALS_JSON=./google_tts_credentials.json")
            self.client = None

    def generate_speech(self,
                       text: str,
                       output_path: str,
                       voice: str = 'wavenet_c',  # Female, warm
                       speaking_rate: float = 1.0,  # 0.25 to 4.0
                       pitch: float = 0.0,  # -20.0 to 20.0
                       volume_gain_db: float = 0.0) -> bool:
        """
        Text'i sese çevir ve MP3 olarak kaydet

        Args:
            text: Konuşulacak metin
            output_path: Çıkış MP3 dosyası
            voice: Voice name (wavenet_a, wavenet_b, etc.)
            speaking_rate: Konuşma hızı (0.25-4.0, default 1.0)
            pitch: Ses perdesi (-20 to +20, default 0)
            volume_gain_db: Volume gain in dB

        Returns:
            Başarılı ise True
        """
        if not self.client:
            logger.error("❌ Google Cloud TTS not initialized")
            return False

        try:
            logger.info(f"🎤 Generating speech with Google Cloud TTS...")
            logger.info(f"   Text length: {len(text)} chars")

            # Get voice config
            voice_config = self.GERMAN_VOICES.get(voice, self.GERMAN_VOICES['wavenet_c'])
            logger.info(f"   Voice: {voice} ({voice_config['name']})")

            # Set text input
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Build voice parameters
            voice_params = texttospeech.VoiceSelectionParams(
                language_code='de-DE',
                name=voice_config['name']
            )

            # Set audio config
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=speaking_rate,
                pitch=pitch,
                volume_gain_db=volume_gain_db
            )

            # Perform synthesis
            logger.info("   Synthesizing...")
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config
            )

            # Write to file
            with open(output_path, 'wb') as f:
                f.write(response.audio_content)

            # Verify
            if Path(output_path).exists():
                file_size = Path(output_path).stat().st_size / 1024  # KB
                logger.info(f"✅ Speech generated: {file_size:.1f} KB")
                return True
            else:
                logger.error("❌ Output file not created")
                return False

        except Exception as e:
            logger.error(f"❌ Google Cloud TTS generation failed: {e}")
            return False

    def get_available_voices(self) -> Dict:
        """
        Kullanılabilir German sesleri döndür

        Returns:
            Voice configurations dict
        """
        return self.GERMAN_VOICES.copy()

    def estimate_cost(self, text: str) -> Dict:
        """
        Maliyet tahmini

        Args:
            text: Metin

        Returns:
            Cost estimation dict
        """
        char_count = len(text)

        # Google Cloud TTS pricing
        # WaveNet: First 1M chars free, then $16/million
        # Standard: First 4M chars free, then $4/million

        free_tier_limit = 4_000_000  # 4M chars/month
        cost_per_million = 16  # WaveNet pricing

        if char_count <= free_tier_limit:
            cost = 0
            free_tier_sufficient = True
        else:
            billable_chars = char_count - free_tier_limit
            cost = (billable_chars / 1_000_000) * cost_per_million
            free_tier_sufficient = False

        return {
            'character_count': char_count,
            'free_tier_limit': free_tier_limit,
            'free_tier_sufficient': free_tier_sufficient,
            'estimated_cost_usd': cost,
            'pricing_model': 'WaveNet',
            'cost_per_million': cost_per_million
        }

    def get_provider_info(self) -> Dict:
        """Provider bilgilerini döndür"""
        return {
            'provider': 'google-cloud-tts',
            'name': 'Google Cloud Text-to-Speech',
            'cost': '0-16',  # $0 (free tier) to $16/million
            'free_tier': '4M chars/month',
            'limit': 4_000_000,  # chars/month
            'quality': 'WaveNet (Premium)',
            'languages': ['de-DE', 'en-US', 'en-GB', 'tr-TR', '100+ languages'],
            'german_voices': len(self.GERMAN_VOICES),
            'api_key_required': False,
            'credentials_required': True,
            'official_api': True,
            'pros': [
                'Highest quality (WaveNet)',
                '4M chars/month FREE',
                'Official Google API',
                'Very stable and reliable',
                '100+ languages',
                'Perfect naturalness'
            ],
            'cons': [
                'Requires Google Cloud account',
                'Billing setup needed (credit card)',
                'Service account JSON required',
                'Complex setup',
                'Paid after free tier ($16/million)'
            ]
        }


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
    print("🎤 GOOGLE CLOUD TTS GENERATOR TEST")
    print("="*60)

    # Check if credentials exist
    creds_path = "google_tts_credentials.json"

    if not Path(creds_path).exists():
        print(f"\n❌ Credentials not found: {creds_path}")
        print("\n📋 Setup Instructions:")
        print("   1. Go to: https://console.cloud.google.com/")
        print("   2. Select project: kozmik oda")
        print("   3. Enable API: Cloud Text-to-Speech API")
        print("   4. Create Service Account:")
        print("      - IAM & Admin > Service Accounts")
        print("      - CREATE SERVICE ACCOUNT")
        print("      - Name: videocu-tts")
        print("      - Role: Cloud Text-to-Speech Admin")
        print("   5. Create Key:")
        print("      - Click on service account")
        print("      - KEYS tab > ADD KEY > JSON")
        print("      - Download and save as google_tts_credentials.json")
        print("\n⚠️ Cannot test without credentials")
        sys.exit(1)

    print(f"✅ Credentials found: {creds_path}")

    # Initialize
    generator = GoogleTTSGenerator(credentials_json=creds_path)

    if not generator.client:
        print("\n❌ Google Cloud TTS initialization failed")
        print("   Check credentials and API enablement")
        sys.exit(1)

    # Show provider info
    info = generator.get_provider_info()
    print(f"\n📊 Provider: {info['name']}")
    print(f"   Cost: ${info['cost']}/million chars")
    print(f"   Free Tier: {info['free_tier']}")
    print(f"   Quality: {info['quality']}")
    print(f"   German Voices: {info['german_voices']}")

    # Show available voices
    print(f"\n🎭 Available German Voices:")
    voices = generator.get_available_voices()
    for name, config in voices.items():
        print(f"   - {name}: {config['name']} ({config['gender']}) - {config['description']}")

    # Test text
    test_text = """
    Künstliche Intelligenz revolutioniert die deutsche Wirtschaft im Jahr 2025.
    Von automatisierten Produktionsprozessen bis hin zu personalisierten Kundenservices -
    KI verändert unsere Arbeitsweise grundlegend.
    """

    print(f"\n📝 Test Text:")
    print(f"   Characters: {len(test_text)}")

    # Cost estimation
    cost_info = generator.estimate_cost(test_text)
    print(f"\n💰 Cost Estimation:")
    print(f"   Characters: {cost_info['character_count']:,}")
    print(f"   Free Tier: {cost_info['free_tier_sufficient']}")
    print(f"   Estimated Cost: ${cost_info['estimated_cost_usd']:.4f}")

    # Generate speech
    output_file = "output/test_google_tts.mp3"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    print(f"\n🎤 Generating speech...")
    print(f"   Output: {output_file}")

    import time
    start_time = time.time()
    success = generator.generate_speech(
        text=test_text.strip(),
        output_path=output_file,
        voice='wavenet_c',  # Female, warm
        speaking_rate=1.0
    )
    generation_time = time.time() - start_time

    if success:
        file_size = Path(output_file).stat().st_size / 1024
        print(f"\n✅ Speech generated successfully!")
        print(f"   File: {output_file}")
        print(f"   Size: {file_size:.1f} KB")
        print(f"   Generation Time: {generation_time:.2f}s")
        print(f"\n💡 Play the audio file to test quality!")
    else:
        print(f"\n❌ Generation failed!")

    print("\n" + "="*60)
    print("✅ GOOGLE CLOUD TTS TEST COMPLETE")
    print("="*60)
