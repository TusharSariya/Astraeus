## Context

Weather rasters and geographic reference information have different jobs. The
raster is evidence and must retain its published pixels. Coastlines, lakes,
roads and labels are orientation aids and must remain legible without appearing
to be meteorological values. A single raster basemap cannot satisfy both jobs
when an opaque weather field covers it.

## Decisions

### Use a three-part map sandwich

The owned style defines muted land and water fills below every weather image.
Weather images are inserted immediately before the first reference layer.
Reference water outlines, coastlines, selected roads, boundaries and labels are
transparent vector layers above the weather. Deck.gl observations and interface
controls remain above the MapLibre canvas.

Reference lines use a casing plus a narrow core. This preserves their shape
over both very light cloud and dark precipitation imagery while keeping the
line visually distinct from the data. Road detail increases with zoom so the
regional view is not cluttered.

### Own the style, not the geographic dataset

The browser uses OpenFreeMap's OpenMapTiles-compatible vector source, glyphs and
sprites, but every layer selection and paint value is defined locally. This
keeps cartographic hierarchy, contrast and the weather insertion point under
application control. The remote source is still an online dependency; offline
packaging is deliberately outside this experiment.

### Theme the desk and map together

Both themes use semantic CSS and map tokens. Land and ocean are deliberately
separable before weather is enabled. The initial theme follows
`prefers-color-scheme`; the explicit two-state control persists in localStorage
and updates the map paints in place. A small inline head script prevents a
wrong-theme flash.

### Never style weather data as decoration

Raster images are not recoloured, blended into a decorative gradient, or given
client-authored scales. Provider legends are displayed unmodified and labelled
as provider legends. Layer-kind swatches remain identity marks only. The map
frame has no decorative weather rings or fake isobars.

### Fail the reference layer independently

A vector source or glyph failure changes a visible and live-region status to
"Reference map unavailable". It does not remove already retrieved weather,
Deck.gl observations, controls, or the textual map alternative. The message
does not describe missing geography as missing weather evidence.

## Accessibility and responsive behavior

- Text and controls target WCAG AA contrast; non-text boundaries target 3:1.
- Theme controls are real pressed buttons, and map/drawer state remains named.
- The layer drawer begins closed, closes with Escape, and becomes a bottom sheet
  on narrow screens so it does not permanently consume the map.
- Motion is limited and disabled under `prefers-reduced-motion`.
- Active legends remain adjacent to the map at desktop widths and scroll rather
  than shrink their provider graphics beyond usefulness.
