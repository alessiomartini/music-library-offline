#!/usr/bin/env python3
"""
Chunk 6 (Fixed): MusicXML → Normalized JSON for Pino Daniele - E cerca 'e me capi
Convert the lead-sheet.musicxml to the web repo's Score JSON format.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from music21 import converter, note, harmony as m21harmony

MUSICXML = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "lead-sheet.musicxml"
OUTPUT_JSON = Path(__file__).parent.parent / "output" / "json" / "e-cerca-e-me-capi.json"

PPQ = 960

QUALITY_MAP = {
    '': 'major',
    'm': 'minor',
    '7': 'dominant7',
    'maj7': 'major7',
    'm7': 'minor7',
    'm7b5': 'halfDiminished7',
    'dim7': 'diminished7',
    'aug': 'augmented',
    'sus4': 'sus4',
    '7sus4': 'dominant7sus4',
    '6': 'major6',
}

def parse_chord_symbol(cs):
    """Parse a music21 ChordSymbol into root, quality, slashBass."""
    root_pc = cs.root().pitchClass if cs.root() else 0

    quality = 'major'
    if cs.chordKind:
        kind = cs.chordKind
        quality = QUALITY_MAP.get(kind, 'major')

    slash_bass = None
    if cs.bass() and cs.bass().pitchClass != root_pc:
        slash_bass = cs.bass().pitchClass

    return root_pc, quality, slash_bass

def extract_voice_part(voice_part):
    """Extract voice notes with lyrics from music21 part."""
    events = []

    for element in voice_part.flatten().notes:
        if isinstance(element, note.Note):
            start_ticks = int(round(element.offset * PPQ / 4.0))
            dur_ticks = int(round(element.duration.quarterLength * PPQ / 4.0))
            pitch = element.pitch.midi

            lyrics = []
            for ly in element.lyrics:
                lyrics.append({
                    "verse": f"verse{ly.number}" if ly.number else "verse1",
                    "text": ly.text,
                    "syllabic": ly.syllabic if ly.syllabic else "single",
                })

            event = {
                "kind": "note",
                "start": start_ticks,
                "duration": dur_ticks,
                "pitch": pitch,
            }
            if lyrics:
                event["lyrics"] = lyrics
            events.append(event)
        elif isinstance(element, note.Rest):
            start_ticks = int(round(element.offset * PPQ / 4.0))
            dur_ticks = int(round(element.duration.quarterLength * PPQ / 4.0))
            events.append({
                "kind": "rest",
                "start": start_ticks,
                "duration": dur_ticks
            })

    events.sort(key=lambda e: e["start"])
    return events

def extract_harmony(harmony_part):
    """Extract harmony events from music21 part."""
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

    # Duration is derived from the *next* event's (already rounded) start
    # rather than rounded independently from element.duration.quarterLength.
    # MusicXML's own duration/divisions rounding can disagree by a tick with
    # the offset rounding, which used to produce stray overlaps and gaps
    # between consecutive chords. Deriving duration = nextStart - start
    # guarantees the chords tile exactly, by construction.
    for i, event in enumerate(events):
        if i + 1 < len(events):
            event["duration"] = events[i + 1]["start"] - event["start"]
        else:
            event["duration"] = PPQ // 4

    events = [e for e in events if e["duration"] > 0]

    # Merge consecutive identical chords
    merged = []
    for event in events:
        if merged and merged[-1]["root"] == event["root"] and merged[-1]["quality"] == event["quality"]:
            merged[-1]["duration"] += event["duration"]
        else:
            merged.append(event)

    return merged

def get_time_signature(score):
    ts = score.flatten().getElementsByClass('TimeSignature')
    if ts:
        t = ts[0]
        return {"numerator": t.numerator, "denominator": t.denominator}
    return {"numerator": 4, "denominator": 4}

def get_key_signature(score):
    ks = score.flatten().getElementsByClass('KeySignature')
    if ks:
        k = ks[0]
        return k.tonic.name + ("m" if k.mode == "minor" else "")
    return "Bb"

def get_tempo(score):
    mm = score.flatten().getElementsByClass('MetronomeMark')
    if mm:
        return float(mm[0].number)
    return 112.0

def build_measures(time_sig, total_ticks):
    measure_duration = time_sig["numerator"] * PPQ * 4 // time_sig["denominator"]
    measures = []
    start = 0
    while start < total_ticks:
        measures.append({"start": start, "duration": measure_duration})
        start += measure_duration
    return measures

def convert_musicxml_to_json():
    print("Loading MusicXML...")
    score = converter.parse(str(MUSICXML))

    print("Parts:", [p.id for p in score.parts])

    voice_part = None
    harmony_part = None
    for p in score.parts:
        if p.id == 'Voice' or p.partName == 'Voice':
            voice_part = p
        elif p.id == 'Harmony' or p.partName == 'Harmony':
            harmony_part = p

    if not voice_part:
        print("ERROR: Voice part not found")
        return False

    print("Extracting voice...")
    voice_events = extract_voice_part(voice_part)
    print(f"Voice events: {len(voice_events)}")

    harmony_events = []
    if harmony_part:
        print("Extracting harmony...")
        harmony_events = extract_harmony(harmony_part)
        print(f"Harmony events: {len(harmony_events)}")

    time_sig = get_time_signature(score)
    key_sig = get_key_signature(score)
    tempo_bpm = get_tempo(score)

    all_events = voice_events + harmony_events
    if all_events:
        max_end = max(e["start"] + e["duration"] for e in all_events)
    else:
        max_end = PPQ * 4 * 40

    measures = build_measures(time_sig, max_end)

    print(f"Time signature: {time_sig}")
    print(f"Key: {key_sig}")
    print(f"Tempo: {tempo_bpm} BPM")
    print(f"Measures: {len(measures)}")
    print(f"Total ticks: {max_end}")

    score_json = {
        "schemaVersion": 1,
        "score": {
            "ppq": PPQ,
            "originalKey": key_sig,
            "timeSignature": time_sig,
            "measures": measures,
            "tempo": {"bpm": tempo_bpm},
            "parts": [
                {
                    "id": "voice",
                    "name": "Voice",
                    "role": "voice",
                    "events": voice_events
                }
            ],
            "harmony": harmony_events
        }
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(score_json, f, indent=2)

    print(f"\nJSON saved to: {OUTPUT_JSON}")
    return True

if __name__ == "__main__":
    success = convert_musicxml_to_json()
    sys.exit(0 if success else 1)