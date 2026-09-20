#!/usr/bin/env python3
"""
Step 3 — lyric alignment.

Forced alignment: given the vocal stem and the song config's already-known
lyric text, finds when each syllable is actually sung by running torchaudio's
MMS_FA (a multilingual Wav2Vec2 CTC forced aligner) over the full audio
against the flattened, romanized syllable sequence from every verse in
songs/<slug>.json's "lyrics", in order. This replaces the previous
sequential/per-verse heuristic (assign syllables to notes in order, reset at
guessed verse boundaries), which had no information about where in the
recording a syllable actually falls and broke down whenever the automatic
melody transcription's note count didn't match the syllable count.

Because CTC forced alignment naturally absorbs silence/instrumental gaps
between tokens (via the blank symbol), it does not need verse boundaries
guessed in advance, and it produces exact onset/offset timing per syllable
directly from the audio.

Vocal note pitch still comes from working/<slug>/vocal-events.json (Basic
Pitch, see transcribe_vocals.py): each syllable's aligned time window is
matched to the Basic Pitch note event active at its midpoint (nearest by
start tick if none is active there) purely to read off a pitch. Basic
Pitch's own note *boundaries* are no longer used for anything — every
output event's timing comes from the forced aligner, and there is exactly
one output event per syllable (no more notes carried with no lyric).

A syllable whose text romanizes to no character in the aligner's vocabulary
(e.g. corrupted source text) cannot be aligned and is dropped with a
warning, rather than crashing the run.

Writes working/<slug>/aligned-lyrics.json.

Run with:  python pipeline/align_lyrics.py <slug>
"""
import argparse
import json
import sys
from pathlib import Path

import torch
import librosa
from torchaudio.pipelines import MMS_FA as BUNDLE
import uroman

from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent


def safe_print(message: str) -> None:
    """print() that can't crash on a console codepage that doesn't cover a
    character in song lyrics (e.g. Windows cp1252 vs. a source file's
    mojibake or accented text)."""
    encoding = sys.stdout.encoding or "ascii"
    print(message.encode(encoding, errors="replace").decode(encoding))


# Snap syllable onsets/durations to a sixteenth-note grid: the forced
# aligner's raw frame timestamps land at arbitrary audio-frame precision,
# and an unquantized quarterLength is either rejected outright or notated
# unreadably by music21's MusicXML writer (same rationale as
# transcribe_vocals.py's and extract_harmony.py's grid quantization).
GRID_TICKS = PPQ // 4
MIN_DURATION_TICKS = GRID_TICKS


def flatten_syllables(config: dict) -> list[dict]:
    return [
        {"verse": verse["verse"], "text": syl["text"], "syllabic": syl.get("syllabic", "single")}
        for verse in config["lyrics"]
        for syl in verse["syllables"]
    ]


def romanize_syllables(syllables: list[dict], valid_chars: set[str], warnings: list[str]) -> list[str]:
    romanizer = uroman.Uroman()
    romanized = []
    for syl in syllables:
        text = romanizer.romanize_string(syl["text"]).lower().strip()
        text = "".join(c for c in text if c in valid_chars)
        if not text:
            warnings.append(f"syllable {syl['text']!r} (verse {syl['verse']!r}) romanized to nothing usable, dropping")
        romanized.append(text)
    return romanized


def align_audio(vocals_path: Path, romanized: list[str]) -> tuple[list, float]:
    """Returns (per-word TokenSpan lists, seconds-per-frame ratio) for the
    non-empty entries of `romanized`, aligned against the full vocal stem."""
    model = BUNDLE.get_model()
    model.eval()
    tokenizer = BUNDLE.get_tokenizer()
    aligner = BUNDLE.get_aligner()

    audio, _ = librosa.load(str(vocals_path), sr=BUNDLE.sample_rate, mono=True)
    waveform = torch.from_numpy(audio).unsqueeze(0)

    non_empty = [w for w in romanized if w]
    safe_print(f"Running forced alignment on {waveform.shape[1] / BUNDLE.sample_rate:.1f}s of audio, {len(non_empty)} words ...")
    with torch.inference_mode():
        emission, _ = model(waveform)

    tokens = tokenizer(non_empty)
    spans = aligner(emission[0], tokens)
    ratio = waveform.shape[1] / emission.shape[1] / BUNDLE.sample_rate
    return spans, ratio


def nearest_pitch(vocal_events: list[dict], midpoint_tick: int) -> int:
    for event in vocal_events:
        if event["start"] <= midpoint_tick < event["start"] + event["duration"]:
            return event["pitch"]
    return min(vocal_events, key=lambda e: abs(e["start"] - midpoint_tick))["pitch"]


def align(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    vocals_path = REPO_ROOT / "working" / slug / "vocals.wav"
    if not vocals_path.exists():
        raise SystemExit(f"ERROR: {vocals_path} not found — run separate.py first")
    events_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    if not events_path.exists():
        raise SystemExit(f"ERROR: {events_path} not found — run transcribe_vocals.py first")
    vocal_events = sorted(json.loads(events_path.read_text())["events"], key=lambda e: e["start"])

    syllables = flatten_syllables(config)
    safe_print(f"Syllables in song config: {len(syllables)}")

    warnings: list[str] = []
    valid_chars = set(BUNDLE.get_dict(star=None)) - {"-"}
    romanized = romanize_syllables(syllables, valid_chars, warnings)
    for w in warnings:
        safe_print(f"WARNING: {w}")

    spans, ratio = align_audio(vocals_path, romanized)

    tempo_bpm = config["tempoBpm"]
    ticks_per_sec = tempo_bpm / 60.0 * PPQ

    aligned = []
    span_i = 0
    previous_end = 0
    dropped = 0
    for syl, word in zip(syllables, romanized):
        if not word:
            dropped += 1
            continue
        span = spans[span_i]
        span_i += 1

        start_sec = span[0].start * ratio
        end_sec = span[-1].end * ratio
        start = round(start_sec * ticks_per_sec / GRID_TICKS) * GRID_TICKS
        end = round(end_sec * ticks_per_sec / GRID_TICKS) * GRID_TICKS
        start = max(start, previous_end)
        duration = max(end - start, MIN_DURATION_TICKS)

        pitch = nearest_pitch(vocal_events, start + duration // 2)
        aligned.append({
            "start": start,
            "duration": duration,
            "pitch": pitch,
            "lyric": {"verse": syl["verse"], "text": syl["text"], "syllabic": syl["syllabic"]},
        })
        previous_end = start + duration

    safe_print(f"Aligned {len(aligned)}/{len(syllables)} syllables ({dropped} dropped, unalignable text)")

    output_path = REPO_ROOT / "working" / slug / "aligned-lyrics.json"
    output_path.write_text(json.dumps({
        "ppq": PPQ,
        "aligned": aligned,
        "total_syllables": len(syllables),
        "syllables_dropped": dropped,
    }, indent=2))
    safe_print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    align(args.slug)
