"""
VIDEOCU v1 - Voice Provider Comparison Test

Tests all 3 TTS providers:
1. Edge TTS (FREE, unlimited)
2. Google Cloud TTS (Premium, 4M free/month)
3. ElevenLabs (Premium, 10K free/month)

Generates sample audio with each provider and creates comparison report.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import time
from typing import Dict, List, Optional
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from modules import (
    UnifiedVoiceGenerator,
    EdgeTTSGenerator,
    GoogleTTSGenerator,
    VoiceGenerator
)
from config import load_config


def get_test_text(language: str = 'de') -> Dict[str, str]:
    """Get test text in different languages"""

    texts = {
        'de': {
            'short': 'Hallo, dies ist ein Test der Sprachsynthese.',
            'medium': '''
            Willkommen bei VIDEOCU. Dies ist ein Test der verschiedenen
            Text-zu-Sprache-Anbieter. Wir vergleichen die Qualität,
            Geschwindigkeit und Kosten von Edge TTS, Google Cloud und ElevenLabs.
            '''.strip(),
            'long': '''
            Künstliche Intelligenz revolutioniert die Content-Erstellung.
            Mit modernen Text-zu-Sprache-Technologien können wir natürlich
            klingende Stimmen in verschiedenen Sprachen und Stilen erzeugen.
            Edge TTS bietet kostenlose Neural-Stimmen von Microsoft.
            Google Cloud Text-to-Speech liefert Premium WaveNet-Qualität.
            Und ElevenLabs bietet die realistischsten KI-Stimmen auf dem Markt.
            Jeder Anbieter hat seine Stärken und Schwächen.
            Dieser Test hilft uns, die beste Lösung für unser YouTube-Projekt zu finden.
            '''.strip()
        },
        'en': {
            'short': 'Hello, this is a speech synthesis test.',
            'medium': '''
            Welcome to VIDEOCU. This is a test of different text-to-speech providers.
            We compare quality, speed, and cost of Edge TTS, Google Cloud, and ElevenLabs.
            '''.strip(),
            'long': '''
            Artificial intelligence is revolutionizing content creation.
            With modern text-to-speech technologies, we can generate naturally
            sounding voices in different languages and styles.
            Edge TTS offers free neural voices from Microsoft.
            Google Cloud Text-to-Speech delivers premium WaveNet quality.
            And ElevenLabs offers the most realistic AI voices on the market.
            Each provider has its strengths and weaknesses.
            This test helps us find the best solution for our YouTube project.
            '''.strip()
        }
    }

    return texts.get(language, texts['en'])


def get_file_size_mb(file_path: str) -> float:
    """Get file size in MB"""
    if os.path.exists(file_path):
        return os.path.getsize(file_path) / (1024 * 1024)
    return 0.0


def test_edge_tts(output_dir: Path, test_text: str) -> Dict:
    """Test Edge TTS provider"""

    print("\n" + "="*60)
    print("🎤 Testing Edge TTS (Microsoft)")
    print("="*60)

    results = {
        'provider': 'edge-tts',
        'status': 'unknown',
        'voices_tested': [],
        'total_time': 0,
        'avg_time_per_voice': 0,
        'files': [],
        'errors': []
    }

    try:
        generator = EdgeTTSGenerator()

        # Test 2 German voices
        voices_to_test = [
            ('katja', 'de-DE-KatjaNeural'),
            ('conrad', 'de-DE-ConradNeural')
        ]

        start_time = time.time()

        for voice_key, voice_name in voices_to_test:
            print(f"\n📢 Testing voice: {voice_name}")

            output_path = output_dir / f"edge_tts_{voice_key}.mp3"

            voice_start = time.time()
            success = generator.generate_speech(
                text=test_text,
                output_path=str(output_path),
                voice=voice_key
            )
            voice_time = time.time() - voice_start

            if success and output_path.exists():
                file_size = get_file_size_mb(str(output_path))
                print(f"  ✅ Generated: {output_path.name}")
                print(f"  ⏱️  Time: {voice_time:.2f}s")
                print(f"  📦 Size: {file_size:.2f} MB")

                results['voices_tested'].append({
                    'voice': voice_name,
                    'file': str(output_path),
                    'size_mb': file_size,
                    'time_seconds': voice_time,
                    'success': True
                })
                results['files'].append(str(output_path))
            else:
                print(f"  ❌ Failed to generate")
                results['errors'].append(f"Failed to generate {voice_name}")
                results['voices_tested'].append({
                    'voice': voice_name,
                    'success': False
                })

        results['total_time'] = time.time() - start_time
        results['avg_time_per_voice'] = results['total_time'] / len(voices_to_test)
        results['status'] = 'success' if results['files'] else 'failed'

        print(f"\n📊 Edge TTS Summary:")
        print(f"   Total time: {results['total_time']:.2f}s")
        print(f"   Success rate: {len(results['files'])}/{len(voices_to_test)}")
        print(f"   Cost: $0.00 (FREE)")

    except Exception as e:
        print(f"\n❌ Edge TTS Error: {e}")
        results['status'] = 'error'
        results['errors'].append(str(e))

    return results


def test_google_tts(output_dir: Path, test_text: str, credentials_path: Optional[str] = None) -> Dict:
    """Test Google Cloud TTS provider"""

    print("\n" + "="*60)
    print("🎤 Testing Google Cloud Text-to-Speech")
    print("="*60)

    results = {
        'provider': 'google-cloud',
        'status': 'unknown',
        'voices_tested': [],
        'total_time': 0,
        'avg_time_per_voice': 0,
        'files': [],
        'errors': []
    }

    if not credentials_path or not os.path.exists(credentials_path):
        print("⚠️  Google Cloud credentials not found")
        print(f"   Looking for: {credentials_path}")
        print("   Skipping Google Cloud TTS test")
        results['status'] = 'skipped'
        results['errors'].append('Credentials file not found')
        return results

    try:
        generator = GoogleTTSGenerator(credentials_json=credentials_path)

        # Test 2 WaveNet voices
        voices_to_test = [
            ('wavenet_a', 'de-DE-Wavenet-A', 'FEMALE'),
            ('wavenet_b', 'de-DE-Wavenet-B', 'MALE')
        ]

        start_time = time.time()

        for voice_key, voice_name, gender in voices_to_test:
            print(f"\n📢 Testing voice: {voice_name} ({gender})")

            output_path = output_dir / f"google_tts_{voice_key}.mp3"

            voice_start = time.time()
            success = generator.generate_speech(
                text=test_text,
                output_path=str(output_path),
                voice=voice_key
            )
            voice_time = time.time() - voice_start

            if success and output_path.exists():
                file_size = get_file_size_mb(str(output_path))
                print(f"  ✅ Generated: {output_path.name}")
                print(f"  ⏱️  Time: {voice_time:.2f}s")
                print(f"  📦 Size: {file_size:.2f} MB")

                results['voices_tested'].append({
                    'voice': voice_name,
                    'file': str(output_path),
                    'size_mb': file_size,
                    'time_seconds': voice_time,
                    'success': True
                })
                results['files'].append(str(output_path))
            else:
                print(f"  ❌ Failed to generate")
                results['errors'].append(f"Failed to generate {voice_name}")
                results['voices_tested'].append({
                    'voice': voice_name,
                    'success': False
                })

        results['total_time'] = time.time() - start_time
        results['avg_time_per_voice'] = results['total_time'] / len(voices_to_test)
        results['status'] = 'success' if results['files'] else 'failed'

        # Cost estimation
        cost_info = generator.estimate_cost(test_text)

        print(f"\n📊 Google Cloud TTS Summary:")
        print(f"   Total time: {results['total_time']:.2f}s")
        print(f"   Success rate: {len(results['files'])}/{len(voices_to_test)}")
        print(f"   Characters: {cost_info['characters']}")
        print(f"   Cost: ${cost_info['estimated_cost_usd']:.6f}")

        results['cost_info'] = cost_info

    except Exception as e:
        print(f"\n❌ Google Cloud TTS Error: {e}")
        results['status'] = 'error'
        results['errors'].append(str(e))

    return results


def test_elevenlabs(output_dir: Path, test_text: str, api_key: Optional[str] = None) -> Dict:
    """Test ElevenLabs provider"""

    print("\n" + "="*60)
    print("🎤 Testing ElevenLabs")
    print("="*60)

    results = {
        'provider': 'elevenlabs',
        'status': 'unknown',
        'voices_tested': [],
        'total_time': 0,
        'avg_time_per_voice': 0,
        'files': [],
        'errors': []
    }

    if not api_key:
        print("⚠️  ElevenLabs API key not found")
        print("   Skipping ElevenLabs test")
        results['status'] = 'skipped'
        results['errors'].append('API key not provided')
        return results

    try:
        generator = VoiceGenerator(api_key=api_key)

        # Test 1 voice (to save quota)
        voices_to_test = [
            ('Bella', 'EXAVITQu4vr4xnSDxMaL')  # Female, German
        ]

        start_time = time.time()

        for voice_name, voice_id in voices_to_test:
            print(f"\n📢 Testing voice: {voice_name}")

            output_path = output_dir / f"elevenlabs_{voice_name.lower()}.mp3"

            voice_start = time.time()
            success = generator.generate_speech(
                text=test_text,
                output_path=str(output_path),
                voice_id=voice_id
            )
            voice_time = time.time() - voice_start

            if success and output_path.exists():
                file_size = get_file_size_mb(str(output_path))
                print(f"  ✅ Generated: {output_path.name}")
                print(f"  ⏱️  Time: {voice_time:.2f}s")
                print(f"  📦 Size: {file_size:.2f} MB")

                results['voices_tested'].append({
                    'voice': voice_name,
                    'file': str(output_path),
                    'size_mb': file_size,
                    'time_seconds': voice_time,
                    'success': True
                })
                results['files'].append(str(output_path))
            else:
                print(f"  ❌ Failed to generate")
                results['errors'].append(f"Failed to generate {voice_name}")
                results['voices_tested'].append({
                    'voice': voice_name,
                    'success': False
                })

        results['total_time'] = time.time() - start_time
        results['avg_time_per_voice'] = results['total_time'] / len(voices_to_test)
        results['status'] = 'success' if results['files'] else 'failed'

        print(f"\n📊 ElevenLabs Summary:")
        print(f"   Total time: {results['total_time']:.2f}s")
        print(f"   Success rate: {len(results['files'])}/{len(voices_to_test)}")
        print(f"   Characters used: {len(test_text)}")

    except Exception as e:
        print(f"\n❌ ElevenLabs Error: {e}")
        results['status'] = 'error'
        results['errors'].append(str(e))

    return results


def generate_comparison_report(results: List[Dict], output_dir: Path) -> str:
    """Generate comparison report"""

    report_lines = [
        "="*70,
        "VIDEOCU v1 - TTS Provider Comparison Report",
        "="*70,
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\nTest Text Length: {len(get_test_text('de')['long'])} characters",
        "\n" + "="*70,
        "\n📊 PROVIDER COMPARISON\n",
        "="*70
    ]

    # Summary table
    report_lines.append("\n{:<20} {:<10} {:<12} {:<15} {:<10}".format(
        "Provider", "Status", "Voices", "Avg Time", "Cost"
    ))
    report_lines.append("-"*70)

    for result in results:
        provider = result['provider']
        status = result['status']
        voices_count = len([v for v in result['voices_tested'] if v.get('success')])
        avg_time = result.get('avg_time_per_voice', 0)

        # Cost info
        if provider == 'edge-tts':
            cost = "FREE"
        elif provider == 'google-cloud' and 'cost_info' in result:
            cost = f"${result['cost_info']['estimated_cost_usd']:.6f}"
        elif provider == 'elevenlabs':
            cost = "Quota-based"
        else:
            cost = "N/A"

        report_lines.append("{:<20} {:<10} {:<12} {:<15} {:<10}".format(
            provider,
            status,
            f"{voices_count} voices",
            f"{avg_time:.2f}s",
            cost
        ))

    # Detailed results
    report_lines.append("\n" + "="*70)
    report_lines.append("\n📋 DETAILED RESULTS\n")
    report_lines.append("="*70)

    for result in results:
        report_lines.append(f"\n{result['provider'].upper()}")
        report_lines.append("-"*70)
        report_lines.append(f"Status: {result['status']}")
        report_lines.append(f"Total Time: {result.get('total_time', 0):.2f}s")
        report_lines.append(f"Files Generated: {len(result['files'])}")

        if result.get('errors'):
            report_lines.append(f"\nErrors:")
            for error in result['errors']:
                report_lines.append(f"  - {error}")

        if result.get('voices_tested'):
            report_lines.append(f"\nVoices Tested:")
            for voice in result['voices_tested']:
                if voice.get('success'):
                    report_lines.append(
                        f"  ✅ {voice['voice']}: "
                        f"{voice['size_mb']:.2f} MB, "
                        f"{voice['time_seconds']:.2f}s"
                    )
                else:
                    report_lines.append(f"  ❌ {voice['voice']}: Failed")

    # Recommendations
    report_lines.append("\n" + "="*70)
    report_lines.append("\n💡 RECOMMENDATIONS\n")
    report_lines.append("="*70)

    successful_providers = [r for r in results if r['status'] == 'success']

    if successful_providers:
        # Best for cost
        report_lines.append("\n🏆 Best for COST: Edge TTS (FREE, unlimited)")

        # Best for quality
        google_success = any(r['provider'] == 'google-cloud' and r['status'] == 'success' for r in results)
        elevenlabs_success = any(r['provider'] == 'elevenlabs' and r['status'] == 'success' for r in results)

        if elevenlabs_success:
            report_lines.append("🏆 Best for QUALITY: ElevenLabs (most realistic)")
        elif google_success:
            report_lines.append("🏆 Best for QUALITY: Google Cloud (WaveNet premium)")
        else:
            report_lines.append("🏆 Best for QUALITY: Edge TTS (good Neural voices)")

        # Best for speed
        fastest = min(successful_providers, key=lambda x: x.get('avg_time_per_voice', float('inf')))
        report_lines.append(f"🏆 Best for SPEED: {fastest['provider']} ({fastest.get('avg_time_per_voice', 0):.2f}s avg)")

        # Recommended strategy
        report_lines.append("\n📋 Recommended Strategy:")
        report_lines.append("  1. Primary: Edge TTS (FREE, unlimited, good quality)")
        report_lines.append("  2. Fallback: Google Cloud (premium quality if Edge fails)")
        report_lines.append("  3. Premium: ElevenLabs (for highest quality content)")
    else:
        report_lines.append("\n⚠️  No providers succeeded. Check API keys and credentials.")

    # Audio files location
    report_lines.append("\n" + "="*70)
    report_lines.append("\n📁 Generated Audio Files\n")
    report_lines.append("="*70)
    report_lines.append(f"\nLocation: {output_dir}")
    report_lines.append("\nListen to the files to compare quality yourself:")

    for result in results:
        if result['files']:
            report_lines.append(f"\n{result['provider'].upper()}:")
            for file_path in result['files']:
                report_lines.append(f"  - {Path(file_path).name}")

    report_lines.append("\n" + "="*70)

    report_text = "\n".join(report_lines)

    # Save report
    report_path = output_dir / f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    print(f"\n📄 Report saved: {report_path}")

    return report_text


def main():
    """Run TTS provider comparison test"""

    # Set UTF-8 encoding for Windows console
    import sys
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except:
                pass

    print("="*70)
    print("VIDEOCU v1 - TTS Provider Comparison Test")
    print("="*70)

    # Load config
    config = load_config()

    # Create output directory
    output_dir = Path(__file__).parent / "output" / "voice_comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 Output directory: {output_dir}")

    # Get test text
    test_texts = get_test_text('de')
    test_text = test_texts['long']

    print(f"📝 Test text: {len(test_text)} characters")
    print(f"\n\"{test_text[:100]}...\"")

    # Test all providers
    all_results = []

    # 1. Edge TTS
    edge_results = test_edge_tts(output_dir, test_text)
    all_results.append(edge_results)

    # 2. Google Cloud TTS
    google_creds = config.get('google_tts_credentials', 'google_tts_credentials.json')
    google_results = test_google_tts(output_dir, test_text, google_creds)
    all_results.append(google_results)

    # 3. ElevenLabs
    elevenlabs_key = config.get('elevenlabs_api_key')
    elevenlabs_results = test_elevenlabs(output_dir, test_text, elevenlabs_key)
    all_results.append(elevenlabs_results)

    # Generate report
    print("\n" + "="*70)
    print("📊 Generating Comparison Report")
    print("="*70)

    report = generate_comparison_report(all_results, output_dir)
    print(report)

    # Save results as JSON
    json_path = output_dir / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Results saved: {json_path}")

    print("\n" + "="*70)
    print("✅ Comparison test completed!")
    print("="*70)
    print(f"\n📁 Check files in: {output_dir}")
    print("🎧 Listen to the audio files to compare quality")
    print("\n")


if __name__ == '__main__':
    main()
