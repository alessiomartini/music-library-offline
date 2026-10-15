#!/usr/bin/env python3
"""
Vocal range and duration-weighted pitch distribution of a song, from its recording.

    recording (YouTube, checked against the Deezer duration)
      -> Demucs vocal stem
      -> pYIN f0 track
      -> seconds sung on each note, normalized to a distribution

Writes output/vocal/<slug>.json:
    low, high          lowest / highest note sung for at least MIN_SHARE of the time
    coreLow, coreHigh  CORE_PERCENTILES of the singing time (where the voice sits)
    seconds            total voiced seconds counted
    histogram          {midi note: share of the singing time}, shares sum to 1
    source             YouTube video id of the recording

The audio, the stem and the f0 track stay in input/ and working/<slug>/ (gitignored).

Run with:  python pipeline/audio_first/vocal_distribution.py <slug> --title "..." --artist "..."
"""
import argparse
import json
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from constants import (  # noqa: E402
    VOCAL_CORE_PERCENTILES,
    VOCAL_DURATION_TOLERANCE_S,
    VOCAL_FMAX,
    VOCAL_FMIN,
    VOCAL_HOP_S,
    VOCAL_MEDIAN_FRAMES,
    VOCAL_MIN_RUN_S,
    VOCAL_MIN_SHARE,
    VOCAL_VOICED_PROB,
)

REPO_ROOT = Path(__file__).parent.parent.parent


def note_seconds(f0_hz: np.ndarray, voiced_prob: np.ndarray, hop_s: float, min_prob: float = VOCAL_VOICED_PROB,
                 min_run_s: float = VOCAL_MIN_RUN_S, median_frames: int = VOCAL_MEDIAN_FRAMES) -> dict[int, float]:
    """Seconds sung on each MIDI note. Frames without f0 (pYIN's unvoiced decision) or below `min_prob`
    are silence; the pitch is median-smoothed so vibrato doesn't flip the rounded note, and runs of
    one note shorter than `min_run_s` (stem bleed, octave jumps) are dropped."""
    from scipy.ndimage import median_filter
    ok = (voiced_prob >= min_prob) & np.isfinite(f0_hz) & (f0_hz > 0)
    midi = np.zeros(len(f0_hz))
    midi[ok] = 69 + 12 * np.log2(f0_hz[ok] / 440.0)
    if median_frames > 1:
        midi = median_filter(midi, size=median_frames)
    notes = np.where(ok, np.rint(midi), -1).astype(int)
    seconds: dict[int, float] = {}
    start = 0
    for i in range(1, len(notes) + 1):
        if i == len(notes) or notes[i] != notes[start]:
            run = (i - start) * hop_s
            if notes[start] >= 0 and run >= min_run_s:
                seconds[int(notes[start])] = seconds.get(int(notes[start]), 0.0) + run
            start = i
    return seconds


def distribution(seconds: dict[int, float], min_share: float = VOCAL_MIN_SHARE,
                 core: tuple[float, float] = VOCAL_CORE_PERCENTILES) -> dict:
    """Normalized histogram, range and core (percentiles of singing time) from note seconds."""
    total = sum(seconds.values())
    if total == 0:
        raise ValueError("no sung notes")
    hist = {n: s / total for n, s in sorted(seconds.items())}
    kept = [n for n, share in hist.items() if share >= min_share]
    cum, core_low, core_high = 0.0, None, None
    for n, share in hist.items():
        cum += share
        if core_low is None and cum >= core[0]:
            core_low = n
        if core_high is None and cum >= core[1]:
            core_high = n
    return {
        "low": min(kept), "high": max(kept), "coreLow": core_low, "coreHigh": core_high,
        "seconds": round(total, 1), "histogram": {str(n): round(s, 4) for n, s in hist.items()},
    }


def _norm(s: str) -> str:
    """"E cerca 'e me capì" -> "e cerca e me capi"."""
    s = unicodedata.normalize("NFD", s.lower())
    return " ".join("".join(c if c.isalnum() else " " for c in s if unicodedata.category(c) != "Mn").split())


def deezer_duration(title: str, artist: str) -> int | None:
    """Duration of the Deezer track with this title by this artist (first word of the credit must match)."""
    q = urllib.parse.quote(f"{artist} {title}")
    with urllib.request.urlopen(f"https://api.deezer.com/search?q={q}", timeout=30) as r:
        data = json.load(r).get("data") or []
    lead = _norm(artist.split(",")[0])
    for t in data:
        if _norm(t["title_short"]) == _norm(title) and _norm(t["artist"]["name"]) == lead:
            return t["duration"]
    return None


def find_recording(title: str, artist: str, youtube_id: str | None) -> tuple[str, int]:
    """YouTube id of the recording: the given one, or the first of five search results
    whose duration matches Deezer's within the tolerance."""
    if youtube_id:
        return youtube_id, 0
    expected = deezer_duration(title, artist)
    if expected is None:
        raise SystemExit(f"Deezer has no {title} by {artist}: pass --youtube to choose the recording by hand")
    out = subprocess.run([sys.executable, "-m", "yt_dlp", "--flat-playlist", "--print", "%(id)s\t%(duration)s",
                          f"ytsearch5:{title} {artist} audio"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        vid, dur = line.split("\t")
        if dur != "NA" and abs(float(dur) - expected) <= VOCAL_DURATION_TOLERANCE_S:
            return vid, expected
    raise SystemExit(f"No YouTube result matches the Deezer duration ({expected} s) for {title} — {artist}")


def download(slug: str, vid: str) -> Path:
    path = REPO_ROOT / "input" / f"{slug}.mp3"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        subprocess.run([sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "-x", "--audio-format", "mp3",
                        "-o", str(path.with_suffix(".%(ext)s")), f"https://www.youtube.com/watch?v={vid}"],
                       check=True, capture_output=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug")
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--youtube", help="YouTube id of the recording (skips the search)")
    args = parser.parse_args()

    t0 = time.time()
    source = REPO_ROOT / "input" / f"{args.slug}.source"
    if source.exists() and not args.youtube:
        vid, expected = source.read_text().strip(), deezer_duration(args.title, args.artist)
    else:
        vid, expected = find_recording(args.title, args.artist, args.youtube)
    download(args.slug, vid)
    source.write_text(vid + "\n")
    t1 = time.time()
    vocals = REPO_ROOT / "working" / args.slug / "vocals.wav"
    if not vocals.exists():
        from separate import run_demucs
        run_demucs(args.slug)
    t2 = time.time()

    f0_file = vocals.with_name("f0.npz")
    if not f0_file.exists():
        import librosa
        y, sr = librosa.load(vocals, sr=22050, mono=True)
        hop = int(round(VOCAL_HOP_S * sr))
        f0, _, prob = librosa.pyin(y, fmin=librosa.note_to_hz(VOCAL_FMIN), fmax=librosa.note_to_hz(VOCAL_FMAX),
                                   sr=sr, hop_length=hop)
        np.savez_compressed(f0_file, f0=f0, prob=prob, hop_s=hop / sr)
    t3 = time.time()
    track = np.load(f0_file)

    result = distribution(note_seconds(track["f0"], track["prob"], float(track["hop_s"])))
    result["source"] = vid
    out = REPO_ROOT / "output" / "vocal" / f"{args.slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{args.slug}: {result['low']}-{result['high']} (core {result['coreLow']}-{result['coreHigh']}), "
          f"{result['seconds']} s sung, youtube {vid} (Deezer {expected} s) -> {out}")
    print(f"timings: download {t1 - t0:.0f} s, separation {t2 - t1:.0f} s, pitch {t3 - t2:.0f} s")


if __name__ == "__main__":
    main()
