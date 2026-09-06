# GFS APCP native interval evidence

Status: non-normative research for issue #208. Read 2026-09-06.

NOAA's GRIB2 parameter table defines APCP as total precipitation in `kg m-2`, while PRATE is the distinct rate in `kg m-2 s-1`. The application can preserve APCP as an accumulated water-equivalent amount; it must not label the value as an instantaneous rate. For liquid-water depth, `1 kg m-2` equals `1 mm`, so changing the label to millimetres is a dimension-preserving unit conversion, not a temporal derivation. [NCEP GRIB2 Table 4.2-0-1](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-1.shtml)

GRIB2 Product Definition Template 4.8 carries the beginning and end of the statistical interval and the processing type. The interval must travel with each returned APCP value; the selected valid time alone is insufficient. [NCEP Product Definition Template 4.8](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_temp4-8.shtml)

The retained actual NOAA GFS 2026-09-06 12Z `.idx` files under `/private/tmp/gfs208-capture/final` contain two APCP surface records at each inspected forecast lead. At f006 they are both `0-6 hour acc fcst`. Starting at f007, one record is a recent block (`6-7`, then `6-8` ... `6-12`), while the second remains run-to-date (`0-7` ... `0-12`). The pattern resets the recent block at six-hour boundaries (`12-13`, `18-19`, `24-25`, `30-31`). Through the retained f037 index, both records remain present and semantically distinct. The record offsets and interval labels are provider-issued evidence; no precipitation payload was fetched for this note.

This creates one unresolved current-client choice. A point card has one `precipitation_accumulation` slot but NOAA supplies both a recent block accumulation and a run-to-date accumulation for the same native valid time. Both can be represented faithfully only if interval start/end and a stable accumulation-series identity are exposed. Selecting one silently, subtracting cumulative records, or converting either to a rate would add behavior not owned by the current contract.

Recommended minimal experimental contract: fetch and validate both exact APCP records for the selected native frame; preserve each native interval and amount independently; expose neither as the single primary point-card value until the owner chooses whether the existing card represents the recent block, run-to-date, or becomes an interval-qualified multi-value control. No interpolation, differencing, carry-forward, or rate derivation.
