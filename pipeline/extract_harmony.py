#!/usr/bin/env python3
"""
Step 4 — harmony extraction.

Detects chord symbols from a song's accompaniment stem using lv-chordia
(openmirlab/lv-chordia: MIT-licensed, ISMIR 2019 "Large-Vocabulary Chord
Transcription" model, an ensemble of 5 networks decoded with an HMM for
temporal smoothing; weights are bundled with the package — no separate
download needed). This replaced an earlier librosa chroma-template
per-beat matcher, which had no temporal smoothing and produced far noisier
chord boundaries.

Writes working/<slug>/harmony-events.json.

Run with:  python pipeline/extract_harmony.py <slug>
"""
import argparse
import json
import os
from pathlib import Path

from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent

# Quantize chord onsets to a sixteenth-note grid. lv-chordia's raw start
# times land at arbitrary audio-frame precision; a chord duration built
# straight from that (see the tick-tiling comment below) produces
# quarterLength fractions too fine for music21's MusicXML writer to notate
# (it caps at a 2048th note). Same rationale as the eighth-note quantization
# transcribe_vocals.py applies to basic-pitch's raw note timings.
GRID_TICKS = PPQ // 4

NOTE_TO_PC = {
    'C': 0, 'B#': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'Fb': 4,
    'F': 5, 'E#': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9,
    'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11,
}

# mir_eval scale-degree bass intervals -> semitones above the chord root.
DEGREE_TO_SEMITONES = {
    '1': 0, 'b2': 1, '2': 2, '#2': 3, 'b3': 3, '3': 4, '4': 5, '#4': 6,
    'b5': 6, '5': 7, '#5': 8, 'b6': 8, '6': 9, 'bb7': 9, 'b7': 10, '7': 11,
}

# lv-chordia (mir_eval shorthand) quality -> our supported ChordQuality
# (src/lib/score.ts). Qualities our schema can't represent are approximated
# to the nearest supported one rather than crashing or being invented; this
# is deliberate, recorded information loss (see FUTURE-ARCHITECTURE.md §5),
# not silent data corruption.
QUALITY_MAP = {
    'maj': 'major', 'min': 'minor', '7': 'dominant7', 'maj7': 'major7',
    'min7': 'minor7', 'hdim7': 'halfDiminished7',
    'dim7': 'halfDiminished7',  # our schema has no fully-diminished-7th quality
    'dim': 'minor',             # our schema has no diminished-triad quality
    'aug': 'augmented', 'sus4': 'sus4', 'sus2': 'sus4',
    'maj6': 'major6', 'min6': 'minor',
    '9': 'dominant7', 'maj9': 'major7', 'min9': 'minor7',
    '11': 'dominant7', '13': 'dominant7', '1': 'major', '5': 'major',
}


def parse_chord_label(label: str, warnings: list[str]):
    """'Eb:maj7', 'Ab:maj/5', 'N', 'X' -> (root_pc, quality, slash_bass_pc | None) or None."""
    if label in ('N', 'X'):
        return None

    root_part, _, rest = label.partition(':')
    quality_part, _, bass_part = rest.partition('/')

    root_pc = NOTE_TO_PC.get(root_part)
    if root_pc is None:
        warnings.append(f"unrecognized root {root_part!r} in {label!r}, dropping this segment")
        return None

    quality = QUALITY_MAP.get(quality_part)
    if quality is None:
        warnings.append(f"unrecognized quality {quality_part!r} in {label!r}, approximating as major")
        quality = 'major'

    slash_bass = None
    if bass_part:
        semitones = DEGREE_TO_SEMITONES.get(bass_part)
        if semitones is None:
            warnings.append(f"unrecognized bass degree {bass_part!r} in {label!r}, dropping slash bass")
        else:
            slash_bass = (root_pc + semitones) % 12

    return root_pc, quality, slash_bass


def retile_durations(events: list[dict], final_duration: int) -> list[dict]:
    """Derive each event's duration from the next event's start (see the
    tick-tiling note below); the last event gets `final_duration`."""
    for i, event in enumerate(events):
        event["duration"] = events[i + 1]["start"] - event["start"] if i + 1 < len(events) else final_duration
    return [e for e in events if e["duration"] > 0]


def dedupe_adjacent_within_measure(events: list[dict], measure_length_ticks: int) -> list[dict]:
    """Drop a chord event that repeats the one immediately before it, but
    only when both land in the same measure (e.g. a bar reading A A C D
    becomes A C D). A repeat that crosses a measure boundary — the same
    chord restated at the top of a new bar, e.g. bar N ending on D and bar
    N+1 starting on D again — is left alone: that's the ordinary way a
    chart shows the harmony continuing into a new measure, not a duplicate
    to clean up. This also absorbs the common case of two adjacent
    lv-chordia segments coming out identical from recognizer noise (e.g. a
    dropped no-chord segment) when they land in the same bar.
    """
    deduped = []
    for event in events:
        if deduped:
            previous = deduped[-1]
            same_chord = (previous["root"] == event["root"] and previous["quality"] == event["quality"]
                          and previous.get("slashBass") == event.get("slashBass"))
            same_measure = (previous["start"] // measure_length_ticks) == (event["start"] // measure_length_ticks)
            if same_chord and same_measure:
                continue
        deduped.append(event)
    return deduped


def extract_harmony(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    accompaniment = REPO_ROOT / "working" / slug / "accompaniment.wav"
    if not accompaniment.exists():
        raise SystemExit(f"ERROR: {accompaniment} not found — run separate.py first")

    from lv_chordia.chord_recognition import chord_recognition

    print(f"Running lv-chordia on {accompaniment} ...")
    results = chord_recognition(audio_path=os.path.abspath(str(accompaniment)), chord_dict_name="submission")
    print(f"{len(results)} raw segments detected")

    tempo_bpm = config["tempoBpm"]
    ticks_per_sec = tempo_bpm / 60.0 * PPQ

    warnings: list[str] = []
    events = []
    for r in results:
        parsed = parse_chord_label(r["chord"], warnings)
        if parsed is None:
            continue
        root, quality, slash_bass = parsed
        raw_start = r["start_time"] * ticks_per_sec
        start = int(round(raw_start / GRID_TICKS)) * GRID_TICKS
        event = {"start": start, "root": root, "quality": quality}
        if slash_bass is not None:
            event["slashBass"] = slash_bass
        events.append(event)

    for w in warnings:
        print(f"WARNING: {w}")

    events.sort(key=lambda e: e["start"])

    # Duration is derived from the *next* event's already-rounded start
    # rather than rounded independently from lv-chordia's end_time. Two
    # independent roundings of dependent quantities can each land on either
    # side of .5, producing stray one-tick gaps/overlaps between consecutive
    # chords (see FUTURE-ARCHITECTURE.md, "Harmony tick-tiling"). Deriving
    # duration this way guarantees exact tiling by construction.
    events = retile_durations(events, final_duration=PPQ)
    dropped_count = len(events)
    events = [e for e in events if e["duration"] > 0]
    dropped_count -= len(events)
    if dropped_count:
        print(f"Dropping {dropped_count} zero/negative-duration event(s) from coincident-start rounding")

    # Drop a chord that just repeats the previous one within the same bar
    # (lv-chordia's HMM decoding already avoids most flutter, but a dropped
    # N/X segment or a quality approximation can still leave two adjacent
    # segments identical) — but not across a bar line, where the repeat is
    # a legitimate restatement of the still-current harmony.
    ts = config["timeSignature"]
    measure_length_ticks = ts["numerator"] * PPQ * 4 // ts["denominator"]
    before_dedupe = len(events)
    merged = dedupe_adjacent_within_measure(events, measure_length_ticks)
    merged = retile_durations(merged, final_duration=PPQ)
    print(f"Deduped same-bar repeats: {before_dedupe} -> {len(merged)} events")

    output_path = REPO_ROOT / "working" / slug / "harmony-events.json"
    output_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": tempo_bpm, "harmony": merged}, indent=2))
    print(f"{len(merged)} harmony events -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    extract_harmony(args.slug)
