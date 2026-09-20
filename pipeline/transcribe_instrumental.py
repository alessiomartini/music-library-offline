#!/usr/bin/env python3
"""
Step 4.5 — instrumental transcription.

Transcribes the accompaniment stem (working/<slug>/accompaniment.wav,
produced by separate.py) into note events via Basic Pitch — the same
automatic-transcription tool transcribe_vocals.py's "basic-pitch" melody
source uses, but run polyphonically here and reduced to a piano part: the
accompaniment stem is Demucs' undifferentiated mix of every non-vocal
instrument (piano, strings, etc. — see corrections/<slug>/musicxml-audit.md
for what a fuller arrangement can contain), and transcribing all of it
literally produces a note-for-note pile no pianist could read or play.
`MAX_POLYPHONY` below keeps only the loudest simultaneous notes at each
onset, and `GRID_TICKS` quantizes to an eighth-note grid (coarser than the
melody path's sixteenth), both aimed at a legible piano reduction rather
than a literal multi-instrument transcript.

This is an independent transcription of the accompaniment audio, not a
reduction of the harmony analysis (extract_harmony.py) — the two describe
the same music from different signals and are not expected to read
identically. songs/<slug>.json's "instrumentalSource" thresholds below are
a starting point, not a tuned result — expect this to need the same kind of
human correction as any other automatic transcription (see
docs/FUTURE-ARCHITECTURE.md, "Human Curation Is Part of the Workflow").

Writes working/<slug>/instrumental-events.json and, for reference,
working/<slug>/instrumental-midi.mid (both forced to Acoustic Grand Piano —
program 0 — regardless of what Basic Pitch's own MIDI export defaults to).

Run with:  python pipeline/transcribe_instrumental.py <slug>
"""
import argparse
import json
from pathlib import Path

from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent

GRID_TICKS = PPQ // 2  # eighth note
ACOUSTIC_GRAND_PIANO = 0
DEFAULT_MAX_POLYPHONY = 6


def transcribe(slug: str) -> None:
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    accompaniment = REPO_ROOT / "working" / slug / "accompaniment.wav"
    if not accompaniment.exists():
        raise SystemExit(f"ERROR: {accompaniment} not found — run separate.py first")
    midi_out = REPO_ROOT / "working" / slug / "instrumental-midi.mid"

    source = config.get("instrumentalSource", {})
    pitch_range = source.get("pitchRange", [21, 108])  # full piano range by default
    velocity_threshold = source.get("velocityThreshold", 0.3)
    min_duration_ticks = source.get("minDurationTicks", GRID_TICKS)
    max_polyphony = source.get("maxPolyphony", DEFAULT_MAX_POLYPHONY)

    print(f"Running Basic Pitch transcription on {accompaniment} ...")
    _, midi_data, note_events = predict(str(accompaniment), ICASSP_2022_MODEL_PATH)
    for instrument in midi_data.instruments:
        instrument.program = ACOUSTIC_GRAND_PIANO
        instrument.is_drum = False
        instrument.name = "Piano"
    midi_data.write(str(midi_out))

    raw = [
        {"start_sec": float(item[0]), "end_sec": float(item[1]), "pitch": int(item[2]), "velocity": float(item[3])}
        for item in note_events
    ]
    before = len(raw)
    vmin, vmax = pitch_range
    raw = [n for n in raw if vmin <= n["pitch"] <= vmax]
    raw = [n for n in raw if n["velocity"] >= velocity_threshold]
    print(f"Raw notes: {before} -> after range/velocity filters: {len(raw)}")

    # Basic Pitch's raw note timings are real seconds, tied to the actual
    # recording, never to a musical tempo — and the tempo baked into the
    # MIDI it writes is PrettyMIDI's meaningless default (120bpm), not a
    # detected value. Reading that back would silently rescale every note's
    # tick position by song_tempo/120 and drift the instrumental timeline
    # out of sync with the voice/harmony grid (both built from the song
    # config's real tempo) over the course of the song — the same bug once
    # fixed in transcribe_vocals.py's basic-pitch path. Always convert using
    # the song's actual tempo instead.
    tempo_bpm = config["tempoBpm"]
    ticks_per_sec = tempo_bpm / 60.0 * PPQ

    events = []
    for n in raw:
        # Round independently per note (not clamped against a "previous"
        # note, unlike the monophonic vocal path): accompaniment is
        # polyphonic by nature, so two notes at different pitches
        # legitimately overlap and there is no single preceding event to
        # clamp against.
        start = round(n["start_sec"] * ticks_per_sec / GRID_TICKS) * GRID_TICKS
        end = round(n["end_sec"] * ticks_per_sec / GRID_TICKS) * GRID_TICKS
        duration = max(end - start, min_duration_ticks)
        events.append({"start": start, "duration": duration, "pitch": n["pitch"], "velocity": n["velocity"], "kind": "note"})

    # Cap simultaneous notes per onset to the loudest `max_polyphony`, for a
    # playable piano reduction instead of every instrument's every note
    # stacked into one chord.
    by_start: dict[int, list[dict]] = {}
    for event in events:
        by_start.setdefault(event["start"], []).append(event)
    limited = []
    dropped = 0
    for start, group in by_start.items():
        group.sort(key=lambda e: e["velocity"], reverse=True)
        limited.extend(group[:max_polyphony])
        dropped += max(0, len(group) - max_polyphony)
    if dropped:
        print(f"Capped polyphony at {max_polyphony} notes/onset: dropped {dropped} quieter simultaneous note(s)")
    limited.sort(key=lambda e: (e["start"], e["pitch"]))

    output_path = REPO_ROOT / "working" / slug / "instrumental-events.json"
    output_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": tempo_bpm, "events": limited}, indent=2))
    print(f"{len(limited)} instrumental note events -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    transcribe(args.slug)
