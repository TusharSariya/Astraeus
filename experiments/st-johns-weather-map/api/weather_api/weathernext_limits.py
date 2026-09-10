"""Bounded WN3 acquisition policy. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

Owner authorized 1 GiB aggregate downloads on 2026-09-09. Per-object bounds
preserve the existing base64 pipe envelope and decoder memory limits.
"""
MAX_ACQUISITION_BYTES = 1024**3
MAX_OBJECT_BYTES = 64 * 1024**2
MAX_FIELDS = 36


def operation_limit(field_count, *, regional=False, inventory=False):
    if inventory:
        return 10
    if regional:
        return 30
    # Coordinates plus metadata/payload pairs per selected field. Never exceed
    # NativeLimits' existing 270-operation maximum.
    return min(270, max(30, 10 + 4 * field_count))
