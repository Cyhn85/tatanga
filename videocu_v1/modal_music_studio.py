"""
VIDEOCU Music Studio - Modal GPU Backend
MusicGen, Basic Pitch, Demucs ile AI muzik uretimi

Deploy: modal deploy modal_music_studio.py
Test: modal run modal_music_studio.py
"""

import modal

# Modal App
app = modal.App("videocu-music-studio")

# GPU Image - gerekli kutuphaneler (uyumlu surumler)
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "pkg-config", "libavformat-dev", "libavcodec-dev", "libavdevice-dev", "libavutil-dev", "libswscale-dev", "libswresample-dev", "libavfilter-dev", "fluidsynth", "fluid-soundfont-gm")
    .pip_install(
        "torch==2.1.0",
        "torchaudio==2.1.0",
        "transformers==4.36.0",
        "numpy<2.0",
        "scipy",
        "librosa",
        "pretty_midi",
        "midiutil",
        "pyfluidsynth",
    )
    .pip_install("audiocraft")
    .pip_install("basic-pitch")
    .pip_install("demucs")
)

# ============ MUSICGEN - AI Muzik Uretimi ============
@app.function(
    image=image,
    gpu="T4",
    timeout=600,
    memory=16384,
)
def generate_music(prompt: str, duration: int = 30) -> bytes:
    """MusicGen ile muzik uret"""
    import torch
    import torchaudio
    from audiocraft.models import MusicGen
    from audiocraft.data.audio import audio_write
    import tempfile
    import os

    print(f"MusicGen baslatiliyor... Prompt: {prompt[:50]}...")

    # Model yukle
    model = MusicGen.get_pretrained('facebook/musicgen-small')
    model.set_generation_params(duration=duration, temperature=1.0, top_k=250)

    # Uret
    wav = model.generate([prompt])

    # Kaydet
    output_dir = tempfile.mkdtemp()
    output_path = os.path.join(output_dir, "generated")
    audio_write(output_path, wav[0].cpu(), model.sample_rate, strategy="loudness")

    # Bytes olarak don
    with open(output_path + ".wav", "rb") as f:
        audio_bytes = f.read()

    print(f"Muzik uretildi: {len(audio_bytes)} bytes")
    return audio_bytes


# ============ BASIC PITCH - Melodi Cikarma ============
@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    memory=8192,
)
def extract_melody(audio_bytes: bytes) -> dict:
    """Ses dosyasindan melodi cikar"""
    import tempfile
    import os
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    print("Basic Pitch ile melodi cikariliyor...")

    # Gecici dosyaya kaydet
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        audio_path = f.name

    try:
        # Melodi cikar
        model_output, midi_data, note_events = predict(audio_path, ICASSP_2022_MODEL_PATH)

        # MIDI kaydet
        output_dir = tempfile.mkdtemp()
        midi_path = os.path.join(output_dir, "melody.mid")
        midi_data.write(midi_path)

        # Nota bilgileri
        notes_info = []
        if midi_data.instruments:
            for note in midi_data.instruments[0].notes:
                notes_info.append({
                    "pitch": note.pitch,
                    "start": round(note.start, 3),
                    "end": round(note.end, 3),
                    "velocity": note.velocity
                })

        # MIDI bytes
        with open(midi_path, "rb") as f:
            midi_bytes = f.read()

        result = {
            "success": True,
            "note_count": len(notes_info),
            "notes": notes_info[:20],  # Ilk 20 nota
            "midi_bytes": midi_bytes.hex(),  # Hex encoded
        }
        print(f"Melodi cikarildi: {len(notes_info)} nota")
        return result

    finally:
        os.unlink(audio_path)


# ============ DEMUCS - Vokal/Enstruman Ayirma ============
@app.function(
    image=image,
    gpu="T4",
    timeout=600,
    memory=16384,
)
def separate_stems(audio_bytes: bytes) -> dict:
    """Vokal ve enstrumani ayir"""
    import tempfile
    import os
    import subprocess

    print("Demucs ile stem ayirma baslatiliyor...")

    # Gecici dosyaya kaydet
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        audio_path = f.name

    try:
        output_dir = tempfile.mkdtemp()

        # Demucs calistir
        cmd = f'python -m demucs -o {output_dir} --two-stems vocals "{audio_path}"'
        subprocess.run(cmd, shell=True, check=True)

        # Cikti dosyalarini bul
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        stems_dir = os.path.join(output_dir, "htdemucs", base_name)

        vocals_path = os.path.join(stems_dir, "vocals.wav")
        instrumental_path = os.path.join(stems_dir, "no_vocals.wav")

        result = {"success": False}

        if os.path.exists(vocals_path) and os.path.exists(instrumental_path):
            with open(vocals_path, "rb") as f:
                vocals_bytes = f.read()
            with open(instrumental_path, "rb") as f:
                instrumental_bytes = f.read()

            result = {
                "success": True,
                "vocals_bytes": vocals_bytes.hex(),
                "instrumental_bytes": instrumental_bytes.hex(),
            }
            print(f"Stem ayirma tamamlandi")

        return result

    finally:
        os.unlink(audio_path)


# ============ TRANSFORM MELODY - Stil Donusturme ============
@app.function(
    image=image,
    gpu="T4",
    timeout=600,
    memory=16384,
)
def transform_melody(audio_bytes: bytes, style_prompt: str, duration: int = 30) -> bytes:
    """Melodiyi farkli stile donustur"""
    import torch
    import torchaudio
    from audiocraft.models import MusicGen
    from audiocraft.data.audio import audio_write
    import tempfile
    import os

    print(f"Stil donusturme baslatiliyor: {style_prompt[:50]}...")

    # Gecici dosyaya kaydet
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        audio_path = f.name

    try:
        # Model yukle
        model = MusicGen.get_pretrained('facebook/musicgen-small')
        model.set_generation_params(duration=duration, temperature=1.0, top_k=250)

        # Melodi yukle
        melody_waveform, sr = torchaudio.load(audio_path)
        if melody_waveform.shape[0] > 1:
            melody_waveform = melody_waveform.mean(dim=0, keepdim=True)

        # Resample
        if sr != model.sample_rate:
            resampler = torchaudio.transforms.Resample(sr, model.sample_rate)
            melody_waveform = resampler(melody_waveform)

        # Melody-conditioned generation
        wav = model.generate_with_chroma(
            descriptions=[style_prompt],
            melody_wavs=melody_waveform.unsqueeze(0).cuda() if torch.cuda.is_available() else melody_waveform.unsqueeze(0),
            melody_sample_rate=model.sample_rate,
            progress=True
        )

        # Kaydet
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "transformed")
        audio_write(output_path, wav[0].cpu(), model.sample_rate, strategy="loudness")

        with open(output_path + ".wav", "rb") as f:
            result_bytes = f.read()

        print(f"Donusum tamamlandi: {len(result_bytes)} bytes")
        return result_bytes

    finally:
        os.unlink(audio_path)


# ============ PITCH QUANTIZE - Notalari Duzeltme ============
@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    memory=8192,
)
def quantize_midi(midi_hex: str, grid: str = "16th") -> dict:
    """
    MIDI notalarini grid'e oturtur (pitch quantize)

    Args:
        midi_hex: Hex encoded MIDI bytes
        grid: Quantize grid ("8th", "16th", "32nd")

    Returns:
        {
            "success": True/False,
            "midi_bytes": hex string (quantized),
            "note_count": int,
            "corrections": int (duzeltilen nota sayisi)
        }
    """
    import tempfile
    import os
    import pretty_midi

    print(f"MIDI Quantize baslatiliyor... Grid: {grid}")

    # Grid degerleri (saniye cinsinden, 120 BPM bazinda)
    grid_values = {
        "8th": 0.25,    # 8'lik nota
        "16th": 0.125,  # 16'lik nota
        "32nd": 0.0625  # 32'lik nota
    }
    grid_size = grid_values.get(grid, 0.125)

    # MIDI'yi temp dosyaya yaz
    midi_bytes = bytes.fromhex(midi_hex)
    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        f.write(midi_bytes)
        midi_path = f.name

    try:
        # MIDI yukle
        midi = pretty_midi.PrettyMIDI(midi_path)

        corrections = 0
        total_notes = 0

        for instrument in midi.instruments:
            for note in instrument.notes:
                total_notes += 1

                # Start time'i grid'e oturtur
                original_start = note.start
                quantized_start = round(note.start / grid_size) * grid_size

                # End time'i da grid'e oturtur (sure korunur)
                duration = note.end - note.start
                quantized_duration = max(grid_size, round(duration / grid_size) * grid_size)

                if abs(original_start - quantized_start) > 0.01:
                    corrections += 1

                note.start = quantized_start
                note.end = quantized_start + quantized_duration

        # Kaydet
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "quantized.mid")
        midi.write(output_path)

        with open(output_path, "rb") as f:
            result_bytes = f.read()

        print(f"Quantize tamamlandi: {corrections}/{total_notes} nota duzeltildi")

        return {
            "success": True,
            "midi_bytes": result_bytes.hex(),
            "note_count": total_notes,
            "corrections": corrections
        }

    finally:
        os.unlink(midi_path)


# ============ MIDI TO AUDIO - Enstruman Sentezi ============
@app.function(
    image=image,
    gpu="T4",
    timeout=300,
    memory=8192,
)
def midi_to_audio(midi_hex: str, instrument: str = "piano") -> dict:
    """
    MIDI'yi enstruman sesiyle audio'ya donustur (FluidSynth)

    Args:
        midi_hex: Hex encoded MIDI bytes
        instrument: Enstruman tipi ("piano", "bass", "synth", "strings", "guitar")

    Returns:
        {
            "success": True/False,
            "audio_bytes": WAV bytes,
            "duration": float
        }
    """
    import tempfile
    import os
    import subprocess
    import wave

    print(f"MIDI -> Audio donusumu baslatiliyor... Enstruman: {instrument}")

    # Program numbers (General MIDI)
    instruments = {
        "piano": 0,        # Acoustic Grand Piano
        "electric_piano": 4,  # Electric Piano
        "bass": 33,        # Electric Bass (finger)
        "synth_bass": 38,  # Synth Bass 1
        "synth": 80,       # Lead 1 (square)
        "pad": 88,         # Pad 1 (new age)
        "strings": 48,     # String Ensemble 1
        "guitar": 25,      # Acoustic Guitar (steel)
        "organ": 16,       # Drawbar Organ
    }

    program = instruments.get(instrument, 0)

    # MIDI'yi temp dosyaya yaz
    midi_bytes = bytes.fromhex(midi_hex)
    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        f.write(midi_bytes)
        midi_path = f.name

    try:
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "output.wav")

        # SoundFont yolu (Debian fluid-soundfont-gm paketi)
        soundfont = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

        # FluidSynth ile render
        cmd = [
            "fluidsynth",
            "-ni",  # No interactive mode
            "-g", "1.0",  # Gain
            "-F", output_path,  # Output file
            "-r", "44100",  # Sample rate
            soundfont,
            midi_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"FluidSynth hatasi: {result.stderr}")
            return {"success": False, "error": result.stderr}

        if not os.path.exists(output_path):
            return {"success": False, "error": "Output dosyasi olusturulamadi"}

        # WAV dosyasini oku
        with open(output_path, "rb") as f:
            audio_bytes = f.read()

        # Duration hesapla
        try:
            with wave.open(output_path, 'rb') as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                duration = frames / float(rate)
        except:
            duration = 0

        print(f"MIDI -> Audio tamamlandi: {len(audio_bytes)} bytes, {duration:.1f}s")

        return {
            "success": True,
            "audio_bytes": audio_bytes.hex(),
            "duration": duration
        }

    finally:
        os.unlink(midi_path)


# ============ TRANSPOSE MIDI - Ton Degistirme ============
@app.function(
    image=image,
    gpu="T4",
    timeout=120,
    memory=4096,
)
def transpose_midi(midi_hex: str, semitones: int) -> dict:
    """
    MIDI'yi transpoze et (tonu degistir)

    Args:
        midi_hex: Hex encoded MIDI bytes
        semitones: Kac yarim adim (pozitif=yukari, negatif=asagi)

    Returns:
        {
            "success": True/False,
            "midi_bytes": hex string,
            "note_count": int
        }
    """
    import tempfile
    import os
    import pretty_midi

    print(f"MIDI Transpose: {semitones:+d} semitone")

    midi_bytes = bytes.fromhex(midi_hex)
    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        f.write(midi_bytes)
        midi_path = f.name

    try:
        midi = pretty_midi.PrettyMIDI(midi_path)

        note_count = 0
        for instrument in midi.instruments:
            for note in instrument.notes:
                note.pitch = max(0, min(127, note.pitch + semitones))
                note_count += 1

        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "transposed.mid")
        midi.write(output_path)

        with open(output_path, "rb") as f:
            result_bytes = f.read()

        print(f"Transpose tamamlandi: {note_count} nota")

        return {
            "success": True,
            "midi_bytes": result_bytes.hex(),
            "note_count": note_count
        }

    finally:
        os.unlink(midi_path)


# ============ WEB ENDPOINT - Health Check ============
@app.function(
    image=image,
    gpu="T4",
    timeout=3600,
    memory=16384,
)
@modal.fastapi_endpoint(method="GET")
def health():
    """Health check endpoint"""
    import torch
    return {
        "status": "healthy",
        "gpu": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    }


# ============ TEST ============
@app.local_entrypoint()
def main():
    """Test fonksiyonu"""
    print("VIDEOCU Music Studio - Modal GPU Backend")
    print("=" * 50)

    # Health check
    result = health.remote()
    print(f"Health: {result}")

    # MusicGen test
    print("\nMusicGen testi (10 saniye hip hop)...")
    audio = generate_music.remote(
        prompt="modern hip hop beat with heavy 808 bass, trap hi-hats",
        duration=10
    )
    print(f"Uretilen audio: {len(audio)} bytes")

    # Kaydet
    with open("test_output.wav", "wb") as f:
        f.write(audio)
    print("Kaydedildi: test_output.wav")

    print("\nTum testler basarili!")