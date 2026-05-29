"""Factoribot brain.

Terminal-first Factorio assistant backend. The production solver works on a
dump of the game's real prototype data (``data-raw-dump.json``), so it is
automatically correct for whatever mods are enabled.
"""

__all__ = ["gamedata", "model", "spec", "solver", "report"]
