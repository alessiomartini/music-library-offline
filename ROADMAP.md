# Roadmap

<!--
Single file for todos, ideas, decisions and diary, read by Projects Overview
(https://alessiomartini.github.io/projects-overview/). Protocol: templates/ROADMAP.md of projects-overview.
The main tracker of the project is the ROADMAP.md of `music-library`; here only the offline part (pipeline and sources).
-->

## Done
- [x] Generic audio-first pipeline (Demucs, Basic Pitch, lyrics alignment, lv-chordia, music21 → JSON)
- [x] Your Song and E cerca 'e me capi transcribed as Score
- [x] Vocal range measured from the recording: 1743 songs (batch completed)

## To do
- [ ] MIDI-first path (hand-made karaoke MIDI instead of ML transcription): see `midi-intake/README.md`
- [ ] Transcribe more songs as Score and transfer them to `music-library`

## Decisions and things tried

- Separate repo from the frontend on purpose: here audio sources, Python pipeline, intermediates (`working/`) and curation notes;
  `music-library` receives only the normalized JSON.
- Free ML tools do not give a good enough audio-first transcription (2026-09-22): hence the MIDI-first
  path, which is added without replacing audio-first (it stays as a fallback).
- The long design document is `docs/DESIGN.md` in the `music-library` repo. The old code is in `pipeline/_OLD/`.

## Log
- 2026-11-21: 🤖 ROADMAP translated to English (language rule: projects in English or bilingual EN/IT).
- 2026-10-18: created ROADMAP.md (single protocol); references to docs/FUTURE-ARCHITECTURE.md → docs/DESIGN.md
