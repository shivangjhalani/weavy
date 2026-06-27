"""Memory-system adapters.

Each adapter implements :class:`~bench.adapters.base.MemorySystem`. Only the
adapter module is allowed to import the system it wraps, keeping the harness
system-agnostic.
"""
