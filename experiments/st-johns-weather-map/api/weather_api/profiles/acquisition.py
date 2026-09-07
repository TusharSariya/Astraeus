"""Activity's bounded source reads; existing coordinators own acquisition/cache/QC."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

from ingest.derive.registry import DE442_GEOMETRY, resolve
from registry.fields import units_for

from .. import astronomy
from ..config import VERDICT_SOURCE_PRECEDENCE, WINDOW_BACK
from ..models import Coverage, DataMode, EvidenceField, Freshness, Provenance, Quality
from .windows import GeometrySample, WindowRule, resolve_window


def tier(at, reference):
    return 'core' if at <= reference + WINDOW_BACK else 'planning'


def ancillary(field, value, at, *, source, product, retrieved, revision, quality, freshness, derivation=None, version=None, native_resolution='exact selected instant'):
    return EvidenceField(field=field, value=value, provenance=Provenance(
        data_mode=DataMode.LIVE, evidence_class='derived_here' if derivation else 'retrieved',
        source_id=source, artifact_revision=revision, provider='NASA JPL' if derivation else 'NOAA SWPC',
        product=product, forecast_centre='NASA JPL' if derivation else 'NOAA SWPC', run_time=None,
        valid_time=at, retrieval_time=retrieved, vertical_level='not applicable',
        original_units=units_for(field), normalized_units=units_for(field), native_resolution=native_resolution,
        native_crs='topocentric WGS84' if derivation else 'planetary index', quality=quality,
        freshness=freshness, coverage=Coverage(status='complete'), licence='Public domain',
        attribution='NASA/JPL DE442 via Skyfield' if derivation else 'NOAA Space Weather Prediction Center',
        adapter_version='activity-evidence-v1', derivation=derivation, derivation_version=version,
        derivation_citation='Registered de442_sun_moon_geometry; pinned DE442 kernel and astronomy-de442-v1' if derivation else None,
        contributing_evidence=['retrieval_time is computation time; kernel retrieval age is unknown'] if derivation else []))


class ActivityReader:
    """At most four native weather queries + one finite Kp query per instant.

    Window geometry is a 25-hour minute scan using the existing registered
    ephemeris path, never a remote astronomy call. No /point fanout occurs.
    """
    def factories(self):
        from ..hrdps_query import hrdps_query_coordinator
        from ..rdps_query import rdps_query_coordinator
        from ..gdps_query import gdps_query_coordinator
        from ..gfs_query import gfs_query_coordinator
        return dict(zip(VERDICT_SOURCE_PRECEDENCE['core'], [hrdps_query_coordinator, rdps_query_coordinator, gdps_query_coordinator, gfs_query_coordinator]))

    def __call__(self, focus, profiles, reference, stop: Callable[[], bool]):
        from ..store import configured_mode, LIVE_MODE
        if configured_mode() != LIVE_MODE:
            raise RuntimeError('Activity requires live source queries; no fixture fallback')
        at = focus.valid_time
        fields, notices, resolutions = [], [], {}
        for source in VERDICT_SOURCE_PRECEDENCE[tier(at, reference)]:
            if stop():
                raise TimeoutError('Activity acquisition deadline exceeded')
            try:
                coordinator = self.factories()[source]()
                rows, _, source_notices = coordinator.point_fields(focus.latitude, focus.longitude, at)
                fields.extend(row for row in rows if row.provenance.source_id == source and row.provenance.valid_time == at)
                notices.extend(source_notices)
                try:
                    resolutions[source] = 3600 if tier(at, reference) == 'core' else coordinator.native_resolution_seconds(at, at + timedelta(seconds=1))
                except Exception:
                    notices.append(f'{source}: native cadence unavailable; exact values retained')
            except Exception:
                notices.append(f'{source}: selected-time read unavailable')
        if stop():
            raise TimeoutError('Activity acquisition deadline exceeded')
        try:
            from ..swpc_kp_query import swpc_kp_query_service
            observed, forecast = swpc_kp_query_service().series(at)
            series = observed if at <= reference else forecast
            exact = [row for row in series.readings if row.time == at]
            if series.available and series.acquisition and len(exact) == 1:
                item, receipt = exact[0], series.acquisition
                resolutions['noaa-swpc-kp'] = 10800
                fields.append(ancillary('kp_index', item.value, at, source=series.source_id,
                    product=f'{series.product}; provider status: {item.status}', retrieved=receipt.transport_completed_at,
                    revision=receipt.body_sha256, quality=Quality(status='unknown', flags=['provider_qc_not_supplied']),
                    freshness=series.freshness, native_resolution='3 hours; exact native time only'))
            else:
                notices.append('Kp: no exact native row; observed and forecast are not substituted')
        except Exception:
            notices.append('noaa-swpc-kp: selected-time read unavailable')
        windows = {}
        geometry = None
        refusal = resolve(DE442_GEOMETRY)
        if not refusal and not stop():
            try:
                geometry = astronomy.sky_geometry(focus.latitude, focus.longitude, at - timedelta(hours=1), at + timedelta(hours=24), at)
                from ..ephemeris import EPHEMERIS_SHA256
                for field, value in [('sun_altitude', geometry.sun_altitude_deg), ('moon_altitude', geometry.moon_altitude_deg), ('moon_illuminated_fraction', geometry.moon.illuminated_fraction)]:
                    fields.append(ancillary(field, value, at, source=astronomy.SOURCE_ID, product='DE442 Sun/Moon geometry',
                        retrieved=reference, revision=EPHEMERIS_SHA256, quality=Quality(status='passed', flags=['derived']),
                        freshness=Freshness(status='unknown'), derivation=astronomy.derivation(), version=astronomy.DERIVATION_VERSION))
            except astronomy.AstronomyUnavailable as error:
                notices.append(str(error))
        for pid, profile in profiles.items():
            samples = [GeometrySample(stamp, altitude) for stamp, altitude in geometry.sun_samples] if geometry else []
            resolved = resolve_window(WindowRule.from_profile(profile), samples, now=at)
            missing = [name for name in profile['window']['geometry_fields'] if not any(row.key == name for row in fields)]
            if resolved.unresolved:
                missing.append(resolved.unresolved)
            intervals = resolved.as_dict()['intervals'] if not missing else []
            windows[pid] = {**resolved.as_dict(), 'intervals': intervals, 'unresolved_fields': list(dict.fromkeys(missing)),
                'outside_window': None if missing else not any(start <= at <= end for start, end in resolved.intervals),
                'rule': profile['window']['rule'],
                'current': next((interval for interval in intervals if datetime.fromisoformat(interval['start']) <= at <= datetime.fromisoformat(interval['end'])), None),
                'next': next((interval for interval in intervals if datetime.fromisoformat(interval['start']) > at), None),
                'sample_resolution_seconds': astronomy.STEP_SECONDS, 'start': (at - timedelta(hours=1)).isoformat(), 'end': (at + timedelta(hours=24)).isoformat()}
        if stop():
            raise TimeoutError('Activity acquisition deadline exceeded')
        return fields, windows, notices, resolutions

    def native_times(self, focus, end, reference, stop):
        """Issued inventory only. Weather and Kp keep their own native gaps."""
        stamps, steps, notices = set(), {}, []
        for source in VERDICT_SOURCE_PRECEDENCE[tier(focus.valid_time, reference)]:
            if stop():
                raise TimeoutError('Activity inventory deadline exceeded')
            try:
                coordinator = self.factories()[source]()
                values = coordinator.timeline_times(focus.valid_time)
                if source == 'noaa-gfs':
                    values, _ = values
                ordered = sorted(set(values))
                selected = [value for value in ordered if focus.valid_time <= value < end]
                stamps.update(selected)
                if selected:
                    steps[source] = 3600 if tier(focus.valid_time, reference) == 'core' else coordinator.native_resolution_seconds(focus.valid_time, end)
            except Exception:
                notices.append(f'{source}: native inventory unavailable')
        try:
            from ..swpc_kp_query import swpc_kp_query_service
            observed, forecast = swpc_kp_query_service().series(focus.valid_time)
            series = observed if focus.valid_time <= reference else forecast
            if series.available:
                stamps.update(row.time for row in series.readings if focus.valid_time <= row.time < end)
                steps['noaa-swpc-kp'] = 10800
        except Exception:
            notices.append('Kp native inventory unavailable')
        if not steps:
            return [], None, notices + ['Native resolution unavailable']
        # Base alignment is hourly; each planning profile receives its coarsest
        # driving source step. Missing files never alter the declared cadence.
        return sorted(stamp for stamp in stamps if stamp.timestamp() % 3600 == 0), steps, notices
