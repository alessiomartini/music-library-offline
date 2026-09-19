#!/usr/bin/env python3
"""
Chunk 2 (Fixed): Vocal Melody Transcription with filtering
Uses Basic Pitch + post-processing to extract clean vocal melody.
"""
import json
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
import pretty_midi

PPQ = 960

VOCALS_WAV = Path(__file__).parent.parent / "working" / "your-song" / "vocals.wav"
OUTPUT_MIDI = Path(__file__).parent.parent / "working" / "your-song" / "vocal-midi.mid"
OUTPUT_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "vocal-events.json"

# Expected vocal range for Elton John's "Your Song" (male tenor)
VOCAL_MIN_PITCH = 55  # G3
VOCAL_MAX_PITCH = 79  # G5

# Minimum note duration (32nd note at PPQ=960 = 30 ticks)
MIN_DURATION_TICKS = 30

def transcribe_vocals():
    print(f"Input: {VOCALS_WAV}")

    if not VOCALS_WAV.exists():
        print(f"ERROR: Vocals file not found: {VOCALS_WAV}")
        return False

    print("Running Basic Pitch transcription...")
    model_output, midi_data, note_events = predict(str(VOCALS_WAV), ICASSP_2022_MODEL_PATH)

    # Save raw MIDI
    midi_data.write(str(OUTPUT_MIDI))
    print(f"Raw MIDI saved to: {OUTPUT_MIDI}")

    # Convert note_events to list of dicts
    # note_events: (start_sec, end_sec, pitch, velocity, contour)
    raw_notes = []
    for item in note_events:
        start_sec, end_sec, pitch, velocity = float(item[0]), float(item[1]), int(item[2]), float(item[3])
        raw_notes.append({
            "start_sec": start_sec,
            "end_sec": end_sec,
            "pitch": pitch,
            "velocity": velocity,
            "duration_sec": end_sec - start_sec
        })

    print(f"Raw notes detected: {len(raw_notes)}")

    # Filter 1: Remove notes before first vocal activity (~9s based on RMS analysis)
    # The original song starts at ~1.1s, but Demucs vocal stem has silence until ~9s
    first_vocal_sec = 9.0
    filtered = [n for n in raw_notes if n["start_sec"] >= first_vocal_sec]
    print(f"After time filter (>{first_vocal_sec}s): {len(filtered)}")

    # Filter 2: Vocal range filter
    filtered = [n for n in filtered if VOCAL_MIN_PITCH <= n["pitch"] <= VOCAL_MAX_PITCH]
    print(f"After pitch filter ({VOCAL_MIN_PITCH}-{VOCAL_MAX_PITCH}): {len(filtered)}")

    # Filter 3: Velocity threshold (remove very quiet artifacts)
    # Basic Pitch velocity is 0-1, filter very low confidence
    filtered = [n for n in filtered if n["velocity"] >= 0.3]
    print(f"After velocity filter (>=0.3): {len(filtered)}")

    # Filter 4: Minimum duration
    # Convert to ticks for duration check
    # We'll do this after getting tempo
    pm = pretty_midi.PrettyMIDI(str(OUTPUT_MIDI))
    tempo = pm.get_tempo_changes()[1][0] if len(pm.get_tempo_changes()[1]) > 0 else 120.0
    tempo = float(tempo)
    print(f"Detected tempo: {tempo:.1f} BPM")

    seconds_per_tick = 60.0 / (tempo * PPQ)

    score_events = []
    for n in filtered:
        start_ticks = int(round(n["start_sec"] / seconds_per_tick))
        end_ticks = int(round(n["end_sec"] / seconds_per_tick))
        duration_ticks = end_ticks - start_ticks

        if duration_ticks >= MIN_DURATION_TICKS:
            score_events.append({
                "start": start_ticks,
                "duration": duration_ticks,
                "pitch": n["pitch"],
                "velocity": n["velocity"],
                "kind": "note"
            })

    print(f"After min duration filter (>{MIN_DURATION_TICKS} ticks): {len(score_events)}")

    # Sort by start time
    score_events.sort(key=lambda e: e["start"])

    # Save events JSON
    output_data = {
        "ppq": PPQ,
        "tempo_bpm": tempo,
        "events": score_events
    }

    with open(OUTPUT_EVENTS, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"Events saved to: {OUTPUT_EVENTS}")
    print(f"Total note events: {len(score_events)}")

    # Print first 20
    for e in score_events[:20]:
        print(f"  start={e['start']:5d}, dur={e['duration']:4d}, pitch={e['pitch']:3d} (MIDI {e['pitch']}) vel={e['velocity']:.3f}")

    # Pitch statistics
    pitches = [e["pitch"] for e in score_events]
    print(f"\nPitch range: {min(pitches)} - {max(pitches)}")
    print(f"Mean pitch: {np.mean(pitches):.1f}")

    return True

if __name__ == "__main__":
    success = transcribe_vocals()
    sys.exit(0 if success else 1)