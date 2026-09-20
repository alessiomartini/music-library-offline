#!/usr/bin/env python3
"""
Step 6 — MusicXML to normalized JSON.

Reads working/<slug>/lead-sheet.musicxml back and emits the schemaVersion 1
envelope the web app's loadScoreJson (src/lib/scoreLoader.ts) expects, to
output/json/<slug>.json — the file that gets copied into the web repo's
src/data/songs/.

Run with:  python pipeline/musicxml_to_json.py <slug>
"""
import argparse
import json
from pathlib import Path

from music21 import converter, harmony as m21harmony, note

REPO_ROOT = Path(__file__).parent.parent
PPQ = 960

QUALITY_MAP = {
    '': 'major', 'm': 'minor', '7': 'dominant7', 'maj7': 'major7',
    'm7': 'minor7', 'm7b5': 'halfDiminished7', 'aug': 'augmented',
    'sus4': 'sus4', '7sus4': 'dominant7sus4', '6': 'major6',
}


def parse_chord_symbol(cs):
    root_pc = cs.root().pitchClass if cs.root() else 0
    quality = QUALITY_MAP.get(cs.chordKind, 'major') if cs.chordKind else 'major'
    bass = cs.bass()
    slash_bass = bass.pitchClass if bass and bass.pitchClass != root_pc else None
    return root_pc, quality, slash_bass


def extract_voice_part(voice_part) -> list[dict]:
    events = []
    for element in voice_part.flatten().notes:
        start_ticks = int(round(element.offset * PPQ / 4.0))
        dur_ticks = int(round(element.duration.quarterLength * PPQ / 4.0))

        if isinstance(element, note.Note):
            lyrics = [
                {
                    "verse": f"verse{ly.number}" if ly.number else "verse1",
                    "text": ly.text,
                    "syllabic": ly.syllabic if ly.syllabic else "single",
                }
                for ly in element.lyrics
            ]
            event = {"kind": "note", "start": start_ticks, "duration": dur_ticks, "pitch": element.pitch.midi}
            if lyrics:
                event["lyrics"] = lyrics
            events.append(event)
        elif isinstance(element, note.Rest):
            events.append({"kind": "rest", "start": start_ticks, "duration": dur_ticks})

    events.sort(key=lambda e: e["start"])
    return events


def extract_harmony(harmony_part) -> list[dict]:
    events = []
    for element in harmony_part.flatten().notes:
        if isinstance(element, m21harmony.ChordSymbol):
            start_ticks = int(round(element.offset * PPQ / 4.0))
            root_pc, quality, slash_bass = parse_chord_symbol(element)
            event = {"start": start_ticks, "root": root_pc, "quality": quality}
            if slash_bass is not None:
                event["slashBass"] = slash_bass
            events.append(event)

    events.sort(key=lambda e: e["start"])

    # Same tiling fix as extract_harmony.py: derive duration from the next
    # event's already-rounded start rather than from MusicXML's own float
    # offset/duration, which can independently round the other direction
    # and reintroduce the overlap this pipeline exists to avoid.
    for i, event in enumerate(events):
        event["duration"] = events[i + 1]["start"] - event["start"] if i + 1 < len(events) else PPQ // 4
    events = [e for e in events if e["duration"] > 0]

    merged = []
    for event in events:
        if merged and merged[-1]["root"] == event["root"] and merged[-1]["quality"] == event["quality"]:
            merged[-1]["duration"] += event["duration"]
        else:
            merged.append(event)
    return merged


def build_measures(time_sig: dict, total_ticks: int) -> list[dict]:
    measure_duration = time_sig["numerator"] * PPQ * 4 // time_sig["denominator"]
    measures = []
    start = 0
    while start < total_ticks:
        measures.append({"start": start, "duration": measure_duration})
        start += measure_duration
    return measures


def convert(slug: str) -> None:
    config = json.loads((REPO_ROOT / "songs" / f"{slug}.json").read_text())
    musicxml_path = REPO_ROOT / "working" / slug / "lead-sheet.musicxml"
    print("Loading MusicXML...")
    score = converter.parse(str(musicxml_path))

    voice_part = next((p for p in score.parts if p.id == 'voice' or p.partName == 'Voice'), None)
    harmony_part = next((p for p in score.parts if p.id == 'harmony' or p.partName == 'Harmony'), None)
    if voice_part is None:
        raise SystemExit("ERROR: Voice part not found in MusicXML")

    voice_events = extract_voice_part(voice_part)
    harmony_events = extract_harmony(harmony_part) if harmony_part is not None else []
    print(f"Voice events: {len(voice_events)}")
    print(f"Harmony events: {len(harmony_events)}")

    ts = config["timeSignature"]
    all_events = voice_events + harmony_events
    max_end = max((e["start"] + e["duration"] for e in all_events), default=PPQ * ts["numerator"])
    measures = build_measures(ts, max_end)
    print(f"Measures: {len(measures)}")

    score_json = {
        "schemaVersion": 1,
        "score": {
            "ppq": PPQ,
            "originalKey": config["originalKey"],
            "timeSignature": ts,
            "measures": measures,
            "tempo": {"bpm": config["tempoBpm"]},
            "parts": [{"id": "voice", "name": "Voice", "role": "voice", "events": voice_events}],
            "harmony": harmony_events,
        },
    }

    output_path = REPO_ROOT / "output" / "json" / f"{slug}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(score_json, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    convert(args.slug)
