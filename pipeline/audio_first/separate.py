#!/usr/bin/env python3
"""
Step 1 — source separation.

Splits a song's input recording (input/<slug>.mp3) into a vocal stem and an
accompaniment stem using Demucs. Works for any song with an entry in
songs/<slug>.json — no per-song script needed.

Run with:  python pipeline/audio_first/separate.py <slug>
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(Path(__file__).parent.parent))
from constants import DEMUCS_OVERLAP  # noqa: E402


def run_demucs(slug: str) -> None:
    input_path = REPO_ROOT / "input" / f"{slug}.mp3"
    working_dir = REPO_ROOT / "working" / slug

    if not input_path.exists():
        raise SystemExit(f"ERROR: input recording not found: {input_path}")

    working_dir.mkdir(parents=True, exist_ok=True)

    # DEMUCS_PYTHON can point to another interpreter (e.g. one with the CUDA build of
    # PyTorch), DEMUCS_DEVICE picks "cuda" or "cpu" (Demucs' default: cuda when available).
    cmd = [
        os.environ.get("DEMUCS_PYTHON", sys.executable), "-m", "demucs.separate",
        "--two-stems=vocals",
        "-n", "htdemucs",
        "--overlap", str(DEMUCS_OVERLAP),
        *(["-d", os.environ["DEMUCS_DEVICE"]] if os.environ.get("DEMUCS_DEVICE") else []),
        "-o", str(working_dir / "demucs_output"),
        str(input_path),
    ]
    print(f"Running Demucs on {input_path} ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit("Demucs failed")
    print(result.stdout)

    htdemucs_dir = working_dir / "demucs_output" / "htdemucs"
    song_dirs = list(htdemucs_dir.iterdir()) if htdemucs_dir.exists() else []
    if not song_dirs:
        raise SystemExit(f"ERROR: no output directory under {htdemucs_dir}")
    output_subdir = song_dirs[0]

    vocals_wav = output_subdir / "vocals.wav"
    accompaniment_wav = output_subdir / "no_vocals.wav"
    if not (vocals_wav.exists() and accompaniment_wav.exists()):
        raise SystemExit(f"ERROR: expected stems not found in {output_subdir}")

    shutil.copy2(vocals_wav, working_dir / "vocals.wav")
    shutil.copy2(accompaniment_wav, working_dir / "accompaniment.wav")
    print(f"Vocals: {working_dir / 'vocals.wav'}")
    print(f"Accompaniment: {working_dir / 'accompaniment.wav'}")

    # demucs_output is Demucs' own raw output layout, already copied above
    # into the two stems working/<slug>/ actually uses; keeping it around
    # just duplicates ~2x the audio on disk for no reason.
    shutil.rmtree(working_dir / "demucs_output")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="Song slug — matches input/<slug>.mp3 and songs/<slug>.json")
    args = parser.parse_args()
    run_demucs(args.slug)
