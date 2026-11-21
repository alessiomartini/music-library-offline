# Claude Code instructions

Offline half of `music-library`: source recordings, Python pipelines and their intermediates. Read `README.md`
first (active pipelines, `.source` files, layout). The legacy audio-first pipeline is documented in `docs/legacy.md`.

- The long-term design (`docs/DESIGN.md`) is in the separate repo `alessiomartini/music-library`, not here.
  It is partly outdated; trust the code and this README.
- Never commit audio/MIDI sources (see `.gitignore`) or regenerated `working/` intermediates.
  Exception: `working/<slug>/` JSON files that are already tracked for published songs.
- Run `pytest` after changing anything under `pipeline/`.
- `pipeline/_OLD/` and `_OLD/` are legacy; do not edit them unless asked.
