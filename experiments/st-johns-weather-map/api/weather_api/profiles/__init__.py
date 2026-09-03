"""Activity profile evaluation seams that hold no solar model of their own.

Two things live here, and both are deliberately starved of ephemeris access:

* :mod:`weather_api.profiles.windows` resolves a profile's window rule from
  Sun geometry that arrives as samples. It never calls Skyfield, never opens
  the kernel and never computes an altitude. The registered DE442 entry of
  ``ingest.derive.registry`` is the only solar model in this deployment, so
  the window code asks that registry whether the entry may produce a value
  and otherwise reports the window unresolved rather than guessing one.
* :mod:`weather_api.profiles.overrides` records the reader threshold
  overrides that produced a score, and records explicitly when none was in
  force, so a score never carries an omitted record a reader could mistake
  for "the defaults were used".

Nothing here admits a source, promotes a registry status or enables a
derivation.
"""
