"""
VIDEOCU v1 - FULL INTEGRATION TEST
Complete workflow: Gemini Script → Images → Voice → Video
"""

import sys
import logging
from pathlib import Path
import json

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from modules import ContentGenerator, ImageGenerator, VoiceGenerator, VideoEditor
import config

print("\n" + "="*70)
print("🚀 VIDEOCU v1 - FULL INTEGRATION TEST")
print("="*70)

# Test configuration
TEST_TOPIC = "Künstliche Intelligenz Revolution 2025"
TEST_DURATION = 60
TEST_LANGUAGE = "de"
TEST_STYLE = "informativ"

output_dir = Path("output/integration_test")
output_dir.mkdir(parents=True, exist_ok=True)

# =============================================================================
# STEP 1: GENERATE SCRIPT (Gemini AI)
# =============================================================================
print("\n" + "="*70)
print("STEP 1/4: SCRIPT GENERATION (Gemini 2.5 Flash)")
print("="*70)

gemini_key = config.get_api_key("gemini")
if not gemini_key:
    print("❌ Gemini API key not found!")
    sys.exit(1)

print(f"📝 Topic: {TEST_TOPIC}")
print(f"⏱️  Duration: {TEST_DURATION}s")
print(f"🌍 Language: {TEST_LANGUAGE}")
print(f"🎨 Style: {TEST_STYLE}")

content_gen = ContentGenerator(api_key=gemini_key)

print(f"\n🤖 Generating script...")
script = content_gen.generate_video_script(
    topic=TEST_TOPIC,
    duration=TEST_DURATION,
    language=TEST_LANGUAGE,
    style=TEST_STYLE
)

if 'error' in script.get('metadata', {}):
    print("❌ Script generation failed!")
    sys.exit(1)

print(f"\n✅ Script Generated!")
print(f"   Title: {script['title']}")
print(f"   Scenes: {len(script['scenes'])}")
print(f"   Hashtags: {', '.join(script['hashtags'][:3])}")

# Save script as JSON
script_json = output_dir / "script.json"
with open(script_json, 'w', encoding='utf-8') as f:
    json.dump(script, f, indent=2, ensure_ascii=False)
print(f"\n💾 Script saved: {script_json}")

# =============================================================================
# STEP 2: GENERATE IMAGES (Pollinations.ai)
# =============================================================================
print("\n" + "="*70)
print("STEP 2/4: IMAGE GENERATION (Pollinations.ai - FREE)")
print("="*70)

image_gen = ImageGenerator()

images_dir = output_dir / "images"
images_dir.mkdir(exist_ok=True)

print(f"🎨 Generating {len(script['scenes'])} scene images...")
print(f"💡 Free API - might have timeouts, using retry logic")

image_files = []
for i, scene in enumerate(script['scenes'], 1):
    print(f"\n   [{i}/{len(script['scenes'])}] {scene['image_prompt'][:50]}...")

    output_path = str(images_dir / f"scene_{i:03d}.jpg")

    # Try with timeout handling
    success = image_gen.generate_image(
        prompt=scene['image_prompt'],
        output_path=output_path,
        width=1920,
        height=1080,
        enhance=True
    )

    if success:
        print(f"      ✅ Generated")
        image_files.append(output_path)
    else:
        print(f"      ⚠️ Timeout - using placeholder")
        # Create simple colored placeholder
        from PIL import Image
        placeholder = Image.new('RGB', (1920, 1080), color=(30, 30, 40))
        placeholder.save(output_path)
        image_files.append(output_path)

print(f"\n✅ Images ready: {len(image_files)}/{len(script['scenes'])}")

# =============================================================================
# STEP 3: GENERATE VOICE (ElevenLabs - Optional)
# =============================================================================
print("\n" + "="*70)
print("STEP 3/4: VOICE GENERATION (ElevenLabs)")
print("="*70)

elevenlabs_key = config.get_api_key("elevenlabs")
voiceover_path = None

if not elevenlabs_key:
    print("⚠️  ElevenLabs API key not configured")
    print("   Skipping voice generation")
    print("   Video will be created without voiceover")
    print("\n💡 To add voice:")
    print("   1. Get free key: https://elevenlabs.io")
    print("   2. Add to .env: ELEVENLABS_API_KEY=sk-...")
    print("   3. Re-run this test")
else:
    print(f"✅ ElevenLabs API key found")

    voice_gen = VoiceGenerator(api_key=elevenlabs_key)

    # Cost estimation
    cost_info = voice_gen.estimate_cost(script['script'])
    print(f"\n💰 Voice Generation Cost:")
    print(f"   Characters: {cost_info['character_count']:,}")
    print(f"   Duration: ~{cost_info['estimated_minutes']:.1f} minutes")
    print(f"   Free tier: {'✅ OK' if cost_info['free_tier_sufficient'] else '❌ Exceeds limit'}")

    # Generate voice
    print(f"\n🎤 Generating voiceover...")
    voiceover_file = output_dir / "voiceover.mp3"

    success = voice_gen.generate_speech(
        text=script['script'],
        voice_id="EXAVITQu4vr4xnSDxMaL",  # Bella (German Female)
        output_path=str(voiceover_file)
    )

    if success:
        print(f"✅ Voiceover generated: {voiceover_file}")
        voiceover_path = str(voiceover_file)
    else:
        print(f"❌ Voice generation failed")

# =============================================================================
# STEP 4: CREATE FINAL VIDEO (MoviePy)
# =============================================================================
print("\n" + "="*70)
print("STEP 4/4: VIDEO MONTAGE (MoviePy + FFmpeg)")
print("="*70)

video_editor = VideoEditor(resolution=(1920, 1080), fps=30)

print(f"🎬 Assembling final video...")
print(f"   Images: {len(image_files)}")
print(f"   Voiceover: {'Yes' if voiceover_path else 'No'}")
print(f"   Background Music: No")

# Create final video
final_video_path = output_dir / "final_video.mp4"

success = video_editor.create_video_from_script(
    script_data=script,
    image_files=image_files,
    voiceover_path=voiceover_path,
    music_path=None,  # TODO: Add royalty-free music
    output_path=str(final_video_path)
)

if not success:
    print("❌ Video creation failed!")
    sys.exit(1)

# Get video info
info = video_editor.get_video_info(str(final_video_path))

print(f"\n✅ Final Video Created!")
print(f"   File: {final_video_path}")
print(f"   Duration: {info['duration']:.1f}s")
print(f"   Resolution: {info['size'][0]}x{info['size'][1]}")
print(f"   Audio: {'Yes' if info['has_audio'] else 'No'}")
print(f"   Size: {info['file_size_mb']:.2f} MB")

# Create SRT subtitles
print(f"\n📝 Creating SRT subtitles...")
video_editor.add_subtitles(
    video_path=str(final_video_path),
    script_data=script,
    output_path=str(final_video_path.with_suffix('.srt'))
)

srt_file = final_video_path.with_suffix('.srt')
if srt_file.exists():
    print(f"✅ Subtitles: {srt_file}")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "="*70)
print("📊 INTEGRATION TEST SUMMARY")
print("="*70)

print(f"\n✅ Generated Content:")
print(f"   1. Script (JSON): {script_json}")
print(f"   2. Images: {len(image_files)} files in {images_dir}")
if voiceover_path:
    print(f"   3. Voiceover: {voiceover_path}")
print(f"   4. Video (MP4): {final_video_path}")
print(f"   5. Subtitles (SRT): {srt_file}")

print(f"\n🎯 Video Specs:")
print(f"   Title: {script['title']}")
print(f"   Duration: {info['duration']:.1f}s")
print(f"   Resolution: 1920x1080 (Full HD)")
print(f"   FPS: 30")
print(f"   Size: {info['file_size_mb']:.2f} MB")
print(f"   Audio: {'Yes (Voiceover)' if info['has_audio'] else 'No'}")

print(f"\n📁 Output Directory: {output_dir}")

print("\n" + "="*70)
print("✅ FULL INTEGRATION TEST COMPLETE")
print("="*70)

print(f"\n💡 Video is YouTube-ready!")
print(f"   Title: {script['title']}")
print(f"   Description: {script['description'][:100]}...")
print(f"   Hashtags: {', '.join(script['hashtags'])}")

print(f"\n🎬 Next Phase:")
print(f"   FAZ 5: YouTube Upload Module")
print(f"   - OAuth2 authentication")
print(f"   - Video upload API")
print(f"   - Metadata & thumbnail upload")
print(f"   - Publish & schedule")
