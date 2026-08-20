"""Safe, lightweight inference from repository-owned JSON artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from .features import FEATURES, feature_frame


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = REPO_ROOT / "artifacts" / "models"


@dataclass(frozen=True)
class PredictionResult:
    probability: float
    label: bool
    threshold: float
    model_available: bool
    model_version: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "probability": round(self.probability, 4),
            "label": self.label,
            "threshold": self.threshold,
            "model_available": self.model_available,
            "model_version": self.model_version,
            "reason": self.reason,
        }


class JsonLogisticPredictor:
    """Minimal scorer for a standardized sklearn logistic regression."""

    def __init__(self, payload: Mapping[str, object]):
        if payload.get("artifact_format") != "orbit-logistic-json-v1":
            raise ValueError("Unsupported model artifact format")
        if payload.get("features") != FEATURES:
            raise ValueError("Model feature contract does not match application")
        self.mean = np.asarray(payload["mean"], dtype=float)
        self.scale = np.asarray(payload["scale"], dtype=float)
        self.coefficients = np.asarray(payload["coefficients"], dtype=float)
        self.intercept = float(payload["intercept"])
        self.threshold = float(payload["threshold"])
        self.version = str(payload["model_version"])
        if not (
            len(self.mean) == len(self.scale) == len(self.coefficients) == len(FEATURES)
        ):
            raise ValueError("Malformed model dimensions")
        if not 0.0 < self.threshold < 1.0 or (self.scale <= 0).any():
            raise ValueError("Malformed model threshold or scaling")

    def predict_probability(self, values: Mapping[str, object]) -> float:
        x = feature_frame(values).iloc[0].to_numpy(dtype=float)
        logit = float(np.dot((x - self.mean) / self.scale, self.coefficients) + self.intercept)
        # Numerically stable sigmoid.
        probability = 1.0 / (1.0 + np.exp(-np.clip(logit, -35.0, 35.0)))
        return float(probability)


def _contained_json_path(task: str, model_dir: Path) -> Path:
    if task not in {"churn_risk", "consultation_intent"}:
        raise ValueError("Unknown prediction task")
    root = model_dir.resolve()
    repository = REPO_ROOT.resolve()
    if root != repository and repository not in root.parents:
        raise ValueError("Model artifacts must be inside the repository")
    path = (root / f"{task}.json").resolve()
    if root not in path.parents or path.suffix != ".json":
        raise ValueError("Model path must remain within the configured artifact directory")
    return path


def load_predictor(task: str, model_dir: Path | None = None) -> JsonLogisticPredictor | None:
    """Load an integrity-checked JSON model, returning ``None`` if unavailable.

    Only a fixed filename beneath the configured repository artifact directory
    is accepted.  No pickle, eval, imports, or executable objects are loaded.
    """

    root = (model_dir or DEFAULT_MODEL_DIR).resolve()
    # Custom directories are useful for tests, but the production default is
    # fixed inside the repository. Callers cannot influence it via request data.
    try:
        path = _contained_json_path(task, root)
        digest_path = path.with_suffix(".sha256")
        raw = path.read_bytes()
        expected = digest_path.read_text(encoding="ascii").strip().split()[0]
    except (FileNotFoundError, OSError, IndexError, ValueError):
        return None
    if not expected or hashlib.sha256(raw).hexdigest() != expected:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
        return JsonLogisticPredictor(payload)
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def predict_user(
    task: str,
    values: Mapping[str, object],
    model_dir: Path | None = None,
) -> PredictionResult:
    """Score one user or return a clearly marked conservative fallback."""

    predictor = load_predictor(task, model_dir)
    if predictor is None:
        return PredictionResult(
            probability=0.0,
            label=False,
            threshold=1.0,
            model_available=False,
            model_version="unavailable",
            reason="Model artifact unavailable; no automated risk/action assigned.",
        )
    probability = predictor.predict_probability(values)
    return PredictionResult(
        probability=probability,
        label=probability >= predictor.threshold,
        threshold=predictor.threshold,
        model_available=True,
        model_version=predictor.version,
        reason="Behavioural estimate from synthetic-demo model; not an astrology claim.",
    )
