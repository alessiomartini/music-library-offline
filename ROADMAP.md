# Roadmap

<!-- Single file for todo, ideas, decisions and log, read by Projects Overview (https://alessiomartini.github.io/projects-overview/). Protocol: templates/ROADMAP.md in projects-overview. -->

The main tracker of the project is the ROADMAP.md of `music-library`; this one covers only the offline part (pipeline and sources).

## Done
- [x] Generic audio-first pipeline (Demucs, Basic Pitch, lyric alignment, lv-chordia, music21 → JSON)
- [x] Your Song and E cerca 'e me capi transcribed as Score
- [x] Vocal range measured from the recording: 1743 songs (batch completed)

## To do
- [ ] MIDI-first path (hand-made karaoke MIDI instead of ML transcription): see `midi-intake/README.md`
- [ ] Transcribe more pieces as Score and transfer them to `music-library`

## Decisions and things tried

- Separate repo from the frontend on purpose: audio sources, Python pipeline, intermediates (`working/`) and curation notes live here;
  `music-library` receives only the normalized JSON.
- Free ML tools do not give an audio-first transcription that is good enough (2026-09-22): hence the MIDI-first path,
  which is added without replacing the audio-first one (kept as a fallback).
- The long design document is `docs/DESIGN.md` in the `music-library` repo. The old code is in `pipeline/_OLD/`.

## Log
- 2026-11-21: 🤖 Docs cleanup: README rewritten around the active pipelines (vocal range, MIDI-first, `.source` files), legacy audio-first docs moved to `docs/legacy.md`, CLAUDE.md fixed, ROADMAP translated to English.
- 2026-10-18: created ROADMAP.md (single protocol); references to docs/FUTURE-ARCHITECTURE.md → docs/DESIGN.md
