# NVIDIA Earth-2 and CPU feasibility

Last reviewed: 2026-09-03

Status: non-normative research. Hardware, hosted quotas, checkpoints, licences,
and model versions are time-sensitive and must be rechecked before admission.

## Executive conclusion

NVIDIA Earth-2 is an ecosystem rather than one evidence source. Earth2Studio is
an Apache-2.0 inference framework; provenance and permission still belong to
each model, checkpoint, initializer, and dataset. It is a strong experimental
route for Astraeus, but running a model locally creates `generated-here`
evidence rather than a new observational or national forecast centre.

FourCastNet 1 is plausibly usable for a CPU smoke experiment. FourCastNet 3 is
device-generic at the wrapper level and can load on CPU, but NVIDIA does not
publish a successful full-checkpoint CPU inference test. Its CPU practicality
therefore remains unverified. The catalogue's 40 GB and 80 GB badges are
recommended GPU-memory classes, not enforced minimums.

## Earth2Studio

[Earth2Studio](https://github.com/NVIDIA/earth2studio) provides forecast,
ensemble, diagnostic, downscaling, data-source, statistics, and output
interfaces. The framework is Apache 2.0. Its documentation explicitly says
third-party models and datasets retain their providers' licences.

The [installation guide](https://nvidia.github.io/earth2studio/main/userguide/about/install/)
states that Earth2Studio has no package-wide hardware requirement and that many
features work wherever PyTorch works. It recommends Ubuntu 24.04, Python 3.13,
CUDA 13, one recent NVIDIA GPU, at least 40 GB GPU memory at FP32, and 128 GB
disk because most substantial models require or practically need GPU compute.

## FourCastNet 1

The [FourCastNet 1 model card](https://huggingface.co/nvidia/fourcastnet1)
declares Apache 2.0 commercial and non-commercial use, global 0.25-degree
coverage, six-hour steps, and 26 surface/pressure-level variables. The public
checkpoint was observed by HTTP metadata as 301,168,640 bytes.

NVIDIA's Earth2Studio implementation is an ordinary PyTorch module with no
unconditional `.cuda()` call; model state follows the input device. Its raw
FP32 input is approximately:

```text
26 * 720 * 1440 * 4 bytes = 108 MB
```

Activations and FFT workspaces make peak memory larger. CPU execution is
structurally plausible, but NVIDIA supplies no authoritative CPU wall-time or
peak-RAM benchmark. One global six-hour step on the target CPU is the minimum
honest validation.

FourCastNet 1 does not directly output total/stratified cloud, condensate, fog,
ceiling, or visibility. It cannot satisfy critical cloud evidence by itself.

## FourCastNet 3

The [FourCastNet 3 model card](https://huggingface.co/nvidia/fourcastnet3)
declares Apache 2.0 use, about 711 million parameters, 72 variables on a
721-by-1440 global 0.25-degree grid, probabilistic rollouts, and BF16 as the
recommended inference precision. The main public checkpoint was observed as
2,843,497,639 bytes.

Approximate lower bounds, before activations and workspaces:

```text
FP32 parameters: 711 million * 4 bytes = 2.84 GB
BF16 parameters: 711 million * 2 bytes = 1.42 GB
FP32 input:       72 * 721 * 1440 * 4 bytes = 299 MB
```

The [FCN3 wrapper](https://github.com/NVIDIA/earth2studio/blob/main/earth2studio/models/px/fcn3.py)
accepts PyTorch devices. Its tests exercise a dummy wrapper on CPU and CUDA and
move a loaded package to both devices. When the optimized torch-harmonics CUDA
extension is absent, loading warns about reduced GPU performance rather than
immediately rejecting the model.

That is not a full CPU inference validation. The repository's real full-model
inference test is commented out, cites lack of an 80 GB CI GPU, and does not
substitute a CPU run. A complete CPU step may be extremely slow or encounter a
poorly supported spherical operator. A high-memory x86-64 Linux host is a more
credible CPU experiment than assuming Apple MPS compatibility.

FCN3 predicts pressure-level moisture, temperature, wind, geopotential and
selected surface fields, but no direct cloud/fog/ceiling/visibility field. Its
best initial role is a labelled probabilistic moisture and synoptic scenario.
Any cloud diagnostic is a separate registered and validated construction.

## Hosted and local access

The [NVIDIA hosted FourCastNet page](https://build.nvidia.com/nvidia/fourcastnet)
offers an account/API-key prototype. The page observed on 2026-09-03 advertised
shared limits up to 40 requests per minute and 10,000 requests per day, subject
to model availability and shared throttling. This is not a production SLA.
Dedicated NIM or an inference partner is a paid production route whose current
terms and price must be obtained before implementation.

Local framework and Apache-licensed checkpoints are free to download and use;
hardware, cloud GPU time, storage, and initializer data access are not
necessarily free. A local forecast must record the exact initialization source,
model/checkpoint digest, Earth2Studio version, precision, seed/member, runtime,
and transformation chain.

## ForecastNet

[jjdabr/forecastNet](https://github.com/jjdabr/forecastNet) is an MIT-licensed
2020 generic multi-step time-series architecture with synthetic demonstrations.
It supplies no current atmospheric analysis, global spatial model, operational
weather checkpoint, cloud product, or uncertainty calibration. It is not an
NWP provider and should not enter the provider catalogue. A locally trained
station model would be a separately validated generated method and must beat
persistence and seasonal baselines.

## Measurement plan

1. Run FourCastNet 1 for one six-hour step on CPU and record processor, threads,
   PyTorch build, wall time, peak RSS, checkpoint digest, input source and
   output checksum.
2. Load FCN3 on CPU without inference and record dependencies, load time and
   resident memory.
3. Attempt one FCN3 member and one six-hour step with batch one under a bounded
   timeout and memory monitor. Treat timeout or unsupported operation as a
   measured result.
4. Repeat the identical FCN3 case on a rented A100 80 GB or H100 only if the
   CPU result is impractical.
5. Compare relevant FCN outputs against IFS/ENS, GFS/GEFS, HRDPS/REPS, GOES and
   surface observations. Do not treat availability or vendor scorecards as
   Avalon cloud skill.
