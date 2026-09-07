# Earth-2 and Microsoft Aurora: source execution handoff

Reviewed 2026-09-07 at source-worktree head 3227be3. Non-normative research;
no implementation, deployment, credentials, inference, or model payload reads.
This bounded pass applies the repository research skill as the already-delegated
worker; the current task explicitly prohibits further agents.

## Existing repository seam and decision

The existing proposal is
[optional-north-atlantic-models](../../../openspec/changes/optional-north-atlantic-models/proposal.md),
with [generated-evidence constraints](../../../openspec/changes/optional-north-atlantic-models/specs/optional-forecast-centres/spec.md).
[Earlier Earth-2 research](../../../../../docs/research/nvidia-earth2-cpu-feasibility.md)
records the CPU experiment, which remains unmeasured. The source registry has no
NVIDIA/Earth-2 or Microsoft-Aurora row; searches of tracked paths, adapters and
fixtures found no relevant native input/output fixture or execution client.
`api/weather_api/aurora.py` concerns astronomical aurora, not Microsoft's model.

**Do not add a generic inference validator yet.** No settled concrete checkpoint,
initializer, native fixture, resource budget and output mapping jointly support
one. Software implementation missing is separate from compute/deployment missing
and access or licence unresolved. None of these candidates has a verified local
forecast result in this pass.

## Published access paths and incompatible identities

| Candidate | Verified official software/data path | Remaining concrete distinction |
| --- | --- | --- |
| Earth2Studio | [NVIDIA component APIs](https://nvidia.github.io/earth2studio/main/modules/) separate models, input data and output stores. | Framework; not a producer or a ready current-forecast feed. |
| Local FourCastNet 1 | [Official checkpoint card](https://huggingface.co/nvidia/fourcastnet1): 26 native channels, six-axis tensors, 0.25-degree input 720 by 1440, Apache 2.0. | Pin wrapper/checkpoint and ordered variable lexicon. Card's output table says 72 by 1440 while also claiming same-as-input: resolve against pinned implementation before validating output shape. |
| Local FourCastNet 3 | [Official checkpoint card](https://huggingface.co/nvidia/fourcastnet3): 72 native channels, six-axis tensors, 721 by 1440, six-hour output; BF16 AMP recommended, inputs/outputs typically FP32, Apache 2.0. | Separate FCN3 checkpoint/runtime/member identity. Full inference on the target CPU remains unmeasured; GPU examples do not prove CPU viability. |
| Hosted FourCastNet | [NVIDIA build page](https://build.nvidia.com/nvidia/fourcastnet) offers an account/key trial, historical demo events and downloadable deployment. Current page names API Trial and AI Foundation Models Community terms. | No anonymous current-output feed established. Do not inherit FCN1/3 checkpoint licences or stale numeric quotas for this different service. |
| Dedicated FourCastNet NIM 1.0.0 | [NIM quickstart](https://docs.nvidia.com/nim/earth-2/fourcastnet/1.0.0/quickstart-guide.html): SFNO default, 73 ERA5 channels, FP32 NumPy input shape (1,1,73,721,1440); deployed service POST /v1/infer takes input_array, input_time and simulation_length. Output TAR members encode lead and batch indexes. | This is neither the 26-channel FCN1 contract nor 72-channel FCN3. Select exact profile/container and retain input ownership before client work. |
| Microsoft Aurora | [Model catalogue](https://microsoft.github.io/aurora/models.html) publishes checkpoints, including Aurora 1.5 deterministic and ensemble variants. | No Microsoft anonymous current-output feed found in the checked docs; self-run/Foundry require supplied initial conditions. |
| Aurora Foundry | [Current Foundry introduction](https://microsoft.github.io/aurora/foundry/intro.html) exposes original Aurora and Aurora-1.5 models, with caller-supplied input and optional output field subsets. | Endpoint availability is not a populated forecast feed; model deployment, storage communication and initializer are separate prerequisites. |
| NOAA/CIRA AIWP retrieval | [Official registry](https://registry.opendata.aws/aiwp/) and [bucket README](https://noaa-oar-mlwp-data.s3.amazonaws.com/README.txt) describe public NetCDF reforecasts at noaa-oar-mlwp-data, near-real-time updates, model/version/initializer directories and native six-hour sequences. | Registry lists FCN-v2-small/Pangu/GraphCast; README additionally FCN-v1. Neither checked document establishes Aurora or FCN3 output. Existing repo Aurora-archive claim needs current object/schema evidence; absence from these docs does not prove bucket absence. |

The documented AIWP pattern is
`MMMM_vNNN_III/YYYY/mmdd/MMMM_vNNN_III_YYYYmmddhh_fXXX_fYYY_ZZ.nc`.
Exact current object availability, object size and a safe bounded slice have not
been probed. This retrieval path must preserve NOAA/CIRA publisher, original
model and GFS/IFS initializer; it is distinct from locally generated inference.

## Aurora input/output contract to settle

The [batch contract](https://microsoft.github.io/aurora/batch.html) requires
unnormalized surface (batch, history, latitude, longitude), atmospheric (batch,
history, level, latitude, longitude) and static (latitude, longitude) arrays.
Inputs contain previous/current states; outputs have one history state. Latitude
is decreasing, longitude increasing in [0,360), pressure-level order matches all
atmospheric arrays, and metadata time identifies the current input state.

Aurora 1.5 has 18 supplied surface inputs plus computed insolation, seven output-
only fields, 36 static arrays and five atmospheric variables at 13 pressure
levels. It includes total/low/medium/high clouds, unlike the researched FCN1/3
outputs. Native hourly substeps are supported, with only the final six-hour step
feeding the next autoregressive state. Feedback clipping does not guarantee
that delivered predictions meet physical bounds. These are vendor capabilities,
not accepted Astraeus cloud mappings. See the
[model catalogue](https://microsoft.github.io/aurora/models.html) and
[worked input example](https://microsoft.github.io/aurora/example_v1p5.html).

The example's ERA5 input is illustrative; the provider cautions that IFS-trained
accuracy does not transfer automatically. Its sample NaN-to-zero preparation
is not an accepted Astraeus missing-data rule. Freeze model-specific initializer
(HRES T0 versus analysis versus ERA5), history interval, regridding, native units,
normalization/static versions, masks and input completeness before coding.
Aurora variants for air pollution and waves need their own CAMS or HRES-WAM
input contract; do not expose them through a weather-only descriptor.

## Actionable remaining contracts

1. **Identity and fields:** choose one model/version/profile, checkpoint and
   static-data digests, ordered native channel table, grids and coordinate
   orientation. Define explicit source/initializer/member/run/time identity,
   permitted requested outputs and unmapped dispositions. Retain generated-here
   lineage and no extra forecast-centre vote for a framework/model rerun.
2. **Input authority:** identify a lawful, available complete initializer with
   exact two-state history where required. Freeze transformations, missing/QC
   refusal, pressure levels and static data. A selected point cannot initialize
   a global forecast tensor.
3. **Native evidence:** retain one real bounded input/output slice plus a
   manifest binding the full tensor shape, checkpoint, transformation versions,
   run, lead and output checksum. Only then implement a pure metadata/value
   validator and fixed-fixture tests. Synthetic tensors test plumbing, not
   scientific or CPU feasibility.
4. **Execution:** choose local measured CPU/GPU or a named deployed service;
   establish wall-time, memory, disk, transfer, output and concurrency ceilings,
   cancellation and partial-result refusal. NIM archive processing requires
   bounded streaming, safe member names/types and expected lead cardinality.
   Treat checkpoint loading as loading, never completed forecast inference.
5. **Foundry deployment:** use the current catalogue/custom-container path.
   Microsoft's [endpoint page](https://microsoft.github.io/aurora/foundry/server.html)
   explicitly deprecates the older MLflow deployment recipe; the repo does not
   currently support building your own new endpoint through that recipe.
   Endpoint configuration, communication storage, readiness and model/input
   availability need separate safe status outcomes. Credential workflow remains
   blocked by the unavailable required aws-secrets-manager skill; no local
   secret state was inspected and no client/configuration code was added.
6. **Scientific admission:** preserve cloud units/support, precipitation and
   radiation accumulation windows, physical-bound violations and masks rather
   than clipping into favorable evidence. Validate selected Avalon cells and
   native timelines against the accepted target use before consumer mapping.
   Do not infer fog/visibility or operational skill from available moisture.

Recommended next bounded decision: choose **AIWP delivered FCN-v2-small** if
retrieval without local inference is the aim, or **Aurora 1.5 with an explicitly
licensed IFS initializer** if direct generated cloud output is the aim. These
are research choices for owner review, not new capabilities promised by this
branch. A generic "Earth-2/Aurora client" would hide incompatible contracts.

Spec-Impact: none. Source-local research handoff; no behavior or normative status changed.
Verification: repository tracked-path/content audit and primary-document reads;
no model, current forecast payload, authenticated request or deployment proof.
