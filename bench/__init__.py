"""Weavy benchmark harness.

A standalone evaluation harness that treats a memory system as a black box
behind the :class:`~bench.adapters.base.MemorySystem` protocol. The harness has
no knowledge of Weavy internals — only the public adapter contract — so new
systems (mem0, graphiti, ...) plug in by adding one adapter file.

Nothing under ``weavy/`` imports from ``bench/``. The dependency points one way.
"""
