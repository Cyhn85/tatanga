# 🎵 VIDEOCU Hit Song Factory - Sistem Mimarisi

## Genel Bakış: Ağızdan Sesten Tam Aranjmana

Bu sistem, müzik teorisi bilmeden amatör ses/mırıldanmayı profesyonel müziğe dönüştürmeyi hedefler.

---

## 🏗️ Hibrit Mimari: CPU Server + Colab GPU

```
┌─────────────────────────────────────────────────────────────────┐
│                    VIDEOCU HIT SONG FACTORY                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────┐         ┌─────────────────────────────┐       │
│   │ CPU SERVER  │ ◄─────► │     GOOGLE COLAB (GPU)      │       │
│   │ (Control)   │   API   │        (Power)              │       │
│   │             │         │                             │       │
│   │ • Telegram  │         │ • Basic Pitch (Melody→MIDI) │       │
│   │ • CEO Agent │         │ • MusicGen (AI Arrangement) │       │
│   │ • Celery    │         │ • Demucs (Stem Separation)  │       │
│   │ • DAW Engine│         │ • T4/V100 GPU               │       │
│   └─────────────┘         └─────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Agent Mimarisi

### 1. CEO Agent (Merkez)
- Tüm iş akışını koordine eder
- Kullanıcı kararlarını alır ve dağıtır
- Proaktif önerilerde bulunur

### 2. Composer Agent (Geliştirilmiş)
```python
class ComposerAgent:
    def process_melody_input(self, audio_file):
        """
        1. Basic Pitch ile melodi çıkar (Colab GPU)
        2. MIDI dosyası oluştur
        3. Nota ve zamanlama bilgisi döndür
        """

    def extract_rhythm_pattern(self, audio_file):
        """
        1. librosa ile onset detection
        2. BPM tespiti
        3. Ritim pattern'i çıkar
        """
```

### 3. MusicGen Agent (YENİ - Colab)
```python
class MusicGenAgent:
    def generate_arrangement(self, midi_file, style_prompt):
        """
        1. MIDI + stil prompt'u al
        2. Colab GPU'da MusicGen çalıştır
        3. Profesyonel ses döndür
        """

    def apply_style(self, audio, style):
        """
        Stiller: hip-hop, pop, rock, electronic, jazz
        """
```

### 4. Beatbox Agent (Mevcut - Geliştirilmiş)
```python
class BeatboxAgent:
    def transform_to_808(self, beatbox_audio):
        """
        Ağız sesi → 808/909 kit dönüşümü
        - Kick detection → 808 kick
        - Snare detection → 808 snare
        - Hi-hat detection → 808 hi-hat
        """
```

### 5. DAW Engine (YENİ)
```python
class DAWEngine:
    def orchestrate_layers(self, json_timeline):
        """
        JSON timeline ile layer yönetimi:
        {
            "layers": [
                {"name": "melody", "file": "melody.wav", "start": 0, "end": 120},
                {"name": "bass", "file": "bass.wav", "start": 82, "end": 120},
                {"name": "drums", "file": "drums.wav", "start": 0, "end": 120}
            ]
        }
        """

    def add_sound_at_time(self, layer, sound, timestamp):
        """
        Belirli zamana ses ekleme
        Örnek: 82. saniyeye bass drop
        """
```

---

## 🔄 Non-Destructive Workflow

```
Original Files (ASLA DEĞİŞMEZ)
        │
        ▼
┌───────────────────┐
│   Project JSON    │  ← Tüm değişiklikler burada
│                   │
│ • Layer bilgileri │
│ • Effect chain    │
│ • Timeline        │
│ • Undo history    │
└───────────────────┘
        │
        ▼
   Final Render
```

---

## 👤 Kullanıcı Kontrol Akışı

### Adım 1: Melodi Girişi
```
Kullanıcı: [Ses kaydı gönderir - mırıldanma/ıslık]
Bot: "Melodini analiz ediyorum..."
Bot: "🎵 Melodi çıkarıldı!
      - Nota sayısı: 24
      - Anahtar: C major
      - Tempo: 120 BPM

      Şimdi ne yapmak istersin?
      1️⃣ Ritim ekle
      2️⃣ Stil seç
      3️⃣ Direkt aranje et"
```

### Adım 2: Ritim Girişi
```
Kullanıcı: [Beatbox kaydı gönderir]
Bot: "Ritim pattern'i algılandı!
      - BPM: 120
      - Pattern: Kick-Hat-Snare-Hat

      Kit seç:
      🥁 808 Classic
      🎹 909 Electronic
      🎸 Acoustic"
```

### Adım 3: Aranjman Fikri
```
Kullanıcı: "82. saniyede bass drop istiyorum"
Bot: "Bass drop eklendi!
      [Preview butonu]

      Başka değişiklik?"
```

### Adım 4: Layer Yönetimi
```
Bot: "Mevcut layer'lar:

      1. 🎤 Melodi [0:00 - 2:00] ✅
      2. 🥁 Drums [0:00 - 2:00] ✅
      3. 🎸 Bass [1:22 - 2:00] ✅

      Seçenekler:
      • Layer sil
      • Layer taşı
      • Yeni layer ekle
      • Volume ayarla"
```

### Adım 5: Final Render
```
Kullanıcı: "Tamamla"
Bot: "🎵 Hit şarkın hazır!

      📊 Proje özeti:
      - Süre: 2:00
      - Layer: 5
      - Stil: Hip-Hop

      [WAV İndir] [MP3 İndir] [Projeyi Kaydet]"
```

---

## 🔧 Teknik Gereksinimler

### CPU Server (195.201.146.224)
- Python 3.9+
- Celery + Redis (task queue)
- pydub, librosa
- Telegram Bot API
- FastAPI (Colab bridge)

### Google Colab
- T4 veya V100 GPU
- PyTorch
- Basic Pitch
- MusicGen (audiocraft)
- Demucs
- ngrok (API tunnel)

---

## 📁 Dosya Yapısı

```
videocu_v1/
├── modules/
│   ├── agents/
│   │   ├── ceo_agent.py
│   │   ├── composer_agent.py      # Geliştirilecek
│   │   ├── musicgen_agent.py      # YENİ
│   │   ├── beatbox_agent.py       # YENİ
│   │   └── daw_engine.py          # YENİ
│   ├── colab/
│   │   ├── colab_bridge.py        # Colab iletişimi
│   │   └── task_queue.py          # Celery tasks
│   └── core/
│       └── non_destructive.py     # Project JSON manager
├── notebooks/
│   └── videocu_music_studio.ipynb # Colab notebook
└── telegram_bot.py
```

---

## 🚀 Uygulama Sırası

1. **Faz 1: Colab Notebook**
   - Basic Pitch entegrasyonu
   - MusicGen kurulumu
   - API endpoint'leri

2. **Faz 2: Bridge Sistemi**
   - Celery task queue
   - Colab ↔ Server iletişimi
   - Dosya transferi

3. **Faz 3: Agent Güncellemeleri**
   - Composer Agent GPU desteği
   - MusicGen Agent
   - DAW Engine

4. **Faz 4: Telegram UI**
   - Inline keyboard'lar
   - Timeline görselleştirme
   - Layer yönetimi

---

## 💡 Hedef

**"Müzik teorisi bilmeden, sadece ağzınla söyleyerek HIT şarkı yap!"**

- Mırıldanma → Profesyonel melodi
- Beatbox → 808/909 drums
- Ses komutu → Aranjman
- Timeline kontrolü → Prodüktör gibi düzenleme