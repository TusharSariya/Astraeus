"""Requestable catalogue axes; stored samples and WMS images stay separate."""
from collections import Counter
from datetime import datetime

from . import wms
from .fixtures import window_start, window_end
from .layer_identity import imagery
from .models import DataMode, LayersResponse


def serving_inventory(response: LayersResponse, reference: datetime) -> LayersResponse:
    start, end = window_start(reference), window_end(reference)
    notices = list(response.notices)
    layers = []
    for layer in response.layers:
        inventory = layer.imagery_availability
        raster_available = layer.raster_available
        # Only the endpoint actually recorded by the artifact is used. The
        # provider's image axis is not the stored GetFeatureInfo sample axis.
        if (response.data_mode == DataMode.LIVE and layer.evidence_basis == wms.PUBLISHED_ARTIFACT
                and layer.upstream_endpoint == 'https://geo.weather.gc.ca/geomet/' and layer.upstream_wms_layer):
            spec = wms.ForecastLayerSpec(layer.id, layer.upstream_wms_layer, layer.field, layer.title, product=layer.product)
            try:
                coverage = wms.forecast_coverage(spec)
            except Exception as error:  # One malformed provider inventory cannot hide other layers.
                coverage = wms.ForecastCoverage(spec, (), 'unknown', None, notice=f'Provider image inventory unavailable: {type(error).__name__}: {error}')
            image_times = [stamp for stamp in coverage.times if start <= stamp <= end]
            reason = coverage.notice or ('Provider GetCapabilities image inventory; these are not stored sample times, and rendering may still fail' if coverage.times else 'Provider capabilities did not advertise a timed image inventory; stored sample timestamps are not image timestamps')
            if coverage.times and not image_times:
                reason += f'; no provider image falls inside the serving window {start.isoformat()}..{end.isoformat()}'
            inventory = imagery('known' if coverage.times else 'unknown', reference, 'provider_capabilities_read', reason, image_times)
            raster_available = bool(image_times)
            if coverage.notice:
                notices.append(f'{layer.id}: {coverage.notice}')
        times = [stamp for stamp in layer.times if start <= stamp <= end]
        frames = [frame for frame in layer.frames if start <= frame.valid_time <= end]
        image_times = [stamp for stamp in inventory.times if start <= stamp <= end]
        excluded = [stamp for stamp in [*layer.times, *(frame.valid_time for frame in layer.frames), *inventory.times] if not start <= stamp <= end]
        if excluded:
            notices.append(f'{layer.id}: excluded frames {min(excluded).isoformat()}..{max(excluded).isoformat()} outside the serving window {start.isoformat()}..{end.isoformat()}; no stored sample or image is substituted')
        if image_times != inventory.times:
            inventory = inventory.model_copy(update={'times': image_times, 'reason': f'{inventory.reason}; image times restricted to the serving window'})
            if inventory.status == 'known' and not image_times:
                raster_available = False
        runs = layer.runs
        if frames != layer.frames:
            counts = Counter(frame.provider_run_id for frame in frames)
            runs = [run.model_copy(update={'frame_count': counts[run.provider_run_id]}) for run in runs if counts[run.provider_run_id]]
        layers.append(layer.model_copy(update={'times': times, 'frames': frames, 'runs': runs,
                     'imagery_availability': inventory, 'raster_available': raster_available}))
    return response.model_copy(update={'layers': layers, 'notices': notices})
