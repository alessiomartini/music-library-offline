#!/usr/bin/env python3
"""
Step 2 — vocal melody transcription.

Produces working/<slug>/vocal-events.json: Basic Pitch detects notes from
the vocal stem (filtered by songs/<slug>.json's melodySource.vocalRange /
firstVocalSec / velocityThreshold / minDurationTicks), and MuseScore 4
(see musescore_import.py) quantizes and notates them — replacing this
script's former hand-rolled fixed-grid snap, which produced far worse
notation than opening the same raw MIDI directly in MuseScore. Expect the
result to still need correction, same as any automatic transcription (see
docs/FUTURE-ARCHITECTURE.md, "Human Curation Is Part of the Workflow").

Run with:  python pipeline/audio_first/transcribe_vocals.py <slug>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # pipeline/ — shared constants.py, musescore_import.py, etc.
import musescore_import
from constants import PPQ, VOICE_PROGRAM

REPO_ROOT = Path(__file__).parent.parent.parent


def load_song_config(slug: str) -> dict:
    path = REPO_ROOT / "songs" / f"{slug}.json"
    if not path.exists():
        raise SystemExit(f"ERROR: no song config at {path}")
    return json.loads(path.read_text())


def from_basic_pitch(slug: str, config: dict):
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    vocals_wav = REPO_ROOT / "working" / slug / "vocals.wav"
    midi_out = REPO_ROOT / "working" / slug / "vocal-midi.mid"
    if not vocals_wav.exists():
        raise SystemExit(f"ERROR: {vocals_wav} not found — run separate.py first")

    source = config["melodySource"]
    vmin, vmax = source.get("vocalRange", [40, 84])
    first_vocal_sec = source.get("firstVocalSec", 0.5)
    velocity_threshold = source.get("velocityThreshold", 0.3)
    tempo_bpm = config["tempoBpm"]
    min_duration_sec = source.get("minDurationTicks", 30) * 60.0 / (tempo_bpm * PPQ)

    print("Running Basic Pitch transcription...")
    # midi_tempo: without it, predict() writes PrettyMIDI's meaningless
    # 120bpm default into the MIDI file rather than a detected value, which
    # would make MuseScore's import land at the wrong absolute times.
    _, midi_data, _ = predict(str(vocals_wav), ICASSP_2022_MODEL_PATH, midi_tempo=tempo_bpm)

    instrument = midi_data.instruments[0]
    before = len(instrument.notes)
    instrument.notes = [
        n for n in instrument.notes
        if n.start >= first_vocal_sec
        and vmin <= n.pitch <= vmax
        and n.velocity / 127.0 >= velocity_threshold
        and n.end - n.start >= min_duration_sec
    ]
    print(f"Raw notes: {before} -> after filters: {len(instrument.notes)}")
    instrument.program = VOICE_PROGRAM
    instrument.name = "Voice"
    instrument.is_drum = False
    midi_data.write(str(midi_out))

    ts = config["timeSignature"]
    measure_length_quarters = ts["numerator"] * 4 / ts["denominator"]
    events = musescore_import.import_midi(midi_out, measure_length_quarters)
    before_mono = len(events)
    events = musescore_import.enforce_monophonic(events)
    if len(events) != before_mono:
        print(f"Resolved {before_mono - len(events)} overlapping note(s) to a single vocal line: {before_mono} -> {len(events)}")

    return events, tempo_bpm


def transcribe(slug: str) -> None:
    config = load_song_config(slug)
    events, tempo_bpm = from_basic_pitch(slug, config)

    output_path = REPO_ROOT / "working" / slug / "vocal-events.json"
    output_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": tempo_bpm, "events": events}, indent=2))
    print(f"{len(events)} vocal events -> {output_path}")
    if events:
        pitches = [e["pitch"] for e in events]
        print(f"Pitch range: {min(pitches)}-{max(pitches)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    transcribe(args.slug)
