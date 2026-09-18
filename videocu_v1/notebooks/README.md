# VIDEOCU Music Studio

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Cyhn85/videocu-music-studio/blob/main/notebooks/videocu_music_studio.ipynb)

GPU-powered AI music production studio for VIDEOCU Hit Song Factory.

## Features

### Basic Pitch - Melody Extraction
- Hum or whistle a melody
- Automatic transcription to MIDI
- Interactive Piano Roll visualization
- Note editing with sliders

### MusicGen - AI Music Generation
- Text-to-music generation
- Style-conditioned melody transformation
- Multiple genre presets (Hip-Hop, Pop, Electronic, Jazz, etc.)

### Demucs - Stem Separation
- Separate vocals from instrumentals
- High-quality audio isolation
- GPU-accelerated processing

## Usage Modes

### 1. Interactive Mode (ipywidgets)
Run cells step-by-step and use the interactive widgets:
- Upload audio via file picker or microphone
- Select operations from dropdown menus
- Adjust parameters with sliders
- Visualize results in real-time

### 2. API Mode (Flask + ngrok)
Run `start_server()` to expose endpoints for your Telegram bot:
```
POST /extract-melody   - Extract melody from audio
POST /generate-music   - Generate music from prompt
POST /transform-melody - Transform melody with style
POST /separate-stems   - Separate vocals/instrumental
```

### 3. Demo Mode (Gradio)
Run `launch_gradio()` to get a public URL:
- Share with clients for demos
- Integrate with Telegram bot
- No coding required

## Quick Start

1. Open in Colab (click badge above)
2. Change runtime to GPU: `Runtime > Change runtime type > GPU`
3. Run all cells: `Runtime > Run all`
4. Use interactive widgets or start API server

## Style Presets

| Style | Prompt |
|-------|--------|
| Hip-Hop | `modern hip hop beat with heavy 808 bass, trap hi-hats` |
| Pop | `catchy pop melody with bright synths, upbeat drums` |
| Electronic | `electronic dance music with pulsing synths, four-on-the-floor beat` |
| Lo-Fi | `chill lofi hip hop with jazzy piano, vinyl crackle` |
| Orchestral | `epic orchestral piece with strings, brass, dramatic percussion` |
| Jazz | `jazz composition with piano, upright bass, swing drums` |

## API Integration

### For Telegram Bot
```python
import requests
import base64

# Extract melody
with open('humming.wav', 'rb') as f:
    audio_b64 = base64.b64encode(f.read()).decode()

response = requests.post(
    'https://YOUR_NGROK_URL/extract-melody',
    json={'audio': audio_b64}
)
result = response.json()
print(f"Notes: {result['result']['note_count']}")
```

### For Web Frontend
```python
from gradio_client import Client

client = Client("YOUR_GRADIO_URL")
result = client.predict(
    "humming.wav",  # audio file
    api_name="/extract_melody"
)
```

## Requirements

- Google Colab with GPU runtime
- ngrok account (free) for API mode
- Python 3.8+

## License

MIT License - Part of VIDEOCU Project
