#!/usr/bin/env python3
"""
Chunk 4: Harmony Extraction
Extract chord symbols from accompaniment stem using librosa + chroma analysis.
This is a simpler approach than Chordino (which needs Sonic Annotator + Vamp).
"""
import json
import numpy as np
import librosa
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

ACCOMPANIMENT_WAV = Path(__file__).parent.parent / "working" / "your-song" / "accompaniment.wav"
OUTPUT_HARMONY = Path(__file__).parent.parent / "working" / "your-song" / "harmony-events.json"

# PPQ from web repo
PPQ = 960

# Chord templates for major/minor triads and 7ths
CHORD_TEMPLATES = {
    'major': [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
    'minor': [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    'dominant7': [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0],
    'major7': [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
    'minor7': [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0],
    'halfDiminished7': [1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0],
    'diminished7': [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0],
    'augmented': [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    'sus4': [1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
}

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def extract_harmony():
    print(f"Loading accompaniment: {ACCOMPANIMENT_WAV}")

    if not ACCOMPANIMENT_WAV.exists():
        print(f"ERROR: File not found: {ACCOMPANIMENT_WAV}")
        return False

    # Load audio
    y, sr = librosa.load(str(ACCOMPANIMENT_WAV), sr=None)
    print(f"Audio loaded: {len(y)/sr:.1f}s at {sr}Hz")

    # Extract chroma features (12 pitch classes)
    # Use CQT-based chroma for better harmonic resolution
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    print(f"Chroma shape: {chroma.shape} (frames x 12)")

    # Get frame times
    frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=512)

    # Detect tempo
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0])
    else:
        tempo = float(tempo)
    print(f"Detected tempo: {tempo:.1f} BPM")

    # Beat times in seconds
    beat_times = librosa.frames_to_time(beats, sr=sr)

    # For each beat, analyze chroma to detect chord
    # Use a window around each beat
    hop_length = 512
    frame_duration = hop_length / sr  # seconds per frame

    harmony_events = []

    for i, beat_time in enumerate(beat_times):
        # Find frames within ~1 beat window
        window_start = max(0, int((beat_time - 0.5) / frame_duration))
        window_end = min(chroma.shape[1], int((beat_time + 0.5) / frame_duration))

        if window_end <= window_start:
            continue

        # Average chroma in window
        avg_chroma = np.mean(chroma[:, window_start:window_end], axis=1)

        # Normalize
        if np.sum(avg_chroma) > 0:
            avg_chroma = avg_chroma / np.sum(avg_chroma)

        # Match against chord templates
        best_chord = None
        best_score = -1
        best_root = 0

        for root in range(12):
            # Rotate templates for each root
            for quality, template in CHORD_TEMPLATES.items():
                rotated = np.roll(template, root)
                score = np.dot(avg_chroma, rotated)
                if score > best_score:
                    best_score = score
                    best_chord = quality
                    best_root = root

        if best_chord:
            # Convert beat time to ticks
            # ticks = time_sec * (tempo/60) * PPQ
            start_ticks = int(round(beat_time * (tempo / 60.0) * PPQ))

            harmony_events.append({
                "start": start_ticks,
                "root": best_root,
                "quality": best_chord,
                "slashBass": None,  # Could add bass detection later
                "confidence": float(best_score)
            })

    # Duration is derived from the *next* event's (already rounded) start
    # rather than rounded independently from the real inter-beat time. Two
    # independent roundings of dependent quantities can each land on either
    # side of .5, which used to produce a stray tick of gap or overlap
    # between consecutive chords and made the score fail overlap validation.
    # Deriving duration = nextStart - start guarantees the chords tile
    # exactly, by construction.
    for i, event in enumerate(harmony_events):
        if i + 1 < len(harmony_events):
            event["duration"] = harmony_events[i + 1]["start"] - event["start"]
        else:
            event["duration"] = PPQ  # one beat, last event

    # Two detected beats can round to the same tick; a zero/negative-duration
    # event is invalid, so drop it rather than emit unplayable harmony.
    dropped = sum(1 for e in harmony_events if e["duration"] <= 0)
    if dropped:
        print(f"Dropping {dropped} zero/negative-duration event(s) from coincident beat roundings")
    harmony_events = [e for e in harmony_events if e["duration"] > 0]

    # Merge consecutive identical chords
    merged = []
    for event in harmony_events:
        if merged and merged[-1]["root"] == event["root"] and merged[-1]["quality"] == event["quality"]:
            merged[-1]["duration"] += event["duration"]
        else:
            merged.append(event)

    print(f"Detected {len(merged)} harmony events (merged from {len(harmony_events)})")

    # Save
    output = {
        "ppq": PPQ,
        "tempo_bpm": float(tempo),
        "harmony": merged
    }

    with open(OUTPUT_HARMONY, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Output: {OUTPUT_HARMONY}")

    # Show first 20
    print("\nFirst 20 harmony events:")
    for h in merged[:20]:
        print(f"  [{h['start']:5d}] {NOTE_NAMES[h['root']]} {h['quality']:15s} dur={h['duration']:4d} conf={h['confidence']:.3f}")

    return True

if __name__ == "__main__":
    success = extract_harmony()
    sys.exit(0 if success else 1)