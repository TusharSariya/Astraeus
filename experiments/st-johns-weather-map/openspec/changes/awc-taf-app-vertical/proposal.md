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
- Serve the artifact through the existing refresh, store, HTTP, Brief and
  Workbench paths without a snapshot or fragment framework dependency.

This is an experimental implementation. It does not promote source status or
change the 64 GiB, retention-window, cold-tier, or daily-receive policies.
