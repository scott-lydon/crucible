"""Red module (Pillar 2): adversarial search, strategy catalog, white-box
mode, hybrid fallback (slices 11 to 13).
"""

from __future__ import annotations

from .catalog import CatalogEntry, StrategyCatalog
from .search import Proposal, RedSearchAgent, parse_proposal

__all__ = ["CatalogEntry", "Proposal", "RedSearchAgent", "StrategyCatalog", "parse_proposal"]
