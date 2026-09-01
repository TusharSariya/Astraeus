Owned: `web/src/playback.ts` (new), `web/src/playback.test.ts` (new),
`web/src/api.ts`, `web/src/api.test.ts`, `web/src/TimelineDock.tsx`,
`web/src/App.tsx`, `web/src/App.test.tsx`, `web/src/styles.css`.
Not touched: API, worker, ingest, registry, `openspec/config.yaml`,
`web/src/MapPanel.tsx`.

## 1. The clock

- [x] 1.1 `playback.ts`: the 1/2/4/8/16/32 ladder clamped at both ends,
      `advanceClock` integrating elapsed wall-clock seconds with a modular
      wrap at the window edges, and a speed readout. Pinned: the wrap in
      both directions, a stall longer than the window staying inside it, a
      zero/negative/NaN elapsed holding still.
      Verify: `cd web && npm test -- --run src/playback.test.ts`

## 2. The markers

- [x] 2.1 `api.ts`: `LAYER_TICK_COLORS`, `layerTickColor` (position in the
      retrieved layer list, stable under toggling) and `frameMarkers`
      grouping the active visible layers' published instants inside the
      window, reporting layers with no axis instead of dropping them.
      Verify: `cd web && npm test -- --run src/api.test.ts`

## 3. The dock

- [x] 3.1 `TimelineDock.tsx`: transport cluster (slower, play/pause,
      faster, reverse, readout) and the marker rail aligned to the slider
      thumb, one button per instant with a multi-colour fill where layers
      share it, plus the colour key and the no-axis / nothing-published
      notes. Presentational only.
- [x] 3.2 `App.tsx`: playback state, the rAF effect advancing the selected
      instant, pause on every manual time action (`selectMinutes`,
      `onScrubKeyDown` including Home/End, `jumpToTime`), and the
      `frameMarkers` memo.
      Verify: `cd web && npm test -- --run src/App.test.tsx`
- [x] 3.3 `styles.css`: transport, rail, marker and key styling in both
      themes; the shared `.visually-hidden` clip.

## 4. Validation and live verification

- [x] 4.1 Full web suite and build.
      Verify: `cd web && npm test -- --run && npm run build`
- [x] 4.2 Change validates.
      Verify: `openspec validate --all`
- [ ] 4.3 Browser, in a VISIBLE tab (a hidden tab gets no animation frames,
      which freezes both playback and MapLibre): play at 1 and at 32 min/s,
      reverse, confirm the loop continues from the opposite edge, confirm a
      drag stops playback, and confirm a marker click lands on that frame
      with no fallback note. Watch for churn while playing with
      interpolation on.
      Verify: `docker compose up -d --build web` then the checks above
      Status 2026-08-31: web container rebuilt and driven live in Chrome
      against the deployed build with GOES-East day visible/night IR and
      ECCC-HRDPS total cloud (rendered grid) both active. The automation tab
      is hidden, so the browser issues NO animation frames at all; the real
      playback effect was exercised by substituting requestAnimationFrame in
      the page and pumping it with known timestamps. Measured: 3 s at
      1 min/s advanced the valid instant +3 min and 60 s advanced it
      +1 h 3 min; five presses of faster reached 32 min/s with the control
      disabled; 60 s at 32 min/s from +11 h 43 min carried the clock past
      +24h and it continued from the past side at +16 h 43 min, i.e. exactly
      one modular wrap of the 27-hour window; reverse at 2 min/s ran the
      clock back 20 min in 10 s and the readout read "◀ 2 min/s"; an
      ArrowLeft on the scrubber stopped playback (play control back to
      aria-pressed=false) and further frames moved nothing. The rail drew 36
      ticks in two colours with both layers in the key; clicking the tick
      labelled 07:30 a.m. NT selected exactly 07:30 a.m. NT with no
      fallback note. Both themes checked. What remains for the owner's own
      eyes, in a visible tab: whether the animation LOOKS right at each
      speed and whether playing with interpolation on churns.
