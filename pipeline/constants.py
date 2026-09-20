"""Shared constants for the offline pipeline scripts.

PPQ (ticks per quarter note) must be identical across every script that
produces or consumes tick values, and must match the web app's
SCORE_PPQ (src/lib/score.ts). It used to be copied by hand into each
script; two of those copies drifted into a different (wrong) convention,
which is what caused the your-song tick-unit bug. Import it from here
instead of redefining it.
"""

PPQ = 960
