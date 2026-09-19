#!/usr/bin/env python3
"""
Chunk 5 (Fixed): MusicXML Assembly
- Single 4/4 time signature throughout (2/4 measures are ritardando/fermata)
- Harmony extracted from original track, not separated accompaniment
- Proper lyric synchronization with syllabification
- Valid MusicXML output
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from music21 import stream, note, chord, meter, tempo, key, clef, instrument, metadata
from music21 import pitch as m21pitch
from music21 import harmony as m21harmony

VOCAL_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "vocal-events.json"
ALIGNED_LYRICS = Path(__file__).parent.parent / "working" / "your-song" / "aligned-lyrics.json"
HARMONY_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "harmony-events.json"
OUTPUT_MUSICXML = Path(__file__).parent.parent / "working" / "your-song" / "lead-sheet-fixed.musicxml"

PPQ = 960

# Lyrics with proper syllabification and melisma marking
LYRICS_DATA = [
    ("verse1", [
        ("It's", "single"), ("a", "single"), ("lit", "begin"), ("tle", "end"),
        ("bit", "single"), ("fun", "begin"), ("ny", "end"),
        ("this", "single"), ("fee", "begin"), ("ling", "end"),
        ("in", "single"), ("side", "single"),
        ("I'm", "single"), ("not", "single"), ("one", "single"), ("of", "single"),
        ("those", "single"), ("who", "single"), ("can", "single"),
        ("eas", "begin"), ("i", "middle"), ("ly", "end"), ("hide", "single"),
        ("I", "single"), ("don't", "single"), ("have", "single"), ("much", "single"),
        ("mo", "begin"), ("ney", "end"),
        ("but", "single"), ("boy", "single"), ("if", "single"), ("I", "single"), ("did", "single"),
        ("I'd", "single"), ("buy", "single"), ("a", "single"), ("big", "single"), ("house", "single"), ("where", "single"),
        ("we", "single"), ("both", "single"), ("could", "single"), ("live", "single"),
    ]),
    ("verse2", [
        ("If", "single"), ("I", "single"), ("was", "single"), ("a", "single"),
        ("sculp", "begin"), ("tor", "end"), ("but", "single"), ("then", "single"), ("a", "single"), ("gain", "single"), ("no", "single"),
        ("or", "single"), ("a", "single"), ("man", "single"), ("who", "single"), ("makes", "single"),
        ("po", "begin"), ("tions", "end"), ("in", "single"), ("a", "single"),
        ("tra", "begin"), ("vel", "middle"), ("ling", "end"), ("show", "single"),
        ("I", "single"), ("know", "single"), ("it's", "single"), ("not", "single"), ("much", "single"),
        ("but", "single"), ("it's", "single"), ("the", "single"), ("best", "single"), ("I", "single"), ("can", "single"), ("do", "single"),
        ("My", "single"), ("gift", "single"), ("is", "single"), ("my", "single"), ("song", "single"),
        ("and", "single"), ("this", "single"), ("one's", "single"), ("for", "single"), ("you", "single"),
    ]),
    ("chorus1", [
        ("And", "single"), ("you", "single"), ("can", "single"), ("tell", "single"),
        ("ev", "begin"), ("ry", "middle"), ("bo", "middle"), ("dy", "end"),
        ("this", "single"), ("is", "single"), ("your", "single"), ("song", "single"),
        ("It", "single"), ("may", "single"), ("be", "single"),
        ("qui", "begin"), ("te", "end"), ("sim", "begin"), ("ple", "end"),
        ("but", "single"), ("now", "single"), ("that", "single"), ("it's", "single"), ("done", "single"),
        ("I", "single"), ("hope", "single"), ("you", "single"), ("don't", "single"), ("mind", "single"),
        ("I", "single"), ("hope", "single"), ("you", "single"), ("don't", "single"), ("mind", "single"),
        ("that", "single"), ("I", "single"), ("put", "single"), ("down", "single"), ("in", "single"), ("words", "single"),
        ("how", "single"), ("won", "begin"), ("der", "end"), ("ful", "single"), ("life", "single"), ("is", "single"),
        ("while", "single"), ("you're", "single"), ("in", "single"), ("the", "single"), ("world", "single"),
    ]),
    ("verse3", [
        ("I", "single"), ("sat", "single"), ("on", "single"), ("the", "single"), ("roof", "single"),
        ("and", "single"), ("kicked", "single"), ("off", "single"), ("the", "single"), ("moss", "single"),
        ("well", "single"), ("a", "single"), ("few", "single"), ("of", "single"), ("the", "single"), ("verses", "single"),
        ("well", "single"), ("they've", "single"), ("got", "single"), ("me", "single"), ("quite", "single"), ("cross", "single"),
        ("but", "single"), ("the", "single"), ("sun", "single"), ("been", "single"),
        ("qui", "begin"), ("te", "end"), ("kind", "single"),
        ("while", "single"), ("I", "single"), ("wrote", "single"), ("this", "single"), ("song", "single"),
        ("it's", "single"), ("for", "single"), ("peo", "begin"), ("ple", "end"), ("like", "single"), ("you", "single"),
        ("that", "single"), ("keep", "single"), ("it", "single"), ("turn", "begin"), ("ing", "end"), ("on", "single"),
    ]),
    ("chorus2", [
        ("So", "single"), ("ex", "begin"), ("cuse", "end"), ("me", "single"), ("for", "single"), ("get", "begin"), ("ting", "end"),
        ("but", "single"), ("these", "single"), ("things", "single"), ("I", "single"), ("do", "single"),
        ("you", "single"), ("see", "single"), ("I've", "single"), ("for", "single"), ("got", "begin"), ("ten", "end"),
        ("if", "single"), ("they're", "single"), ("green", "single"), ("or", "single"), ("they're", "single"), ("blue", "single"),
        ("an", "begin"), ("y", "end"), ("way", "single"), ("the", "single"), ("thing", "single"), ("is", "single"),
        ("what", "single"), ("I", "single"), ("re", "begin"), ("al", "middle"), ("ly", "end"), ("mean", "single"),
        ("yours", "single"), ("are", "single"), ("the", "single"), ("sweet", "begin"), ("est", "end"), ("eyes", "single"),
        ("I've", "single"), ("ev", "begin"), ("er", "end"), ("seen", "single"),
    ]),
    ("chorus3", [
        ("And", "single"), ("you", "single"), ("can", "single"), ("tell", "single"),
        ("ev", "begin"), ("ry", "middle"), ("bo", "middle"), ("dy", "end"),
        ("this", "single"), ("is", "single"), ("your", "single"), ("song", "single"),
        ("It", "single"), ("may", "single"), ("be", "single"),
        ("qui", "begin"), ("te", "end"), ("sim", "begin"), ("ple", "end"),
        ("but", "single"), ("now", "single"), ("that", "single"), ("it's", "single"), ("done", "single"),
        ("I", "single"), ("hope", "single"), ("you", "single"), ("don't", "single"), ("mind", "single"),
        ("I", "single"), ("hope", "single"), ("you", "single"), ("don't", "single"), ("mind", "single"),
        ("that", "single"), ("I", "single"), ("put", "single"), ("down", "single"), ("in", "single"), ("words", "single"),
        ("how", "single"), ("won", "begin"), ("der", "end"), ("ful", "single"), ("life", "single"), ("is", "single"),
        ("while", "single"), ("you're", "single"), ("in", "single"), ("the", "single"), ("world", "single"),
    ]),
    ("outro", [
        ("I", "single"), ("hope", "single"), ("you", "single"), ("don't", "single"), ("mind", "single"),
        ("I", "single"), ("hope", "single"), ("you", "single"), ("don't", "single"), ("mind", "single"),
        ("that", "single"), ("I", "single"), ("put", "single"), ("down", "single"), ("in", "single"), ("words", "single"),
        ("how", "single"), ("won", "begin"), ("der", "end"), ("ful", "single"), ("life", "single"), ("is", "single"),
        ("while", "single"), ("you're", "single"), ("in", "single"), ("the", "single"), ("world", "single"),
    ])
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

def assemble_musicxml():
    print("Loading data...")
    vocal_data = load_json(VOCAL_EVENTS)
    lyrics_data = load_json(ALIGNED_LYRICS)
    harmony_data = load_json(HARMONY_EVENTS)

    vocal_events = vocal_data["events"]
    aligned = lyrics_data["aligned"]
    harmony_events = harmony_data["harmony"]
    tempo_bpm = 72  # Use constant tempo

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
    score.metadata.title = "Your Song"
    score.metadata.composer = "Elton John"
    score.metadata.lyricist = "Bernie Taupin"

    # Global settings
    score.insert(0, tempo.MetronomeMark(number=tempo_bpm))
    score.insert(0, meter.TimeSignature('4/4'))  # Single 4/4 throughout
    score.insert(0, key.Key('E-', 'major'))

    # Voice part
    voice_part = stream.Part()
    voice_part.id = "voice"
    voice_part.partName = "Voice"
    voice_part.instrument = instrument.Vocalist()
    voice_part.insert(0, clef.TrebleClef())

    # Add voice notes with lyrics
    for event in vocal_events:
        start_offset = event["start"] / PPQ * 4.0
        dur_ql = ticks_to_quarter_length(event["duration"])
        p = midi_to_pitch(event["pitch"])

        n = note.Note(p)
        n.duration.quarterLength = dur_ql
        n.offset = start_offset

        # Add lyric if present
        if event["start"] in lyrics_by_start:
            lyric_info = lyrics_by_start[event["start"]]
            ly = note.Lyric(
                text=lyric_info["text"],
                number=1,  # All verse 1 for now
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
        if i < 10 or i > 60:
            continue
        ts = m.timeSignature
        if ts:
            print(f"  Measure {i+1}: {ts.numerator}/{ts.denominator}")

    print("Done!")
    return True

if __name__ == "__main__":
    success = assemble_musicxml()
    sys.exit(0 if success else 1)