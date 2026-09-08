"""Source-local GEFS point capability proposal; registration is separate.

The bounded selected-lead reader publishes members, not provider reductions.
No complete native timeline or separately selectable previous run is proved.
"""
from registry import fields as catalogue
from ingest.derive.registry import ENSEMBLE_MEAN, ENSEMBLE_SPREAD

from .gefs_query import GEFS_FIELDS, declared_members
from .source_contract import SourceCapability, SourceVariant


def point_capabilities() -> tuple[SourceCapability, ...]:
    """Describe implemented unparameterized point identities without I/O.

    Parameterized quantiles and threshold probabilities remain explicit caller
    choices; this finite declaration does not invent their parameters. Means
    and spreads still apply the existing method-specific eligibility guards.
    """
    return tuple(SourceCapability(
        source_id="noaa-gefs", product_id="pgrb2ap5", field=field,
        variants=[*(SourceVariant(kind="member", member=member) for member in declared_members()),
                  SourceVariant(kind="derived_statistic", statistic=ENSEMBLE_MEAN),
                  SourceVariant(kind="derived_statistic", statistic=ENSEMBLE_SPREAD)],
        levels=[str(catalogue.field(field).level)], point=True, point_product="GEFS",
        native_series=False, run_selection="latest",
        time_semantics=("Selected native lead only; total_cloud_mean_6h retains its provider-labelled "
                        "averaging interval and is not instantaneous cloud"),
        coverage_description=("Bounded Avalon member-family point read; control-index discovery alone "
                              "does not establish member, optional-field or sampled-cell availability"),
    ) for field in GEFS_FIELDS)
