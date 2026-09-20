#!/usr/bin/env python3
"""
Chunk 4: Harmony Extraction for Pino Daniele - E cerca 'e me capi
"""
import json
import numpy as np
import librosa
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

ACCOMPANIMENT_WAV = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "accompaniment.wav"
OUTPUT_HARMONY = Path(__file__).parent.parent / "working" / "e-cerca-e-me-capi" / "harmony-events.json"

PPQ = 960

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

    y, sr = librosa.load(str(ACCOMPANIMENT_WAV), sr=None)
    print(f"Audio loaded: {len(y)/sr:.1f}s at {sr}Hz")

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    print(f"Chroma shape: {chroma.shape} (frames x 12)")

    frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=512)

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0])
    else:
        tempo = float(tempo)
    print(f"Detected tempo: {tempo:.1f} BPM")

    beat_times = librosa.frames_to_time(beats, sr=sr)

    hop_length = 512
    frame_duration = hop_length / sr

    harmony_events = []

    for i, beat_time in enumerate(beat_times):
        window_start = max(0, int((beat_time - 0.5) / frame_duration))
        window_end = min(chroma.shape[1], int((beat_time + 0.5) / frame_duration))

        if window_end <= window_start:
            continue

        avg_chroma = np.mean(chroma[:, window_start:window_end], axis=1)

        if np.sum(avg_chroma) > 0:
            avg_chroma = avg_chroma / np.sum(avg_chroma)

        best_chord = None
        best_score = -1
        best_root = 0

        for root in range(12):
            for quality, template in CHORD_TEMPLATES.items():
                rotated = np.roll(template, root)
                score = np.dot(avg_chroma, rotated)
                if score > best_score:
                    best_score = score
                    best_chord = quality
                    best_root = root

        if best_chord:
            start_ticks = int(round(beat_time * (tempo / 60.0) * PPQ))

            if i + 1 < len(beat_times):
                next_beat_time = beat_times[i + 1]
                duration_sec = next_beat_time - beat_time
            else:
                duration_sec = 60.0 / tempo

            duration_ticks = int(round(duration_sec * (tempo / 60.0) * PPQ))

            harmony_events.append({
                "start": start_ticks,
                "duration": duration_ticks,
                "root": best_root,
                "quality": best_chord,
                "slashBass": None,
                "confidence": float(best_score)
            })

    # Merge consecutive identical chords
    merged = []
    for event in harmony_events:
        if merged and merged[-1]["root"] == event["root"] and merged[-1]["quality"] == event["quality"]:
            merged[-1]["duration"] += event["duration"]
        else:
            merged.append(event)

    print(f"Detected {len(merged)} harmony events (merged from {len(harmony_events)})")

    output = {
        "ppq": PPQ,
        "tempo_bpm": float(tempo),
        "harmony": merged
    }

    with open(OUTPUT_HARMONY, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Output: {OUTPUT_HARMONY}")

    print("\nFirst 20 harmony events:")
    for h in merged[:20]:
        print(f"  [{h['start']:5d}] {NOTE_NAMES[h['root']]} {h['quality']:15s} dur={h['duration']:4d} conf={h['confidence']:.3f}")

    return True

if __name__ == "__main__":
    success = extract_harmony()
    sys.exit(0 if success else 1)