"""
VIDEOCU v1 - Composer Agent
Multi-input music composition from hummed melodies

Features:
- Accept multiple audio inputs (melody, rhythm, samples)
- Time-based layer orchestration (start at 30s, end at 60s)
- Extract melody with Basic Pitch
- Combine layers with pydub overlay
- Project session management via AgentMemory
- Beatbox to instrument transformation
- Raw voice layer support
"""

import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
import json
import numpy as np

logger = logging.getLogger(__name__)


class ComposerAgent:
    """
    Advanced music composition agent with multi-input support

    Capabilities:
    1. Melody extraction (Basic Pitch)
    2. Rhythm extraction (onset detection)
    3. Time-based layer orchestration
    4. AI arrangement (MusicGen/AudioCraft) - optional
    5. Project session management
    """

    # Input types
    INPUT_MELODY = "melody"
    INPUT_RHYTHM = "rhythm"
    INPUT_SAMPLE = "sample"
    INPUT_BACKGROUND = "background"
    INPUT_BEATBOX = "beatbox"      # Beatbox sounds to transform
    INPUT_RAW_VOICE = "raw_voice"  # Raw voice (no transformation)

    # Beatbox sound categories
    BEATBOX_CATEGORIES = {
        'kick': ['boom', 'bum', 'dum', 'dun', 'pum'],
        'snare': ['psh', 'tsh', 'ksh', 'pah', 'tah'],
        'hihat': ['ts', 'tss', 'ch', 'ss', 'tic'],
        'bass': ['hmm', 'brr', 'bzz', 'wub', 'dub'],
        'clap': ['pah', 'clap', 'pak'],
        'cymbal': ['shh', 'sss', 'crash']
    }

    # Sample kits for beatbox transformation
    SAMPLE_KITS = {
        '808': {
            'name': 'TR-808 Kit',
            'description': 'Classic 808 sounds - HipHop/Trap',
            'sounds': {
                'kick': {'freq': 60, 'decay': 0.5, 'punch': 0.8},
                'snare': {'freq': 200, 'noise': 0.6, 'decay': 0.3},
                'hihat': {'freq': 8000, 'decay': 0.1, 'noise': 0.9},
                'bass': {'freq': 40, 'decay': 1.0, 'sub': True},
                'clap': {'freq': 1000, 'decay': 0.2, 'layers': 3}
            }
        },
        '909': {
            'name': 'TR-909 Kit',
            'description': 'Classic 909 sounds - House/Techno',
            'sounds': {
                'kick': {'freq': 80, 'decay': 0.4, 'punch': 0.9},
                'snare': {'freq': 250, 'noise': 0.7, 'decay': 0.25},
                'hihat': {'freq': 10000, 'decay': 0.08, 'noise': 0.95},
                'bass': {'freq': 50, 'decay': 0.8, 'sub': False},
                'clap': {'freq': 1200, 'decay': 0.15, 'layers': 4}
            }
        },
        'acoustic': {
            'name': 'Acoustic Kit',
            'description': 'Natural drum sounds - Pop/Rock',
            'sounds': {
                'kick': {'freq': 100, 'decay': 0.3, 'punch': 0.7},
                'snare': {'freq': 300, 'noise': 0.5, 'decay': 0.2},
                'hihat': {'freq': 12000, 'decay': 0.05, 'noise': 0.8},
                'bass': {'freq': 60, 'decay': 0.6, 'sub': False},
                'clap': {'freq': 800, 'decay': 0.1, 'layers': 1}
            }
        },
        'electronic': {
            'name': 'Electronic Kit',
            'description': 'Modern EDM sounds - Club/Dance',
            'sounds': {
                'kick': {'freq': 55, 'decay': 0.6, 'punch': 1.0},
                'snare': {'freq': 180, 'noise': 0.8, 'decay': 0.35},
                'hihat': {'freq': 9000, 'decay': 0.12, 'noise': 0.85},
                'bass': {'freq': 35, 'decay': 1.2, 'sub': True},
                'clap': {'freq': 1100, 'decay': 0.18, 'layers': 5}
            }
        }
    }

    # Supported styles
    STYLES = {
        'jazz': {'tempo': 120, 'description': 'Smooth jazz with improvisation'},
        'pop': {'tempo': 128, 'description': 'Modern pop with catchy hooks'},
        'club': {'tempo': 130, 'description': 'Electronic dance music'},
        'classical': {'tempo': 100, 'description': 'Classical orchestral arrangement'},
        'ambient': {'tempo': 80, 'description': 'Atmospheric background music'},
        'rock': {'tempo': 140, 'description': 'Energetic rock arrangement'},
        'hiphop': {'tempo': 90, 'description': 'Hip-hop beats and grooves'}
    }

    def __init__(self, memory=None, output_dir: str = "output/compositions"):
        """
        Initialize Composer Agent

        Args:
            memory: AgentMemory instance for project persistence
            output_dir: Directory for output files
        """
        self.memory = memory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create voice inputs directory
        self.voice_dir = self.output_dir / "voice_inputs"
        self.voice_dir.mkdir(parents=True, exist_ok=True)

        # Check available tools
        self.basic_pitch_available = self._check_basic_pitch()
        self.pydub_available = self._check_pydub()
        self.librosa_available = self._check_librosa()
        self.musicgen_available = self._check_musicgen()

        logger.info("🎼 Composer Agent initialized")
        logger.info(f"   Basic Pitch: {'OK' if self.basic_pitch_available else 'N/A'}")
        logger.info(f"   PyDub: {'OK' if self.pydub_available else 'N/A'}")
        logger.info(f"   Librosa: {'OK' if self.librosa_available else 'N/A'}")
        logger.info(f"   MusicGen: {'OK' if self.musicgen_available else 'N/A'}")

    def _check_basic_pitch(self) -> bool:
        try:
            import basic_pitch
            return True
        except ImportError:
            return False

    def _check_pydub(self) -> bool:
        try:
            from pydub import AudioSegment
            # ffmpeg yolunu ayarla (imageio-ffmpeg kullan)
            try:
                import imageio_ffmpeg
                ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
                AudioSegment.converter = ffmpeg_path
                AudioSegment.ffmpeg = ffmpeg_path
                AudioSegment.ffprobe = ffmpeg_path.replace('ffmpeg', 'ffprobe')
                logger.info(f"   ffmpeg path set: {ffmpeg_path}")
            except ImportError:
                logger.warning("   imageio-ffmpeg not found, pydub may not work")
            return True
        except ImportError:
            return False

    def _check_librosa(self) -> bool:
        try:
            import librosa
            return True
        except ImportError:
            return False

    def _check_musicgen(self) -> bool:
        try:
            import audiocraft
            return True
        except ImportError:
            return False

    # ========== Project Management ==========

    def create_project(self, user_id: str, project_name: str,
                      style: str = 'pop') -> Optional[Dict]:
        """
        Create a new music project

        Args:
            user_id: Telegram user ID
            project_name: Project name
            style: Music style

        Returns:
            Project dict or None
        """
        if not self.memory:
            logger.error("No memory system configured")
            return None

        project_id = self.memory.create_music_project(
            user_id=user_id,
            project_name=project_name,
            style=style
        )

        if project_id:
            # Create project directory
            project_dir = self.voice_dir / user_id / project_id
            project_dir.mkdir(parents=True, exist_ok=True)

            return self.memory.get_music_project(project_id)

        return None

    def get_active_project(self, user_id: str) -> Optional[Dict]:
        """Get user's active project"""
        if not self.memory:
            return None
        return self.memory.get_active_project(user_id)

    def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project by ID"""
        if not self.memory:
            return None
        return self.memory.get_music_project(project_id)

    # ========== Audio Input Processing ==========

    def process_audio_input(self, project_id: str, audio_path: str,
                           input_type: str = INPUT_MELODY,
                           start_time: float = 0.0,
                           end_time: float = None,
                           loop_enabled: bool = False) -> Dict:
        """
        Process and add audio input to project

        Args:
            project_id: Project ID
            audio_path: Path to audio file
            input_type: Type of input (melody, rhythm, sample, background)
            start_time: Start time in composition (seconds)
            end_time: End time in composition (seconds)
            loop_enabled: Loop this input

        Returns:
            Processing result
        """
        if not os.path.exists(audio_path):
            return {'success': False, 'error': 'Audio file not found'}

        try:
            result = {
                'success': True,
                'input_type': input_type,
                'audio_path': audio_path,
                'midi_path': None,
                'analysis': {}
            }

            # Extract melody/notes if it's a melodic input
            if input_type == self.INPUT_MELODY and self.basic_pitch_available:
                midi_path = self._extract_melody(audio_path, project_id)
                if midi_path:
                    result['midi_path'] = midi_path
                    result['analysis']['melody_extracted'] = True

            # Analyze rhythm if it's a rhythm input
            elif input_type == self.INPUT_RHYTHM and self.librosa_available:
                rhythm_data = self._analyze_rhythm(audio_path)
                result['analysis']['rhythm'] = rhythm_data

            # Get audio duration
            duration = self._get_audio_duration(audio_path)
            result['analysis']['duration'] = duration

            # Add to database
            if self.memory:
                input_id = self.memory.add_audio_input(
                    project_id=project_id,
                    input_type=input_type,
                    audio_path=audio_path,
                    start_time=start_time,
                    end_time=end_time if end_time else (start_time + duration),
                    loop_enabled=loop_enabled
                )

                if input_id:
                    result['input_id'] = input_id

                    # Update with midi path if extracted
                    if result.get('midi_path'):
                        self.memory.update_audio_input(input_id, {
                            'midi_path': result['midi_path'],
                            'processed': True
                        })

            logger.info(f"   Audio input processed: {input_type} ({duration:.1f}s)")
            return result

        except Exception as e:
            logger.error(f"   Failed to process audio: {e}")
            return {'success': False, 'error': str(e)}

    def _extract_melody(self, audio_path: str, project_id: str) -> Optional[str]:
        """Extract melody using Basic Pitch"""
        try:
            from basic_pitch.inference import predict
            from basic_pitch import ICASSP_2022_MODEL_PATH

            logger.info(f"      Extracting melody from: {Path(audio_path).name}")

            # Predict notes
            model_output, midi_data, note_events = predict(
                audio_path,
                ICASSP_2022_MODEL_PATH
            )

            # Save MIDI
            output_name = f"melody_{Path(audio_path).stem}.mid"
            midi_path = str(self.output_dir / project_id / output_name)

            Path(midi_path).parent.mkdir(parents=True, exist_ok=True)
            midi_data.write(midi_path)

            logger.info(f"      MIDI saved: {midi_path}")
            return midi_path

        except Exception as e:
            logger.warning(f"      Melody extraction failed: {e}")
            return None

    def _analyze_rhythm(self, audio_path: str) -> Dict:
        """Analyze rhythm using librosa onset detection"""
        try:
            import librosa
            import numpy as np

            y, sr = librosa.load(audio_path)

            # Tempo estimation
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)

            # Onset detection
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
            onset_times = librosa.frames_to_time(onset_frames, sr=sr)

            return {
                'tempo': float(tempo),
                'beat_count': len(beat_frames),
                'onset_count': len(onset_times),
                'onset_times': onset_times[:20].tolist() if len(onset_times) > 0 else []
            }

        except Exception as e:
            logger.warning(f"      Rhythm analysis failed: {e}")
            return {}

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio file duration in seconds"""
        try:
            if self.pydub_available:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(audio_path)
                return len(audio) / 1000.0
            elif self.librosa_available:
                import librosa
                y, sr = librosa.load(audio_path)
                return len(y) / sr
            else:
                return 0.0
        except Exception as e:
            logger.warning(f"      Duration check failed: {e}")
            return 0.0

    # ========== Composition ==========

    def compose_project(self, project_id: str) -> Dict:
        """
        Compose final audio from all project inputs

        Args:
            project_id: Project ID

        Returns:
            Composition result with final audio path
        """
        if not self.memory:
            return {'success': False, 'error': 'No memory system'}

        if not self.pydub_available:
            return {'success': False, 'error': 'pydub not available (pip install pydub)'}

        try:
            # Get project
            project = self.memory.get_music_project(project_id)
            if not project:
                return {'success': False, 'error': 'Project not found'}

            # Update status
            self.memory.update_music_project(project_id, {'status': 'composing'})

            # Get all inputs
            inputs = self.memory.get_project_inputs(project_id)
            if not inputs:
                return {'success': False, 'error': 'No inputs in project'}

            logger.info(f"   Composing project: {project['project_name']}")
            logger.info(f"   Inputs: {len(inputs)}")

            # Orchestrate layers
            final_audio = self._orchestrate_layers(inputs)

            if final_audio is None:
                return {'success': False, 'error': 'Layer orchestration failed'}

            # Save final audio
            safe_name = "".join(c for c in project['project_name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            output_filename = f"{safe_name}_{project_id}.mp3"
            output_path = str(self.output_dir / output_filename)

            final_audio.export(output_path, format="mp3", bitrate="192k")

            # Update project with final path
            self.memory.update_music_project(project_id, {
                'status': 'completed',
                'final_audio_path': output_path
            })

            logger.info(f"   Final composition saved: {output_path}")

            return {
                'success': True,
                'project_id': project_id,
                'project_name': project['project_name'],
                'audio_path': output_path,
                'duration': len(final_audio) / 1000.0,
                'layers': len(inputs)
            }

        except Exception as e:
            logger.error(f"   Composition failed: {e}")
            self.memory.update_music_project(project_id, {'status': 'failed'})
            return {'success': False, 'error': str(e)}

    def _orchestrate_layers(self, inputs: List[Dict]) -> Optional[Any]:
        """
        Orchestrate multiple audio layers based on time positions

        Args:
            inputs: List of audio input dictionaries

        Returns:
            Combined AudioSegment or None
        """
        try:
            from pydub import AudioSegment

            # Calculate total duration
            max_end_time = 0
            for inp in inputs:
                end = inp.get('end_time') or (inp.get('start_time', 0) + 30)
                if end > max_end_time:
                    max_end_time = end

            # Create silent base track
            base_duration_ms = int(max_end_time * 1000)
            composition = AudioSegment.silent(duration=base_duration_ms)

            logger.info(f"      Base duration: {max_end_time:.1f}s")

            # Overlay each input at its designated time
            for inp in inputs:
                audio_path = inp.get('audio_path')
                if not audio_path or not os.path.exists(audio_path):
                    logger.warning(f"      Skipping missing audio: {audio_path}")
                    continue

                try:
                    layer = AudioSegment.from_file(audio_path)

                    # Apply volume
                    volume = inp.get('volume', 1.0)
                    if volume != 1.0:
                        layer = layer + (20 * (volume - 1))  # dB adjustment

                    start_ms = int(inp.get('start_time', 0) * 1000)
                    end_ms = int((inp.get('end_time') or max_end_time) * 1000)

                    # Handle looping
                    if inp.get('loop_enabled'):
                        target_duration = end_ms - start_ms
                        while len(layer) < target_duration:
                            layer = layer + layer
                        layer = layer[:target_duration]

                    # Trim if needed
                    available_space = base_duration_ms - start_ms
                    if len(layer) > available_space:
                        layer = layer[:available_space]

                    # Overlay
                    composition = composition.overlay(layer, position=start_ms)

                    logger.info(f"      Added: {inp['input_type']} at {start_ms/1000:.1f}s ({len(layer)/1000:.1f}s)")

                except Exception as e:
                    logger.warning(f"      Failed to add layer: {e}")
                    continue

            return composition

        except Exception as e:
            logger.error(f"      Orchestration error: {e}")
            return None

    # ========== Time-based Layer Management ==========

    def set_layer_timing(self, project_id: str, input_id: str,
                        start_time: float, end_time: float = None) -> bool:
        """
        Set timing for a specific input layer

        Args:
            project_id: Project ID
            input_id: Input ID
            start_time: Start time in seconds
            end_time: End time in seconds (None = until end of composition)

        Returns:
            True if successful
        """
        if not self.memory:
            return False

        updates = {'start_time': start_time}
        if end_time is not None:
            updates['end_time'] = end_time

        return self.memory.update_audio_input(input_id, updates)

    def get_project_timeline(self, project_id: str) -> Dict:
        """
        Get visual timeline of project layers

        Args:
            project_id: Project ID

        Returns:
            Timeline information
        """
        if not self.memory:
            return {'error': 'No memory system'}

        inputs = self.memory.get_project_inputs(project_id)

        if not inputs:
            return {'layers': [], 'total_duration': 0}

        # Calculate total duration
        max_end = 0
        for inp in inputs:
            end = inp.get('end_time') or (inp.get('start_time', 0) + 30)
            if end > max_end:
                max_end = end

        timeline = {
            'layers': [],
            'total_duration': max_end
        }

        for inp in inputs:
            layer = {
                'input_id': inp['input_id'],
                'type': inp['input_type'],
                'name': inp.get('layer_name', inp['input_type']),
                'start': inp.get('start_time', 0),
                'end': inp.get('end_time') or max_end,
                'loop': inp.get('loop_enabled', False),
                'volume': inp.get('volume', 1.0)
            }
            timeline['layers'].append(layer)

        return timeline

    # ========== Beatbox Transformation ==========

    def process_beatbox_input(self, project_id: str, audio_path: str,
                              kit: str = '808',
                              start_time: float = 0.0,
                              end_time: float = None) -> Dict:
        """
        Process beatbox audio and transform to professional sounds

        Args:
            project_id: Project ID
            audio_path: Path to beatbox audio
            kit: Sample kit to use (808, 909, acoustic, electronic)
            start_time: Start time in composition
            end_time: End time in composition

        Returns:
            Processing result with detected sounds and transformed audio
        """
        if not os.path.exists(audio_path):
            return {'success': False, 'error': 'Audio file not found'}

        if not self.librosa_available:
            return {'success': False, 'error': 'librosa required for beatbox processing'}

        if kit not in self.SAMPLE_KITS:
            kit = '808'

        try:
            logger.info(f"   Processing beatbox with {kit} kit")

            # Step 1: Detect onsets and classify sounds
            onset_data = self._detect_beatbox_onsets(audio_path)
            if not onset_data['success']:
                return onset_data

            logger.info(f"      Found {len(onset_data['onsets'])} beats")

            # Step 2: Classify each onset
            classifications = self._classify_beatbox_sounds(
                audio_path,
                onset_data['onsets'],
                onset_data['sr']
            )

            logger.info(f"      Classifications: {classifications['summary']}")

            # Step 3: Generate transformed audio
            transformed_path = self._transform_beatbox_to_kit(
                project_id,
                onset_data['onsets'],
                classifications['events'],
                kit,
                onset_data['sr']
            )

            if not transformed_path:
                return {'success': False, 'error': 'Transformation failed'}

            # Get duration
            duration = self._get_audio_duration(transformed_path)

            # Step 4: Add to project
            if self.memory:
                input_id = self.memory.add_audio_input(
                    project_id=project_id,
                    input_type=self.INPUT_BEATBOX,
                    audio_path=transformed_path,
                    start_time=start_time,
                    end_time=end_time if end_time else (start_time + duration),
                    loop_enabled=False
                )

                # Store original and transformation metadata
                if input_id:
                    self.memory.update_audio_input(input_id, {
                        'processed': True,
                        'layer_name': f'beatbox_{kit}'
                    })

            return {
                'success': True,
                'input_type': self.INPUT_BEATBOX,
                'original_path': audio_path,
                'transformed_path': transformed_path,
                'kit': kit,
                'onset_count': len(onset_data['onsets']),
                'classifications': classifications['summary'],
                'events': classifications['events'],
                'duration': duration,
                'input_id': input_id if self.memory else None
            }

        except Exception as e:
            logger.error(f"   Beatbox processing failed: {e}")
            return {'success': False, 'error': str(e)}

    def _detect_beatbox_onsets(self, audio_path: str) -> Dict:
        """Detect onset times in beatbox audio"""
        try:
            import librosa

            y, sr = librosa.load(audio_path, sr=22050)

            # Get onset envelope with higher sensitivity
            onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)

            # Detect onsets
            onset_frames = librosa.onset.onset_detect(
                onset_envelope=onset_env,
                sr=sr,
                hop_length=512,
                backtrack=True,
                pre_max=3,
                post_max=3,
                pre_avg=3,
                post_avg=5,
                delta=0.1,
                wait=5
            )

            # Convert frames to times
            onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)

            return {
                'success': True,
                'onsets': onset_times.tolist(),
                'sr': sr,
                'duration': len(y) / sr
            }

        except Exception as e:
            logger.error(f"      Onset detection failed: {e}")
            return {'success': False, 'error': str(e)}

    def _classify_beatbox_sounds(self, audio_path: str,
                                  onset_times: List[float],
                                  sr: int) -> Dict:
        """Classify each detected beatbox sound"""
        try:
            import librosa

            y, _ = librosa.load(audio_path, sr=sr)

            events = []
            summary = {'kick': 0, 'snare': 0, 'hihat': 0, 'bass': 0, 'other': 0}

            for i, onset_time in enumerate(onset_times):
                # Extract segment around onset (100ms window)
                start_sample = int(onset_time * sr)
                end_sample = min(start_sample + int(0.1 * sr), len(y))

                if start_sample >= len(y):
                    continue

                segment = y[start_sample:end_sample]

                if len(segment) < 100:
                    continue

                # Analyze segment features
                category = self._classify_segment(segment, sr)

                events.append({
                    'time': onset_time,
                    'category': category,
                    'index': i
                })

                summary[category] = summary.get(category, 0) + 1

            return {
                'success': True,
                'events': events,
                'summary': summary
            }

        except Exception as e:
            logger.error(f"      Sound classification failed: {e}")
            return {'success': False, 'events': [], 'summary': {}}

    def _classify_segment(self, segment: np.ndarray, sr: int) -> str:
        """Classify a single audio segment based on spectral features"""
        try:
            import librosa

            # Get spectral features
            spectral_centroid = librosa.feature.spectral_centroid(y=segment, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=segment, sr=sr)[0]
            zero_crossings = librosa.feature.zero_crossing_rate(segment)[0]

            avg_centroid = np.mean(spectral_centroid)
            avg_rolloff = np.mean(spectral_rolloff)
            avg_zcr = np.mean(zero_crossings)

            # Simple classification based on spectral features
            # Low centroid + low ZCR = kick or bass
            # High centroid + high ZCR = hihat
            # Mid centroid + high ZCR = snare

            if avg_centroid < 1500 and avg_zcr < 0.1:
                # Low frequency, sustained = bass
                if avg_rolloff < 2000:
                    return 'bass'
                else:
                    return 'kick'
            elif avg_centroid > 4000 and avg_zcr > 0.2:
                # High frequency, noisy = hihat
                return 'hihat'
            elif avg_centroid > 2000 and avg_zcr > 0.15:
                # Mid-high frequency, noisy = snare
                return 'snare'
            elif avg_centroid < 2000:
                return 'kick'
            else:
                return 'other'

        except Exception as e:
            logger.warning(f"      Segment classification failed: {e}")
            return 'other'

    def _transform_beatbox_to_kit(self, project_id: str,
                                   onset_times: List[float],
                                   events: List[Dict],
                                   kit: str,
                                   sr: int) -> Optional[str]:
        """Generate transformed audio using synthesized kit sounds"""
        try:
            from pydub import AudioSegment

            kit_config = self.SAMPLE_KITS.get(kit, self.SAMPLE_KITS['808'])

            # Calculate total duration
            if not onset_times:
                return None

            total_duration = max(onset_times) + 0.5  # Add 0.5s padding
            total_duration_ms = int(total_duration * 1000)

            # Create silent base
            composition = AudioSegment.silent(duration=total_duration_ms)

            # Generate and place each sound
            for event in events:
                category = event['category']
                time_ms = int(event['time'] * 1000)

                if category in kit_config['sounds']:
                    sound_config = kit_config['sounds'][category]
                    # Generate synthesized sound
                    sound_segment = self._synthesize_drum_sound(
                        category,
                        sound_config,
                        sr
                    )

                    if sound_segment:
                        # Overlay at correct position
                        composition = composition.overlay(sound_segment, position=time_ms)

            # Save transformed audio
            output_filename = f"beatbox_transformed_{project_id}_{kit}.wav"
            output_path = str(self.output_dir / output_filename)

            composition.export(output_path, format="wav")

            logger.info(f"      Transformed audio saved: {output_filename}")
            return output_path

        except Exception as e:
            logger.error(f"      Beatbox transformation failed: {e}")
            return None

    def _synthesize_drum_sound(self, category: str, config: Dict, sr: int) -> Optional[Any]:
        """Synthesize a drum sound based on category and config"""
        try:
            from pydub import AudioSegment
            from pydub.generators import Sine, WhiteNoise

            freq = config.get('freq', 100)
            decay = config.get('decay', 0.3)
            noise_level = config.get('noise', 0)

            duration_ms = int(decay * 1000)

            if category == 'kick':
                # Kick: sine wave with pitch drop
                sound = Sine(freq).to_audio_segment(duration=duration_ms)
                # Add punch with higher frequency at start
                punch = Sine(freq * 3).to_audio_segment(duration=20)
                sound = punch.append(sound[20:], crossfade=10)
                # Apply fade out
                sound = sound.fade_out(int(duration_ms * 0.8))

            elif category == 'snare':
                # Snare: tone + noise
                tone = Sine(freq).to_audio_segment(duration=duration_ms)
                noise = WhiteNoise().to_audio_segment(duration=duration_ms)
                noise = noise - 12  # Reduce noise volume
                sound = tone.overlay(noise)
                sound = sound.fade_out(int(duration_ms * 0.7))

            elif category == 'hihat':
                # Hi-hat: filtered noise
                sound = WhiteNoise().to_audio_segment(duration=duration_ms)
                sound = sound.high_pass_filter(freq)
                sound = sound.fade_out(int(duration_ms * 0.9))
                sound = sound - 6  # Reduce volume

            elif category == 'bass':
                # Bass: low sine with longer decay
                sound = Sine(freq).to_audio_segment(duration=duration_ms)
                # Add sub harmonic
                if config.get('sub'):
                    sub = Sine(freq / 2).to_audio_segment(duration=duration_ms)
                    sub = sub - 6
                    sound = sound.overlay(sub)
                sound = sound.fade_out(int(duration_ms * 0.6))

            elif category == 'clap':
                # Clap: layered noise bursts
                layers = config.get('layers', 3)
                sound = AudioSegment.silent(duration=duration_ms)
                for i in range(layers):
                    layer = WhiteNoise().to_audio_segment(duration=30)
                    layer = layer.fade_out(25)
                    delay = i * 10
                    sound = sound.overlay(layer, position=delay)
                sound = sound.fade_out(int(duration_ms * 0.5))

            else:
                # Default: short noise burst
                sound = WhiteNoise().to_audio_segment(duration=100)
                sound = sound.fade_out(80)

            return sound

        except Exception as e:
            logger.warning(f"      Sound synthesis failed for {category}: {e}")
            return None

    def add_raw_voice(self, project_id: str, audio_path: str,
                      start_time: float, effect: str = 'none',
                      label: str = None) -> Dict:
        """
        Add raw/unprocessed voice to project

        Args:
            project_id: Project ID
            audio_path: Path to voice audio
            start_time: Start time in composition
            effect: Effect to apply (none, reverb, delay, autotune)
            label: Label for this voice (e.g., "nakarat oncesi hey")

        Returns:
            Processing result
        """
        if not os.path.exists(audio_path):
            return {'success': False, 'error': 'Audio file not found'}

        try:
            # Get duration
            duration = self._get_audio_duration(audio_path)

            # Apply effect if requested
            processed_path = audio_path
            if effect != 'none' and self.pydub_available:
                processed_path = self._apply_voice_effect(
                    audio_path, project_id, effect
                )

            # Add to database
            if self.memory:
                input_id = self.memory.add_audio_input(
                    project_id=project_id,
                    input_type=self.INPUT_RAW_VOICE,
                    audio_path=processed_path,
                    start_time=start_time,
                    end_time=start_time + duration,
                    loop_enabled=False
                )

                if input_id and label:
                    self.memory.update_audio_input(input_id, {
                        'layer_name': label
                    })

            return {
                'success': True,
                'input_type': self.INPUT_RAW_VOICE,
                'audio_path': processed_path,
                'effect': effect,
                'start_time': start_time,
                'duration': duration,
                'label': label,
                'input_id': input_id if self.memory else None
            }

        except Exception as e:
            logger.error(f"   Raw voice processing failed: {e}")
            return {'success': False, 'error': str(e)}

    def _apply_voice_effect(self, audio_path: str, project_id: str,
                            effect: str) -> str:
        """Apply effect to voice audio"""
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(audio_path)

            if effect == 'reverb':
                # Simple reverb simulation with delayed copies
                reverb = audio - 10
                delayed = AudioSegment.silent(duration=50) + reverb
                delayed2 = AudioSegment.silent(duration=100) + (reverb - 15)
                audio = audio.overlay(delayed).overlay(delayed2)

            elif effect == 'delay':
                # Echo effect
                delay = AudioSegment.silent(duration=200) + (audio - 8)
                delay2 = AudioSegment.silent(duration=400) + (audio - 16)
                audio = audio.overlay(delay).overlay(delay2)

            elif effect == 'autotune':
                # Note: Real autotune requires pitch detection/correction
                # This is a placeholder - just applies slight pitch shift
                logger.info("      AutoTune effect (placeholder)")

            # Save processed
            output_filename = f"voice_{effect}_{project_id}.wav"
            output_path = str(self.output_dir / output_filename)
            audio.export(output_path, format="wav")

            return output_path

        except Exception as e:
            logger.warning(f"      Effect application failed: {e}")
            return audio_path

    def get_available_kits(self) -> Dict:
        """Get available sample kits for beatbox transformation"""
        return {
            kit_id: {
                'name': kit['name'],
                'description': kit['description']
            }
            for kit_id, kit in self.SAMPLE_KITS.items()
        }

    # ========== AI Enhancement (Optional) ==========

    def add_ai_arrangement(self, project_id: str, style: str = None) -> Dict:
        """
        Add AI-generated arrangement to project (requires GPU)

        Args:
            project_id: Project ID
            style: Override style (uses project style if None)

        Returns:
            Result with AI-generated audio
        """
        if not self.musicgen_available:
            return {
                'success': False,
                'error': 'MusicGen not available (pip install audiocraft)'
            }

        try:
            from audiocraft.models import MusicGen
            import torchaudio

            project = self.memory.get_music_project(project_id) if self.memory else None
            if not project:
                return {'success': False, 'error': 'Project not found'}

            style = style or project.get('style', 'pop')
            style_info = self.STYLES.get(style, self.STYLES['pop'])

            logger.info(f"   Generating AI arrangement: {style}")

            # Load model
            model = MusicGen.get_pretrained('facebook/musicgen-small')
            model.set_generation_params(duration=30)

            # Generate
            description = f"{style_info['description']}, tempo {style_info['tempo']} BPM"
            wav = model.generate([description])

            # Save
            output_path = str(self.output_dir / f"ai_arrangement_{project_id}.wav")
            torchaudio.save(output_path, wav[0].cpu(), model.sample_rate)

            # Add as background layer
            if self.memory:
                self.memory.add_audio_input(
                    project_id=project_id,
                    input_type=self.INPUT_BACKGROUND,
                    audio_path=output_path,
                    start_time=0,
                    volume=0.6  # Lower volume for background
                )

            return {
                'success': True,
                'audio_path': output_path,
                'style': style,
                'duration': 30
            }

        except Exception as e:
            logger.error(f"   AI arrangement failed: {e}")
            return {'success': False, 'error': str(e)}

    # ========== Utilities ==========

    def get_capabilities(self) -> Dict:
        """Get agent capabilities"""
        return {
            'melody_extraction': self.basic_pitch_available,
            'audio_mixing': self.pydub_available,
            'rhythm_analysis': self.librosa_available,
            'ai_arrangement': self.musicgen_available,
            'beatbox_transformation': self.librosa_available and self.pydub_available,
            'supported_styles': list(self.STYLES.keys()),
            'available_kits': list(self.SAMPLE_KITS.keys()),
            'input_types': [
                self.INPUT_MELODY,
                self.INPUT_RHYTHM,
                self.INPUT_SAMPLE,
                self.INPUT_BACKGROUND,
                self.INPUT_BEATBOX,
                self.INPUT_RAW_VOICE
            ]
        }

    def get_project_summary(self, project_id: str) -> Dict:
        """Get comprehensive project summary"""
        if not self.memory:
            return {'error': 'No memory system'}

        project = self.memory.get_music_project(project_id)
        if not project:
            return {'error': 'Project not found'}

        inputs = self.memory.get_project_inputs(project_id)
        timeline = self.get_project_timeline(project_id)

        return {
            'project': project,
            'input_count': len(inputs),
            'inputs': inputs,
            'timeline': timeline,
            'ready_to_compose': len(inputs) > 0 and project['status'] == 'draft'
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
    print("COMPOSER AGENT TEST")
    print("="*70)

    # Test without memory
    agent = ComposerAgent()

    print(f"\nCapabilities:")
    caps = agent.get_capabilities()
    for key, value in caps.items():
        if isinstance(value, list):
            print(f"   {key}: {', '.join(value)}")
        else:
            status = 'OK' if value else 'N/A'
            print(f"   {key}: {status}")

    print(f"\nSupported Styles:")
    for style, info in agent.STYLES.items():
        print(f"   {style}: {info['description']} ({info['tempo']} BPM)")

    print("\n" + "="*70)
    print("COMPOSER AGENT TEST COMPLETE")
    print("="*70 + "\n")
