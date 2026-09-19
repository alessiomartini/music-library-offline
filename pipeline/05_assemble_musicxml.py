#!/usr/bin/env python3
"""
Chunk 5: MusicXML Assembly
Combine vocal melody + lyrics + harmony into a MusicXML lead sheet using music21.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from music21 import stream, note, chord, meter, tempo, key, clef, instrument, metadata
from music21 import pitch as m21pitch

VOCAL_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "vocal-events.json"
ALIGNED_LYRICS = Path(__file__).parent.parent / "working" / "your-song" / "aligned-lyrics.json"
HARMONY_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "harmony-events.json"
OUTPUT_MUSICXML = Path(__file__).parent.parent / "working" / "your-song" / "lead-sheet.musicxml"

PPQ = 960

def load_json(path):
    with open(path) as f:
        return json.load(f)

# Grid quantization: 32nd notes = 960/32 = 30 ticks
GRID_TICKS = PPQ // 32  # 30 ticks per 32nd note

def quantize_ticks(ticks):
    """Quantize ticks to 32nd note grid."""
    return round(ticks / GRID_TICKS) * GRID_TICKS

def ticks_to_duration(ticks):
    """Convert ticks to music21 duration (quarterLength)."""
    ql = ticks / PPQ * 4.0  # 4 quarters per whole note
    min_ql = 1.0 / 32.0  # 128th note minimum
    if ql < min_ql:
        ql = min_ql
    ql = round(ql * 32) / 32
    return max(ql, min_ql)

def midi_to_pitch(midi_num):
    """Convert MIDI note number to music21 Pitch."""
    p = m21pitch.Pitch()
    p.midi = midi_num
    return p

def assemble_musicxml():
    print("Loading data...")
    vocal_data = load_json(VOCAL_EVENTS)
    lyrics_data = load_json(ALIGNED_LYRICS)
    harmony_data = load_json(HARMONY_EVENTS)

    vocal_events = vocal_data["events"]
    aligned = lyrics_data["aligned"]
    harmony_events = harmony_data["harmony"]
    tempo_bpm = harmony_data.get("tempo_bpm", 120)

    print(f"Vocal events: {len(vocal_events)}")
    print(f"Aligned lyrics: {len([a for a in aligned if a['lyric']])}")
    print(f"Harmony events: {len(harmony_events)}")
    print(f"Tempo: {tempo_bpm} BPM")

    # Create score
    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = "Your Song"
    score.metadata.composer = "Elton John"
    score.metadata.lyricist = "Bernie Taupin"

    # Add metronome mark
    mm = tempo.MetronomeMark(number=tempo_bpm)
    score.insert(0, mm)

    # Time signature - start with 4/4
    ts = meter.TimeSignature('4/4')
    score.insert(0, ts)

    # Key signature - Eb major (3 flats) based on audit
    ks = key.Key('E-', 'major')
    score.insert(0, ks)

    # Part 1: Voice (with lyrics)
    voice_part = stream.Part()
    voice_part.id = "voice"
    voice_part.partName = "Voice"
    voice_part.instrument = instrument.Vocalist()

    # Add clef
    voice_part.insert(0, clef.TrebleClef())

    # We need to place notes at absolute positions
    # music21 works with offset (quarter notes from start)
    # Convert ticks to offset: offset = ticks / PPQ * 4.0

    # Build a dict of lyrics by event start tick (quantized)
    lyrics_by_start = {}
    for a in aligned:
        if a["lyric"]:
            q_start = quantize_ticks(a["start"])
            lyrics_by_start[q_start] = a["lyric"]

    # Add voice notes - quantize all timing to 32nd grid
    for event in vocal_events:
        start_ticks = quantize_ticks(event["start"])
        dur_ticks = quantize_ticks(event["duration"])
        start_offset = start_ticks / PPQ * 4.0
        dur_ql = ticks_to_duration(dur_ticks)
        p = midi_to_pitch(event["pitch"])

        n = note.Note(p)
        n.duration.quarterLength = dur_ql
        n.offset = start_offset

        # Add lyric if present
        if event["start"] in lyrics_by_start:
            lyric_info = lyrics_by_start[event["start"]]
            # music21 Lyric: text, number (verse), syllabic
            ly = note.Lyric(
                text=lyric_info["text"],
                number=1 if lyric_info["verse"] == "verse1" else
                     2 if lyric_info["verse"] == "verse2" else
                     3 if lyric_info["verse"].startswith("chorus") else
                     4 if lyric_info["verse"] == "verse3" else 5,
                syllabic=lyric_info["syllabic"]
            )
            n.lyrics.append(ly)

        voice_part.insert(start_offset, n)

    # Make measures in voice part
    voice_part.makeMeasures(inPlace=True)

    # Part 2: Harmony (chord symbols)
    # We'll add chord symbols to a separate staff or as harmony annotations
    # For lead sheet, add chord symbols above the voice part
    harmony_part = stream.Part()
    harmony_part.id = "harmony"
    harmony_part.partName = "Harmony"
    harmony_part.instrument = instrument.Piano()

    # Add chord symbols at their positions - quantize timing
    for h_event in harmony_events:
        start_ticks = quantize_ticks(h_event["start"])
        dur_ticks = quantize_ticks(h_event["duration"])
        start_offset = start_ticks / PPQ * 4.0
        dur_ql = ticks_to_duration(dur_ticks)

        # Create chord symbol
        root_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][h_event["root"]]

        # Map quality to music21 chord symbol
        quality_map = {
            'major': '',
            'minor': 'm',
            'dominant7': '7',
            'major7': 'maj7',
            'minor7': 'm7',
            'halfDiminished7': 'm7b5',
            'diminished7': 'dim7',
            'augmented': 'aug',
            'sus4': 'sus4',
        }
        quality_suffix = quality_map.get(h_event["quality"], '')

        chord_symbol = f"{root_name}{quality_suffix}"
        if h_event.get("slashBass") is not None:
            bass_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][h_event["slashBass"]]
            chord_symbol += f"/{bass_name}"

        # Create a harmony.ChordSymbol
        from music21 import harmony
        cs = harmony.ChordSymbol(chord_symbol)
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

    print("Done!")
    return True

if __name__ == "__main__":
    success = assemble_musicxml()
    sys.exit(0 if success else 1)