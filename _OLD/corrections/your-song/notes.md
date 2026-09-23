# Your Song Audio-First Working Notes

The `Your Song` reference workflow is restarted from the recording, not from
the previously obtained MusicXML. The current goal is to prepare a curated
lead-sheet score containing only vocal melody, lyrics, harmony, and meter.
Piano notation, complete orchestration, full accompaniment, and every
instrumental performance detail are intentionally out of scope for the first
score.

## Intended workflow

```text
source recording
    ↓
source separation
    ├── vocal stem
    │      ↓
    │   melody transcription
    │      ↓
    │   lyric recognition/alignment
    │
    └── accompaniment/instrumental material
           ↓
        harmony analysis
           ↓
       human curation
           ↓
      normalized JSON
```

Source separation is expected before vocal transcription. The vocal path is
responsible for melody pitches, timing, musically meaningful rests, lyrics,
and lyric-to-note alignment. The accompaniment path is used primarily to
derive independent timed harmony events; it is not a requirement to recreate
the complete arrangement.

MIDI is optional. A future experiment may use audio → MIDI → symbolic
processing, direct symbolic transcription, or another route. No MIDI file is
created merely because it is an available intermediate. MusicXML is also
optional and may be used for authoring, inspection, or comparison, but it is
not the source of truth for this workflow.

Automatic transcription, lyric recognition/alignment, and harmony analysis
require human verification and correction. Specific tools and algorithms
remain open until transcription experiments provide evidence.

The existing MusicXML audit, curation plan, and MusicXML working file record a
previous approach. They remain available for optional comparison only and are
not inputs to the new audio-first transcription workflow.
