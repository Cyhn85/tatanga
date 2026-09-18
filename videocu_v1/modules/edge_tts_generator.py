"""
VIDEOCU v1 - Edge TTS Generator Module
Microsoft Edge Text-to-Speech (FREE, Unlimited)
"""

import edge_tts
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List
import time

logger = logging.getLogger(__name__)


class EdgeTTSGenerator:
    """
    Microsoft Edge TTS ile ses üretimi

    Avantajlar:
    - Tamamen ücretsiz, API key gerektirmez
    - Sınırsız kullanım
    - Yüksek kalite Neural voices
    - German voices: Katja, Conrad, Amala, Seraphina

    Dezavantajlar:
    - Unofficial API (Microsoft istediği zaman kapatabilir)
    """

    # Voices by language (Neural quality)
    VOICES = {
        'de': {
            'katja': 'de-DE-KatjaNeural',      # Female, warm, natural
            'conrad': 'de-DE-ConradNeural',    # Male, clear, professional
            'amala': 'de-DE-AmalaNeural',      # Female, friendly
            'seraphina': 'de-DE-SeraphinaNeural',  # Female, expressive
            'killian': 'de-DE-KillianNeural',  # Male, dynamic
            'louisa': 'de-DE-LouisaNeural',    # Female, calm
            'kasper': 'de-DE-KasperNeural',    # Male, young
            'greta': 'de-DE-GretaNeural'       # Female, energetic
        },
        'en': {
            'guy': 'en-US-GuyNeural',          # Male, clear, news
            'jenny': 'en-US-JennyNeural',      # Female, friendly
            'aria': 'en-US-AriaNeural',        # Female, professional
            'davis': 'en-US-DavisNeural',      # Male, casual
            'tony': 'en-US-TonyNeural',        # Male, cheerful
            'nancy': 'en-US-NancyNeural',      # Female, warm
        },
        'tr': {
            'ahmet': 'tr-TR-AhmetNeural',      # Male, professional
            'emel': 'tr-TR-EmelNeural',        # Female, natural
        }
    }

    # Default voices per language
    DEFAULT_VOICES = {
        'de': 'conrad',
        'en': 'guy',
        'tr': 'ahmet'
    }

    # Backward compatibility
    GERMAN_VOICES = VOICES['de']

    def __init__(self, default_voice: str = 'katja', language: str = 'de'):
        """
        Args:
            default_voice: Default voice name (katja, conrad, guy, ahmet, etc.)
            language: Language code (de, en, tr)
        """
        self.language = language
        self.default_voice = default_voice or self.DEFAULT_VOICES.get(language, 'conrad')
        logger.info(f"✅ EdgeTTS initialized (language: {language}, voice: {self.default_voice})")

    def generate_speech(self,
                       text: str,
                       output_path: str,
                       voice: Optional[str] = None,
                       rate: str = '+0%',  # Speed: -50% to +100%
                       volume: str = '+0%',  # Volume: -50% to +50%
                       pitch: str = '+0Hz') -> bool:
        """
        Text'i sese çevir ve MP3 olarak kaydet

        Args:
            text: Konuşulacak metin
            output_path: Çıkış MP3 dosyası
            voice: Voice name (katja, conrad, etc.) - None ise default
            rate: Konuşma hızı (-50% to +100%)
            volume: Ses seviyesi (-50% to +50%)
            pitch: Ses perdesi (pitch adjustment)

        Returns:
            Başarılı ise True
        """
        try:
            logger.info(f"🎤 Generating speech with Edge TTS...")
            logger.info(f"   Text length: {len(text)} chars")

            # Select voice based on language
            voice_name = voice or self.default_voice
            lang_voices = self.VOICES.get(self.language, self.VOICES['de'])
            voice_id = lang_voices.get(voice_name)

            # Fallback: try other language voices or default
            if not voice_id:
                for lang, voices in self.VOICES.items():
                    if voice_name in voices:
                        voice_id = voices[voice_name]
                        break
                if not voice_id:
                    # Use default for current language
                    default_name = self.DEFAULT_VOICES.get(self.language, 'conrad')
                    voice_id = lang_voices.get(default_name, 'de-DE-ConradNeural')

            logger.info(f"   Voice: {voice_name} ({voice_id})")

            # Run async generation - FIXED: Always use new event loop for sync context
            # This fixes the "Event loop is already running" issue in Streamlit/Jupyter
            try:
                # Try to get existing loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context (Streamlit, Jupyter, etc.)
                    # Create a NEW loop in a separate thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self._async_generate(text, output_path, voice_id, rate, volume, pitch)
                        )
                        future.result(timeout=60)  # 60 second timeout
                else:
                    # No loop running, use asyncio.run
                    asyncio.run(self._async_generate(
                        text, output_path, voice_id, rate, volume, pitch
                    ))
            except RuntimeError:
                # No event loop exists, create one
                asyncio.run(self._async_generate(
                    text, output_path, voice_id, rate, volume, pitch
                ))

            # Verify output
            if Path(output_path).exists():
                file_size = Path(output_path).stat().st_size / 1024  # KB
                logger.info(f"✅ Speech generated: {file_size:.1f} KB")
                return True
            else:
                logger.error("❌ Output file not created")
                return False

        except Exception as e:
            logger.error(f"❌ Edge TTS generation failed: {e}")
            return False

    async def _async_generate(self,
                             text: str,
                             output_path: str,
                             voice_id: str,
                             rate: str,
                             volume: str,
                             pitch: str):
        """Async speech generation"""
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_id,
            rate=rate,
            volume=volume,
            pitch=pitch
        )

        await communicate.save(output_path)

    def get_available_voices(self) -> Dict[str, str]:
        """
        Kullanılabilir German sesleri döndür

        Returns:
            {voice_name: voice_id} dict
        """
        return self.GERMAN_VOICES.copy()

    def estimate_duration(self, text: str, rate: str = '+0%') -> float:
        """
        Tahmini ses süresi (saniye)

        Args:
            text: Metin
            rate: Konuşma hızı

        Returns:
            Tahmini süre (saniye)
        """
        # Average: 150 words/minute = 2.5 words/second
        word_count = len(text.split())

        # Adjust for rate
        rate_multiplier = 1.0
        if '+' in rate:
            rate_percent = int(rate.replace('+', '').replace('%', ''))
            rate_multiplier = 1.0 + (rate_percent / 100)
        elif '-' in rate:
            rate_percent = int(rate.replace('-', '').replace('%', ''))
            rate_multiplier = 1.0 - (rate_percent / 100)

        duration = (word_count / 2.5) / rate_multiplier
        return duration

    def get_provider_info(self) -> Dict:
        """Provider bilgilerini döndür"""
        return {
            'provider': 'edge-tts',
            'name': 'Microsoft Edge TTS',
            'cost': 0,  # FREE
            'limit': None,  # UNLIMITED
            'quality': 'Neural (High)',
            'languages': ['de-DE', 'en-US', 'en-GB', 'tr-TR', 'fr-FR', '...'],
            'german_voices': len(self.GERMAN_VOICES),
            'api_key_required': False,
            'official_api': False,
            'pros': [
                'Completely free',
                'Unlimited usage',
                'High quality Neural voices',
                'No API key needed',
                'Fast generation'
            ],
            'cons': [
                'Unofficial API (can be shut down)',
                'Internet connection required',
                'Not suitable for commercial large-scale use'
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
    print("🎤 EDGE TTS GENERATOR TEST")
    print("="*60)

    # Initialize
    generator = EdgeTTSGenerator(default_voice='katja')

    # Show provider info
    info = generator.get_provider_info()
    print(f"\n📊 Provider: {info['name']}")
    print(f"   Cost: ${info['cost']} (FREE)")
    print(f"   Limit: {'Unlimited' if info['limit'] is None else info['limit']}")
    print(f"   Quality: {info['quality']}")
    print(f"   German Voices: {info['german_voices']}")

    # Show available voices
    print(f"\n🎭 Available German Voices:")
    voices = generator.get_available_voices()
    for name, voice_id in voices.items():
        print(f"   - {name}: {voice_id}")

    # Test text
    test_text = """
    Künstliche Intelligenz revolutioniert die deutsche Wirtschaft im Jahr 2025.
    Von automatisierten Produktionsprozessen bis hin zu personalisierten Kundenservices -
    KI verändert unsere Arbeitsweise grundlegend.
    """

    print(f"\n📝 Test Text:")
    print(f"   Characters: {len(test_text)}")
    print(f"   Words: {len(test_text.split())}")

    # Estimate duration
    duration = generator.estimate_duration(test_text)
    print(f"   Estimated Duration: {duration:.1f} seconds")

    # Generate speech
    output_file = "output/test_edge_tts.mp3"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    print(f"\n🎤 Generating speech...")
    print(f"   Output: {output_file}")

    start_time = time.time()
    success = generator.generate_speech(
        text=test_text.strip(),
        output_path=output_file,
        voice='katja',
        rate='+0%'
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
    print("✅ EDGE TTS TEST COMPLETE")
    print("="*60)

    # Test all voices
    print(f"\n🎭 Testing all German voices...")
    for voice_name in ['katja', 'conrad', 'amala']:
        output = f"output/test_edge_tts_{voice_name}.mp3"
        print(f"\n   Generating {voice_name}...")

        success = generator.generate_speech(
            text="Hallo, ich bin eine künstliche Intelligenz.",
            output_path=output,
            voice=voice_name
        )

        if success:
            print(f"   ✅ {voice_name} generated")
        else:
            print(f"   ❌ {voice_name} failed")

    print(f"\n✅ All voice tests complete!")
