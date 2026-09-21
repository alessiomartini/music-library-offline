#!/usr/bin/env python3
"""
Step 3 — lyric alignment.

Forced alignment: given the vocal stem and the song config's already-known
lyric text, finds when each syllable is actually sung by running torchaudio's
MMS_FA (a multilingual Wav2Vec2 CTC forced aligner) over the full audio
against the flattened, romanized syllable sequence from every verse in
songs/<slug>.json's "lyrics", in order. Because CTC forced alignment
naturally absorbs silence/instrumental gaps between tokens (via the blank
symbol), it needs no verse-boundary guessing, and it produces exact
onset/offset timing per syllable directly from the audio.

Each syllable's aligned onset is then attached to whichever
working/<slug>/vocal-events.json note (transcribe_vocals.py: Basic Pitch
detection, MuseScore-quantized — see musescore_import.py) is sounding at
that instant, or the nearest one if none is. The notes themselves — their
pitch *and* timing — are never altered or fabricated here: forced alignment
only decides which note each syllable belongs to. When a passage has more
sung syllables than detected notes (common — automatic transcription misses
notes a human wouldn't), more than one syllable lands on the same note,
which the schema already supports (a note's "lyrics" is a list); a note
that gets none keeps its pitch with no lyric, same as an ordinary
wordless/melisma-continuation note.

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


# If a syllable's aligned instant isn't inside any detected note, only
# attach it to the nearest one when that note starts within this many
# seconds — otherwise it's very likely a real gap in transcribe_vocals.py's
# detection (a passage with no notes at all), and forcing an attachment
# there would silently pile unrelated syllables from a real gap onto
# whatever note happens to be nearest, arbitrarily far away.
MAX_FALLBACK_GAP_SECONDS = 1.5


def find_note_index(vocal_events: list[dict], tick: int, max_gap_ticks: int) -> int | None:
    for i, event in enumerate(vocal_events):
        if event["start"] <= tick < event["start"] + event["duration"]:
            return i
    nearest_i = min(range(len(vocal_events)), key=lambda i: abs(vocal_events[i]["start"] - tick))
    nearest = vocal_events[nearest_i]
    if tick >= nearest["start"] + nearest["duration"]:
        gap = tick - (nearest["start"] + nearest["duration"])
    else:
        gap = nearest["start"] - tick
    return nearest_i if gap <= max_gap_ticks else None


def align(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    vocals_path = REPO_ROOT / "working" / slug / "vocals.wav"
    if not vocals_path.exists():
        raise SystemExit(f"ERROR: {vocals_path} not found — run separate.py first")
    events_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    if not events_path.exists():
        raise SystemExit(f"ERROR: {events_path} not found — run transcribe_vocals.py first")
    vocal_events = sorted(json.loads(events_path.read_text())["events"], key=lambda e: e["start"])
    if not vocal_events:
        raise SystemExit(f"ERROR: no vocal notes in {events_path}")

    syllables = flatten_syllables(config)
    safe_print(f"Syllables in song config: {len(syllables)}, vocal notes: {len(vocal_events)}")

    warnings: list[str] = []
    valid_chars = set(BUNDLE.get_dict(star=None)) - {"-"}
    romanized = romanize_syllables(syllables, valid_chars, warnings)
    for w in warnings:
        safe_print(f"WARNING: {w}")

    spans, ratio = align_audio(vocals_path, romanized)

    tempo_bpm = config["tempoBpm"]
    ticks_per_sec = tempo_bpm / 60.0 * PPQ

    max_gap_ticks = round(MAX_FALLBACK_GAP_SECONDS * ticks_per_sec)
    notes_lyrics: list[list[dict]] = [[] for _ in vocal_events]
    span_i = 0
    dropped = 0
    unplaced: list[tuple[dict, float]] = []
    for syl, word in zip(syllables, romanized):
        if not word:
            dropped += 1
            continue
        span = spans[span_i]
        span_i += 1
        start_sec = span[0].start * ratio
        start_tick = round(start_sec * ticks_per_sec)
        note_index = find_note_index(vocal_events, start_tick, max_gap_ticks)
        if note_index is None:
            unplaced.append((syl, start_sec))
            continue
        notes_lyrics[note_index].append({"verse": syl["verse"], "text": syl["text"], "syllabic": syl["syllabic"]})

    aligned = []
    notes_with_lyrics = 0
    max_syllables_per_note = 0
    for event, lyrics in zip(vocal_events, notes_lyrics):
        entry = {"start": event["start"], "duration": event["duration"], "pitch": event["pitch"]}
        if lyrics:
            entry["lyrics"] = lyrics
            notes_with_lyrics += 1
            max_syllables_per_note = max(max_syllables_per_note, len(lyrics))
        aligned.append(entry)

    placed = len(syllables) - dropped - len(unplaced)
    safe_print(f"Placed {placed}/{len(syllables)} syllables onto {notes_with_lyrics}/{len(vocal_events)} notes "
               f"({dropped} dropped as unalignable text, {len(unplaced)} unplaced — more than {MAX_FALLBACK_GAP_SECONDS}s from any detected note)")
    if max_syllables_per_note > 1:
        safe_print(f"NOTE: up to {max_syllables_per_note} syllables landed on the same note (fewer detected notes than sung syllables here) — check working/{slug}/voice.musicxml")
    if unplaced:
        safe_print("Unplaced syllables (likely a gap in transcribe_vocals.py's note detection around these times):")
        group_start = unplaced[0][1]
        group_texts = [unplaced[0][0]["text"]]
        for (syl, sec), (prev_syl, prev_sec) in zip(unplaced[1:], unplaced):
            if sec - prev_sec > MAX_FALLBACK_GAP_SECONDS:
                safe_print(f"  ~{group_start:.1f}s-{prev_sec:.1f}s: {' '.join(group_texts)!r}")
                group_start = sec
                group_texts = []
            group_texts.append(syl["text"])
        safe_print(f"  ~{group_start:.1f}s-{unplaced[-1][1]:.1f}s: {' '.join(group_texts)!r}")

    output_path = REPO_ROOT / "working" / slug / "aligned-lyrics.json"
    output_path.write_text(json.dumps({
        "ppq": PPQ,
        "aligned": aligned,
        "total_syllables": len(syllables),
        "syllables_dropped": dropped,
        "syllables_unplaced": len(unplaced),
        "notes_without_lyrics": len(vocal_events) - notes_with_lyrics,
    }, indent=2))
    safe_print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    align(args.slug)
