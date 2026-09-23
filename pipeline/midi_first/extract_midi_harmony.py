#!/usr/bin/env python3
"""
Step 4m (alternate to extract_harmony.py) — harmony extraction from a
source MIDI's own notes, for the MIDI-first path.

No ML chord recognition: groups the configured harmony/accompaniment
track(s) notes by onset, and matches each onset's pitch-class set against a
small interval-template table targeting the same ChordQuality vocabulary
extract_harmony.py's QUALITY_MAP already targets. With ground-truth MIDI
pitches instead of recognition on separated audio, this should be more
reliable, at the cost of the same "recorded, deliberate information loss"
extract_harmony.py already documents for chord qualities the schema can't
represent (e.g. a 9th chord reduces to its 7th-chord quality).

A symmetric chord (e.g. an augmented triad, which reads the same from any
of its three notes) has no single correct "root" from pitch content alone
— this is a genuine, known limitation, not a bug; see
docs/FUTURE-ARCHITECTURE.md Open Question 24 ("How should accompaniment be
represented when harmony is ambiguous?").

Writes working/<slug>/harmony-events.json — same shape as
extract_harmony.py's output.

Run with:  python pipeline/midi_first/extract_midi_harmony.py <slug>
"""
import argparse
import json
import sys
from pathlib import Path

import mido

import midi_track_utils as mtu

sys.path.insert(0, str(Path(__file__).parent.parent))  # pipeline/ — shared constants.py, harmony_utils.py, etc.
from constants import PPQ
from harmony_utils import retile_durations, dedupe_adjacent_within_measure, smooth_short_events, suggest_key

REPO_ROOT = Path(__file__).parent.parent.parent

# A "chord change" shorter than this is treated as a passing/incidental
# tone or an asynchronous instrument attack, not a real harmonic change a
# listener would perceive — see harmony_utils.smooth_short_events.
# Calibrated 2026-09-22 against a real full-band arrangement ("Anna e
# Marco"): the resulting chord count drops off a cliff between an eighth
# note (480 ticks, 501 events survive) and 600 ticks (38 events), then
# stays flat through 840 ticks before dropping again at a quarter note
# (960 ticks, 28 events) — 600 sits in the middle of that stable plateau
# rather than right on the cliff edge, where a small timing jitter would
# swing the result wildly.
MIN_CHORD_DURATION_TICKS = PPQ * 5 // 8  # 600 ticks at PPQ=960

# Chords with more distinctive tones first, so a chord with extra
# (extension) tones beyond a template still matches its richest applicable
# quality rather than an incidental smaller subset.
CHORD_TEMPLATES: list[tuple[str, frozenset[int]]] = [
    ("dominant7sus4", frozenset({0, 5, 7, 10})),
    ("halfDiminished7", frozenset({0, 3, 6, 10})),
    ("minor7", frozenset({0, 3, 7, 10})),
    ("major7", frozenset({0, 4, 7, 11})),
    ("dominant7", frozenset({0, 4, 7, 10})),
    ("major6", frozenset({0, 4, 7, 9})),
    ("augmented", frozenset({0, 4, 8})),
    ("sus4", frozenset({0, 5, 7})),
    ("minor", frozenset({0, 3, 7})),
    ("major", frozenset({0, 4, 7})),
]

# A tolerance window for "simultaneous" note onsets, since a human-played
# accompaniment track's chord tones are rarely at the exact same tick.
ONSET_GROUP_TOLERANCE_TICKS = PPQ // 16


def classify_chord(pitch_classes: set[int]) -> tuple[int, str] | None:
    """Returns (root_pc, quality) for the best-matching candidate root, or
    None if pitch_classes is empty."""
    if not pitch_classes:
        return None
    best: tuple[int, int, str] | None = None  # (template size, root, quality)
    for root in sorted(pitch_classes):  # deterministic tie-break: lowest pitch class wins
        intervals = frozenset((p - root) % 12 for p in pitch_classes)
        for quality, template in CHORD_TEMPLATES:
            if intervals == template:
                return root, quality
            if template.issubset(intervals) and (best is None or len(template) > best[0]):
                best = (len(template), root, quality)
    if best is not None:
        return best[1], best[2]
    # Fewer tones than any template (a dyad or a single note): approximate
    # from whatever third is present, defaulting to major — the same
    # fallback convention extract_harmony.py's QUALITY_MAP already uses for
    # an unpitched power-chord label ('5' -> major).
    root = min(pitch_classes)
    intervals = {(p - root) % 12 for p in pitch_classes}
    return (root, "minor") if 3 in intervals else (root, "major")


def resolve_harmony_channels(mid: mido.MidiFile, midi_source: dict, vocal_channel: int | None) -> list[int]:
    """Channel, not track: a real karaoke file commonly puts every
    instrument on one track, distinguished only by channel (see
    midi_track_utils.note_onsets_by_channel)."""
    configured = midi_source.get("harmonyChannel")
    if configured is not None:
        return configured if isinstance(configured, list) else [configured]
    configured = midi_source.get("instrumentalChannels")
    if configured is not None:
        return configured
    # Default: every note-carrying, non-drum, non-vocal channel — mirrors
    # extract_harmony.py running on the whole accompaniment stem.
    onsets = mtu.note_onsets_by_channel(mid)
    return [
        channel for channel, ticks in onsets.items()
        if ticks and channel != mtu.DRUM_CHANNEL and channel != vocal_channel
    ]


def collect_canonical_note_events(mid: mido.MidiFile, channels: list[int]) -> list[tuple[int, int]]:
    """[(canonical PPQ tick, MIDI pitch), ...] across the given channels,
    collected from all tracks."""
    wanted = set(channels)
    events = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and msg.channel in wanted:
                canonical_tick = round(abs_tick / mid.ticks_per_beat * PPQ)
                events.append((canonical_tick, msg.note))
    events.sort()
    return events


def group_onsets(note_events: list[tuple[int, int]], tolerance_ticks: int) -> list[tuple[int, list[int]]]:
    """[(group start tick, [MIDI pitches]), ...], merging onsets within
    tolerance_ticks of a group's first tick."""
    groups: list[tuple[int, list[int]]] = []
    group_start = None
    group_pitches: list[int] = []
    for tick, pitch in note_events:
        if group_start is None or tick - group_start > tolerance_ticks:
            if group_start is not None:
                groups.append((group_start, group_pitches))
            group_start = tick
            group_pitches = []
        group_pitches.append(pitch)
    if group_start is not None:
        groups.append((group_start, group_pitches))
    return groups


def build_harmony_events(note_events: list[tuple[int, int]]) -> list[dict]:
    events = []
    for start, pitches in group_onsets(note_events, ONSET_GROUP_TOLERANCE_TICKS):
        classified = classify_chord({p % 12 for p in pitches})
        if classified is None:
            continue
        root, quality = classified
        event = {"start": start, "root": root, "quality": quality}
        bass_pc = min(pitches) % 12
        if bass_pc != root:
            event["slashBass"] = bass_pc
        events.append(event)
    return events


def extract(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    midi_source = config.get("midiSource") or {}
    midi_path = mtu.find_midi_source(slug, config)
    mid = mido.MidiFile(str(midi_path), clip=True)

    vocal_channel, _ = mtu.resolve_vocal_channel(mid, midi_source)
    harmony_channels = resolve_harmony_channels(mid, midi_source, vocal_channel)
    if not harmony_channels:
        raise SystemExit(f"ERROR: no candidate harmony/accompaniment channels found in {midi_path}")
    print(f"Harmony source channel(s): {harmony_channels}")

    note_events = collect_canonical_note_events(mid, harmony_channels)
    events = build_harmony_events(note_events)
    print(f"{len(events)} raw chord group(s) detected")

    events = retile_durations(events, final_duration=PPQ)
    before_smoothing = len(events)
    events = smooth_short_events(events, MIN_CHORD_DURATION_TICKS)
    print(f"Smoothed passing/incidental chords shorter than an eighth note: {before_smoothing} -> {len(events)} events")

    ts = config["timeSignature"]
    measure_length_ticks = ts["numerator"] * PPQ * 4 // ts["denominator"]
    before_dedupe = len(events)
    merged = dedupe_adjacent_within_measure(events, measure_length_ticks)
    merged = retile_durations(merged, final_duration=PPQ)
    print(f"Deduped same-bar repeats: {before_dedupe} -> {len(merged)} events")

    vocal_events_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    if vocal_events_path.exists():
        vocal_pitches = [e["pitch"] for e in json.loads(vocal_events_path.read_text())["events"]]
        try:
            tonic, mode = suggest_key(vocal_pitches)
            print(f"Suggested key (from the vocal melody, music21 key-analysis — confirm by ear): {tonic} {mode}"
                  f" (songs/{slug}.json's originalKey is currently {config.get('originalKey')!r})")
        except Exception as e:  # music21's analyzer can fail on pathological input; never let a suggestion crash the run
            print(f"Key suggestion skipped ({e})")

    output_path = REPO_ROOT / "working" / slug / "harmony-events.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": config["tempoBpm"], "harmony": merged}, indent=2))
    print(f"{len(merged)} harmony events -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    extract(args.slug)
