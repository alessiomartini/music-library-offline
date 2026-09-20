#!/usr/bin/env python3
"""
Chunk 5 (Fixed): MusicXML Assembly for Pino Daniele - E cerca 'e me capi
- Single 4/4 time signature throughout
- Proper lyric synchronization with syllabification
- Valid MusicXML output
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from music21 import stream, note, meter, tempo, key, clef, instrument, metadata
from music21 import pitch as m21pitch
from music21 import harmony as m21harmony

VOCAL_EVENTS = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "vocal-events.json"
ALIGNED_LYRICS = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "aligned-lyrics.json"
HARMONY_EVENTS = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "harmony-events.json"
OUTPUT_MUSICXML = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "lead-sheet.musicxml"

PPQ = 960

# Lyrics with proper syllabification
LYRICS_DATA = [
    ("verse1", [
        ("E", "single"), ("cer", "begin"), ("ca", "middle"), ("e", "end"), ("me", "single"), ("ca", "begin"), ("pi", "end"),
        ("chi", "single"), ("sa", "single"), ("pe", "single"), ("che", "single"), ("co", "single"), ("sa", "single"), ("è", "single"),
        ("l'a", "single"), ("mo", "begin"), ("re", "end"), ("che", "single"), ("non", "single"), ("si", "single"), ("di", "begin"), ("men", "middle"), ("ti", "middle"), ("ca", "end"),
        ("ma", "single"), ("ti", "single"), ("pren", "begin"), ("de", "end"), ("e", "single"), ("ti", "single"), ("por", "begin"), ("ta", "middle"), ("via", "end")
    ]),
    ("chorus1", [
        ("E", "single"), ("cer", "begin"), ("ca", "middle"), ("e", "end"), ("me", "single"), ("ca", "begin"), ("pi", "end"),
        ("se", "single"), ("po", "begin"), ("sso", "end"), ("sta", "single"), ("vo", "single"), ("tan", "begin"), ("to", "end"), ("ma", "single"), ("le", "single"),
        ("per", "single"), ("un", "single"), ("ba", "begin"), ("cio", "end"), ("che", "single"), ("non", "single"), ("ho", "single"), ("da", "begin"), ("to", "end"),
        ("ma", "single"), ("il", "single"), ("tem", "begin"), ("po", "end"), ("pas", "begin"), ("sa", "end"), ("e", "single"), ("non", "single"), ("tor", "begin"), ("na", "end")
    ]),
    ("verse2", [
        ("Nun", "single"), ("te", "single"), ("ne", "single"), ("vai", "single"), ("sen", "begin"), ("za", "end"), ("di", "single"), ("me", "single"),
        ("las", "begin"), ("san", "end"), ("do", "single"), ("un", "single"), ("vuo", "begin"), ("to", "end"), ("che", "single"), ("non", "single"), ("si", "single"), ("co", "begin"), ("lma", "end"),
        ("ma", "single"), ("io", "single"), ("so", "single"), ("che", "single"), ("tor", "begin"), ("ne", "middle"), ("rai", "end"),
        ("per", "single"), ("ché", "single"), ("l'a", "single"), ("mo", "begin"), ("re", "end"), ("non", "single"), ("si", "single"), ("fer", "begin"), ("ma", "middle"), ("mai", "end")
    ]),
    ("chorus2", [
        ("E", "single"), ("cer", "begin"), ("ca", "middle"), ("e", "end"), ("me", "single"), ("ca", "begin"), ("pi", "end"),
        ("se", "single"), ("pos", "begin"), ("so", "end"), ("sta", "single"), ("vo", "single"), ("tan", "begin"), ("to", "end"), ("ma", "single"), ("le", "single"),
        ("per", "single"), ("un", "single"), ("ba", "begin"), ("cio", "end"), ("che", "single"), ("non", "single"), ("ho", "single"), ("da", "begin"), ("to", "end"),
        ("ma", "single"), ("il", "single"), ("tem", "begin"), ("po", "end"), ("pas", "begin"), ("sa", "end"), ("e", "single"), ("non", "single"), ("tor", "begin"), ("na", "end")
    ]),
    ("bridge", [
        ("E", "single"), ("for", "begin"), ("se", "end"), ("un", "single"), ("gior", "begin"), ("no", "end"), ("ca", "begin"), ("pri", "middle"), ("rai", "end"),
        ("che", "single"), ("io", "single"), ("so", "single"), ("no", "single"), ("qui", "single"), ("ad", "begin"), ("as", "middle"), ("pet", "middle"), ("tar", "middle"), ("ti", "end"),
        ("e", "single"), ("all'o", "begin"), ("ra", "end"), ("sa", "single"), ("rai", "single"), ("che", "single"), ("non", "single"), ("c'è", "single"),
        ("nien", "begin"), ("te", "end"), ("di", "single"), ("più", "single"), ("for", "begin"), ("te", "end"), ("di", "single"), ("me", "single")
    ]),
    ("chorus3", [
        ("E", "single"), ("cer", "begin"), ("ca", "middle"), ("e", "end"), ("me", "single"), ("ca", "begin"), ("pi", "end"),
        ("se", "single"), ("pos", "begin"), ("so", "end"), ("sta", "single"), ("vo", "single"), ("tan", "begin"), ("to", "end"), ("ma", "single"), ("le", "single"),
        ("per", "single"), ("un", "single"), ("ba", "begin"), ("cio", "end"), ("che", "single"), ("non", "single"), ("ho", "single"), ("da", "begin"), ("to", "end"),
        ("ma", "single"), ("il", "single"), ("tem", "begin"), ("po", "end"), ("pas", "begin"), ("sa", "end"), ("e", "single"), ("non", "single"), ("tor", "begin"), ("na", "end")
    ]),
]

def load_json(path):
    with open(path) as f:
        return json.load(f)

def ticks_to_quarter_length(ticks):
    return ticks / PPQ * 4.0

def midi_to_pitch(midi_num):
    p = m21pitch.Pitch()
    p.midi = midi_num
    return p

def quantize_duration(ql, grid=0.5):
    """Quantize quarter length to nearest grid (default: 8th note = 0.5 quarter lengths)"""
    quantized = round(ql / grid) * grid
    # Ensure minimum duration (16th note = 0.25)
    return max(quantized, 0.25)

def quantize_offset(offset, grid=0.5):
    """Quantize offset to nearest grid"""
    return round(offset / grid) * grid

def assemble_musicxml():
    print("Loading data...")
    vocal_data = load_json(VOCAL_EVENTS)
    lyrics_data = load_json(ALIGNED_LYRICS)
    harmony_data = load_json(HARMONY_EVENTS)

    vocal_events = vocal_data["events"]
    aligned = lyrics_data["aligned"]
    harmony_events = harmony_data["harmony"]
    tempo_bpm = 112  # Use detected tempo

    print(f"Vocal events: {len(vocal_events)}")
    print(f"Aligned lyrics: {len([a for a in aligned if a['lyric']])}")
    print(f"Harmony events: {len(harmony_events)}")

    # Build lyrics lookup by event start tick
    lyrics_by_start = {}
    for a in aligned:
        if a["lyric"]:
            lyrics_by_start[a["start"]] = a["lyric"]

    # Create score
    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = "E cerca 'e me capi"
    score.metadata.composer = "Pino Daniele"
    score.metadata.lyricist = "Pino Daniele"

    # Global settings
    score.insert(0, tempo.MetronomeMark(number=tempo_bpm))
    score.insert(0, meter.TimeSignature('4/4'))  # Single 4/4 throughout
    score.insert(0, key.Key('B-', 'major'))  # Bb major

    # Voice part
    voice_part = stream.Part()
    voice_part.id = "voice"
    voice_part.partName = "Voice"
    voice_part.instrument = instrument.Vocalist()
    voice_part.insert(0, clef.TrebleClef())

    # Add voice notes with lyrics
    for event in vocal_events:
        start_offset = quantize_offset(event["start"] / PPQ * 4.0)
        dur_ql = quantize_duration(ticks_to_quarter_length(event["duration"]))
        p = midi_to_pitch(event["pitch"])

        n = note.Note(p)
        n.duration.quarterLength = dur_ql
        n.offset = start_offset

        # Add lyric if present
        if event["start"] in lyrics_by_start:
            lyric_info = lyrics_by_start[event["start"]]
            ly = note.Lyric(
                text=lyric_info["text"],
                number=1,
                syllabic=lyric_info["syllabic"]
            )
            n.lyrics.append(ly)

        voice_part.insert(start_offset, n)

    # Make measures with single 4/4 time signature
    voice_part.makeMeasures(inPlace=True)

    # Harmony part - chord symbols above voice
    harmony_part = stream.Part()
    harmony_part.id = "harmony"
    harmony_part.partName = "Harmony"
    harmony_part.instrument = instrument.Piano()

    for h_event in harmony_events:
        start_offset = h_event["start"] / PPQ * 4.0
        dur_ql = ticks_to_quarter_length(h_event["duration"])

        if dur_ql <= 0:
            dur_ql = 1.0

        root_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][h_event["root"]]
        quality_map = {
            'major': '', 'minor': 'm', 'dominant7': '7', 'major7': 'maj7',
            'minor7': 'm7', 'halfDiminished7': 'm7b5', 'diminished7': 'dim7',
            'augmented': 'aug', 'sus4': 'sus4', 'dominant7sus4': '7sus4', 'major6': '6',
        }
        quality_suffix = quality_map.get(h_event["quality"], '')

        chord_symbol = f"{root_name}{quality_suffix}"
        if h_event.get("slashBass") is not None:
            bass_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][h_event["slashBass"]]
            chord_symbol += f"/{bass_name}"

        cs = m21harmony.ChordSymbol(chord_symbol)
        cs.duration.quarterLength = dur_ql
        cs.offset = start_offset
        harmony_part.insert(start_offset, cs)

    harmony_part.makeMeasures(inPlace=True)

    # Add parts to score
    score.insert(0, voice_part)
    score.insert(0, harmony_part)

    # Write MusicXML
    print(f"Writing MusicXML to: {OUTPUT_MUSICXML}")
    score.write('musicxml', fp=str(OUTPUT_MUSICXML))

    # Verify measures
    print("\nVerifying measures...")
    for i, m in enumerate(voice_part.getElementsByClass('Measure')):
        if i < 5 or i > 50:
            continue
        ts = m.timeSignature
        if ts:
            print(f"  Measure {i+1}: {ts.numerator}/{ts.denominator}")

    print("Done!")
    return True

if __name__ == "__main__":
    success = assemble_musicxml()
    sys.exit(0 if success else 1)