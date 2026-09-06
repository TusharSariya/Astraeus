# Bounded CYYT TAF app path

## Why

The registered AWC TAF adapter retrieves provider data during discovery without
a complete-operation reservation, so the worker correctly refuses it. The
existing app therefore cannot show its native CYYT forecast evidence.

## What changes

- Admit one complete, finite CYYT TAF JSON response before payload retrieval.
- Decode it in the existing kernel-limited child and publish one immutable
  point artifact with native report, issue/validity, ordered forecast-group,
  wind/gust, visibility, weather, and cloud-layer evidence.
- Add one read-only `/aviation/taf` view over the immutable artifact and a
  compact Workbench TAF panel. The view returns every native group whose
  interval contains the selected instant, in provider order. It never merges
  groups into a single synthetic forecast. Brief continues to show its current
  model forecast and does not label sparse TAF groups as prevailing conditions.

This is an experimental implementation. It does not promote source status or
change the 64 GiB, retention-window, cold-tier, or daily-receive policies.
