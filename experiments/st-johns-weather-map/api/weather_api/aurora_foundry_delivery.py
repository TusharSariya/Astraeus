"""Experimental Aurora 1.5 submission; no provider/registry admission.

The caller owns a complete native Batch and bounded network/storage transports.
No initializer, credentials, deployment, normalization, or forecast skill is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import hashlib
from importlib.metadata import version
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterator, Protocol
from urllib.parse import urlsplit

import numpy as np

CONTRACT_VERSION = "aurora-foundry-delivery-v1"
SDK_VERSION = "2.0.1"
SDK_API_SHA256 = "073ca4c7a2159079180368485f207e086140f19fad39d8a0ac534bf869b8f26c"
SDK_REVISION = "7179f501b9f1a66e0444b782ecd06aa07062c8bc"
MODEL_NAME = "aurora-0.25-v1.5"
SURFACE_INPUTS = (
    "2t", "10u", "10v", "msl", "2d", "tcwv", "tcc", "100u", "100v", "sp",
    "lcc", "mcc", "hcc", "skt", "stl1", "swvl1", "ci", "scaled_sd", "insolation",
)
SURFACE_OUTPUTS = SURFACE_INPUTS + (
    "i10fg", "blh", "uvb_1h", "ssrd_1h", "ttr_1h", "scaled_tp_1h", "scaled_sf_1h",
)
STATIC_INPUTS = (
    "lsm", "z", "anor", "isor", "cvh", "cl", "dl", "cvl", "slor", "slt_0", "slt_1",
    "slt_2", "slt_3", "slt_4", "slt_5", "slt_6", "slt_7", "sdfor", "sdor", "tvh_0",
    "tvh_18", "tvh_19", "tvh_3", "tvh_4", "tvh_5", "tvh_6", "tvl_0", "tvl_1", "tvl_10",
    "tvl_11", "tvl_13", "tvl_16", "tvl_17", "tvl_2", "tvl_7", "tvl_9",
)
ATMOS_INPUTS = ("z", "u", "v", "t", "q")
LEVELS = (50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000)
LAT = np.linspace(90, -90, 721)
LON = np.arange(1440) * 0.25


class DeliveryError(RuntimeError):
    """A stable error code; upstream bodies and URLs must never be included."""


@dataclass(frozen=True)
class RuntimeConfig:
    endpoint_url: str = field(repr=False)
    deployment_id: str
    sdk_revision: str = SDK_REVISION
    request_timeout_seconds: float = 30
    deadline_seconds: float = 900
    poll_interval_seconds: float = 2
    max_polls: int = 450
    max_input_bytes: int = 1_073_741_824
    max_output_bytes: int = 268_435_456

    def validate(self) -> None:
        url = urlsplit(self.endpoint_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise DeliveryError("invalid_endpoint_config")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.deployment_id):
            raise DeliveryError("invalid_deployment_identity")
        if self.sdk_revision != SDK_REVISION:
            raise DeliveryError("unsupported_sdk_revision")
        for value, upper in ((self.request_timeout_seconds, 120),
                             (self.deadline_seconds, 3600),
                             (self.poll_interval_seconds, 60)):
            if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= upper:
                raise DeliveryError("invalid_runtime_bounds")
        for value, upper in ((self.max_polls, 3600), (self.max_input_bytes, 1_073_741_824),
                             (self.max_output_bytes, 1_073_741_824)):
            if type(value) is not int or not 0 < value <= upper:
                raise DeliveryError("invalid_runtime_bounds")


@dataclass(frozen=True)
class Initialization:
    """Caller attestation, bound to the supplied batch; not scientific admission."""
    source: str
    run_id: str
    previous_time: datetime
    current_time: datetime
    input_sha256: str
    static_sha256: str
    checkpoint_sha256: str
    transformation_version: str
    native_units_contract: str
    terms_reference: str

    def validate(self) -> None:
        for value in (self.source, self.run_id, self.transformation_version,
                      self.native_units_contract, self.terms_reference):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise DeliveryError("missing_initialization_provenance")
        for value in (self.input_sha256, self.static_sha256, self.checkpoint_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise DeliveryError("invalid_initialization_digest")
        for value in (self.previous_time, self.current_time):
            if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
                raise DeliveryError("initialization_time_requires_utc")
        if self.current_time - self.previous_time != timedelta(hours=6):
            raise DeliveryError("initialization_history_requires_six_hours")


@dataclass(frozen=True)
class ForecastRequest:
    num_steps: int = 1
    fine_lead_times: tuple[int, ...] = (6,)
    saved_surf_vars: tuple[str, ...] = ("2t", "tcc", "lcc", "mcc", "hcc")

    def validate(self) -> None:
        if type(self.num_steps) is not int or not 1 <= self.num_steps <= 40:
            raise DeliveryError("invalid_step_count")
        leads = self.fine_lead_times
        if (not isinstance(leads, tuple) or not leads
                or any(type(v) is not int or not 1 <= v <= 6 for v in leads)
                or tuple(sorted(set(leads))) != leads or leads[-1] != 6):
            raise DeliveryError("invalid_fine_lead_times")
        if self.num_steps * len(leads) > 240:
            raise DeliveryError("output_count_exceeded")
        names = self.saved_surf_vars
        if (not isinstance(names, tuple) or not names or len(set(names)) != len(names)
                or any(v not in SURFACE_OUTPUTS for v in names)):
            raise DeliveryError("invalid_saved_surface_variables")

    @property
    def leads(self) -> tuple[int, ...]:
        return tuple(6 * step + lead for step in range(self.num_steps)
                     for lead in self.fine_lead_times)


class BoundedClient(Protocol):
    """Must enforce timeout, limit response size, and suppress upstream body logging."""
    endpoint_url: str
    def submit_task(self, data: dict, *, timeout: float) -> dict: ...
    def get_progress(self, task_id: str, *, timeout: float) -> dict: ...


@dataclass(frozen=True)
class ReceivedBatch:
    batch: Any = field(repr=False)
    serialized_bytes: int


class BoundedChannel(Protocol):
    """Must enforce timeout and byte caps BEFORE allocation/deserialization.

    to_spec returns SDK communication configuration, managed outside this module.
    Implementations must not log configuration or upstream bodies.
    """
    def to_spec(self) -> str: ...
    def send(self, batch: Any, task_id: str, name: str, *, timeout: float,
             max_bytes: int) -> None: ...
    def read(self, task_id: str, name: str, *, timeout: float, max_bytes: int) -> bytes: ...
    def receive(self, task_id: str, name: str, *, timeout: float, max_bytes: int) -> ReceivedBatch: ...


def _array(value: Any) -> np.ndarray:
    # Native SDK tensors must already be on CPU, detached and unnormalized.
    if hasattr(value, "detach"):
        if value.device.type != "cpu":
            raise DeliveryError("batch_requires_cpu_tensors")
        value = value.detach().numpy()
    if not isinstance(value, np.ndarray) or value.dtype != np.float32:
        raise DeliveryError("batch_requires_float32")
    return value


def _metadata(batch: Any, valid_time: datetime, *, output: bool = False) -> None:
    meta = batch.metadata
    if not np.array_equal(np.asarray(meta.lat), LAT[:-1] if output else LAT) or not np.array_equal(np.asarray(meta.lon), LON):
        raise DeliveryError("invalid_global_grid")
    # The SDK uses naive UTC datetime values in its official example.
    if tuple(meta.time) not in ((valid_time,), (valid_time.replace(tzinfo=None),)):
        raise DeliveryError("batch_time_mismatch")


def _fields(values: dict, names: tuple[str, ...], shape: tuple[int, ...], budget: int) -> int:
    if set(values) != set(names):
        raise DeliveryError("native_field_inventory_mismatch")
    used = 0
    for value in values.values():
        arr = _array(value)
        if arr.shape != shape:
            raise DeliveryError("native_shape_mismatch")
        used += arr.nbytes
        if used > budget:
            raise DeliveryError("tensor_byte_limit")
        # Scan one latitude row at a time, bounding the validation temporary.
        for row in range(shape[-2]):
            if not np.isfinite(arr[..., row, :]).all():
                raise DeliveryError("nonfinite_native_values")
    return used


def validate_initialization(batch: Any, init: Initialization, max_bytes: int) -> None:
    init.validate()
    _metadata(batch, init.current_time)
    if tuple(batch.metadata.atmos_levels) != LEVELS:
        raise DeliveryError("pressure_level_mismatch")
    used = _fields(batch.surf_vars, SURFACE_INPUTS, (1, 2, 721, 1440), max_bytes)
    used += _fields(batch.atmos_vars, ATMOS_INPUTS, (1, 2, 13, 721, 1440), max_bytes - used)
    _fields(batch.static_vars, STATIC_INPUTS, (721, 1440), max_bytes - used)


@dataclass(frozen=True)
class GeneratedForecast:
    initialization: Initialization
    deployment_id: str
    requested_leads: tuple[int, ...]
    predictions: tuple[Any, ...] = field(repr=False)
    model_name: str = MODEL_NAME
    sdk_revision: str = SDK_REVISION
    contract_version: str = CONTRACT_VERSION
    evidence_kind: str = "generated-here"
    admitted: bool = False


def load_sdk_submit() -> Callable[..., Iterator[Any]]:
    """Load only the reviewed distribution and source file, without installing it."""
    try:
        if version("microsoft-aurora") != SDK_VERSION:
            raise DeliveryError("unsupported_sdk_version")
        from aurora.foundry.client import api
        if hashlib.sha256(Path(api.__file__).read_bytes()).hexdigest() != SDK_API_SHA256:
            raise DeliveryError("unsupported_sdk_source")
        return api.submit
    except DeliveryError:
        raise
    except Exception:
        raise DeliveryError("runtime_sdk_unavailable") from None


class _Budget:
    def __init__(self, config: RuntimeConfig, clock: Callable[[], float]):
        self.config, self.clock = config, clock
        self.end = clock() + config.deadline_seconds
        self.polls = 0

    def timeout(self) -> float:
        remaining = self.end - self.clock()
        if remaining <= 0:
            raise DeliveryError("execution_deadline_exceeded")
        return min(remaining, self.config.request_timeout_seconds)


def deliver(batch: Any, initialization: Initialization, request: ForecastRequest,
            config: RuntimeConfig, *, sdk_submit: Callable[..., Iterator[Any]] | None = None,
            client: BoundedClient, channel: BoundedChannel,
            clock: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep) -> GeneratedForecast:
    """Call pinned aurora.foundry.submit using bounded SDK-compatible facades.

    sdk_submit is supplied by the runtime owner. Raw upstream FoundryClient and
    BlobStorageChannel do not satisfy the bounded transport protocols. Deadline
    enforcement during an I/O call depends on the injected transport honoring timeout.
    Failure returns no partial predictions and does not retry or cancel a remote job.
    """
    try:
        config.validate()
        request.validate()
        required_output_bytes = len(request.leads) * len(request.saved_surf_vars) * 720 * 1440 * 4
        if required_output_bytes > config.max_output_bytes:
            raise DeliveryError("output_byte_limit")
        if client.endpoint_url != config.endpoint_url:
            raise DeliveryError("endpoint_identity_mismatch")
        budget = _Budget(config, clock)
        validate_initialization(batch, initialization, config.max_input_bytes)
        task_id: str | None = None
        output_bytes = 0

        class ClientFacade:
            def submit_task(self, data: dict) -> dict:
                nonlocal task_id
                response = client.submit_task(data, timeout=budget.timeout())
                candidate = response.get("task_id")
                if not isinstance(candidate, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", candidate):
                    raise DeliveryError("invalid_task_response")
                task_id = candidate
                return {"task_id": candidate}

            def get_progress(self, candidate: str) -> dict:
                if candidate != task_id:
                    raise DeliveryError("task_identity_mismatch")
                if budget.polls >= config.max_polls:
                    raise DeliveryError("poll_limit_exceeded")
                if budget.polls:
                    sleep(min(config.poll_interval_seconds, budget.timeout()))
                budget.polls += 1
                result = client.get_progress(candidate, timeout=budget.timeout())
                if (result.get("task_id") != candidate
                        or type(result.get("completed")) is not bool
                        or type(result.get("submitted")) is not bool
                        or type(result.get("progress_percentage")) is not int
                        or not 0 <= result["progress_percentage"] <= 100
                        or result.get("success") is not None and type(result["success"]) is not bool):
                    raise DeliveryError("invalid_progress_response")
                if result["completed"] and (not result["submitted"] or result["success"] is not True):
                    raise DeliveryError("remote_task_failed")
                # The SDK logs status, so never pass upstream status text through.
                return {**{key: result[key] for key in (
                    "task_id", "completed", "submitted", "progress_percentage")},
                    "success": result.get("success"), "status": "completed" if result["completed"] else "pending"}

        class ChannelFacade:
            def to_spec(self) -> str:
                budget.timeout()
                return channel.to_spec()

            def send(self, supplied: Any, candidate: str, name: str) -> None:
                if candidate != task_id or name != "input.nc" or supplied is not batch:
                    raise DeliveryError("invalid_upload_request")
                channel.send(supplied, candidate, name, timeout=budget.timeout(),
                             max_bytes=config.max_input_bytes)

            def read(self, candidate: str, name: str, timeout: int = 120) -> bytes:
                if candidate != task_id or name != "input.nc.ack":
                    raise DeliveryError("invalid_ack_request")
                data = channel.read(candidate, name, timeout=min(timeout, budget.timeout()), max_bytes=4096)
                if not isinstance(data, bytes) or len(data) > 4096:
                    raise DeliveryError("invalid_ack_response")
                return data

            def receive(self, candidate: str, name: str) -> Any:
                nonlocal output_bytes
                index = len(predictions)
                if candidate != task_id or name != f"prediction-{index:03d}.nc" or index >= len(request.leads):
                    raise DeliveryError("invalid_prediction_request")
                remaining = config.max_output_bytes - output_bytes
                if remaining <= 0:
                    raise DeliveryError("output_byte_limit")
                receipt = channel.receive(candidate, name, timeout=budget.timeout(), max_bytes=remaining)
                if (not isinstance(receipt, ReceivedBatch) or type(receipt.serialized_bytes) is not int
                        or not 0 < receipt.serialized_bytes <= remaining):
                    raise DeliveryError("invalid_output_receipt")
                prediction = receipt.batch
                _metadata(prediction, initialization.current_time + timedelta(hours=request.leads[index]), output=True)
                if prediction.atmos_vars or prediction.static_vars:
                    raise DeliveryError("unexpected_output_fields")
                tensor_bytes = _fields(prediction.surf_vars, request.saved_surf_vars,
                                       (1, 1, 720, 1440), remaining)
                output_bytes += max(tensor_bytes, receipt.serialized_bytes)
                return prediction

        predictions: list[Any] = []
        iterator = (sdk_submit or load_sdk_submit())(
            batch, model_name=MODEL_NAME, num_steps=request.num_steps,
            channel=ChannelFacade(), foundry_client=ClientFacade(),
            fine_lead_times=request.fine_lead_times, saved_surf_vars=request.saved_surf_vars,
            saved_atmos_vars=(), saved_atmos_levels=(), saved_static_vars=(),
            async_upload_workers=0, return_urls=False,
        )
        try:
            for prediction in iterator:
                budget.timeout()
                predictions.append(prediction)
                if len(predictions) > len(request.leads):
                    raise DeliveryError("output_count_mismatch")
        finally:
            close = getattr(iterator, "close", None)
            if close:
                close()
        if len(predictions) != len(request.leads):
            raise DeliveryError("output_count_mismatch")
        return GeneratedForecast(initialization, config.deployment_id, request.leads, tuple(predictions))
    except DeliveryError:
        raise
    except Exception:
        raise DeliveryError("aurora_delivery_failed") from None
