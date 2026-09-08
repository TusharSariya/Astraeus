"""Named OSTIA analysis delivery over the existing bounded native reader."""
from .source_contract import SourceCapability, SourceVariant
from .source_status import observed_read
from .ostia_query import FIELDS


class OSTIASource:
    source_id, product_id = 'metoffice-ostia-sst', 'ostia-foundation-sst-v2'

    def __init__(self, factory):
        self.factory = factory

    def descriptors(self):
        from registry import fields as catalogue
        return tuple(SourceCapability(
            source_id=self.source_id, product_id=self.product_id, field=key,
            variants=[SourceVariant(kind='deterministic')],
            levels=[str(catalogue.field(key).level)], point=True,
            point_product='OSTIA SST', native_series=False, run_selection='not_applicable',
            time_semantics='Exact latest published daily analysis; no forecast run or interpolation',
            coverage_description='Native cells in the fixed coastal evidence box; SST, uncertainty and surface mask retained',
        ) for key in FIELDS)

    @observed_read
    def read_point(self, latitude, longitude, selected, *, run='latest', refresh=False):
        if run != 'latest':
            from .native_runs import RunUnavailable
            raise RunUnavailable('OSTIA analyses have no selectable forecast runs')
        return tuple(self.factory().point_fields(latitude, longitude, selected, refresh=refresh))

    def plan_series(self, start, end, *, run='latest'):
        return None
