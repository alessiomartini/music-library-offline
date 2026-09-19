#!/usr/bin/env python3
"""
Chunk 2: Vocal Melody Transcription
Uses Basic Pitch to transcribe vocals.wav to MIDI, then converts to symbolic events.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
import pretty_midi

# PPQ from web repo's score model
PPQ = 960

VOCALS_WAV = Path(__file__).parent.parent / "working" / "your-song" / "vocals.wav"
OUTPUT_MIDI = Path(__file__).parent.parent / "working" / "your-song" / "vocal-midi.mid"
OUTPUT_EVENTS = Path(__file__).parent.parent / "working" / "your-song" / "vocal-events.json"

def transcribe_vocals():
    print(f"Input: {VOCALS_WAV}")

    if not VOCALS_WAV.exists():
        print(f"ERROR: Vocals file not found: {VOCALS_WAV}")
        return False

    # Run Basic Pitch prediction
    print("Running Basic Pitch transcription...")
    model_output, midi_data, note_events = predict(str(VOCALS_WAV), ICASSP_2022_MODEL_PATH)

    # Save MIDI
    midi_data.write(str(OUTPUT_MIDI))
    print(f"MIDI saved to: {OUTPUT_MIDI}")

    # Convert to our event format (ticks at PPQ=960)
    # note_events is list of (start_time_sec, end_time_sec, pitch, velocity, contour)
    events = []
    for item in note_events:
        start_sec, end_sec, pitch, velocity = item[0], item[1], item[2], item[3]
        events.append({
            "start_sec": float(start_sec),
            "end_sec": float(end_sec),
            "pitch": int(pitch),
            "velocity": float(velocity)
        })

    # Better: use pretty_midi to get proper timing with tempo
    pm = pretty_midi.PrettyMIDI(str(OUTPUT_MIDI))

    # Get tempo (first tempo change)
    tempo = pm.get_tempo_changes()[1][0] if len(pm.get_tempo_changes()[1]) > 0 else 120.0
    print(f"Detected tempo: {tempo:.1f} BPM")

    # Convert seconds to ticks: ticks = seconds * (tempo/60) * PPQ
    seconds_per_tick = 60.0 / (tempo * PPQ)

    score_events = []
    for instrument in pm.instruments:
        if instrument.is_drum:
            continue
        for note in instrument.notes:
            start_ticks = int(round(note.start / seconds_per_tick))
            end_ticks = int(round(note.end / seconds_per_tick))
            duration_ticks = end_ticks - start_ticks

            if duration_ticks > 0:
                score_events.append({
                    "start": start_ticks,
                    "duration": duration_ticks,
                    "pitch": note.pitch,
                    "velocity": note.velocity,
                    "kind": "note"
                })

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

    # Print first few events
    for e in score_events[:10]:
        print(f"  start={e['start']}, dur={e['duration']}, pitch={e['pitch']} (MIDI note {e['pitch']})")

    return True

if __name__ == "__main__":
    success = transcribe_vocals()
    sys.exit(0 if success else 1)