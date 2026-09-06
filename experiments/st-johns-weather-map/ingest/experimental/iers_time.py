"""Bounded readers for experimental IERS time inputs and the NAIF LSK."""

from __future__ import annotations

import hashlib
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy
import xarray

from ingest.contract import MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.grib import write_zarr
from ingest.http import PoliteClient

UTC = timezone.utc
FINALS_URL = "https://datacenter.iers.org/data/9/finals2000A.all"
LEAPS_URL = "https://hpiers.obspm.fr/iers/bul/bulc/Leap_Second.dat"
NAIF_LSK_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls"
NAIF_LSK_IDENTITY_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/aareadme.txt"
FINALS_MAX_BYTES = 4 * 1024 * 1024
TEXT_MAX_BYTES = 64 * 1024


def _field(line: str, start: int, stop: int) -> str:
    return line[start - 1 : stop].strip()


def _number(line: str, start: int, stop: int, name: str, *, optional: bool = False) -> float:
    raw = _field(line, start, stop)
    if optional and not raw:
        return numpy.nan
    try:
        return float(raw)
    except ValueError as error:
        raise AdapterUnavailable(f"finals2000A invalid {name}") from error


def _mjd_at_midnight(instant: datetime) -> float:
    return 40587.0 + instant.timestamp() / 86400.0


def parse_finals(body: bytes, window: FetchWindow) -> list[dict[str, object]]:
    try:
        lines = body.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise AdapterUnavailable("finals2000A is not ASCII") from error
    rows: list[dict[str, object]] = []
    for line in lines:
        if not line.strip():
            continue
        if len(line) < 15:
            raise AdapterUnavailable("finals2000A contains a truncated row")
        mjd = _number(line, 8, 15, "MJD")
        year = int(_field(line, 1, 2)) + (1900 if mjd <= 51543 else 2000)
        try:
            instant = datetime(year, int(_field(line, 3, 4)), int(_field(line, 5, 6)), tzinfo=UTC)
        except ValueError as error:
            raise AdapterUnavailable("finals2000A contains an invalid calendar date") from error
        if mjd != _mjd_at_midnight(instant):
            raise AdapterUnavailable("finals2000A MJD disagrees with its UTC calendar date")
        if not window.covers(instant):
            continue
        if len(line) < 134:
            raise AdapterUnavailable("finals2000A contains a truncated row")
        pm_flag, ut1_flag, nutation_flag = _field(line, 17, 17), _field(line, 58, 58), _field(line, 96, 96)
        if pm_flag not in {"I", "P"} or ut1_flag not in {"I", "P"} or nutation_flag not in {"I", "P"}:
            raise AdapterUnavailable("finals2000A contains an unknown IERS/prediction flag")
        rows.append({
            "time": instant, "mjd_utc": mjd,
            "pm_status": pm_flag, "ut1_status": ut1_flag, "nutation_status": nutation_flag,
            "pm_x": _number(line, 19, 27, "PM-x"), "pm_x_error": _number(line, 28, 36, "PM-x error"),
            "pm_y": _number(line, 38, 46, "PM-y"), "pm_y_error": _number(line, 47, 55, "PM-y error"),
            "ut1_utc": _number(line, 59, 68, "UT1-UTC"), "ut1_utc_error": _number(line, 69, 78, "UT1-UTC error"),
            "lod": _number(line, 80, 86, "LOD", optional=True), "lod_error": _number(line, 87, 93, "LOD error", optional=True),
            "dx": _number(line, 98, 106, "dX"), "dx_error": _number(line, 107, 115, "dX error"),
            "dy": _number(line, 117, 125, "dY"), "dy_error": _number(line, 126, 134, "dY error"),
            "bulletin_b_pm_x": _number(line, 135, 144, "Bulletin B PM-x", optional=True),
            "bulletin_b_pm_y": _number(line, 145, 154, "Bulletin B PM-y", optional=True),
            "bulletin_b_ut1_utc": _number(line, 155, 165, "Bulletin B UT1-UTC", optional=True),
            "bulletin_b_dx": _number(line, 166, 175, "Bulletin B dX", optional=True),
            "bulletin_b_dy": _number(line, 176, 185, "Bulletin B dY", optional=True),
        })
    if not rows:
        raise AdapterUnavailable("finals2000A has no complete Earth-orientation rows in the requested window")
    if len({row["time"] for row in rows}) != len(rows):
        raise AdapterUnavailable("finals2000A repeats an epoch")
    return rows


_LEAP_ROW = re.compile(r"^\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")


def parse_iers_leaps(body: bytes, captured_at: datetime) -> tuple[list[dict[str, object]], datetime, str, str]:
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as error:
        raise AdapterUnavailable("IERS leap-second table is not ASCII") from error
    expiry_match = re.search(r"File expires on (\d{1,2} \w+ \d{4})", text)
    update_match = re.search(r"Updated through IERS Bulletin (\d+) issued in (\w+ \d{4})", text)
    if not expiry_match or not update_match:
        raise AdapterUnavailable("IERS leap-second table lacks update or expiry identity")
    expiry = datetime.strptime(expiry_match.group(1), "%d %B %Y").replace(tzinfo=UTC)
    if captured_at >= expiry:
        raise AdapterUnavailable("IERS leap-second table is expired")
    rows = []
    for line in text.splitlines():
        match = _LEAP_ROW.match(line)
        if not match:
            continue
        mjd, day, month, year, offset = match.groups()
        instant = datetime(int(year), int(month), int(day), tzinfo=UTC)
        if float(mjd) != _mjd_at_midnight(instant):
            raise AdapterUnavailable("IERS leap-second MJD disagrees with its UTC calendar date")
        rows.append({"time": instant, "mjd_utc": float(mjd), "tai_minus_utc": int(offset)})
    if not rows or any(b["time"] <= a["time"] or abs(b["tai_minus_utc"] - a["tai_minus_utc"]) != 1 for a, b in zip(rows, rows[1:])):
        raise AdapterUnavailable("IERS leap-second table has an invalid offset sequence")
    return rows, expiry, update_match.group(1), update_match.group(2)


_LSK_CONSTANT = re.compile(r"^DELTET/(DELTA_T_A|K|EB)\s*=\s*([\d.+-]+(?:D[+-]?\d+)?)\s*$", re.MULTILINE)
_LSK_LEAP = re.compile(r"\s*(\d+),\s*@(?P<year>\d{4})-(?P<month>[A-Z]{3})-(?P<day>\d+)")


def parse_naif_lsk(body: bytes, identity_body: bytes) -> tuple[list[dict[str, object]], dict[str, float | list[float]], str]:
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as error:
        raise AdapterUnavailable("NAIF LSK is not ASCII") from error
    try:
        identity = identity_body.decode("ascii")
    except UnicodeDecodeError as error:
        raise AdapterUnavailable("NAIF LSK identity note is not ASCII") from error
    version = re.search(r"LEAPSECONDS KERNEL VERSION (NAIF\d{4})", identity)
    constants = {name: float(value.replace("D", "E")) for name, value in _LSK_CONSTANT.findall(text)}
    mean = re.search(r"DELTET/M\s*=\s*\(\s*([\d.+-]+D\d+)\s+([\d.+-]+D[+-]?\d+)\s*\)", text)
    if not text.startswith("KPL/LSK") or not version or version.group(1) != "NAIF0012" or set(constants) != {"DELTA_T_A", "K", "EB"} or not mean:
        raise AdapterUnavailable("NAIF LSK lacks its versioned DELTET constants")
    constants["M"] = [float(value.replace("D", "E")) for value in mean.groups()]
    months = {name: index for index, name in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
    rows = [{"time": datetime(int(m.group("year")), months[m.group("month")], int(m.group("day")), tzinfo=UTC), "delta_at": int(m.group(1))} for m in _LSK_LEAP.finditer(text)]
    if not rows or any(b["time"] <= a["time"] or abs(b["delta_at"] - a["delta_at"]) != 1 for a, b in zip(rows, rows[1:])):
        raise AdapterUnavailable("NAIF LSK has an invalid DELTA_AT sequence")
    return rows, constants, version.group(1).lower()


class _SingleDownloadAdapter:
    source_id: str
    adapter_version: str
    endpoint: str
    max_bytes: int
    logical_name: str

    def __init__(self, client: PoliteClient | None = None, endpoint: str | None = None, clock=None) -> None:
        self.client = client or PoliteClient()
        self.endpoint = endpoint or self.endpoint
        self.clock = clock or (lambda: datetime.now(UTC))

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        with tempfile.TemporaryDirectory(prefix="iers-time-") as directory:
            path = Path(directory) / "payload"
            try:
                self.client.download(self.endpoint, path, max_bytes=self.max_bytes)
            except Exception as error:
                raise AdapterUnavailable(f"{self.source_id} request failed: {error}") from error
            body = path.read_bytes()
        captured_at = self.clock()
        detail = self._validate(body, window, captured_at)
        digest = hashlib.sha256(body).hexdigest()
        detail.update(body=body, captured_at=captured_at, byte_count=len(body), sha256=digest)
        return [RunCandidate(f"{self.source_id}-{digest[:16]}", None, [self.endpoint], detail)]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        captured_at = candidate.detail.get("captured_at")
        body = candidate.detail.get("body")
        if not isinstance(captured_at, datetime) or captured_at.tzinfo is None or not isinstance(body, bytes):
            raise AdapterUnavailable(f"{self.source_id} candidate lacks payload or UTC capture time")
        detail = self._validate_candidate(candidate, body, window, captured_at)
        dataset, extra = self._dataset(detail)
        path = workdir / f"{self.logical_name}.zarr.zip"
        write_zarr(dataset, path)
        provenance = {
            "source_id": self.source_id, "producer": self.producer, "product": self.product,
            "adapter_version": self.adapter_version, "operational": False,
            "evidence_classes": ["retrieved"], "quality": {"status": "unknown", "flags": ["experimental", "not_admitted", "nonpublishable"]},
            "request": {"url": self.endpoint, "parameters": {}, "byte_count": candidate.detail["byte_count"], "sha256": candidate.detail["sha256"]},
            "valid_times": [numpy.datetime_as_string(value, timezone="UTC") for value in dataset.valid_time.values],
            "field_disposition": self.field_disposition, **extra,
            "validation": {"publishable": False, "reason": "no accepted reference-input RunManifest or publication contract"},
        }
        if "identity_sha256" in candidate.detail:
            provenance["request"]["identity"] = {"url": candidate.urls[1], "byte_count": candidate.detail["identity_byte_count"], "sha256": candidate.detail["identity_sha256"]}
        provenance["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        provenance["byte_size"] = path.stat().st_size
        artifact = Artifact(self.logical_name, MEDIA_ZARR, path, provenance)
        return RunResult(self.source_id, candidate.provider_run_id, None, captured_at.astimezone(UTC), False, False, [artifact], "not_applicable", "nonpublishable evidence: reference-input RunManifest contract is not accepted")

    def _validate_candidate(self, candidate, body, window, captured_at):
        return self._validate(body, window, captured_at)


class IERSBulletinAAdapter(_SingleDownloadAdapter):
    source_id = "iers-bulletin-a-finals2000a"
    adapter_version = "iers-finals2000a-v1"
    endpoint, max_bytes, logical_name = FINALS_URL, FINALS_MAX_BYTES, "earth_orientation"
    producer, product = "IERS Rapid Service/Prediction Centre", "finals.all (IAU2000) / finals2000A.all"
    field_disposition = {
        "year/month/day": "UTC calendar epoch identity", "MJD": "fractional Modified Julian Date in UTC",
        "PM flag": "IERS observed or prediction status for Bulletin A polar motion",
        "PM-x/error, PM-y/error": "stored in arcseconds", "UT1 flag": "IERS observed or prediction status for Bulletin A UT1-UTC",
        "UT1-UTC/error": "stored in seconds", "LOD/error": "stored in milliseconds; blank remains missing",
        "nutation flag": "IERS observed or prediction status for Bulletin A celestial pole offsets",
        "dX/error, dY/error": "stored in milliarcseconds relative to IAU 2000A; FCN not removed",
        "Bulletin B PM-x, PM-y, UT1-UTC, dX, dY": "stored in published units when present; blank remains missing",
    }
    def _validate(self, body, window, captured_at): return {"rows": parse_finals(body, window)}
    def _dataset(self, detail):
        rows = detail["rows"]
        units = {"mjd_utc":"d", "pm_x":"arcsec", "pm_x_error":"arcsec", "pm_y":"arcsec", "pm_y_error":"arcsec", "ut1_utc":"s", "ut1_utc_error":"s", "lod":"ms", "lod_error":"ms", "dx":"mas", "dx_error":"mas", "dy":"mas", "dy_error":"mas", "bulletin_b_pm_x":"arcsec", "bulletin_b_pm_y":"arcsec", "bulletin_b_ut1_utc":"s", "bulletin_b_dx":"mas", "bulletin_b_dy":"mas"}
        arrays = {name: (("valid_time",), numpy.asarray([row[name] for row in rows]), {"units": unit}) for name, unit in units.items()}
        arrays.update({name: (("valid_time",), numpy.asarray([row[name] for row in rows], dtype="U1"), {"meaning": "I=IERS observed; P=prediction"}) for name in ("pm_status", "ut1_status", "nutation_status")})
        return xarray.Dataset(arrays, coords={"valid_time": numpy.asarray([numpy.datetime64(row["time"].replace(tzinfo=None), "ns") for row in rows])}, attrs={"operational": False}), {"time_identity": "daily 00:00 UTC epochs; MJD is explicitly UTC"}


class IERSLeapSecondAdapter(_SingleDownloadAdapter):
    source_id = "iers-leap-second-table"
    adapter_version = "iers-leap-second-table-v1"
    endpoint, max_bytes, logical_name = LEAPS_URL, TEXT_MAX_BYTES, "leap_seconds"
    producer, product = "International Earth Rotation and Reference Systems Service", "Leap_Second.dat"
    field_disposition = {"MJD": "effective UTC epoch as Modified Julian Date", "Date": "effective UTC calendar date", "TAI-UTC (s)": "stored integer offset in seconds", "Updated through": "Bulletin/version identity in provenance", "File expires": "freshness ceiling; expired tables fail closed"}
    def _validate(self, body, window, captured_at):
        rows, expiry, bulletin, issued = parse_iers_leaps(body, captured_at)
        return {"rows": rows, "expiry": expiry, "bulletin": bulletin, "issued": issued}
    def _dataset(self, detail):
        rows = detail["rows"]
        ds = xarray.Dataset({"mjd_utc": (("valid_time",), [r["mjd_utc"] for r in rows], {"units":"d"}), "tai_minus_utc": (("valid_time",), [r["tai_minus_utc"] for r in rows], {"units":"s"})}, coords={"valid_time": numpy.asarray([numpy.datetime64(r["time"].replace(tzinfo=None), "ns") for r in rows])}, attrs={"operational":False})
        return ds, {"expires_at": detail["expiry"].isoformat().replace("+00:00", "Z"), "updated_through_bulletin": detail["bulletin"], "bulletin_issued": detail["issued"], "time_identity":"each epoch is the UTC instant at which the listed TAI-UTC offset becomes effective"}


class NAIFLeapSecondsKernelAdapter(_SingleDownloadAdapter):
    source_id = "naif-leapseconds-kernel-naif0012"
    adapter_version = "naif-lsk-v1"
    endpoint, max_bytes, logical_name = NAIF_LSK_URL, TEXT_MAX_BYTES, "naif_leapseconds_kernel"
    producer, product = "NASA/JPL Navigation and Ancillary Information Facility", "NAIF0012 leapseconds kernel"
    field_disposition = {"DELTET/DELTA_T_A": "stored kernel constant", "DELTET/K": "stored kernel constant", "DELTET/EB": "stored kernel constant", "DELTET/M": "stored two kernel coefficients", "DELTET/DELTA_AT": "stored offset and effective UTC epoch pairs", "comments/modification history": "identity documentation only; not promoted as computed science"}
    identity_endpoint = NAIF_LSK_IDENTITY_URL
    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        with tempfile.TemporaryDirectory(prefix="naif-lsk-") as directory:
            payload_path, identity_path = Path(directory) / "naif0012.tls", Path(directory) / "aareadme.txt"
            try:
                self.client.download(self.endpoint, payload_path, max_bytes=self.max_bytes)
                self.client.download(self.identity_endpoint, identity_path, max_bytes=TEXT_MAX_BYTES)
            except Exception as error:
                raise AdapterUnavailable(f"{self.source_id} request failed: {error}") from error
            body, identity_body = payload_path.read_bytes(), identity_path.read_bytes()
        captured_at = self.clock()
        detail = self._validate_parts(body, identity_body)
        digest = hashlib.sha256(body).hexdigest()
        detail.update(body=body, identity_body=identity_body, captured_at=captured_at, byte_count=len(body), sha256=digest,
                      identity_byte_count=len(identity_body), identity_sha256=hashlib.sha256(identity_body).hexdigest())
        return [RunCandidate(f"{self.source_id}-{digest[:16]}", None, [self.endpoint, self.identity_endpoint], detail)]
    def _validate_parts(self, body, identity_body):
        rows, constants, version = parse_naif_lsk(body, identity_body)
        return {"rows": rows, "constants": constants, "version": version}
    def _validate_candidate(self, candidate, body, window, captured_at):
        identity_body = candidate.detail.get("identity_body")
        if not isinstance(identity_body, bytes):
            raise AdapterUnavailable("NAIF LSK candidate lacks its version identity note")
        return self._validate_parts(body, identity_body)
    def _dataset(self, detail):
        rows = detail["rows"]
        ds = xarray.Dataset({"delta_at": (("valid_time",), [r["delta_at"] for r in rows], {"units":"s"})}, coords={"valid_time": numpy.asarray([numpy.datetime64(r["time"].replace(tzinfo=None), "ns") for r in rows])}, attrs={"operational":False})
        return ds, {"kernel_version": detail["version"], "deltet_constants": detail["constants"], "time_identity":"DELTET/DELTA_AT effective UTC epochs as encoded by the selected NAIF LSK"}
