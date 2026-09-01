# Design: timeline transport and published-frame markers

## The clock

Playback is a pure function over the selected instant, kept in
`web/src/playback.ts` so the rules are testable without a browser clock:

```
advanceClock({ ms, elapsedSeconds, speed, direction, windowStartMs, windowEndMs })
  stepped = ms + direction * elapsedSeconds * speed * 60_000
  offset  = ((stepped - windowStartMs) mod span + span) mod span
  return windowStartMs + offset
```

Two properties matter:

- **Elapsed, not accumulated.** The React effect integrates the gap between
  successive `requestAnimationFrame` timestamps. A backgrounded tab receives
  no frames at all, so it resumes where it left off instead of jumping by
  however long it was hidden. (This is also why the browser check must be
  run in a visible tab: a hidden one gets no rAF, and both playback and
  MapLibre freeze.)
- **Modular wrap, not a clamp-and-stop.** Whatever the frame gap - a stall,
  a slow paint, a debugger pause - the result lands inside the window. A
  clamp would have parked the clock silently on the edge; a raw add could
  have carried it out of the window entirely.

The speed ladder is a fixed tuple, and `fasterSpeed`/`slowerSpeed` clamp at
its ends rather than wrapping, so a press at 32 min/s is a no-op the
disabled button already showed.

## Why playback does not snap and does not force interpolation

The scrubber snaps to the union frame axis when interpolation is off, so a
scrub always lands on a retrieved instant. Playback deliberately does not:
snapping a continuous clock would make it stutter between frames at every
speed, and at 32 min/s it would skip frames outright. Instead the clock runs
continuously and each layer resolves it as usual - which, with interpolation
off, means each retrieved frame simply holds until the next one is nearer.
That is a frame animation with no invention in it.

Nor does pressing play enable interpolation. Interpolation is the
owner-approved display carve-out and an explicit opt-in; turning it on
because someone pressed play would apply a derivation the reader never
asked for. Play animates whatever the reader already chose.

## Marker colours and shared instants

`layerTickColor` indexes the layer's position in the retrieved `/layers`
list into a fixed eight-colour palette. Two alternatives were rejected:

- *Index among the active layers* - toggling one layer off recolours the
  others, so the tick a reader was following changes colour underneath them.
- *Hash of the layer id* - stable, but collisions are invisible and land two
  layers on the same colour with no way to notice.

The palette avoids the orange the slider thumb owns, so the selection is
never mistaken for a frame marker.

Layers publish on different cadences that frequently coincide (hourly HRDPS,
RDPS and GFS all land on the hour). Two ticks at the same position would put
one on top of the other, and the covered one would be unclickable. So
markers are grouped by instant: one tick, one button, one jump target, its
fill a hard-stop gradient of the colours of every layer that published that
instant, and its label naming them all.

## Alignment with the slider

A range input's thumb travels between its own inset edges, so a tick placed
at a flat percentage drifts from the thumb by up to half a thumb width at
the ends. Ticks are placed at
`calc(fraction * 100% + (0.5 - fraction) * 18px)`, the same 18px thumb the
stylesheet draws, so a tick and the thumb coincide at the same instant.

## Fail-closed

- A layer that published no readable time axis contributes no ticks and is
  named in the key ("No published frame axis: ..."). It is never left
  silently absent, which would read as "this layer has no frames right now".
- An unparseable timestamp is skipped rather than placed at an invalid
  position, and does not count as an absent axis.
- Frames outside the window carry no tick; the rail spans exactly the
  window the scrubber spans.
- With nothing active or nothing published, the rail says so in words
  rather than rendering an empty strip that reads as "no frames exist".
