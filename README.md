# Music Library Offline

Offline source material and Python pipelines for the `music-library` project
(<https://github.com/alessiomartini/music-library>). The web repository is a static React app that consumes
published normalized JSON; this repository holds the source recordings and MIDI files, the scripts that turn them
into those assets, working intermediates, and curation notes. The long-term design is `docs/DESIGN.md` in the
`music-library` repository (it is not in this one).

## What is active

| Pipeline | Scripts | What it produces |
| --- | --- | --- |
| Vocal range from the recording | `pipeline/audio_first/vocal_distribution.py`, `vocal_batch.py`, `separate.py` | `output/vocal/<slug>.json` for 1902 songs (published by the web repo as vocal-range histograms) |
| MIDI-first score | `pipeline/midi_first/*.py`, then shared `pipeline/assemble_musicxml.py` and `pipeline/musicxml_to_json.py` | `output/json/<slug>.json` (normalized `schemaVersion 1` score); so far `anna-e-marco` |
| MIDI intake | `pipeline/midi_first/organize_midi_intake.py` | `midi-intake/library/<slug>/` (see `midi-intake/README.md`) |

The older audio-first transcription (Demucs + Basic Pitch + forced alignment + lv-chordia) is **legacy**: it
produced the first two published scores (Your Song, E cerca 'e me capi) but free ML tools were not accurate
enough. Its scripts are in `pipeline/_OLD/audio_first/`, its per-song data in `_OLD/`, and its full
documentation is in [`docs/legacy.md`](docs/legacy.md). Those scripts do not run from there as they are
(`REPO_ROOT` is one level too shallow).

## Requirements

Python dependencies are in `pipeline/pyproject.toml` (`pip install -e pipeline`; run tests with `pytest` from the
repo root). **MuseScore 4** is needed for the MIDI-first path (headless quantization, see
`pipeline/musescore_import.py`); it is located through the `MUSESCORE4_PATH` environment variable, its default
Windows install path, or `mscore`/`mscore4portable` on `PATH`. Vocal ranges also need `yt-dlp` (with `node` for
its JS runtime), `ffmpeg` and Demucs.

## Vocal range from the recording

`python pipeline/audio_first/vocal_distribution.py <slug> --title "..." --artist "..."` measures how long each
note is sung in the original recording, without needing a score:

```text
YouTube search (accepted only if the duration matches Deezer's within 5 s)
  -> Demucs vocal stem (separate.py)
  -> pYIN f0 track (working/<slug>/f0.npz, cached)
  -> seconds sung per MIDI note -> output/vocal/<slug>.json
```

The JSON has two normalized histograms (shares of the singing time, and shares of the sung notes), the range
(notes with at least 1% of the time) and the core (10th-90th percentile of the time). Thresholds are in
`pipeline/constants.py`. Almost all the time is Demucs.

### `input/*.source` files

`input/<slug>.source` holds one line: the YouTube video id of the recording used for that song (for example
`dCdbKK_hyQw`). `vocal_distribution.py` writes it after the first successful match and reuses it on later runs;
`--youtube <id>` overrides it. The audio itself (`input/<slug>.mp3`/`.webm`, stems, f0 tracks) is gitignored, so
the `.source` files are what makes a measurement reproducible: delete one to force a new search.

### Many songs

`python pipeline/audio_first/vocal_batch.py songs.tsv --gpu` (TSV lines: `slug`, `title`, `artist`, optional
YouTube id). It is resumable (songs with an `output/vocal/<slug>.json` are skipped) and logs failures to
`working/vocal-batch.log`. `--gpu` separates on the GPU, one song at a time, while the other worker downloads or
tracks pitch on the CPU. It needs the CUDA build of PyTorch in its own environment:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu126
.venv/Scripts/python -m pip install demucs soundfile
```

Timing measured on one PC (2026-10-16, 148 s of audio): CPU 148 s (123 s with overlap 0.1, same histogram), GPU
76 s; the `--gpu` batch did about 2 minutes per song.

Validation on 2026-10-15 against published lead sheets: E cerca 'e me capi overlap 0.91; Anna e Marco same notes
an octave lower than the karaoke-MIDI lead sheet (0.77 by pitch class); Your Song's audio-first lead sheet is too
unreliable to compare (it reaches A5).

## MIDI-first score

Many songs have good human-made MIDI files (often karaoke-style, with lyrics synced to the notes), which avoids
ML transcription. Steps, per song slug (each reads `songs/<slug>.json` for song-specific settings):

1. Organize downloaded MIDI files: `python pipeline/midi_first/organize_midi_intake.py` (dry run; `--apply` to
   move into `midi-intake/library/<slug>/`). See `midi-intake/README.md`.
2. `import_karaoke_midi.py <slug>`: find the vocal track and quantize it through MuseScore 4
   (`working/<slug>/vocal-events.json`).
3. `extract_midi_lyrics.py <slug>`: attach the MIDI's embedded syllables to the notes.
4. `extract_midi_harmony.py <slug>`: chord templates over the accompaniment notes.
5. Optional: `parse_chord_chart_pdf.py <slug>` then `apply_verified_source.py <slug>` replace lyrics and harmony
   with a human-verified chart in `corrections/<slug>/verified-source.json`, keeping the MIDI timing.
6. `assemble_musicxml.py <slug>` (MusicXML views in `working/<slug>/`) and `musicxml_to_json.py <slug>`
   (`output/json/<slug>.json`).
7. Review `working/<slug>/lead-sheet.musicxml` and the JSON (automatic extraction needs correction), then copy to
   the web repo: `cp output/json/<slug>.json ../music-library/src/data/songs/<slug>.json`, wire it into
   `src/data/songs/index.ts` and run `npm run validate` there.

## Layout

- `songs/<slug>.json`: hand-edited pipeline input (title, key, tempo, meter, source settings, lyrics).
- `input/`: source recordings (gitignored) and the tracked `<slug>.source` files.
- `midi-intake/`: inbox and organized library of source MIDI files (gitignored media; overrides tracked).
- `working/<slug>/`: pipeline intermediates, regenerated on every run, never hand-edited.
- `corrections/<slug>/`: manual correction notes and verified sources. Not read by the pipeline except
  `verified-source.json`.
- `output/json/`: final scores, copied verbatim to the web repo. `output/vocal/`: vocal-range measurements.
- `pipeline/`: active scripts (`audio_first/` for vocal range and separation, `midi_first/`, shared modules at the
  root); `pipeline/_OLD/` and `_OLD/` are the legacy audio-first scripts and data.
- `tests/`: pytest suite for the MIDI-first and vocal-distribution code.

Raw audio, MIDI and virtualenvs/caches are gitignored; working JSON, corrections and output JSON are tracked.
