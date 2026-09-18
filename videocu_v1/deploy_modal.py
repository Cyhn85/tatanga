"""Deploy Modal app with proper encoding"""
import subprocess
import sys
import os

os.chdir(r"c:\Users\cyhnsrgc\Desktop\CSS BOT\videocu_v1")
os.environ["PYTHONIOENCODING"] = "utf-8"

# Run modal deploy
result = subprocess.run(
    ["modal", "deploy", "modal_music_studio.py"],
    capture_output=False,
    text=True,
    encoding="utf-8",
    errors="replace"
)

print(f"\nDeploy exit code: {result.returncode}")