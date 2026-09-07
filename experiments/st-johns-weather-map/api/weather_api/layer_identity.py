"""Explicit layer declarations, without title guessing or new provider reads."""
from datetime import datetime
from typing import Iterable

from .models import ImageryAvailability, LayerFieldMapping, catalogue_key_for


def mappings(pairs: Iterable[tuple[str, str | None]]) -> dict:
    """The caller supplies authoritative source/declared-field associations.

    Only the existing field catalogue alias rule resolves a field. A known
    source with an unmapped field remains partial, never an invented bundle key.
    """
    records = []
    seen = set()
    for source, native in pairs:
        key = catalogue_key_for(native) if isinstance(native, str) else None
        identity = (source, key, native)
        if identity in seen:
            continue
        seen.add(identity)
        records.append(LayerFieldMapping(source_id=source, field_key=key, declared_field=native))
    status = 'known' if records and all(row.field_key is not None for row in records) else 'partial' if records else 'unknown'
    return dict(field_mappings=records, mapping_status=status,
                mapping_reason='Explicit source/field declaration; this is not proof of a retrieved point value' if status == 'known'
                else 'Source is explicit; one or more declared fields have no catalogue association' if records
                else 'No explicit source/field declaration is available')


def imagery(status: str, checked_at: datetime, basis: str, reason: str, times=()) -> ImageryAvailability:
    return ImageryAvailability(status=status, checked_at=checked_at, basis=basis, reason=reason, times=list(times))
