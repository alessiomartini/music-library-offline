# Music Library Offline

This repository contains offline source material and the audio-first
transcription pipeline for the `music-library` project. It is intentionally
separate from the frontend repository: the web repository (`music-library`)
contains the static React application and consumes published normalized JSON
score assets; this repository contains source recordings, the Python
pipeline that turns them into those assets, working intermediates, and
curation notes.

Two songs have been transcribed so far: **Your Song** (Elton John) and
**E cerca 'e me capi** (Pino Daniele). The workflow, per song:

```text
source recording
  -> source separation (Demucs)
  -> vocal melody transcription (or reuse of a curated MusicXML reference)
  -> lyric recognition/alignment
  -> harmony extraction from accompaniment (librosa chroma + beat tracking)
  -> MusicXML assembly (music21)
  -> normalized JSON (schemaVersion 1 envelope)
  -> transfer to the web repository (src/data/songs/<slug>.json)
```

## Layout

- `input/` — source recordings.
- `working/<slug>/` — intermediate files per song: separated stems,
  vocal/harmony event JSON, aligned lyrics, assembled MusicXML. Regenerated
  by the pipeline; not hand-edited except `curation-plan.md` /
  `musicxml-audit.md` style curation notes.
- `corrections/<slug>/` — manual corrections and curation notes.
- `output/json/` — final normalized JSON, transferred verbatim into the web
  repository's `src/data/songs/`. This is the one directory whose content is
  meant to exactly match what's published on the web.
- `pipeline/` — the numbered conversion scripts (below). Working, not
  aspirational.

Raw audio, MIDI, and Python virtualenvs/caches are gitignored. Working JSON,
corrections, and final output JSON are tracked.

## Pipeline scripts

Each step is numbered; a `_pino` suffix is Pino Daniele's per-song copy of
the same step (there is no shared, parameterized pipeline yet — each song
currently has its own copy of scripts 01–06, which is duplication worth
collapsing into one parameterized pipeline once a third song is added, not
before).

1. `01_separate*.py` — Demucs source separation into vocal + accompaniment
   stems.
2. `02_transcribe_vocals*.py` — automatic vocal melody transcription (Basic
   Pitch), **or** `02c_use_curated_melody.py`, which instead reads a
   manually curated `curated.musicxml` as the authoritative melody when one
   exists (this is what Your Song actually uses — its `02_transcribe_vocals`
   output was superseded and removed). There is no working curated-melody
   path for Pino Daniele yet; it uses the automatic transcription directly.
3. `03_align_lyrics*.py` — lyric/syllable alignment to the vocal events.
4. `04_extract_harmony*.py` — chroma-template chord detection per beat,
   merged into harmony events. **Durations are derived from the next
   event's already-rounded start tick, not rounded independently** — see
   "Harmony tick-tiling" below.
5. `05b_assemble_musicxml*.py` — assembles voice + harmony into MusicXML via
   `music21`.
6. `06b_musicxml_to_json*.py` — reads the MusicXML back and emits the
   `schemaVersion: 1` normalized JSON envelope the web repo's
   `loadScoreJson` expects.

Run a song's steps in order (2 or 2c, 3, 4, 5b, 6b); each reads the previous
step's output from `working/<slug>/`.

## Harmony tick-tiling (fixed 2026-09-20)

The harmony extractor and the MusicXML-to-JSON converter both used to round
each chord event's `start` and `duration` **independently** — once from real
beat timing in step 4, and again from `music21`'s float `offset` /
`quarterLength` in step 6. Two independent roundings of dependent quantities
can each land on either side of `.5`, which produced stray one-tick
gaps/overlaps between consecutive chords and failed the web repo's
`validateScore` overlap check on both published songs (`E cerca 'e me capi`
had no working score in the app for this reason — the app rendered
nothing rather than an invalid chart).

Fixed in both `04_extract_harmony*.py` and `06b_musicxml_to_json*.py` by
deriving `duration = nextEvent.start - event.start` from the already-rounded
starts instead of rounding duration separately. This guarantees exact tiling
by construction. Re-run steps 4 through 6b for a song if you touch harmony
extraction again, and copy the regenerated `output/json/<slug>.json` into the
web repo — don't hand-patch a published JSON asset's harmony array.

Also fixed at the same time: the JSON writer was emitting explicit `null` for
absent optional fields (`tie`, `melisma`, `elision`, `lyrics`, `slashBass`).
The web repo's schema treats "optional" as "key absent", not `null`; `null`
failed validation. The writer now omits the key instead.

## Transferring to the web repository

```bash
cp output/json/<slug>.json ../music-library/src/data/songs/<slug>.json
```

then, in `music-library`, run `npm run validate` to confirm the score is
structurally valid before it reaches `src/data/songs/index.ts`.
