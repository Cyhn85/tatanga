"""
VIDEOCU v1 - Music Composer Agent
Melody extraction and music arrangement specialist

Features:
- Extract MIDI from hummed/sung melodies
- Arrange music in various styles (jazz, pop, club, classical)
- Integration with Chef AI system
"""

import logging
import os
from typing import Dict, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class MusicComposerAgent:
    """
    Music composition specialist agent

    Responsibilities:
    - Extract melodies from voice recordings
    - Arrange MIDI into full music compositions
    - Style-specific arrangement (jazz, pop, club, classical)
    - Audio format conversion
    """

    # Supported music styles
    STYLES = {
        'jazz': {
            'tempo': 120,
            'instruments': ['piano', 'bass', 'drums', 'saxophone'],
            'description': 'Smooth jazz with improvisation'
        },
        'pop': {
            'tempo': 128,
            'instruments': ['synth', 'bass', 'drums', 'vocals'],
            'description': 'Modern pop with catchy hooks'
        },
        'club': {
            'tempo': 130,
            'instruments': ['synth', 'bass', 'drums', 'effects'],
            'description': 'Electronic dance music'
        },
        'classical': {
            'tempo': 100,
            'instruments': ['piano', 'strings', 'orchestra'],
            'description': 'Classical orchestral arrangement'
        },
        'ambient': {
            'tempo': 80,
            'instruments': ['pad', 'piano', 'strings'],
            'description': 'Atmospheric background music'
        }
    }

    def __init__(self, skill_library=None, output_dir: str = "output/music"):
        """
        Initialize Music Composer Agent

        Args:
            skill_library: SkillLibrary instance
            output_dir: Directory for output files
        """
        self.skill_library = skill_library
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.agent_type = "music_composer"

        # Check for melody extraction library (Basic Pitch)
        self.melody_extractor_available = self._check_basic_pitch()

        # Check for music generation library (MusicGen or similar)
        self.music_generator_available = self._check_music_generator()

        logger.info("🎵 Music Composer Agent initialized")
        logger.info(f"   Melody Extractor: {'✅' if self.melody_extractor_available else '❌ (install: pip install basic-pitch)'}")
        logger.info(f"   Music Generator: {'✅' if self.music_generator_available else '❌ (install: pip install audiocraft)'}")

    def _check_basic_pitch(self) -> bool:
        """Check if Basic Pitch is available"""
        try:
            import basic_pitch
            return True
        except ImportError:
            return False

    def _check_music_generator(self) -> bool:
        """Check if music generation library is available"""
        try:
            # Check for MusicGen (Meta's AudioCraft)
            import audiocraft
            return True
        except ImportError:
            return False

    def execute_task(self, task: Dict) -> Dict:
        """
        Execute music composition task

        Args:
            task: Task from Chef AI

        Returns:
            Execution result
        """
        try:
            analysis = task['analysis']
            parameters = analysis.get('parameters', {})

            logger.info(f"🎵 Music Composer Agent executing task: {task['task_id']}")

            # Determine music task type
            if parameters.get('extract_melody', False) or parameters.get('audio_file'):
                return self._extract_melody_task(parameters)
            elif parameters.get('arrange_music', False) or parameters.get('midi_file'):
                return self._arrange_music_task(parameters)
            else:
                return self._create_music_from_description(parameters)

        except Exception as e:
            logger.error(f"❌ Music Composer Agent failed: {e}")
            return {'success': False, 'error': str(e)}

    def _extract_melody_task(self, params: Dict) -> Dict:
        """
        Extract melody from audio file

        Args:
            params: Task parameters with 'audio_file'

        Returns:
            Result with MIDI file path
        """
        logger.info("   🎤 Extracting melody from audio...")

        audio_file = params.get('audio_file')
        if not audio_file or not os.path.exists(audio_file):
            return {'success': False, 'error': 'Audio file not found'}

        if not self.melody_extractor_available:
            return {
                'success': False,
                'error': 'Melody extractor not available. Install: pip install basic-pitch'
            }

        try:
            # Extract melody using Basic Pitch
            output_midi = self.output_dir / f"melody_{Path(audio_file).stem}.mid"
            success = self._extract_melody_with_basic_pitch(audio_file, str(output_midi))

            if success:
                return {
                    'success': True,
                    'midi_file': str(output_midi),
                    'message': 'Melody extracted successfully'
                }
            else:
                return {'success': False, 'error': 'Melody extraction failed'}

        except Exception as e:
            logger.error(f"   ❌ Melody extraction error: {e}")
            return {'success': False, 'error': str(e)}

    def _extract_melody_with_basic_pitch(self, audio_path: str, output_midi: str) -> bool:
        """
        Extract melody using Basic Pitch (Spotify)

        Args:
            audio_path: Input audio file
            output_midi: Output MIDI file

        Returns:
            True if successful
        """
        try:
            from basic_pitch.inference import predict
            from basic_pitch import ICASSP_2022_MODEL_PATH

            logger.info(f"      Processing: {Path(audio_path).name}")

            # Predict notes
            model_output, midi_data, note_events = predict(
                audio_path,
                ICASSP_2022_MODEL_PATH
            )

            # Save MIDI
            midi_data.write(output_midi)

            logger.info(f"      ✅ MIDI saved: {output_midi}")
            return True

        except Exception as e:
            logger.error(f"      ❌ Basic Pitch error: {e}")
            return False

    def _arrange_music_task(self, params: Dict) -> Dict:
        """
        Arrange MIDI into full music composition

        Args:
            params: Task parameters with 'midi_file' and 'style'

        Returns:
            Result with audio file path
        """
        logger.info("   🎹 Arranging music...")

        midi_file = params.get('midi_file')
        style = params.get('style', 'pop')

        if not midi_file or not os.path.exists(midi_file):
            return {'success': False, 'error': 'MIDI file not found'}

        if style not in self.STYLES:
            logger.warning(f"   ⚠️ Unknown style '{style}', using 'pop'")
            style = 'pop'

        style_info = self.STYLES[style]
        logger.info(f"      Style: {style} - {style_info['description']}")

        if not self.music_generator_available:
            # Fallback: Use music library with MIDI
            return self._arrange_with_music_library(midi_file, style, params)
        else:
            # Use AI music generation
            return self._arrange_with_ai(midi_file, style, params)

    def _arrange_with_music_library(self, midi_file: str, style: str, params: Dict) -> Dict:
        """
        Arrange using existing music library as fallback

        Args:
            midi_file: Input MIDI file
            style: Music style
            params: Additional parameters

        Returns:
            Result with audio file
        """
        logger.info("      Using music library fallback...")

        try:
            from modules.music_library import MusicLibrary

            music_lib = MusicLibrary()
            style_info = self.STYLES[style]

            # Get music matching the style
            music_path = music_lib.get_music_by_style(
                style=style,
                duration=params.get('duration', 60)
            )

            if music_path:
                return {
                    'success': True,
                    'audio_file': music_path,
                    'style': style,
                    'method': 'music_library',
                    'message': f'Arranged in {style} style using library'
                }
            else:
                return {
                    'success': False,
                    'error': f'No {style} music found in library'
                }

        except Exception as e:
            logger.error(f"      ❌ Music library error: {e}")
            return {'success': False, 'error': str(e)}

    def _arrange_with_ai(self, midi_file: str, style: str, params: Dict) -> Dict:
        """
        Arrange using AI music generation (MusicGen)

        Args:
            midi_file: Input MIDI file
            style: Music style
            params: Additional parameters

        Returns:
            Result with generated audio
        """
        logger.info("      Using AI music generation...")

        try:
            from audiocraft.models import MusicGen
            import torch

            # Load MusicGen model
            model = MusicGen.get_pretrained('facebook/musicgen-small')

            style_info = self.STYLES[style]

            # Generate music description from style
            description = f"{style_info['description']}, tempo {style_info['tempo']} BPM"

            logger.info(f"      Generating: {description}")

            # Generate audio
            model.set_generation_params(duration=params.get('duration', 30))
            wav = model.generate([description])

            # Save output
            output_path = self.output_dir / f"generated_{style}_{Path(midi_file).stem}.wav"

            import torchaudio
            torchaudio.save(str(output_path), wav[0].cpu(), model.sample_rate)

            logger.info(f"      ✅ Generated: {output_path}")

            return {
                'success': True,
                'audio_file': str(output_path),
                'style': style,
                'method': 'ai_generation',
                'message': f'Generated {style} music with AI'
            }

        except Exception as e:
            logger.error(f"      ❌ AI generation error: {e}")
            # Fallback to music library
            return self._arrange_with_music_library(midi_file, style, params)

    def _create_music_from_description(self, params: Dict) -> Dict:
        """
        Create music directly from text description

        Args:
            params: Task parameters with 'topic' or 'description'

        Returns:
            Result with audio file
        """
        logger.info("   📝 Creating music from description...")

        topic = params.get('topic', params.get('description', 'ambient music'))
        style = params.get('style', 'pop')
        duration = params.get('duration', 30)

        logger.info(f"      Topic: {topic}")
        logger.info(f"      Style: {style}")
        logger.info(f"      Duration: {duration}s")

        if not self.music_generator_available:
            # Use music library
            logger.info("      AI not available, using music library...")
            try:
                from modules.music_library import MusicLibrary

                music_lib = MusicLibrary()
                music_path = music_lib.get_music_by_style(style=style, duration=duration)

                if music_path:
                    return {
                        'success': True,
                        'audio_file': music_path,
                        'style': style,
                        'method': 'music_library'
                    }
                else:
                    return {'success': False, 'error': 'No suitable music found'}

            except Exception as e:
                return {'success': False, 'error': str(e)}

        # Use AI generation
        try:
            from audiocraft.models import MusicGen

            model = MusicGen.get_pretrained('facebook/musicgen-small')
            model.set_generation_params(duration=duration)

            # Generate description
            style_info = self.STYLES.get(style, self.STYLES['pop'])
            description = f"{topic}, {style} style, {style_info['description']}"

            logger.info(f"      Generating: {description}")

            wav = model.generate([description])

            # Save
            output_path = self.output_dir / f"music_{style}_{duration}s.wav"

            import torchaudio
            torchaudio.save(str(output_path), wav[0].cpu(), model.sample_rate)

            return {
                'success': True,
                'audio_file': str(output_path),
                'style': style,
                'duration': duration,
                'method': 'ai_generation'
            }

        except Exception as e:
            logger.error(f"      ❌ AI generation failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_available_styles(self) -> Dict:
        """Get list of available music styles"""
        return self.STYLES

    def get_capabilities(self) -> Dict:
        """Get agent capabilities"""
        return {
            'melody_extraction': self.melody_extractor_available,
            'ai_generation': self.music_generator_available,
            'music_library_fallback': True,
            'supported_styles': list(self.STYLES.keys())
        }


# Test
if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎵 MUSIC COMPOSER AGENT TEST")
    print("="*70)

    agent = MusicComposerAgent()

    print(f"\n📊 Agent Capabilities:")
    capabilities = agent.get_capabilities()
    for key, value in capabilities.items():
        if key == 'supported_styles':
            print(f"   {key}: {', '.join(value)}")
        else:
            status = '✅' if value else '❌'
            print(f"   {status} {key}")

    print(f"\n🎹 Available Styles:")
    for style, info in agent.get_available_styles().items():
        print(f"   • {style}: {info['description']} ({info['tempo']} BPM)")

    # Test task execution (mock)
    print(f"\n🧪 Testing task execution...")

    test_task = {
        'task_id': 'test_001',
        'analysis': {
            'task_type': 'music_creation',
            'parameters': {
                'topic': 'Relaxing ambient music',
                'style': 'ambient',
                'duration': 30
            }
        }
    }

    result = agent.execute_task(test_task)
    print(f"   Result: {result['success']}")
    if result['success']:
        print(f"   Audio: {result.get('audio_file', 'N/A')}")
        print(f"   Method: {result.get('method', 'N/A')}")
    else:
        print(f"   Error: {result.get('error', 'Unknown')}")

    print("\n" + "="*70)
    print("✅ MUSIC COMPOSER AGENT TEST COMPLETE")
    print("="*70 + "\n")
