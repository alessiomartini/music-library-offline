# Roadmap

<!--
Unico file per todo, idee, decisioni e diario, letto da Projects Overview
(https://alessiomartini.github.io/projects-overview/). Protocollo: templates/ROADMAP.md di projects-overview.
Il tracker principale del progetto è il ROADMAP.md di `music-library`; qui solo la parte offline (pipeline e sorgenti).
-->

## Fatto
- [x] Pipeline audio-first generica (Demucs, Basic Pitch, allineamento testo, lv-chordia, music21 → JSON)
- [x] Your Song e E cerca 'e me capi trascritte come Score
- [x] Range vocale misurato dalla registrazione: 1743 canzoni (batch completato)

## Da fare
- [ ] Percorso MIDI-first (MIDI karaoke fatti a mano al posto della trascrizione ML): vedi `midi-intake/README.md`
- [ ] Trascrivere altri brani come Score e trasferirli in `music-library`

## Decisioni e cose provate

- Repo separato dal frontend apposta: qui sorgenti audio, pipeline Python, intermedi (`working/`) e note di curazione;
  `music-library` riceve solo i JSON normalizzati.
- Gli strumenti ML gratuiti non danno una trascrizione audio-first abbastanza buona (2026-09-22): da qui il percorso
  MIDI-first, che si aggiunge senza sostituire l'audio-first (resta come ripiego).
- Il documento di progetto lungo è `docs/DESIGN.md` nel repo `music-library`. Il codice vecchio sta in `pipeline/_OLD/`.

## Log
- 2026-10-18: creata ROADMAP.md (protocollo unico); riferimenti a docs/FUTURE-ARCHITECTURE.md → docs/DESIGN.md
