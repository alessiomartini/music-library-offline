# Music Library Offline

This repository contains offline source material and curation work for the
`music-library` project. It is intentionally separate from the frontend
repository: the web repository contains the static React application and
published normalized JSON score assets, while this repository contains source
MusicXML, optional MIDI/audio material, corrections, and conversion work.

The first reference song is **Your Song — Elton John**. The intended workflow
is:

```text
source asset
  -> inspection
  -> correction
  -> normalized JSON
  -> transfer to the web repository
```

## Layout

- `input/your-song/` — original source assets. `source.musicxml` is preserved
  unchanged for provenance and comparison.
- `working/your-song/` — local inspection and intermediate working files.
- `corrections/your-song/` — manual corrections and curation notes.
- `output/json/` — final normalized JSON intended for transfer to the web
  repository. It is not ignored by default.
- `pipeline/` — future offline conversion tooling.

No transcription or conversion tooling is implemented yet.

