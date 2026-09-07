# NOAA/CIRA AIWP published model outputs, September 7

**Public AURO files do exist for September 7, alongside the already verified
FourCastNet v2-small feed.** This corrects the evidence gap in the
[inference handoff](inference-candidate-handoff.md): the
[official registry](https://registry.opendata.aws/aiwp/) and
[bucket README](https://noaa-oar-mlwp-data.s3.amazonaws.com/README.txt) omit AURO,
but actual bucket listings contain it. The publisher is NOAA/CIRA; these are
externally produced outputs, not a Microsoft hosted inference endpoint or
locally generated Earth2Studio evidence.

At 2026-09-07T23:57:29–44Z, three anonymous ListObjectsV2 requests returned
3,135 bytes total. Each requested at most 1,000 keys, enforced a 256 KiB
response ceiling and 20-second timeout, and refused redirects. All three
responses were untruncated. No NetCDF, model weights or inference was fetched
or executed. Raw XML, digest-bearing JSON receipts and the bounded script are
outside Git at `/private/tmp/astraeus-aiwp-prefix-proof/`.

## Observed prefixes and exact current objects

The complete [top-level listing](https://noaa-oar-mlwp-data.s3.amazonaws.com/?list-type=2&max-keys=1000&prefix=&delimiter=%2F)
contains these native model prefixes:

| Candidate | Exact published prefixes | What this check establishes |
| --- | --- | --- |
| Aurora candidate | `AURO_v100_GFS/`, `AURO_v100_IFS/` | Current files below; `v100` is the publisher version token, not proof of an exact Microsoft checkpoint or Aurora 1.5. |
| FourCastNet | `FOUR_v100_GFS/`, `FOUR_v200_GFS/`, `FOUR_v200_IFS/` | Prefixes present; earlier [FCNv2 receipt](noaa-aiwp-discovery-20260907.receipt.json) establishes September 7 12Z GFS output, 4,526,908,784 bytes. |
| GraphCast | `GRAP_v100_GFS/`, `GRAP_v100_IFS/` | Prefixes present; newest object identity/size not inspected in this bounded pass. |
| Pangu | `PANG_v100_GFS/`, `PANG_v100_IFS/` | Prefixes present; newest object identity/size not inspected in this bounded pass. |
| Aurora 1.5, FCN3, FuXi, GenCast | No separately named top-level prefix observed | No established feed for these exact models/versions in this bucket. This does not prove absence under another name, nested product or another publisher. |

The remaining top-level prefixes are `Derived/`, `colab_resources/` and
`parquet/`; their contents were not inspected.

The two further reads were the exact
[GFS date prefix](https://noaa-oar-mlwp-data.s3.amazonaws.com/?list-type=2&max-keys=1000&prefix=AURO_v100_GFS%2F2026%2F0907%2F)
and [IFS date prefix](https://noaa-oar-mlwp-data.s3.amazonaws.com/?list-type=2&max-keys=1000&prefix=AURO_v100_IFS%2F2026%2F0907%2F):

| Exact object key | Bytes | Last modified UTC |
| --- | ---: | --- |
| `AURO_v100_GFS/2026/0907/AURO_v100_GFS_2026090712_f000_f240_06.nc` | 4,576,425,283 | September 7 16:52:51 |
| `AURO_v100_IFS/2026/0907/AURO_v100_IFS_2026090700_f000_f240_06.nc` | 2,760,658,154 | September 7 08:33:11 |
| `AURO_v100_IFS/2026/0907/AURO_v100_IFS_2026090712_f000_f240_06.nc` | 2,760,536,169 | September 7 20:30:43 |

Latest observed initialization is 12Z for each initializer. The names encode
forecast hours 000–240 at six-hour steps under the documented filename
convention; internal coordinates, completeness, grid, fields, units, QC and
checkpoint identity remain unverified. The GFS date prefix contained only its
12Z object. No historical cadence or availability guarantee follows.

## Delivery conclusion and limits

An anonymous published-output route is available to investigate for AURO and
FourCastNet v2-small without deploying inference. It is not yet an Astraeus
point API: settle the external-source identity and an explicitly bounded native
NetCDF metadata/subset strategy before acquisition of these multi-GB objects.
Do not label `AURO_v100` as Aurora 1.5 or `FOUR_v200` as FCN3. No evidence here
establishes a generic current-output feed for every Earth-2 model.

Verification: three bounded successful HTTP listings, untruncated XML parsing,
retained response digests, 0 model-payload bytes; `specctl validate` and
`git diff --check`. Spec-Impact: none; non-normative research only, no behavior,
capability, source admission, credentials or normative status changes.
