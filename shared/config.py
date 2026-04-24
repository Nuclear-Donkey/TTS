"""Shared config helpers."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def apply_section(section_obj, values: dict) -> None:
    """Apply TOML section values to a dataclass instance.

    Unknown keys are warned about and ignored.
    """
    for k, v in values.items():
        if hasattr(section_obj, k):
            setattr(section_obj, k, v)
        else:
            log.warning("unknown config key %s.%s", type(section_obj).__name__, k)
