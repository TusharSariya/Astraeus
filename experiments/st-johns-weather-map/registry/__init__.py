"""Registry package: the source registry and the field catalogue.

Importable as ``registry.source_data`` and ``registry.fields`` from the
experiment root. This marker exists so the container images, which copy in
only the modules they need, still expose a regular package rather than a
namespace package whose contents depend on what happened to be copied.
"""
