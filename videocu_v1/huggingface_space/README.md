---
title: VIDEOCU Music Studio
emoji: 🎵
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
hardware: gpu-basic
---

# 🎵 VIDEOCU Music Studio

GPU-powered AI music production backend for VIDEOCU Telegram Bot.

## Features

- **Basic Pitch**: Extract melody from humming/whistling → MIDI
- **MusicGen**: AI music generation from text prompts
- **Demucs**: Vocal/instrumental separation
- **Style Transfer**: Transform melodies to professional sounds

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/extract_melody` | Audio → MIDI melody extraction |
| `/generate_music` | Text → AI music generation |
| `/transform_melody` | Audio + Style → Transformed audio |
| `/separate_stems` | Audio → Vocals + Instrumental |

## Usage

```python
from gradio_client import Client

client = Client("Cyhn85/videocu-music-studio")

# Extract melody
result = client.predict(
    "audio.wav",
    api_name="/extract_melody"
)

# Generate music
audio = client.predict(
    "hip hop beat with 808 bass",
    "",  # custom prompt
    30,  # duration
    api_name="/generate_music"
)
```

## Part of VIDEOCU Project

This Space serves as the GPU backend for the VIDEOCU Hit Song Factory system.
