"""Behavioural prediction utilities for AstroLive Orbit.

The package intentionally contains no astrology inference.  It predicts only
demonstration product behaviours from consent-safe engagement aggregates.
"""

from .inference import PredictionResult, load_predictor, predict_user

__all__ = ["PredictionResult", "load_predictor", "predict_user"]
