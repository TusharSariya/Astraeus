# Camera inventory with terms, positions and orientation metadata

Non-normative research, 2026-09-02. No registry state changed, nothing published
to the store. Evidence-class vocabulary is `CONTEXT.md` at the repository root:
retrieved, reprocessed, derived-here, generated-display, uncalibrated
observation. **Camera geometry** there is "the registered position, bearing,
field of view and horizon landmarks of a camera, which make its frames usable as
an input to cloud and fog derivation." Evidence box is 45.0 to 50.5 N, 58.0 to
46.0 W; this ticket covers the Avalon.

Reuses without repeating: the CCG viewpoint list and the camera computer-vision
guardrails in
[`../newfoundland-operational-data-improvements.md`](../newfoundland-operational-data-improvements.md),
and the NL 511 terms finding in [`running-sources.md`](running-sources.md)
(branch `research/running-sources`) — NL 511 needs a developer key and its site
terms are an "AS IS" liability release with no reuse, attribution or
redistribution clause at all. That probe was **not** repeated here; the NL 511
camera endpoint stays behind the same gate and is listed below for completeness
only.

Probe window 2026-09-02 06:15 to 06:26 Z, 41 upstream calls.

**The headline finding is that no camera on the Avalon publishes its own
geometry.** Not one operator publishes latitude, longitude, bearing, field of
view, focal length or horizon landmarks for any camera in this table. Every
usable camera therefore needs hand registration before a frame can be an input
to cloud or fog derivation, and the positions in this table are approximate
site positions inferred from the operator's own place name, not surveyed camera
positions. The only machine-readable direction metadata found anywhere is
Windy's coarse eight-point compass sector, which is third-party and unverified.

## Inventory

| # | Camera | Operator | Terms and redistribution | Retrieval endpoint | Format | Cadence (measured) | Lat, lon | Bearing / FOV documented | Looks at | Privacy | Live 2026-09-02 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Fort Amherst | Canadian Coast Guard (Camera Ice Monitoring System) | Page states verbatim: "these cameras are intented for operational use for the CCG. The images are offered to the public as a courtesy and are for information only." No licence grant; canada.ca terms and conditions apply and were **not** retrievable at probe time (403 to a non-browser client), so redistribution is unresolved | `https://e-nav.ccg-gcc.gc.ca/nvss-svsn/sequences/FortAmherst.mp4` (page `https://e-navigation.canada.ca/topics/cameras/camera-en?camfile=FortAmherst`) | MP4 image sequence, 31.7 MB | page claims 30 min; measured 06:02:16 → 06:22:17 Z, so **20 min** | ~47.564, -52.684 (approx, inferred) | No | Narrows and harbour entrance, sea horizon beyond | Public waterway; small-craft occupants possible | Yes, HTTP 200, `Last-Modified` advancing |
| 2 | St. John's Base | Canadian Coast Guard | as #1 | `https://e-nav.ccg-gcc.gc.ca/nvss-svsn/sequences/StJohnsBase.mp4` | MP4, 15.9 MB | ~20–30 min (06:02:17 Z at probe) | ~47.563, -52.702 (approx, inferred) | No | CCG wharf and inner harbour | Vessel crews and wharf workers in frame | Yes |
| 3 | Sir Humphrey Gilbert Building | Canadian Coast Guard | as #1 | `https://e-nav.ccg-gcc.gc.ca/nvss-svsn/sequences/SirHumphreyGilbertBuilding.mp4` | MP4, 14.0 MB | ~20–30 min (06:02:17 Z at probe) | ~47.584, -52.683 (approx, inferred) | No | Harbour from the White Hills side | as #2 | Yes |
| 4 | New Gower Street | City of St. John's | `https://www.stjohns.ca/en/city-hall/terms-of-use.aspx`; page not retrievable at probe time, no licence statement found on the camera page. Registry already carries the City as having no open-data portal and no licence statement | `https://apps.stjohns.ca/Camera/images/NewGower/NewGower.jpg` (page `https://apps.stjohns.ca/accessstjohns/WebCameras.aspx`) | JPEG, 257 KB | fresh at 06:22:44 Z | ~47.562, -52.713 (approx) | No | Downtown street, road surface | Pedestrians and plates at street distance | Yes |
| 5 | Middle Pond | City of St. John's (images served from a Nimbus S3 bucket) | as #4 | `https://nimbus-clients-public-stj.s3.amazonaws.com/images/RNLMP1.jpg` | JPEG, 52 KB, `Content-Type: JPG` | 06:15:59 Z; sibling advanced 06:15:41 → 06:25:42, so **~10 min** | Avalon, approx only | No | Road surface | Vehicles and plates | Yes |
| 6 | Shea Heights | City of St. John's | as #4 | `.../images/RNLSH.jpg` | JPEG, 34 KB | ~10 min, measured | ~47.550, -52.700 (approx) | No | Road surface, elevated south-side site | Vehicles and plates | Yes |
| 7 | Thorburn Road | City of St. John's | as #4 | `.../images/RNLTH.jpg` | JPEG, 36 KB | ~10 min | ~47.590, -52.750 (approx) | No | Road surface | Vehicles and plates | Yes |
| 8 | Windsor Lake | City of St. John's | as #4 | `.../images/RNLWL4.jpg` | JPEG, 73 KB | ~10 min | ~47.613, -52.769 (approx) | No | Road, lake water surface | Vehicles and plates | Yes |
| 9 | Kenmount Road | City of St. John's | as #4 | `.../images/RNLKM1.jpg` | JPEG, 55 KB | ~10 min | ~47.556, -52.777 (approx) | No | Road surface | Vehicles and plates | Yes |
| 10 | St. John's Sky | NTV (Newfoundland Broadcasting) | No terms, copyright or privacy page found anywhere on `ntv.ca`; a broadcaster asset, all rights presumed reserved. Redistribution **not** granted | `https://ntv.ca/cams/thumb_st-johns-sky-cam.jpg` | JPEG, 140 KB (full frame despite the `thumb_` prefix) | `Last-Modified` 06:13:04 Z unchanged across probes to 06:26 Z, so **≥13 min**, undocumented | St. John's, approx only | No | Sky dome — the only camera on the Avalon whose stated subject is sky | Low | Yes |
| 11 | Quidi Vidi Lake | NTV | as #10 | `https://ntv.ca/cams/thumb_quidi-vidi-lake-cam.jpg` | JPEG, 133 KB | ≥13 min | ~47.583, -52.694 (approx) | No; Windy third-party sector for a Quidi Vidi Lake cam is **north-west** | Lake and rowing course | Rowers and park users | Yes |
| 12 | Downtown | NTV | as #10 | `https://ntv.ca/cams/thumb_downtown-cam.jpg` | JPEG, 155 KB | ≥13 min | St. John's downtown (approx) | No | Downtown roofs and harbour | Street-level people | Yes |
| 13 | George Street | NTV | as #10 | `https://ntv.ca/cams/thumb_george-street-cam.jpg` | JPEG, 178 KB | ≥13 min | ~47.565, -52.710 (approx) | No; Windy sector **south-west** | Bar street | High: crowd scenes at night | Yes |
| 14 | Admiral's Green | NTV | as #10 | `https://ntv.ca/cams/thumb_admirals-green-cam.jpg` | JPEG, 125 KB | ≥13 min | Pippy Park (approx) | No | Golf course, open ground and sky | Golfers | Yes |
| 15 | Logy Bay Road | NTV | as #10 | `https://ntv.ca/cams/thumb_logy-bay-road-cam.jpg` | JPEG, 220 KB | ≥13 min | ~47.610, -52.690 (approx) | No | Road | Vehicles and plates | Yes |
| 16 | St. Philip's / Bell Island | NTV | as #10 | `https://ntv.ca/cams/thumb_st-philips-bell-island-cam.jpg` | JPEG, 16 KB | ≥13 min | ~47.605, -52.885 (approx) | No | Conception Bay water and Bell Island across it | Low | Yes |
| 17 | Port de Grave | NTV | as #10 | `https://ntv.ca/cams/thumb_port-de-grave-cam.jpg` | JPEG, 138 KB | ≥13 min | ~47.600, -53.200 (approx) | No | Harbour and Conception Bay | Fishing crews | Yes |
| 18 | St. John's harbour from The Rooms | CBC News NL, redistributed by SkylineWebcams and a dozen other aggregators | CBC Terms of Use, all rights reserved; delivered as a YouTube live stream, so frame capture would also breach YouTube's terms. **No reuse** | YouTube live `y7FKz_y86Bo`; no still-image endpoint | H.264 live stream only | continuous | The Rooms, ~47.570, -52.716 (approx) | No; aggregator titles say **east** ("St. John's › East: Saint John's Harbour") | Harbour, the Narrows, and open Atlantic through the gap | Public waterfront | Yes, `isLiveContent: true` |
| 19 | NAV CANADA weather cameras (CYYT and all sites) | NAV CANADA | Site terms; now moot | `https://weathercams.navcanada.ca/` — **NXDOMAIN**, confirmed against Cloudflare DoH (`Status: 3`) while `plan.navcanada.ca` resolves normally. Replacement is the NC-SPACES METCAM workspace (`https://spaces.navcanada.ca`), whose API answers `401 {"error":"User not authenticated"}` and whose bundle exposes only `/api/auth/jwt/refresh`, `/api/otp/…`, `/api/account/…` | n/a | n/a | n/a | n/a | n/a | n/a | **No** |
| 20 | NL 511 cameras | 511 Newfoundland and Labrador | Developer key required; site terms grant no reuse (prior finding, not re-probed) | `https://511nl.ca/api/v2/get/cameras` | JSON metadata plus images | event/provider dependent | provincial | Unknown | Roads | Vehicles and plates | Not probed; gate unchanged |
| 21 | Windy / webcams.travel listings | third-party operators, unnamed | Windy Webcams API v3 requires `x-windy-api-key` (`403 Missing Header`); webcams.travel now redirects to windy.com. Meteoblue mirrors the same set with the bare attribution "Webcams provided by windy.com" and no operator names | `https://api.windy.com/webcams/api/v3/webcams?nearby=…` | JSON plus JPEG | per-camera | listing exposes coordinates and an eight-point sector | see notes | varies | Listing reachable only with a key |

## Notes

### Canadian Coast Guard — the strongest position, the weakest terms

Three of the five active CCG cameras east of Quebec are in St. John's harbour:
Fort Amherst, St. John's Base and Sir Humphrey Gilbert Building. All three
answered `200` with `Last-Modified` advancing during the probe window. They are
the only cameras in this inventory that a federal operator runs, and the only
ones pointed at the harbour entrance where marine fog arrives.

Two problems. First, the delivery is a **30-minute MP4 image sequence, not a
still**: Fort Amherst is 31.7 MB. Fetching all three at the measured 20-minute
cadence is roughly 62 MB per cycle, about 4.4 GB a day, against a storage budget
that allows three hours of history. A frame-extraction step at the edge, keeping
one still per cycle, is the only affordable shape.

Second, the page says the images "are offered to the public as a courtesy and
are for information only" — a courtesy notice, not a licence. The canada.ca
terms and conditions page (`https://www.canada.ca/en/transparency/terms.html`)
returned `403` to every non-browser client tried, so the reproduction clause
could not be read at probe time and must be resolved by hand before any frame is
stored, let alone republished.

### City of St. John's — live, cheap, and legally silent

Six road cameras, all live, all small JPEGs, refreshing about every ten minutes.
Five are served from `nimbus-clients-public-stj.s3.amazonaws.com` with a
non-standard `Content-Type: JPG`. This is the cheapest camera evidence available
on the Avalon by two orders of magnitude — under 100 KB per camera per cycle.

But they are road cameras: the subject is asphalt, they are low and oblique, and
they carry the highest privacy load in the table (vehicles, plates, pedestrians).
The prior guardrail stands — no plate or face recognition, mask private regions,
minimise retention. And the City publishes no licence: the terms-of-use page did
not answer at probe time, and prior research already recorded that the City has
no open-data portal and no licence statement.

### NTV — the only sky camera, and no terms at all

`ntv.ca/cams/thumb_<name>.jpg` returns full-resolution JPEGs for ten cameras, of
which eight are on the Avalon. The `thumb_` prefix is misleading: these are
120–220 KB frames, not thumbnails.

**St. John's Sky is the only camera found anywhere on the Avalon whose stated
subject is the sky dome.** For cloud derivation that makes it the single most
interesting asset in this inventory — and the one with the worst paperwork.
`ntv.ca` publishes no terms of use, no copyright page and no privacy policy that
could be found by crawling the site or the camera page. A broadcaster's imagery
with no published terms is all-rights-reserved by default. Written permission is
the only route, and it should be sought for St. John's Sky specifically rather
than for the set.

`Last-Modified` did not move between 06:13 and 06:26 Z on two cameras, so the
refresh interval is at least thirteen minutes; the page's cache-busting `ts`
parameter suggests a fixed schedule but the operator documents none.

### NAV CANADA — the registry endpoint is dead

Registry record `nav-canada-weather-cameras` points at
`https://weathercams.navcanada.ca/` with `access_state: licence_review`. That
hostname no longer exists. Cloudflare DoH returns `Status: 3` (NXDOMAIN) with
the `navcanada.ca` SOA in the authority section, while `plan.navcanada.ca`
resolves and answers normally, so this is the subdomain being withdrawn rather
than a local resolver fault. The AWWS notice board confirms the move: "Aviation
Weather Cameras are now served on the NC-SPACES platform through the METCAM
workspace."

NC-SPACES is an authenticated Nuxt application. `https://spaces.navcanada.ca/api/notice/all/`
returns `401 {"error":"User not authenticated"}`, and the only API paths in its
JavaScript bundles are account, auth-JWT, OTP, chat, notice and workspace — no
anonymous camera or image route. The public `plan.navcanada.ca/weather/api/alpha/`
service, which does answer anonymously for METAR at CYYT, has no camera alpha
type: `alpha=camera`, `alpha=cameras`, `alpha=webcam` and `alpha=metcam` return
`500` or an empty `alpha.geomNone` error.

**The record should move from `licence_review` to `credential_required` or
`unavailable`, with the dead hostname replaced.** This mirrors the ECCC Datamart
pattern already noted in the charter: a link-only record that quietly stopped
resolving. Recording it is a registry change, out of scope for a research
ticket, and belongs in a follow-up.

### Parks Canada, Memorial University, Marine Institute, Port of St. John's — nothing

No camera exists at any of them. `parks.canada.ca/lhn-nhs/nl/signalhill` and
`parks.canada.ca/lhn-nhs/nl/spear` both answer `200` and contain no occurrence of
"webcam", "web cam", "live cam" or "caméra". Neither does `www.mun.ca`,
`www.mi.mun.ca`, `www.mun.ca/osc/` or `www.sjport.com`. The "Cape Spear
lighthouse webcam" and "Signal Hill webcam" that aggregator and tourism pages
advertise resolve, on inspection, to the CBC stream at The Rooms and to NTV's
Signal Hill signature shot — not to cameras those operators run. Signal Hill
remains what the prior dossier called it: a destination and validation site, not
a station.

### Aggregators expose no operators

SkylineWebcams, WebcamTaxi, Tabi.cam, BalticLiveCam, LiveBeaches, Cruising Earth
and Outdooractive all list "St. John's Harbour" cameras. Every one traced back to
the same CBC News NL YouTube live stream. Aggregator pages are therefore useless
as sources and mildly dangerous as evidence: they present one camera as many.

Windy is the only aggregator with real metadata — it stores coordinates and an
eight-point viewing sector per camera — and it is the only one that will not give
it up without a key. Meteoblue's mirror of the Windy set shows twelve cameras
within about 31 km of Torbay, including `Torbay › East: Torbay Bight`,
`St. John's › East: Saint John's Harbour`, `St. John's › North-west: Quidi Vidi
Lake`, `St. John's › North-west: International Airport, Terminal 4`,
`St. John's › South-west: Harbourside Park`, `St. John's › South-west: George
Street`, `Cowan Heights › North-east` and `St. John's › East: Paddy's Pond Road`.
Those sector labels are the only machine-readable bearings found in this whole
exercise, and they are third-party, eight-point-coarse, and unattributed to the
operators who actually own the cameras. They are a hint for hand registration,
not a substitute for it.

### What hand registration has to supply

Because no operator publishes geometry, every admitted camera needs, recorded by
hand and versioned: surveyed latitude, longitude and height; true bearing of the
optical axis; horizontal and vertical field of view; at least two named horizon
landmarks with known bearings for drift detection; and the sky/sea/land fraction
of the frame. Without the landmarks there is no way to detect the camera being
nudged, which is the failure mode that silently poisons a cloud-fraction series.

## Which cameras can serve cloud and fog derivation

Cloud and fog derivation needs open sky or a sea horizon, and the sunrise and
sunset sectors are where fog banks and clearing edges show first. Ranked by what
the geometry can actually support:

**East, open sea horizon — the sunrise sector, and where Atlantic fog arrives:**

1. **CCG Fort Amherst** is the best-placed camera on the Avalon for fog. It sits
   on the south head of the Narrows looking out through the harbour entrance to
   open water, which is exactly the line of sight the charter's open question
   about "fog-at-sunrise line-of-sight evidence in the eastward ocean sector"
   asks for. Federal operator, verified live, advancing timestamps. Blocked only
   by an unread reproduction clause and a 31.7 MB payload per cycle.
2. **CBC at The Rooms** looks east over the harbour and out through the Narrows —
   the aggregators' own sector label is east. Geometrically it is the second-best
   fog line of sight in the city. Legally it is the worst: all rights reserved,
   delivered only as a YouTube live stream. Not usable without a written grant
   from CBC.
3. **Torbay Bight (Windy `Torbay › East`)** is the only listing found that points
   east at open ocean from outside the harbour, clear of the Narrows' framing. Its
   operator is unknown because Windy will not name operators without a key.
   Worth one follow-up: identify the operator, then approach them directly.

**West, open water — the sunset sector:**

4. **NTV St. Philip's / Bell Island** looks west across Conception Bay at Bell
   Island, giving a genuine water horizon in the sunset direction. Useful for
   clearing-edge timing and for the west-side fog that the harbour cameras
   cannot see.
5. **NTV Port de Grave** gives a second Conception Bay water view further west.

**Sky dome, direction-independent:**

6. **NTV St. John's Sky** is the only sky-dome camera found. It does not serve
   the east/west horizon question, but it is the natural input for total cloud
   fraction and for cirrus, which the astronomy work already flagged as the
   field practitioners most want and no model publishes usably.
7. **NTV Admiral's Green** at Pippy Park has open ground and a large sky
   fraction, and is a reasonable second sky camera for cross-checking.

**Cannot serve cloud or fog derivation:** all six City of St. John's road
cameras, NTV Downtown, George Street and Logy Bay Road, and the CCG St. John's
Base and Sir Humphrey Gilbert Building wharf views. These look at asphalt,
buildings and wharf structure. They can support road-state and lens-health
signals, which is what the prior guardrails scoped them to, but their sky
fraction is too small and too obstructed for a cloud estimate, and they have no
sea horizon at all.

The uncomfortable summary: **the three cameras with the right geometry all have
the wrong paperwork.** Fort Amherst has an unread federal reproduction clause,
The Rooms is all-rights-reserved, and Torbay Bight has an operator nobody will
name without paying Windy. The two cameras with acceptable-in-principle access —
the City's road set — point at the ground. Any admission decision here is a
permissions exercise before it is a technical one, and Fort Amherst is where to
spend the first request.
