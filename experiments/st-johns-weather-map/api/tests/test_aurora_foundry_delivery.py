"""Offline plumbing fixtures, not real forecasts or scientific admission evidence."""
import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from types import SimpleNamespace
import typing
import warnings
import zipfile

import numpy as np
from pydantic import BaseModel
import pytest

from weather_api import aurora_foundry_delivery as a

NOW = datetime(2026, 9, 7, 6, tzinfo=timezone.utc)
INIT = a.Initialization("owner-supplied-ifs", "2026090706", NOW - timedelta(hours=6), NOW,
                        "1" * 64, "2" * 64, "3" * 64, "owner-transform-v1",
                        "owner-native-units-v1", "owner-terms-reference")


def arrays(names, shape):
    # Logical native-size fixture without allocating a global forecast.
    return {key: np.broadcast_to(np.array(0.5, dtype=np.float32), shape) for key in names}


def batch(output=False, lead=6, names=None):
    return SimpleNamespace(
        surf_vars=arrays(names or (a.ForecastRequest().saved_surf_vars if output else a.SURFACE_INPUTS),
                         (1, 1, 720, 1440) if output else (1, 2, 721, 1440)),
        atmos_vars={} if output else arrays(a.ATMOS_INPUTS, (1, 2, 13, 721, 1440)),
        static_vars={} if output else arrays(a.STATIC_INPUTS, (721, 1440)),
        metadata=SimpleNamespace(lat=a.LAT[:-1] if output else a.LAT, lon=a.LON,
                                 time=(NOW + timedelta(hours=lead) if output else NOW,),
                                 atmos_levels=() if output else a.LEVELS),
    )


class Client:
    endpoint_url = "https://fixture.example.test/score"

    def __init__(self, pending=False, failure=False):
        self.calls = []
        self.pending, self.failure = pending, failure

    def submit_task(self, data, *, timeout):
        self.calls.append(("submit", data, timeout))
        return {"task_id": "fixture-task"}

    def get_progress(self, task_id, *, timeout):
        self.calls.append(("poll", task_id, timeout))
        return dict(task_id=task_id, completed=not self.pending, submitted=True,
                    success=False if self.failure else (None if self.pending else True),
                    progress_percentage=0 if self.pending else 100,
                    status="untrusted upstream response must not reach logs")


class Channel:
    def __init__(self):
        self.calls = []
        self.predictions = [batch(output=True)]

    def to_spec(self):
        return "fixture-channel-config"

    def send(self, supplied, task_id, name, *, timeout, max_bytes):
        self.calls.append(("send", name, timeout, max_bytes))

    def read(self, task_id, name, *, timeout, max_bytes):
        self.calls.append(("read", name, timeout, max_bytes))
        return b"ack"

    def receive(self, task_id, name, *, timeout, max_bytes):
        self.calls.append(("receive", name, timeout, max_bytes))
        prediction = self.predictions.pop(0)
        return a.ReceivedBatch(prediction, sum(v.nbytes for v in prediction.surf_vars.values()) + 100)


def sdk_fixture(batch, *, model_name, num_steps, channel, foundry_client, fine_lead_times,
                saved_surf_vars, saved_atmos_vars, saved_atmos_levels, saved_static_vars,
                async_upload_workers, return_urls):
    assert model_name == a.MODEL_NAME
    assert saved_atmos_vars == saved_atmos_levels == saved_static_vars == ()
    assert async_upload_workers == 0 and return_urls is False
    task = foundry_client.submit_task(dict(model_name=model_name, num_steps=num_steps,
                                         data_folder_uri=channel.to_spec(),
                                         fine_lead_times=list(fine_lead_times),
                                         saved_surf_vars=list(saved_surf_vars)))
    task_id = task["task_id"]
    channel.send(batch, task_id, "input.nc")
    ack = False
    while True:
        progress = foundry_client.get_progress(task_id)
        assert "untrusted" not in progress["status"]
        if progress["submitted"] and not ack:
            channel.read(task_id, "input.nc.ack", timeout=120)
            ack = True
        if progress["completed"]:
            break
    for i in range(num_steps * len(fine_lead_times)):
        yield channel.receive(task_id, f"prediction-{i:03d}.nc")


def run(*, supplied=None, init=INIT, request=None, config=None, client=None, channel=None,
        sdk=sdk_fixture, **kw):
    return a.deliver(supplied or batch(), init, request or a.ForecastRequest(),
                     config or a.RuntimeConfig(Client.endpoint_url, "fixture-deployment"),
                     sdk_submit=sdk, client=client or Client(), channel=channel or Channel(),
                     sleep=lambda seconds: None, **kw)


def test_native_submission_and_provenance():
    client, channel = Client(), Channel()
    result = run(client=client, channel=channel)
    assert result.model_name == "aurora-0.25-v1.5"
    assert result.evidence_kind == "generated-here" and result.admitted is False
    assert result.initialization is INIT
    assert result.requested_leads == (6,)
    assert result.predictions[0].surf_vars["tcc"].shape == (1, 1, 720, 1440)
    assert [call[0] for call in channel.calls] == ["send", "read", "receive"]
    assert all(0 < call[2] <= 30 for call in channel.calls)
    assert channel.calls[1][3] == 4096
    assert client.calls[0][1]["saved_surf_vars"] == ["2t", "tcc", "lcc", "mcc", "hcc"]


@pytest.mark.parametrize("change,code", [
    ({"num_steps": True}, "invalid_step_count"),
    ({"num_steps": 41}, "invalid_step_count"),
    ({"fine_lead_times": (1, 2)}, "invalid_fine_lead_times"),
    ({"fine_lead_times": (6, 1)}, "invalid_fine_lead_times"),
    ({"fine_lead_times": (6, 6)}, "invalid_fine_lead_times"),
    ({"saved_surf_vars": ("fog",)}, "invalid_saved_surface_variables"),
])
def test_invalid_request_never_submits(change, code):
    client = Client()
    with pytest.raises(a.DeliveryError, match=code):
        run(request=replace(a.ForecastRequest(), **change), client=client)
    assert client.calls == []


@pytest.mark.parametrize("case,code", [
    ("field", "native_field_inventory_mismatch"), ("grid", "invalid_global_grid"),
    ("levels", "pressure_level_mismatch"), ("shape", "native_shape_mismatch"),
    ("nan", "nonfinite_native_values"), ("dtype", "batch_requires_float32"),
    ("time", "batch_time_mismatch"),
])
def test_bad_native_initialization_never_submits(case, code):
    supplied, client = batch(), Client()
    if case == "field":
        del supplied.surf_vars["tcc"]
    elif case == "grid":
        supplied.metadata.lat = a.LAT[::-1]
    elif case == "levels":
        supplied.metadata.atmos_levels = tuple(reversed(a.LEVELS))
    elif case == "shape":
        supplied.surf_vars["tcc"] = np.zeros((1, 2, 2, 2), dtype=np.float32)
    elif case == "nan":
        supplied.surf_vars["tcc"] = np.broadcast_to(np.array(np.nan, dtype=np.float32), (1, 2, 721, 1440))
    elif case == "dtype":
        supplied.surf_vars["tcc"] = np.broadcast_to(np.array(0, dtype=np.float64), (1, 2, 721, 1440))
    else:
        supplied.metadata.time = (NOW - timedelta(hours=6),)
    with pytest.raises(a.DeliveryError, match=code):
        run(supplied=supplied, client=client)
    assert not client.calls


def test_initialization_attestation_and_runtime_bounds():
    with pytest.raises(a.DeliveryError, match="six_hours"):
        run(init=replace(INIT, previous_time=NOW))
    with pytest.raises(a.DeliveryError, match="requires_utc"):
        run(init=replace(INIT, current_time=NOW.replace(tzinfo=None)))
    with pytest.raises(a.DeliveryError, match="digest"):
        run(init=replace(INIT, static_sha256="unknown"))
    for change in ({"sdk_revision": "other"}, {"max_polls": 0},
                   {"deadline_seconds": float("nan")}, {"endpoint_url": "http://example.test"}):
        with pytest.raises(a.DeliveryError):
            run(config=replace(a.RuntimeConfig(Client.endpoint_url, "fixture"), **change))


def test_poll_bound_and_remote_failure_return_no_partial_result():
    client = Client(pending=True)
    with pytest.raises(a.DeliveryError, match="poll_limit_exceeded"):
        run(client=client, config=a.RuntimeConfig(Client.endpoint_url, "fixture", max_polls=2))
    assert len([call for call in client.calls if call[0] == "poll"]) == 2
    with pytest.raises(a.DeliveryError, match="remote_task_failed"):
        run(client=Client(failure=True))


def test_deadline_and_byte_bounds():
    ticks = iter((0, 901))
    with pytest.raises(a.DeliveryError, match="execution_deadline_exceeded"):
        run(clock=lambda: next(ticks))
    with pytest.raises(a.DeliveryError, match="tensor_byte_limit"):
        run(config=a.RuntimeConfig(Client.endpoint_url, "fixture", max_input_bytes=100))
    with pytest.raises(a.DeliveryError, match="output_byte_limit"):
        run(config=a.RuntimeConfig(Client.endpoint_url, "fixture", max_output_bytes=100))


def test_output_native_timeline_and_complete_count():
    channel = Channel()
    channel.predictions = [batch(output=True, lead=12)]
    with pytest.raises(a.DeliveryError, match="batch_time_mismatch"):
        run(channel=channel)
    with pytest.raises(a.DeliveryError, match="output_count_mismatch"):
        run(sdk=lambda *args, **kwargs: iter(()))
    channel = Channel()
    channel.predictions = [batch(output=True, lead=lead) for lead in (1, 6, 7, 12)]
    result = run(channel=channel, request=a.ForecastRequest(num_steps=2, fine_lead_times=(1, 6)))
    assert result.requested_leads == (1, 6, 7, 12)


def test_safe_failure_and_endpoint_binding():
    class Broken(Client):
        def submit_task(self, *args, **kwargs):
            raise RuntimeError("private upstream response")
    with pytest.raises(a.DeliveryError) as exc:
        run(client=Broken())
    assert str(exc.value) == "aurora_delivery_failed"
    assert exc.value.__suppress_context__ is True
    with pytest.raises(a.DeliveryError, match="endpoint_identity_mismatch"):
        run(config=a.RuntimeConfig("https://different.example.test/", "fixture"))


def test_reviewed_sdk_submit_offline_when_wheel_supplied():
    """Exercise actual wheel submit source; replace imports, never model/torch execution."""
    path = os.environ.get("AURORA_SDK_WHEEL")
    if not path:
        pytest.skip("Set AURORA_SDK_WHEEL to the documented, hash-checked 2.0.1 wheel")
    with zipfile.ZipFile(path) as wheel:
        source = wheel.read("aurora/foundry/client/api.py")
    assert hashlib.sha256(source).hexdigest() == a.SDK_API_SHA256
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    namespace = dict(vars(typing), BaseModel=BaseModel, Batch=SimpleNamespace,
                     FoundryClient=object, CommunicationChannel=object, logging=logging,
                     warnings=warnings, models={a.MODEL_NAME: object},
                     iterate_prediction_files=lambda name, count: (f"prediction-{i:03d}.nc" for i in range(count)))
    exec(compile(tree, "reviewed-aurora-2.0.1-submit", "exec"), namespace)
    result = run(sdk=namespace["submit"])
    assert result.requested_leads == (6,)
    assert len(result.predictions) == 1


def test_impossible_complete_output_budget_never_submits():
    client, channel = Client(), Channel()
    with pytest.raises(a.DeliveryError, match="output_byte_limit"):
        run(request=a.ForecastRequest(num_steps=40), client=client, channel=channel)
    assert client.calls == channel.calls == []


@pytest.mark.parametrize("receipt_bytes", [0, -1, True, 2 ** 30])
def test_output_receipt_size_is_bounded(receipt_bytes):
    class BadChannel(Channel):
        def receive(self, *args, **kwargs):
            return a.ReceivedBatch(batch(output=True), receipt_bytes)
    with pytest.raises(a.DeliveryError, match="invalid_output_receipt"):
        run(channel=BadChannel())


def test_output_grid_fields_and_nonfinite_are_refused():
    channel = Channel()
    output = batch(output=True)
    output.metadata.lat = a.LAT
    channel.predictions = [output]
    with pytest.raises(a.DeliveryError, match="invalid_global_grid"):
        run(channel=channel)
    output = batch(output=True)
    output.surf_vars["tcc"] = np.broadcast_to(np.array(np.nan, dtype=np.float32), (1, 1, 720, 1440))
    channel.predictions = [output]
    with pytest.raises(a.DeliveryError, match="nonfinite_native_values"):
        run(channel=channel)
    output = batch(output=True)
    output.static_vars = {"z": np.zeros(1)}
    channel.predictions = [output]
    with pytest.raises(a.DeliveryError, match="unexpected_output_fields"):
        run(channel=channel)
