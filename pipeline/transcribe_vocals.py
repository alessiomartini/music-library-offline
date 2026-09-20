#!/usr/bin/env python3
"""
Step 2 — vocal melody transcription.

Produces working/<slug>/vocal-events.json. The melody source is chosen per
song by songs/<slug>.json's "melodySource.type":

  - "curated": read a manually curated MusicXML reference (the file at
    melodySource.musicxml, relative to the repo root). Authoritative — use
    once a curated reference exists and has been checked against the
    recording.
  - "basic-pitch": automatic transcription (Basic Pitch) over the vocal
    stem, filtered by melodySource.vocalRange / firstVocalSec /
    velocityThreshold / minDurationTicks. Use when no curated reference
    exists yet; expect the result to need correction, same as any automatic
    transcription (see docs/FUTURE-ARCHITECTURE.md, "Human Curation Is Part
    of the Workflow").

Run with:  python pipeline/transcribe_vocals.py <slug>
"""
import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PPQ = 960


def load_song_config(slug: str) -> dict:
    path = REPO_ROOT / "songs" / f"{slug}.json"
    if not path.exists():
        raise SystemExit(f"ERROR: no song config at {path}")
    return json.loads(path.read_text())


def from_curated(config: dict):
    from music21 import converter

    musicxml_path = REPO_ROOT / config["melodySource"]["musicxml"]
    if not musicxml_path.exists():
        raise SystemExit(f"ERROR: curated melody source not found: {musicxml_path}")
    print(f"Loading curated melody from {musicxml_path}")
    score = converter.parse(str(musicxml_path))
    voice_part = score.parts[0]

    events = []
    for n in voice_part.flatten().notes:
        if n.isNote:
            events.append({
                "start": int(round(n.offset * PPQ / 4.0)),
                "duration": int(round(n.duration.quarterLength * PPQ / 4.0)),
                "pitch": n.pitch.midi,
                "velocity": 0.8,
                "kind": "note",
            })
    events.sort(key=lambda e: e["start"])
    return events, config["tempoBpm"]


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
    min_duration_ticks = source.get("minDurationTicks", 30)

    print("Running Basic Pitch transcription...")
    _, midi_data, note_events = predict(str(vocals_wav), ICASSP_2022_MODEL_PATH)
    midi_data.write(str(midi_out))

    # Index by position rather than unpacking the whole tuple: basic-pitch's
    # note_events rows carry extra trailing fields (e.g. pitch bend) we
    # don't use, and a strict `for s, e, p, v in note_events` breaks if a
    # basic-pitch version adds one.
    raw = [
        {"start_sec": float(item[0]), "end_sec": float(item[1]), "pitch": int(item[2]), "velocity": float(item[3])}
        for item in note_events
    ]
    before = len(raw)
    raw = [n for n in raw if n["start_sec"] >= first_vocal_sec]
    raw = [n for n in raw if vmin <= n["pitch"] <= vmax]
    raw = [n for n in raw if n["velocity"] >= velocity_threshold]
    print(f"Raw notes: {before} -> after filters: {len(raw)}")

    # Basic Pitch's raw note_events start/end times are real seconds, tied
    # to the actual recording — never to a musical tempo. The tempo baked
    # into the MIDI it writes is PrettyMIDI's meaningless default (120bpm),
    # not a detected value, so reading it back here silently rescaled every
    # note's tick position by song_tempo/120 and made the vocal timeline
    # drift out of sync with the harmony/measure grid (both built from the
    # song config's real tempo) over the course of the song. Always convert
    # using the song's actual tempo instead.
    tempo_bpm = config["tempoBpm"]
    seconds_per_tick = 60.0 / (tempo_bpm * PPQ)

    events = []
    for n in raw:
        start = int(round(n["start_sec"] / seconds_per_tick))
        end = int(round(n["end_sec"] / seconds_per_tick))
        duration = end - start
        if duration >= min_duration_ticks:
            events.append({
                "start": start, "duration": duration, "pitch": n["pitch"],
                "velocity": n["velocity"], "kind": "note",
            })
    events.sort(key=lambda e: e["start"])

    # Basic Pitch's raw millisecond-derived tick values rarely land on a
    # notatable duration (music21's MusicXML writer rejects "inexpressible"
    # durations outright). Snap to an eighth-note grid, with a sixteenth-note
    # minimum, then clamp against the previous event so quantization can't
    # introduce an overlap between two originally-adjacent notes.
    eighth_note = PPQ // 2
    sixteenth_note = PPQ // 4
    previous_end = 0
    for event in events:
        start = round(event["start"] / eighth_note) * eighth_note
        end = round((event["start"] + event["duration"]) / eighth_note) * eighth_note
        start = max(start, previous_end)
        duration = max(end - start, sixteenth_note)
        event["start"] = start
        event["duration"] = duration
        previous_end = start + duration

    return events, tempo_bpm


def transcribe(slug: str) -> None:
    config = load_song_config(slug)
    source_type = config["melodySource"]["type"]

    if source_type == "curated":
        events, tempo_bpm = from_curated(config)
    elif source_type == "basic-pitch":
        events, tempo_bpm = from_basic_pitch(slug, config)
    else:
        raise SystemExit(f"ERROR: unknown melodySource.type {source_type!r}")

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
