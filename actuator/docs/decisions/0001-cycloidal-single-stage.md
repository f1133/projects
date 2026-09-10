# 1. Single-stage cycloidal, 24:1, inside Ø48

Date: 2026-09-10
Status: accepted

## Context

Each of the three CAN joint nodes needs a reduction between a small BLDC and
the arm joint. The board overhangs a Ø48 gearbox, which fixes the envelope
before anything else is chosen. Wiring runs through the joint, so the middle
has to stay open. Phase current is capped at 2.5 A by the DRV8313, so the
available input torque is small and the reduction has to be large.

## Decision

A single-stage cycloidal drive: 25 ring pins, 24 lobes, 24:1, two discs at
180°, output taken through six pins in oversized holes.

## Why not the alternatives

**Planetary.** A single planetary stage tops out near 10:1, so hitting 24:1
means two stages and roughly double the axial length in an envelope already
short on room. Tooth loads also concentrate on three or four planets, where a
cycloidal spreads them over about half of 25 pins.

**Harmonic drive.** The right answer for backlash and ratio, and the wrong one
here: the flexspline is not something to make on a printer or a small lathe,
and bought units in this size cost more than the whole arm.

**Belt or spur reduction.** Offsets the output, which does not suit a joint, and
needs more radial room than Ø48 leaves.

## Consequences

- 24:1 in one stage, 20 mm of disc stack, output counter-rotating.
- Load spreads over ~12 pins at once, so the drive tolerates shock well.
- The input eccentric bearing carries about twice what the naive estimate
  suggests and becomes the life-limiting part.
- Contact stress is concentrated in a small patch and is what decides the disc
  material — see the design log.
- Backlash comes from pin and hole fits rather than tooth geometry, and is
  tuned with `profile_offset_mm` rather than by re-cutting anything.
