# Your Song Curated MusicXML Plan

## Scope and source facts

The immutable source is:

`input/your-song/source.musicxml`

It is MusicXML 4.0 `score-partwise` with four 68-measure parts:

- `P1` Voice: one voice, 459 pitched notes and 88 rests, no backups or
  note-level chord markers;
- `P2` Piano: multiple staves/voices and polyphonic chord material;
- `P3` Violoncellos: multiple voices and simultaneous-note material;
- `P4` Strings: multiple voices and simultaneous-note material.

The source uses fixed `divisions=8`, has an initial `4/4` signature, and
contains explicit `2/4` measures at 10, 19, 26, 29, 40, 49, 56, 59, 62, and
65, each followed by a return to `4/4`. It has no `<harmony>` elements and no
song lyrics in the voice part.

## Explicit reference-score decision

### Retained

Only `P1` is retained as `P1` Voice.

This is supported by evidence rather than track order:

- the declared part name and instrument metadata identify it as Voice;
- it has exactly one MusicXML voice;
- it has no `<backup>` elements;
- it has no `<chord>` note markers;
- its notes and rests form one monophonic sequence;
- it has an initial treble clef and no later clef changes.

This is sufficient for the first reference workflow to establish a verified
vocal line and exact note/rest timing without inventing a line from the
accompaniment.

### Excluded

`P2` Piano, `P3` Violoncellos, and `P4` Strings are excluded from the curated
reference file.

All three contain multiple voices and/or simultaneous notes. Their note
content is arrangement material rather than an unambiguous single bass or
instrumental line. Extracting one line would require musical judgment about
voice priority, chord reduction, and arrangement intent that cannot be
justified by XML structure alone. No monophonic extraction is performed.

The excluded information remains recoverable in the immutable source and may
be curated later as explicitly named monophonic parts if a musical decision
supports that work.

## Curation decisions

### File and part structure

The working file is:

`input/your-song-curated.musicxml`

It remains `score-partwise`, MusicXML 4.0, and contains only the original
`P1` part and its 68 measures. No new musical notes, rests, parts, harmony,
or lyrics were created.

### Time signatures

The alternating `4/4` and `2/4` measures are preserved exactly. They are not
flattened into a single time signature because doing so would silently change
bar boundaries and could change the interpretation of absolute musical time.

This means the curated file is cleaner and narrower than the source but is
still not directly compatible with the current v1 `Score` object, which has
one score-level time signature. A later conversion step must either extend
the target representation, or obtain an explicit human-approved re-barring
decision. This unresolved issue is intentionally preserved rather than
invented here.

The retained P1 measure durations remain:

- 4/4 measures: 32 source divisions;
- 2/4 measures: 16 source divisions.

With `PPQ=960`, the fixed source resolution still maps exactly at 120 score
ticks per source division.

### Tempo

All `<direction>` elements were removed from the curated working file. The
source has eight changing tempo directions/sounds, but the current v1 model
supports one constant tempo and the source does not justify selecting one
single BPM.

Removing tempo directions does not alter note or rest durations, divisions,
measure boundaries, or pitch content. The expressive tempo curve is
intentionally deferred and must be restored or represented separately if a
later workflow requires it.

### Clefs and pitch

P1's initial treble clef (`G`, line 2) is retained. P1 has no later clef
changes, so no clef simplification was needed for the retained part.

Pitch elements, octave values, and accidental information are retained
unchanged. No sounding pitch is altered. The source has no instrument
transpose element, so later conversion to concert MIDI-style pitch remains
deterministic.

### Ties

All P1 tie start/stop elements are retained, and note durations are
unchanged. The source contains 126 P1 tie elements, representing 63
start/stop pairs.

Because MusicXML tie elements do not provide the stable IDs required by the
internal score model, deterministic IDs `tie-001` through `tie-063` were
added to the corresponding `<notations><tied>` elements using their
MusicXML `number` attribute. Each pair receives the same ID. The original
`<tie type="start|stop">` semantics remain intact.

The IDs are a curation aid for the later conversion step, not a claim that
the source itself contained IDs.

### Rhythms and notation cleanup

P1's exact duration values and dotted-note markers are retained. No
quantization or duration rewriting was performed. P1 has no tuplets, grace
notes, or multiple voices.

The following layout/presentation material was removed from the working copy:

- page/layout defaults and print metadata;
- tempo directions;
- note stems, beams, staff numbers, and dynamics;
- non-tie notation details such as staccato articulations.

These removals do not change P1 pitch, rest, duration, measure, or tie
content. They keep the working source focused on the symbolic material
needed for later curation.

## Intentionally deferred

- **Harmony:** the source has no `<harmony>` elements. Harmony must be
  supplied or curated from a separate source in a later step. No harmony
  events or chord qualities were invented.
- **Lyrics:** the source has no actual lyrics in P1. Lyrics must be supplied
  from a separate, rights-appropriate source and aligned to the verified voice
  melody in a later step. No lyrics were added.
- **Time-signature resolution:** the exact 4/4 and 2/4 structure is preserved,
  but the v1 one-time-signature `Score` target cannot represent it directly.
- **Bass/instrumental parts:** no P2–P4 lane was selected without a justified
  musical extraction decision.
- **Tempo:** the changing tempo curve is omitted from this symbolic working
  file; no constant BPM was invented.
- **Final normalized JSON:** this file is still MusicXML preparation material,
  not a normalized score asset.

## Human verification required

Before JSON conversion, a curator must verify:

1. that P1 is the intended reference melody for the chosen arrangement;
2. ~~whether the 2/4 measures should be supported in the target schema or
   explicitly re-barred~~ — **resolved 2026-09-20: re-barred to uniform 4/4**,
   see "Time-signature resolution" below;
3. that the deterministic tie pairing remains correct at every tie boundary
   (note: the pipeline now assigns its own tie ids in chain order rather than
   reusing tie-001..tie-063 from this file — see
   `pipeline/transcribe_vocals.py`'s `from_curated()` — but the underlying
   start/stop pairing and pitch/timing continuity are unchanged);
4. the intended key mode for the three-flat key signature;
5. the separate harmony source and lyric source;
6. whether any later bass or instrumental extraction is musically valuable.

## Time-signature resolution (2026-09-20)

Decision: re-bar to a uniform 4/4 for the v1 `Score` object, rather than
extending the schema to support per-measure time signatures. The pipeline
already did this by construction (`musicxml_to_json.py`'s `build_measures()`
lays a continuous 4/4 grid over the absolute tick timeline, ignoring the
source's own bar lines); this section makes that an explicit, verified
decision instead of an accidental side effect.

Consequence: the source's ten 2/4 bars (measures 10, 19, 26, 29, 40, 49, 56,
59, 62, 65) don't each cost a full published measure. Two 2/4 bars in a row
cancel out to a net one-measure deficit, so half of the ten insertions
(19, 29, 49, 59, 65) land two beats *into* a published 4/4 measure rather
than on one of its bar lines — the published bar grid is real 4/4 throughout
but is offset from the source's phrase structure at those five points. No
note actually straddles one of these off-phase bar lines (checked
computationally against `working/your-song/vocal-events.json`: zero note
start/end pairs cross a measure boundary), so nothing renders split or
requires an inserted tie — the visual effect is at most an odd-looking
rhythm relative to where a musician transcribing from a printed 2/4 bar
would expect the barline, not a broken one.

Approximate timestamps for a quick check against the recording, in case
the phrasing there suggests a different re-bar choice would read better:

| source measure (2/4) | ~seconds | published measure | offset into it |
|---:|---:|---:|---:|
| 10 | 30.0s | 10 | 0 beats (on the bar line) |
| 19 | 58.3s | 18 | 2 beats in |
| 26 | 80.0s | 25 | 0 beats (on the bar line) |
| 29 | 88.3s | 27 | 2 beats in |
| 40 | 123.3s | 38 | 0 beats (on the bar line) |
| 49 | 151.7s | 46 | 2 beats in |
| 56 | 173.3s | 53 | 0 beats (on the bar line) |
| 59 | 181.7s | 55 | 2 beats in |
| 62 | 190.0s | 58 | 0 beats (on the bar line) |
| 65 | 198.3s | 60 | 2 beats in |

## Result

`curated.musicxml` is a faithful, narrower working source for the
monophonic voice line. It is suitable for the next curation/conversion
decision, but it is not claimed to be a v1-normalized score yet because the
source's genuine mid-score time-signature changes remain unresolved.
