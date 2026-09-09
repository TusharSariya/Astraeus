"""Versioned experimental IFS catalogue; membership is not retrieval evidence."""
import json
from pathlib import Path

MANIFEST = json.loads(Path(__file__).with_name('ifs_manifest.json').read_text())
FIELDS = {row['id']: row for row in MANIFEST['fields']}
PRODUCTS = {row['id']: row for row in MANIFEST['products']}
BOUNDS = dict(zip(('west','south','east','north'), MANIFEST['bounds']))


def field_selection(product, field, level):
    if product not in PRODUCTS or field not in FIELDS:
        raise ValueError('unsupported_product_or_field')
    row = FIELDS[field]
    if product not in row['products'] or level not in row.get('product_levels', {}).get(product, row['levels']):
        raise ValueError('unsupported_product_field_level')
    return row
