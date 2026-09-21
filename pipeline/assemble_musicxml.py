#!/usr/bin/env python3
"""
Step 5 — MusicXML assembly.

Builds several MusicXML views of a song from its vocal events (with
aligned lyrics), harmony events, instrumental events (from
transcribe_instrumental.py), and metadata (title, composer, key, tempo,
time signature) from songs/<slug>.json, all via music21:

  - working/<slug>/voice.musicxml       — voice only.
  - working/<slug>/instrumental.musicxml — the accompaniment as actually
    transcribed from the audio (working/<slug>/instrumental-events.json),
    not a reduction of the harmony analysis — the two are independent
    transcriptions of different signals (accompaniment stem vs. chord
    recognition) and are not expected to read identically.
  - working/<slug>/harmony.musicxml     — harmony as chord-symbol text
    only, no noteheads (what a lead-sheet chart shows above the staff).
  - working/<slug>/full-score.musicxml  — all three parts together.
  - working/<slug>/lead-sheet.musicxml  — voice + harmony (symbols) only;
    this is the one working/<slug>/musicxml_to_json.py's JSON output
    corresponds to, and the one meant for a quick visual read of the
    published song.

Every multi-part file pads its parts to the same total length before
handing them to music21's makeMeasures(), so every part ends on the same
final measure — otherwise a part that runs shorter than another (typically
Voice, whose last note can end well before Harmony's, itself derived from
the full audio) produces a MusicXML file most notation software reports as
having "incomplete" trailing measures in the shorter part.

Run with:  python pipeline/assemble_musicxml.py <slug>
"""
import argparse
import json
from pathlib import Path

from music21 import chord, clef, harmony as m21harmony, instrument, key as m21key, metadata, meter, note, pitch as m21pitch, stream, tempo, tie as m21tie

from constants import PPQ

REPO_ROOT = Path(__file__).parent.parent
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
QUALITY_TO_SYMBOL = {
    'major': '', 'minor': 'm', 'dominant7': '7', 'major7': 'maj7',
    'minor7': 'm7', 'halfDiminished7': 'm7b5', 'augmented': 'aug',
    'sus4': 'sus4', 'dominant7sus4': '7sus4', 'major6': '6',
}


def ticks_to_ql(ticks: int) -> float:
    return ticks / PPQ


def chord_symbol(h: dict) -> m21harmony.ChordSymbol:
    symbol = f"{NOTE_NAMES[h['root']]}{QUALITY_TO_SYMBOL.get(h['quality'], '')}"
    if h.get("slashBass") is not None:
        symbol += f"/{NOTE_NAMES[h['slashBass']]}"
    return m21harmony.ChordSymbol(symbol)


def build_voice_part(aligned: list[dict]) -> stream.Part:
    """Builds the voice part from align_lyrics.py's own events: real
    detected/quantized notes (see musescore_import.py), each carrying zero
    or more attached syllables in "lyrics" — more than one when a passage
    has more sung syllables than detected notes."""
    part = stream.Part()
    part.id = "voice"
    part.partName = "Voice"
    part.instrument = instrument.Vocalist()
    part.insert(0, clef.TrebleClef())

    for event in aligned:
        p = m21pitch.Pitch()
        p.midi = event["pitch"]
        n = note.Note(p)
        n.duration.quarterLength = ticks_to_ql(event["duration"])
        n.offset = ticks_to_ql(event["start"])

        for i, lyric in enumerate(event.get("lyrics", [])):
            n.lyrics.append(note.Lyric(text=lyric["text"], number=i + 1, syllabic=lyric.get("syllabic", "single")))

        if "tie" in event:
            n.tie = m21tie.Tie(event["tie"]["type"])

        part.insert(n.offset, n)
    return part


def build_harmony_symbols_part(harmony_events: list[dict]) -> stream.Part:
    part = stream.Part()
    part.id = "harmony"
    part.partName = "Harmony"
    part.instrument = instrument.Piano()

    for h in harmony_events:
        cs = chord_symbol(h)
        dur_ql = ticks_to_ql(h["duration"])
        cs.duration.quarterLength = dur_ql if dur_ql > 0 else 1.0
        cs.offset = ticks_to_ql(h["start"])
        part.insert(cs.offset, cs)
    return part


def build_instrumental_part(instrumental_events: list[dict]) -> stream.Part:
    """The accompaniment as transcribed from audio — polyphonic, so notes
    sharing an (already-quantized) start tick are grouped into one chord
    rather than assumed to be a single melodic line."""
    part = stream.Part()
    part.id = "instrumental"
    part.partName = "Instrumental"
    part.instrument = instrument.Piano()
    part.insert(0, clef.BassClef())

    by_start: dict[int, list[dict]] = {}
    for event in instrumental_events:
        by_start.setdefault(event["start"], []).append(event)

    for start in sorted(by_start):
        group = by_start[start]
        dur_ql = ticks_to_ql(max(e["duration"] for e in group))
        pitches = [m21pitch.Pitch(midi=e["pitch"]) for e in group]
        el = note.Note(pitches[0]) if len(pitches) == 1 else chord.Chord(pitches)
        el.duration.quarterLength = dur_ql if dur_ql > 0 else 0.25
        el.offset = ticks_to_ql(start)
        part.insert(el.offset, el)
    return part


def pad_to_common_length(parts: list[stream.Part], measure_length_ql: float) -> None:
    # Round the shared target up to a whole number of measures, and pad
    # with one Rest per measure rather than a single Rest spanning several
    # empty measures. Both matter: a fractional final measure, *and* a
    # single long trailing rest crossing more than one measure boundary,
    # each independently made music21's makeMeasures() emit a duplicated
    # "whole measure" rest in the final measure instead of one correctly
    # sized rest — notation software then reports that measure as
    # overfull/incomplete. One rest per measure, landing exactly on a
    # measure boundary, avoids both.
    raw_target = max(p.highestTime for p in parts)
    measure_count = -(-raw_target // measure_length_ql)  # ceil
    target = measure_count * measure_length_ql
    for part in parts:
        pos = part.highestTime
        if target - pos <= 1e-6:
            continue
        remainder = pos % measure_length_ql
        if remainder > 1e-9:
            end = min(pos + (measure_length_ql - remainder), target)
            r = note.Rest()
            r.duration.quarterLength = end - pos
            part.insert(pos, r)
            pos = end
        while target - pos > 1e-6:
            r = note.Rest()
            r.duration.quarterLength = min(measure_length_ql, target - pos)
            part.insert(pos, r)
            pos += measure_length_ql


def build_score(config: dict, parts: list[stream.Part]) -> stream.Score:
    ts = config["timeSignature"]
    measure_length_ql = ts["numerator"] * 4 / ts["denominator"]
    pad_to_common_length(parts, measure_length_ql)
    for part in parts:
        part.makeMeasures(inPlace=True)

    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = config["title"]
    score.metadata.composer = config["composer"]
    if config.get("lyricist"):
        score.metadata.lyricist = config["lyricist"]

    score.insert(0, tempo.MetronomeMark(number=config["tempoBpm"]))
    score.insert(0, meter.TimeSignature(f"{ts['numerator']}/{ts['denominator']}"))
    score.insert(0, m21key.Key(config["originalKey"].replace('b', '-'), config.get("mode", "major")))

    for part in parts:
        score.insert(0, part)
    return score


def assemble(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    working_dir = REPO_ROOT / "working" / slug

    aligned = json.loads((working_dir / "aligned-lyrics.json").read_text())["aligned"]
    harmony_events = json.loads((working_dir / "harmony-events.json").read_text())["harmony"]
    instrumental_path = working_dir / "instrumental-events.json"
    if not instrumental_path.exists():
        raise SystemExit(f"ERROR: {instrumental_path} not found — run transcribe_instrumental.py first")
    instrumental_events = json.loads(instrumental_path.read_text())["events"]

    print(f"Aligned voice events: {len(aligned)} ({len([a for a in aligned if a.get('lyrics')])} with a lyric)")
    print(f"Harmony events: {len(harmony_events)}")
    print(f"Instrumental events: {len(instrumental_events)}")

    outputs = {
        "voice.musicxml": [build_voice_part(aligned)],
        "instrumental.musicxml": [build_instrumental_part(instrumental_events)],
        "harmony.musicxml": [build_harmony_symbols_part(harmony_events)],
        "full-score.musicxml": [
            build_voice_part(aligned),
            build_instrumental_part(instrumental_events),
            build_harmony_symbols_part(harmony_events),
        ],
        "lead-sheet.musicxml": [
            build_voice_part(aligned),
            build_harmony_symbols_part(harmony_events),
        ],
    }

    for filename, parts in outputs.items():
        score = build_score(config, parts)
        output_path = working_dir / filename
        score.write("musicxml", fp=str(output_path))
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    assemble(args.slug)
