#!/usr/bin/env python3
"""
Vocal range and duration-weighted pitch distribution of a song, from its recording.

    recording (YouTube, checked against the Deezer duration)
      -> Demucs vocal stem
      -> pYIN f0 track
      -> seconds sung on each note and times each note is sung, normalized

Writes output/vocal/<slug>.json:
    low, high          lowest / highest note sung for at least MIN_SHARE of the time
    coreLow, coreHigh  CORE_PERCENTILES of the singing time (where the voice sits)
    seconds            total voiced seconds counted
    notes              number of sung notes counted
    histogram          {midi note: share of the singing time}, shares sum to 1
    countHistogram     {midi note: share of the sung notes (how many times)}, shares sum to 1
    source             YouTube video id of the recording

The audio, the stem and the f0 track stay in input/ and working/<slug>/ (gitignored).

Run with:  python pipeline/audio_first/vocal_distribution.py <slug> --title "..." --artist "..."
"""
import argparse
import json
import os
import re
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
    VOCAL_CONSENSUS_MAX_DIFF_S,
    VOCAL_CORE_PERCENTILES,
    VOCAL_DURATION_TOLERANCE_S,
    VOCAL_FMAX,
    VOCAL_FMIN,
    VOCAL_HOP_S,
    VOCAL_MEDIAN_FRAMES,
    VOCAL_MIN_RUN_S,
    VOCAL_MIN_SHARE,
    VOCAL_STRAY_GAP,
    VOCAL_STRAY_SHARE,
    VOCAL_VOICED_PROB,
)

REPO_ROOT = Path(__file__).parent.parent.parent


def sung_notes(f0_hz: np.ndarray, voiced_prob: np.ndarray, hop_s: float, min_prob: float = VOCAL_VOICED_PROB,
               min_run_s: float = VOCAL_MIN_RUN_S, median_frames: int = VOCAL_MEDIAN_FRAMES) -> list[tuple[int, float]]:
    """The sung notes in order, as (MIDI note, seconds). Frames without f0 (pYIN's unvoiced decision)
    or below `min_prob` are silence; the pitch is median-smoothed so vibrato doesn't flip the rounded
    note. Runs shorter than `min_run_s` (stem bleed, octave jumps) are dropped, and the same note on
    both sides of a dropped run stays one note; a silence between two equal notes makes two."""
    from scipy.ndimage import median_filter
    ok = (voiced_prob >= min_prob) & np.isfinite(f0_hz) & (f0_hz > 0)
    midi = np.zeros(len(f0_hz))
    midi[ok] = 69 + 12 * np.log2(f0_hz[ok] / 440.0)
    if median_frames > 1:
        midi = median_filter(midi, size=median_frames)
    frames = np.where(ok, np.rint(midi), -1).astype(int)
    notes: list[tuple[int, float]] = []
    last = -1  # note of the last kept run, or -1 after a silence
    start = 0
    for i in range(1, len(frames) + 1):
        if i == len(frames) or frames[i] != frames[start]:
            note, run = int(frames[start]), (i - start) * hop_s
            if note < 0:
                last = -1
            elif run >= min_run_s:
                if note == last:
                    notes[-1] = (note, notes[-1][1] + run)
                else:
                    notes.append((note, run))
                last = note
            start = i
    return notes


def distribution(notes: list[tuple[int, float]], min_share: float = VOCAL_MIN_SHARE,
                 core: tuple[float, float] = VOCAL_CORE_PERCENTILES) -> dict:
    """Two normalized histograms of the sung notes, by singing time and by number of times sung,
    plus the range and core (percentiles of the singing time). Stray notes, not joined to the range
    by a chain of notes with some singing time, are dropped first (octave errors, backing vocals)."""
    notes = drop_strays(notes, min_share)
    seconds: dict[int, float] = {}
    counts: dict[int, int] = {}
    for n, s in notes:
        seconds[n] = seconds.get(n, 0.0) + s
        counts[n] = counts.get(n, 0) + 1
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
        "seconds": round(total, 1), "notes": len(notes),
        "histogram": {str(n): round(s, 4) for n, s in hist.items()},
        "countHistogram": {str(n): round(c / len(notes), 4) for n, c in sorted(counts.items())},
    }


def drop_strays(notes: list[tuple[int, float]], min_share: float = VOCAL_MIN_SHARE,
                stray_share: float = VOCAL_STRAY_SHARE, max_gap: int = VOCAL_STRAY_GAP) -> list[tuple[int, float]]:
    """The notes without those far from the range: walking out from the range (notes with
    `min_share`), a note is kept while fewer than `max_gap` + 1 semitones in a row lack `stray_share`."""
    seconds: dict[int, float] = {}
    for n, s in notes:
        seconds[n] = seconds.get(n, 0.0) + s
    total = sum(seconds.values())
    if total == 0:
        return notes
    share = {n: s / total for n, s in seconds.items()}
    kept = [n for n, x in share.items() if x >= min_share] or list(share)
    bounds = []
    for start, step in ((min(kept), -1), (max(kept), 1)):
        edge, n, gap = start, start + step, 0
        while gap <= max_gap and min(share) <= n <= max(share):
            if share.get(n, 0) >= stray_share:
                edge, gap = n, 0
            else:
                gap += 1
            n += step
        bounds.append(edge)
    return [(n, s) for n, s in notes if bounds[0] <= n <= bounds[1]]


def _norm(s: str) -> str:
    """"E cerca 'e me capì" -> "e cerca e me capi"."""
    s = unicodedata.normalize("NFD", s.lower())
    return " ".join("".join(c if c.isalnum() else " " for c in s if unicodedata.category(c) != "Mn").split())


def _bare(title: str) -> str:
    """"Uptown Funk (feat. Bruno Mars)" -> "uptown funk"."""
    return _norm(re.sub(r"\s*[(\[].*?[)\]]", "", title))


def deezer_durations(title: str, artist: str) -> list[int]:
    """Durations of the Deezer tracks with this title by this artist (lead artist of the credit)."""
    q = urllib.parse.quote(f"{artist} {title}")
    with urllib.request.urlopen(f"https://api.deezer.com/search?q={q}", timeout=30) as r:
        data = json.load(r).get("data") or []
    lead = _norm(_lead(artist))
    return [t["duration"] for t in data if _bare(t["title_short"]) == _bare(title) and _norm(t["artist"]["name"]) == lead]


def official(channel: str | None, artist: str) -> bool:
    """A channel of the artist: "<artist> - Topic" (label audio YouTube generates), "<artist>VEVO", or the artist's own."""
    c = _norm((channel or "").removesuffix(" - Topic"))
    lead = _norm(_lead(artist))
    return bool(lead) and c.replace(" ", "") in (lead.replace(" ", ""), lead.replace(" ", "") + "vevo")


def _lead(artist: str) -> str:
    return re.split(r",| ft\.? | feat\.? | & ", artist)[0]


def pick_videos(results: list[tuple[str, float | None, str | None, int | None]], durations: list[int], artist: str,
                tolerance: float = VOCAL_DURATION_TOLERANCE_S) -> list[tuple[str, int]]:
    """Search results to try, best first, as (video id, expected duration): results whose duration
    matches one of the song's Deezer versions (album, single, live... have different lengths), the
    artist's official channels and the most viewed first; else the recording at least 3 uploads agree
    on, close to a Deezer version; else (no Deezer match at all) the artist's official uploads."""
    rank = lambda r: (not official(r[2], artist), -(r[3] or 0))  # noqa: E731
    matching = []
    for r in sorted(results, key=rank):
        for expected in durations:
            if r[1] is not None and abs(r[1] - expected) <= tolerance:
                matching.append((r[0], expected))
                break
    if matching:
        return matching
    for vid, dur, *_ in results:
        if dur is None:
            continue
        agreeing = sum(1 for r in results if r[1] is not None and abs(r[1] - dur) <= tolerance)
        if agreeing >= 3 and any(abs(dur - e) <= VOCAL_CONSENSUS_MAX_DIFF_S for e in durations):
            return [(vid, int(dur))]
    return [(r[0], int(r[1] or 0)) for r in sorted(results, key=rank) if official(r[2], artist)]


def find_recording(title: str, artist: str, youtube_id: str | None) -> list[tuple[str, int]]:
    """YouTube ids of the recording to try in order: the given one, or the best of ten search results."""
    if youtube_id:
        return [(youtube_id, 0)]
    durations = deezer_durations(title, artist)
    out = subprocess.run([sys.executable, "-m", "yt_dlp", "--flat-playlist", "--print",
                          "%(id)s	%(duration)s	%(channel)s	%(view_count)s",
                          f"ytsearch10:{title} {artist} audio"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=True).stdout
    results = []
    for line in out.splitlines():
        v, d, c, n = (line.split("	") + ["NA"] * 4)[:4]
        results.append((v, None if d == "NA" else float(d), None if c == "NA" else c, None if n == "NA" else int(n)))
    picked = pick_videos(results, durations, artist)
    if not picked:
        raise SystemExit(f"No YouTube result matches a Deezer duration ({durations} s) and none is from an official "
                         f"channel for {title} - {artist}: pass --youtube to choose the recording by hand")
    return picked


def download(slug: str, vid: str) -> Path:
    path = REPO_ROOT / "input" / f"{slug}.mp3"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        for attempt in range(3):  # YouTube refuses a download now and then; a retry usually works
            r = subprocess.run([sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "-x", "--audio-format", "mp3",
                                "-o", str(path.with_suffix(".%(ext)s")), f"https://www.youtube.com/watch?v={vid}"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                break
            time.sleep(30 * (attempt + 1))
        else:
            raise SystemExit(f"yt-dlp failed for {vid}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ''}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug")
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--youtube", help="YouTube id of the recording (skips the search)")
    parser.add_argument("--separate-only", action="store_true",
                        help="stop after the vocal stem (vocal_batch.py runs the pitch step separately)")
    args = parser.parse_args()

    t0 = time.time()
    source = REPO_ROOT / "input" / f"{args.slug}.source"
    if source.exists() and not args.youtube:
        candidates = [(source.read_text().strip(), 0)]
    else:
        candidates = find_recording(args.title, args.artist, args.youtube)
    for i, (vid, expected) in enumerate(candidates):  # some uploads are blocked here: try the next one
        try:
            download(args.slug, vid)
            break
        except SystemExit:
            if i == len(candidates) - 1:
                raise
    source.write_text(vid + "\n")
    t1 = time.time()
    vocals = REPO_ROOT / "working" / args.slug / "vocals.wav"
    if not vocals.exists():
        from separate import run_demucs
        run_demucs(args.slug)
    t2 = time.time()
    if args.separate_only:
        print(f"timings: download {t1 - t0:.0f} s, separation {t2 - t1:.0f} s")
        return

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

    result = distribution(sung_notes(track["f0"], track["prob"], float(track["hop_s"])))
    result["source"] = vid
    out = REPO_ROOT / "output" / "vocal" / f"{args.slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{args.slug}: {result['low']}-{result['high']} (core {result['coreLow']}-{result['coreHigh']}), "
          f"{result['seconds']} s sung, youtube {vid} (Deezer {expected} s) -> {out}")
    print(f"timings: download {t1 - t0:.0f} s, separation {t2 - t1:.0f} s, pitch {t3 - t2:.0f} s")


if __name__ == "__main__":
    main()
