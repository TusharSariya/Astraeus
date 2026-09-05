# GOES-19 ABI and GLM live receipt

Captured 2026-09-05 at 20:30 UTC from the anonymous public
`noaa-goes19.s3.amazonaws.com` HTTPS endpoint. The operation was capped at
512 MiB and retrieved 15 current objects totalling 237,222,989 bytes (about 226 MiB);
each adapter also enforces a 64 MiB per-object ceiling. No payload or rebuilt
artifact is committed. URLs have no request parameters beyond their immutable
object key; discovery used `list-type=2`, the product/hour `prefix`, and
`max-keys=1000`.

| Product | Bytes | SHA-256 | URL |
|---|---:|---|---|
| ABI-L2-CCLF | 2346040 | `6d40f9353bd2da8bbb58e3625abf49cdfff38359f7f81f8ce26b5be483462673` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-CCLF/2026/248/20/OR_ABI-L2-CCLF-M6_G19_s20262482000207_e20262482009515_c20262482018094.nc |
| ABI-L2-ACTPF | 3796872 | `de2da2390d2c509f063dfc4f7edfcd111dcd67e7c87cc7be492f818992545998` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-ACTPF/2026/248/20/OR_ABI-L2-ACTPF-M6_G19_s20262482020207_e20262482029515_c20262482030486.nc |
| ABI-L2-ACHTF | 28466343 | `6688b0d2dfaa1ad8045c7d29b6bbca9a92e3465d49dec3acdf8cff5263a52af9` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-ACHTF/2026/248/20/OR_ABI-L2-ACHTF-M6_G19_s20262482010207_e20262482019515_c20262482022351.nc |
| ABI-L2-CODF | 6652900 | `970abd4fb439761483efc8b4168d185a5b70965875455d83b4086ca731c3fab1` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-CODF/2026/248/20/OR_ABI-L2-CODF-M6_G19_s20262482010207_e20262482019515_c20262482024104.nc |
| ABI-L2-COD2KMF | 24235509 | `713e2f28a2ce1edded913d7490dbc37d0a260ae7a6eddc4d303ef927e661d4f3` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-COD2KMF/2026/248/20/OR_ABI-L2-COD2KMF-M6_G19_s20262482010207_e20262482019515_c20262482024099.nc |
| ABI-L2-CPSF | 25999086 | `291db7991d0adb9cb087118aef54699c9ef122b56af8e9962fbc340a44a8c4ce` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-CPSF/2026/248/20/OR_ABI-L2-CPSF-M6_G19_s20262482010207_e20262482019515_c20262482024101.nc |
| ABI-L2-TPWF | 1185477 | `da0e6577a3ad166c8f129a578e31106394112b4fa9745d1c723ae1291e28d78f` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-TPWF/2026/248/20/OR_ABI-L2-TPWF-M6_G19_s20262482010207_e20262482019515_c20262482020528.nc |
| ABI-L2-LVMPF | 54424204 | `9b87f00b61670678f985d097b4f0c5415cdd9b3db2e470480701680f4a7faccc` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-LVMPF/2026/248/20/OR_ABI-L2-LVMPF-M6_G19_s20262482010207_e20262482019515_c20262482020536.nc |
| ABI-L2-LVTPF | 55506795 | `84a70031a706cb3799c9fef3b3b0b8b9472e9ad1e15d9040d51e1f12bc151822` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-LVTPF/2026/248/20/OR_ABI-L2-LVTPF-M6_G19_s20262482010207_e20262482019515_c20262482020532.nc |
| ABI-L2-DSIF | 4112056 | `84f0e2c30f6e6ab54ebeca122c5c71e5d0cb47468aee4364ae320f3d354cbb5d` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-DSIF/2026/248/20/OR_ABI-L2-DSIF-M6_G19_s20262482010207_e20262482019515_c20262482020523.nc |
| ABI-L2-SSTF | 26484149 | `c416165fd95f5d28fa14b904836764e99f80a7ae5e9323a33ec81dc22ac59210` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-SSTF/2026/248/19/OR_ABI-L2-SSTF-M6_G19_s20262481900207_e20262481959515_c20262482002505.nc |
| ABI-L2-RRQPEF | 2082498 | `dfab8d52d1295b73a0915b3483d4c94fc220b6cbaa42a8b8aab09d3dca9e322a` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-RRQPEF/2026/248/20/OR_ABI-L2-RRQPEF-M6_G19_s20262482020207_e20262482029515_c20262482029565.nc |
| ABI-L2-DMWF | 1088444 | `a2f5c5317a44b43b7e0480406311d2b4a8ce1fb1ff839de8faa2283b1eb2581e` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-DMWF/2026/248/20/OR_ABI-L2-DMWF-M6C14_G19_s20262482000207_e20262482009515_c20262482024344.nc |
| ABI-L2-DMWVF | 227923 | `7e4a0c166963730ac7bd4d53cdf2d7eab4e831898a8602eccd8ac88dc61045c7` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-DMWVF/2026/248/19/OR_ABI-L2-DMWVF-M6C08_G19_s20262481900207_e20262481909515_c20262481940234.nc |
| GLM-L2-LCFA | 614693 | `ed23c27f84e5165e26f63495e0eecc716ee7baf4fcfa1ee1d6a751f26086a8e4` | https://noaa-goes19.s3.amazonaws.com/GLM-L2-LCFA/2026/248/20/OR_GLM-L2-LCFA_G19_s20262482030200_e20262482030400_c20262482030420.nc |

## Artifact and reader readback

The real adapter produced content-addressed Zarr revisions and the production
`LiveStore._sample_dataset` reader returned every mapped readable field with
its source revision, valid time, native sampled coordinate and
`curvilinear_nearest_cell` method. CCLF returned TCF, CF1-CF5 and CL; ACTPF
Phase; ACHTF TEMP; TPWF TPW; LVMPF/LVTPF their 101-level profiles; DSIF all
five indices; SSTF SST; and RRQPEF RRQPE. This is a production-reader proof
below the HTTP route; the automated API suite separately exercises the
`/point` and `/profile` HTTP contracts. The live proof used a finite
producer-good cell per field rather than substituting St. John's when that
cell was absent.

| Product | Artifact revision (SHA-256) | Reader fields |
|---|---|---:|
| CCLF | `8fb8ea8d2838ccb6e78006ba952cf448fee4c5667e9bbd51fc0298b7f442feaa` | 7 |
| ACTPF | `1ae8325739ae7028927bc2207be0fb2b5fa5f502635285e03657ede0472141bb` | 1 |
| ACHTF | `ec03490628a48d3d18f0155e34d36fdb6ac559468150291f917665ae0a816504` | 1 |
| TPWF | `937e9177daaaaa1dfbde60d59bf04a2e2857088e8e9aa5e9e7ba5082e48aa767` | 1 |
| LVMPF | `e3c4b435b2003ee2e169f33511717743f780fb845f07bc0a497f59c2e22ef035` | 1 per requested producer pressure |
| LVTPF | `c78995b5a4af30f0c6f12ccd53582f99f08e49a79ac9806d3b2043b17fb8796f` | 1 per requested producer pressure |
| DSIF | `e62c5a36414b1fc5a8f9982a813a2262704f6338a7410b3049b86b2151da79b8` | 5 |
| SSTF | `3da5f72fac84369626880cf1d5b8b61db4d0d3239ae448e6dbe4ab4034bbe8ef` | 1 |
| RRQPEF | `05c61f6fe4aa27bff6e3d492be432a4ac99d38f15bda42ec0b9ff8d50cca58b3` | 1 |

CODF, COD2KMF and CPSF produced immutable artifacts with revisions
`f375389c4b25114b5eff6b065ceab65db95a48c12f7471d4407757dab728c61d`,
`ed96d74a57f9953f318f83e168ae2f1077e3403b495f8769b6f88bb6df909b9f`, and
`092e592fa7df583370ed48498ab5d5f107143ec012f6283ca017ddf6f18084dd`.
Their native DQF is a bit field: values 1 and 2 select the day or night
algorithm with the degraded-quality bit clear. No such cell occurred inside
the evidence box in this scan, so `complete=false`, `qc_passed=false`, and
the reader returned a null field. This is an explicit missing disposition.

DMWF produced 161 in-box vectors from the captured C14 file. The captured
DMWVF file produced an empty collection. Neither single-band capture proves a
complete DMW scan, so the adapter requires its complete expected band set
before setting `complete=true`. The captured GLM file contained 1,341 flashes,
19,078 groups and 39,597 events globally and zero at all three levels in the
box; its declared field of view contained the box, so the empty collection is
an observed empty for that 20-second file. It does not prove a complete
ten-minute interval; the adapter requires all expected files. The DMWVF and
GLM empty artifacts both hash to
`fcd19a92362e5ace443cea187479eaf1b646e4a307c533d6190f24c74edfea4d`;
the DMWF artifact hashes to
`87463896441e2bb59ecb0a89810cfc57417a3b2d4021df95161077f04750363d`.

## Completion capture

Captured 2026-09-05 from the same anonymous HTTPS endpoint. Discovery again
used `list-type=2`, product/hour `prefix` and `max-keys=1000`. The completion
operation was capped at 4 GiB in aggregate; adapter ceilings remained 64 MiB
per gridded file, 4 MiB per DMWF file, 2 MiB per DMWVF file and 2 MiB per GLM
file. Temporary source and artifact bytes were removed after verification.

The native COD/CPS DQF is a CF bit field, not an enumerated whole-value flag.
The adapter verified its `flag_masks`, `flag_values` and `flag_meanings`, then
required exactly one day/night branch and a clear degraded-quality bit. The
14:50 UTC daylight scan yielded 98 readable CODF cells and 108 readable
COD2KMF cells in the evidence box:

| Product | Bytes | Source SHA-256 | Artifact revision | URL |
|---|---:|---|---|---|
| ABI-L2-CODF | 6825571 | `44017a740d28af9e3685203f04b856ebdd8b1d677f882480f8df8b5ac1d56d5c` | `b284e8ffcd3fa76bbf4403c2298b74f7d60611998a867840eabcc9c3f4f70847` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-CODF/2026/248/14/OR_ABI-L2-CODF-M6_G19_s20262481450209_e20262481459517_c20262481503508.nc |
| ABI-L2-COD2KMF | 24926948 | `ee2584c28838e2006142ecee6a008940d21cdb32d9f34e9b66a90ae9cd2527ea` | `11afafe0cd36508e55878e2d963051092c907f320e35c6659f61038ffcc7a169` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-COD2KMF/2026/248/14/OR_ABI-L2-COD2KMF-M6_G19_s20262481450209_e20262481459517_c20262481503503.nc |
| ABI-L2-CPSF | 26837207 | `e57584882158dccf4154f15810bf4fb3dacb7973afc546eb67cc99e97a69467a` | `4474bc86e7af261e4a94770704113376a91eb73d66f15e322eacea70af10e67f` | https://noaa-goes19.s3.amazonaws.com/ABI-L2-CPSF/2026/248/14/OR_ABI-L2-CPSF-M6_G19_s20262481450209_e20262481459517_c20262481503505.nc |

CPSF had 108 in-box cells whose algorithm and quality bits passed, but its CPS
value was fill at every one. Fourteen additional daylight scans at 10:50 to
18:50 UTC across September 3-5 produced the same result. Those 15 files totalled
384722543 bytes. Every immutable key, byte count and source SHA is retained in
`goes-abi-glm-completion-receipt.json`.
This is an evidence-backed `retrieved-no-usable-native-quality-cell`
disposition. No degraded CPS value is served as a substitute.

One complete 14:00 UTC scan was retrieved for both DMW products. DMWF contained
all published C02/C07/C08/C09/C10/C14 files and 422 in-box, producer-good
vectors. DMWVF contained its published C08 file and one in-box, producer-good
vector. Three consecutive day/hour listings confirmed that DMWVF publishes
C08, not the previously assumed C08/C10 set. Their artifact revisions are
`f69266269348542224611017b6f2ea8cd6c5a6c45929de27e8ee208efcfaab19`
and `18c4cad3da59e5bfb6a4e4928c42affdd22ee6fd466db1e379f10e9dd1ae2e2b`.

The complete GLM interval covers 2026-09-05 14:50:00 through 15:00:00 UTC:
all thirty 20-second files were retrieved and decoded. They contained 8,534
flashes, 171,201 groups and 334,443 events globally, and zero at all three
levels in the evidence box. The empty GeoJSON artifact revision is
`fcd19a92362e5ace443cea187479eaf1b646e4a307c533d6190f24c74edfea4d`.
The seven DMW and thirty GLM source files totalled 14561263 bytes. Their exact
URL, byte count and SHA are retained in the completion receipt.

Actual FastAPI `TestClient` requests against the production routes and the
captured artifacts compared 12 `/point` values and all their units and valid
times byte-for-byte/equivalently after the declared ACTPF flag decoding. CODF
and COD2KMF were among those comparisons. Their artifact revisions were fixed
on the only artifacts supplied to the route. Every comparison is retained in
the completion receipt.

`/layers/noaa-goes-east-abi_dmwf/features` returned all 422 stored features and
`/layers/noaa-goes-east-abi_dmwvf/features` returned the one stored feature;
the first complete feature from each response matched its source artifact.
`/layers/noaa-goes-glm-glm_lcfa/features` returned zero features for the
observed-empty interval, matching the artifact. The compact committed receipt
is 36172 bytes with SHA-256
`7a2f543458e15298cf968262c35eb1ea04fd1515a88a1b1411d9db2a0ae274e5`.
The current HTTP provenance schema does not expose an artifact revision, so
the revision comparison remains anchored by the single supplied artifact and
the core sampler's revision result; this experiment does not invent a new API
field. GLM remains catalogued and unregistered, and every response remains
`operational: false`.
