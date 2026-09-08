> Historical recovery: restored from `eb0ae0fc3f31` during the September 8 unused-work audit. This retains the original September 3 research; version, licensing, performance and product claims have not been revalidated. Current accepted contracts and implemented behavior take precedence over its recommendations.

# Prior art: how forecasting workbenches organise layers, time and verdicts

Resolves wayfinder research ticket #45 (child of map #38). Last reviewed:
2026-09-03.

Vocabulary is `CONTEXT.md`'s: **Focus** (the one shared point and instant every
view reads), **View** (Map, Series, Sky, Activity, Sources), **Layer stack**
(the ordered set of fields drawn on the Map at one focus), **Verdict** (the
decision layer's derived-here score for an activity profile). The governing
rule the comparison is judged against: nothing shown that was not retrieved,
absence shown as null, blocked or aged-out, and provenance always reachable.

## Method and caveats

Primary sources are the products' own help pages, user manuals and staff
answers on their official forums. Several vendor pages refuse automated
fetches (Astrospheric returns 403 on every page; `charts.ecmwf.int` sits
behind an Anubis challenge; Windy's article pages render empty without
JavaScript), so for those the evidence is the App Store listing, ECMWF's
Confluence and news pages, and moderator answers on `community.windy.com`.
Where a product's behaviour was only visible in a screenshot the text does not
describe, this note says so rather than guessing. No screenshots were captured:
none of the products publishes a licence that clearly permits redistribution of
interface captures, and text with URLs is enough for design work.
`docs/research/product-landscape.md` and
`docs/research/wayfinder/astronomy-tool-needs.md` already cover what these
products *compute*; this note covers only how they *organise* it.

Ambient (named in the ticket) has no first-party documentation of a
multi-source workbench that could be found; it is omitted rather than
described from memory.

## Product by product

### Windy (windy.com)

- **Layer picking and stacking.** One colour-shaded overlay at a time, chosen
  from the right-hand menu. Staff answer to a request to leave several layers
  on: "This option is not possible"; multiple shaded overlays cannot be stacked
  "due to visual contrast issues". What can be combined: point symbols
  ("Reported temperature or Reported wind") over Satellite or Radar, four
  isoline choices over any overlay, and "Radar + Satellite" on the browser
  version. Users asked for a "4-panel view" as the alternative; unimplemented.
  Source: <https://community.windy.com/topic/24498/multiple-layers>.
- **Time.** One timeline bar at the foot of the map with a play button; drag
  to a time or press play (third-party guides describe it the same way, e.g.
  <https://support.followmychallenge.com/docs/basics/windy-layer/>). Altitude is
  a separate slider in the point picker, by pressure level
  (<https://community.windy.com/topic/12172/reading-wind-and-gusts-at-different-altitudes>).
- **Source comparison.** Off-map, at a point: the location forecast's "Source"
  section has "Compare forecasts", which lays "all of the available Models"
  out "in a vertical orientation" for the chosen period, one row per model
  (ECMWF, GFS, ICON, Meteoblue, AROME, NAM where available), now with a 1-hour
  option and meteogram ("Clouds, rain") and wave comparison.
  Sources: <https://community.windy.com/topic/9427/how-to-use-the-compare-feature>,
  <https://community.windy.com/topic/26304/understanding-the-compare-forecast-feature-in-windy-com>.
- **Runs and staleness.** The location forecast shows "Updated Xh ago" for the
  selected model. Per-model update time lives only "at the right end" of the
  Compare table ("in UTC only"), in the mobile model menu, or behind "the small
  circled i at bottom right corner" of the browser. Users repeatedly report
  losing it: "Please bring back updated time of each weather forecast model";
  "Why is Windy's weather update time missing? It matters!". One user notes the
  run time shown does not necessarily reflect "the model's recency within
  Windy", i.e. producer run time and Windy's ingest time are conflated.
  Sources: <https://community.windy.com/topic/41949/why-is-windy-s-weather-update-time-missing-it-matters>,
  <https://community.windy.com/topic/37898/is-there-no-way-to-see-when-every-model-was-updated-on-desktop-web-version>,
  <https://community.windy.com/topic/32543/web-latest-model-update-and-time-to-next-update>,
  <https://community.windy.com/topic/41762/please-bring-back-updated-time-of-each-weather-forecast-model>.
- **Verdicts.** None as such; activity is expressed by overlay choice (sailing,
  kite, aviation menus) not by a score.
- **What it hides.** The "Meteoblue AI" row in Compare is a machine-learned
  merge of models whose inputs and weights are not disclosed anywhere in the
  product; a moderator confirms it "was already a machine learning (ML)-based
  model" before the "AI" label was added. It sits in the same table as the
  producer runs with no glyph separating it. In CONTEXT.md terms this is an
  intermediary-derived value presented as a peer of retrieved ones.
  Source: <https://community.windy.com/topic/45410/meteoblue-ai-a-smart-merge-of-all-models-does-not-give-the-best-results>.

### Meteoblue (meteoblue.com), including Astronomy Seeing

- **Layer picking.** Maps show one variable at a time with a model selector;
  the maps help page was not reachable (404), so the map side is not described
  further here.
- **Source comparison.** The **MultiModel** meteogram is the strongest
  off-map comparison surveyed: "Every model uses its own colour, that is used
  in all diagrams. The legend on the left has a list with the model names,
  their spatial resolution (in km) and the corresponding colours." Its stated
  purpose is honest: "the goal of the MultiModel is not to make local
  predictions for the selected place, but to show the possible divergence of
  the evolutions of the weather." Temperature and wind panels carry "the
  dashed line indicates the average of all models"; precipitation "bars get
  darker when more models predict precipitation". "The number of models
  depends on the region: some models cover only certain areas (domains)".
  Users may select up to five models to build their own MultiModel.
  Sources: <https://content.meteoblue.com/en/private-customers/website-help/forecast/multimodel>,
  <https://www.meteoblue.com/en/blog/article/show/39935_Make+your+own+MultiModel!>.
- **Runs and staleness.** "The domain and the last update time of the model
  forecast are indicated on the main page under the rainSPOT (above the
  register 'More / show hourly details')" (MultiModel help). One line, one
  place, for the primary model only.
- **Astronomy Seeing view.** A single time-by-row grid, hourly, free for 3
  days (7 with point+). Rows: cloud cover in three altitude bands "0-4 km,
  4-8 km, and 8-15 km above sea level" with the warning that "A partial
  coverage in two layers can result in the total obstruction of the sky
  visibility, due to cloud overlap"; Seeing Index 1 and 2 ("two different
  models ... independent of the cloud cover", 1 poor to 5 excellent; "Seeing 2
  gives more weight to the effect of density fluctuations"); arcsecond
  estimates; jet stream (">35 m/s ... as well as very low speeds <5 m/s"
  are bad); "Bad Layers" with "a temperature gradient of more than
  0.5K/100m", top and bottom heights shown; then planet azimuth, altitude, RA
  and Dec per hour. Reading rule: "look for dark blue colours in the cloud
  cover and green values in the Seeing Indices and Jet Stream."
  Source: <https://content.meteoblue.com/en/private-customers/website-help/outdoor-and-sports/astronomy-seeing>.
- **What it hides.** The seeing page names no model, no run and no update
  time; the two seeing indices are described as "two different models" without
  citation. Good pattern in the row design, weak provenance.

### ECMWF OpenCharts and ecCharts

- **Layer picking and stacking (ecCharts).** A layer list: "add layers to the
  existing map - use *add layers* at the top right", checkboxes toggle
  visibility, "change the layer order by dragging the layers in the list",
  waste-basket to delete, an edit icon per layer for style and for processing
  parameters (accumulation interval, probability threshold). "nearly 300
  layers representing surface and upper-air parameters from ensemble (ENS),
  high-resolution (HRES), extended-range (ENS Extended) and wave forecasts."
  Sources: <https://confluence.ecmwf.int/display/DAC/ecCharts>,
  <https://www.ecmwf.int/en/newsletter/166/news/update-latest-options-eccharts>.
- **Time.** Two explicit axes: "Base time (BT) and validity time (VT) exist
  for each gridded dataset, so also apply to each layer." The **data
  availability table** has "validity time on the x-axis and base time on the
  y-axis"; "The red box indicates the base time (BT) and validity time (VT) of
  the currently selected chart", green boxes are available and clicking one
  changes both at once. The time navigator steps and animates, and "the time
  resolution of different *layers* can be different". OpenCharts URLs encode
  the same pair explicitly, e.g.
  `?base_time=202602230000&valid_time=202602230000&projection=...`.
  Source: <https://confluence.ecmwf.int/display/DAC/ecCharts>;
  <https://charts.ecmwf.int/products/opencharts_vertical-profile-meteogram?base_time=202602230000&lat=48.1374&lon=11.5755&station_name=M%C3%BCnchen&valid_time=202602230000>.
- **Source comparison.** Within one producer only. **ChartSet** lets users
  "select the parameters they would like to explore ... set them to show the
  area of interest, and then compare them side-by-side", and "change time
  steps or areas in one click for the entire set of charts" (a shared focus
  across small multiples).
  Source: <https://www.ecmwf.int/en/about/media-centre/news/2021/ecmwfs-free-use-opencharts-catalogue-extended-and-new-feature-added>.
- **Runs and staleness.** The run is a first-class coordinate (base time) in
  every chart, URL and table, never an afterthought label.
- **Verdicts.** None; probabilities and "forecast confidence" products, not
  activity scores.
- **What it hides.** Nothing about run or validity; but only ECMWF products,
  so no cross-producer comparison and no observation overlay.

### NOAA AWIPS II / CAVE D2D (Unidata manual and NOAA OCLO fundamentals)

- **Layer picking and stacking.** Loaded products form the **Resource Stack**
  (legend list) at the bottom right: "A left click on any resource in the
  stack will hide the resource and turn the label gray"; right-click-hold
  gives image properties, colormaps, colour, width, density and lets users
  "move resources up and down in the stack". Every legend line carries "the
  product model, run time, and valid time". Whole stacks are saved as
  **Displays** ("save loaded resources and current view configurations") and
  as **Procedures** (partial, named bundles of resources).
  Sources: <http://unidata.github.io/awips2/cave/d2d-perspective/>,
  <https://vlab.noaa.gov/web/oclo/awipsfundamentals?page=product-overlays>,
  <http://unidata.github.io/awips2/cave/bundles-and-procedures/>.
- **Time.** Frame-based: the Frames menu sets how many time steps are loaded
  (default 12, up to 64), toolbar buttons step first/back/forward/last and
  Loop; Loop Properties set speed and dwell "between zero and 2.5 seconds"
  for first and last frames. **Time Match Basis**: "The first product loaded
  into a display, by default, determines the Time Match Basis", marked "with
  an asterisk in the legend" and reassignable by right-click; "It is important
  to consider the frequency of the products when choosing which product you
  want to drive the updating". Time Options offers a tolerance from "None"
  (exact match) to "Infinite" ("the closest match in each frame, regardless of
  how far off it is").
  Sources: <https://vlab.noaa.gov/web/oclo/awipsfundamentals?page=d2d-toolbar>,
  <http://unidata.github.io/awips2/cave/d2d-perspective/>.
- **Runs.** **Load modes** make the run an explicit choice: "Valid time seq"
  (latest, backfilling empty frames), "Latest", "Previous run", "dProg/dt"
  ("Selects forecasts from different model runs that all have the same valid
  times"), "Prognosis loop", "Analysis loop", "Forecast match" (overlay only
  where forecast times match the base product), "Forced" (latest in all
  frames, no matching).
- **Source comparison.** On-map overlay of any products, plus a four-panel
  layout; run-to-run comparison is dProg/dt.
- **Verdicts.** None; a forecaster tool.
- **What it hides.** Backfilling: "Valid time seq" and "Latest" silently fill
  empty frames with older data; "Infinite" matching draws a frame however far
  off its time is. These are exactly the substitutions the experiment must
  surface as aged-out rather than perform silently.

### Astrospheric (astrospheric.com; App Store listing and prior repo notes)

- **Layout.** An "84 hour, hour-by-hour forecast" grid; "The top three rows
  in the forecast show the hourly sky details, with darker blue indicating
  better conditions" (cloud, transparency, seeing), then ground rows (wind,
  temperature, humidity, dew point). Map layers: "smoke, cloud, transparency,
  seeing, temperature, dew point, wind", GOES imagery, light pollution.
- **Sources and comparison.** RDPS is primary; GFS for aerosol optical depth,
  long-range cloud and jet stream; smoke from RAP; seeing and transparency
  from Rahill's CMC model. Pro's **ensemble cloud** view "lets you quickly
  compare the major forecast models with hourly updates", "color coded so you
  know which model is forecasting clouds" (RDPS, GFS, NBM, NAM). This is the
  only astronomy product surveyed that shows source disagreement per hour.
- **Runs.** Free tier "updated every 6 hours"; no per-row run stamp is
  documented.
- **Verdicts.** Colour intensity per cell plus Pro "weather alerts when
  conditions meeting your requirements are met" (user-set thresholds).
  Sources: <https://apps.apple.com/us/app/astrospheric/id1166046863>,
  <https://www.astrospheric.com/dynamiccontent/astrospheric.html> (403 to
  automated fetch; cited in `docs/research/product-landscape.md`).
- **What it hides.** The free grid blends four models into one cloud row
  without saying which model each hour came from; only Pro un-blends it.

### Clear Outside (First Light Optics)

- **Layout.** One hourly grid, 7 days, rows: total/low/medium/high cloud as
  "% Sky Obscured", visibility, fog %, precipitation type/probability/amount,
  wind, temperature, feels-like, dew point, humidity, pressure, ozone, ISS
  passes, moon phase and rise/set, sun times, civil/nautical/astronomical
  darkness. A summary row rates each hour "Good", "OK" or "Bad" with a colour.
- **Runs and staleness.** A single footer line: "Generated: 03/09/26 13:44:49.
  Forecast: 03/09/26 to 09/09/26. Timezone: UTC-2.50", and "Powered by
  Meteosource Weather API" with a residual Forecast.io attribution.
- **Verdicts.** The Good/OK/Bad row is the verdict; the How To Use page does
  not state the thresholds ("designed to be intuitive and easy to use").
  Sources: <https://clearoutside.com/forecast/47.56/-52.71>,
  <https://clearoutside.com/page/how_to_use/>.
- **What it hides.** The model behind Meteosource, the run time (only the
  page generation time is shown), the verdict rule, and it presents "Est. Sky
  Quality ... Bortle" (a light-pollution statement about the site) beside
  weather rows as if it were a forecast quantity.

### Ventusky

- **Layers and models.** One layer at a time; model selector "in the lower
  left corner": Automatic ("switches data between ICON and GFS ... highest
  resolution possible"), ICON (72 h), GFS, GEM, ECMWF, regional models
  (ICON-EU, HRRR). An "Altitude" pop-up for temperature and wind only.
- **Time.** Timeline at the foot with play and arrow keys; "The timeline
  below the map uses the time that you have set in your device. By contrast,
  the card of the particular location uses the local time of this location."
- **Comparison.** Manual: "it is recommended to monitor and compare the
  calculations of all of the models". Update cadence is documented per model
  ("ICON ... every 6 hours, while ICON-EU ... every 3 hours", ECMWF "four
  times a day", radar every 10 minutes).
  Sources: <https://www.ventusky.com/help>,
  <https://my.ventusky.com/guide/help/user-guide-7/>,
  <https://www.ventusky.com/about>.
- **What it hides.** "Automatic" switches models under the reader, so the
  drawn field can change source at 72 h with no on-map marker; the run time
  itself is not shown next to the layer.

### Runner-oriented products

- **Strava.** Weather is a post-hoc annotation of a finished activity for
  subscribers: "The weather during your activity using data from Weather
  Kit." No forecast, no verdict, no source beyond the vendor name.
  Source: <https://support.strava.com/en-us/articles/15401943-viewing-activities>.
- **Garmin Connect.** Weather is "fetched from a nearby weather station based
  on the GPS location of the watch" and attached to the activity; again
  retrospective. Source: <https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/257354/weather-data>.
- **The Weather Channel GoRun index.** "a scale from 1-10 ... the higher the
  number the better", from temperature, humidity, precipitation and wind,
  shown "hour by hour"; the app lets users "see the science behind the
  numbers" explaining each factor. Source (secondary, reviewer describing the
  app): <https://wrinkledrunner.com/what-is-the-weather-channel-run-score/>.
- **RunWeather.** A 0-100 "Run Score" from "dew point bands, WBGT heat-strain
  tiers, wind and precipitation gates" with a "50/35/15
  performance-safety-experience blend" and "safety cutoffs"; picks "the best
  time to run today". The methodology page publishes the shape of the rule
  but not the weather source per hour.
  Sources: <https://runweather.app/how-the-run-score-works>,
  <https://runweather.app/>.
- **Run Window.** "Today's best running hour, decided for you in 3 seconds",
  "Backup windows", learns from logged runs ("Your conditions, not a generic
  'good weather' label"); the site names no data source and no per-hour
  reasoning. Source: <https://www.runwindow.com/>.
- **What they hide.** All of them collapse inputs into one number; only
  GoRun and RunWeather publish the factors. None shows which source or run
  produced the hour being scored, none distinguishes forecast from
  observation, and Run Window's personalised model is unexplained by design.

## Cross-product summary

| Concern | Strongest pattern seen | Product |
| --- | --- | --- |
| Layer stack | Ordered legend list; click hides, drag reorders, each line names model, run and valid time | AWIPS CAVE; ecCharts layer list |
| Time | Base time and valid time as two explicit coordinates; availability matrix to pick both | ECMWF ecCharts/OpenCharts |
| Cadence mismatch in a stack | A declared Time Match Basis layer (asterisked) plus a tolerance setting | AWIPS CAVE |
| Run choice | Load modes: latest, previous run, dProg/dt at fixed valid time | AWIPS CAVE |
| Cross-source at a point | One colour per model, model list with resolution in the legend, average as a dashed line, agreement as bar darkness | Meteoblue MultiModel |
| Cross-source, hourly, colour-coded by model | Pro ensemble cloud row | Astrospheric |
| Shared focus across small multiples | ChartSet: one click changes time or area for the whole set | ECMWF OpenCharts |
| Sky-specific rows | Cloud by altitude band, two seeing indices, jet stream, bad layers, planet altitudes on one hourly grid | Meteoblue Astronomy Seeing |
| Verdict with published rule | 0-100 score with named bands, gates and cutoffs | RunWeather; GoRun's "science behind the numbers" |

## Patterns worth adopting

1. **Two time coordinates, always visible** (ECMWF). Every layer in the stack
   and every value in Series and Activity carries run (base) time and valid
   time; the Focus is a valid time, and the run is a reader-selectable
   coordinate, not a footnote. The availability matrix (base time on one axis,
   valid time on the other) is a good Sources-view element for showing exactly
   which frames exist per source.
2. **Legend as the layer stack** (AWIPS CAVE, ecCharts). An ordered list where
   each line names source, run and valid time, click toggles visibility, drag
   reorders, and one entry is marked as the time-match basis. This maps
   directly onto the permanent evidence-class glyph plus source tag beside
   every value that map #38 requires.
3. **Explicit run modes instead of silent "latest"** (AWIPS load modes).
   "Latest", "previous run" and "same valid time across runs" (dProg/dt) are
   the three the Map and Series need; the run-stale boundary across a stack is
   then a rendered consequence of each layer's run, not a hidden rule.
4. **One colour per source, everywhere** (Meteoblue MultiModel, Astrospheric
   ensemble). Series and the off-map point comparison use a fixed source colour
   carried across every panel, with the source list showing resolution and
   domain, and the reason a source is absent ("covers only certain areas")
   stated in the list.
5. **Agreement drawn as intensity, not as a merged number** (Meteoblue
   precipitation bars). Where several retrieved sources agree, darken; do not
   average into a value no producer issued. If an average is drawn at all it
   is a dashed derived-here line with its inputs listed.
6. **Shared focus across small multiples** (OpenCharts ChartSet). Changing the
   focus instant or area once moves every panel, which is what the Map's side
   by side and Series need.
7. **The hourly sky grid** (Meteoblue seeing, Clear Outside, Astrospheric):
   cloud by altitude band with the overlap caveat, seeing, jet stream, bad
   layers, darkness bands and target altitudes on one time axis. The Sky view
   can adopt the row set; each row must add the source tag and class glyph
   those products omit.
8. **Verdict with the rule beside it** (RunWeather, GoRun). A score plus the
   named gates that produced it, per hour, with the "science behind the
   numbers" one click away. The Activity view's verdict should show its
   inputs, thresholds and which input was limiting, as derived-here evidence.
9. **Time zone stated on the axis** (Ventusky's device-versus-location
   distinction, Clear Outside's "Timezone: UTC-2.50" footer). St. John's is
   UTC-2:30; the axis must say so and the run stamps must say UTC.

## Patterns to avoid

1. **Update time hidden three clicks away** (Windy: only in the Compare
   table's right edge, the mobile menu, or an "i" button; users lost it and
   asked for it back). Run time and ingest time are separate facts; show both
   on the layer line.
2. **A blended or ML row seated among producer runs with no marker** (Windy's
   "Meteoblue AI"; Astrospheric's free blended cloud row; Meteoblue's
   uncited "two different models" for seeing). Any intermediary-derived value
   gets its glyph, is never the display primary and never a derivation input.
3. **Silent backfill and loose time matching** (AWIPS "Valid time seq",
   "Latest" backfill, "Infinite" tolerance). Frames older than the tolerance
   are drawn as aged-out or null, never as the nearest available.
4. **Automatic source switching under the reader** (Ventusky "Automatic":
   ICON to GFS at 72 h with no on-map marker). Tier changes and source
   handovers are drawn on the scrubber and in the layer line.
5. **A verdict with an unpublished rule** (Clear Outside Good/OK/Bad, Run
   Window's learned windows). No score without its method, inputs and
   limiting factor reachable.
6. **Only one shaded layer at a time** (Windy, Ventusky). The Map's multi-layer
   stack is the point of this experiment; the compositing findings in
   `raster-compositing-compare.md` (#44) already cover how.
7. **A page-generation time standing in for a run time** (Clear Outside
   "Generated: ..."). The stamp beside a value is the producer's run or
   observation time, with retrieval time reachable separately.
8. **Site light-pollution statistics presented beside forecast rows as if
   they were forecast** (Clear Outside Bortle/SQM). Site properties belong to
   the Site record, not the time grid.
9. **Retrospective-only weather** (Strava, Garmin). Not wrong, but not a
   workbench; the Activity view is forward-looking and window-finding.
