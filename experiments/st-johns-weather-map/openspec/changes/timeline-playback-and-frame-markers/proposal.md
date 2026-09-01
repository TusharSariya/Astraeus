# Timeline playback transport and published-frame markers

## Why

The timeline dock moves only by hand: drag the scrubber, press a quick jump,
or arrow along the frame axis. Watching a system cross the Avalon means
dragging at a steady speed, which nobody can do. The owner asked for the
usual video-player transport in the corner of the timeline - play/pause,
faster, slower, reverse - with a defined speed ladder, and for pointers on
the timeline showing where the **real published frames** are as against the
interpolated instants between them, colour-coded per layer and clickable to
jump to that frame.

The markers are not decoration. The dock already offers display
interpolation and discloses it in words; nothing on the timeline showed the
reader *where* the retrieved frames actually sit, so "this pixel is a
composite" and "this pixel is a retrieved frame" looked identical on the
control that chooses between them. The rail is that axis, drawn from
`layer.times` exactly as `/layers` returned it.

Playback moves nothing but the selected instant. Every layer still resolves
that instant through `resolveLayerFrame` under the existing rules, so a
played frame is exactly the frame a scrub to the same instant would have
shown, with the same disclosures.

## What changes

- **Transport** in the corner of the dock's scrubber block: slower,
  play/pause, faster, reverse, and a speed readout. The ladder is
  1, 2, 4, 8, 16, 32 weather-minutes per wall-clock second (owner's
  numbers), starting at 1 and doubling per press, clamped and disabled at
  both ends. Reverse is a separate direction flag, so the speed survives it.
- **Looping** at the window edges (owner decision): passing `now+24h`
  continues from `now-3h`. The wrap is modular on the window length, so a
  stalled tab cannot carry the clock out of the window.
- **Pause on touch**: any manual time action - slider, quick jump, keyboard
  step, marker click, story card, a map jump-to-frame - stops playback, so a
  hand and the clock never fight over the same instant.
- **Markers**: one rail under the slider, one tick per published instant of
  the active visible layers, on the slider's own scale. A layer's colour is
  its position in the retrieved layer list into a fixed palette, so toggling
  one layer never recolours another. An instant several layers share is one
  tick split between their colours - one target, not overlapping ones. Each
  tick is a button that jumps to that exact instant and names the layers and
  the NT clock time to assistive tech. A key beside the rail names the
  layers, and a layer that published no time axis is named there instead of
  vanishing.
- Playback deliberately does **not** snap to the frame axis and does **not**
  touch the interpolation setting: it is a clock, and interpolation stays an
  explicit opt-in the reader made. With interpolation off, playback steps
  frame to frame; with it on, the disclosed composite animates.

## Impact

- Classification: Experiment, Spec-Impact: none (experiment-local specs
  under `openspec/`).
- Affected specs: web-evidence-interface (ADDED x2).
- Affected code: `web/src/playback.ts` (new), `web/src/api.ts`,
  `web/src/TimelineDock.tsx`, `web/src/App.tsx`, `web/src/styles.css`, and
  their tests.
- `openspec/config.yaml` is untouched: this displays retrieved frame times
  and moves the existing clock. Nothing new is derived or drawn, and the
  interpolation carve-out is unchanged.
- No API, worker, ingest or registry change; no new request is issued. The
  markers read the `times` already carried by `/layers`.
