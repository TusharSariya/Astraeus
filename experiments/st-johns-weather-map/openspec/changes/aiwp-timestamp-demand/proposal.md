# NOAA/CIRA AIWP selected-time demand proposal

## Why

Issues #267 and #268 require GraphCast and Pangu-Weather delivery without running models. Recent NOAA/CIRA public output files exist for both GFS and IFS initializers. Whole-run files are 2.8–5.7 GB; measured HDF5 chunk metadata supports bounded native-field reads instead.

## What changes

Propose four distinct AIWP identities, initially native two-metre temperature and mean-sea-level pressure at one selected valid time and nearest native point. Preserve full wind/profile and GraphCast precipitation scope as residual work. Reuse existing HTTP receipt/resource and demand-cache seams; no new general framework.

## Authority and owner decision

This is a requirement-change proposal, not implementation authority. The current source-contract matrix marks AIWP owner-source-contract-required. Only @TusharSariya may accept this source contract, the proposed 8 MiB/128-request/600-second policy, discovery limits and native selection rules. No accepted requirement is replaced, registry entry activated, API changed or operational status promoted. Implementation tasks remain blocked until acceptance; this PR must remain draft meanwhile.

Parents: #70, #38; existing acquisition distinction #96. Native metadata evidence: [GraphCast checkpoint](https://github.com/TusharSariya/Astraeus/issues/267#issuecomment-5565248294), [Pangu checkpoint](https://github.com/TusharSariya/Astraeus/issues/268#issuecomment-5565248400). Metadata success does not establish forecast-value correctness or operational suitability.
