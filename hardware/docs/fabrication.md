# Fabrication: JLCPCB, not home etching

**Recommendation: order both boards from JLCPCB as 2-layer, 1.6 mm, 1 oz.
Do not try to etch these single-sided at home.** Keep home etching for the
things it is genuinely good at, listed at the bottom.

This is not a cost judgement — it is that single-sided home etch cannot
physically host these two designs, and that the electrical problems it creates
land exactly on the parts of these boards that are hardest to debug.

## What this recommendation is arguing against

Worth being explicit: Juno is *designed* for single-sided home etch, and not
casually. `CLAUDE.md` fixes the node board at 50 x 45 mm, one copper layer, SMD
on the face that looks at air and through-hole bodies in the four corners only.
The BOM carries eight 0 R jumpers for single-layer crossovers, a sheet of copper
clad and a bottle of ferric chloride. `06_electrical.md` sets toner-transfer
design rules down to the LQFP fanout, and the runbook has "etch board one" on
the critical path. The part choices follow from it too: the driver is a module
on sockets specifically to keep the high-current gate layout off an etched
board.

So this is a recommendation to change a settled decision, and the burden is on
it. The argument is below. The counter-argument - that the design already bends
around the constraint and mostly succeeds - is real, and the turnaround section
takes it seriously.

## Why single-sided does not work for these boards

**The packages rule it out.** Between them these boards carry an ESP32-S3
module on 1.27 mm castellations, MEMS microphones, an LQFP MCU, and 0603
passives. Home etch gives no plated through-holes, so every layer change
becomes a hand-soldered wire link. A board with a 48-pin MCU needs dozens of
crossings; that is dozens of jumper wires, each one a joint that can fail and a
thing to get wrong. It is not a harder version of the same job, it is a
different and much worse one.

**No solder mask is the quiet killer.** Bare etched copper with no mask between
fine-pitch pads bridges readily, and reflowing or drag-soldering an LQFP
without mask to contain the solder is genuinely unpleasant. Mask matters more
than silkscreen here.

**No ground plane causes real failures on this specific design**, not cosmetic
ones. Four places on these two boards depend on a solid return:

- **CAN.** A differential pair with no reference plane on a multi-node
  daisy-chained bus gets reflections and radiates. This is the subsystem whose
  failures look like random dropped frames under load — the worst kind to chase.
- **Two microphones on a shared clock.** A clock fanned out to two mics over a
  plane-less board both picks up noise and radiates it. Shared-clock mic arrays
  are sensitive to exactly this.
- **The ESP32-S3 antenna**, which needs a defined ground pour and keepout to
  hit its rated pattern. Without one, range is whatever it happens to be.
- **Motor current sense into the ADC**, which needs a quiet analog return
  separated from the motor's high-di/dt path.

**The cost argument no longer favours home etch.** JLCPCB is roughly $2 for
five 2-layer boards up to 100 x 100 mm, plus shipping. Laminate, resist, toner
transfer paper, etchant, disposal, and the hours spent debugging under-etched
traces and lifted pads all cost more than that. The saving was real fifteen
years ago; it is not now.

## What you give up by not etching at home

Turnaround, and only turnaround: same afternoon versus about a week. That is a
genuine cost when you are iterating, which is why the split below is worth
keeping rather than abandoning home etching entirely.

## Where home etching still earns its place

- **Fat-trace, few-crossing boards.** A motor-phase distribution board or a
  screw-terminal fan-out has no fine pitch and few crossings. Good candidate.
- **Mechanical fit checks, same day.** Etch — or just print at 1:1 and drill a
  blank — the board outline, mounting holes and connector positions to confirm
  the board fits the actuator before committing to a JLC order. This catches
  the expensive class of mistake without waiting a week.
- **Test fixtures and jigs**, where appearance and EMC are irrelevant.

## What the projects assume

Both generated projects are 2-layer, so if you overrule this you are not just
changing a fab order. The node board would need the 0 R crossovers back, the
ground pour removed, and a placement pass that keeps every crossing solvable —
the console's own budget is "8 planned, expect 12, stop at 15". Regenerating
against single-sided rules is a real change but a contained one; the schematic
does not move.

## If you decide to home-etch anyway

Then the design has to change to suit the process, and that is a real
redesign rather than a re-export:

- Through-hole and SOIC only. No LQFP, no QFN, no castellated modules — the
  ESP32-S3 and the MCU both move to pre-made modules on headers.
- Budget for wire links and place parts to minimise them.
- Widen everything: 0.4 mm minimum track and 0.4 mm clearance, since home etch
  undercuts and the error is not symmetric.
- Expect no mask and no silkscreen; tin the board after etching so it stays
  solderable.

Say the word and the projects get regenerated against those rules instead.

## Board setup as configured

2 layers, 1.6 mm, 1 oz. Bottom layer is a mostly-solid GND pour, top carries
signals. JLCPCB's hard floor is 0.0889 mm track and space with a 0.3 mm
minimum drill; the rules in these projects sit far above that, so the order
stays in the cheapest tier and does not trigger DFM queries.

Netclasses are set up so hand-routing is mostly a matter of picking the right
class and following the ratsnest:

| Netclass | Track | Notes |
|---|---|---|
| Default | 0.25 mm | signals |
| Analog | 0.25 mm | current sense, kept off the motor return |
| CAN | 0.25 mm | routed as a pair, kept over unbroken ground |
| Power | 0.5-1.0 mm | sized per rail from the build console's current figures |
| Motor | 1.0-2.0 mm | phase outputs, sized for peak not average |
