# midi-intake

Landing area for the MIDI-first offline workflow (see the root
[README.md](../README.md) and `docs/FUTURE-ARCHITECTURE.md` in the
`music-library` repo for the two-path pipeline this feeds into).

## Usage

1. Drop newly downloaded MIDI files, with whatever filename they arrive as
   (either `Title - Artist.mid` or `Artist - Title.mid` — see "Title/artist
   order" below), into `inbox/`.
2. Run the organizer in dry-run mode first (default — nothing is moved or
   deleted):

   ```bash
   python pipeline/midi_first/organize_midi_intake.py
   ```

   It prints a report: which files it grouped as the same song, which
   source website it could detect for each (best-effort — see below),
   which files look like exact-content duplicates re-hosted under a
   different name, and which songs don't have a `songs/<slug>.json` yet.
3. Review the report. Fix anything wrong by hand (rename a file in
   `inbox/`, or add an entry to `source-overrides.json` — see
   `source-overrides.example.json`).
4. Re-run with `--apply` to actually move files from `inbox/` into
   `library/<slug>/`, rename them to include the detected source(s), and
   delete confirmed duplicate copies.

## Title/artist order

Real filenames aren't consistent about which side of the `-` is the title
and which is the artist. Most of Alessio's bulk collection is
`Title - Artist.mid` (e.g. `Voglio A Te - G. Celeste.mid`); some
individually-picked files are `Artist - Title.mid` instead (e.g.
`Dalla - Caruso.mid`). The organizer detects an abbreviated `Initial.
Surname` credit or the literal `Vari` ("various artists") marker — both
common in the real data — as a strong, side-independent signal for which
segment is the artist, and otherwise defaults to the dominant
`Title - Artist` convention. A file that matches neither and doesn't follow
the default needs an entry in `title-artist-overrides.json` (filename →
`"artist-first"` or `"title-first"`) — already populated for the known
`Dalla`/`Queen`/`The Beatles` files. Getting this wrong for a song by an
artist with many songs is exactly the kind of collision the next section
guards against, but check `title-artist-overrides.json` first if a report
looks off for one specific artist.

## Source-site detection (best-effort)

Two methods are tried, in order; the result is always reported so you can
correct it:

1. The NTFS `Zone.Identifier` alternate data stream that browsers attach to
   a downloaded file (`HostUrl=...`). Lost if the file was moved through a
   zip, a non-NTFS filesystem, or wasn't downloaded directly by a browser —
   don't expect this to work for every file.
2. A domain-looking string inside the MIDI's own Copyright/Text meta
   events, when the source site stamped one in.

When neither works, the file is marked `source: unknown`. You can fix it
without re-downloading anything by adding a line to
`source-overrides.json` (original filename → site).

## Deduplication

"Duplicate" here means *the same musical content* (same notes, same
timing), hashed while ignoring copyright/text metadata — not just a
similar filename. Two genuinely different MIDI transcriptions of the same
song are **not** duplicates; they're kept side by side in
`library/<slug>/` as separate files (useful later for cross-referencing
multiple sources, which this tool doesn't attempt yet).

## Same song, different interpretations — and avoiding collisions

The same song commonly shows up as several genuinely different files —
piano-only, full band, a live recording, a different transcriber's take.
A trailing qualifier on the title, like `Song (Piano Version).mid` or
`Song - Live 1981.mid`, is recognized and does **not** split these into
separate songs: they're grouped into the same `library/<slug>/` folder,
and the qualifier is kept in the destination filename (alongside the
source) specifically so you can tell interpretations apart at a glance —
e.g. `Napul'e' (Live 1981)__src-somesite.mid`.

The opposite case is just as important: two **different** songs that
happen to share a title (different artists) must never be merged into one
folder. The organizer checks for this — both within one run and against
songs already organized by an earlier run (each `library/<slug>/` folder
keeps a small `.meta.json` recording which artist(s) it belongs to) — and
disambiguates automatically by folding the artist into the slug
(`library/song/` vs. `library/song-other-artist/`), printing a
`COLLISION WARNINGS` line in the report whenever this happens. Check that
line after every run.

## Supported file types

Both `.mid`/`.midi` and `.kar` ("Soft Karaoke") files — `.kar` is the same
MIDI format under a different extension convention.

## What this tool does not do

It does not create `songs/<slug>.json` config files for new songs, parse
lyrics, or transcribe anything — see `import_karaoke_midi.py` and
`extract_midi_lyrics.py` for that (run after a song's MIDI is organized
here).
