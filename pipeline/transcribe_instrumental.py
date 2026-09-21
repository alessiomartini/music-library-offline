#!/usr/bin/env python3
"""
Step 4.5 — instrumental transcription.

Transcribes the accompaniment stem (working/<slug>/accompaniment.wav,
produced by separate.py) into note events: Basic Pitch detects notes
(filtered by songs/<slug>.json's "instrumentalSource" thresholds), and
MuseScore 4 (see musescore_import.py) quantizes and notates them, keeping
its own polyphony/voices — replacing this script's former hand-rolled
fixed-grid snap plus fixed loudest-N-notes cap, which produced far worse
notation than opening the same raw MIDI directly in MuseScore. A polyphony
cap is still applied after import as a safety net against pathologically
dense passages, not as the primary way of making the result playable.

The accompaniment stem is Demucs' undifferentiated mix of every non-vocal
instrument (piano, strings, etc. — see corrections/<slug>/musicxml-audit.md
for what a fuller arrangement can contain), and transcribing all of it
literally can still produce a note-for-note pile no pianist could read or
play, hence the cap.

This is an independent transcription of the accompaniment audio, not a
reduction of the harmony analysis (extract_harmony.py) — the two describe
the same music from different signals and are not expected to read
identically. songs/<slug>.json's "instrumentalSource" thresholds below are
a starting point, not a tuned result — expect this to need the same kind of
human correction as any other automatic transcription (see
docs/FUTURE-ARCHITECTURE.md, "Human Curation Is Part of the Workflow").

Writes working/<slug>/instrumental-events.json and, for reference,
working/<slug>/instrumental-midi.mid (forced to Acoustic Grand Piano —
program 0 — regardless of what Basic Pitch's own MIDI export defaults to;
a piano program is what we want here, unlike the vocal path, since this is
genuinely a piano-style reduction and MuseScore's grand-staff import suits
it).

Run with:  python pipeline/transcribe_instrumental.py <slug>
"""
import argparse
import json
from pathlib import Path

import musescore_import
from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent

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
    vmin, vmax = source.get("pitchRange", [21, 108])  # full piano range by default
    velocity_threshold = source.get("velocityThreshold", 0.3)
    max_polyphony = source.get("maxPolyphony", DEFAULT_MAX_POLYPHONY)
    tempo_bpm = config["tempoBpm"]

    print(f"Running Basic Pitch transcription on {accompaniment} ...")
    _, midi_data, _ = predict(str(accompaniment), ICASSP_2022_MODEL_PATH, midi_tempo=tempo_bpm)

    before = 0
    after = 0
    for instrument in midi_data.instruments:
        before += len(instrument.notes)
        instrument.notes = [
            n for n in instrument.notes
            if vmin <= n.pitch <= vmax and n.velocity / 127.0 >= velocity_threshold
        ]
        after += len(instrument.notes)
        instrument.program = ACOUSTIC_GRAND_PIANO
        instrument.is_drum = False
        instrument.name = "Piano"
    print(f"Raw notes: {before} -> after range/velocity filters: {after}")
    midi_data.write(str(midi_out))

    ts = config["timeSignature"]
    measure_length_quarters = ts["numerator"] * 4 / ts["denominator"]
    events = musescore_import.import_midi(midi_out, measure_length_quarters)

    by_start: dict[int, list[dict]] = {}
    for event in events:
        by_start.setdefault(event["start"], []).append(event)
    limited = []
    dropped = 0
    for start, group in by_start.items():
        group.sort(key=lambda e: e["pitch"])
        limited.extend(group[:max_polyphony])
        dropped += max(0, len(group) - max_polyphony)
    if dropped:
        print(f"Capped polyphony at {max_polyphony} notes/onset: dropped {dropped} note(s) (no velocity data from MuseScore's import, so the highest-pitched notes were kept)")
    limited.sort(key=lambda e: (e["start"], e["pitch"]))

    output_path = REPO_ROOT / "working" / slug / "instrumental-events.json"
    output_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": tempo_bpm, "events": limited}, indent=2))
    print(f"{len(limited)} instrumental note events -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    transcribe(args.slug)
