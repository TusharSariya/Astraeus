"""A learned flow estimator (RAFT via ONNX) in place of DIS - everything downstream unchanged.

One plugin, one module. See ``ingest.derive.methods`` for the contract.
"""

from __future__ import annotations

from typing import Any

from ingest.derive.flow_ops import (
    _consistency,
    _development_agreement,
    _dis_flow,
    _display_weight,
    _prior_corrected,
    _steering_prior,
    _supported_flow,
)
from ingest.derive.methods.contract import Requirement, MethodContext, PairMotion
from ingest.derive.methods.baseline import BaselineMethod


#: Where the RAFT ONNX graph is read from. Absent or unreadable, the method
#: falls back to DIS and says so in provenance - an optional model may never
#: fail the motion artifact the whole map depends on.
FLOW_NET_MODEL_ENV = "WEATHER_FLOW_NET_MODEL"
#: The exported graph's fixed input, (rows, cols). RAFT was exported at one
#: size, so every field is resampled to this and its flow resampled back;
#: inference cost is therefore constant in the source grid, not proportional.
FLOW_NET_INPUT = (360, 480)


class FlowNetMethod(BaselineMethod):
    """Motion from a learned network instead of DIS. Everything else baseline.

    The ONLY variable under test is the ESTIMATOR. The consistency score, the
    neighbourhood fill, the support field, the steering prior, the development
    agreement, the display weight and the composite are the baseline's,
    untouched - ``composite`` is inherited from ``BaselineMethod`` and is
    deliberately not overridden, so this method draws with exactly the shipped
    `hermite` shader. A controlled comparison is the whole point: any score
    difference against `baseline` is attributable to the flow field alone.

    The network emits a DISPLACEMENT FIELD and nothing else. No pixel is
    synthesised, every displayed cell still comes from a retrieved frame, and
    so this is an ordinary method under the governing rule - ``generative``
    stays False and no carve-out is required (bench design, owner decision
    2026-08-31).

    DISABLED, on this experiment's own measurement rather than on principle.
    Scored against the shipped baseline on the live cycle of 2026-09-01, same
    frames, same downstream, improvement over the reversed-flow control:

        layer                     grid      DIS      flow-net    delta
        eccc-hrdps total_cloud    148x149   0.2331   0.2968      +0.0637
        eccc-rdps  total_cloud     35x36    0.1183   0.0889      -0.0294
        noaa-gfs   cloud_low       61x121   0.3609   0.3330      -0.0279
        noaa-gfs   cloud_middle    61x121   0.4197   0.3413      -0.0784
        noaa-gfs   cloud_high      61x121   0.3792   0.2843      -0.0949
        noaa-gfs   total_cloud     61x121   0.3359   0.2826      -0.0533

    It wins on exactly one layer of six and loses on five, worst on the
    coarsest grids - the mean change is -0.037. The single win is the layer
    whose grid is closest to the size RAFT was trained and exported at; a
    35x36 field upsampled thirteenfold into a network whose priors are rigid
    edges in natural video is interpolation, not estimation.

    The control that settles it: DIS run at the SAME 360x480 resolution and
    resampled back the same way scores 0.2506 on HRDPS - so a quarter of the
    apparent gain is the resampling, not the learning - and it beats native
    DIS on ALL SIX layers (+0.016 to +0.043) for microseconds. Smoothing the
    native DIS field instead changes nothing (0.2320 against 0.2331), so the
    lever is the RESOLUTION the estimator runs at, not the estimator family.
    That is pySTEPS' finding (GMD 2019, under 2% skill spread across flow
    estimators) reproduced rather than broken, and it points at a free change
    to the baseline that is not this method's to make.

    Cost, measured on this machine, were it enabled: 689 ms per pair against
    ``_dis_flow``'s 2.2 ms (312x), constant in grid size because the graph's
    input is fixed; roughly 370 flow calls per variable per cycle once the
    held-out harness and ``configure`` are counted, so about 25 minutes added
    to a cycle that derives six variables. Image cost is about 150 MB on the
    worker only - onnxruntime 75 MB installed, protobuf and flatbuffers ~10 MB,
    and the 64 MB graph. Weights are BSD-3-Clause (Copyright 2020 princeton-vl,
    the original RAFT release), the ONNX conversion MIT, both verified from the
    licence files published beside the graph in OpenCV's own model repository.
    """

    id = "flow-net"
    title = "Advection along learned flow (RAFT)"
    summary = (
        "The baseline construction with its motion estimated by a learned optical-flow network "
        "(RAFT) instead of OpenCV DIS. The network emits a displacement field only - every "
        "displayed pixel still comes from a retrieved frame - and everything downstream of the "
        "estimator is the baseline's unchanged, so the comparison isolates the estimator."
    )
    shader = "hermite"
    # Measured, not assumed: a net regression across the layer set (see the
    # class docstring) for 312x the inference cost and ~150 MB of image. It
    # stays registered because the measurement is worth keeping reproducible.
    enabled = False


    def requirements(self) -> list[Requirement]:
        """An ONNX runtime and a graph, neither vendored into the image."""
        try:
            import onnxruntime  # noqa: F401, PLC0415

            runtime = True
        except Exception:  # noqa: BLE001
            runtime = False
        import os  # noqa: PLC0415

        graph = bool(os.environ.get(FLOW_NET_MODEL_ENV))
        return [
            Requirement(name="onnxruntime", met=runtime,
                        detail="installed" if runtime else "not installed; the method falls back to DIS bit for bit"),
            Requirement(name="a flow graph", met=graph,
                        detail=f"{FLOW_NET_MODEL_ENV} points at a graph" if graph else f"{FLOW_NET_MODEL_ENV} is unset, so no graph is loaded"),
        ]

    def __init__(self, *, use_prior: bool = False) -> None:
        super().__init__(use_prior=use_prior)
        #: Set by `_estimate` when the runtime or the graph is missing, so
        #: provenance can never report DIS numbers under this method's name.
        self.fell_back = False

    def _session(self) -> Any | None:
        """The cached ORT session, or None when the optional runtime is absent.

        Imported lazily and inside the method precisely so that neither the
        ingest image nor the API image carries onnxruntime unless someone has
        deliberately selected the `flownet` extra and pointed the environment
        at a graph. A missing optional dependency is a fallback, never an error.
        """
        import os  # noqa: PLC0415

        # The sentinel distinguishes "not looked yet" from "looked and there is
        # nothing there". Without it a corrupt graph is re-opened on every pair
        # of every hold-out, which is hundreds of failed 64 MB loads per cycle.
        cached = getattr(self, "_cached_session", "unset")
        if cached != "unset":
            return cached
        self._cached_session = None
        path = os.environ.get(FLOW_NET_MODEL_ENV, "")
        if not path or not os.path.exists(path):
            return None
        try:
            import onnxruntime  # noqa: PLC0415

            self._cached_session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
        except Exception:
            # An unreadable graph or an absent runtime is an absent estimator.
            # The motion artifact the whole map depends on still gets built.
            self._cached_session = None
        return self._cached_session

    def _estimate(self, previous: Any, following: Any) -> Any:
        """Displacement from `previous` to `following`, in grid cells.

        Falls back to `_dis_flow` - the baseline's own estimator - whenever the
        runtime or the graph is unavailable, and records that it did.
        """
        import numpy  # noqa: PLC0415

        session = self._session()
        if session is None:
            self.fell_back = True
            return _dis_flow(previous, following)
        import cv2  # noqa: PLC0415

        rows, cols = numpy.asarray(previous).shape
        net_rows, net_cols = FLOW_NET_INPUT

        def prepared(field: Any) -> Any:
            # The same 0-100 percent -> 0-255 scaling `_dis_flow` uses, so the
            # two estimators see the same photometry; replicated to the three
            # channels the graph was exported for.
            filled = numpy.nan_to_num(numpy.asarray(field, dtype="float64"), nan=0.0)
            scaled = numpy.clip(filled, 0.0, 100.0) * 2.55
            resized = cv2.resize(scaled.astype("float32"), (net_cols, net_rows), interpolation=cv2.INTER_LINEAR)
            return numpy.repeat(resized[None, :, :], 3, axis=0)[None, ...].astype("float32")

        names = [item.name for item in session.get_inputs()]
        raw = session.run(None, {names[0]: prepared(previous), names[1]: prepared(following)})
        # The full-resolution head, not the 1/8 one: pick the output whose
        # trailing shape is the graph's input size rather than trusting order.
        field = next(
            item[0].transpose(1, 2, 0) for item in raw if item.ndim == 4 and item.shape[-2:] == FLOW_NET_INPUT
        )
        flow = cv2.resize(field, (cols, rows), interpolation=cv2.INTER_LINEAR)
        # Network pixels back to grid cells: the resample changes the unit as
        # well as the sampling, and forgetting the scale is a silent 3x error.
        flow[..., 0] *= cols / net_cols
        flow[..., 1] *= rows / net_rows
        return flow.astype("float32")

    def motion(self, context: MethodContext) -> list[PairMotion]:
        """The baseline's derivation with `_estimate` in place of `_dis_flow`.

        The body below is BaselineMethod.motion line for line except for the
        two estimator calls. It is duplicated rather than seamed because the
        baseline is not this change's to edit; `test_flow_net_matches_baseline
        _when_it_falls_back` pins the two against each other on real frames, so
        the duplication is checkable rather than hoped for.
        """
        import numpy  # noqa: PLC0415

        self.fell_back = False
        results: list[PairMotion] = []
        for position in range(len(context.frames) - 1):
            previous = context.frames[position]
            following = context.frames[position + 1]
            raw01 = self._estimate(previous, following)
            raw10 = self._estimate(following, previous)
            agreed = _consistency(raw01, raw10)
            flow01, support = _supported_flow(raw01.astype("float64"), agreed)
            flow10, _ = _supported_flow(raw10.astype("float64"), agreed)
            carried = 0.0
            if self.use_prior and context.dataset is not None:
                pair_indices = (context.indices[position], context.indices[position + 1])
                prior = _steering_prior(
                    context.dataset,
                    context.variable,
                    pair_indices,
                    context.interval_seconds,
                    numpy.asarray(previous).shape,
                )
                if prior is not None:
                    flow01, carried = _prior_corrected(flow01, support, prior)
                    flow10, _ = _prior_corrected(flow10, support, -prior)
            results.append(
                PairMotion(
                    flow01=flow01,
                    flow10=flow10,
                    confidence=agreed,
                    support=support,
                    advect_weight=_display_weight(support, _development_agreement(previous, following, flow01)),
                    diagnostics={
                        "prior_weight_carried": carried,
                        # 1.0 means these fields are DIS wearing this method's
                        # name. Provenance has to be able to say which.
                        "flow_net_fell_back": 1.0 if self.fell_back else 0.0,
                    },
                )
            )
        return results


#: The fractions of an interval a held-out frame is reconstructed at. The
#: midpoint is the hardest case and the one the shipped thresholds were
#: measured against; the thirds are reached by holding a frame out of a
#: three-interval span, and they catch a construction that is right at the
#: middle and wrong on the way there - which a midpoint-only score cannot
#: see, and which is exactly what the reader watches during playback.
