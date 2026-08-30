"""Ingestion plumbing shared by the worker and the API.

``contract`` is the frozen coordination surface for adapter authors; the other
modules are the shared implementation they build on.
"""

from __future__ import annotations
