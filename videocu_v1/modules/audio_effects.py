"""
VIDEOCU v1 - Audio Effects Processor
Ham seslere elektronik efektler uygulama

Efekt Kategorileri:
- Distortion (Overdrive, Bitcrusher, Fuzz)
- Modulation (Chorus, Flanger, Phaser)
- Filter (Low-pass, High-pass, Band-pass)
- Spatial (Reverb, Delay, Echo)
- Dynamics (Compressor, Limiter)
- Pitch/Time (Speed, Pitch Shift)
"""

import numpy as np
from typing import Tuple, Optional, Dict, Any
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioEffectsProcessor:
    """
    Ham seslere elektronik efektler uygula

    Kullanim:
        processor = AudioEffectsProcessor()
        audio, sr = processor.load_audio("input.wav")
        audio = processor.apply_distortion(audio, sr, drive=0.5)
        audio = processor.apply_reverb(audio, sr, room_size=0.5)
        processor.save_audio(audio, sr, "output.wav")
    """

    # Efekt presetleri
    PRESETS = {
        'club': {
            'name': 'Club',
            'description': 'High energy dance sound',
            'effects': [
                ('highpass', {'cutoff': 80}),
                ('compressor', {'threshold': -20, 'ratio': 4}),
                ('bass_boost', {'gain': 6}),
                ('reverb', {'room_size': 0.3, 'damping': 0.5}),
            ]
        },
        'lofi': {
            'name': 'Lo-Fi',
            'description': 'Vintage, warm sound',
            'effects': [
                ('bitcrusher', {'bits': 12, 'sample_rate': 22050}),
                ('lowpass', {'cutoff': 8000}),
                ('vinyl_crackle', {'intensity': 0.3}),
                ('reverb', {'room_size': 0.4, 'damping': 0.7}),
            ]
        },
        '8bit': {
            'name': '8-Bit',
            'description': 'Retro chiptune sound',
            'effects': [
                ('bitcrusher', {'bits': 4, 'sample_rate': 8000}),
                ('lowpass', {'cutoff': 4000}),
            ]
        },
        'ambient': {
            'name': 'Ambient',
            'description': 'Atmospheric, spacey sound',
            'effects': [
                ('lowpass', {'cutoff': 6000}),
                ('reverb', {'room_size': 0.9, 'damping': 0.3}),
                ('delay', {'delay_ms': 400, 'feedback': 0.5}),
            ]
        },
        'trap': {
            'name': 'Trap',
            'description': 'Hard-hitting trap style',
            'effects': [
                ('highpass', {'cutoff': 30}),
                ('bass_boost', {'gain': 10}),
                ('compressor', {'threshold': -15, 'ratio': 6}),
                ('distortion', {'drive': 0.2}),
            ]
        },
        'rock': {
            'name': 'Rock',
            'description': 'Classic rock sound',
            'effects': [
                ('overdrive', {'gain': 0.5}),
                ('eq_mid_boost', {'gain': 4}),
                ('reverb', {'room_size': 0.5, 'damping': 0.4}),
            ]
        },
        'dreamy': {
            'name': 'Dreamy',
            'description': 'Ethereal, floating sound',
            'effects': [
                ('chorus', {'rate': 0.5, 'depth': 0.6}),
                ('reverb', {'room_size': 0.8, 'damping': 0.2}),
                ('delay', {'delay_ms': 300, 'feedback': 0.4}),
                ('lowpass', {'cutoff': 10000}),
            ]
        }
    }

    def __init__(self):
        self.sample_rate = 44100  # Default sample rate
        logger.info("AudioEffectsProcessor initialized")

    # ==================== I/O METHODS ====================

    def load_audio(self, file_path: str) -> Tuple[np.ndarray, int]:
        """
        Ses dosyasini yukle (M4A, MP3, WAV, vb. destekler)

        Returns:
            Tuple[audio_data, sample_rate]
        """
        import os
        import tempfile

        # Check file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        actual_path = file_path
        temp_wav = None

        # Convert non-WAV formats to WAV first (scipy/soundfile doesn't support M4A/AAC)
        if file_ext in ['.m4a', '.mp3', '.ogg', '.flac', '.aac', '.wma']:
            try:
                from pydub import AudioSegment
                logger.info(f"Converting {file_ext} to WAV for processing...")
                audio_segment = AudioSegment.from_file(file_path)
                temp_wav = os.path.join(tempfile.mkdtemp(), "temp_audio.wav")
                audio_segment.export(temp_wav, format="wav")
                actual_path = temp_wav
                logger.info(f"Converted to: {temp_wav}")
            except Exception as conv_err:
                logger.warning(f"Pydub conversion failed: {conv_err}")
                raise ValueError(f"Format donusturme hatasi: {conv_err}. FFmpeg yuklu oldugundan emin olun.")

        try:
            # Try soundfile first (no numba dependency)
            import soundfile as sf
            audio, sr = sf.read(actual_path)
            if len(audio.shape) > 1:
                audio = np.mean(audio, axis=1)  # Stereo to mono
            self.sample_rate = sr
            logger.info(f"Loaded audio: {file_path} (sr={sr}, len={len(audio)/sr:.2f}s)")
            return audio.astype(np.float32), sr
        except ImportError:
            pass
        except Exception as sf_err:
            logger.warning(f"Soundfile error: {sf_err}")

        # Fallback to scipy.wavfile (WAV only)
        try:
            from scipy.io import wavfile
            sr, audio = wavfile.read(actual_path)
            if audio.dtype == np.int16:
                audio = audio.astype(np.float32) / 32768.0
            elif audio.dtype == np.int32:
                audio = audio.astype(np.float32) / 2147483648.0
            if len(audio.shape) > 1:
                audio = np.mean(audio, axis=1)
            self.sample_rate = sr
            logger.info(f"Loaded audio with scipy: {file_path} (sr={sr})")
            return audio, sr
        except Exception as wav_err:
            raise ValueError(f"Ses dosyasi yuklenemedi: {wav_err}")

    def save_audio(self, audio: np.ndarray, sr: int, file_path: str) -> str:
        """Ses dosyasini kaydet"""
        try:
            import soundfile as sf
            # Normalize
            audio = self._normalize(audio)
            sf.write(file_path, audio, sr)
            logger.info(f"Saved audio: {file_path}")
            return file_path
        except ImportError:
            from scipy.io import wavfile
            audio = self._normalize(audio)
            audio_int = (audio * 32767).astype(np.int16)
            wavfile.write(file_path, sr, audio_int)
            return file_path

    def _normalize(self, audio: np.ndarray, target_db: float = -3.0) -> np.ndarray:
        """Ses seviyesini normalize et"""
        peak = np.max(np.abs(audio))
        if peak > 0:
            target_peak = 10 ** (target_db / 20)
            audio = audio * (target_peak / peak)
        return np.clip(audio, -1.0, 1.0)

    # ==================== DISTORTION EFFECTS ====================

    def apply_distortion(self, audio: np.ndarray, sr: int, drive: float = 0.5) -> np.ndarray:
        """
        Soft clipping distortion

        Args:
            drive: 0.0-1.0, distortion miktari
        """
        gain = 1 + drive * 10
        audio = audio * gain
        # Soft clipping with tanh
        audio = np.tanh(audio)
        return self._normalize(audio)

    def apply_overdrive(self, audio: np.ndarray, sr: int, gain: float = 0.5) -> np.ndarray:
        """
        Tube-style overdrive
        """
        gain_factor = 1 + gain * 5
        audio = audio * gain_factor
        # Asymmetric soft clipping (tube karakteri)
        positive = np.where(audio > 0, np.tanh(audio), 0)
        negative = np.where(audio < 0, np.tanh(audio * 0.8), 0)
        audio = positive + negative
        return self._normalize(audio)

    def apply_bitcrusher(self, audio: np.ndarray, sr: int,
                         bits: int = 8, sample_rate: int = 8000) -> np.ndarray:
        """
        Bit depth ve sample rate dusurme (retro sound)

        Args:
            bits: Bit depth (1-16)
            sample_rate: Target sample rate
        """
        # Bit crushing
        levels = 2 ** bits
        audio = np.round(audio * levels) / levels

        # Sample rate reduction (downsampling)
        if sample_rate < sr:
            ratio = sr // sample_rate
            # Downsample
            audio = audio[::ratio]
            # Upsample back (hold)
            audio = np.repeat(audio, ratio)

        return audio

    def apply_fuzz(self, audio: np.ndarray, sr: int, intensity: float = 0.7) -> np.ndarray:
        """Agresif fuzz distortion"""
        gain = 1 + intensity * 20
        audio = audio * gain
        # Hard clipping
        audio = np.clip(audio, -0.8, 0.8)
        # Add harmonics
        audio = audio + 0.3 * np.sign(audio) * audio ** 2
        return self._normalize(audio)

    # ==================== MODULATION EFFECTS ====================

    def apply_chorus(self, audio: np.ndarray, sr: int,
                     rate: float = 1.0, depth: float = 0.5) -> np.ndarray:
        """
        Chorus efekti - ses kalinlastirma

        Args:
            rate: LFO rate (Hz)
            depth: Modulation depth (0-1)
        """
        n_samples = len(audio)
        t = np.arange(n_samples) / sr

        # LFO for delay modulation
        lfo = np.sin(2 * np.pi * rate * t) * depth * 0.003 * sr  # Max 3ms variation

        # Base delay (20ms)
        base_delay = int(0.02 * sr)

        # Create delayed signal with modulation
        output = np.zeros_like(audio)
        for i in range(n_samples):
            delay = int(base_delay + lfo[i])
            if i - delay >= 0:
                output[i] = audio[i] * 0.7 + audio[i - delay] * 0.3
            else:
                output[i] = audio[i]

        return self._normalize(output)

    def apply_flanger(self, audio: np.ndarray, sr: int,
                      rate: float = 0.5, depth: float = 0.7) -> np.ndarray:
        """Flanger efekti - jet engine sound"""
        n_samples = len(audio)
        t = np.arange(n_samples) / sr

        # LFO (slower, deeper than chorus)
        lfo = (np.sin(2 * np.pi * rate * t) + 1) / 2  # 0-1 range

        # Variable delay 0-10ms
        max_delay = int(0.01 * sr)

        output = np.zeros_like(audio)
        for i in range(n_samples):
            delay = int(lfo[i] * max_delay * depth)
            if i - delay >= 0:
                output[i] = audio[i] + audio[i - delay] * 0.7
            else:
                output[i] = audio[i]

        return self._normalize(output)

    def apply_phaser(self, audio: np.ndarray, sr: int,
                     rate: float = 0.3, depth: float = 0.6) -> np.ndarray:
        """Phaser efekti - sweeping filter"""
        n_samples = len(audio)
        t = np.arange(n_samples) / sr

        # LFO
        lfo = np.sin(2 * np.pi * rate * t)

        # Allpass filter simulation
        output = np.zeros_like(audio)
        prev = 0
        for i in range(n_samples):
            # Variable coefficient based on LFO
            coeff = 0.7 + lfo[i] * depth * 0.3
            output[i] = coeff * audio[i] + prev - coeff * (output[i-1] if i > 0 else 0)
            prev = audio[i]

        # Mix dry/wet
        output = audio * 0.5 + output * 0.5
        return self._normalize(output)

    def apply_tremolo(self, audio: np.ndarray, sr: int,
                      rate: float = 5.0, depth: float = 0.5) -> np.ndarray:
        """Tremolo - volume modulation"""
        n_samples = len(audio)
        t = np.arange(n_samples) / sr

        # LFO for amplitude
        lfo = 1 - depth * (np.sin(2 * np.pi * rate * t) + 1) / 2

        return audio * lfo

    # ==================== FILTER EFFECTS ====================

    def apply_lowpass(self, audio: np.ndarray, sr: int, cutoff: int = 2000) -> np.ndarray:
        """Low-pass filter - yuksek frekanslari kes"""
        from scipy.signal import butter, filtfilt

        nyquist = sr / 2
        normalized_cutoff = min(cutoff / nyquist, 0.99)
        b, a = butter(4, normalized_cutoff, btype='low')
        return filtfilt(b, a, audio)

    def apply_highpass(self, audio: np.ndarray, sr: int, cutoff: int = 200) -> np.ndarray:
        """High-pass filter - dusuk frekanslari kes"""
        from scipy.signal import butter, filtfilt

        nyquist = sr / 2
        normalized_cutoff = max(cutoff / nyquist, 0.01)
        b, a = butter(4, normalized_cutoff, btype='high')
        return filtfilt(b, a, audio)

    def apply_bandpass(self, audio: np.ndarray, sr: int,
                       low: int = 300, high: int = 3000) -> np.ndarray:
        """Band-pass filter"""
        from scipy.signal import butter, filtfilt

        nyquist = sr / 2
        low_norm = max(low / nyquist, 0.01)
        high_norm = min(high / nyquist, 0.99)
        b, a = butter(4, [low_norm, high_norm], btype='band')
        return filtfilt(b, a, audio)

    def apply_bass_boost(self, audio: np.ndarray, sr: int, gain: float = 6) -> np.ndarray:
        """Bass boost - dusuk frekanslari guclendir"""
        from scipy.signal import butter, filtfilt

        nyquist = sr / 2
        cutoff = min(200 / nyquist, 0.99)
        b, a = butter(2, cutoff, btype='low')
        bass = filtfilt(b, a, audio)

        # Boost bass
        boost_factor = 10 ** (gain / 20)
        return audio + bass * (boost_factor - 1)

    def apply_eq_mid_boost(self, audio: np.ndarray, sr: int, gain: float = 4) -> np.ndarray:
        """Mid frequencies boost (presence)"""
        from scipy.signal import butter, filtfilt

        nyquist = sr / 2
        low_norm = max(500 / nyquist, 0.01)
        high_norm = min(4000 / nyquist, 0.99)
        b, a = butter(2, [low_norm, high_norm], btype='band')
        mids = filtfilt(b, a, audio)

        boost_factor = 10 ** (gain / 20)
        return audio + mids * (boost_factor - 1)

    # ==================== SPATIAL EFFECTS ====================

    def apply_reverb(self, audio: np.ndarray, sr: int,
                     room_size: float = 0.5, damping: float = 0.5) -> np.ndarray:
        """
        Simple reverb (comb filter based)

        Args:
            room_size: 0-1, buyuk deger = uzun reverb
            damping: 0-1, yuksek frekans absorpsiyonu
        """
        # Delay times for comb filters (in samples)
        base_delays = [1557, 1617, 1491, 1422, 1277, 1356]
        delays = [int(d * room_size * 1.5) for d in base_delays]

        output = np.zeros(len(audio) + max(delays))

        # Apply comb filters
        for delay in delays:
            feedback = 0.7 * (1 - damping * 0.5)
            comb_output = np.zeros_like(output)
            for i in range(len(audio)):
                comb_output[i + delay] = audio[i] + comb_output[i] * feedback if i < len(comb_output) else 0
            output += comb_output / len(delays)

        # Trim and mix
        output = output[:len(audio)]
        wet_mix = 0.3 + room_size * 0.4
        output = audio * (1 - wet_mix) + output * wet_mix

        return self._normalize(output)

    def apply_delay(self, audio: np.ndarray, sr: int,
                    delay_ms: int = 250, feedback: float = 0.3) -> np.ndarray:
        """
        Echo/Delay efekti

        Args:
            delay_ms: Gecikme suresi (ms)
            feedback: 0-1, tekrar sayisi
        """
        delay_samples = int(delay_ms * sr / 1000)

        # Create output with extra length for delays
        n_repeats = 5
        output = np.zeros(len(audio) + delay_samples * n_repeats)
        output[:len(audio)] = audio

        # Apply feedback delays
        current_gain = feedback
        for i in range(1, n_repeats + 1):
            offset = delay_samples * i
            if offset < len(output):
                end = min(offset + len(audio), len(output))
                output[offset:end] += audio[:end-offset] * current_gain
            current_gain *= feedback

        # Trim to original length
        output = output[:len(audio)]
        return self._normalize(output)

    def apply_echo(self, audio: np.ndarray, sr: int,
                   delay_ms: int = 300, decay: float = 0.5) -> np.ndarray:
        """Simple echo (single repeat)"""
        delay_samples = int(delay_ms * sr / 1000)
        output = np.zeros(len(audio) + delay_samples)
        output[:len(audio)] = audio
        output[delay_samples:delay_samples + len(audio)] += audio * decay
        return self._normalize(output[:len(audio)])

    # ==================== DYNAMICS EFFECTS ====================

    def apply_compressor(self, audio: np.ndarray, sr: int,
                         threshold: float = -20, ratio: float = 4) -> np.ndarray:
        """
        Dynamic range compressor

        Args:
            threshold: dB threshold
            ratio: Compression ratio (4:1 = 4)
        """
        threshold_linear = 10 ** (threshold / 20)

        output = np.zeros_like(audio)
        envelope = 0

        # Attack/release times
        attack = 0.01  # 10ms
        release = 0.1  # 100ms

        attack_coef = np.exp(-1 / (sr * attack))
        release_coef = np.exp(-1 / (sr * release))

        for i in range(len(audio)):
            input_level = np.abs(audio[i])

            # Envelope follower
            if input_level > envelope:
                envelope = attack_coef * envelope + (1 - attack_coef) * input_level
            else:
                envelope = release_coef * envelope + (1 - release_coef) * input_level

            # Gain reduction
            if envelope > threshold_linear:
                gain_reduction = threshold_linear + (envelope - threshold_linear) / ratio
                gain = gain_reduction / envelope if envelope > 0 else 1
            else:
                gain = 1

            output[i] = audio[i] * gain

        return self._normalize(output)

    def apply_limiter(self, audio: np.ndarray, sr: int,
                      threshold: float = -3) -> np.ndarray:
        """Hard limiter - max level sinirla"""
        threshold_linear = 10 ** (threshold / 20)
        return np.clip(audio, -threshold_linear, threshold_linear)

    # ==================== PITCH/TIME EFFECTS ====================

    def apply_speed_change(self, audio: np.ndarray, sr: int,
                           speed: float = 1.0) -> Tuple[np.ndarray, int]:
        """
        Hiz degistir (pitch de degisir)

        Args:
            speed: 0.5 = yarim hiz, 2.0 = iki kat hiz

        Returns:
            (audio, new_sample_rate)
        """
        try:
            import librosa
            # Pitch koruyarak tempo degistir
            audio = librosa.effects.time_stretch(audio, rate=speed)
            return audio, sr
        except ImportError:
            # Simple resampling (pitch also changes)
            from scipy import signal
            new_length = int(len(audio) / speed)
            audio = signal.resample(audio, new_length)
            return audio, sr

    def apply_pitch_shift(self, audio: np.ndarray, sr: int,
                          semitones: float = 0) -> np.ndarray:
        """
        Pitch shift (hiz koruyarak)

        Args:
            semitones: Yari ton sayisi (+12 = bir oktav yukari)
        """
        try:
            import librosa
            return librosa.effects.pitch_shift(audio, sr=sr, n_steps=semitones)
        except ImportError:
            # Fallback: simple resampling (hiz degisir)
            factor = 2 ** (semitones / 12)
            from scipy import signal
            new_length = int(len(audio) / factor)
            audio = signal.resample(audio, new_length)
            # Resample back to original length
            audio = signal.resample(audio, int(len(audio) * factor))
            return audio

    # ==================== SPECIAL EFFECTS ====================

    def apply_vinyl_crackle(self, audio: np.ndarray, sr: int,
                            intensity: float = 0.3) -> np.ndarray:
        """Vinil plak cizirti sesi ekle"""
        # Generate crackle noise
        noise = np.random.randn(len(audio)) * 0.01 * intensity

        # Random pops
        n_pops = int(len(audio) * 0.001 * intensity)
        pop_positions = np.random.randint(0, len(audio), n_pops)
        for pos in pop_positions:
            noise[pos] = np.random.uniform(0.05, 0.1) * intensity

        # Low-pass filter the noise
        from scipy.signal import butter, filtfilt
        nyquist = sr / 2
        b, a = butter(2, min(3000 / nyquist, 0.99), btype='low')
        noise = filtfilt(b, a, noise)

        return audio + noise

    def apply_telephone(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Telefon sesi efekti (band-limited)"""
        return self.apply_bandpass(audio, sr, low=300, high=3400)

    def apply_radio(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """AM Radio sesi efekti"""
        audio = self.apply_bandpass(audio, sr, low=200, high=5000)
        audio = self.apply_bitcrusher(audio, sr, bits=10, sample_rate=16000)
        return audio

    # ==================== PRESET APPLICATION ====================

    def apply_preset(self, audio: np.ndarray, sr: int, preset_name: str) -> np.ndarray:
        """
        Preset uygula

        Args:
            preset_name: 'club', 'lofi', '8bit', 'ambient', 'trap', 'rock', 'dreamy'
        """
        if preset_name not in self.PRESETS:
            logger.warning(f"Unknown preset: {preset_name}")
            return audio

        preset = self.PRESETS[preset_name]
        logger.info(f"Applying preset: {preset['name']} - {preset['description']}")

        for effect_name, params in preset['effects']:
            method_name = f"apply_{effect_name}"
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                audio = method(audio, sr, **params)
                logger.debug(f"  Applied {effect_name} with {params}")
            else:
                logger.warning(f"  Unknown effect: {effect_name}")

        return self._normalize(audio)

    def get_available_presets(self) -> Dict[str, Dict[str, Any]]:
        """Mevcut presetleri getir"""
        return {
            name: {'name': p['name'], 'description': p['description']}
            for name, p in self.PRESETS.items()
        }

    def get_available_effects(self) -> list:
        """Mevcut efektlerin listesi"""
        return [
            # Distortion
            {'name': 'distortion', 'category': 'Distortion', 'params': ['drive']},
            {'name': 'overdrive', 'category': 'Distortion', 'params': ['gain']},
            {'name': 'bitcrusher', 'category': 'Distortion', 'params': ['bits', 'sample_rate']},
            {'name': 'fuzz', 'category': 'Distortion', 'params': ['intensity']},
            # Modulation
            {'name': 'chorus', 'category': 'Modulation', 'params': ['rate', 'depth']},
            {'name': 'flanger', 'category': 'Modulation', 'params': ['rate', 'depth']},
            {'name': 'phaser', 'category': 'Modulation', 'params': ['rate', 'depth']},
            {'name': 'tremolo', 'category': 'Modulation', 'params': ['rate', 'depth']},
            # Filter
            {'name': 'lowpass', 'category': 'Filter', 'params': ['cutoff']},
            {'name': 'highpass', 'category': 'Filter', 'params': ['cutoff']},
            {'name': 'bandpass', 'category': 'Filter', 'params': ['low', 'high']},
            {'name': 'bass_boost', 'category': 'Filter', 'params': ['gain']},
            # Spatial
            {'name': 'reverb', 'category': 'Spatial', 'params': ['room_size', 'damping']},
            {'name': 'delay', 'category': 'Spatial', 'params': ['delay_ms', 'feedback']},
            {'name': 'echo', 'category': 'Spatial', 'params': ['delay_ms', 'decay']},
            # Dynamics
            {'name': 'compressor', 'category': 'Dynamics', 'params': ['threshold', 'ratio']},
            {'name': 'limiter', 'category': 'Dynamics', 'params': ['threshold']},
            # Special
            {'name': 'vinyl_crackle', 'category': 'Special', 'params': ['intensity']},
            {'name': 'telephone', 'category': 'Special', 'params': []},
            {'name': 'radio', 'category': 'Special', 'params': []},
        ]


    # ==================== DRUM SYNTHESIS ====================

    def synthesize_808_kick(self, sr: int, duration: float = 0.5) -> np.ndarray:
        """808 style kick drum - deep sub bass"""
        t = np.linspace(0, duration, int(sr * duration))

        # Pitch envelope: starts at ~150Hz, drops to ~40Hz
        freq_start = 150
        freq_end = 40
        freq_decay = 0.1
        freq = freq_end + (freq_start - freq_end) * np.exp(-t / freq_decay)

        # Generate sine wave with pitch envelope
        phase = 2 * np.pi * np.cumsum(freq) / sr
        kick = np.sin(phase)

        # Amplitude envelope
        amp_decay = 0.3
        amp = np.exp(-t / amp_decay)

        # Add click at start
        click_duration = 0.005
        click_samples = int(sr * click_duration)
        click = np.random.randn(click_samples) * 0.3
        click *= np.exp(-np.linspace(0, 5, click_samples))

        kick = kick * amp
        kick[:click_samples] += click

        return self._normalize(kick)

    def synthesize_808_snare(self, sr: int, duration: float = 0.3) -> np.ndarray:
        """808 style snare - punchy with noise"""
        t = np.linspace(0, duration, int(sr * duration))

        # Body (pitched component)
        body_freq = 180
        body = np.sin(2 * np.pi * body_freq * t)
        body *= np.exp(-t / 0.1)

        # Noise component
        noise = np.random.randn(len(t))
        noise *= np.exp(-t / 0.15)

        # High-pass the noise
        from scipy.signal import butter, filtfilt
        nyq = sr / 2
        b, a = butter(2, min(1000 / nyq, 0.99), btype='high')
        noise = filtfilt(b, a, noise)

        snare = body * 0.5 + noise * 0.5
        return self._normalize(snare)

    def synthesize_808_hihat(self, sr: int, duration: float = 0.1, open_hat: bool = False) -> np.ndarray:
        """808 style hi-hat - metallic noise"""
        dur = duration * 3 if open_hat else duration
        t = np.linspace(0, dur, int(sr * dur))

        # Generate metallic noise (multiple high frequencies)
        freqs = [800, 1200, 3000, 6000, 8000, 12000]
        hihat = np.zeros_like(t)
        for f in freqs:
            if f < sr / 2:  # Nyquist check
                hihat += np.sin(2 * np.pi * f * t + np.random.random() * 2 * np.pi) * 0.2

        # Add noise
        noise = np.random.randn(len(t)) * 0.6
        hihat += noise

        # High-pass filter
        from scipy.signal import butter, filtfilt
        nyq = sr / 2
        b, a = butter(2, min(6000 / nyq, 0.99), btype='high')
        hihat = filtfilt(b, a, hihat)

        # Envelope
        decay = 0.2 if open_hat else 0.03
        hihat *= np.exp(-t / decay)

        return self._normalize(hihat) * 0.7

    def synthesize_909_kick(self, sr: int, duration: float = 0.4) -> np.ndarray:
        """909 style kick - punchy with more attack"""
        t = np.linspace(0, duration, int(sr * duration))

        # Pitch envelope (faster than 808)
        freq_start = 200
        freq_end = 50
        freq = freq_end + (freq_start - freq_end) * np.exp(-t / 0.05)

        phase = 2 * np.pi * np.cumsum(freq) / sr
        kick = np.sin(phase)

        # Shorter, punchier envelope
        kick *= np.exp(-t / 0.15)

        # Stronger click
        click_samples = int(sr * 0.01)
        click = np.random.randn(click_samples) * 0.5
        click *= np.exp(-np.linspace(0, 8, click_samples))
        kick[:click_samples] += click

        return self._normalize(kick)

    def synthesize_909_snare(self, sr: int, duration: float = 0.25) -> np.ndarray:
        """909 style snare - snappy, tight"""
        t = np.linspace(0, duration, int(sr * duration))

        # Two pitched components
        body1 = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.05)
        body2 = np.sin(2 * np.pi * 330 * t) * np.exp(-t / 0.08)

        # Tight noise
        noise = np.random.randn(len(t))
        noise *= np.exp(-t / 0.1)

        from scipy.signal import butter, filtfilt
        nyq = sr / 2
        b, a = butter(2, [min(500 / nyq, 0.99), min(8000 / nyq, 0.99)], btype='band')
        noise = filtfilt(b, a, noise)

        snare = body1 * 0.3 + body2 * 0.2 + noise * 0.5
        return self._normalize(snare)

    def detect_onsets(self, audio: np.ndarray, sr: int, threshold: float = 0.3) -> list:
        """Detect onset times in audio (beat positions)"""
        from scipy.signal import find_peaks

        # Calculate envelope
        hop_length = 512
        n_fft = 2048

        # Simple energy-based onset detection
        num_frames = (len(audio) - n_fft) // hop_length + 1
        onset_env = np.zeros(num_frames)

        for i in range(num_frames):
            start = i * hop_length
            frame = audio[start:start + n_fft]
            if len(frame) < n_fft:
                frame = np.pad(frame, (0, n_fft - len(frame)))

            # Spectral flux
            spectrum = np.abs(np.fft.rfft(frame * np.hanning(n_fft)))
            onset_env[i] = np.sum(spectrum)

        # Normalize
        onset_env = (onset_env - np.min(onset_env)) / (np.max(onset_env) - np.min(onset_env) + 1e-6)

        # Find peaks
        peaks, properties = find_peaks(onset_env, height=threshold, distance=5)

        # Convert to time
        onset_times = (peaks * hop_length / sr).tolist()

        # Get strengths for classification
        onset_strengths = properties['peak_heights'].tolist() if 'peak_heights' in properties else [1.0] * len(peaks)

        return list(zip(onset_times, onset_strengths))

    def classify_onset(self, audio: np.ndarray, sr: int, onset_time: float, window_ms: float = 50) -> str:
        """Classify an onset as kick, snare, or hihat based on frequency content"""
        from scipy.signal import butter, filtfilt

        start_sample = int(onset_time * sr)
        window_samples = int(window_ms * sr / 1000)
        end_sample = min(start_sample + window_samples, len(audio))

        if start_sample >= len(audio):
            return 'hihat'

        segment = audio[start_sample:end_sample]
        if len(segment) < 100:
            return 'hihat'

        # Calculate energy in different frequency bands
        nyq = sr / 2

        # Low band (kick): 20-150 Hz
        try:
            b, a = butter(2, [max(20 / nyq, 0.01), min(150 / nyq, 0.99)], btype='band')
            low_energy = np.mean(np.abs(filtfilt(b, a, segment)))
        except:
            low_energy = 0

        # Mid band (snare): 150-1000 Hz
        try:
            b, a = butter(2, [min(150 / nyq, 0.99), min(1000 / nyq, 0.99)], btype='band')
            mid_energy = np.mean(np.abs(filtfilt(b, a, segment)))
        except:
            mid_energy = 0

        # High band (hihat): 3000+ Hz
        try:
            b, a = butter(2, min(3000 / nyq, 0.99), btype='high')
            high_energy = np.mean(np.abs(filtfilt(b, a, segment)))
        except:
            high_energy = 0

        # Classify
        total = low_energy + mid_energy + high_energy + 1e-6
        low_ratio = low_energy / total
        mid_ratio = mid_energy / total
        high_ratio = high_energy / total

        if low_ratio > 0.4:
            return 'kick'
        elif high_ratio > 0.35:
            return 'hihat'
        else:
            return 'snare'

    def transform_to_drumkit(self, audio: np.ndarray, sr: int, kit: str = '808') -> np.ndarray:
        """
        Transform audio to drum kit by detecting beats and replacing with synth drums

        Args:
            kit: '808', '909', 'acoustic', 'electronic'

        Returns:
            Transformed audio with synthesized drums
        """
        logger.info(f"🥁 Transforming audio to {kit} drum kit...")

        # Detect onsets
        onsets = self.detect_onsets(audio, sr, threshold=0.25)
        logger.info(f"   Found {len(onsets)} beats")

        if len(onsets) == 0:
            logger.warning("   No beats detected, returning original audio")
            return audio

        # Synthesize drum sounds based on kit
        if kit == '808':
            kick = self.synthesize_808_kick(sr)
            snare = self.synthesize_808_snare(sr)
            hihat = self.synthesize_808_hihat(sr)
        elif kit == '909':
            kick = self.synthesize_909_kick(sr)
            snare = self.synthesize_909_snare(sr)
            hihat = self.synthesize_808_hihat(sr, duration=0.08)
        else:
            # Acoustic/Electronic - use 808 as base with different processing
            kick = self.synthesize_808_kick(sr)
            snare = self.synthesize_808_snare(sr)
            hihat = self.synthesize_808_hihat(sr)

            if kit == 'acoustic':
                # Add more noise/body to simulate acoustic
                kick = self.apply_reverb(kick, sr, room_size=0.3)
                snare = self.apply_reverb(snare, sr, room_size=0.4)
            else:  # electronic
                # Add distortion for electronic feel
                kick = self.apply_distortion(kick, sr, drive=0.3)
                snare = self.apply_bitcrusher(snare, sr, bits=10)

        # Create output - mix original with drums
        output = audio.copy()

        # Track counts
        counts = {'kick': 0, 'snare': 0, 'hihat': 0}

        for onset_time, strength in onsets:
            # Classify the onset
            drum_type = self.classify_onset(audio, sr, onset_time)

            # Select appropriate drum sound
            if drum_type == 'kick':
                drum_sound = kick
                counts['kick'] += 1
            elif drum_type == 'snare':
                drum_sound = snare
                counts['snare'] += 1
            else:
                drum_sound = hihat
                counts['hihat'] += 1

            # Mix drum at onset position
            start_sample = int(onset_time * sr)
            end_sample = min(start_sample + len(drum_sound), len(output))
            samples_to_add = end_sample - start_sample

            if samples_to_add > 0:
                # Mix: reduce original, add drum
                output[start_sample:end_sample] *= 0.3  # Reduce original
                output[start_sample:end_sample] += drum_sound[:samples_to_add] * strength * 0.8

        logger.info(f"   Applied: {counts['kick']} kicks, {counts['snare']} snares, {counts['hihat']} hihats")

        return self._normalize(output)


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    processor = AudioEffectsProcessor()

    print("Available Presets:")
    for name, info in processor.get_available_presets().items():
        print(f"  - {name}: {info['description']}")

    print("\nAvailable Effects:")
    for effect in processor.get_available_effects():
        print(f"  - {effect['name']} ({effect['category']})")
