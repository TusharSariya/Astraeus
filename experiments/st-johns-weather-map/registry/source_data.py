"""Declarative source inventory for the St. John's weather-map experiment.

The public ``registry()`` function returns fully materialized records conforming
to schema.json.  Compact declarations below intentionally share policy text,
while the emitted record contains every required field.
"""

from __future__ import annotations

import copy
from typing import Any

ECCC_CATALOGUE = "https://eccc-msc.github.io/open-data/msc-data/readme_en/"
ECCC_USAGE = "https://eccc-msc.github.io/open-data/usage/readme_en/"
ECCC_LICENCE = "https://eccc-msc.github.io/open-data/licence/readme_en/"
ECCC_DATAMART = "https://dd.weather.gc.ca/"
ECCC_API = "https://api.weather.gc.ca/"
ECMWF_OPEN = "https://www.ecmwf.int/en/forecasts/datasets/open-data"
ECMWF_ENDPOINT = "https://data.ecmwf.int/forecasts/"

#: Where every reach, run cadence and latency seed below comes from. Nothing
#: here is a producer commitment: the latency numbers are three live
#: measurements taken on 2026-09-02 and recorded in that file, and they are
#: seeds for the worker's estimator, which re-measures them.
HORIZON_MATRIX = "docs/research/wayfinder/planning-horizon-matrix.md"
LATENCY_SEED_BASIS = f"seed: {HORIZON_MATRIX}, 2026-09-02"

#: Publication-latency seeds, in seconds after run time, from the matrix.
ICON_LATENCY_SECONDS = 12600  # final lead of the 00z run at T+3 h 32 m
GFS_LATENCY_SECONDS = 19080  # 00z f384 at T+5 h 18 m
ECMWF_LATENCY_SECONDS = 27360  # IFS/ENS/AIFS-ENS 360 h index at T+7 h 36 m

RUN_CADENCE_4X_DAILY = 21600
RUN_CADENCE_2X_DAILY = 43200

#: The dated WXO-DD layout `ingest/adapters/eccc_datamart.py` documents and
#: walks: `today/model_hrdps/` is empty and its `continental/2.5km` child is a
#: 404, so the working path is `/{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/`. The
#: model and resolution segments are the adapter's own `model_subpath` values.
DATAMART_FALLBACK = {
    "eccc-hrdps": f"{ECCC_DATAMART}{{YYYYMMDD}}/WXO-DD/model_hrdps/continental/2.5km/{{HH}}/{{FFF}}/",
    "eccc-rdps": f"{ECCC_DATAMART}{{YYYYMMDD}}/WXO-DD/model_rdps/10km/{{HH}}/{{FFF}}/",
    "eccc-gdps": f"{ECCC_DATAMART}{{YYYYMMDD}}/WXO-DD/model_gdps/10km/{{HH}}/{{FFF}}/",
}


def _reach(earliest_hours: float, latest_hours: float, per_cycle: dict[str, float] | None = None) -> dict[str, Any]:
    """Earliest and latest valid time a run can cover, relative to its run time.

    ``per_cycle`` states the latest hour by UTC run hour where the cycles
    differ, which is not a corner case: IFS and IFS ENS reach 360 h at 00z and
    12z and 144 h at 06z and 18z, so a record's single longest reach would
    promise nine days of coverage on a run that never had it.
    """
    reach: dict[str, Any] = {"earliest_hours": earliest_hours, "latest_hours": latest_hours}
    if per_cycle is not None:
        reach["per_cycle"] = per_cycle
    return reach


#: An observation covers its own instant and nothing else.
#:
#: Carried by radar and lightning as well, because what those adapters retrieve
#: is the observed composite and the observed flash density
#: (`ingest.registry.VARIABLE_OVERRIDES`), not the extrapolation products the
#: records also catalogue. If an extrapolation collection is ever retrieved,
#: that record states its own forward reach then, not now.
#:
#: CAP alerts carry it too. An alert is not a frame and covers no valid time:
#: its own validity interval travels inside each message and is read from
#: there. A reach of 0..0 says exactly that - the alert layer answers "what is
#: in force now", and nothing in the layer answers a future instant.
OBSERVED_INSTANT = _reach(0, 0)


def _latency(estimate_seconds: int | None, basis: str) -> dict[str, Any]:
    """A publication latency this deployment has not yet observed.

    Every record starts here: ``measured`` is false and the observation count
    is zero, because a research measurement made against someone else's clock
    on one day is not this deployment's measurement. The worker sets
    ``measured`` and ``last_observed`` only after it has watched a run appear.
    """
    return {
        "estimate_seconds": estimate_seconds,
        "observation_count": 0,
        "last_observed": None,
        "measured": False,
        "basis": basis,
    }


#: No seed and no observation: scheduling falls back to the run time itself
#: rather than to a guessed offset.
NO_LATENCY = _latency(None, "none")

#: GEPS is the one record whose earliest reach is not the run hour. Its 12z
#: run advertised `2026-09-01T15Z/2026-09-17T12Z/PT3H` on GeoMet (verified live
#: 2026-09-02, planning-horizon matrix), so its first published step is +3 h
#: and it covers nothing at all at the run instant. Declaring 0 here would
#: promise an analysis hour that the reduction set does not contain.
GEPS_REACH = _reach(3, 384)

ECCC_POLICY = {
    "licence": {"name": "MSC Open Data licence", "url": ECCC_LICENCE, "review_state": "verified"},
    "attribution": "Credit Environment and Climate Change Canada; preserve producer, product, run/valid time and supplied notices.",
    "caching": "Cache only within the 25 GiB experiment cap; retain the latest and previous complete model run or at least three observation hours.",
    "archival": "Immutable downloaded artifact plus seven days of run/status metadata; no claim of a permanent provider archive.",
    "redistribution": "Redistribution permitted subject to the MSC Open Data licence, attribution and no-warranty terms.",
}

OPEN_US_POLICY = {
    "licence": {"name": "United States government public data; product-specific terms still apply", "url": "https://www.noaa.gov/information-technology/open-data-dissemination", "review_state": "verified"},
    "attribution": "Credit NOAA and the named NOAA product office; preserve native metadata and quality flags.",
    "caching": "Cache bounded Avalon/Grand Banks subsets within the experiment cap.",
    "archival": "Retain immutable source artifacts locally only for the experiment retention window.",
    "redistribution": "May be redistributed, but NOAA attribution, disclaimers and any embedded third-party restrictions must remain.",
}


#: The 21 record ids a registered adapter claims, as
#: ``registry.audit.adapter_source_ids()`` returned them on 2026-09-02. It is
#: written out here rather than imported because ``audit`` reads this module
#: and not the other way round, and it is data rather than prose because
#: Decision 1 of the source-admissions ledger splits the old ``implementing``
#: population on exactly this membership: an adapter claims the id, the
#: integration is not ``link_only``, and the fixture suite passes. All 21 have
#: passing fixture suites under ``api/tests/test_adapter_*.py``.
ADAPTER_BACKED_IDS: frozenset[str] = frozenset(
    {
        "awc-metar-speci",
        "awc-taf",
        "dwd-icon-global",
        "eccc-aqhi",
        "eccc-cap-alerts",
        "eccc-gdps",
        "eccc-hrdps",
        "eccc-lightning",
        "eccc-radar",
        "eccc-rdps",
        "eccc-reps",
        "eccc-swob",
        "ecmwf-aifs-ens",
        "ecmwf-ens",
        "ecmwf-ifs",
        "noaa-gefs",
        "noaa-gfs",
        "noaa-goes-east",
        "noaa-swpc-kp",
        "noaa-swpc-ovation",
        "noaa-swpc-rtsw",
    }
)

#: Appended to the reason of every record the 2026-09-02 migration moved to
#: ``catalogued``. The sentence is there so that a reader of the record alone
#: can tell the two kinds of catalogue entry apart: one that was never admitted,
#: and one that the resolutions admitted and that is waiting for an adapter.
CATALOGUED_UNTIL_ADAPTER = (
    " Catalogued until a registered adapter claims the id; admission by the "
    "2026-09-02 resolutions is a ceiling, not a fetch."
)


def _admission(id: str, reason: str) -> tuple[str, str]:
    """The state and the reason ``_source`` takes at positions three and four.

    Decision 1 of the source-admissions ledger is an objective test, so it is
    applied here once rather than transcribed onto fifty records by hand: a
    record whose id a registered adapter claims is ``implemented-unverified``,
    and every other declaration is a ``catalogued`` one whose reason says so.
    The existing reason is never rewritten, only extended, because the reason
    records why the source was admitted and the migration did not change that.
    """
    if id in ADAPTER_BACKED_IDS:
        return "implemented-unverified", reason
    return "catalogued", reason + CATALOGUED_UNTIL_ADAPTER


def _source(
    id: str,
    category: str,
    status: str,
    reason: str,
    producer: str,
    product: str,
    docs: list[str],
    endpoints: list[str],
    integration: tuple[str, str],
    names: list[str],
    levels: list[str],
    coverage: str,
    cadence: str,
    horizon: str,
    authentication: tuple[bool, str, str | None],
    policy: dict[str, Any],
    schema_version: str,
    freshness: str,
    role: str,
    consensus: tuple[bool, str | None, str],
    fixture: str | None = None,
    live: str = "planned",
    *,
    delivery_kind: str,
    intermediary: dict[str, Any] | None = None,
    field_delivery_kinds: dict[str, str] | None = None,
    display_primary: bool | None = None,
    reach: dict[str, Any] | None = None,
    run_cadence_seconds: int | None = None,
    native_cadence_seconds: int | None = None,
    publication_latency: dict[str, Any] | None = None,
    datamart_fallback_path: str | None = None,
    credential: dict[str, Any] | None = None,
    restricted_terms: dict[str, Any] | None = None,
    admission_condition: dict[str, Any] | None = None,
    superseded_by: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``delivery_kind`` is keyword-only and has no default, deliberately.

    A value whose provenance cannot say whether it is the producer's own cell
    is not evidence anyone can weigh, so every record states how its values
    reach this deployment: ``published_cell`` (the producer's own grid or
    observation, retrieved from the producer or from a mirror that copies it
    byte for byte), ``reprocessed`` (an intermediary transformed the
    producer's field first) or ``intermediary_derived`` (an intermediary
    computed a value the producer never published). A default would let the
    next aggregator record inherit ``published_cell`` in silence, which is the
    exact failure the declaration exists to prevent.

    ``display_primary`` follows from the kind unless a record overrides it: a
    value that is not the producer's own cell is never what the map shows
    first. The audit enforces that rather than leaving it to the display
    layer.

    The five horizon fields (``reach``, ``run_cadence_seconds``,
    ``native_cadence_seconds``, ``publication_latency``,
    ``datamart_fallback_path``) are keyword-only and default to ``None``,
    which emits nothing. Absent means absent: a record that has not stated how
    far it reaches must not inherit a reach, and a latency nobody measured
    must not acquire a number by falling through a default. The audit requires
    them where a registered adapter exists, and refuses a latency estimate
    that carries no basis.

    ``fixture`` defaults to ``None``, which resolves to ``"passing"`` for a
    record in ``ADAPTER_BACKED_IDS`` and ``"planned"`` for every other. A
    record that states its own fixture status keeps it: a blocked or
    not-applicable suite is a fact about the record, not about the adapter set.

    The four admission blocks (``credential``, ``restricted_terms``,
    ``admission_condition``, ``superseded_by``) are keyword-only and default to
    ``None``, which emits nothing, on the same rule as the horizon fields:
    absent means absent. Each is emitted verbatim when given. ``credential``
    names the environment variable and the registration page and never a value;
    ``restricted_terms`` carries the verbatim clause that admits the source for
    research use only; ``admission_condition`` says what is outstanding before
    the record may be scheduled; ``superseded_by`` names the record a reader
    should look at instead.
    """
    record: dict[str, Any] = {
        "id": id,
        "category": category,
        "status": status,
        "reason": reason,
        "producer": producer,
        "product": product,
        "documentation_urls": docs,
        "access_endpoints": endpoints,
        "integration": {
            "kind": integration[0],
            "client": integration[1],
            "metadata_contract": "Must expose producer/product, retrieval/run/valid time, member, level, native units/CRS/resolution, QC and source metadata.",
        },
        "variables": [{"names": names, "levels": levels}],
        "coverage": coverage,
        "cadence": cadence,
        "forecast_horizon": horizon,
        "authentication": {"required": authentication[0], "mechanism": authentication[1], "registration_url": authentication[2]},
        "licence": policy["licence"],
        "attribution": policy["attribution"],
        "caching": policy["caching"],
        "archival": policy["archival"],
        "redistribution": policy["redistribution"],
        "schema_version": schema_version,
        "freshness_threshold": freshness,
        "poc_role": role,
        "consensus": {"eligible": consensus[0], "family": consensus[1], "reason": consensus[2]},
        "fixture_status": ("passing" if id in ADAPTER_BACKED_IDS else "planned") if fixture is None else fixture,
        "live_smoke_test_status": live,
    }
    record["delivery_kind"] = delivery_kind
    record["display_primary"] = (delivery_kind == "published_cell") if display_primary is None else display_primary
    if intermediary is not None:
        record["intermediary"] = intermediary
    if field_delivery_kinds is not None:
        record["field_delivery_kinds"] = field_delivery_kinds
    if reach is not None:
        record["reach"] = reach
    if run_cadence_seconds is not None:
        record["run_cadence_seconds"] = run_cadence_seconds
    if native_cadence_seconds is not None:
        record["native_cadence_seconds"] = native_cadence_seconds
    if publication_latency is not None:
        record["publication_latency"] = publication_latency
    if datamart_fallback_path is not None:
        record["datamart_fallback_path"] = datamart_fallback_path
    if credential is not None:
        record["credential"] = credential
    if restricted_terms is not None:
        record["restricted_terms"] = restricted_terms
    if admission_condition is not None:
        record["admission_condition"] = admission_condition
    if superseded_by is not None:
        record["superseded_by"] = superseded_by
    return record


def _eccc_model(id: str, category: str, product: str, doc_slug: str, names: list[str], levels: list[str], cadence: str, horizon: str, role: str, eligible: bool, family: str = "ECCC", endpoints: list[str] | None = None, reason: str | None = None, status: str | None = None, fixture: str | None = None, live: str = "planned", integration: tuple[str, str] | None = None, reason_suffix: str | None = None, **horizon_fields: Any) -> dict[str, Any]:
    """``category`` is stated per record rather than guessed from the product name.

    Inferring it from ``"EPS" not in product`` typed CIOPS-East (ocean), the wave
    and surge systems, the precipitation *analyses* and the land-surface systems
    all as ``deterministic_forecast``. That is not cosmetic:
    ``api.weather_api.store._consensus_candidates`` derives consensus
    eligibility and family from ``category``, so an ocean model was eligible to
    vote on air temperature.

    ``endpoints`` and ``reason`` override the Datamart defaults for a product
    that is not on the open HTTP tree. Every ECCC model is assumed to live at
    ``dd.weather.gc.ca/today/model_<name>/``; GEPS and REPS no longer do, and a
    default that 404s is worse than no default because it reads as verified.
    ``endpoints=[]`` is honoured as an explicit empty list (a record with no
    access path), distinct from the omitted default.

    ``status`` overrides the objective ``_admission`` test for a record the
    owner has explicitly rejected or moved to an absence state; when given,
    ``reason`` is used verbatim rather than run through ``_admission``.
    ``fixture`` and ``live`` override the state's own fixture/live test
    status for a terminal record. ``integration`` overrides the default
    official-SDK tuple for a record with no access path.

    ``horizon_fields`` forwards the keyword-only reach, cadence, latency,
    Datamart-fallback and admission-block arguments of ``_source`` unchanged;
    nothing is defaulted here, so a model that states none of them emits none
    of them.
    """
    document_name = doc_slug.removeprefix("nwp_")
    endpoint_path = {"caldas-nsrps": "model_nsrps-caldas", "nowcasting": "nowcasting/matrices"}.get(document_name, f"model_{document_name}")
    if status is not None:
        state, final_reason = status, reason
    else:
        state, final_reason = _admission(id, reason or "Official product is catalogued; ingestion and fixture/live tests are not implemented yet.")
    if reason_suffix:
        final_reason = final_reason + reason_suffix
    final_endpoints = endpoints if endpoints is not None else [f"{ECCC_DATAMART}today/{endpoint_path}/"]
    final_integration = integration or ("official_sdk", "MetPX Sarracenia for ECCC AMQP discovery/distribution; ecCodes + cfgrib + xarray for official GRIB2/NetCDF")
    return _source(id, category, state, final_reason, "Environment and Climate Change Canada", product, [f"https://eccc-msc.github.io/open-data/msc-data/{doc_slug}/readme_{document_name}_en/", ECCC_CATALOGUE], final_endpoints, final_integration, names, levels, "Published native domain; crop high-resolution data to Avalon and retain coarser Grand Banks context.", cadence, horizon, (False, "Anonymous HTTPS/AMQP", None), ECCC_POLICY, "Official product definition as documented by ECCC; pin discovered GRIB2/NetCDF templates before activation", "newest complete run no older than two nominal cycles", role, (eligible, family if eligible else None, "One representative from the ECCC centre may vote only for semantically comparable raw-model fields." if eligible else "Analysis, post-processing, or non-comparable product; source-specific display only."), fixture, live, delivery_kind="published_cell", **horizon_fields)


#: Where every ensemble number below was measured: one file, one ticket
#: (wayfinder #22, 2026-09-02). A family declares this path as its evidence, or
#: declares ``"none"`` and is unverified. Nothing here is a producer promise.
ENSEMBLE_EVIDENCE = "docs/research/wayfinder/ensemble-access.md"

#: The owner's admission order for the six ensemble families, as source ids.
#: Declared here rather than left an implementation convention, so a partial
#: build is a prefix of this tuple and a reader of the catalogue alone can tell
#: which families are expected to exist yet.
ENSEMBLE_BUILD_ORDER: tuple[str, ...] = (
    "eccc-reps",
    "ecmwf-aifs-ens",
    "ecmwf-ens",
    "noaa-gefs",
    "eccc-geps",
    "dwd-icon-eps",
)

#: The four reduction shapes a provider may publish instead of members. Listed
#: on a ``reduction``-shaped record only: a member-publishing family's own
#: provider reductions are retrieved evidence of a different product, and are
#: never mixed with a statistic over its member set.
PROVIDER_REDUCTIONS = ("mean", "spread", "percentile", "threshold_probability")


def _control(identifier: str | None, rule: str, separate_retrieval: bool) -> dict[str, Any]:
    """How one family identifies its control member, as a flag on the member axis.

    ``identifier`` is the provider's own token (``gec00``, the GRIB ``number``
    ``"0"``) and is null only where the family publishes members and no
    measurement identifies which of them is the control. A null identifier is
    not the same as a null ``control`` block: the block being null means the
    family publishes no members and so has no control to declare (GEPS), while
    a null identifier means the control exists and has not been located, which
    is a reason not to schedule the family rather than a licence to promote a
    perturbed member into its place.
    """
    return {"identifier": identifier, "rule": rule, "separate_retrieval": separate_retrieval}


def _verification(member_count: str, access_path: str, cadence: str, evidence: str) -> dict[str, Any]:
    """What was measured about a family, and where the measurement is written down.

    Each field is ``verified`` or ``unverified``; a family carrying any
    ``unverified`` field is not schedulable, because a member count that was
    assumed cannot be used to check completeness and an access path that was
    assumed cannot be retried.
    """
    return {"member_count": member_count, "access_path": access_path, "cadence": cadence, "evidence": evidence}


def _ensemble(
    *,
    family: str,
    build_order: int,
    shape: str,
    subsetting: str,
    storage_scope: str,
    member_count: int | None,
    control: dict[str, Any] | None,
    reductions: tuple[str, ...],
    gaps: tuple[dict[str, str], ...],
    verification: dict[str, Any],
    schedulable: bool,
    schedulable_reason: str,
) -> dict[str, Any]:
    """One ensemble family declaration, in the shape the schema validates.

    ``subsetting`` and ``storage_scope`` reuse the exact values
    ``registry/fields.py`` ``SOURCE_SCOPE`` already declares for the same source
    ids, so the storage scope follows from the access shape in one place rather
    than being judged twice.
    """
    return {
        "family": family,
        "build_order": build_order,
        "shape": shape,
        "subsetting": subsetting,
        "storage_scope": storage_scope,
        "member_count": member_count,
        "control": control,
        "reductions": list(reductions),
        "gaps": [dict(gap) for gap in gaps],
        "verification": verification,
        "schedulable": schedulable,
        "schedulable_reason": schedulable_reason,
    }


#: The six admitted ensemble families, keyed by source id. Every number and
#: every access shape below is one measurement in ``ENSEMBLE_EVIDENCE``, and a
#: family declares ``unverified`` wherever there is no measurement to name.
#: All six are ``schedulable: false``: nothing is scheduled by this change, an
#: unverified field makes a family unschedulable on its own, and the four
#: families that cannot subset server side additionally wait on the owner's
#: acceptance of their upstream cost.
ENSEMBLE_DECLARATIONS: dict[str, dict[str, Any]] = {
    "eccc-reps": _ensemble(
        family="REPS",
        build_order=1,
        shape="members",
        subsetting="server_side",
        storage_scope="every_published_field",
        member_count=21,
        control=_control(
            None,
            "GeoMet publishes the members as REPS.MEM.<VAR>.01 through .21 and distinguishes no "
            "coverage as the control: the 1239 member coverages enumerated on 2026-09-02 carry no "
            "control label and no ECCC field definition read for this ticket names one. The "
            "control is therefore not identified, no member stands in for it, and the family is "
            "not schedulable until the identification rule is measured against the source GRIB.",
            False,
        ),
        reductions=(),
        gaps=(
            {
                "field": "wind_direction_10m",
                "reason": "REPS publishes WSPD on its members and no ETA_UU or ETA_VV on any "
                          "member, so member wind direction is not retrievable. It is not derived "
                          "from the speed, not borrowed from a neighbouring model and not taken "
                          "from the REPS provider reductions; the field stays null with this "
                          "reason.",
            },
        ),
        verification=_verification("verified", "verified", "unverified", ENSEMBLE_EVIDENCE),
        schedulable=False,
        schedulable_reason=(
            "21 members and the GeoMet WCS GetCoverage path are verified live (40 224 bytes per "
            "member field per lead, already subset to the box), but the run cycles and lead set "
            "are cited from ECCC documentation and were never enumerated, and GeoMet names no "
            "control among the 21 coverages. An unverified cadence and an unidentified control "
            "each make the family unschedulable on their own. Nothing is scheduled by this change."
        ),
    ),
    "ecmwf-aifs-ens": _ensemble(
        family="AIFS-ENS",
        build_order=2,
        shape="members",
        subsetting="none",
        storage_scope="family_fields_only",
        member_count=51,
        control=_control(
            "0",
            "The GRIB number as a string: 0 is the cf control and 1 through 50 the pf members. "
            "The control arrives in its own <stamp>-<L>h-enfo-cf.grib2 file beside the pf file "
            "holding all 50 perturbed members. That is an access-shape difference and not an "
            "identity difference: two files, one member axis of 51, and a run whose cf file is "
            "absent is partial with the control named as the missing member.",
            True,
        ),
        reductions=(),
        gaps=(),
        verification=_verification("verified", "verified", "verified", ENSEMBLE_EVIDENCE),
        schedulable=False,
        schedulable_reason=(
            "Members, access path and cadence are all verified live, and AIFS-ENS is the only "
            "admitted family publishing per-member layered cloud. It still cannot subset server "
            "side: about 72 MB on the wire per lead for one field across 51 members, to store "
            "about 4.5 KB per member. Scheduling waits on the owner's acceptance of that upstream "
            "cost, and nothing is scheduled by this change."
        ),
    ),
    "ecmwf-ens": _ensemble(
        family="IFS ENS",
        build_order=3,
        shape="members",
        subsetting="none",
        storage_scope="family_fields_only",
        member_count=51,
        control=_control(
            "0",
            "The GRIB number as a string: 0 is the cf control and 1 through 50 the pf members. "
            "The f024 enfo-ef file measured on 2026-09-02 carried type=pf number 1 to 50 and no "
            "cf record, so where the control is published in the ifs/0p25/enfo layout is "
            "unverified. separate_retrieval is declared false because no second file was found, "
            "not because a second file was ruled out; the declared count of 51 rests on a control "
            "nobody has located, which is why the member count is declared unverified too.",
            False,
        ),
        reductions=(),
        gaps=(
            {
                "field": "cloud_low",
                "reason": "The IFS ENS open-data set publishes whole-column tcc and no lcc, mcc "
                          "or hcc on any member. Not a storage-scope exclusion: the producer does "
                          "not publish the field for this family.",
            },
            {
                "field": "cloud_middle",
                "reason": "As cloud_low: no layered cloud is published on any IFS ENS member.",
            },
            {
                "field": "cloud_high",
                "reason": "As cloud_low: no layered cloud is published on any IFS ENS member.",
            },
        ),
        verification=_verification("unverified", "unverified", "unverified", ENSEMBLE_EVIDENCE),
        schedulable=False,
        schedulable_reason=(
            "50 pf members, the byte-range access path and the 00z lead set are verified live, but "
            "the control's file was never located, so neither the count of 51 nor the retrieval "
            "path for the whole member axis is established, and 06z/18z coverage was not listed. "
            "IFS ENS also cannot subset server side: about 29 MB on the wire per lead for one "
            "field across 51 members. Both the unverified fields and the owner's cost acceptance "
            "stand between this family and a schedule."
        ),
    ),
    "noaa-gefs": _ensemble(
        family="GEFS",
        build_order=4,
        shape="members",
        subsetting="none",
        storage_scope="family_fields_only",
        member_count=31,
        control=_control(
            "gec00",
            "The member token in the S3 object name: gec00 is the control, self-labelled "
            "ENS=low-res ctl, beside the perturbed gep01 through gep30, and the expected count of "
            "31 includes it. separate_retrieval is false because every GEFS member, the control "
            "included, is already its own file: the control needs no retrieval step the perturbed "
            "members do not, which is the difference the flag exists to record (contrast "
            "AIFS-ENS, whose one pf file holds all 50 perturbed members and whose control needs a "
            "second request).",
            False,
        ),
        reductions=(),
        gaps=(
            {
                "field": "total_cloud_geometric",
                "reason": "GEFS publishes no instantaneous total-cloud column at any lead in any "
                          "product set: TCDC:entire atmosphere is a 3 h or 6 h mean, confirmed at "
                          "the GRIB2 level, and is stored under total_cloud_mean_6h instead. The "
                          "only instantaneous cloud records are TCDC:475 mb (a single isobaric "
                          "level), TCDC:convective cloud layer, HGT:cloud ceiling and "
                          "CWAT:entire atmosphere, none of which is the column quantity, so the "
                          "column field stays absent rather than being filled from one of them.",
            },
        ),
        verification=_verification("verified", "verified", "verified", ENSEMBLE_EVIDENCE),
        schedulable=False,
        schedulable_reason=(
            "31 members, the .idx byte-range path and the four-cycle 3-hourly-to-f240 lead set are "
            "verified live. GEFS cannot subset server side: about 7.7 MB on the wire per lead for "
            "one 0.5 degree field across 31 members, to store about 1.2 KB per member. Scheduling "
            "waits on the owner's acceptance of that upstream cost, and nothing is scheduled by "
            "this change."
        ),
    ),
    "eccc-geps": _ensemble(
        family="GEPS reductions",
        build_order=5,
        shape="reduction",
        subsetting="server_side",
        storage_scope="every_published_field",
        member_count=None,
        control=None,
        reductions=PROVIDER_REDUCTIONS,
        gaps=(),
        verification=_verification("verified", "verified", "verified", ENSEMBLE_EVIDENCE),
        schedulable=False,
        schedulable_reason=(
            "GEPS publishes no members at all: zero GEPS.MEM.* coverages exist and all 532 "
            "coverages are the provider's own reduction (ERMEAN, ERSSTD, percentiles ERC0 to "
            "ERC100, threshold probabilities), which is a measurement and not an omission. The "
            "GeoMet path is verified and its 12z run advertised a 3-hourly interval to 384 h live "
            "on 2026-09-02 (docs/research/wayfinder/planning-horizon-matrix.md). It is still not "
            "schedulable here because nothing is scheduled by this change: the adapters and the "
            "derivation entries its reductions are served beside land later. Those reductions are "
            "retrieved evidence, stored as issued, never recomputed and never combined with a "
            "statistic over another member set."
        ),
    ),
    "dwd-icon-eps": _ensemble(
        family="ICON-EPS",
        build_order=6,
        shape="members",
        subsetting="none",
        storage_scope="family_fields_only",
        member_count=None,
        control=_control(
            None,
            "Nothing about ICON-EPS was measured on wayfinder ticket 22, so no control identifier, "
            "no member numbering and no retrieval shape is known. separate_retrieval is false "
            "because a boolean must carry a value, not because a single-file retrieval was "
            "observed; no code may rely on it while the family is unschedulable, and the rule is "
            "rewritten from the measurement rather than confirmed by it.",
            False,
        ),
        reductions=(),
        gaps=(),
        verification=_verification("unverified", "unverified", "unverified", "none"),
        schedulable=False,
        schedulable_reason=(
            "Nothing was measured: no member count, no access path, no cadence, no field list and "
            "no size figure. The record exists so that the sixth family in the owner's build order "
            "is a registry fact rather than an implementation convention, and so that the "
            "catalogue can say the family is unmeasured instead of showing an empty family as "
            "though it were awaiting a run. It declares no member count at all rather than "
            "inheriting one from another centre's EPS, because a count that was assumed cannot be "
            "used to check completeness. Measurement order is the owner's decision."
        ),
    ),
}


def ensemble_families() -> list[dict[str, Any]]:
    """The six ensemble declarations, in the owner's build order.

    Deep copies, so a reader cannot edit the registry by holding a block.
    """
    return [
        copy.deepcopy(ENSEMBLE_DECLARATIONS[source_id])
        for source_id in sorted(ENSEMBLE_BUILD_ORDER, key=lambda sid: ENSEMBLE_DECLARATIONS[sid]["build_order"])
    ]


#: The six transformations Open-Meteo documents applying to every value it
#: serves (`docs/research/wayfinder/aggregator-models.md` section 4, read
#: 2026-09-02). Any record that declares an Open-Meteo delivery `reprocessed`
#: has to name all six, so they are written once here rather than transcribed
#: onto each record, where one of them would eventually go missing.
OPEN_METEO_TRANSFORMATIONS: tuple[str, ...] = (
    "Regridding off the producer's native grid onto Open-Meteo's own grid.",
    "Statistical elevation downscaling against a 90 m digital elevation model, on by default.",
    "Grid-cell selection by Open-Meteo's own policy (cell_selection=land|sea|nearest).",
    "Temporal interpolation to the finest step Open-Meteo offers, finer than the producer's own output step.",
    "Derivation of fields the producer never published, including every cloud field and relative humidity.",
    "Accumulation redistribution of 6-hourly totals across finer steps.",
)

#: The refusal that applies to every Open-Meteo record, appended to each reason
#: so a reader of one record alone knows the aggregator's default routing is not
#: admissible here.
OPEN_METEO_BEST_MATCH_REFUSAL = (
    " Anything reachable only through best_match is refused: it names no producer."
)

OPEN_METEO_TERMS = "https://open-meteo.com/en/terms"

#: Where the Open-Meteo findings below were measured. Cited by path in the
#: reasons, because the research is non-normative and a reason that cannot be
#: traced back to a measurement is an assertion.
AGGREGATOR_RESEARCH = "docs/research/wayfinder/aggregator-models.md"
ENDPOINT_RESEARCH = "docs/research/wayfinder/open-meteo-endpoints.md"


def _open_meteo_intermediary(method: str, extra: tuple[str, ...] = ()) -> dict[str, Any]:
    """The intermediary block every Open-Meteo `reprocessed` record carries.

    ``method`` is the one sentence that says what Open-Meteo did to this
    particular product; ``extra`` adds the record-specific transformations that
    the six documented ones do not cover, such as the CAMS upsample or the
    mandatory sea cell selection.
    """
    return {
        "name": "Open-Meteo",
        "method": method,
        "transformations": list(OPEN_METEO_TRANSFORMATIONS) + list(extra),
    }


def _open_meteo_policy(
    producer_attribution: str,
    *,
    licence_name: str | None = None,
    licence_url: str = OPEN_METEO_TERMS,
    review_state: str = "verified",
    redistribution: str | None = None,
) -> dict[str, Any]:
    """CC BY 4.0 from Open-Meteo, with the producer's own terms still upstream.

    Open-Meteo's licence page states the API data is CC BY 4.0 and requires the
    attribution link beside any displayed value, and it also records that the
    upstream licences are not uniform (UK Met Office is CC BY-SA). So the
    producer's attribution is carried in addition, never instead.
    """
    return {
        "licence": {
            "name": licence_name
            or "Open-Meteo API data under CC BY 4.0; the producer's own upstream terms apply in addition, and the free tier is non-commercial use only",
            "url": licence_url,
            "review_state": review_state,
        },
        "attribution": "Weather data by Open-Meteo.com, linked beside every displayed value as CC BY 4.0 requires; "
        + producer_attribution,
        "caching": "Cache point series only, inside the 25 GiB experiment cap, with the run stamp read from data/<domain>/static/meta.json beside every call.",
        "archival": "Retain the immutable JSON response and its meta.json run stamp for the experiment retention window only.",
        "redistribution": redistribution
        or "Redistribution under CC BY 4.0 with the Open-Meteo link and the producer's own attribution preserved; the free tier is non-commercial use only.",
    }


BRIGHT_SKY_POLICY = {
    "licence": {"name": "DWD open data (GeoNutzV) upstream; Bright Sky serves it from MIT-licensed code and adds no terms of its own", "url": "https://brightsky.dev/", "review_state": "verified"},
    "attribution": "Credit Deutscher Wetterdienst as the producer of MOSMIX and Bright Sky as the intermediary on every value.",
    "caching": "Cache the station 71801 point series only, inside the 25 GiB experiment cap.",
    "archival": "Retain the immutable JSON response for the experiment retention window only.",
    "redistribution": "Permitted under the DWD open-data terms with attribution to Deutscher Wetterdienst preserved.",
}


def registry() -> dict[str, Any]:
    s: list[dict[str, Any]] = []
    # Canadian NWP, analyses, nowcasting, land and ocean systems.
    s.extend([
        _eccc_model("eccc-hrdps", "deterministic_forecast", "HRDPS raw", "nwp_hrdps", ["air_temperature", "relative_humidity", "specific_humidity", "dew_point", "wind_u", "wind_v", "gust", "mean_sea_level_pressure", "precipitation_rate", "precipitation_accumulation", "precipitation_type", "total_cloud", "low_cloud", "middle_cloud", "high_cloud", "visibility", "cloud_base", "CAPE", "CIN", "boundary_layer_height", "vertical_velocity", "cloud_liquid_water", "cloud_ice", "soil_temperature", "soil_moisture", "snow_depth", "surface_fluxes"], ["surface", "2 m", "10 m", "height levels", "isobaric levels through at least 300 hPa", "entire atmosphere column", "soil layers"], "4 runs/day; product-dependent hourly output", "approximately 48 h; use only +24 h in this POC", "Primary high-resolution deterministic forecast and explicit first fallback", True, reach=_reach(0, 48), run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=NO_LATENCY, datamart_fallback_path=DATAMART_FALLBACK["eccc-hrdps"]),
        _eccc_model("eccc-hrdps-weg-prognos", "postprocessed_forecast", "HRDPS Weather Elements on Grid and PROGNOS", "nwp_hrdps", ["statistically_postprocessed_temperature", "wind", "precipitation", "cloud", "weather_elements"], ["surface", "2 m", "10 m"], "Product-dependent", "Short range", "Display as post-processing, never raw HRDPS", False),
        _eccc_model("eccc-rdps", "deterministic_forecast", "RDPS", "nwp_rdps", ["temperature", "dew_point", "relative_humidity", "specific_humidity", "wind", "gust", "pressure", "precipitation", "cloud", "visibility", "CAPE", "CIN", "soil_and_surface_state", "seeing_class_index", "sky_transparency_class_index"], ["surface", "2 m", "10 m", "height", "isobaric", "column", "soil"], "4 runs/day; product-dependent steps", "approximately 84 h", "Regional comparison and explicit second fallback", True, reach=_reach(0, 84), run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=NO_LATENCY, datamart_fallback_path=DATAMART_FALLBACK["eccc-rdps"], reason_suffix=" Includes the ECCC seeing index (RDPS_10km_SeeingIndex) and sky-transparency index (RDPS_10km_SkyTransparencyIndex) admitted by ticket 25 as class-index fields: unlabelled integer classes whose definitions are not published, carried inside the seeing and transparency families whose comparability notes record a fourth incompatible transparency encoding; never converted into any other encoding."),
        _eccc_model("eccc-reps", "ensemble", "REPS all members and control", "nwp_reps", ["temperature", "humidity", "wind", "precipitation", "pressure", "cloud", "threshold_occurrence"], ["surface", "2 m", "10 m", "isobaric", "column", "member and control (21 members, GeoMet REPS.MEM.<VAR>.01-21)"], "4 runs/day; product-dependent steps", "approximately 72 h", "ECCC regional ensemble distributions; retain all members", False, reach=_reach(0, 72), run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=NO_LATENCY, endpoints=["https://geo.weather.gc.ca/geomet/"], reason='Probed 2026-09-02: absent from the open HTTP tree. https://dd.weather.gc.ca/today/model_reps/ and .../today/ensemble/reps/ are 404 on dd.weather.gc.ca and on the hpfx.collab.science.gc.ca mirror, whose ensemble/ tree holds only cansips and doc. Reachable through GeoMet, which publishes 1239 individual member coverages as REPS.MEM.<VAR>.<NN> for members 01-21 in both WMS and WCS, including ETA_TT, ETA_HR, ETA_NT, ETA_PN and ETA_WSPD; there is no ETA_UU or ETA_VV, so members carry wind speed without direction. MetPX Sarracenia over AMQP is the one open route not yet probed.'),
        _eccc_model("eccc-gdps", "deterministic_forecast", "GDPS", "nwp_gdps", ["temperature", "humidity", "wind", "pressure", "precipitation", "cloud", "surface_state"], ["surface", "2 m", "10 m", "isobaric", "column", "soil"], "2 runs/day", "10 days", "Broader Canadian deterministic context", True, reach=_reach(0, 240), run_cadence_seconds=RUN_CADENCE_2X_DAILY, publication_latency=NO_LATENCY, datamart_fallback_path=DATAMART_FALLBACK["eccc-gdps"]),
        _eccc_model("eccc-geps", "ensemble", "GEPS ensemble statistics (no members published openly)", "nwp_geps", ["temperature", "humidity", "wind", "pressure", "precipitation", "cloud", "threshold_occurrence"], ["surface", "2 m", "10 m", "isobaric", "column", "provider reduction only: mean, spread, percentiles, threshold probabilities"], "2 runs/day", "16 days; extended 39-day anomalies twice weekly", "Provider-published ensemble statistics; stored as retrieved, never recomputed here", False, reach=GEPS_REACH, run_cadence_seconds=RUN_CADENCE_2X_DAILY, publication_latency=NO_LATENCY, endpoints=["https://geo.weather.gc.ca/geomet/"], reason="Probed 2026-09-02: absent from the open HTTP tree. https://dd.weather.gc.ca/today/model_geps/ and .../today/ensemble/geps/grib2/ are 404 on dd.weather.gc.ca and on the hpfx.collab.science.gc.ca mirror, and MSC's own product readme still documents the dead path. Reachable through GeoMet, but GeoMet publishes NO GEPS members at all: only the provider's own reduction as GEPS.DIAG.* - ERMEAN, ERSSTD, percentiles ERC0 to ERC100, and threshold probabilities. Store those as retrieved; never recompute them here. MetPX Sarracenia over AMQP is the one open route not yet probed."),
        _eccc_model(
            "eccc-integrated-nowcasting", "nowcasting", "Integrated Nowcasting System", "nwp_nowcasting", ["precipitation_probability", "precipitation_rate", "lightning_probability", "cloud_fraction", "surface_weather_elements"], ["surface forecast points/matrices"], "hourly", "12 h", "Source-specific observation-informed nowcast", False,
            reason="Zero WCS coverages on 2026-09-02; no adapter until a WMS re-probe answers.",
            admission_condition={"condition": "Zero WCS coverages exist for the Integrated Nowcasting System on GeoMet as of 2026-09-02.", "satisfied_by": "A WMS probe recording the available layers and their TIME dimension.", "satisfied": False, "recorded_on": "2026-09-02"},
        ),
        _eccc_model("eccc-hrdpa", "analysis", "HRDPA", "nwp_hrdpa", ["precipitation_accumulation"], ["surface analysis intervals"], "Product-dependent", "analysis, not forecast", "Recent high-resolution precipitation analysis", False),
        _eccc_model("eccc-rdpa", "analysis", "RDPA", "nwp_rdpa", ["precipitation_accumulation"], ["surface analysis intervals"], "Product-dependent", "analysis, not forecast", "Recent regional precipitation analysis", False),
        _eccc_model("eccc-hrepa", "analysis", "HREPA", "nwp_hrepa", ["precipitation_analysis", "analysis_uncertainty", "confidence_index", "25th_percentile", "75th_percentile"], ["6-hour surface accumulation", "24 perturbed members plus control"], "4 analyses/day at 00/06/12/18 UTC", "analysis, not forecast", "Precipitation-analysis uncertainty", False),
        _eccc_model("eccc-hrdlps", "land_surface_forecast", "HRDLPS", "nwp_hrdlps", ["surface_temperature", "soil_temperature", "soil_moisture", "snow_state", "surface_fluxes"], ["surface", "soil layers", "snow layers"], "Product-dependent", "short range", "Land-state evidence", False),
        _eccc_model("eccc-caldas", "analysis", "CaLDAS-NSRPS", "nwp_caldas-nsrps", ["air_temperature", "dew_point", "radiative_surface_temperature", "soil_temperature", "soil_liquid_water_content", "snow_depth", "snow_water_equivalent", "surface_fluxes"], ["surface", "1.5 m", "soil depths 0.025, 0.075, 0.15, 0.3, 0.7, 1.5 and 2.5 m", "snow"], "analyses valid every 3 h at 00/03/06/09/12/15/18/21 UTC; four main launches/day", "analysis, not forecast", "Land-data-assimilation evidence", False),
        _eccc_model("eccc-ciops-east", "ocean", "CIOPS-East", "nwp_ciops", ["sea_surface_temperature", "water_temperature", "salinity", "current_u", "current_v", "mixed_layer_fields", "sea_ice_fields"], ["surface", "ocean depth levels", "water column"], "4 runs/day", "48 h", "Marine/ocean evidence; fields remain separate from atmospheric consensus", False),
        _eccc_model(
            "eccc-riops", "ocean", "RIOPS", "nwp_riops",
            ["sea_water_temperature_RIOPS_VOTEMPER_DBS-0.5m", "current_u", "current_v", "sea_ice_concentration", "sea_ice_thickness"],
            ["0.5 m depth-below-surface", "surface", "ocean depth levels"],
            "Runs every 6 h", "84 h", "Marine/ocean evidence at 5 km; fields remain separate from atmospheric consensus", False,
            endpoints=["https://geo.weather.gc.ca/geomet"],
            reason="https://dd.weather.gc.ca/model_riops/ is 404; the dated WXO-DD path exists at "
            "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_riops/netcdf/forecast/polar_stereographic/{2d,3d}/ "
            "but GeoMet WCS 2.0.1 subsets server side and is the path (docs/research/wayfinder/fog-cloud-line-of-sight-sources.md). "
            "Every field stored at 5 km polar stereographic: sea water temperature at 0.5 m (RIOPS_VOTEMPER_DBS-0.5m), currents and sea ice.",
        ),
        _eccc_model(
            "eccc-rdwps", "wave", "RDWPS", "nwp_rdwps", ["significant_wave_height", "wind_wave_height", "swell_height", "wave_direction", "wave_period"], ["sea surface"], "Product-dependent", "regional wave forecast", "Deterministic wave evidence", False,
            reason="Admitted subject to an Atlantic-domain coverage check over the evidence box (45.0 to 50.5 N, 58.0 to 46.0 W); if the domain does not cover the box the record moves to rejected the way REWPS did.",
            admission_condition={"condition": "Atlantic-domain coverage of the evidence box (45.0 to 50.5 N, 58.0 to 46.0 W) is unverified.", "satisfied_by": "A GeoMet coverage check recorded on the record; moving to rejected the way REWPS did if it fails.", "satisfied": False, "recorded_on": "2026-09-02"},
        ),
        _eccc_model(
            "eccc-gdwps", "wave", "GDWPS", "nwp_gdwps", ["significant_wave_height", "wind_wave_height", "swell_height", "wave_direction", "wave_period"], ["sea surface"], "Product-dependent", "global wave forecast", "Deterministic global wave evidence", False,
            endpoints=["https://geo.weather.gc.ca/geomet"],
            reason="Admitted subject to an Atlantic-domain coverage check over the evidence box (45.0 to 50.5 N, 58.0 to 46.0 W) the same way RDWPS is; if the domain does not cover the box the record moves to rejected as eccc-rewps did.",
            admission_condition={"condition": "Atlantic-domain coverage of the evidence box (45.0 to 50.5 N, 58.0 to 46.0 W) by GDWPS is unverified.", "satisfied_by": "A GeoMet coverage check over the box recorded on the record; if the domain does not cover the box the record moves to rejected as eccc-rewps did.", "satisfied": False, "recorded_on": "2026-09-02"},
        ),
        _eccc_model(
            "eccc-rewps", "wave", "REWPS", "nwp_rewps", ["wave_height", "wave_direction", "wave_period", "ensemble_uncertainty"], ["sea surface", "ensemble member"], "Product-dependent", "regional wave forecast", "Wave ensemble uncertainty", False,
            status="rejected",
            reason="Great Lakes domain only, verified on GeoMet 2026-09-02; no access path.",
            endpoints=[],
            fixture="not_applicable", live="not_applicable",
            integration=("link_only", "No access path; rejected as Great Lakes domain only, verified on GeoMet 2026-09-02."),
        ),
        _eccc_model("eccc-gdsps", "surge", "GDSPS", "nwp_gdsps", ["storm_surge"], ["coastal water-level anomaly"], "Product-dependent", "global surge forecast", "Storm-surge evidence, separate from tides and observed levels", False),
        _eccc_model("eccc-resps", "surge", "RESPS", "nwp_resps", ["storm_surge", "ensemble_uncertainty"], ["coastal water-level anomaly", "ensemble member"], "Product-dependent", "regional surge forecast", "Storm-surge ensemble evidence, separate from tides and levels", False),
    ])

    # ECCC observations, hazards and air quality.
    s.extend([
        _source("eccc-swob", "surface_observation", *_admission("eccc-swob", "Official SWOB-ML feed and v8.16 guide are available; adapter is not yet implemented."), "Environment and Climate Change Canada", "SWOB-ML surface and marine observations", ["https://dd.weather.gc.ca/20260423/WXO-DD/observations/doc/SWOB-ML_Product_User_Guide_v8.16_e.pdf"], [f"{ECCC_DATAMART}observations/swob-ml/"], ("typed_adapter", "httpx + Pydantic XML adapter"), ["air_temperature", "dew_point", "relative_humidity_when_published", "wind", "gust", "pressure", "visibility", "present_weather", "cloud_amount", "cloud_base", "wave_height", "sea_state", "SST", "quality_flags"], ["station surface", "cloud layers", "marine surface"], "Canada; filter CYYT, nearby Avalon stations and official marine platforms", "station-dependent, minute to hourly", "observations only", (False, "Anonymous HTTPS", None), ECCC_POLICY, "SWOB-ML Product User Guide 8.16 / product_generic_swob-xml-2.0", "90 minutes for hourly stations; retain provider cadence metadata", "Primary official surface/humidity observation evidence", (False, None, "Observations do not vote in forecast consensus."), delivery_kind="published_cell", reach=OBSERVED_INSTANT, native_cadence_seconds=3600),
        _source("eccc-radiosonde", "humidity_profile", "unavailable", "The CYYT sounding is gone from Datamart and absent from GeoMet; the served vertical profile is HRDPS and RDPS pressure levels, not an observed sounding. A standing re-probe of Datamart and GeoMet for the CYYT sounding is recorded (docs/research/wayfinder/geomet-wcs-inventory.md).", "Environment and Climate Change Canada", "Upper-air radiosonde observations", [ECCC_CATALOGUE], [], ("raw_protocol", "official TEMP/BUFR protocol decoded with ecCodes"), ["pressure", "temperature", "dew_point", "relative_humidity", "wind_u", "wind_v", "height", "quality_flags"], ["reported mandatory and significant levels from surface through at least 300 hPa"], "Canadian upper-air stations applicable to Newfoundland", "typically 00 and 12 UTC; station-dependent", "observations only", (False, "Anonymous HTTPS", None), ECCC_POLICY, "WMO TEMP/BUFR edition discovered from artifact", "15 h", "Observed vertical humidity and wind profile", (False, None, "Observations do not vote in forecast consensus."), "not_applicable", "not_applicable", delivery_kind="published_cell", admission_condition={"condition": "The CYYT sounding is absent from both Datamart and GeoMet; a standing re-probe of both is outstanding.", "satisfied_by": "The CYYT sounding reappearing on Datamart or GeoMet.", "satisfied": False, "recorded_on": "2026-09-02"}),
        _source("eccc-radar", "radar", *_admission("eccc-radar", "Official composite/rate/type and extrapolation products exist; no-echo semantics must be fixture-tested."), "Environment and Climate Change Canada", "Weather radar composite and extrapolation", ["https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_en/", "https://eccc-msc.github.io/open-data/faq/readme_en/"], ["https://geo.weather.gc.ca/geomet/"], ("raw_protocol", "OWSLib WMS/WCS plus GeoTIFF adapter"), ["radar_precipitation_rate", "radar_precipitation_type", "radar_extrapolation", "coverage_mask", "no_echo"], ["radar mosaic surface projection"], "North American/Canadian radar coverage; crop Avalon", "approximately 6-10 minutes, collection-dependent", "short extrapolation only", (False, "Anonymous OGC services", None), ECCC_POLICY, "GeoMet collection metadata at activation", "20 minutes", "Observed precipitating-echo evidence; no echo never means clear sky", (False, None, "Radar is observation/nowcast evidence and is not blended into NWP consensus."), delivery_kind="published_cell", reach=OBSERVED_INSTANT, native_cadence_seconds=360),
        _source("eccc-lightning", "lightning", *_admission("eccc-lightning", "Official ten-minute density product exists; collection and geometry fixtures remain."), "Environment and Climate Change Canada", "Lightning flash density", ["https://eccc-msc.github.io/open-data/msc-data/lightning/readme_lightning_en/"], [f"{ECCC_DATAMART}observations/lightning/"], ("raw_protocol", "official GeoTIFF protocol via rasterio"), ["lightning_flash_density", "coverage_mask"], ["10-minute gridded accumulation"], "Canada", "10 minutes", "observations only", (False, "Anonymous HTTPS", None), ECCC_POLICY, "ECCC lightning GeoTIFF product version discovered from metadata", "25 minutes", "Observed lightning evidence", (False, None, "Lightning is not blended."), delivery_kind="published_cell", reach=OBSERVED_INSTANT, native_cadence_seconds=600),
        _source("eccc-cap-alerts", "hazard", *_admission("eccc-cap-alerts", "Official CAP alert feed is available; alert revision/expiry fixtures remain."), "Environment and Climate Change Canada / authorized alert issuers", "Common Alerting Protocol weather alerts", ["https://eccc-msc.github.io/open-data/msc-data/alerts/readme_alerts_en/"], [f"{ECCC_DATAMART}alerts/cap/"], ("typed_adapter", "httpx + defusedxml CAP adapter"), ["event", "severity", "urgency", "certainty", "onset", "expires", "instruction", "area_geometry", "identifier", "references"], ["alert polygon/geocode"], "Canada; filter Newfoundland and adjacent marine areas", "event-driven", "validity interval in alert", (False, "Anonymous HTTPS/AMQP", None), ECCC_POLICY, "CAP-CP as declared in each message", "15 minutes after issue/update", "Official warning layer; never numerically blended", (False, None, "Warnings are authoritative categorical evidence, not model votes."), delivery_kind="published_cell", reach=OBSERVED_INSTANT, native_cadence_seconds=600),
        _source("eccc-thunderstorm-outlooks", "hazard", *_admission("eccc-thunderstorm-outlooks", "Official outlook candidate is catalogued but exact machine collection must be pinned."), "Environment and Climate Change Canada", "Thunderstorm outlooks", ["https://eccc-msc.github.io/open-data/msc-data-themes/thunderstorms_en/"], [ECCC_API], ("typed_adapter", "httpx + Pydantic OGC API adapter"), ["thunderstorm_outlook_category", "validity", "geometry"], ["forecast area/polygon"], "Canada where issued", "issuance-dependent", "product validity", (False, "Anonymous OGC API", None), ECCC_POLICY, "GeoMet collection schema to pin", "one issue cycle", "Supporting human-authored severe-weather guidance", (False, None, "Human guidance is not an independent NWP vote."), delivery_kind="published_cell"),
        _source("eccc-hurricane-products", "hazard", *_admission("eccc-hurricane-products", "Used only when official products are active; exact collection is season/event dependent."), "Canadian Hurricane Centre / ECCC", "Hurricane bulletins, tracks and watches/warnings", ["https://weather.gc.ca/hurricane/index_e.html", ECCC_CATALOGUE], [ECCC_API], ("typed_adapter", "httpx + Pydantic OGC/CAP adapter"), ["storm_identity", "track", "forecast_positions", "wind_extent", "watch_warning", "validity", "uncertainty"], ["point", "track", "polygon"], "Canadian Atlantic responsibility area", "advisory-dependent", "advisory validity", (False, "Anonymous HTTPS", None), ECCC_POLICY, "Product/CAP version per message", "one advisory cycle", "Event-driven official tropical-cyclone context", (False, None, "Hazards are not blended."), delivery_kind="published_cell"),
        _source("eccc-aqhi", "air_quality", *_admission("eccc-aqhi", "Official real-time observations and forecasts are exposed by GeoMet; adapter remains."), "Environment and Climate Change Canada", "Air Quality Health Index observations and forecasts", [ECCC_CATALOGUE, "https://api.weather.gc.ca/collections/aqhi-observations-realtime"], ["https://api.weather.gc.ca/collections/aqhi-observations-realtime/items"], ("typed_adapter", "httpx + Pydantic OGC API Features adapter"), ["AQHI", "observation_or_forecast_indicator", "valid_time", "station_or_region"], ["station point", "forecast region"], "Canada; select St. John's/Avalon", "hourly observations; forecast issuance-dependent", "forecast collection validity", (False, "Anonymous OGC API", None), ECCC_POLICY, "live OGC collection schema", "2 h observation; one forecast issue cycle", "AQHI only; never substitute for PM, AOD or extinction", (False, None, "Air-quality indices are not weather consensus fields."), delivery_kind="published_cell", reach=OBSERVED_INSTANT, native_cadence_seconds=3600),
        _source("eccc-raqdps", "air_quality", *_admission("eccc-raqdps", "Operational RAQDPS is in the current catalogue; variables must be selected from the current product inventory."), "Environment and Climate Change Canada", "RAQDPS", [ECCC_CATALOGUE], [f"{ECCC_DATAMART}model_raqdps/", ECCC_API], ("raw_protocol", "ecCodes/cfgrib or OGC coverage adapter"), ["PM1", "PM2.5", "PM10", "ozone", "NO2", "other_published_species", "smoke_related_fields", "wildfire_hotspot_inputs"], ["surface", "model vertical levels where published", "column where published"], "North America/Canada product domain", "operational cycles; product-dependent", "operational air-quality horizon", (False, "Anonymous HTTPS/OGC", None), ECCC_POLICY, "current RAQDPS GRIB2/GeoMet schema", "two nominal cycles", "Source-specific air-quality forecast", (False, None, "Not semantically interchangeable with AQHI/AOD/extinction or weather consensus."), delivery_kind="published_cell"),
        _source("eccc-rdaqa", "air_quality", *_admission("eccc-rdaqa", "Operational RDAQA analysis is in the current catalogue; decoder remains."), "Environment and Climate Change Canada", "RDAQA", [ECCC_CATALOGUE], [ECCC_API], ("raw_protocol", "OGC coverage or official GRIB2 adapter"), ["PM2.5", "PM10", "ozone", "NO2", "other_published_species", "analysis_quality"], ["surface analysis grid"], "Canadian air-quality analysis domain", "product-dependent", "analysis, not forecast", (False, "Anonymous OGC", None), ECCC_POLICY, "current RDAQA collection schema", "two analysis cycles", "Air-quality analysis", (False, None, "Analysis is not forecast consensus."), delivery_kind="published_cell"),
        _source("eccc-wildfire-hotspots", "air_quality", *_admission("eccc-wildfire-hotspots", "Official Canadian hotspot feed is catalogued; detection confidence/QC mapping remains."), "Natural Resources Canada / ECCC distribution", "Canadian Wildland Fire Information System hotspots", ["https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/"], ["https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/"], ("typed_adapter", "httpx geospatial feature adapter"), ["hotspot_location", "detection_time", "confidence", "satellite", "fire_radiative_power_when_published"], ["point detections"], "Canada", "satellite-pass dependent", "observations only", (False, "Anonymous HTTPS", None), ECCC_POLICY, "CWFIS hotspot schema at activation", "one applicable satellite pass", "Smoke/fire context, not proof of surface PM", (False, None, "Detection context is not blended."), delivery_kind="published_cell"),
        _source("eccc-raqdps-firework", "air_quality", "superseded", "The standalone RAQDPS-FireWork feed is listed under retired open data and must not be requested; smoke is incorporated into RAQDPS.", "Environment and Climate Change Canada", "RAQDPS-FireWork standalone", ["https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps-fw/readme_raqdps-fw_en/", ECCC_CATALOGUE], [f"{ECCC_DATAMART}model_raqdps-fw/"], ("raw_protocol", "No client; endpoint retained only as historical registry evidence"), ["historical_smoke_and_air_quality_fields"], ["historical surface/model levels"], "Historical North American product domain", "retired", "none", (False, "No access should be attempted", None), ECCC_POLICY, "retired product", "not applicable", "Registry tombstone only", (False, None, "Retired product cannot contribute."), "not_applicable", "not_applicable", delivery_kind="published_cell", superseded_by={"source_id": "eccc-raqdps", "detail": "RAQDPS smoke-plume layers, published on GeoMet and the dated WXO-DD Datamart path"}),
        _source("eccc-marine-buoys-synop", "marine_observation", *_admission("eccc-marine-buoys-synop", "SWOB guide documents MSC and DFO moored buoy sources; station QC/identity fixtures remain. Verified 2026-09-02: no ECCC buoy inside the evidence box carries dew point or visibility, and no ship reports were observed, so fog over water stays unverifiable in situ from this source."), "Environment and Climate Change Canada and Fisheries and Oceans Canada", "Official marine, ship, buoy SYNOP/SWOB observations", ["https://dd.weather.gc.ca/20260423/WXO-DD/observations/doc/SWOB-ML_Product_User_Guide_v8.16_e.pdf"], [f"{ECCC_DATAMART}observations/swob-ml/", f"{ECCC_DATAMART}observations/marine/"], ("typed_adapter", "SWOB XML and official SYNOP/BUFR adapter"), ["air_temperature", "dew_point", "relative_humidity_when_published", "wind", "pressure", "SST", "wave_height", "wave_period", "wave_direction", "visibility", "present_weather", "quality_flags"], ["marine platform surface", "wave groups"], "Official platforms in Newfoundland and upstream Atlantic waters", "platform-dependent", "observations only", (False, "Anonymous HTTPS", None), ECCC_POLICY, "SWOB-ML 8.16 plus WMO message version", "2 h", "Official marine observations", (False, None, "Observations are not forecast votes."), delivery_kind="published_cell"),
        _source("eccc-marine-forecasts-alerts", "marine", *_admission("eccc-marine-forecasts-alerts", "Official marine forecasts and warnings are accessible; machine collection/revision handling remains."), "Environment and Climate Change Canada", "Marine forecasts, warnings and coastal-flooding guidance", ["https://weather.gc.ca/marine/index_e.html", ECCC_CATALOGUE], [ECCC_API, f"{ECCC_DATAMART}alerts/cap/"], ("typed_adapter", "httpx OGC/CAP adapter"), ["marine_forecast_text", "wind", "visibility", "freezing_spray", "wave_guidance", "warning", "coastal_flooding_risk", "validity"], ["marine forecast area", "alert polygon"], "Newfoundland marine forecast areas", "issuance/event dependent", "published validity", (False, "Anonymous HTTPS", None), ECCC_POLICY, "CAP/product version in payload", "one issue cycle", "Human-authored marine guidance and hazards", (False, None, "Guidance and warnings are not blended."), delivery_kind="published_cell"),
        _source(
            "ccg-navwarn", "hazard",
            *_admission("ccg-navwarn", "Hazard text feed for the marine sectors around the Avalon and the Grand Banks; retrieved text products, no adapter registered yet."),
            "Canadian Coast Guard", "NAVWARN navigational warnings",
            ["https://www.notmar.gc.ca/"], ["https://www.marinfo.gc.ca/"],
            ("typed_adapter", "No production adapter; NAVWARN text products would be retrieved and stored as issued"),
            ["navwarn_text"], ["marine navigation sector (no vertical level)"],
            "Canadian marine navigation sectors including the Avalon and Grand Banks",
            "issuance-dependent", "published validity",
            (False, "Anonymous HTTPS", None),
            {"licence": {"name": "canada.ca terms and conditions", "url": "https://www.canada.ca/en/transparency/terms.html", "review_state": "pending"},
             "attribution": "Credit the Canadian Coast Guard and preserve the NAVWARN message identifier and issue time.",
             "caching": "Cache bounded text products within the experiment cap.",
             "archival": "Retain immutable text products for the local experiment window.",
             "redistribution": "Pending review of the canada.ca terms and conditions for this product."},
            "NAVWARN text product as issued", "one issue cycle",
            "Official hazard text layer for the marine sectors; never numerically blended",
            (False, None, "Hazard text is not a forecast vote."), delivery_kind="published_cell",
        ),
        _source("eccc-hydrometric", "hydrology", *_admission("eccc-hydrometric", "GeoMet exposes real-time hydrometric collections; station relevance selection remains."), "Environment and Climate Change Canada / Water Survey of Canada", "Real-time hydrometric stations", ["https://eccc-msc.github.io/open-data/usage/use-case_oafeat/use-case_oafeat-interactive_en/"], ["https://api.weather.gc.ca/collections/hydrometric-realtime/items"], ("generated_client", "Generate from https://api.weather.gc.ca/openapi after pinning a stable document; otherwise typed httpx adapter"), ["water_level", "discharge", "station_metadata", "quality_or_provisional_flags", "observation_time"], ["gauging station point"], "Canada; select relevant Avalon catchments", "station-dependent near-real-time", "observations only", (False, "Anonymous OGC API", None), ECCC_POLICY, "live GeoMet OpenAPI/collection schema", "3 h unless provider cadence indicates otherwise", "Official hydrometric observations", (False, None, "Hydrology is source-specific."), delivery_kind="published_cell"),
        _source(
            "nl-air-quality-csv", "air_quality",
            *_admission(
                "nl-air-quality-csv",
                "The only timely PM2.5 and ozone measurement in the box: the NL provincial St. John's NAPS site publishes "
                "an hourly CSV, rolling 35 days (890 rows at probe), with the last row at 2026-09-02 01:00 NDT read at "
                "06:16Z, about 2.75 h latency. The data is flagged PROVISIONAL, so it is an uncalibrated observation "
                "and is never used for verification (docs/research/wayfinder/running-sources.md).",
            ),
            "Government of Newfoundland and Labrador",
            "NL provincial hourly PM2.5 and ozone station CSV, St. John's NAPS site",
            ["https://www.mae.gov.nl.ca/wrmd/pp_adrs/template_airmon.asp?station=stjohns"],
            ["https://www.mae.gov.nl.ca/wrmd/pp_adrs/Data/StJohns_Line.csv"],
            ("typed_adapter", "No production adapter yet; httpx CSV fetch against the published rolling file"),
            ["pm2_5", "ozone"], ["station surface (no vertical level)"],
            "St. John's NAPS station only",
            "hourly, rolling 35-day file", "observations only",
            (False, "Anonymous HTTPS", None),
            {"licence": {"name": "Copyright Government of Newfoundland and Labrador, all rights reserved; data flagged PROVISIONAL", "url": "https://www.mae.gov.nl.ca/wrmd/pp_adrs/template_airmon.asp?station=stjohns", "review_state": "restricted"},
             "attribution": "Credit the Government of Newfoundland and Labrador and preserve the PROVISIONAL flag on every value.",
             "caching": "Cache bounded rolling-window rows within the experiment cap.",
             "archival": "Retain immutable CSV pulls for the local experiment window only.",
             "redistribution": "Not granted; the source is copyright, all rights reserved, and never redistributed."},
            "unversioned rolling CSV as served", "about 2.75 h",
            "The only timely PM2.5 and ozone uncalibrated observation in the box; PROVISIONAL and never used for verification",
            (False, None, "Uncalibrated observations are not forecast votes."), delivery_kind="published_cell", display_primary=False,
            restricted_terms={
                "terms_text": "copyright, Government of Newfoundland and Labrador, all rights reserved; PROVISIONAL, has not undergone quality control checks and may be subject to significant change",
                "terms_source_url": "https://www.mae.gov.nl.ca/wrmd/pp_adrs/template_airmon.asp?station=stjohns",
                "redistribution": False,
                "read_date": "2026-09-02",
            },
        ),
    ])

    # Independent forecast centres.
    ecmwf_policy = {"licence": {"name": "CC BY 4.0 plus ECMWF Terms of Use", "url": ECMWF_OPEN, "review_state": "verified"}, "attribution": "Credit ECMWF and identify IFS/AIFS product, cycle, type, member and processing.", "caching": "Open-data portal retains a rolling set; cache only bounded POC subsets.", "archival": "Immutable local artifacts for latest/previous complete run; ECMWF open portal is not a permanent archive.", "redistribution": "Permitted for the open-data subset under CC BY 4.0 with attribution and ECMWF terms."}
    # Reach differs by cycle for the two physical models and does not for the
    # two ML models, verified live 2026-09-02: IFS and IFS ENS publish 85 lead
    # files at 00z/12z (360 h) and 49 at 06z/18z (144 h), while AIFS single and
    # AIFS-ENS publish 61 files (360 h) at every cycle. A record that stated
    # only its longest reach would promise nine days on a 06z IFS run that has
    # six.
    ecmwf_reach = {
        "ecmwf-ifs": _reach(0, 360, {"00": 360, "06": 144, "12": 360, "18": 144}),
        "ecmwf-ens": _reach(0, 360, {"00": 360, "06": 144, "12": 360, "18": 144}),
        "ecmwf-aifs-single": _reach(0, 360),
        "ecmwf-aifs-ens": _reach(0, 360),
    }
    for id, product, model, ensemble in [("ecmwf-ifs", "IFS Open Data", "ifs", False), ("ecmwf-ens", "IFS ENS Open Data", "ifs", True), ("ecmwf-aifs-single", "AIFS Single Open Data", "aifs-single", False), ("ecmwf-aifs-ens", "AIFS ENS Open Data", "aifs-ens", True)]:
        s.append(_source(id, "ensemble" if ensemble else "deterministic_forecast", *_admission(id, "Current official open-data product is documented; client retrieval and fixture/live tests remain."), "European Centre for Medium-Range Weather Forecasts", product, [ECMWF_OPEN, "https://ecmwf-opendata.readthedocs.io/"], [ECMWF_ENDPOINT], ("official_sdk", f"ecmwf-opendata model={model} plus earthkit/ecCodes"), ["2m_temperature", "2m_dewpoint", "10m_wind", "mean_sea_level_pressure", "total_precipitation", "total_column_water_vapour", "relative_humidity", "specific_humidity", "geopotential", "temperature", "wind", "vertical_velocity", "cloud", "wave_fields_when_published", "probability_products_when_published"], ["surface", "2 m", "10 m", "isobaric including 1000-300 hPa and published upper levels", "column", "member/control" if ensemble else "deterministic"], "Global", "00/06/12/18 UTC", "up to 15 days; POC uses +24 h", (False, "Anonymous open-data HTTPS/S3", None), ecmwf_policy, "IFS Cycle 50r1 / current AIFS open-data schema as advertised", "newest run no older than two nominal cycles", "Independent-centre comparison" if not ensemble else "Within-family distribution; retain members separately", (not ensemble, "ECMWF", "At most one ECMWF representative may vote; related IFS/AIFS products are one centre family." if not ensemble else "Ensemble members remain a distribution and do not become independent centre votes."), delivery_kind="published_cell", reach=ecmwf_reach[id], run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=_latency(ECMWF_LATENCY_SECONDS, LATENCY_SEED_BASIS)))

    s.extend([
        _source("noaa-gfs", "deterministic_forecast", *_admission("noaa-gfs", "Official NOAA cloud/NOMADS data are public; Herbie path and GRIB inventory fixtures remain."), "NOAA/NCEP", "Global Forecast System", ["https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast", "https://registry.opendata.aws/noaa-gfs-bdp-pds/"], ["https://noaa-gfs-bdp-pds.s3.amazonaws.com/", "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"], ("community_client", "Herbie with s3fs fallback to official stores; ecCodes/cfgrib decoding"), ["temperature", "relative_humidity", "specific_humidity", "wind", "gust", "pressure", "precipitation", "cloud", "visibility", "CAPE", "CIN", "precipitable_water", "soil_fields"], ["surface", "2 m", "10 m", "isobaric", "column", "soil"], "Global", "00/06/12/18 UTC", "global medium range; POC uses +24 h", (False, "Anonymous HTTPS/S3", None), OPEN_US_POLICY, "current NCEP GFS GRIB2 production schema", "newest run no older than two nominal cycles", "Independent NOAA deterministic comparison", (True, "NOAA", "One NOAA representative may vote for comparable fields."), delivery_kind="published_cell", reach=_reach(0, 384), run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=_latency(GFS_LATENCY_SECONDS, LATENCY_SEED_BASIS)),
        _source("noaa-gefs", "ensemble", *_admission("noaa-gefs", "Official NOAA open store is available; member inventory and completeness fixtures remain."), "NOAA/NCEP", "Global Ensemble Forecast System", ["https://registry.opendata.aws/noaa-gefs/"], ["https://noaa-gefs-pds.s3.amazonaws.com/"], ("community_client", "Herbie with s3fs fallback; ecCodes/cfgrib decoding"), ["temperature", "humidity", "wind", "pressure", "precipitation", "cloud", "threshold_occurrence"], ["surface", "2 m", "10 m", "isobaric", "column", "all members and control"], "Global", "00/06/12/18 UTC", "global medium range; POC uses +24 h", (False, "Anonymous S3", None), OPEN_US_POLICY, "current NCEP GEFS GRIB2 production schema", "newest complete ensemble no older than two nominal cycles", "NOAA ensemble distribution", (False, "NOAA", "Members remain separate; GEFS does not add another NOAA centre vote."), delivery_kind="published_cell", reach=_reach(0, 384), run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=_latency(GFS_LATENCY_SECONDS, f"{LATENCY_SEED_BASIS}; f024 measured at T+3 h 57 m and f384 still absent at T+5 h 21 m, so the final leads land later than this seed and the upper bound is unmeasured")),
        _source("dwd-icon-global", "deterministic_forecast", *_admission("dwd-icon-global", "DWD publishes an official ICON open-data subset; exact inventory and licence notices must be captured per artifact. Two paths under one source, each value labelled with its evidence class: point samples are retrieved nearest-cell on the published CLAT/CLON icosahedral mesh with no regrid; rendered rasters are derived-here through a CDO-weights regrid method that must be registered in the derivation registry before any raster is served, and until it is registered only point samples are retrievable."), "Deutscher Wetterdienst", "ICON Global", ["https://www.dwd.de/EN/ourservices/opendata/opendata.html", "https://isabel.dwd.de/SharedDocs/downloads/DE/modelldokumentationen/nwv/icon/icon_dbbeschr_aktuell.pdf"], ["https://opendata.dwd.de/weather/nwp/icon/grib/"], ("raw_protocol", "official HTTPS GRIB2 via httpx, ecCodes, cfgrib and xarray"), ["temperature", "relative_humidity", "specific_humidity", "wind", "pressure", "precipitation", "cloud", "visibility", "CAPE", "soil_fields"], ["surface", "2 m", "10 m", "model levels", "isobaric", "column", "soil"], "Global", "operational cycles documented by DWD", "global forecast; POC uses +24 h", (False, "Anonymous HTTPS", None), {"licence": {"name": "DWD Open Data terms", "url": "https://www.dwd.de/EN/service/copyright/copyright_artikel.html", "review_state": "verified"}, "attribution": "Credit Deutscher Wetterdienst (DWD) and ICON; preserve product metadata.", "caching": "Cache only bounded domain/run subsets.", "archival": "Latest and previous complete run locally; no permanent-archive claim.", "redistribution": "Subject to DWD open-data copyright and attribution terms."}, "current ICON database/open-data GRIB2 schema", "newest run no older than two nominal cycles", "Independent DWD deterministic comparison", (True, "DWD", "One DWD representative may vote for comparable fields."), delivery_kind="published_cell", reach=_reach(0, 180, {"00": 180, "06": 120, "12": 180, "18": 120}), run_cadence_seconds=RUN_CADENCE_4X_DAILY, publication_latency=_latency(ICON_LATENCY_SECONDS, LATENCY_SEED_BASIS)),
        # Sixth in the owner's ensemble build order and the only one of the six
        # nobody has probed. It is a record rather than a silence so that the
        # catalogue can say the family is unmeasured, instead of a reader
        # inferring from an absent record that no such family was admitted. The
        # status is `unavailable` because no access path has been established
        # for this deployment, and because the enum the audit enforces has no
        # value meaning "admitted, catalogued, never probed"; `implementing`
        # would claim work that has not started. Nothing is measured here and
        # nothing is scheduled: see ENSEMBLE_DECLARATIONS["dwd-icon-eps"].
        _source("dwd-icon-eps", "ensemble", "unavailable", "Nothing about ICON-EPS was measured on wayfinder ticket 22: no member count, no control identifier, no access path, no cadence, no field list and no size figure. The record is declared so that the sixth family in the owner's ensemble build order is a registry fact rather than an implementation convention; it is not schedulable, not retrievable and carries no inventory until it is probed.", "Deutscher Wetterdienst", "ICON-EPS", ["https://www.dwd.de/EN/ourservices/opendata/opendata.html", "https://isabel.dwd.de/SharedDocs/downloads/DE/modelldokumentationen/nwv/icon/icon_dbbeschr_aktuell.pdf"], ["https://opendata.dwd.de/weather/nwp/"], ("link_only", "No adapter and no client: the access path has never been probed, and an adapter written against an assumed layout is what the unverified declaration exists to prevent"), ["unmeasured: no field list has been established for this family"], ["unmeasured"], "Documented DWD ICON-EPS domain; never probed for this deployment", "unknown; the run cycles were not enumerated", "unknown; the lead set was not enumerated", (False, "Anonymous HTTPS as documented for the ICON open-data tree; not probed", None), {"licence": {"name": "DWD Open Data terms", "url": "https://www.dwd.de/EN/service/copyright/copyright_artikel.html", "review_state": "verified"}, "attribution": "Credit Deutscher Wetterdienst (DWD) and ICON-EPS; preserve product metadata.", "caching": "Not applicable until an access path is measured.", "archival": "Not applicable until an access path is measured.", "redistribution": "Subject to DWD open-data copyright and attribution terms."}, "unknown; no GRIB2 template has been pinned", "not applicable until a cadence is measured", "Sixth in the declared ensemble build order; unmeasured and never scheduled", (False, None, "Ensemble members remain a distribution and do not become independent centre votes."), "not_applicable", "not_applicable", delivery_kind="published_cell"),
        _source("google-weathernext-2", "research_comparison", "credential-required", "Terms read 2026-09-02 and the licence is now split rather than pending; access still requires a reviewed Google data request, so the status stays credential-required. Bands verified from the Earth Engine catalogue: 2 m temperature, 10 m and 100 m winds, MSLP, SST, 6-hourly total precipitation, and geopotential, specific humidity, temperature, u, v and vertical velocity on 50-1000 hPa. 0.25 degrees, 6-hourly, 64 members, 15 days. There is no cloud variable, which is decisive for a map whose subject is cloud.", "Google DeepMind", "WeatherNext 2 forecasts", ["https://developers.google.com/weathernext/guides/access-forecast"], ["https://console.cloud.google.com/marketplace/product/bigquery-public-data/weathernext"], ("typed_adapter", "xarray/Zarr or BigQuery adapter only after approved access and pinned official starter guide"), ["temperature", "wind", "precipitation", "humidity", "geopotential", "vertical_velocity", "pressure"], ["major surface fields", "published atmospheric levels"], "Global", "official dataset-dependent", "global medium range", (True, "Google-approved dataset access", "https://developers.google.com/weathernext/guides/access-forecast"), {"licence": {"name": "Split by VALID TIME, read 2026-09-02. Historic Experimental Data, \"any data that relates to a time that is more than 48 hours ago\", is CC BY 4.0. Real-Time Experimental Data, \"any data that relates to a time that is no more than 48 hours in the past\", is under the separate, revocable GDM Real-Time Weather Forecasting Experimental Data Terms of Use, which restrict redistribution and proxying. A forecast for a future instant relates to a time that is not in the past at all, so EVERY forward-looking value is in the restricted tier and only history is CC BY.", "url": "https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_2_0_0", "review_state": "restricted"}, "attribution": "Historic tier requires verbatim: \"(c) 2025 DeepMind Technologies Limited's machine learning models used to create the experimental data made available at [dataset URL] under CC BY 4.0 licence terms. This data is intended for experimental modelling only and is not intended, validated, or approved for real world use.\" Real-time tier carries its own citation requirement in its terms document.", "caching": "Historic tier may be cached under CC BY with the required citation. No caching of the real-time tier until the owner accepts its terms.", "archival": "Historic tier only; the real-time terms are revocable, so nothing from that tier is archived locally.", "redistribution": "Historic tier permitted under CC BY 4.0 with the required citation. Real-time tier restricts redistribution and raw-data proxying and is prohibited here until the owner accepts the terms. Note the model publishes NO cloud variable of any kind, so any cloud field attributed to it downstream is that reseller's own humidity closure, not model output."}, "WeatherNext 2 dataset version to pin after access", "to be established by live latency audit", "Research comparison only", (False, "Google", "Excluded until operational latency, semantic fields and licence are validated."), "blocked", "blocked", delivery_kind="published_cell", display_primary=False, credential={"name": "WEATHER_SECRET_GOOGLE_WEATHERNEXT_TOKEN", "registration_url": "https://developers.google.com/weathernext/guides/access-forecast"}, restricted_terms={"terms_text": "Real-Time Experimental Data, \"any data that relates to a time that is no more than 48 hours in the past\", is under the separate, revocable GDM Real-Time Weather Forecasting Experimental Data Terms of Use, which restrict redistribution and proxying.", "terms_source_url": "https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_2_0_0", "redistribution": False, "read_date": "2026-09-02"},
                # 15 days at 6-hourly steps is documentation (Earth Engine
                # catalogue, read 2026-09-02), so the reach can be stated. The
                # run cadence cannot: the record says "official
                # dataset-dependent" and the planning-horizon matrix left it
                # unverified, so no `run_cadence_seconds` is declared rather
                # than a plausible 21600 invented from the step interval. The
                # latency block is present and empty for the same reason the
                # matrix gives: the record is credential-required, was never
                # probed, and still calls for a live latency audit.
                reach=_reach(0, 360), publication_latency=NO_LATENCY),
    ])

    # The one intermediary-derived record. Google WeatherNext 2 publishes no
    # cloud variable of any kind (verified from the Earth Engine band list,
    # 2026-09-02, and recorded on `google-weathernext-2` above), yet Open-Meteo
    # serves total, low, mid and high cloud for it, per member, for 64 members.
    # Open-Meteo documents exactly how: the cloud layers are computed from
    # relative humidity on pressure levels, and that relative humidity is
    # itself Open-Meteo's conversion of the producer's specific humidity. So
    # the cloud is not `reprocessed` - there is no producer cloud field that
    # anyone transformed - and it is not `derived_here` - this deployment did
    # not compute it and cannot list its inputs as retrieved values. The owner
    # admitted it on 2026-09-02 as `intermediary_derived`: producer,
    # intermediary and the intermediary's documented method named, carrying the
    # reprocessed limits (never the display primary, never a derivation input).
    # The status is `credential-required` and stays there: every forward-looking
    # WeatherNext value sits in the revocable GDM Real-Time Experimental Data
    # tier, and an intermediary proxying it does not move it into CC BY.
    open_meteo_transformations = list(OPEN_METEO_TRANSFORMATIONS)
    s.append(_source(
        "open-meteo-weathernext-2", "research_comparison", "credential-required",
        "Open-Meteo serves Google WeatherNext 2 (google_weathernext2_ensemble, 64 members) with total, low, mid and high cloud cover that the producer does not publish; Open-Meteo's own documentation states the cloud layers are an estimate from the vertical humidity profile and 'not a native cloud fraction forecast from WeatherNext', and the humidity is itself its conversion of the producer's specific humidity. Admitted 2026-09-02 as intermediary_derived rather than refused, under the reprocessed limits. Status stays credential-required because every forward-looking WeatherNext value is in the revocable GDM Real-Time Experimental Data tier and must be accepted with Google before retrieval, whatever route it arrives by. Never the display primary and never a derivation input.",
        "Google DeepMind", "WeatherNext 2 ensemble delivered by Open-Meteo",
        ["https://open-meteo.com/en/docs/weathernext-api", "https://developers.google.com/weathernext/guides/access-forecast"],
        ["https://api.open-meteo.com/v1/forecast"],
        ("typed_adapter", "httpx + Pydantic adapter reading data/<domain>/static/meta.json beside every call; no adapter is written until the real-time terms are accepted"),
        ["total_cloud", "low_cloud", "middle_cloud", "high_cloud", "relative_humidity", "air_temperature", "dew_point", "wind_speed", "wind_direction", "mean_sea_level_pressure", "precipitation"],
        ["surface", "2 m", "10 m", "pressure levels 50-1000 hPa", "ensemble member 01-64"],
        "Global; queried per point over the evidence box",
        "6-hourly producer steps interpolated by the intermediary; no run fields exposed in meta.json",
        "15 days",
        (True, "Anonymous to Open-Meteo, but Google's Real-Time Experimental Data Terms of Use must be accepted for any forward-looking value", "https://developers.google.com/weathernext/guides/access-forecast"),
        {"licence": {"name": "Google DeepMind Real-Time Weather Forecasting Experimental Data Terms of Use for every forward-looking value; CC BY 4.0 only for data more than 48 hours in the past. Open-Meteo's own terms (CC BY 4.0, non-commercial call budget) apply to the delivery, not to the underlying data.", "url": "https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_2_0_0", "review_state": "restricted"},
         "attribution": "Name Google DeepMind as producer and Open-Meteo as intermediary on every value, and carry the tier's required citation; a cloud value additionally names Open-Meteo's humidity closure as the method that produced it.",
         "caching": "No caching until the owner accepts the real-time terms; the historic tier may be cached with its required citation.",
         "archival": "Nothing from the real-time tier is archived locally, because those terms are revocable.",
         "redistribution": "Prohibited for the real-time tier, which the intermediary route does not change."},
        "Open-Meteo JSON schema as served, with the producer's dataset version unexposed", "no run fields are published, so freshness cannot be asserted",
        "Intermediary-derived cloud for a producer that publishes none; never the display primary and never a derivation input",
        (False, None, "There is nothing to be eligible for, and an intermediary's own diagnostic could not vote in any case."),
        "blocked", "blocked",
        delivery_kind="intermediary_derived", credential={"name": "WEATHER_SECRET_GOOGLE_WEATHERNEXT_TOKEN", "registration_url": "https://developers.google.com/weathernext/guides/access-forecast"},
        intermediary={
            "name": "Open-Meteo",
            "method": "Low cloud cover derived from relative humidity at 1000, 925 and 850 hPa; mid from 700, 600, 500 and 400 hPa; high from 300, 250, 200, 150, 100 and 50 hPa; total by combining the derived low, mid and high layers. The relative humidity is Open-Meteo's own conversion of the producer's specific humidity. Documented by Open-Meteo, read 2026-09-02.",
            "transformations": open_meteo_transformations,
        },
        field_delivery_kinds={
            "total_cloud": "intermediary_derived",
            "low_cloud": "intermediary_derived",
            "middle_cloud": "intermediary_derived",
            "high_cloud": "intermediary_derived",
            "relative_humidity": "reprocessed",
            "air_temperature": "reprocessed",
            "dew_point": "reprocessed",
            "wind_speed": "reprocessed",
            "wind_direction": "reprocessed",
            "mean_sea_level_pressure": "reprocessed",
            "precipitation": "reprocessed",
        },
    ))

    # Satellite and atmospheric composition.
    s.extend([
        _source("noaa-goes-east", "satellite", *_admission("noaa-goes-east", "Re-pointed from GOES-16 to GOES-19 (noaa-goes19 official S3 bucket). Admitted product set: Enterprise Cloud Mask (ABI-L2-ACM), five-layer cloud fraction (ABI-L2-CCLF, about 21 KB over the box), cloud-top height (ABI-L2-ACHA, 2 km), cloud-top phase (ACTP) and cloud-top temperature (ACHT). No fog or cloud-base product exists on GOES-19, and the record makes no claim of one; DQF, parallax and zenith-angle fixtures remain."), "NOAA/NESDIS", "GOES-19 ABI L2+ Enterprise Cloud Mask, five-layer cloud fraction and cloud-top products", ["https://www.goes-r.gov/downloads/resources/documents/Beginners_Guide_to_GOES-R_Series_Data.pdf", "https://www.goes-r.gov/products/overview.html"], ["https://noaa-goes19.s3.amazonaws.com/"], ("community_client", "goes2go discovery + Satpy calibration/resampling + s3fs official bucket"), ["cloud_mask_ABI_L2_ACM", "cloud_fraction_five_layer_ABI_L2_CCLF", "cloud_top_height_ABI_L2_ACHA_2km", "cloud_top_phase_ACTP", "cloud_top_temperature_ACHT", "DQF", "parallax", "zenith_angle", "coverage"], ["satellite pixels", "derived cloud top", "derived layer/profile products"], "GOES-East (GOES-19) full disk; Newfoundland is high-zenith-angle edge coverage requiring masks", "10 minutes (full disk L2 cloud products)", "observations/derived products only", (False, "Anonymous public S3", None), OPEN_US_POLICY, "GOES-R ABI L2+ product versions embedded in NetCDF", "30 minutes, product-dependent", "Satellite cloud evidence with DQF and coverage; no fog or cloud-base product on GOES-19", (False, None, "Satellite retrievals are not forecast-centre votes."), delivery_kind="published_cell", reach=OBSERVED_INSTANT, native_cadence_seconds=600),
        _source("copernicus-cams", "air_quality", "credential-required", "Official CAMS store uses Copernicus/ECMWF credentials; adapter can be tested only after a key is supplied later. The previous licence text disagreed with the ADS catalogue and was corrected to CC BY 4.0 on 2026-09-02.", "Copernicus Atmosphere Monitoring Service / ECMWF", "CAMS global atmospheric composition forecasts", ["https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts", "https://cds.climate.copernicus.eu/licences/licence-to-use-copernicus-products"], ["https://ads.atmosphere.copernicus.eu/api"], ("official_sdk", "ecmwf-datastores-client"), ["aerosol_optical_depth", "extinction_coefficient", "dust", "sea_salt", "organic_matter", "black_carbon", "sulphate", "nitrate", "ammonium", "PM1", "PM2.5", "PM10", "vertical_mixing_ratios", "water_vapour_and_humidity_when_available"], ["surface", "model levels", "pressure levels", "column"], "Global", "operational CAMS cycles", "global composition forecast", (True, "Copernicus ADS personal access token", "https://ads.atmosphere.copernicus.eu/how-to-api"), {"licence": {"name": "CC BY 4.0 (Licence to use Copernicus Products), read 2026-09-02 from the ADS catalogue", "url": "https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts", "review_state": "verified"}, "attribution": "Use the required 'Contains modified Copernicus Atmosphere Monitoring Service information [year]' notice for adaptations.", "caching": "Cache bounded subsets only after authentication and licence acceptance.", "archival": "Retain bounded immutable artifacts under local retention policy.", "redistribution": "Permitted under the Copernicus licence with required notices; third-party products may differ."}, "dataset version returned by ADS", "two nominal cycles", "Independent atmospheric-composition evidence; keep AOD/extinction/PM distinct", (False, None, "Composition fields do not vote in weather consensus."), "blocked", "blocked", delivery_kind="published_cell", credential={"name": "WEATHER_SECRET_COPERNICUS_ADS_TOKEN", "registration_url": "https://ads.atmosphere.copernicus.eu/how-to-api"}),
        _source("nasa-earthdata-aerosol", "air_quality", "credential-required", "MODIS/VIIRS/MAIAC near-real-time products require Earthdata authentication and pass/latency validation.", "NASA", "MODIS, VIIRS and MAIAC aerosol observations", ["https://www.earthdata.nasa.gov/data/instruments/viirs", "https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD19_User_Guide_V6.pdf"], ["https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/"], ("typed_adapter", "earthaccess/httpx discovery plus rasterio/xarray reader"), ["aerosol_optical_depth", "aerosol_type_or_quality_flags", "cloud_mask", "observation_geometry", "pass_time"], ["satellite swath/pixel", "column AOD"], "Polar-orbiting global swaths; pass-dependent Avalon coverage", "satellite pass-dependent", "observations only", (True, "NASA Earthdata Login bearer/cookie", "https://urs.earthdata.nasa.gov/users/new"), {"licence": {"name": "NASA Earth Science data policy and product-specific terms", "url": "https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy", "review_state": "verified"}, "attribution": "Credit NASA and the named instrument/product/science team; preserve DOI and quality flags.", "caching": "Cache only relevant swath/subsets under the cap.", "archival": "Retain immutable granules for the local POC window; cite provider archive identifiers.", "redistribution": "Generally open with attribution, subject to product-specific notices."}, "collection/version embedded in granule, e.g. MAIAC Collection 6", "one useful satellite pass; mark unavailable outside coverage", "Satellite aerosol evidence; AOD is never PM", (False, None, "Satellite aerosol observations are not blended."), "blocked", "blocked", delivery_kind="published_cell", credential={"name": "WEATHER_SECRET_NASA_EARTHDATA_TOKEN", "registration_url": "https://urs.earthdata.nasa.gov/users/new"}),
        _source(
            "falchi-night-sky-atlas", "astronomy",
            *_admission(
                "falchi-night-sky-atlas",
                "A static 2015-epoch raster held locally, under a standing constraint on any commercial path: CC BY-NC 4.0 "
                "recorded as restricted terms and never redistributed (docs/research/wayfinder/transparency-seeing-sources.md).",
            ),
            "Falchi et al. (2016)", "World Atlas of Artificial Night Sky Brightness",
            ["https://www.science.org/doi/10.1126/sciadv.1600377"], ["https://doi.org/10.5880/GFZ.1.4.2016.001"],
            ("typed_adapter", "out-of-band fetch script against the checksum-verified local raster; no adapter registered yet"),
            ["artificial_sky_brightness_zenith"], ["30 arcsec zenith raster (no vertical level)"],
            "Global 30 arcsec raster; crop to the box",
            "static; single 2015 epoch", "static geometry over any requested window",
            (False, "none", None),
            {"licence": {"name": "CC BY-NC 4.0", "url": "https://creativecommons.org/licenses/by-nc/4.0/", "review_state": "restricted"},
             "attribution": "Credit Falchi et al. (2016) and GFZ Data Services; cite the DOI.",
             "caching": "One immutable raster file within the experiment cap; no repeated retrieval.",
             "archival": "The pinned raster is the archive; a changed release is a different source version.",
             "redistribution": "Forbidden on any commercial path under CC BY-NC 4.0; never redistributed."},
            "2016 GFZ Data Services release", "not applicable",
            "Static artificial sky-brightness evidence; a standing constraint on any commercial path, never redistributed",
            (False, None, "A pinned atlas raster is not a forecast centre and casts no vote."),
            delivery_kind="published_cell", display_primary=False,
            restricted_terms={
                "terms_text": "CC BY-NC 4.0: non-commercial use only; the atlas raster may not be redistributed or used on any commercial path",
                "terms_source_url": "https://doi.org/10.5880/GFZ.1.4.2016.001",
                "redistribution": False,
                "read_date": "2026-09-02",
            },
        ),
        _source(
            "viirs-dnb-night-lights", "astronomy", "credential-required",
            "Fails closed without the key; the observational input behind the Falchi atlas and more current "
            "(docs/research/wayfinder/transparency-seeing-sources.md).",
            "NASA / NOAA", "VIIRS day-night band nighttime lights",
            ["https://www.earthdata.nasa.gov/data/instruments/viirs"], ["https://ladsweb.modaps.eosdis.nasa.gov/"],
            ("typed_adapter", "earthaccess/httpx discovery plus rasterio/xarray reader; no adapter registered yet"),
            ["viirs_dnb_radiance", "cloud_free_composite_flag", "quality_flags"], ["satellite swath/pixel", "monthly and annual composite"],
            "Polar-orbiting global swaths and composites; crop to the box",
            "monthly and annual composites; per-overpass swaths", "observations only",
            (True, "NASA Earthdata Login bearer token", "https://urs.earthdata.nasa.gov/users/new"),
            {"licence": {"name": "NASA Earth Science data policy and product-specific terms", "url": "https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy", "review_state": "verified"},
             "attribution": "Credit NASA/NOAA and the named instrument/product/science team; preserve DOI and quality flags.",
             "caching": "Cache only relevant swath/composite subsets under the cap.",
             "archival": "Retain immutable granules for the local POC window; cite provider archive identifiers.",
             "redistribution": "Generally open with attribution, subject to product-specific notices."},
            "collection/version embedded in granule", "one useful satellite pass; composites at their own cadence",
            "The observational input behind the Falchi atlas and more current; never blended",
            (False, None, "Satellite night-lights observations are not forecast votes."),
            "blocked", "blocked", delivery_kind="published_cell",
            credential={"name": "WEATHER_SECRET_NASA_EARTHDATA_TOKEN", "registration_url": "https://urs.earthdata.nasa.gov/users/new"},
        ),
        _source(
            "7timer", "astronomy", "link-only",
            "Benchmark for comparison; never a data path. Publishes seeing and transparency in a derivation the wiki "
            "does not document, so it enters no adapter and is cited only (docs/research/wayfinder/astronomy-tool-needs.md).",
            "Community project (Chinese Academy of Sciences origin)", "7Timer! ASTRO product",
            ["https://github.com/Yeqzids/7timer-issues/wiki/Wiki"], [],
            ("link_only", "Benchmark for comparison; never a data path"),
            ["citation"], ["not applicable"],
            "Global; NCEP GFS at approximately 10 km grid spacing",
            "not applicable", "not applicable",
            (False, "none", None),
            {"licence": {"name": "Citation only; no data retrieved", "url": "https://github.com/Yeqzids/7timer-issues/wiki/Wiki", "review_state": "verified"},
             "attribution": "Link to 7Timer! only; no values are retrieved to attribute.",
             "caching": "Not applicable; nothing is retrieved.",
             "archival": "Not applicable; nothing is retrieved.",
             "redistribution": "Not applicable; nothing is retrieved."},
            "none", "not applicable",
            "Citation only, for the reader; benchmark for comparison, never a data path",
            (False, None, "A benchmark citation is not a forecast centre."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "meteosource", "research_comparison", "catalogued",
            "Paid provider; catalogued with a licence decision only (docs/research/wayfinder/astronomy-tool-needs.md)."
            + CATALOGUED_UNTIL_ADAPTER,
            "Meteosource", "Meteosource commercial weather API",
            ["https://www.meteosource.com/"], [],
            ("link_only", "No adapter; catalogued with a licence decision only"),
            ["citation"], ["not applicable"],
            "Global", "not applicable", "not applicable",
            (True, "Commercial API key", "https://www.meteosource.com/"),
            {"licence": {"name": "Meteosource commercial terms, unread", "url": "https://www.meteosource.com/", "review_state": "unknown"},
             "attribution": "Not applicable; nothing is retrieved.",
             "caching": "Not applicable; nothing is retrieved.",
             "archival": "Not applicable; nothing is retrieved.",
             "redistribution": "Not applicable; nothing is retrieved."},
            "none", "not applicable",
            "Catalogued paid-provider evidence; a licence decision only, never a data path",
            (False, None, "A catalogued paid provider is not a forecast vote."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "noaa-rap", "deterministic_forecast", "catalogued",
            "Domain coverage over the evidence box is unverified; Astrospheric's cited source for smoke and aerosol "
            "optical depth (docs/research/wayfinder/astronomy-tool-needs.md)." + CATALOGUED_UNTIL_ADAPTER,
            "NOAA/NCEP", "Rapid Refresh (RAP): smoke and aerosol optical depth",
            ["https://www.ncei.noaa.gov/products/weather-climate-models/rapid-refresh-update"], ["https://nomads.ncep.noaa.gov/"],
            ("typed_adapter", "No adapter; domain coverage over the box unverified"),
            ["smoke", "aerosol_optical_depth"], ["surface", "model levels"],
            "North American domain; coverage of the box unverified",
            "hourly", "18 h",
            (False, "Anonymous HTTPS", None), OPEN_US_POLICY,
            "NOMADS GRIB2 as served", "unknown",
            "Second aerosol opinion alongside CAMS, catalogued pending a domain-coverage check",
            (False, None, "Domain coverage over the box is unverified."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
            admission_condition={"condition": "Domain coverage of the evidence box (45.0 to 50.5 N, 58.0 to 46.0 W) by RAP is unverified.", "satisfied_by": "A NOMADS coverage check over the box recorded on the record.", "satisfied": False, "recorded_on": "2026-09-02"},
        ),
        _source(
            "noaa-nam", "deterministic_forecast", "catalogued",
            "Domain coverage over the Grand Banks is unverified; named in Astrospheric's cloud ensemble "
            "(docs/research/wayfinder/astronomy-tool-needs.md)." + CATALOGUED_UNTIL_ADAPTER,
            "NOAA/NCEP", "North American Mesoscale Forecast System (NAM): cloud ensemble input",
            ["https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/nam.php"], ["https://nomads.ncep.noaa.gov/"],
            ("typed_adapter", "No adapter; domain coverage over the Grand Banks unverified"),
            ["cloud_fraction"], ["surface", "model levels"],
            "North American domain; coverage of the Grand Banks unverified",
            "4 runs/day", "84 h",
            (False, "Anonymous HTTPS", None), OPEN_US_POLICY,
            "NOMADS GRIB2 as served", "unknown",
            "Cloud-ensemble input alongside other centres, catalogued pending a domain-coverage check",
            (False, None, "Domain coverage over the Grand Banks is unverified."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
            admission_condition={"condition": "Domain coverage of the Grand Banks by NAM is unverified.", "satisfied_by": "A NOMADS coverage check over the Grand Banks recorded on the record.", "satisfied": False, "recorded_on": "2026-09-02"},
        ),
        _source(
            "globe-at-night", "optional_observation", "catalogued",
            "Uncalibrated observation; catalogued only. Ground truth the Falchi atlas itself was calibrated against "
            "(docs/research/wayfinder/astronomy-tool-needs.md)." + CATALOGUED_UNTIL_ADAPTER,
            "Globe at Night / NOIRLab", "Globe at Night citizen sky-brightness observations",
            ["https://globeatnight.org/"], [],
            ("link_only", "No adapter; catalogued only"),
            ["citation"], ["not applicable"],
            "Global citizen submissions", "not applicable", "not applicable",
            (False, "none", None),
            {"licence": {"name": "Globe at Night data terms, unread", "url": "https://globeatnight.org/", "review_state": "unknown"},
             "attribution": "Not applicable; nothing is retrieved.",
             "caching": "Not applicable; nothing is retrieved.",
             "archival": "Not applicable; nothing is retrieved.",
             "redistribution": "Not applicable; nothing is retrieved."},
            "none", "not applicable",
            "Uncalibrated citizen sky-brightness observation; catalogued only, never used for verification",
            (False, None, "Uncalibrated citizen observations are not forecast votes."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
    ])

    # Space weather: NOAA SWPC keyless JSON feeds. The category is
    # deliberately absent from FORECAST_CATEGORIES (no synthesized lead
    # hours for a 3-day Kp outlook) and from the observation categories (a
    # planetary index is not a local observation).
    swpc_docs = ["https://www.swpc.noaa.gov/products", "https://services.swpc.noaa.gov/"]
    s.extend([
        _source(
            "noaa-swpc-kp", "space_weather", *_admission("noaa-swpc-kp", "Official SWPC planetary K index feeds are public JSON; live schema pinned by smoke test 2026-08-31."),
            "NOAA Space Weather Prediction Center", "Planetary K index (observed series and 3-day forecast)",
            swpc_docs,
            ["https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json", "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; observed and forecast series kept separate with the provider's own per-value status"),
            ["kp_index", "a_running", "kp_status"], ["planetary index (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "3 hours", "observed series plus provider 3-day outlook with per-value status; no lead hours",
            (False, "Anonymous HTTPS", None), OPEN_US_POLICY,
            "SWPC products JSON schema as served", "6 hours",
            "Geomagnetic activity evidence for aurora photography; never blended into weather consensus",
            (False, None, "A planetary index is not a forecast-centre vote."), delivery_kind="published_cell",
            # The observed series is what covers an instant. The provider's
            # 3-day outlook is retrieved beside it and carries no lead hours in
            # this deployment (the record's own words), so it extends no reach.
            reach=OBSERVED_INSTANT, native_cadence_seconds=10800,
        ),
        _source(
            "noaa-swpc-rtsw", "space_weather", "catalogued",
            "Official SWPC real-time solar wind magnetometer JSON is public; the feed's own source field names the measuring spacecraft. DSCOVR has left the feed, which now interleaves SWFO-L1, ACE and IMAP; every quality flag must be stored, which the current adapter does not do. Catalogued until re-implemented; admission by the 2026-09-02 resolutions is a ceiling, not a fetch.",
            "NOAA Space Weather Prediction Center", "Real-time solar wind magnetic field (1-minute)",
            swpc_docs,
            ["https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; stored on a bare time axis, no coordinates"),
            ["bz_gsm", "bt"], ["L1 solar wind (no vertical level)"],
            "Upstream solar wind at L1; no spatial coordinates are stored or claimed",
            "1 minute", "nowcast only; ~30-60 min advance warning of geomagnetic response",
            (False, "Anonymous HTTPS", None), OPEN_US_POLICY,
            "SWPC rtsw JSON schema as served", "15 minutes",
            "Southward Bz is the aurora tripwire; served with its measurement instant and age",
            (False, None, "Solar wind measurements are not forecast votes."), delivery_kind="published_cell",
            # A measurement at L1 covers the instant it was taken. The 30 to 60
            # minutes of advance warning it buys is a property of what the
            # measurement implies downstream, not a valid time this source
            # publishes a value for.
            reach=OBSERVED_INSTANT, native_cadence_seconds=60,
            admission_condition={"condition": "The real-time solar wind feed interleaves SWFO-L1, ACE and IMAP since DSCOVR left it, and the current adapter does not store every quality flag.", "satisfied_by": "An adapter that stores every quality flag and passes its fixture.", "satisfied": False, "recorded_on": "2026-09-02"},
        ),
        _source(
            "noaa-swpc-ovation", "space_weather", *_admission("noaa-swpc-ovation", "Official OVATION aurora nowcast grid is public JSON with its own observation and forecast instants."),
            "NOAA Space Weather Prediction Center", "OVATION aurora probability nowcast grid",
            swpc_docs,
            ["https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; global 1-degree grid cropped to the Atlantic context box"),
            ["aurora_probability"], ["auroral emission altitude (single layer)"],
            "Global grid; stored crop covers the Atlantic context box",
            "10 minutes", "model nowcast ~30-40 minutes ahead of its observation instant",
            (False, "Anonymous HTTPS", None), OPEN_US_POLICY,
            "OVATION aurora JSON schema as served", "30 minutes",
            "Aurora probability evidence; a model nowcast, disclosed as such",
            (False, None, "A model nowcast grid is not a forecast-centre vote."), delivery_kind="published_cell",
            # OVATION is the one non-forecast record with a forward reach, and
            # the number is the record's own prose: the grid carries a forecast
            # instant roughly 30 to 40 minutes ahead of the observation instant
            # it was computed from. 0.667 h is the upper end of that, stated in
            # hours because reach is in hours; the nowcast covers everything
            # from its observation instant forward to there.
            reach=_reach(0, 0.667), native_cadence_seconds=600,
        ),
    ])

    # Space weather additions (source-admissions-ledger task 5.x). None of
    # these ids has a registered adapter, so no reach, run cadence, native
    # cadence or publication-latency fields are declared: those keyword
    # arguments are stated only where an adapter exists to measure against
    # them (Deviation 2).
    gfz_policy = {
        "licence": {"name": "CC BY 4.0", "url": "https://kp.gfz.de/en/hp30-hp60", "review_state": "verified"},
        "attribution": "Credit GFZ German Research Centre for Geosciences and the Hp30/Hp60 index.",
        "caching": "Cache bounded time selections within the experiment cap.",
        "archival": "Retain immutable JSON responses for the local experiment window.",
        "redistribution": "May be redistributed with attribution under CC BY 4.0.",
    }
    nrcan_stj_policy = {
        "licence": {"name": "NRCan geomagnetic data terms: redistribution requires written permission", "url": "https://geomag.nrcan.gc.ca/", "review_state": "restricted"},
        "attribution": "Credit Natural Resources Canada Geomagnetic Laboratory.",
        "caching": "Not applicable; no data is retrieved until written permission is granted.",
        "archival": "Not applicable; no data is retrieved until written permission is granted.",
        "redistribution": "Forbidden without NRCan's written permission.",
    }

    def _link_only_policy(url: str) -> dict[str, Any]:
        return {
            "licence": {"name": "Citation only; no data retrieved", "url": url, "review_state": "verified"},
            "attribution": "Link to the producer only; no values are retrieved to attribute.",
            "caching": "Not applicable; nothing is retrieved.",
            "archival": "Not applicable; nothing is retrieved.",
            "redistribution": "Not applicable; nothing is retrieved.",
        }

    s.extend([
        _source(
            "noaa-swpc-plasma", "space_weather", *_admission("noaa-swpc-plasma", "Official SWPC solar wind plasma product (7-day) is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "Solar wind plasma (density, speed, temperature), 7-day",
            swpc_docs, ["https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["density", "speed", "temperature"], ["L1 solar wind (no vertical level)"],
            "Upstream solar wind at L1; no spatial coordinates are stored or claimed",
            "1 minute, 7-day rolling window", "observed series only; no lead hours",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC plasma-7-day JSON schema as served", "15 minutes",
            "Solar wind plasma evidence for space-weather context",
            (False, None, "Solar wind measurements are not forecast votes."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-swpc-propagated-solar-wind", "space_weather", *_admission("noaa-swpc-propagated-solar-wind", "Official SWPC propagated solar wind (1-hour) is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "Propagated solar wind (1-hour), advanced to the bow shock",
            swpc_docs, ["https://services.swpc.noaa.gov/products/geospace/propagated-solar-wind-1-hour.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["density", "speed", "bz_gsm", "bt"], ["L1 solar wind propagated to the bow shock (no vertical level)"],
            "Upstream solar wind propagated forward; no spatial coordinates are stored or claimed",
            "1 minute", "propagated nowcast only; no lead hours",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC propagated-solar-wind-1-hour JSON schema as served", "15 minutes",
            "Propagated solar wind evidence for space-weather context",
            (False, None, "Solar wind measurements are not forecast votes."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-swpc-kp-1m", "space_weather", *_admission("noaa-swpc-kp-1m", "Official SWPC 1-minute planetary K index is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "Planetary K index (1-minute)",
            swpc_docs, ["https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["kp_index"], ["planetary index (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "1 minute", "observed series only; no lead hours",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC planetary_k_index_1m JSON schema as served", "6 hours",
            "Higher-cadence geomagnetic activity evidence beside the 3-hour Kp series",
            (False, None, "A planetary index is not a forecast-centre vote."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-swpc-alerts", "space_weather", *_admission("noaa-swpc-alerts", "Official SWPC alert text products feed is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "Space weather alert, watch and warning text products",
            swpc_docs, ["https://services.swpc.noaa.gov/products/alerts.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["alert_text"], ["alert message (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "issuance dependent", "current alerts only; each message carries its own validity interval",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC alerts.json schema as served", "30 minutes",
            "Space weather alert text evidence for aurora and geomagnetic context",
            (False, None, "Text alerts are not forecast votes."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-swpc-scales", "space_weather", *_admission("noaa-swpc-scales", "Official NOAA space weather scales product is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "NOAA space weather scales (R, S, G)",
            swpc_docs, ["https://services.swpc.noaa.gov/products/noaa-scales.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["r_scale", "s_scale", "g_scale"], ["planetary index (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "issued several times daily", "current and predicted 24 h and day 2/3 scale values",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC noaa-scales.json schema as served", "6 hours",
            "NOAA scale evidence summarising radio blackout, solar radiation storm and geomagnetic storm levels",
            (False, None, "Scale summaries are not forecast votes."), delivery_kind="published_cell",
        ),
        _source(
            "gfz-hp30", "space_weather", *_admission("gfz-hp30", "GFZ Hp30 half-hour geomagnetic index is openly licensed under CC BY 4.0 and live."),
            "GFZ German Research Centre for Geosciences", "Hp30 half-hour geomagnetic index",
            ["https://kp.gfz.de/en/hp30-hp60"], ["https://kp.gfz.de/app/json/?index=Hp30"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["hp30_index"], ["planetary index (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "30 minutes", "observed series only; no lead hours",
            (False, "none", None), gfz_policy,
            "GFZ Hp30 JSON schema as served", "1 hour",
            "Higher-cadence geomagnetic activity evidence beside the 3-hour Kp series",
            (False, None, "A planetary index is not a forecast-centre vote."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-goes-magnetometer", "space_weather", *_admission("noaa-goes-magnetometer", "Official SWPC GOES primary magnetometer (1-day) product is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "GOES primary magnetometer (1-day)",
            swpc_docs, ["https://services.swpc.noaa.gov/json/goes/primary/magnetometers-1-day.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["he", "hp", "hn", "total"], ["GOES geosynchronous orbit (no vertical level)"],
            "Geosynchronous orbit; no spatial coordinates are stored or claimed",
            "1 minute, 1-day rolling window", "observed series only; no lead hours",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC goes/primary/magnetometers-1-day JSON schema as served", "15 minutes",
            "Geosynchronous magnetic field evidence for geomagnetic activity context",
            (False, None, "Satellite magnetometer measurements are not forecast votes."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-goes-xray", "space_weather", *_admission("noaa-goes-xray", "Official SWPC GOES X-ray flux (1-day) product is openly licensed and live."),
            "NOAA Space Weather Prediction Center", "GOES X-ray flux (1-day)",
            swpc_docs, ["https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["xray_flux_short", "xray_flux_long"], ["GOES geosynchronous orbit (no vertical level)"],
            "Geosynchronous orbit; no spatial coordinates are stored or claimed",
            "1 minute, 1-day rolling window", "observed series only; no lead hours",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC goes/primary/xrays-1-day JSON schema as served", "15 minutes",
            "Solar flare evidence for space-weather context",
            (False, None, "Satellite X-ray flux measurements are not forecast votes."), delivery_kind="published_cell",
        ),
        _source(
            "noaa-swpc-kyoto-dst", "space_weather",
            *_admission(
                "noaa-swpc-kyoto-dst",
                "SWPC relays the Kyoto WDC provisional and real-time Dst series as a JSON product; the producer is the Kyoto WDC and SWPC is the intermediary. Never the display primary and never a derivation input.",
            ),
            "Kyoto World Data Center for Geomagnetism", "Dst index (provisional and real-time)",
            swpc_docs, ["https://services.swpc.noaa.gov/products/kyoto-dst.json"],
            ("typed_adapter", "httpx JSON via PoliteClient; no adapter registered yet"),
            ["dst_index"], ["planetary index (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "1 hour", "observed series only; no lead hours",
            (False, "none", None), OPEN_US_POLICY,
            "SWPC kyoto-dst.json schema as served", "3 hours",
            "Dst index evidence, relayed and never treated as a display primary or a derivation input",
            (False, None, "Not a deterministic forecast centre."),
            delivery_kind="reprocessed",
            intermediary={
                "name": "NOAA SWPC",
                "method": "relay of the Kyoto WDC provisional and real-time Dst series as a JSON product",
                "transformations": [
                    "re-serialised from the WDC text tables to SWPC JSON",
                    "provisional and real-time values interleaved without the WDC final flag",
                ],
            },
        ),
        _source(
            "noaa-swpc-stereo-a", "space_weather", "unavailable",
            "STEREO-A solar wind product is stale behind HTTP 200; the endpoint answers but the series has not advanced.",
            "NOAA Space Weather Prediction Center", "STEREO-A solar wind",
            swpc_docs, [],
            ("raw_protocol", "No adapter; the feed is stale behind HTTP 200"),
            ["density", "speed", "bz_gsm", "bt"], ["STEREO-A heliocentric orbit (no vertical level)"],
            "Heliocentric; no spatial coordinates are stored or claimed",
            "unknown", "not applicable",
            (False, "none", None), OPEN_US_POLICY,
            "none", "not applicable",
            "Registry tombstone; prevents a false claim of a live STEREO-A feed",
            (False, None, "Unavailable source cannot contribute."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "noaa-swpc-kp-hourly-prediction", "space_weather", "unavailable",
            "SWPC hourly Kp prediction product is stale behind HTTP 200; the endpoint answers but the series has not advanced.",
            "NOAA Space Weather Prediction Center", "Planetary K index, hourly prediction",
            swpc_docs, [],
            ("raw_protocol", "No adapter; the feed is stale behind HTTP 200"),
            ["kp_index_hourly_prediction"], ["planetary index (no vertical level)"],
            "Planetary; no spatial coordinates are stored or claimed",
            "unknown", "not applicable",
            (False, "none", None), OPEN_US_POLICY,
            "none", "not applicable",
            "Registry tombstone; prevents a false claim of a live hourly Kp prediction feed",
            (False, None, "Unavailable source cannot contribute."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "nrcan-stj-magnetometer", "space_weather", "partnership-only",
            "Live over the NRCan FDSN service, but its terms forbid redistribution without written permission. Permission was requested from NRCan on 2026-09-02 alongside the Fort Amherst camera request. Nothing is retrieved until permission is granted.",
            "Natural Resources Canada Geomagnetic Laboratory", "St. John's geomagnetic observatory magnetometer",
            ["https://geomag.nrcan.gc.ca/"], [],
            ("link_only", "No access path until NRCan grants written permission"),
            ["he", "hp", "hn", "total"], ["St. John's geomagnetic observatory (no vertical level)"],
            "St. John's geomagnetic observatory",
            "unknown", "not applicable",
            (False, "none", None), nrcan_stj_policy,
            "none", "not applicable",
            "Local geomagnetic observatory evidence, pending written permission",
            (False, None, "Not a deterministic forecast centre."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "space-weather-canada-regional", "space_weather", "link-only",
            "Regional space weather forecasts from the Canadian Space Weather Forecast Centre are citation only; no data endpoint exists.",
            "Canadian Space Weather Forecast Centre", "Regional space weather forecasts",
            ["https://www.spaceweather.gc.ca/"], [],
            ("link_only", "Citation only; no data endpoint exists"),
            ["citation"], ["not applicable"],
            "Canada",
            "not applicable", "not applicable",
            (False, "none", None), _link_only_policy("https://www.spaceweather.gc.ca/"),
            "none", "not applicable",
            "Citation only, for the reader; no data path",
            (False, None, "Not a deterministic forecast centre."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "nasa-soho-sdo-goes-suvi-imagery", "space_weather", "link-only",
            "Solar imagery from SOHO, SDO and GOES SUVI is for the reader and never a data path.",
            "NASA / NOAA", "SOHO, SDO and GOES SUVI solar imagery",
            ["https://sdo.gsfc.nasa.gov/", "https://soho.nascom.nasa.gov/", "https://www.swpc.noaa.gov/products/goes-solar-ultraviolet-imager-suvi"], [],
            ("link_only", "Imagery for the reader, never a data path"),
            ["citation"], ["not applicable"],
            "Solar disk imagery",
            "not applicable", "not applicable",
            (False, "none", None), _link_only_policy("https://sdo.gsfc.nasa.gov/"),
            "none", "not applicable",
            "Citation only, for the reader; no data path",
            (False, None, "Not a deterministic forecast centre."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
    ])

    # Astronomy: the one pinned static dataset. Its cadence prose deliberately
    # does not parse to a schedule and its freshness is "not applicable", so
    # the ingestion worker never schedules it; the API verifies the local
    # file's sha256 before computing anything from it.
    s.append(_source(
        "nasa-jpl-de442", "astronomy", *_admission("nasa-jpl-de442", "Pinned planetary ephemeris for computed darkness/moon geometry; retrieved once out of band and checksum-verified (sha256 8d5001fab315eeff222cc51f7cf7ffcdb43fb38fb9ac73ff09e09a5b361fd388)."),
        "NASA JPL", "DE442 planetary ephemeris kernel",
        ["https://ssd.jpl.nasa.gov/planets/eph_export.html", "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/aa_summaries.txt"],
        ["https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de442.bsp"],
        ("typed_adapter", "out-of-band fetch script + Skyfield reader against the checksum-verified local file"),
        ["sun_position", "moon_position", "moon_phase", "moon_illuminated_fraction", "twilight_altitudes"],
        ["geocentric/topocentric geometry"],
        "Solar system barycentric ephemeris, 1550-2650",
        "static kernel; pinned release",
        "deterministic geometry over any requested window",
        (False, "Anonymous HTTPS from NAIF", None),
        {"licence": {"name": "United States government public data (NASA)", "url": "https://science.data.nasa.gov/license/", "review_state": "verified"},
         "attribution": "Credit NASA JPL Solar System Dynamics; name the DE release and checksum in derivations.",
         "caching": "One immutable kernel file, checksum-pinned; no repeated retrieval.",
         "archival": "The pinned kernel is the archive; a changed checksum is a different source version.",
         "redistribution": "US government work; redistributable with attribution."},
        "DE442 (2025-02 NAIF export)", "not applicable",
        "Computed astronomical darkness/moon geometry; never blended with weather evidence",
        (False, None, "A pinned ephemeris is not a forecast centre and casts no vote."), delivery_kind="published_cell",
    ))

    # Astronomy: CelesTrak GP element sets and the refused Space-Track
    # alternative (source-admissions-ledger task 5.1, 5.2). Neither id has a
    # registered adapter, so no reach, run cadence, native cadence or
    # publication-latency fields are declared.
    s.extend([
        _source(
            "celestrak-gp", "astronomy",
            *_admission(
                "celestrak-gp",
                "CelesTrak GP element sets are openly served JSON, but the usage policy has not yet been read and "
                "recorded, so admission carries that condition. Satellite passes over the box are derived-here by "
                "local propagation from the retrieved elements and are never fetched as passes.",
            ),
            "CelesTrak", "GP (General Perturbations) element sets",
            ["https://celestrak.org/NORAD/documentation/", "https://celestrak.org/NORAD/documentation/gp-data-formats.php"],
            ["https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=json"],
            ("typed_adapter", "httpx JSON fetch of GP element sets; local SGP4 propagation for pass geometry; no adapter registered yet"),
            ["gp_elements"], ["orbital element set (no vertical level)"],
            "Global catalogue of tracked objects; propagated locally for passes over the box",
            "catalogue updated multiple times daily", "current epoch elements; propagated forward locally for near-term passes",
            (False, "none", None),
            {"licence": {"name": "CelesTrak usage policy, unread", "url": "https://celestrak.org/NORAD/documentation/gp-data-formats.php", "review_state": "pending"},
             "attribution": "Credit CelesTrak pending the policy read.",
             "caching": "Cache bounded element sets within the experiment cap.",
             "archival": "Retain immutable JSON responses for the local experiment window.",
             "redistribution": "Pending the usage policy read."},
            "GP JSON as served", "next catalogue refresh",
            "Orbital element source for locally derived satellite pass geometry",
            (False, None, "Not a deterministic forecast centre."), delivery_kind="published_cell",
            admission_condition={
                "condition": "CelesTrak usage policy has not been read and recorded",
                "satisfied_by": "the policy text and URL recorded on the record, or a licence-blocked decision",
                "satisfied": False,
                "recorded_on": "2026-09-02",
            },
        ),
        _source(
            "space-track", "astronomy", "rejected",
            "Refused; CelesTrak serves the same publicly reachable elements without the Space-Track account terms.",
            "18th Space Defense Squadron / Space-Track.org", "Space-Track element sets",
            ["https://www.space-track.org/documentation"], [],
            ("link_only", "No account created; CelesTrak serves the same elements without the account terms"),
            ["gp_elements"], ["orbital element set (no vertical level)"],
            "Global catalogue of tracked objects",
            "not applicable", "not applicable",
            (False, "none", None),
            {"licence": {"name": "Space-Track user agreement", "url": "https://www.space-track.org/documentation", "review_state": "restricted"},
             "attribution": "Not applicable; nothing is retrieved.",
             "caching": "Not applicable; nothing is retrieved.",
             "archival": "Not applicable; nothing is retrieved.",
             "redistribution": "Not applicable; nothing is retrieved."},
            "none", "not applicable",
            "Registry tombstone; prevents a false claim of a Space-Track access path",
            (False, None, "Unavailable source cannot contribute."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
    ])

    # Aviation, marine/coastal, local transport and optional observations.
    aviation_policy = {"licence": {"name": "AviationWeather.gov terms / US government data", "url": "https://www.aviationweather.gov/data/api/", "review_state": "verified"}, "attribution": "Credit NOAA/NWS Aviation Weather Center and preserve raw report, issue/valid times and station/report identifiers.", "caching": "Respect rate limits; prefer official cache files for broad requests.", "archival": "Up to 30 days are available from the API; local POC retains bounded artifacts only.", "redistribution": "Preserve attribution and any embedded international provider notices."}
    # Only the two records with registered adapters state a native cadence, and
    # each states its own feed's update interval as the Aviation Weather Center
    # documents it in the record's cadence prose: the METAR cache updates every
    # minute but a station reports hourly, and the TAF cache updates every ten
    # minutes. Both reach only their own instant: `aviation` is deliberately
    # outside `ingest.registry.FORECAST_CATEGORIES` because the group mixes TAF
    # with METAR and PIREP, so no lead hours are synthesized for a TAF and what
    # is stored for it is one `forecast_text` artifact. A TAF's own validity
    # interval travels inside the report and is read from there; it is not a
    # reach this deployment can claim to serve frames across.
    aviation_horizon = {
        "awc-metar-speci": {"reach": OBSERVED_INSTANT, "native_cadence_seconds": 3600},
        "awc-taf": {"reach": OBSERVED_INSTANT, "native_cadence_seconds": 600},
    }
    for id, product, endpoint, names, cadence, role in [
        ("awc-metar-speci", "METAR/SPECI", "metar", ["raw_report", "temperature", "dew_point", "wind", "gust", "visibility", "altimeter", "weather_codes", "cloud_layers", "ceiling", "report_type", "quality"], "station/report dependent; cache updates every minute", "CYYT and nearby aviation surface observations"),
        ("awc-taf", "TAF", "taf", ["raw_report", "validity", "wind", "gust", "visibility", "weather", "cloud_layers", "ceiling", "change_groups"], "issuance-dependent; cache updates every 10 minutes", "Supporting human-authored CYYT terminal forecast"),
        ("awc-sigmet-airmet", "SIGMET/AIRMET", "airsigmet", ["raw_report", "hazard", "severity", "validity", "altitude_bounds", "geometry", "movement"], "event/issuance dependent", "Relevant aviation hazard evidence"),
        ("awc-pirep-airep", "PIREP/AIREP", "pirep", ["raw_report", "location", "time", "altitude", "cloud", "turbulence", "icing", "visibility", "temperature", "wind"], "report dependent", "Pilot/aircraft reports over Newfoundland and North Atlantic"),
    ]:
        s.append(_source(id, "aviation", *_admission(id, "Official OpenAPI and endpoint are live; generated client, fixture and smoke tests remain."), "NOAA/NWS Aviation Weather Center", product, ["https://www.aviationweather.gov/data/api/"], [f"https://aviationweather.gov/api/data/{endpoint}"], ("generated_client", "Generate from the pinned official Aviation Weather OpenAPI; python-metar only decodes raw METAR"), names, ["station surface and cloud layers" if "metar" in id else "report-defined vertical bounds/layers"], "Worldwide API; spatial/station filter around CYYT and relevant North Atlantic FIR", cadence, "report/forecast validity; API provides up to previous 30 days", (False, "Anonymous HTTPS with rate limiting", None), aviation_policy, "official OpenAPI version pinned at implementation", "METAR 20 min; TAF one issue cycle; hazard/PIREP 15 min after publication", role, (False, None, "Aviation observations, hazards and human guidance are not independent NWP votes."), delivery_kind="published_cell", **aviation_horizon.get(id, {})))

    smart_policy = {"licence": {"name": "SmartAtlantic dataset-specific ERDDAP terms", "url": "https://www.smartatlantic.ca/erddap/tabledap/SMA_st_johns.html", "review_state": "pending"}, "attribution": "Credit SmartAtlantic and the station/operator attribution returned by ERDDAP.", "caching": "Cache bounded time selections and preserve ERDDAP metadata.", "archival": "Retain immutable CSV/NetCDF response for local experiment window.", "redistribution": "Pending explicit dataset-level rights review; no image/data republication beyond local POC until verified."}
    s.extend([
        _source("smartatlantic-st-johns", "local_buoy", *_admission("smartatlantic-st-johns", "The official ERDDAP dataset is reachable; its reported time coverage currently ends 2026-05-02, so freshness/live continuity must be tested before activation."), "SmartAtlantic Alliance and buoy operator", "St. John's Buoy SMA_st_johns", ["https://www.smartatlantic.ca/erddap/tabledap/SMA_st_johns.html"], ["https://www.smartatlantic.ca/erddap/tabledap/SMA_st_johns.csv"], ("community_client", "IOOS erddapy against official ERDDAP"), ["time", "position", "air_temperature", "humidity_or_dew_point_when_published", "wind", "pressure", "SST", "wave_height", "wave_period", "wave_direction", "quality_fields"], ["buoy atmospheric surface", "sea surface", "wave spectrum/summary when published"], "St. John's buoy location southeast of Avalon", "dataset/platform dependent", "observations only", (False, "Anonymous ERDDAP", None), smart_policy, "ERDDAP 2.26 dataset schema as returned", "2 h and dataset time_coverage_end must advance", "Primary local buoy evidence", (False, None, "Buoy observations are not forecast votes."), delivery_kind="published_cell"),
        _source("smartatlantic-other-validated", "local_buoy", *_admission("smartatlantic-other-validated", "Other stations must pass station identity, sensor and continuity validation before activation. State is per buoy: a station inside the evidence box is admitted at this record's ceiling (implemented-unverified once an adapter claims the id), a station outside the box is catalogued only."), "SmartAtlantic Alliance and station operators", "Other validated SmartAtlantic stations", ["https://www.smartatlantic.ca/erddap/index.html"], ["https://www.smartatlantic.ca/erddap/tabledap/index.json"], ("community_client", "IOOS erddapy"), ["station_metadata", "meteorology", "SST", "waves", "currents", "quality_fields"], ["station-dependent atmospheric/sea surface and water column"], "Atlantic Canadian stations useful to upstream context", "station-dependent", "observations only", (False, "Anonymous ERDDAP", None), smart_policy, "per-dataset ERDDAP schema", "station cadence plus one interval", "Supplemental validated buoy/station evidence", (False, None, "Observations are not votes."), delivery_kind="published_cell"),
        _source("dfo-iwls", "tide_water_level", *_admission("dfo-iwls", "Official Swagger service is public and rate limited; generated client and separation fixtures remain."), "Canadian Hydrographic Service / Fisheries and Oceans Canada", "Integrated Water Level System API", ["https://www.tides.gc.ca/en/web-services-offered-canadian-hydrographic-service"], ["https://api-iwls.dfo-mpo.gc.ca/api/v1/", "https://api-iwls.dfo-mpo.gc.ca/swagger-ui/index.html"], ("generated_client", "Generate from pinned official IWLS OpenAPI; official IWLS_pygeoapi is reference only"), ["station", "height_type", "tide_table_prediction", "observed_water_level", "forecast_water_level", "time_series_definition", "qcFlagCode", "benchmark", "phenomenon"], ["water-level station datum/time series"], "Canadian water-level stations; select St. John's/Avalon", "1/3 minute and lower-resolution series depending on station/product", "prediction/forecast validity from series", (False, "Anonymous HTTPS; 3 requests/s and 30 requests/min", None), {"licence": {"name": "CHS IWLS API licence agreement", "url": "https://www.tides.gc.ca/en/web-services-offered-canadian-hydrographic-service", "review_state": "verified"}, "attribution": "Credit Canadian Hydrographic Service, preserve datum, height type, station and qcFlagCode.", "caching": "Respect per-request temporal limits and API rate limits; cache bounded station series.", "archival": "Immutable API response under local retention window.", "redistribution": "Subject to the IWLS API licence agreement and official-document caveat."}, "official Swagger/OpenAPI version pinned at generation", "two station reporting intervals; forecasts one issue cycle", "Separate tide prediction, observation and forecast water-level layers; surge remains separate", (False, None, "Water-level series are never blended with surge/tide."), delivery_kind="published_cell"),
        _source("nl-511", "transport", "credential-required", "Official API requires a developer key and throttles clients to ten calls per 60 seconds; no credentials requested until adapter tests are ready.", "Government of Newfoundland and Labrador / 511 Newfoundland and Labrador", "NL 511 REST API", ["https://511nl.ca/developers/doc"], ["https://511nl.ca/api/v2/get/roadconditions", "https://511nl.ca/api/v2/get/cameras", "https://511nl.ca/api/v2/get/ferries", "https://511nl.ca/api/v2/get/events", "https://511nl.ca/api/v2/get/advisories"], ("typed_adapter", "httpx + Pydantic typed adapter; no maintained SDK published"), ["road_conditions", "camera_metadata_and_views", "events", "advisories", "ferry_information", "wreckhouse_wind_warnings_when_documented"], ["road segment", "point camera/event/terminal", "advisory area"], "Newfoundland and Labrador; filter Avalon", "event/provider dependent", "current conditions/advisories", (True, "Developer key query parameter", "https://511nl.ca/developers/doc"), {"licence": {"name": "NL 511 API terms", "url": "https://511nl.ca/developers/doc", "review_state": "pending"}, "attribution": "Credit 511 Newfoundland and Labrador and preserve source fields.", "caching": "Do not cache camera imagery until display rights are confirmed; obey 10 calls/60 s.", "archival": "Metadata only under local POC retention unless terms permit more.", "redistribution": "Pending API/camera display-rights review."}, "API v2 response schemas", "15 minutes for conditions/events; camera timestamps must be evaluated", "Transport evidence; no claim of raw RWIS telemetry", (False, None, "Transport evidence is not blended."), "blocked", "blocked", delivery_kind="published_cell", credential={"name": "WEATHER_SECRET_NL511_API_KEY", "registration_url": "https://511nl.ca/developers/doc"}),
        _source("nl-511-rwis", "transport", "unavailable", "The official NL 511 API documentation lists road conditions, cameras, ferries, Wreckhouse warnings, events and advisories, but no raw RWIS telemetry endpoint.", "Government of Newfoundland and Labrador", "Raw RWIS telemetry", ["https://511nl.ca/developers/doc"], ["https://511nl.ca/developers/doc"], ("raw_protocol", "No adapter because no authoritative endpoint is documented"), ["road_surface_temperature", "air_temperature", "wind", "humidity", "surface_condition"], ["hypothetical RWIS station"], "Newfoundland and Labrador", "unknown", "observations only", (False, "No endpoint", None), {"licence": {"name": "Not available for review", "url": "https://511nl.ca/developers/doc", "review_state": "unknown"}, "attribution": "Not applicable until an authoritative endpoint exists.", "caching": "Not applicable.", "archival": "Not applicable.", "redistribution": "Not applicable."}, "none", "not applicable", "Registry tombstone; prevents false RWIS claims", (False, None, "Unavailable source cannot contribute."), "not_applicable", "not_applicable", delivery_kind="published_cell"),
        _source("nav-canada-weather-cameras", "camera", "credential-required", "The public weather camera registry endpoint at weathercams.navcanada.ca is dead, but the owner holds NC-SPACES credentials, which reach the cameras. Fails closed until the key resolves. Follow-up: NC-SPACES hosts more than cameras, so a HITL ticket inventories its products.", "NAV CANADA", "Weather cameras", ["https://weathercams.navcanada.ca/"], ["https://www.navcanada.ca/"], ("typed_adapter", "NC-SPACES authenticated fetch, adapter only after the product inventory (HITL ticket)"), ["camera_page_link", "location", "nominal_direction"], ["camera viewpoint"], "Canadian aerodromes where cameras are offered", "unknown/display dependent", "current image only", (True, "NC-SPACES account held by the owner", "https://www.navcanada.ca/"), {"licence": {"name": "NAV CANADA site terms", "url": "https://www.navcanada.ca/en/terms-of-use.aspx", "review_state": "pending"}, "attribution": "Link to NAV CANADA only.", "caching": "No image caching.", "archival": "No image archival.", "redistribution": "No image redistribution until written rights review passes."}, "website", "unknown", "Link-only visual context", (False, None, "Cameras are not blended."), "blocked", "blocked", delivery_kind="published_cell", credential={"name": "WEATHER_SECRET_NC_SPACES_TOKEN", "registration_url": "https://www.navcanada.ca/"}),
        _source(
            "ccg-harbour-cameras", "camera", "partnership-only",
            "Three harbour cameras (Fort Amherst, St. John's Base, Sir Humphrey Gilbert Building), 20-minute MP4 sequences, "
            "under a courtesy notice that is not a licence: written permission is required before any image is fetched or "
            "stored. Permission was requested from the Canadian Coast Guard for Fort Amherst first, sent 2026-09-02, for the "
            "three harbour cameras and their 20-minute MP4 sequences (docs/research/wayfinder/camera-inventory.md). Nothing "
            "is fetched or stored until permission is recorded.",
            "Canadian Coast Guard", "Harbour camera ice-monitoring MP4 sequences (Fort Amherst, St. John's Base, Sir Humphrey Gilbert Building)",
            ["https://e-navigation.canada.ca/topics/cameras/camera-en?camfile=FortAmherst"], [],
            ("link_only", "No adapter until written permission is recorded"),
            ["camera_image_sequence"], ["camera viewpoint"],
            "St. John's harbour and the Narrows", "not applicable", "not applicable",
            (False, "none", None),
            {"licence": {"name": "these cameras are intented for operational use for the CCG. The images are offered to the public as a courtesy and are for information only", "url": "https://e-navigation.canada.ca/topics/cameras/camera-en?camfile=FortAmherst", "review_state": "restricted"},
             "attribution": "Not applicable; nothing is retrieved until permission is granted.",
             "caching": "Not applicable; nothing is retrieved until permission is granted.",
             "archival": "Not applicable; nothing is retrieved until permission is granted.",
             "redistribution": "Forbidden without the Canadian Coast Guard's written permission."},
            "none", "not applicable",
            "Harbour camera evidence pending written permission; never fetched until granted",
            (False, None, "Cameras are not blended."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "city-st-johns-road-cameras", "camera", "partnership-only",
            "Six road JPEGs with no licence statement on the camera page or its terms page: written permission is "
            "required before any image is fetched or stored. Permission was requested from the City of St. John's for "
            "the six road JPEGs (docs/research/wayfinder/camera-inventory.md). Nothing is fetched or stored until "
            "permission is recorded.",
            "City of St. John's", "Road traffic camera JPEGs",
            ["https://apps.stjohns.ca/accessstjohns/WebCameras.aspx"], [],
            ("link_only", "No adapter until written permission is recorded"),
            ["camera_image"], ["camera viewpoint"],
            "City of St. John's road network", "not applicable", "not applicable",
            (False, "none", None),
            {"licence": {"name": "No licence statement found; terms page not retrievable", "url": "https://www.stjohns.ca/en/city-hall/terms-of-use.aspx", "review_state": "restricted"},
             "attribution": "Not applicable; nothing is retrieved until permission is granted.",
             "caching": "Not applicable; nothing is retrieved until permission is granted.",
             "archival": "Not applicable; nothing is retrieved until permission is granted.",
             "redistribution": "Forbidden without the City of St. John's written permission."},
            "none", "not applicable",
            "Road camera evidence pending written permission; never fetched until granted",
            (False, None, "Cameras are not blended."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "ntv-cameras", "camera", "partnership-only",
            "Eight JPEGs including the only sky-dome camera on the Avalon, with no terms, copyright or privacy page "
            "found anywhere on ntv.ca: all rights are presumed reserved, so written permission is required before any "
            "image is fetched or stored. Permission was requested from NTV for the eight JPEGs "
            "(docs/research/wayfinder/camera-inventory.md). Nothing is fetched or stored until permission is recorded.",
            "NTV (Newfoundland Broadcasting)", "St. John's Sky and seven other JPEG cameras",
            ["https://ntv.ca/"], [],
            ("link_only", "No adapter until written permission is recorded"),
            ["camera_image"], ["camera viewpoint"],
            "St. John's, Quidi Vidi, Conception Bay and Pippy Park", "not applicable", "not applicable",
            (False, "none", None),
            {"licence": {"name": "No terms page anywhere on ntv.ca; all rights presumed reserved", "url": "https://ntv.ca/", "review_state": "restricted"},
             "attribution": "Not applicable; nothing is retrieved until permission is granted.",
             "caching": "Not applicable; nothing is retrieved until permission is granted.",
             "archival": "Not applicable; nothing is retrieved until permission is granted.",
             "redistribution": "Forbidden without NTV's written permission."},
            "none", "not applicable",
            "Sky-dome and street camera evidence pending written permission; never fetched until granted",
            (False, None, "Cameras are not blended."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
    ])

    optional_policy = {"licence": {"name": "Provider/dataset-specific terms", "url": "https://madis.ncep.noaa.gov/madis_restrictions.shtml", "review_state": "restricted"}, "attribution": "Preserve network and original provider attribution on every observation.", "caching": "Cache only QC-passing bounded observations and respect provider restrictions.", "archival": "Local short retention only where permitted.", "redistribution": "Dataset-specific; restricted records must not be redistributed."}
    s.extend([
        _source("noaa-madis", "optional_observation", "credential-required", "MADIS requests an account and assigns distribution categories; some mesonets restrict redistribution.", "NOAA/NCEP and contributing networks", "MADIS quality-controlled observations", ["https://madis-data.ncep.noaa.gov/index.html", "https://madis.ncep.noaa.gov/madis_restrictions.shtml"], ["https://madis-data.ncep.noaa.gov/"], ("typed_adapter", "official NetCDF/HTTP protocol adapter; preserve provider/QC metadata"), ["surface_meteorology", "radiosonde", "profiler", "satellite_wind", "quality_control_flags", "provider"], ["station surface", "reported vertical profile levels"], "Global/contributor dependent", "network dependent", "observations only", (True, "MADIS account and assigned distribution category", "https://madis-data.ncep.noaa.gov/index.html"), optional_policy, "MADIS NetCDF dataset schema", "network cadence plus one interval", "Optional QC observations only", (False, None, "Optional observations are not votes."), "blocked", "blocked", delivery_kind="reprocessed", credential={"name": "WEATHER_SECRET_MADIS_TOKEN", "registration_url": "https://madis-data.ncep.noaa.gov/index.html"}, intermediary={"name": "NOAA MADIS", "method": None, "transformations": ["Ingests observations from contributing mesonets, networks and agencies and re-serves them in MADIS's own NetCDF encoding rather than the originating network's.", "Applies MADIS's own quality-control checks and attaches its QC flags, which the originating network did not issue.", "Assigns a distribution category that decides which observations a given account may receive at all."]}),
        _source("raw-cwop-pws", "optional_observation", "catalogued", "Raw personal stations require aggressive QC, separate symbology and verified provider rights before use. Licence review closes as admitted once the CWOP licence text is read and recorded; until then the record carries the unread-terms condition." + CATALOGUED_UNTIL_ADAPTER, "Citizen Weather Observer Program / individual station providers", "Raw CWOP and personal weather station observations", ["https://www.weather.gov/media/epz/mesonet/CWOP-Official-Guide.pdf"], ["https://www.findu.com/cgi-bin/wxnear.cgi"], ("typed_adapter", "No production adapter until authoritative machine endpoint and licence are pinned"), ["temperature", "dew_point", "humidity", "wind", "pressure", "precipitation", "station_metadata"], ["station surface"], "Station dependent", "station dependent", "observations only", (False, "Endpoint-dependent", None), optional_policy, "unversioned station protocol candidate", "station cadence plus two intervals", "Optional aggressively QC'd observations with distinct symbology", (False, None, "PWS evidence is not blended."), "blocked", "blocked", delivery_kind="reprocessed", intermediary={"name": "findu.com", "method": None, "transformations": ["Collects the station providers' APRS/CWOP packets from the network and re-serves them as its own nearest-station listing.", "Decodes and re-encodes each packet's units and fields; the originating station's raw packet is not what is returned.", "Documents no transformation of its own, which is precisely why this record stays catalogued with no adapter: a reprocessed declaration is only honest when the intermediary documents what it did."]}, admission_condition={"condition": "The CWOP licence text has not been read and recorded.", "satisfied_by": "The terms text and URL recorded in a restricted_terms block, or a licence-blocked decision if the terms forbid admission.", "satisfied": False, "recorded_on": "2026-09-02"}),
        _source("purpleair", "optional_air_quality", "credential-required", "Optional only after API credentials, licence and sensor-QC policy are ready.", "PurpleAir", "PurpleAir sensor observations", ["https://api.purpleair.com/"], ["https://api.purpleair.com/v1/sensors"], ("typed_adapter", "httpx + Pydantic official API adapter"), ["PM1", "PM2.5", "PM10", "humidity", "temperature", "sensor_metadata", "confidence_fields"], ["sensor surface"], "Sensor dependent", "sensor/API dependent", "observations only", (True, "PurpleAir API key", "https://develop.purpleair.com/keys"), {**optional_policy, "licence": {"name": "PurpleAir API terms", "url": "https://develop.purpleair.com/terms", "review_state": "pending"}}, "PurpleAir API v1", "30 minutes", "Optional distinct low-cost sensor layer", (False, None, "Sensor observations are not blended."), "blocked", "blocked", delivery_kind="published_cell", credential={"name": "WEATHER_SECRET_PURPLEAIR_API_KEY", "registration_url": "https://develop.purpleair.com/keys"}),
        _source("openaq", "optional_air_quality", "credential-required", "Optional after API credentials, per-location provenance and licence review.", "OpenAQ and upstream monitoring agencies", "OpenAQ observations", ["https://docs.openaq.org/"], ["https://api.openaq.org/v3/"], ("typed_adapter", "httpx + Pydantic official REST adapter"), ["PM2.5", "PM10", "ozone", "NO2", "SO2", "CO", "sensor_or_reference_metadata"], ["monitoring location surface"], "Global; availability around St. John's must be verified", "source dependent", "observations only", (True, "OpenAQ API key", "https://explore.openaq.org/register"), {**optional_policy, "licence": {"name": "OpenAQ platform and upstream-source terms", "url": "https://openaq.org/about/terms/", "review_state": "pending"}}, "OpenAQ API v3", "source cadence plus one interval", "Optional air-quality observations preserving upstream provenance", (False, None, "Observations are not blended."), "blocked", "blocked", delivery_kind="reprocessed", credential={"name": "WEATHER_SECRET_OPENAQ_API_KEY", "registration_url": "https://explore.openaq.org/register"}, intermediary={"name": "OpenAQ", "method": None, "transformations": ["Ingests measurements from upstream monitoring agencies and re-serves them under OpenAQ's own location and sensor identifiers.", "Harmonises units and parameter names across agencies that publish neither the same way.", "Applies its own averaging and aggregation windows to series the agencies published on their own cadences."]}),
        _source(
            "netatmo", "optional_observation", "catalogued",
            "Catalogued only." + CATALOGUED_UNTIL_ADAPTER,
            "Netatmo", "Netatmo personal weather station network",
            ["https://dev.netatmo.com/"], [],
            ("link_only", "No adapter; catalogued only"),
            ["citation"], ["not applicable"],
            "Global citizen station network", "not applicable", "not applicable",
            (True, "OAuth2 developer application", "https://dev.netatmo.com/"),
            {**optional_policy, "licence": {"name": "Netatmo developer terms, unread", "url": "https://dev.netatmo.com/", "review_state": "unknown"}},
            "none", "not applicable",
            "Optional citizen station network; catalogued only, never a data path",
            (False, None, "Uncalibrated citizen observations are not forecast votes."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source(
            "weather-underground", "optional_observation", "catalogued",
            "Catalogued only." + CATALOGUED_UNTIL_ADAPTER,
            "The Weather Company / IBM", "Weather Underground personal weather station network",
            ["https://www.wunderground.com/"], [],
            ("link_only", "No adapter; catalogued only"),
            ["citation"], ["not applicable"],
            "Global citizen station network", "not applicable", "not applicable",
            (True, "Commercial API key", "https://www.wunderground.com/"),
            {**optional_policy, "licence": {"name": "Weather Underground / IBM terms, unread", "url": "https://www.wunderground.com/", "review_state": "unknown"}},
            "none", "not applicable",
            "Optional citizen station network; catalogued only, never a data path",
            (False, None, "Uncalibrated citizen observations are not forecast votes."),
            "not_applicable", "not_applicable", delivery_kind="published_cell",
        ),
        _source("provincial-hydrometric", "hydrology", "catalogued", "No stable authoritative provincial machine endpoint has yet been verified for the selected Avalon stations. Licence review closed as catalogued only.", "Government of Newfoundland and Labrador", "Provincial hydrometric network", ["https://www.gov.nl.ca/ecc/waterres/flooding/hydrometric/"], ["https://www.gov.nl.ca/ecc/waterres/flooding/hydrometric/"], ("link_only", "Link-only pending a stable machine endpoint"), ["water_level", "discharge", "station_metadata", "quality_flags"], ["gauging station"], "Newfoundland and Labrador", "unknown", "observations only", (False, "Unknown", None), {**optional_policy, "licence": {"name": "Government of Newfoundland and Labrador site/data terms", "url": "https://www.gov.nl.ca/disclaimer/", "review_state": "pending"}}, "unknown", "unknown", "Candidate supplemental hydrology", (False, None, "Not active and not blended."), "blocked", "blocked", delivery_kind="published_cell"),
        _source("municipal-hydrometric", "hydrology", "unavailable", "No stable authoritative municipal machine endpoint or named network was supplied or discovered for this POC audit.", "Applicable Avalon municipalities", "Municipal hydrometric networks", ["https://www.stjohns.ca/en/water-and-wastewater/water-and-wastewater.aspx"], ["https://www.stjohns.ca/en/water-and-wastewater/water-and-wastewater.aspx"], ("link_only", "No adapter until a real endpoint and provider are identified"), ["water_level", "flow", "quality_flags"], ["municipal station"], "Avalon municipalities", "unknown", "observations only", (False, "No endpoint", None), {**optional_policy, "licence": {"name": "Unknown", "url": "https://www.stjohns.ca/en/city-hall/terms-of-use.aspx", "review_state": "unknown"}}, "none", "not applicable", "Registry placeholder with explicit unavailable status", (False, None, "Unavailable source cannot contribute."), "not_applicable", "not_applicable", delivery_kind="published_cell"),
    ])
    # The Open-Meteo and Bright Sky admissions of the 2026-09-02 ledger. Every
    # one of them is `reprocessed`: the producer is a national centre or a
    # research centre, the intermediary is the aggregator, and the six
    # documented transformations are named on each record because a
    # `reprocessed` declaration is only honest if the intermediary documents
    # what it did. None of these ids has a registered adapter, so each is
    # written `catalogued` by the Decision 1 rule with the admission recorded in
    # its reason.
    s.extend([
        _source(
            "openmeteo-cams-aod", "air_quality",
            *_admission(
                "openmeteo-cams-aod",
                "The only aerosol optical depth reachable over the box without a credential: GeoMet publishes no AOD at all and every direct CAMS path is credential-gated (the ADS execute call and the NASA MAIAC and VIIRS granule GETs all return HTTP 401 anonymously), so this delivery closes a gap nothing else closes ("
                + ENDPOINT_RESEARCH
                + " section 2.4). Total AOD at 550 nm only, with no speciation, so sea-salt AOD, the term that matters most in a maritime box, is not served. Two runs a day (00Z and 12Z) published at T+10 h 16 m, hourly steps, about 4 days of usable forward reach. The record declares the 0.1 versus 0.4 degree upsampling trap rather than leaving it to be discovered: CAMS global publishes a 0.4 degree grid and Open-Meteo returns cell centres stepping in 0.1 degree, so a stored value looks like a 0.1 degree field and is not one; the native 0.4 degree grid is what this record claims. Reprocessed, so never the display primary and never a derivation input."
                + OPEN_METEO_BEST_MATCH_REFUSAL,
            ),
            "ECMWF Copernicus Atmosphere Monitoring Service (CAMS)",
            "CAMS global atmospheric composition forecast delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/air-quality-api", "https://atmosphere.copernicus.eu/"],
            ["https://air-quality-api.open-meteo.com/v1/air-quality"],
            ("typed_adapter", "httpx + Pydantic adapter reading data/cams_global/static/meta.json beside every call; no adapter is registered yet"),
            ["aerosol_optical_depth"], ["total column"],
            "CAMS global 0.4 degree grid served at 0.1 degree cell centres; queried per point over the evidence box",
            "two runs a day (00Z and 12Z), hourly steps, published at about T+10 h 16 m",
            "about 4 days of non-null forward reach; the trailing hours of a 7-day request return null with no marker",
            (False, "none", None),
            _open_meteo_policy(
                "credit ECMWF CAMS as the producer of the composition forecast. The upstream ADS licence dispute recorded on copernicus-cams is inherited here: if it reaches this delivery the record is re-read.",
            ),
            "Open-Meteo air-quality JSON as served; the CAMS cycle version is not exposed",
            "run initialisation time read from meta.json, no older than two 12 h cycles",
            "Aerosol optical depth evidence for sky transparency; never the display primary and never a derivation input",
            (False, None, "A reprocessed composition field is not a centre vote."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the CAMS global composition forecast and re-serves it as point time series on its own grid.",
                (
                    "The 0.4 degree CAMS global grid is served at 0.1 degree cell centres, an upsample; whether it interpolates or repeats the nearest cell is undocumented.",
                ),
            ),
        ),
        _source(
            "openmeteo-lsa-saf-radiation", "analysis",
            *_admission(
                "openmeteo-lsa-saf-radiation",
                "Direct, diffuse and DNI irradiance with a real instantaneous split, which no native source over the box publishes: every model on GeoMet publishes accumulated or averaged shortwave only, so the wet-bulb globe temperature input is missing and this is the only route to it ("
                + ENDPOINT_RESEARCH
                + " section 3.3). The hour-mean and _instant series genuinely differ (159.0 against 185.9 W/m2 at the same hour), so the distinction is carried rather than cosmetic. About 1 h latency, hourly, 0.05 degree. Archive endpoint only: satellite-api /v1/archive has no forward reach, and the beam split served by api.open-meteo.com /v1/forecast is a different quantity, an intermediary's decomposition of a producer's total with no method named, which is refused separately and must never be merged with these values (section 3.4). Admission is conditional on the unmeasured Meteosat limb-geometry cost at 52.7 W. Reprocessed, so never the display primary and never a derivation input."
                + OPEN_METEO_BEST_MATCH_REFUSAL,
            ),
            "EUMETSAT LSA SAF",
            "LSA SAF surface radiation from Meteosat MSG/SEVIRI (eumetsat_lsa_saf_msg) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/satellite-radiation-api", "https://landsaf.ipma.pt/en/"],
            ["https://satellite-api.open-meteo.com/v1/archive"],
            ("typed_adapter", "httpx + Pydantic adapter against the satellite archive endpoint; no adapter is registered yet"),
            ["shortwave_radiation", "direct_radiation", "diffuse_radiation", "direct_normal_irradiance", "global_tilted_irradiance", "terrestrial_radiation"],
            ["surface", "hour mean and instantaneous series"],
            "Meteosat 0 degree disc at 0.05 degree; the evidence box sits near the western limb",
            "hourly, at about 1 h latency behind the observation",
            "archive only; the endpoint has no forward reach",
            (False, "none", None),
            _open_meteo_policy("credit EUMETSAT LSA SAF as the producer of the surface radiation retrieval."),
            "Open-Meteo satellite archive JSON as served",
            "latest hour no older than 3 h",
            "Instantaneous direct-beam irradiance for the running profile; never the display primary and never a derivation input",
            (False, None, "A satellite radiation retrieval is not a forecast centre vote."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the LSA SAF MSG surface radiation retrieval and re-serves it as hourly point time series, carrying both the hour-mean and the instantaneous convention.",
            ),
            admission_condition={
                "condition": "Meteosat limb-geometry cost at 52.7 W over the evidence box is unmeasured",
                "satisfied_by": "a recorded comparison of the LSA SAF direct, diffuse and DNI values against a surface radiation reference or a documented view-angle mask over the box",
                "satisfied": False,
                "recorded_on": "2026-09-02",
            },
        ),
        _source(
            "openmeteo-gfs-wave", "wave",
            *_admission(
                "openmeteo-gfs-wave",
                "The only wave field reachable over the box: no native path publishes significant wave height, period, direction or a swell partition, and no marine SWOB station exists inside the box, so sea state today is the SmartAtlantic buoy or nothing ("
                + ENDPOINT_RESEARCH
                + " section 1.6). Model ncep_gfswave016, the NOAA/NCEP GFS-Wave Atlantic and Arctic 0.16 degree grid, admitted over the alternatives because it carries the swell and wind-wave partition that ecmwf_wam lacks and combines T+5 h 21 m latency, hourly steps, a 16-day reach and the finest grid of the wave set. cell_selection=sea is mandatory: the default land-preferring cell over a coastal point returns a silent column of nulls, and an all-null column is a retrieval failure, not calm. Reprocessed, so never the display primary and never a derivation input."
                + OPEN_METEO_BEST_MATCH_REFUSAL,
            ),
            "NOAA NCEP",
            "GFS-Wave Atlantic and Arctic 0.16 degree (ncep_gfswave016) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/marine-weather-api", "https://polar.ncep.noaa.gov/waves/"],
            ["https://marine-api.open-meteo.com/v1/marine"],
            ("typed_adapter", "httpx + Pydantic adapter sending cell_selection=sea and reading meta.json beside every call; no adapter is registered yet"),
            ["wave_height", "wave_period", "wave_direction", "swell_wave_height", "swell_wave_period", "swell_wave_direction", "wind_wave_height", "wind_wave_period", "wind_wave_direction"],
            ["sea surface"],
            "0.16 degree Atlantic and Arctic wave grid; the evidence box is inside its latitude bound, just",
            "four runs a day, hourly steps, published at about T+5 h 21 m",
            "16 days",
            (False, "none", None),
            _open_meteo_policy("credit NOAA NCEP as the producer of the GFS-Wave forecast."),
            "Open-Meteo marine JSON as served",
            "run initialisation time read from meta.json, no older than two 6 h cycles",
            "Sea state evidence for the marine sectors; never the display primary and never a derivation input",
            (False, None, "A wave model is not a comparable deterministic centre vote for the atmospheric fields."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the NCEP GFS-Wave 0.16 degree grid and re-serves it as hourly point time series.",
                (
                    "cell_selection=sea is mandatory; the default nearest cell over a coastal point is land and returns null",
                ),
            ),
        ),
    ])

    # Three foreign global models that this stack has no other route to, plus
    # the DWD MOSMIX station point. They add spread rather than detail, and the
    # UKMO row is admitted for research use only because its upstream licence is
    # CC BY-SA and a share-alike obligation is not something this deployment can
    # grant onward.
    s.extend([
        _source(
            "openmeteo-jma-gsm", "deterministic_forecast",
            *_admission(
                "openmeteo-jma-gsm",
                "A third independent global model over the box, reachable here only through an aggregator: JMA publishes no open path this deployment can read, and the 2026-09-02 probe returned live values (62, 62, 63 percent cloud, run 2026-09-01 18z at a 9.54 h lag) through Open-Meteo's jma_gsm domain ("
                + AGGREGATOR_RESEARCH
                + " section 5). Admitted for spread, not for detail. The six documented Open-Meteo transformations are named on this record, and the run stamp comes from data/jma_gsm/static/meta.json beside every call, because the forecast response body carries no run reference at all. Reprocessed, so never the display primary and never a derivation input."
                + OPEN_METEO_BEST_MATCH_REFUSAL,
            ),
            "Japan Meteorological Agency",
            "JMA GSM global model (jma_gsm) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/jma-api", "https://www.jma.go.jp/jma/en/Activities/nwp.html"],
            ["https://api.open-meteo.com/v1/forecast"],
            ("typed_adapter", "httpx + Pydantic adapter sending elevation=nan and an explicit cell_selection, reading meta.json beside every call; no adapter is registered yet"),
            ["air_temperature", "dew_point", "relative_humidity", "total_cloud", "low_cloud", "middle_cloud", "high_cloud", "wind_speed", "wind_direction", "mean_sea_level_pressure", "precipitation"],
            ["surface", "2 m", "10 m"],
            "Global; queried per point over the evidence box",
            "producer run cycles as Open-Meteo exposes them in meta.json; measured once at a 9.54 h lag",
            "as published by the domain; not enumerated for this deployment",
            (False, "none", None),
            _open_meteo_policy("credit the Japan Meteorological Agency as the producer of GSM."),
            "Open-Meteo forecast JSON as served; the producer's cycle version is not exposed",
            "run initialisation time read from meta.json, no older than two producer cycles",
            "Independent foreign global model for spread; never the display primary and never a derivation input",
            (False, None, "A reprocessed delivery cannot stand as a centre's vote: the value is not the producer's own cell."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the JMA GSM global model and re-serves it as point time series on its own regular grid.",
            ),
        ),
        _source(
            "openmeteo-arpege", "deterministic_forecast",
            *_admission(
                "openmeteo-arpege",
                "A fourth independent global model over the box on the same terms as JMA GSM: reachable here only through Open-Meteo's meteofrance_arpege_world025 domain, which returned live values (25, 31, 19 percent cloud, run 2026-09-02 00z at a 4.20 h lag) on 2026-09-02 ("
                + AGGREGATOR_RESEARCH
                + " section 5). Admitted for spread, not for detail. The six documented Open-Meteo transformations are named on this record, and the run stamp comes from data/meteofrance_arpege_world025/static/meta.json beside every call. Reprocessed, so never the display primary and never a derivation input."
                + OPEN_METEO_BEST_MATCH_REFUSAL,
            ),
            "Meteo-France",
            "ARPEGE world 0.25 degree (meteofrance_arpege_world025) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/meteofrance-api", "https://meteofrance.com/"],
            ["https://api.open-meteo.com/v1/forecast"],
            ("typed_adapter", "httpx + Pydantic adapter sending elevation=nan and an explicit cell_selection, reading meta.json beside every call; no adapter is registered yet"),
            ["air_temperature", "dew_point", "relative_humidity", "total_cloud", "low_cloud", "middle_cloud", "high_cloud", "wind_speed", "wind_direction", "mean_sea_level_pressure", "precipitation"],
            ["surface", "2 m", "10 m"],
            "Global 0.25 degree; queried per point over the evidence box",
            "producer run cycles as Open-Meteo exposes them in meta.json; measured once at a 4.20 h lag",
            "as published by the domain; not enumerated for this deployment",
            (False, "none", None),
            _open_meteo_policy("credit Meteo-France as the producer of ARPEGE."),
            "Open-Meteo forecast JSON as served; the producer's cycle version is not exposed",
            "run initialisation time read from meta.json, no older than two producer cycles",
            "Independent foreign global model for spread; never the display primary and never a derivation input",
            (False, None, "A reprocessed delivery cannot stand as a centre's vote: the value is not the producer's own cell."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the Meteo-France ARPEGE world 0.25 degree model and re-serves it as point time series on its own grid.",
            ),
        ),
        _source(
            "openmeteo-ukmo-global", "deterministic_forecast",
            *_admission(
                "openmeteo-ukmo-global",
                "A fifth independent global model over the box, live through Open-Meteo's ukmo_global_deterministic_10km domain (20, 19, 36 percent cloud, run 2026-09-01 18z at a 7.43 h lag, 2026-09-02) and reachable no other way here ("
                + AGGREGATOR_RESEARCH
                + " sections 3 and 5). Admitted for research use only: Open-Meteo's own licence page records UK Met Office data as CC BY-SA 4.0, a share-alike obligation this deployment cannot grant onward, so the terms are recorded verbatim, redistribution is refused, and the values are served only to the owner's own reader. The six documented Open-Meteo transformations are named on this record. Reprocessed, so never the display primary and never a derivation input."
                + OPEN_METEO_BEST_MATCH_REFUSAL,
            ),
            "UK Met Office",
            "UKMO global deterministic 10 km (ukmo_global_deterministic_10km) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/ukmo-api", "https://www.metoffice.gov.uk/"],
            ["https://api.open-meteo.com/v1/forecast"],
            ("typed_adapter", "httpx + Pydantic adapter sending elevation=nan and an explicit cell_selection, reading meta.json beside every call; no adapter is registered yet"),
            ["air_temperature", "dew_point", "relative_humidity", "total_cloud", "low_cloud", "middle_cloud", "high_cloud", "wind_speed", "wind_direction", "mean_sea_level_pressure", "precipitation"],
            ["surface", "2 m", "10 m"],
            "Global 10 km; queried per point over the evidence box",
            "producer run cycles as Open-Meteo exposes them in meta.json; measured once at a 7.43 h lag",
            "as published by the domain; not enumerated for this deployment",
            (False, "none", None),
            _open_meteo_policy(
                "credit the UK Met Office as the producer and carry the CC BY-SA 4.0 notice with every stored value.",
                licence_name="UK Met Office data delivered by Open-Meteo under CC BY-SA 4.0; the share-alike clause is not granted onward by this deployment",
                licence_url="https://open-meteo.com/en/docs/ukmo-api",
                review_state="restricted",
                redistribution="Not redistributed. CC BY-SA 4.0 would oblige this deployment to share any derived product under the same licence, which it does not grant, so the values are served only to the owner's own reader.",
            ),
            "Open-Meteo forecast JSON as served; the producer's cycle version is not exposed",
            "run initialisation time read from meta.json, no older than two producer cycles",
            "Independent foreign global model for spread, research use only; never the display primary and never a derivation input",
            (False, None, "Research-use-only values may not stand as a centre's vote, and a reprocessed delivery could not in any case."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the UKMO global deterministic 10 km model and re-serves it as point time series on its own grid.",
            ),
            restricted_terms={
                "terms_text": "UK Met Office data on Open-Meteo is licensed CC BY-SA 4.0: derived products must be shared under the same licence, which this deployment does not grant onward",
                "terms_source_url": "https://open-meteo.com/en/docs/ukmo-api",
                "redistribution": False,
                "read_date": "2026-09-02",
            },
        ),
        _source(
            "brightsky-dwd-mosmix-71801", "postprocessed_forecast",
            *_admission(
                "brightsky-dwd-mosmix-71801",
                "The best value per declaration in the aggregator ticket: DWD MOSMIX station 71801 (ST.JOHNS NEUFUNDL., 47.62 N 52.73 W, 134 m, 6 642 m from the box's reference point) is the only new source carrying visibility and dew point at a St. John's point out to ten days, and the in-situ fog evidence gap is the hardest one in the box ("
                + AGGREGATOR_RESEARCH
                + " sections 3 and 7). Producer DWD, intermediary Bright Sky, which parses the MOSMIX KMZ into JSON and returns the station it chose with its distance, so the selection is inspectable per response. MOSMIX's own statistical post-processing is DWD's, which is why the producer is DWD and not Bright Sky. Several elements (relative humidity, sunshine, solar, gusts, probabilities) came back null at this station, so the element set is narrower than the API schema and a null is the station's, not a failure. Being a station point rather than a grid it does not compete with HRDPS for the map surface. Reprocessed, so never the display primary and never a derivation input.",
            ),
            "Deutscher Wetterdienst",
            "MOSMIX_L station point forecast for WMO station 71801, delivered by Bright Sky",
            ["https://brightsky.dev/docs/", "https://www.dwd.de/EN/ourservices/met_application_mosmix/met_application_mosmix.html"],
            ["https://api.brightsky.dev/weather"],
            ("typed_adapter", "httpx + Pydantic adapter reading the returned sources block for the station id and its distance; no adapter is registered yet"),
            ["air_temperature", "dew_point", "relative_humidity", "total_cloud", "visibility", "mean_sea_level_pressure", "wind_speed", "wind_direction", "wind_gust_speed", "precipitation", "precipitation_probability", "sunshine", "solar", "condition"],
            ["station surface"],
            "WMO station 71801 at 47.62 N 52.73 W; a point, not a grid",
            "hourly records; the MOSMIX cycle and its latency were not measured for this deployment",
            "about ten days from the issue time",
            (False, "none", None),
            BRIGHT_SKY_POLICY,
            "Bright Sky JSON as served, with the MOSMIX element set for this station narrower than the schema",
            "latest record no older than 6 h",
            "Station visibility and dew point to ten days; never the display primary and never a derivation input",
            (False, None, "A station post-processing product delivered by an intermediary is not a centre's raw-model vote."),
            delivery_kind="reprocessed",
            intermediary={
                "name": "Bright Sky",
                "method": "parse of DWD MOSMIX KMZ into JSON and nearest-station selection",
                "transformations": [
                    "KMZ to JSON parse of the MOSMIX_L product",
                    "station 71801 selected by id; no spatial interpolation",
                    "DWD's own MOSMIX statistical post-processing precedes the intermediary and is the producer's, not Bright Sky's",
                ],
            },
        ),
    ])

    # Three aggregator domains that resolve, answer HTTP 200 and carry nothing
    # usable over this box. They are recorded rather than omitted because the
    # failure mode is silence: a stale or flat domain returns a well-formed
    # response, and the next person to reach for a foreign model would find the
    # name valid and the values wrong. Each carries the delivery kind the route
    # would have had, so no reader mistakes an absent path for a producer path.
    for id, producer, product, domain, reason in [
        (
            "openmeteo-kma-gdps",
            "Korea Meteorological Administration",
            "KMA GDPS global model (kma_gdps) delivered by Open-Meteo",
            "kma_gdps",
            "Stale since March 2026 behind HTTP 200: last_run_initialisation_time is 2026-03-31 18z and data_end_time 2026-04-04, five months old when read, so every hour over the box came back null while the response stayed well formed and said nothing about the domain having stopped ("
            + AGGREGATOR_RESEARCH
            + " section 5). The same shape as the SWPC stale-but-HTTP-200 records. Unavailable, with no access path declared, until a probe shows the domain updating again.",
        ),
        (
            "openmeteo-cma-grapes",
            "China Meteorological Administration",
            "CMA GRAPES global model (cma_grapes_global) delivered by Open-Meteo",
            "cma_grapes_global",
            "Flat values over the box: cloud cover came back exactly 0 percent for all 24 hours probed on 2026-09-02, beside ICON at 62 to 67 percent and GEM at 56 percent for the same hours, which is not credible for a September night on the Avalon ("
            + AGGREGATOR_RESEARCH
            + " section 5). Either the field is not what it is labelled or the domain is degraded; unresolved, so the record declares no access path rather than serving a zero somebody would read as clear sky.",
        ),
        (
            "openmeteo-graphcast",
            "NOAA and Google DeepMind",
            "GraphCast 0.25 degree (gfs_graphcast025) delivered by Open-Meteo",
            "gfs_graphcast025",
            "Null over the box: the model name resolves and the response is well formed, but every hour probed on 2026-09-02 was null and the domain's meta.json carries no run fields at all, so neither the values nor their vintage exist ("
            + AGGREGATOR_RESEARCH
            + " section 5). Unavailable, with no access path declared.",
        ),
    ]:
        s.append(_source(
            id, "deterministic_forecast", "unavailable", reason + OPEN_METEO_BEST_MATCH_REFUSAL,
            producer, product,
            ["https://open-meteo.com/en/docs"],
            [],
            ("link_only", f"No adapter and no client: the {domain} domain answers HTTP 200 and carries nothing usable over the box"),
            ["total_cloud"], ["surface"],
            "Global as documented; nothing usable over the evidence box",
            "not applicable: the domain does not deliver over this box",
            "not applicable: the domain does not deliver over this box",
            (False, "none", None),
            _open_meteo_policy(f"credit {producer} as the producer, were the domain ever to deliver."),
            "Open-Meteo forecast JSON as served",
            "not applicable while the record is unavailable",
            "Recorded so a silent aggregator failure is a registry fact rather than a rediscovery",
            (False, None, "An unavailable source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                f"Open-Meteo would ingest the {domain} domain and re-serve it as point time series; over this box it delivers nothing.",
            ),
        ))

    # The Open-Meteo endpoints ticket 28 catalogued: each works, each was
    # measured live on 2026-09-02, and none of them fills a gap a research file
    # names. They are declared so the decision is a registry fact and the next
    # reader does not re-probe them. `catalogued` here is the owner's decision,
    # not the migration rule, so no sentence about a waiting adapter is
    # appended: nothing is waiting.
    s.extend([
        _source(
            "openmeteo-air-quality-particulates", "air_quality", "catalogued",
            "Works and is not needed: PM2.5, PM10, ozone, NO2, SO2, CO and dust all returned 72 of 72 non-null over the box on 2026-09-02, but RAQDPS is native and stays the primary for every one of them, so this is a cross-centre comparison rather than a gap ("
            + ENDPOINT_RESEARCH
            + " sections 2.3 and 2.4). Catalogued with the resolution caveat recorded: CAMS global publishes 0.4 degree and Open-Meteo returns 0.1 degree cell centres, so neighbouring stored cells may be four copies of one value. Ingest only if the running profile later asks for a second opinion on PM."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "ECMWF Copernicus Atmosphere Monitoring Service (CAMS)",
            "CAMS global particulate, gas and dust fields delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/air-quality-api", "https://atmosphere.copernicus.eu/"],
            ["https://air-quality-api.open-meteo.com/v1/air-quality"],
            ("link_only", "Catalogued only: no adapter and no client until a profile asks for a second opinion on PM"),
            ["pm2_5", "pm10", "ozone", "nitrogen_dioxide", "sulphur_dioxide", "carbon_monoxide", "dust"],
            ["surface"],
            "CAMS global 0.4 degree grid served at 0.1 degree cell centres; queried per point over the evidence box",
            "two runs a day (00Z and 12Z), hourly steps",
            "about 4 days of non-null forward reach",
            (False, "none", None),
            _open_meteo_policy("credit ECMWF CAMS as the producer of the composition forecast."),
            "Open-Meteo air-quality JSON as served",
            "not applicable while the record is catalogued only",
            "Catalogued cross-centre comparison for air quality; RAQDPS remains the primary",
            (False, None, "A reprocessed composition field is not a centre vote."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the CAMS global composition forecast and re-serves it as point time series on its own grid.",
                (
                    "The 0.4 degree CAMS global grid is served at 0.1 degree cell centres, an upsample; whether it interpolates or repeats the nearest cell is undocumented.",
                ),
            ),
        ),
        _source(
            "openmeteo-marine-currents-sealevel", "ocean", "catalogued",
            "Catalogued because the producer cannot be declared truthfully, which is what a reprocessed record must do before anything else. The values work (SST 16.0 degrees C, current 1.0 km/h toward 158 degrees, sea level -0.14 m at 47.6 N 52.6 W, 72 of 72 non-null on 2026-09-02) and this is the only domain on the marine endpoint carrying SST, currents and sea level at all; but Open-Meteo labels meteofrance_currents Meteo-France while the field set reads as a Mercator Ocean or Copernicus Marine global analysis, and its meta.json carries no producer string ("
            + ENDPOINT_RESEARCH
            + " sections 1.2 and 1.5). The same reasoning refused Meteosource: if the declaration cannot be written truthfully, the class does not apply. Reading Open-Meteo's marine attribution and the upstream licence would resolve it. No admitted activity profile scores currents or sea level today either."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "undeclarable: Open-Meteo labels meteofrance_currents Meteo-France, the field set reads as a Mercator or Copernicus analysis, meta.json carries no producer string",
            "Ocean surface currents, sea level and SST (meteofrance_currents) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/marine-weather-api"],
            ["https://marine-api.open-meteo.com/v1/marine"],
            ("link_only", "Catalogued only: no adapter until the producer question is answered"),
            ["sea_surface_temperature", "ocean_current_velocity", "ocean_current_direction", "sea_level_height_msl"],
            ["sea surface"],
            "1/12 degree global ocean grid; queried per point over the evidence box",
            "one run a day, hourly steps, published at about T+12 h 06 m",
            "about 10 days",
            (False, "none", None),
            _open_meteo_policy("the producer cannot be named, which is why this record is catalogued and not admitted."),
            "Open-Meteo marine JSON as served",
            "not applicable while the record is catalogued only",
            "Catalogued pending the producer question; the only SST, current and sea-level fields on the marine endpoint",
            (False, None, "An ocean analysis is not a deterministic centre vote, and its producer is not named."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests an ocean analysis it labels meteofrance_currents and re-serves it as hourly point time series.",
            ),
        ),
        _source(
            "openmeteo-glofas", "hydrology", "catalogued",
            "Works and no profile scores it: river discharge returned 35 of 35 non-null at all three points probed on 2026-09-02, with sane magnitudes on the large Newfoundland rivers (Exploits 243 m3/s, Humber 187 m3/s), and none of the admitted activity profiles (running, astronomy, aurora, landscape photography) asks for river discharge ("
            + ENDPOINT_RESEARCH
            + " section 4.1). The Waterford is the warning that keeps it catalogued even if a profile appears: a 0.05 degree cell is about 5 km and does not resolve an urban catchment that size, so the 0.21 to 0.69 m3/s values there are a global routing model's guess and not a gauge."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "Copernicus Emergency Management Service GloFAS, run by ECMWF",
            "GloFAS river discharge delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/flood-api", "https://global-flood.emergency.copernicus.eu/"],
            ["https://flood-api.open-meteo.com/v1/flood"],
            ("link_only", "Catalogued only: no adapter until a profile scores river discharge"),
            ["river_discharge"], ["river reach on a 0.05 degree routing grid"],
            "Global 0.05 degree routing grid; the two large Newfoundland rivers resolve, the Waterford does not",
            "daily",
            "30 days",
            (False, "none", None),
            _open_meteo_policy("credit the Copernicus Emergency Management Service and ECMWF as the producers of GloFAS."),
            "Open-Meteo flood JSON as served",
            "not applicable while the record is catalogued only",
            "Catalogued hydrology comparison; no profile scores river discharge",
            (False, None, "River discharge is not a comparable atmospheric field."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests the GloFAS river discharge forecast and re-serves it as daily point series on the routing grid cell nearest the request.",
            ),
        ),
        _source(
            "openmeteo-elevation", "terrain", "catalogued",
            "Not a forecast field and not evidence in the CONTEXT.md sense, so it is catalogued for one reason: it is the same Copernicus DEM GLO-90 that Open-Meteo's statistical downscaling acts against, and the client rule says to switch that downscaling off with elevation=nan ("
            + ENDPOINT_RESEARCH
            + " section 4.4). Having the DEM addressable separately means a site elevation can be recorded once, deliberately, rather than leaking into every temperature value invisibly. Verified live on 2026-09-02: 46 m at St. John's, matching the elevation the air-quality response echoed, 0 m over open ocean and 222 m at Notre Dame Bay. The downscaling switch is what matters here, not the DEM as a field."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "European Space Agency Copernicus DEM GLO-90",
            "Copernicus GLO-90 elevation lookup delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/elevation-api", "https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model"],
            ["https://api.open-meteo.com/v1/elevation"],
            ("link_only", "Catalogued only: a provenance vocabulary entry, not a data path"),
            ["elevation"], ["ground surface"],
            "Global 90 m digital elevation model; queried per point",
            "static between DEM releases",
            "not applicable: a static field has no forecast horizon",
            (False, "none", None),
            _open_meteo_policy("credit the Copernicus programme and ESA as the producers of the GLO-90 DEM."),
            "Open-Meteo elevation JSON as served",
            "not applicable: the DEM is static",
            "Catalogued as the documented counterpart of elevation=nan, not as an evidence field",
            (False, None, "A static elevation lookup is not a forecast vote."),
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo serves the Copernicus GLO-90 DEM as a point lookup, the same DEM its statistical downscaling acts against.",
            ),
        ),
    ])

    # The Open-Meteo endpoints ticket 28 refused. A refusal is recorded with
    # its reason for the same purpose as an admission: so nobody re-probes the
    # endpoint and reaches the opposite conclusion from the same evidence. Five
    # of the seven are refused transformations of a producer's field and carry
    # `reprocessed`; the two the intermediary constructed itself (the AQI
    # indices and the forecast-endpoint beam split) carry
    # `intermediary_derived`, which is what makes the refusal legible: the
    # reason a value is refused is the class it would have had.
    s.extend([
        _source(
            "openmeteo-marine-sst", "ocean", "rejected",
            "Four native SST paths already exist over this box (CIOPS-East 2 km, RIOPS 5 km, anonymous OSTIA Zarr and GOES-19 ABI-L2-SSTF skin SST), and they are four different quantities. A fifth from a producer that cannot be named makes the air-sea dew point depression derivation harder to write honestly, not easier ("
            + ENDPOINT_RESEARCH
            + " sections 1.5 and 2 of the SST discussion). Refused on evidence value, not on access: the 16.0 degrees C value returned live on 2026-09-02 and sat about 0.3 degrees C below the SmartAtlantic buoy, which is a plausible agreement and not a verification."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "undeclarable: the same meteofrance_currents domain whose producer Open-Meteo labels Meteo-France while the field set reads as a Mercator or Copernicus analysis",
            "Marine sea surface temperature (meteofrance_currents) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/marine-weather-api"], [],
            ("link_only", "Refused: four native SST paths already exist and the producer here cannot be named"),
            ["sea_surface_temperature"], ["sea surface"],
            "1/12 degree global ocean grid; not retrieved",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("the producer cannot be named, which is part of the refusal."),
            "Open-Meteo marine JSON as served", "not applicable: the source is refused",
            "Refused: a fifth SST quantity from an unnameable producer is not evidence",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo would re-serve an ocean analysis SST as hourly point time series; it is refused before that.",
            ),
        ),
        _source(
            "openmeteo-uv-index", "air_quality", "rejected",
            "UV index is producer output on GeoMet, verified live on HRDPS, RDPS and GDPS and on Datamart, and a retrieved producer field beats a reprocessed delivery of one every time ("
            + ENDPOINT_RESEARCH
            + " section 2.4). Refused so the map never carries an aggregator's UV beside the producer's own."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "ECMWF Copernicus Atmosphere Monitoring Service (CAMS)",
            "CAMS UV index and clear-sky UV index delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/air-quality-api"], [],
            ("link_only", "Refused: the same field is retrieved from the producer on GeoMet"),
            ["uv_index", "uv_index_clear_sky"], ["surface"],
            "CAMS global grid; not retrieved",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("credit ECMWF CAMS, were the field ever taken by this route, which it is not."),
            "Open-Meteo air-quality JSON as served", "not applicable: the source is refused",
            "Refused: retrieved beats reprocessed for a field the producer publishes here",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo would re-serve the CAMS UV index as hourly point time series; it is refused before that.",
            ),
        ),
        _source(
            "openmeteo-pollen-ammonia", "air_quality", "rejected",
            "Nothing is served over this box: alder, grass and ragweed pollen returned 0 of 216 non-null over nine days and ammonia 0 of 72, because all four live only on the cams_europe domain, and cams_europe answers HTTP 400 'No data is available for this location' here ("
            + ENDPOINT_RESEARCH
            + " sections 2.1 and 2.3, re-confirmed 2026-09-02). Refused rather than catalogued because there is no value to catalogue: the domain does not reach the box at all."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "ECMWF Copernicus Atmosphere Monitoring Service (CAMS) European domain",
            "CAMS Europe pollen and ammonia delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/air-quality-api"], [],
            ("link_only", "Refused: the European domain returns HTTP 400 over this box"),
            ["alder_pollen", "grass_pollen", "ragweed_pollen", "ammonia"], ["surface"],
            "CAMS Europe domain, which does not reach the evidence box",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("credit ECMWF CAMS, were the European domain ever to reach this box, which it does not."),
            "Open-Meteo air-quality JSON as served", "not applicable: the source is refused",
            "Refused: the European domain does not reach the box",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo would re-serve the CAMS Europe composition fields as hourly point time series; over this box it serves nulls or HTTP 400.",
            ),
        ),
        _source(
            "openmeteo-aqi-indices", "air_quality", "rejected",
            "european_aqi and us_aqi are index constructions over other fields, not fields in the CONTEXT.md sense, and importing a foreign index would put a fifth incompatible encoding beside the four transparency encodings already flagged ("
            + ENDPOINT_RESEARCH
            + " section 2.4). They are the intermediary's own computation over a producer's composition fields, so the class they would carry is intermediary_derived rather than the reprocessed route this record declares, and that is exactly why they are refused: the index is not a quantity anyone can weigh against another source's."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "ECMWF Copernicus Atmosphere Monitoring Service (CAMS) supplies the underlying composition fields; the indices themselves are Open-Meteo's construction",
            "European and US air quality indices computed by Open-Meteo",
            ["https://open-meteo.com/en/docs/air-quality-api"], [],
            ("link_only", "Refused: an index construction is not a field"),
            ["european_aqi", "us_aqi"], ["surface"],
            "CAMS global grid; not retrieved",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("credit ECMWF CAMS for the composition fields; the index is the intermediary's own."),
            "Open-Meteo air-quality JSON as served", "not applicable: the source is refused",
            "Refused: an index construction, and a fifth incompatible encoding",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo computes the European and US AQI from CAMS composition fields by each index's published banding; the producer publishes no such index, which is why the reason and not the kind carries the refusal.",
            ),
        ),
        _source(
            "openmeteo-beam-split", "analysis", "rejected",
            "The forecast endpoint's direct_radiation, diffuse_radiation and direct_normal_irradiance are an intermediary's decomposition of a producer's total shortwave, for producers that publish no such split, with no method named ("
            + ENDPOINT_RESEARCH
            + " section 3.4). That is the WeatherNext 2 cloud refusal reasoning exactly, without the intermediary-derived declaration that saved WeatherNext: this deployment cannot cite the method's inputs and the producer never published the field. Refused, and it must never be catalogued as the same field as the satellite endpoint's LSA SAF split, which is a retrieval from measured radiance."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "ECMWF and the other Open-Meteo forecast producers, none of which publishes a beam split",
            "Direct, diffuse and DNI split computed by Open-Meteo from a producer's total shortwave",
            ["https://open-meteo.com/en/docs"], [],
            ("link_only", "Refused: an undocumented decomposition of a producer's total"),
            ["direct_radiation", "diffuse_radiation", "direct_normal_irradiance"], ["surface"],
            "Global, per forecast domain; not retrieved",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("the split is the intermediary's own and names no method, which is the refusal."),
            "Open-Meteo forecast JSON as served", "not applicable: the source is refused",
            "Refused: a model of a model, never to be merged with the satellite radiation split",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo splits a producer's total shortwave into direct, diffuse and DNI by its own decomposition, which it does not name per model.",
            ),
        ),
        _source(
            "openmeteo-climate-cmip6", "analysis", "rejected",
            "CMIP6 HighResMIP downscaled projections answer for dates inside the 14-day horizon with no marker distinguishing them from a forecast: EC_Earth3P_HR returned daily maxima for 2026-09-01 to 2026-09-10 at St. John's on a call that looks like any other ("
            + ENDPOINT_RESEARCH
            + " section 4.2). That is exactly the confusion the evidence classes exist to prevent, and the projections add nothing inside 14 days. Refused."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "CMIP6 HighResMIP modelling centres (EC_Earth3P_HR and the other models Open-Meteo serves)",
            "CMIP6 downscaled climate projections delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/climate-api"], [],
            ("link_only", "Refused: projections that answer for forecast dates unmarked"),
            ["air_temperature", "precipitation"], ["surface", "2 m"],
            "Global downscaled projection grid; not retrieved",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("credit the CMIP6 modelling centres, were the projections ever taken, which they are not."),
            "Open-Meteo climate JSON as served", "not applicable: the source is refused",
            "Refused: a projection that is confusable with a forecast inside the horizon",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo downscales CMIP6 HighResMIP projections onto its own grid and serves them as daily point series.",
            ),
        ),
        _source(
            "openmeteo-seasonal-seas5", "analysis", "rejected",
            "ECMWF SEAS5 through this endpoint is a monthly run published at T+4.4 days, 6-hourly, on an O320 (about 36 km) mesh; the run read on 2026-09-02 initialised 2026-08-01 ("
            + ENDPOINT_RESEARCH
            + " section 4.3). Inside a 14-day horizon that is a month-old climate signal and it adds nothing. Refused."
            + OPEN_METEO_BEST_MATCH_REFUSAL,
            "ECMWF",
            "SEAS5 seasonal forecast (ecmwf_seas5) delivered by Open-Meteo",
            ["https://open-meteo.com/en/docs/seasonal-forecast-api"], [],
            ("link_only", "Refused: a monthly run adds nothing inside 14 days"),
            ["air_temperature", "precipitation"], ["surface", "2 m"],
            "Global O320 reduced Gaussian mesh; not retrieved",
            "not applicable: the source is refused",
            "not applicable: the source is refused",
            (False, "none", None),
            _open_meteo_policy("credit ECMWF as the producer of SEAS5, were it ever taken, which it is not."),
            "Open-Meteo seasonal JSON as served", "not applicable: the source is refused",
            "Refused: a monthly seasonal run inside a 14-day horizon",
            (False, None, "A refused source cannot contribute."),
            "not_applicable", "not_applicable",
            delivery_kind="reprocessed",
            intermediary=_open_meteo_intermediary(
                "Open-Meteo ingests ECMWF SEAS5 and re-serves it as 6-hourly point series on its own grid.",
            ),
        ),
    ])

    # The ensemble family declaration is attached here rather than threaded
    # through every constructor call, so the six blocks stay readable side by
    # side in one table above and no record can acquire one by inheriting a
    # default. A block whose source id is not in the registry, or an ensemble
    # record with no block, is refused by the audit rather than passed over
    # silently here.
    for record in s:
        declaration = ENSEMBLE_DECLARATIONS.get(record["id"])
        if declaration is not None:
            record["ensemble"] = copy.deepcopy(declaration)
    return {"registry_version": "0.1.0", "as_of": "2026-08-29", "classification": "experiment", "sources": s}
