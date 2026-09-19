# Music Library Offline

This repository contains offline source material and curation work for the
`music-library` project. It is intentionally separate from the frontend
repository: the web repository contains the static React application and
published normalized JSON score assets, while this repository contains source
recordings, optional MusicXML/MIDI intermediates, corrections, and conversion
work.

The first reference song is **Your Song — Elton John**. Its new reference
workflow starts from a recording. The intended workflow is:

```text
source recording
  -> source separation
  -> vocal melody transcription
  -> lyric recognition/alignment
  -> harmony extraction from accompaniment
  -> human curation
  -> normalized JSON
  -> transfer to the web repository
```

## Layout

- `input/your-song/` — source recordings and provenance metadata. The existing
  `source.musicxml` and related MusicXML artifacts are preserved as optional
  historical/reference material only; they are not the primary transcription
  source for `Your Song`.
- `working/your-song/` — audio-first workflow notes and local intermediate
  working files.
- `corrections/your-song/` — manual corrections and curation notes.
- `output/json/` — final normalized JSON intended for transfer to the web
  repository. It is not ignored by default.
- `pipeline/` — future offline conversion tooling.

Raw audio is normally kept local and ignored by Git. Small metadata, workflow
notes, corrections, and final JSON are intended to remain trackable. MIDI is
optional and is not created merely because the architecture permits it.
MusicXML is also optional and may be used for comparison, authoring, or
inspection when useful. No transcription or conversion tooling is implemented
yet.
