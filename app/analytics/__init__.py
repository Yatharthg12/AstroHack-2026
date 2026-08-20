"""Transparent product analytics for the synthetic Growth Cockpit."""

from .metrics import (
    activation_funnel,
    assign_segments,
    cohort_retention,
    growth_summary,
    k_factor,
)
from .dashboard import anonymized_drilldown, load_demo_data, model_catalog, snapshot
from .validation import validate_demo_data

__all__ = [
    "activation_funnel",
    "assign_segments",
    "cohort_retention",
    "growth_summary",
    "k_factor",
    "anonymized_drilldown",
    "load_demo_data",
    "model_catalog",
    "snapshot",
    "validate_demo_data",
]
