"""JSON-safe façade for the Growth Cockpit routes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.features import FEATURES
from app.ml.inference import DEFAULT_MODEL_DIR, load_predictor

from .metrics import activation_funnel, assign_segments, cohort_retention, growth_summary
from .validation import validate_demo_data


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = REPO_ROOT / "data" / "demo" / "synthetic_orbit_users.csv"
ALLOWED_PERIODS = {"all": None, "30d": 30, "90d": 90, "180d": 180}


def load_demo_data(path: Path | None = None) -> pd.DataFrame:
    """Load the public synthetic snapshot table or return an empty frame."""

    source = (path or DEFAULT_DATA_PATH).resolve()
    if path is None and REPO_ROOT.resolve() not in source.parents:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(source)
        validate_demo_data(frame)
    except (FileNotFoundError, OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()
    return frame


def _filtered(frame: pd.DataFrame, period: str, segment: str, focus: str) -> pd.DataFrame:
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"period must be one of {sorted(ALLOWED_PERIODS)}")
    work = frame.copy()
    work["segment"] = assign_segments(work)
    days = ALLOWED_PERIODS[period]
    if days is not None:
        timestamps = pd.to_datetime(work["as_of_date"], errors="coerce")
        latest = timestamps.max()
        work = work.loc[timestamps >= latest - pd.Timedelta(days=days)]
    if segment != "all":
        work = work.loc[work["segment"] == segment]
    if focus != "all":
        work = work.loc[work["focus_area"] == focus]
    return work.copy()


def _risk_distribution(frame: pd.DataFrame, task: str, model_dir: Path | None = None) -> dict[str, Any]:
    predictor = load_predictor(task, model_dir)
    if predictor is None:
        return {"available": False, "bins": [], "message": "Model artifact unavailable."}
    if frame.empty:
        return {"available": True, "bins": [], "message": "No users match these filters."}
    matrix = frame[FEATURES].to_numpy(dtype=float)
    logits = ((matrix - predictor.mean) / predictor.scale) @ predictor.coefficients + predictor.intercept
    probabilities = 1.0 / (1.0 + np.exp(-np.clip(logits, -35, 35)))
    counts, edges = np.histogram(probabilities, bins=np.linspace(0.0, 1.0, 11))
    return {
        "available": True,
        "threshold": predictor.threshold,
        "mean_probability": round(float(probabilities.mean()), 4),
        "above_threshold": int((probabilities >= predictor.threshold).sum()),
        "bins": [
            {
                "from": round(float(edges[index]), 1),
                "to": round(float(edges[index + 1]), 1),
                "count": int(count),
            }
            for index, count in enumerate(counts)
        ],
    }


def model_catalog(model_dir: Path | None = None) -> dict[str, Any]:
    """Expose evaluation evidence and artifact status without loading pickle."""

    root = (model_dir or DEFAULT_MODEL_DIR).resolve()
    evaluation_path = root / "evaluation.json"
    try:
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        evaluation = {}
    tasks = {}
    for task in ("churn_risk", "consultation_intent"):
        evidence = evaluation.get("tasks", {}).get(task, {})
        predictor = load_predictor(task, root)
        tasks[task] = {
            "available": predictor is not None,
            "version": predictor.version if predictor else "unavailable",
            "threshold": predictor.threshold if predictor else None,
            "selected_model": evidence.get("selected_model"),
            "test_metrics": evidence.get("test_metrics", {}),
            "validation_comparison": evidence.get("validation_comparison", {}),
            "feature_importance": evidence.get("permutation_importance_test", []),
            "limitation": "Trained on synthetic demo outcomes; not validated on AstroLive users.",
        }
    return {
        "available": all(value["available"] for value in tasks.values()),
        "split": evaluation.get("split", {}),
        "provenance": evaluation.get(
            "provenance", "Evaluation metadata unavailable; automated claims are suppressed."
        ),
        "tasks": tasks,
    }


def anonymized_drilldown(
    frame: pd.DataFrame,
    limit: int = 25,
    model_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Return capped, non-identifying behavioural rows for operator review."""

    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if frame.empty:
        return []
    predictors = {task: load_predictor(task, model_dir) for task in ("churn_risk", "consultation_intent")}
    output = []
    for _, row in frame.head(limit).iterrows():
        item: dict[str, Any] = {
            "anonymous_id": "U-" + hashlib.sha256(str(row["user_id"]).encode()).hexdigest()[:10].upper(),
            "focus_area": str(row["focus_area"]),
            "segment": str(row["segment"] if "segment" in row else assign_segments(pd.DataFrame([row])).iloc[0]),
            "weekly_active_days": int(row["weekly_active_days"]),
            "pulse_checkins_7d": int(row["pulse_checkins_7d"]),
            "consultations_90d": int(row["consultations_90d"]),
        }
        for task, predictor in predictors.items():
            item[task] = (
                round(predictor.predict_probability(row.to_dict()), 4) if predictor is not None else None
            )
        output.append(item)
    return output


def snapshot(
    period: str = "all",
    segment: str = "all",
    focus: str = "all",
    data_path: Path | None = None,
    model_dir: Path | None = None,
) -> dict[str, Any]:
    """Return the complete Growth Cockpit payload with graceful empty state."""

    frame = load_demo_data(data_path)
    if frame.empty:
        return {
            "available": False,
            "filters": {"period": period, "segment": segment, "focus": focus},
            "message": "Synthetic analytics dataset unavailable.",
            "provenance": "No data loaded; no metrics inferred.",
            "models": model_catalog(model_dir),
        }
    filtered = _filtered(frame, period, segment, focus)
    if filtered.empty:
        # Keep the response contract complete so server-rendered consumers can
        # safely display an honest zero-result state for arbitrary filters.
        summary = growth_summary(filtered)
        funnel: list[dict[str, Any]] = []
        cohorts: list[dict[str, Any]] = []
    else:
        summary = growth_summary(filtered)
        funnel = activation_funnel(filtered)
        cohorts = cohort_retention(filtered)
    choices = {
        "periods": list(ALLOWED_PERIODS),
        "segments": ["all", *sorted(assign_segments(frame).unique().tolist())],
        "focus_areas": ["all", *sorted(frame["focus_area"].dropna().astype(str).unique().tolist())],
    }
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["segment"] = assign_segments(filtered)
    return {
        "available": True,
        "filters": {"period": period, "segment": segment, "focus": focus},
        "filter_options": choices,
        "summary": summary,
        "funnel": funnel,
        "cohorts": cohorts,
        "distributions": {
            "churn_risk": _risk_distribution(filtered, "churn_risk", model_dir),
            "consultation_intent": _risk_distribution(filtered, "consultation_intent", model_dir),
        },
        "models": model_catalog(model_dir),
        "users": anonymized_drilldown(filtered, model_dir=model_dir),
        "provenance": "All dashboard observations are reproducible synthetic demonstrations, not AstroLive KPIs.",
    }
