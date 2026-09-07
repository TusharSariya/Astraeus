"""Compose the one named AQHI observation without widening source categories."""
from datetime import timedelta

from .models import AQHIDemandUnavailable, DataMode, PointResponse


def with_aqhi_observation(response: PointResponse) -> PointResponse:
    from .aqhi_query import AqhiQueryUnavailable, is_aqhi_observation_companion
    from .source_delivery import source_readers

    try:
        fields = source_readers()["eccc-aqhi"].read_point(
            response.latitude, response.longitude, response.valid_time,
        )
        if len(fields) != 1:
            raise AqhiQueryUnavailable("AQHI companion identity is unavailable")
        field = fields[0]
        if (not is_aqhi_observation_companion(field)
                or not timedelta(0) <= response.valid_time - field.provenance.valid_time < timedelta(hours=1)):
            raise AqhiQueryUnavailable("AQHI companion identity or selected time is unavailable")
    except Exception as error:
        outcome = error.outcome if isinstance(error, AqhiQueryUnavailable) else AQHIDemandUnavailable(
            reason="query_failed", error_type="AQHICompanionUnavailable",
        )
        return response.model_copy(update={
            "observation_unavailable": [*response.observation_unavailable, outcome],
            "notices": [*response.notices, "eccc-aqhi has no validated nearby station observation less than one hour old at or before this selection"],
        })
    report = field.provenance.native_report
    return response.model_copy(update={
        "data_mode": DataMode.LIVE,
        "fields": [*response.fields, field],
        "notices": [*response.notices,
            f"eccc-aqhi station {report.station_id} observation at {report.observation_time.isoformat()} is shown with its own native station and transport provenance"],
    })
