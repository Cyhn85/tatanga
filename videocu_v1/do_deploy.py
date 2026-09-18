"""
Modal deploy script - Windows encoding fix
"""
import subprocess
import sys
import os

os.chdir(r"c:\Users\cyhnsrgc\Desktop\CSS BOT\videocu_v1")

# Set encoding
os.environ["PYTHONIOENCODING"] = "utf-8"

result = subprocess.run(
    [sys.executable, "-m", "modal", "deploy", "modal_music_studio.py"],
    capture_output=False,
    text=True,
    encoding="utf-8",
    errors="replace"
)

print(f"\nDeploy completed with code: {result.returncode}")