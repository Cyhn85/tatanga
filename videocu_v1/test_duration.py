"""
Test duration control in PRO Pipeline
"""
import os
import sys
import logging
import shutil
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

from dotenv import load_dotenv
load_dotenv()

from modules.pro_video_pipeline import ProVideoPipeline

def test_duration():
    print('=== DURATION CONTROL TEST ===')
    print()

    # Remove old test output
    output_dir = Path('output/duration_test')
    if output_dir.exists():
        shutil.rmtree(output_dir)

    pipeline = ProVideoPipeline(
        gemini_api_key=os.getenv('GEMINI_API_KEY'),
        pixabay_api_key=os.getenv('PIXABAY_API_KEY'),
        pexels_api_key=os.getenv('PEXELS_API_KEY')
    )

    # Short test
    article_data = {
        'title': 'Test Duration',
        'text': 'Dies ist ein kurzer Test. Die Technologie entwickelt sich weiter.',
        'images': [],
        'video_script': {
            'intro': 'Willkommen.',
            'main_points': ['Kurzer Test.'],
            'outro': 'Danke.'
        }
    }

    TARGET_DURATION = 15  # 15 seconds target

    result = pipeline.produce_video_from_article(
        article_data=article_data,
        output_dir=str(output_dir),
        language='de',
        duration=TARGET_DURATION,
        use_article_images=False,
        use_stock_videos=True
    )

    print()
    print('=== RESULT ===')
    print(f'Success: {result.get("success")}')

    # Check actual video duration
    video_path = result.get('files', {}).get('video')
    if video_path and Path(video_path).exists():
        ffprobe_path = r'C:\Users\cyhnsrgc\AppData\Local\Microsoft\WinGet\Links\ffprobe.exe'
        cmd = [ffprobe_path,
               '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(proc.stdout.strip())
        print(f'Video duration: {duration:.1f}s (target was {TARGET_DURATION}s)')

        # Also check voiceover duration
        vo_path = result.get('files', {}).get('voiceover')
        if vo_path and Path(vo_path).exists():
            cmd2 = [ffprobe_path,
                    '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', vo_path]
            proc2 = subprocess.run(cmd2, capture_output=True, text=True)
            vo_duration = float(proc2.stdout.strip())
            print(f'Voiceover duration: {vo_duration:.1f}s')

            if abs(duration - vo_duration) < 1.0:
                print('SUCCESS: Video duration matches voiceover!')
            else:
                print(f'PROBLEM: Duration mismatch - video {duration:.1f}s vs voiceover {vo_duration:.1f}s')
    else:
        print('Video not found!')

if __name__ == '__main__':
    test_duration()