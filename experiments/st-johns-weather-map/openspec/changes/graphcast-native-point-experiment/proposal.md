# Published GraphCast native point experiment

Classification: experiment. Status: draft; no production admission is authorized.
Tracking: #267, #96. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

Prove selected native `t2` and `msl` decoding from NOAA/CIRA AIWP GraphCast
Operational `GRAP_v100_GFS` or distinct `GRAP_v100_IFS` published objects using
ETag-pinned capped HTTP ranges and h5py's file-like interface. Preserve native
version, initializer, exact run/time, coordinate, units, missingness and receipts.
No latest-run discovery, API registration, scheduler, inference, archive or
operational claim is added. h5py remains an explicit isolated proof dependency.
A selected-time finite-cache production contract still needs owner acceptance.
GenCast remains separate: Google deprecated its Earth Engine/BigQuery datasets
on July 29, 2026; no continuing published GenCast endpoint is established here.
