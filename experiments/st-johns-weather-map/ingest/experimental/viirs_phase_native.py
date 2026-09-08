"""Isolated JRR-CloudPhase v3r2 native-index evidence, not point admission.

No category, quality-bit or fog interpretation. Only NOAA-20's concretely
captured product is supported; other JPSS products/platforms remain separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from hashlib import sha256
from pathlib import Path
import json
import re
import sys
import tempfile

from ingest.isolation import ProcessAllocationLimits, run_bounded_process

MAX_NATIVE_BYTES = 24 * 1024 * 1024
MAX_REPLY_BYTES = 64 * 1024
LIMITS = ProcessAllocationLimits(768 * 1024 * 1024, MAX_NATIVE_BYTES, MAX_NATIVE_BYTES, 1024, 8192)
_PATTERN = re.compile(r"VIIRS-JRR-CloudPhase/(\d{4})/(\d{2})/(\d{2})/JRR-CloudPhase_v3r2_j01_s(\d{15})_e(\d{15})_c(\d{15})\.nc")


@dataclass(frozen=True)
class PhaseObject:
    key: str
    size: int
    sha256: str

    def __post_init__(self):
        match = _PATTERN.fullmatch(self.key)
        if not match or ''.join(match.group(i) for i in (1, 2, 3)) != match[4][:8]:
            raise ValueError("Expected exact NOAA-20 JRR-CloudPhase v3r2 identity")
        times = [datetime.strptime(match[i], '%Y%m%d%H%M%S%f').replace(tzinfo=UTC) for i in (4, 5, 6)]
        if not times[0] <= times[1] <= times[2]:
            raise ValueError("Invalid producer scan and creation times")
        if type(self.size) is not int or not 0 < self.size <= MAX_NATIVE_BYTES or not re.fullmatch('[a-f0-9]{64}', self.sha256):
            raise ValueError("Invalid native object size or digest")

    @property
    def url(self):
        return 'https://noaa-nesdis-n20-pds.s3.amazonaws.com/' + self.key


def inspect_native_cell(body: bytes, source: PhaseObject, row: int, column: int) -> dict:
    """Kernel-bounded raw index read of an already captured exact granule.

    Returned raw integers and fill markers are diagnostic native evidence,
    never QC-passing EvidenceFields. No latitude/longitude point is selected.
    """
    if type(row) is not int or type(column) is not int or not 0 <= row < 1024 or not 0 <= column < 3200:
        raise ValueError("Native row/column outside decoder bounds")
    if len(body) != source.size or sha256(body).hexdigest() != source.sha256:
        raise ValueError("Captured object length/digest mismatch")
    with tempfile.TemporaryDirectory(prefix='viirs-phase-native-') as directory:
        output = Path(directory) / 'native-cell.json'
        run_bounded_process(
            command=[sys.executable, str(Path(__file__).with_name('viirs_phase_native_worker.py')), '{output}', source.key, str(row), str(column)],
            stdin=body, destination=output, limits=LIMITS,
        )
        if output.stat().st_size > MAX_REPLY_BYTES:
            raise ValueError("Native cell metadata exceeds ceiling")
        result = json.loads(output.read_text())
    result.update(source_url=source.url, source_sha256=source.sha256, source_bytes=source.size,
                  operational=False, quality_state='unknown', evidence_use='native-index inspection only')
    return result
