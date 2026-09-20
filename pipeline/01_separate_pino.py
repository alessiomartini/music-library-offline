#!/usr/bin/env python3
"""
Chunk 1: Source Separation for Pino Daniele - E cerca 'e me capi
Separates the input MP3 into vocal and accompaniment stems using Demucs.
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

# Add pipeline to path
sys.path.insert(0, str(Path(__file__).parent))

INPUT_MP3 = Path(__file__).parent.parent / "input" / "Pino Daniele - E cerca 'e me capi'.mp3"
WORKING_DIR = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi"
OUTPUT_DIR = WORKING_DIR / "demucs_output"

def run_demucs():
    """Run Demucs source separation."""
    print(f"Input: {INPUT_MP3}")
    print(f"Working dir: {WORKING_DIR}")

    if not INPUT_MP3.exists():
        print(f"ERROR: Input file not found: {INPUT_MP3}")
        return False

    WORKING_DIR.mkdir(parents=True, exist_ok=True)

    # Run Demucs with htdemucs model (best quality)
    song_name = "Pino Daniele - E cerca 'e me capi"
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "--two-stems=vocals",  # Only separate vocals vs rest
        "-n", "htdemucs",      # Use htdemucs model (high quality)
        "-o", str(WORKING_DIR / "demucs_output"),
        str(INPUT_MP3)
    ]

    print("Running Demucs source separation...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Demucs failed: {result.stderr}")
        return False

    print("Demucs completed successfully!")
    print(result.stdout)

    # Find output files
    htdemucs_dir = WORKING_DIR / "demucs_output" / "htdemucs"
    # Demucs may create directory with slightly different name, find it
    song_dirs = list(htdemucs_dir.iterdir())
    if not song_dirs:
        print(f"ERROR: No song directory found in {htdemucs_dir}")
        return False
    output_subdir = song_dirs[0]

    vocals_wav = output_subdir / "vocals.wav"
    accompaniment_wav = output_subdir / "no_vocals.wav"

    if vocals_wav.exists() and accompaniment_wav.exists():
        # Copy to working directory with simpler names
        final_vocals = WORKING_DIR / "vocals.wav"
        final_accompaniment = WORKING_DIR / "accompaniment.wav"

        shutil.copy2(vocals_wav, final_vocals)
        shutil.copy2(accompaniment_wav, final_accompaniment)

        print(f"\nOutput files:")
        print(f"  Vocals: {final_vocals}")
        print(f"  Accompaniment: {final_accompaniment}")
        return True
    else:
        print(f"ERROR: Output files not found in {output_subdir}")
        return False

if __name__ == "__main__":
    success = run_demucs()
    sys.exit(0 if success else 1)