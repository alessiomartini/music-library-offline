# Your Song MusicXML Audit

## 1. Source identity

- **Source:** `input/your-song/source.musicxml`
- **File size:** 930,144 bytes
- **SHA-256:** `0DFA2A30D6E758CCA81C0990A0B1DB65A60DCDCFDD72482F9FE521E792574E21`
- **Audit method:** read-only inspection with Python's standard-library
  `xml.etree.ElementTree`; no MusicXML or transcription dependency was
  installed.
- The source file was not rewritten.

The observations below distinguish direct XML facts from interpretation and
items requiring human review. Syntactic validity is not treated as evidence
that the musical content is correct.

## 2. Format

### Observed facts

- Root element: `score-partwise`
- MusicXML version: `4.0`
- Four `<score-part>` definitions and four matching `<part>` elements.
- The file contains layout, MIDI playback, stem, beam, articulation, and
  print/page metadata in addition to musical events.

### Interpretation

`score-partwise` is a suitable source representation for part-by-part
inspection. The file is not a compact lead-sheet source: it contains a vocal
line plus piano and string material, including multiple staves/voices.

## 3. Parts

| ID | XML name | Instrument metadata | Measures | Observed structure | Likely role and evidence |
|---|---|---|---:|---|---|
| `P1` | Voice | `Voice`, `voice.vocals`, MIDI program 53 | 68 | 459 pitched notes, 88 rests, one voice, no backups or chord-note markers | **Voice.** The part name and voice instrument metadata agree; it is monophonic in the source. |
| `P2` | Piano | `Piano` | 68 | 1,229 pitched notes, 64 rests, voices `1`, `2`, `5`, `6`, 81 backups, 379 chord-note markers, two clefs/staves | **Instrument.** The explicit part name, piano metadata, multiple staves, voices, and simultaneous chord notes identify piano material. It is polyphonic. |
| `P3` | Violoncellos | `Cellos`, cello/string metadata where present | 68 | 140 pitched notes, 54 rests, voices `1`, `2`, 10 backups, 70 chord-note markers | **Instrument.** The explicit part name and low string clef/material identify a cello section. It is not a v1 monophonic stream as-is. |
| `P4` | Strings | `Strings`, string metadata where present | 68 | 339 pitched notes, 42 rests, voices `1`, `2`, 10 backups, 189 chord-note markers | **Instrument.** The explicit part name and string material identify an instrumental section. It contains simultaneous notes and multiple voices. |

The role assignments above do not rely on part order alone. They use the
declared part names, instrument names/sounds, clefs, staves, and event
structure. `P1` is the only direct candidate for the first v1 vocal part.
`P2`–`P4` require either separate monophonic lanes or a curation decision
before they can be represented by the current `ScorePart` invariant.

## 4. Timeline and measures

### Observed facts

- There are 68 numbered measures, numbered `1` through `68`, in every part.
- The first measure is not marked `implicit`; no pickup/anacrusis marker was
  observed.
- The initial time signature is `4/4` at measure 1.
- Explicit `2/4` measures occur at:
  `10`, `19`, `26`, `29`, `40`, `49`, `56`, `59`, `62`, `65`.
- Each of those is followed by an explicit return to `4/4` in the next
  measure: `11`, `20`, `27`, `30`, `41`, `50`, `57`, `60`, `63`, `66`.
- The key signature is `-3` fifths from the beginning, with no later key
  signature change observed. This is three flats (E-flat major or C minor);
  the mode is not explicitly supplied in the `<key>` element.
- `divisions` is `8` in each part's attributes. Thus one quarter note is
  eight MusicXML duration units and one eighth note is four units.
- The source uses duration values including `1`, `2`, `3`, `4`, `6`, `8`,
  `12`, `16`, `24`, and `32`.
- No change of `divisions` was observed.
- Measure content is not a simple single cursor in the piano and string
  parts: backups, multiple voices, multiple staves, and chord-note markers
  are used. Some voice/staff lanes have different local extents in a measure,
  so a conversion must interpret MusicXML voice/staff timing rather than
  treating serialized note order as one timeline.

### Compatibility with the frozen timing model

The fixed division is promising for exact conversion. With `PPQ = 960`,
eight MusicXML divisions per quarter note gives a deterministic conversion
factor of **120 score ticks per source division**. Nominal full-measure
durations are therefore:

- `4/4`: 32 source divisions = 3,840 score ticks;
- `2/4`: 16 source divisions = 1,920 score ticks.

The source can map to integer absolute ticks without floating-point time.
However, it does **not** map directly to the current one-time-signature,
contiguous-measure `Score` representation because it contains explicit
mid-score `2/4` changes. The v1 score model also stores one score-level time
signature, not a time-signature event sequence.

**Human review required:** decide whether the first reference asset should
preserve the alternating `4/4`/`2/4` structure through a future extension,
re-bar or curate the source into the currently supported scope, or defer the
source until time-signature changes are supported. This must not be silently
flattened during conversion.

## 5. Notes and rhythm

### Observed facts

- `P1` contains 459 pitched notes and 88 rests. It has one voice and no
  `<backup>` elements, so it is structurally the cleanest candidate for a
  monophonic voice part.
- `P2` contains piano chords (`<chord>`), multiple voices and staves, and
  `<backup>` elements. It is polyphonic and cannot be represented as one v1
  monophonic `ScorePart` without selecting or splitting lanes.
- `P3` and `P4` also contain `<chord>` markers, multiple voices, and backups.
  They are polyphonic instrumental material.
- Dotted rhythms are present: 64 dotted notes in `P1`, 163 in `P2`, 8 in
  `P3`, and 15 in `P4`.
- Tuplets: none observed.
- Grace notes: none observed.
- Fermatas: none observed.
- `<beam>` elements are common and are notation/rendering metadata, not
  independent timing.
- Staccato articulations occur 30 times.
- No repeats or endings were observed.
- Rests are present in all four parts.

### Conflicts and curation implications

- Multiple voices/chords in `P2`–`P4` conflict with the v1 requirement that
  events within a `ScorePart` be ordered and non-overlapping.
- The source has multiple time signatures, which conflicts with the current
  one-score-level-time-signature model.
- Dotted durations are compatible in principle because they can be converted
  to exact integer ticks.
- Tuplets, grace notes, fermatas, repeats, and jumps do not currently create
  observed source conflicts, but remain outside the v1 model if introduced
  later.
- The first reference workflow should not force piano or string chords into a
  single monophonic event stream. It should either curate selected lines or
  wait for a representation that supports polyphonic lanes.

## 6. Harmony

### Observed facts

- No `<harmony>` elements were found.
- Therefore the source contains no MusicXML chord-root, chord-kind,
  bass-alteration, or slash-chord annotations to transfer.
- The many `<chord>` elements are note-level simultaneous-note markers in
  instrumental parts; they are not `<harmony>` events and must not be
  mistaken for chord symbols.

### Interpretation

The source does not provide the independent harmony layer required by the
normalized score. Harmony will need to come from a separate source or from
manual curation. No semantic `ChordQuality` mapping should be invented from
the piano note clusters alone. In particular, slash-bass harmony cannot be
recovered as an authoritative `HarmonyEvent` from this file without musical
analysis.

## 7. Lyrics

No song lyrics were found in the vocal part `P1`. There are four `<lyric>`
elements in `P2`, attached to piano notes, containing the labels:

- `Piano -- Right Hand`
- `Vocals` (repeated three times)

These are notation labels/annotations, not lyric text for the song. They are
not suitable for the `ScoreLyric` model and must not be copied into the voice
part.

The actual song lyrics will therefore need to come from a separate,
rights-appropriate source and be manually aligned to the curated vocal notes.
No lyrics were added by this audit.

## 8. Pitch and notation

### Observed facts

- Pitch spelling uses MusicXML step/alter/octave fields.
- The source predominantly uses flats, including E-flat, B-flat, G-flat, and
  A-flat spellings, with explicit natural accidentals also present.
- The source octave numbering follows MusicXML's conventional numbering; no
  `<transpose>` element was observed.
- Clefs include:
  - `P1`: treble clef (`G`, line 2);
  - `P2`: treble and bass clefs, with later clef changes;
  - `P3`: bass clef;
  - `P4`: treble clef.
- No instrument transposition metadata was observed.

### Compatibility

The pitch fields can be converted deterministically to sounding MIDI-style
integer pitch values. The lack of `<transpose>` removes one major ambiguity.
Enharmonic spelling should remain a separate notation concern; the normalized
pitch value should not encode the flat/sharp spelling.

The missing explicit mode for the `-3` key signature and the distinction
between written source labels and sounding pitch still deserve human review,
but they do not prevent pitch conversion for the non-transposing parts.

## 9. Ties

### Observed facts

- The file contains 424 `<tie>` elements and 424 corresponding
  `<notations><tied>` elements across the parts.
- Tie elements use `type="start"`, `type="stop"`, and combinations on notes.
- The MusicXML tie elements do not provide a stable tie ID.
- Tie activity exists in the voice and instrumental parts; examples include
  ties within measures and across larger phrase structures.

### Compatibility

The start/stop semantics are compatible with the current `ScoreTie` shape,
but the source cannot be copied directly because `ScoreTie` requires an
explicit `id`. A conversion/curation pass must assign deterministic IDs by
matching contiguous same-pitch events and must handle notes that carry both
start and stop markers. This is especially important in polyphonic parts,
where pitch and voice/staff context are needed to avoid joining unrelated
ties.

## 10. Unsupported or relevant constructs

| Construct | Observed in source | Current v1 status | Preparation implication |
|---|---:|---|---|
| Multiple time signatures | Yes, 4/4 and 2/4 | Unsupported as a sequence; one score-level signature only | Preserve and resolve by curation or defer conversion. |
| Multiple voices/staves | Yes, especially `P2`–`P4` | One monophonic event stream per `ScorePart` | Split into curated lanes or defer instrumental material. |
| Piano/instrumental chords | Yes | Polyphony within one part is outside v1 | Do not flatten into one part silently. |
| Dotted rhythms | Yes | Compatible as exact tick durations | Convert and validate exact durations. |
| Ties without IDs | Yes | Semantics supported, source IDs absent | Assign IDs during curated conversion. |
| Harmony annotations | No | Independent harmony is supported | Obtain/curate harmony separately. |
| Song lyrics | No in voice part | Lyrics are supported on vocal notes | Acquire and align lyrics separately. |
| Tuplets | No | Deferred | No action for this source. |
| Repeats/endings | No | Deferred | No action for this source. |
| Grace notes | No | Deferred | No action for this source. |
| Fermatas | No | Deferred | No action for this source. |
| Tempo changes | Yes, eight tempo directions/sounds | Constant tempo in v1 | Decide whether to retain one curated tempo or defer the changing tempo. |
| Clef changes | Yes, piano and some instrumental material | Initial clef only in v1 | Curate selected parts or defer clef changes. |
| Beams/articulations/layout | Yes | Renderer/presentation concerns, mostly outside domain | Preserve only if a later renderer needs them. |

## 11. Concrete issues requiring human review

1. **Time-signature scope:** the source alternates between `4/4` and `2/4`.
   This is the clearest direct conflict with the current frozen one-signature
   score model.
2. **Part selection:** only `P1` is directly compatible with a monophonic
   voice `ScorePart`. Piano, cello, and strings require explicit lane
   selection or a future polyphonic representation.
3. **Harmony absence:** no authoritative harmony events or slash chords are
   present.
4. **Lyric absence:** the vocal part has no lyrics; the four piano annotations
   are labels and should be discarded for score lyrics.
5. **Tie identity:** tie starts/stops have no IDs and need deterministic
   curation in a future conversion.
6. **Tempo changes:** eight tempo markings/sounds occur, ranging from 63 BPM
   near the beginning to 52 BPM near the end. The v1 model only has one tempo.
7. **Key interpretation:** three flats are present, but the source does not
   explicitly state major/minor mode in the key element.
8. **Measure timing in polyphonic parts:** backups, voices, and staves require
   proper MusicXML voice/staff interpretation; serialized note order is not a
   single monophonic timeline.

## 12. Data-quality assessment

**Assessment: suitable with substantial manual curation; not suitable as-is.**

Reasons it remains a useful reference source:

- It is a versioned `score-partwise` MusicXML file with a clear named vocal
  part and 68 consistently numbered measures.
- The source uses a fixed divisions value, making exact integer-tick timing
  feasible.
- Pitched notes, rests, ties, dotted rhythms, clefs, and instrumental material
  are explicitly represented.
- The voice part is structurally monophonic and is a credible starting point
  for the first curated vocal line.

Reasons it is not ready to become the golden normalized asset:

- It contains mid-score time-signature changes outside the current v1 score
  model.
- The instrumental parts are polyphonic and cannot be loaded as v1
  monophonic parts without curation.
- It has no usable song lyrics, no harmony layer, and no stable tie IDs.
- It contains tempo changes and clef changes beyond the current minimal model.
- Musical correctness, source provenance, and the intended arrangement have
  not been independently verified by this structural audit.

## 13. Recommended next preparation step

Create a human curation note, without modifying `source.musicxml`, that
explicitly chooses the first reference scope:

1. confirm whether `P1` is the authoritative melody to retain;
2. decide how the `4/4`/`2/4` structure will be represented or whether the
   first asset must wait for time-signature support;
3. decide whether any single-line bass or instrumental lanes are worth
   extracting from `P2`–`P4`;
4. obtain a separate lyrics source and align it manually to `P1`;
5. curate independent harmony and semantic chord qualities;
6. define deterministic tie IDs while preserving the original source for
   comparison;
7. decide which tempo and clef information belongs in the first normalized
   asset.

Only after those choices should a conversion step produce normalized JSON.
This audit generated no normalized JSON and did not modify the source or the
web repository.
