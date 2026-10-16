#!/usr/bin/env python3
"""
Runs vocal_distribution.py on a list of songs, a few at a time.

The list is a TSV file, one song per line:  slug<TAB>title<TAB>artist[<TAB>youtube id]
Songs that already have output/vocal/<slug>.json are skipped, so an interrupted
run resumes where it stopped. Failures (no matching recording, Demucs errors...)
are logged to working/vocal-batch.log and the batch goes on.

Measured on this PC (2026-10-16, Demucs htdemucs, overlap 0.1, 148 s of audio):
  CPU, one song          123 s
  CPU, two in parallel   ~1.25x the throughput (each Demucs run uses 4 of 8 threads)
  GPU (MX150), --gpu     76 s; a CPU song alongside gains almost nothing
So with --gpu one song at a time is separated on the GPU (the 2 GB card holds one
Demucs run) while the other worker does the download or the pitch step on the CPU.
--gpu needs .venv with the CUDA build of PyTorch and Demucs (see README).

Run with:  python pipeline/audio_first/vocal_batch.py songs.tsv [--gpu] [--jobs 2]
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = Path(__file__).parent / "vocal_distribution.py"
LOG = REPO_ROOT / "working" / "vocal-batch.log"
GPU_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

gpu_lock = threading.Lock()


def call(cmd: list[str], env: dict[str, str]) -> tuple[bool, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    lines = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, lines[-1] if lines else ""


def run(song: list[str], gpu: bool) -> tuple[str, bool, str]:
    slug, title, artist, *rest = song
    cmd = [sys.executable, str(SCRIPT), slug, "--title", title, "--artist", artist]
    if rest and rest[0]:
        cmd += ["--youtube", rest[0]]
    if not gpu:
        return slug, *call(cmd, dict(os.environ))
    env = dict(os.environ, DEMUCS_PYTHON=str(GPU_PYTHON), DEMUCS_DEVICE="cuda")
    with gpu_lock:
        ok, last = call(cmd + ["--separate-only"], env)
    if not ok:
        return slug, ok, last
    return slug, *call(cmd, env)  # stems are cached now: only the pitch step runs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # song titles in a cp1252 console
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("songs", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--gpu", action="store_true", help="separate on the GPU, one song at a time")
    args = parser.parse_args()
    if args.gpu and not GPU_PYTHON.exists():
        raise SystemExit(f"--gpu needs {GPU_PYTHON} with the CUDA build of PyTorch and Demucs")

    songs = [line.split("\t") for line in args.songs.read_text(encoding="utf-8").splitlines() if line.strip()]
    todo = [s for s in songs if not (REPO_ROOT / "output" / "vocal" / f"{s[0]}.json").exists()]
    print(f"{len(songs)} songs, {len(songs) - len(todo)} already measured, {len(todo)} to do")
    LOG.parent.mkdir(exist_ok=True)
    start, done = time.time(), 0
    with ThreadPoolExecutor(args.jobs) as pool, LOG.open("a", encoding="utf-8") as log:
        for slug, ok, last in pool.map(lambda s: run(s, args.gpu), todo):
            done += 1
            line = f"{'ok' if ok else 'FAILED'}\t{slug}\t{last}"
            log.write(line + "\n")
            log.flush()
            print(f"[{done}/{len(todo)}, {(time.time() - start) / done:.0f} s/song] {line}", flush=True)


if __name__ == "__main__":
    main()
