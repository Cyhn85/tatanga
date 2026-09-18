"""
VIDEOCU v1 - Content Generation Pipeline Test
Full test: Script → Images → Voice
"""

import sys
import logging
import os
from pathlib import Path

# Set UTF-8 encoding
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from modules import ContentGenerator, ImageGenerator, VoiceGenerator
import config

print("\n" + "="*70)
print("🎬 VIDEOCU v1 - CONTENT GENERATION PIPELINE TEST")
print("="*70)

# Check API keys
print("\n📋 Checking API Keys...")
api_status = config.validate_api_keys()
for service, available in api_status.items():
    status = "✅" if available else "❌"
    print(f"   {status} {service.capitalize()}")

# =============================================================================
# PHASE 1: SCRIPT GENERATION (Gemini AI)
# =============================================================================
print("\n" + "="*70)
print("PHASE 1: SCRIPT GENERATION (Gemini AI)")
print("="*70)

gemini_key = config.get_api_key("gemini")
if not gemini_key:
    print("❌ ERROR: Gemini API key not found!")
    sys.exit(1)

print(f"✅ Gemini API key found: {gemini_key[:20]}...")

# Initialize generator
content_gen = ContentGenerator(api_key=gemini_key)

# Test topic
test_topic = "Künstliche Intelligenz Trends 2025 in Deutschland"
print(f"\n📝 Topic: {test_topic}")
print(f"⏱️ Duration: 60 seconds")
print(f"🌍 Language: Deutsch")
print(f"🎨 Style: Informativ")

# Generate script
print(f"\n🤖 Generating script with Gemini AI...")
script = content_gen.generate_video_script(
    topic=test_topic,
    duration=60,
    language='de',
    style='informativ'
)

if 'error' in script.get('metadata', {}):
    print("❌ Script generation failed!")
    sys.exit(1)

print(f"\n✅ Script Generated Successfully!")
print(f"\n📌 Title: {script['title']}")
print(f"📖 Description: {script['description'][:150]}...")
print(f"🎣 Hook: {script['hook']}")
print(f"📊 Scenes: {len(script['scenes'])}")
print(f"🏷️ Hashtags: {', '.join(script['hashtags'][:5])}")

print(f"\n📜 Full Script Preview:")
print(f"   {script['script'][:300]}...")

print(f"\n🎬 Scenes Breakdown:")
for i, scene in enumerate(script['scenes'][:3], 1):
    print(f"\n   Scene {i} ({scene['time']}):")
    print(f"   📝 Text: {scene['text'][:80]}...")
    print(f"   🎨 Visual: {scene['visual'][:60]}...")

# Save script to file
output_dir = Path("output/test_content")
output_dir.mkdir(parents=True, exist_ok=True)

script_file = output_dir / "script.txt"
with open(script_file, 'w', encoding='utf-8') as f:
    f.write(f"TITLE: {script['title']}\n\n")
    f.write(f"DESCRIPTION:\n{script['description']}\n\n")
    f.write(f"HOOK: {script['hook']}\n\n")
    f.write(f"SCRIPT:\n{script['script']}\n\n")
    f.write(f"HASHTAGS: {', '.join(script['hashtags'])}\n")

print(f"\n💾 Script saved to: {script_file}")

# =============================================================================
# PHASE 2: IMAGE GENERATION (Pollinations.ai - FREE!)
# =============================================================================
print("\n" + "="*70)
print("PHASE 2: IMAGE GENERATION (Pollinations.ai)")
print("="*70)

image_gen = ImageGenerator()

print(f"🎨 Generating images for {len(script['scenes'])} scenes...")
print(f"💡 Using FREE Pollinations.ai API (no key needed!)")

# Generate images from scenes
images_dir = output_dir / "images"
images_dir.mkdir(exist_ok=True)

image_files = image_gen.generate_from_scenes(
    scenes=script['scenes'],
    output_dir=str(images_dir),
    width=1920,
    height=1080
)

print(f"\n✅ Generated {len(image_files)} images!")
for i, img_file in enumerate(image_files, 1):
    info = image_gen.get_image_info(img_file)
    if info:
        print(f"   {i}. {Path(img_file).name} - {info['width']}x{info['height']} ({info['size_kb']:.1f} KB)")

# Generate YouTube thumbnail
print(f"\n🖼️ Generating YouTube thumbnail...")
thumbnail_path = output_dir / "thumbnail.jpg"
success = image_gen.create_thumbnail(
    prompt=f"{script['title']}, youtube thumbnail, professional design",
    output_path=str(thumbnail_path),
    style="clickbait"
)

if success:
    print(f"✅ Thumbnail created: {thumbnail_path}")

# =============================================================================
# PHASE 3: VOICE GENERATION (ElevenLabs)
# =============================================================================
print("\n" + "="*70)
print("PHASE 3: VOICE GENERATION (ElevenLabs)")
print("="*70)

elevenlabs_key = config.get_api_key("elevenlabs")

if not elevenlabs_key:
    print("⚠️ ElevenLabs API key not configured")
    print("   Voice generation will be skipped")
    print("   Get your free key at: https://elevenlabs.io")
    voice_generated = False
else:
    print(f"✅ ElevenLabs API key found: {elevenlabs_key[:20]}...")

    voice_gen = VoiceGenerator(api_key=elevenlabs_key)

    # Show available voices
    print(f"\n🎤 Available Voices:")
    voices = voice_gen.get_available_voices()
    for voice_id, voice_name in list(voices.items())[:3]:
        print(f"   - {voice_name}")

    # Show usage info
    usage = voice_gen.get_usage_info()
    if usage:
        print(f"\n📊 API Usage:")
        print(f"   Characters: {usage['character_count']:,} / {usage['character_limit']:,}")
        print(f"   Tier: {usage['tier']}")

    # Estimate cost
    cost_info = voice_gen.estimate_cost(script['script'])
    print(f"\n💰 Cost Estimation:")
    print(f"   Characters: {cost_info['character_count']:,}")
    print(f"   Duration: ~{cost_info['estimated_minutes']:.1f} minutes")
    print(f"   Free tier OK: {'✅ Yes' if cost_info['free_tier_sufficient'] else '❌ No'}")

    # Generate voice
    print(f"\n🎤 Generating voiceover...")
    voice_file = output_dir / "voiceover.mp3"

    success = voice_gen.generate_speech(
        text=script['script'],
        voice_id="EXAVITQu4vr4xnSDxMaL",  # Bella (German Female)
        output_path=str(voice_file)
    )

    if success:
        print(f"✅ Voice generated: {voice_file}")
        voice_generated = True
    else:
        print(f"❌ Voice generation failed")
        voice_generated = False

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*70)
print("📊 PIPELINE TEST SUMMARY")
print("="*70)

summary = {
    "Script Generation": "✅ Success" if script else "❌ Failed",
    "Image Generation": f"✅ {len(image_files)} images" if image_files else "❌ Failed",
    "Thumbnail": "✅ Created" if success else "❌ Failed",
    "Voice Generation": "✅ Success" if voice_generated else "⚠️ Skipped (no API key)"
}

for phase, status in summary.items():
    print(f"   {phase}: {status}")

print(f"\n📁 Output Directory: {output_dir}")
print(f"   - script.txt")
if image_files:
    print(f"   - images/ ({len(image_files)} images)")
if success:
    print(f"   - thumbnail.jpg")
if voice_generated:
    print(f"   - voiceover.mp3")

print("\n" + "="*70)
print("✅ CONTENT GENERATION PIPELINE TEST COMPLETE")
print("="*70)

print("\n💡 Next Steps:")
print("   1. Review generated content in output/test_content/")
print("   2. Add ElevenLabs API key for voice generation")
print("   3. Proceed to FAZ 4: Video Montage (MoviePy + FFmpeg)")
