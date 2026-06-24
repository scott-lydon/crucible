"""Red module (Pillar 2): adversarial search, strategy catalog, white-box
mode, hybrid fallback (slices 11 to 13).
"""

from __future__ import annotations

from .catalog import CatalogEntry, StrategyCatalog
from .search import Proposal, RedSearchAgent, parse_proposal
from .white_box import compose_white_box_brief

__all__ = [
    "CatalogEntry",
    "Proposal",
    "RedSearchAgent",
    "StrategyCatalog",
    "compose_white_box_brief",
    "parse_proposal",
]
