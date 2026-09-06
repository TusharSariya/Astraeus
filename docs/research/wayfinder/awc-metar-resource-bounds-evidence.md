# AWC CYYT METAR resource-bound evidence

Non-normative evidence for issue #159, captured 2026-09-06. The retained AWC response completed at `06:39:02.227207Z`; its seven rows occupy 3,486 bytes and have SHA-256 `e0d07144b9424c6963e0ab03d7c79e9afe5ffc77447148aae34c96cf7eda773e`. Raw bytes, full headers, measurement inputs, Linux logs, artifact, and replay proof remain outside Git under `/private/tmp/awc159-capture`.

The supported Linux target refused the complete decoder at 384 MiB virtual address space. A 512 MiB trial succeeded in isolation but failed in the complete replay environment during required thread initialization. Repeated 640 MiB runs completed, so the enforced source-specific `RLIMIT_AS` is 640 MiB. This is a virtual-address-space ceiling, not a total-memory guarantee.

A 64-row all-field measurement produced a 36,923-byte ZIP occupying 40,960 bytes on the measured 4096-byte filesystem. The enforced output ceiling is 65,536 bytes, already block aligned; the allocation reservation adds one 4096-byte workspace/directory allowance. The child writes one file and atomically renames the inode, avoiding output-copy overlap.

The retained live response replay produced a 35,913-byte artifact occupying 36,864 physical bytes. All seven timestamps and all 29 stored variables per timestamp matched through real PostgreSQL/MinIO publication and `LiveStore.sample_point`. The accepted point HTTP route exposed 27 AWC fields at each of all seven timestamps, and every directly exposed value matched. A labeled synthetic HRDPS artifact was used only to open the route's existing model-plus-observations boundary and was excluded from every AWC comparison.

This change preserves the existing AWC field, unit, time, quality, and delivery contracts. It adds experimental allocation enforcement and makes no normative transition.
