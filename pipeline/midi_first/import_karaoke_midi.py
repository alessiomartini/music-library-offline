#!/usr/bin/env python3
"""
Step 2m (alternate to transcribe_vocals.py) — vocal-track import from a
source MIDI, for the MIDI-first path (see midi-intake/README.md).

Identifies which track of a karaoke-style source MIDI carries the vocal
melody — primarily by how well each track's note onsets coincide with the
file's lyric-event ticks (GM program number is NOT trusted: karaoke MIDI
authors commonly put the vocal guide line on an unrelated instrument
program) — extracts it to a standalone MIDI, and quantizes/notates it
through MuseScore 4 exactly like transcribe_vocals.py does for Basic
Pitch's output (see musescore_import.py). No audio, no ML transcription:
the notes are whatever the source MIDI already specifies.

Produces working/<slug>/vocal-events.json, identical in shape to
transcribe_vocals.py's output, so downstream steps (assemble_musicxml.py,
musicxml_to_json.py) don't need to know which path produced it.

Run with:  python pipeline/midi_first/import_karaoke_midi.py <slug>
"""
import argparse
import json
import sys
from pathlib import Path

import mido

import midi_track_utils as mtu

sys.path.insert(0, str(Path(__file__).parent.parent))  # pipeline/ — shared constants.py, musescore_import.py, etc.
import musescore_import
from constants import PPQ, VOICE_PROGRAM

REPO_ROOT = Path(__file__).parent.parent.parent


def load_song_config(slug: str) -> dict:
    path = REPO_ROOT / "songs" / f"{slug}.json"
    if not path.exists():
        raise SystemExit(f"ERROR: no song config at {path}")
    return json.loads(path.read_text())


def import_vocal_track(slug: str) -> None:
    config = load_song_config(slug)
    midi_source = config.get("midiSource") or {}
    midi_path = mtu.find_midi_source(slug, config)
    print(f"Reading {midi_path} ...")
    mid = mido.MidiFile(str(midi_path), clip=True)

    event_type = mtu.detect_lyric_event_type(mid, midi_source.get("lyricEventType", "auto"))
    lyrics_track = midi_source.get("lyricsTrack")
    if lyrics_track is None:
        lyrics_track = mtu.detect_lyrics_track(mid, event_type)
    if lyrics_track is None:
        raise SystemExit(
            f"ERROR: no {event_type!r} meta-events found in {midi_path} — this song needs "
            "the audio-first path instead, or set songs/{slug}.json's midiSource.lyricsTrack/lyricEventType"
        )
    vocal_channel, scores = mtu.resolve_vocal_channel(mid, midi_source)
    if scores:
        print("Channel/lyric tick-coincidence scores (GM program not used):")
        for channel, score in sorted(scores.items(), key=lambda kv: -kv[1]):
            print(f"  channel {channel}: {score:.0%}")
    if vocal_channel is None:
        raise SystemExit(
            f"ERROR: couldn't identify a vocal channel in {midi_path} — "
            f"set songs/{slug}.json's midiSource.vocalChannel explicitly"
        )
    print(f"Using channel {vocal_channel} as the vocal melody")

    working_dir = REPO_ROOT / "working" / slug
    submidi_path = working_dir / "vocal-midi-from-source.mid"
    mtu.extract_channel_as_midi(mid, vocal_channel, VOICE_PROGRAM, submidi_path)

    ts = config["timeSignature"]
    measure_length_quarters = ts["numerator"] * 4 / ts["denominator"]
    events = musescore_import.import_midi(submidi_path, measure_length_quarters)
    before_mono = len(events)
    events = musescore_import.enforce_monophonic(events)
    if len(events) != before_mono:
        print(f"Resolved {before_mono - len(events)} overlapping note(s) to a single vocal line: {before_mono} -> {len(events)}")

    tempo_bpm = config["tempoBpm"]
    output_path = working_dir / "vocal-events.json"
    output_path.write_text(json.dumps({"ppq": PPQ, "tempo_bpm": tempo_bpm, "events": events}, indent=2))
    print(f"{len(events)} vocal events -> {output_path}")
    if events:
        pitches = [e["pitch"] for e in events]
        print(f"Pitch range: {min(pitches)}-{max(pitches)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    import_vocal_track(args.slug)
