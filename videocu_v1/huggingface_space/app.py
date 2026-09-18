"""
VIDEOCU Music Studio - HuggingFace Spaces GPU Backend
AI-powered music production: Basic Pitch, MusicGen, Demucs
"""

import gradio as gr
import torch
import os
import tempfile
import numpy as np

# Check GPU
print(f"GPU Available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# ========== LAZY MODEL LOADING ==========
_melody_extractor = None
_music_generator = None
_stem_separator = None


def get_melody_extractor():
    """Lazy load Basic Pitch"""
    global _melody_extractor
    if _melody_extractor is None:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH
        _melody_extractor = {
            'predict': predict,
            'model_path': ICASSP_2022_MODEL_PATH
        }
        print("Basic Pitch loaded!")
    return _melody_extractor


def get_music_generator():
    """Lazy load MusicGen"""
    global _music_generator
    if _music_generator is None:
        from audiocraft.models import MusicGen
        _music_generator = MusicGen.get_pretrained('facebook/musicgen-small')
        _music_generator.set_generation_params(
            duration=30,
            temperature=1.0,
            top_k=250
        )
        print("MusicGen loaded!")
    return _music_generator


def get_stem_separator():
    """Lazy load Demucs"""
    global _stem_separator
    if _stem_separator is None:
        import demucs.api
        _stem_separator = demucs.api.Separator()
        print("Demucs loaded!")
    return _stem_separator


# ========== PROCESSING FUNCTIONS ==========

def extract_melody(audio_file):
    """Extract melody from audio using Basic Pitch"""
    if audio_file is None:
        return None, {"error": "No audio file provided"}

    try:
        import pretty_midi
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        extractor = get_melody_extractor()

        # Run Basic Pitch
        model_output, midi_data, note_events = extractor['predict'](
            audio_file,
            extractor['model_path']
        )

        # Save MIDI
        output_dir = tempfile.mkdtemp()
        midi_path = os.path.join(output_dir, "melody.mid")
        midi_data.write(midi_path)

        # Extract note info
        notes_info = []
        for note in midi_data.instruments[0].notes:
            notes_info.append({
                "pitch": note.pitch,
                "start": round(note.start, 3),
                "end": round(note.end, 3),
                "velocity": note.velocity
            })

        # Estimate key and tempo
        if notes_info:
            pitch_classes = [n["pitch"] % 12 for n in notes_info]
            from collections import Counter
            common = Counter(pitch_classes).most_common(1)
            key_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            key = f"{key_names[common[0][0]]} major" if common else "C major"

            # Tempo from note intervals
            if len(notes_info) > 1:
                intervals = [notes_info[i]["start"] - notes_info[i-1]["start"]
                            for i in range(1, len(notes_info))
                            if 0.1 < notes_info[i]["start"] - notes_info[i-1]["start"] < 2]
                tempo = int(60 / np.median(intervals)) if intervals else 120
                tempo = max(60, min(180, tempo))
            else:
                tempo = 120

            duration = max([n["end"] for n in notes_info])
        else:
            key = "Unknown"
            tempo = 120
            duration = 0

        # Create piano roll visualization
        fig, ax = plt.subplots(figsize=(12, 4))
        colors = plt.cm.viridis(np.linspace(0.2, 0.8, 12))

        for note in notes_info:
            color = colors[note['pitch'] % 12]
            rect = Rectangle(
                (note['start'], note['pitch'] - 0.4),
                note['end'] - note['start'],
                0.8,
                facecolor=color,
                edgecolor='black',
                linewidth=0.5,
                alpha=0.8
            )
            ax.add_patch(rect)

        if notes_info:
            all_pitches = [n['pitch'] for n in notes_info]
            all_times = [n['end'] for n in notes_info]
            ax.set_xlim(0, max(all_times) + 0.5)
            ax.set_ylim(min(all_pitches) - 2, max(all_pitches) + 2)

        ax.set_xlabel('Time (s)')
        ax.set_ylabel('MIDI Note')
        ax.set_title(f'Melody: {len(notes_info)} notes - {key} - {tempo} BPM')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        result = {
            "nota_sayisi": len(notes_info),
            "anahtar": key,
            "tempo": tempo,
            "sure": f"{duration:.1f}s",
            "midi_dosyasi": midi_path
        }

        return fig, result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, {"error": str(e)}


def generate_music(style, custom_prompt, duration):
    """Generate music from text prompt using MusicGen"""
    try:
        from audiocraft.data.audio import audio_write

        prompt = custom_prompt.strip() if custom_prompt.strip() else style
        duration = int(duration)

        generator = get_music_generator()
        generator.set_generation_params(duration=duration)

        # Generate
        wav = generator.generate([prompt])

        # Save
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "generated")
        audio_write(output_path, wav[0].cpu(), generator.sample_rate, strategy="loudness")

        return output_path + ".wav"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


def transform_melody(audio_file, style, duration):
    """Transform melody to professional sound using MusicGen melody-conditioned"""
    if audio_file is None:
        return None

    try:
        import torchaudio
        from audiocraft.data.audio import audio_write

        duration = int(duration)
        generator = get_music_generator()
        generator.set_generation_params(duration=duration)

        # Load reference audio
        melody_waveform, sr = torchaudio.load(audio_file)

        # Convert to mono
        if melody_waveform.shape[0] > 1:
            melody_waveform = melody_waveform.mean(dim=0, keepdim=True)

        # Resample if needed
        if sr != generator.sample_rate:
            resampler = torchaudio.transforms.Resample(sr, generator.sample_rate)
            melody_waveform = resampler(melody_waveform)

        # Generate with melody conditioning
        wav = generator.generate_with_chroma(
            descriptions=[style],
            melody_wavs=melody_waveform.unsqueeze(0).cuda() if torch.cuda.is_available() else melody_waveform.unsqueeze(0),
            melody_sample_rate=generator.sample_rate,
            progress=True
        )

        # Save
        output_dir = tempfile.mkdtemp()
        output_path = os.path.join(output_dir, "transformed")
        audio_write(output_path, wav[0].cpu(), generator.sample_rate, strategy="loudness")

        return output_path + ".wav"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


def separate_stems(audio_file):
    """Separate vocals from instrumentals using Demucs"""
    if audio_file is None:
        return None, None

    try:
        import subprocess

        output_dir = tempfile.mkdtemp()

        # Run demucs
        cmd = f"python -m demucs -o {output_dir} --two-stems vocals \"{audio_file}\""
        subprocess.run(cmd, shell=True, check=True)

        # Find output files
        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        stems_dir = os.path.join(output_dir, "htdemucs", base_name)

        vocals_path = os.path.join(stems_dir, "vocals.wav")
        instrumental_path = os.path.join(stems_dir, "no_vocals.wav")

        if os.path.exists(vocals_path) and os.path.exists(instrumental_path):
            return vocals_path, instrumental_path
        else:
            return None, None

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None


# ========== GRADIO INTERFACE ==========

STYLE_CHOICES = [
    "modern hip hop beat with heavy 808 bass, trap hi-hats",
    "catchy pop melody with bright synths, upbeat drums",
    "electronic dance music with pulsing synths, four-on-the-floor beat",
    "chill lofi hip hop with jazzy piano, vinyl crackle, relaxed drums",
    "epic orchestral piece with strings, brass, dramatic percussion",
    "jazz composition with piano, upright bass, swing drums",
    "rock song with electric guitars, driving drums, powerful bass",
    "smooth r&b with soulful chords, soft drums, warm bass",
    "acoustic ballad with gentle guitar, soft percussion",
    "dark trap beat with heavy 808s, fast hi-hats, aggressive energy"
]

with gr.Blocks(
    title="VIDEOCU Music Studio",
    theme=gr.themes.Soft()
) as demo:

    gr.Markdown("""
    # 🎵 VIDEOCU Music Studio
    **GPU-powered AI music production** - Basic Pitch, MusicGen, Demucs

    Bu API, VIDEOCU Telegram Bot ile entegre çalışır.
    """)

    with gr.Tabs():
        # Tab 1: Melody Extraction
        with gr.TabItem("🎵 Melodi Çıkar"):
            with gr.Row():
                with gr.Column():
                    melody_input = gr.Audio(
                        label="Ses Dosyası (Mırıldanma/Islık)",
                        type="filepath"
                    )
                    melody_btn = gr.Button("🎵 Melodi Çıkar", variant="primary")

                with gr.Column():
                    melody_plot = gr.Plot(label="Piano Roll")
                    melody_info = gr.JSON(label="Melodi Bilgileri")

            melody_btn.click(
                extract_melody,
                inputs=[melody_input],
                outputs=[melody_plot, melody_info],
                api_name="extract_melody"
            )

        # Tab 2: Music Generation
        with gr.TabItem("🎹 AI Müzik Üret"):
            with gr.Row():
                with gr.Column():
                    style_select = gr.Dropdown(
                        choices=STYLE_CHOICES,
                        label="Stil Seç",
                        value=STYLE_CHOICES[0]
                    )
                    custom_prompt = gr.Textbox(
                        label="Özel Prompt (opsiyonel)",
                        placeholder="Kendi stilinizi yazın..."
                    )
                    gen_duration = gr.Slider(
                        5, 60, value=30, step=5,
                        label="Süre (saniye)"
                    )
                    generate_btn = gr.Button("🎹 Üret", variant="primary")

                with gr.Column():
                    generated_audio = gr.Audio(label="Üretilen Müzik")

            generate_btn.click(
                generate_music,
                inputs=[style_select, custom_prompt, gen_duration],
                outputs=[generated_audio],
                api_name="generate_music"
            )

        # Tab 3: Style Transform
        with gr.TabItem("🎨 Stil Dönüştür"):
            with gr.Row():
                with gr.Column():
                    transform_input = gr.Audio(
                        label="Kaynak Ses",
                        type="filepath"
                    )
                    transform_style = gr.Dropdown(
                        choices=STYLE_CHOICES,
                        label="Hedef Stil",
                        value=STYLE_CHOICES[1]
                    )
                    transform_duration = gr.Slider(
                        5, 60, value=30, step=5,
                        label="Süre"
                    )
                    transform_btn = gr.Button("🎨 Dönüştür", variant="primary")

                with gr.Column():
                    transformed_audio = gr.Audio(label="Dönüştürülmüş Ses")

            transform_btn.click(
                transform_melody,
                inputs=[transform_input, transform_style, transform_duration],
                outputs=[transformed_audio],
                api_name="transform_melody"
            )

        # Tab 4: Stem Separation
        with gr.TabItem("🔀 Stem Ayır"):
            with gr.Row():
                with gr.Column():
                    stems_input = gr.Audio(
                        label="Şarkı Dosyası",
                        type="filepath"
                    )
                    stems_btn = gr.Button("🔀 Ayır", variant="primary")

                with gr.Column():
                    vocals_output = gr.Audio(label="🎤 Vokal")
                    instrumental_output = gr.Audio(label="🎸 Enstrümental")

            stems_btn.click(
                separate_stems,
                inputs=[stems_input],
                outputs=[vocals_output, instrumental_output],
                api_name="separate_stems"
            )

    gr.Markdown("""
    ---
    **API Kullanımı:**
    ```python
    from gradio_client import Client
    client = Client("YOUR_SPACE_URL")
    result = client.predict(audio_file, api_name="/extract_melody")
    ```

    **VIDEOCU Project** | GPU: T4/A10G
    """)

# Launch
if __name__ == "__main__":
    demo.launch()
