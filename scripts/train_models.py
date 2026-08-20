"""Train, compare, evaluate, and export Orbit behavioural demo models."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ml.features import FEATURES, TARGETS, validate_feature_contract  # noqa: E402
from app.analytics import validate_demo_data  # noqa: E402


SEED = 2026
DEFAULT_DATA = REPO_ROOT / "data" / "demo" / "synthetic_orbit_users.csv"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "models"


def chronological_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """60/20/20 chronological split with deterministic user-id ordering."""

    required = {"as_of_date", "user_id", *FEATURES, *TARGETS.values()}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Training data is missing columns: {sorted(missing)}")
    work = frame.copy()
    work["as_of_date"] = pd.to_datetime(work["as_of_date"], errors="raise")
    work = work.sort_values(["as_of_date", "user_id"]).reset_index(drop=True)
    unique_dates = np.sort(work["as_of_date"].unique())
    first = int(len(unique_dates) * 0.60)
    second = int(len(unique_dates) * 0.80)
    if first < 1 or second <= first or second >= len(unique_dates):
        raise ValueError("Training data is too small for chronological split")
    first_cutoff = unique_dates[first - 1]
    second_cutoff = unique_dates[second - 1]
    train = work.loc[work["as_of_date"] <= first_cutoff]
    validation = work.loc[(work["as_of_date"] > first_cutoff) & (work["as_of_date"] <= second_cutoff)]
    test = work.loc[work["as_of_date"] > second_cutoff]
    return train, validation, test


def metric_bundle(y_true: pd.Series, probabilities: np.ndarray, threshold: float) -> dict[str, object]:
    predicted = (probabilities >= threshold).astype(int)
    matrix = confusion_matrix(y_true, predicted, labels=[0, 1])
    return {
        "accuracy": round(float(accuracy_score(y_true, predicted)), 4),
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 4),
        "brier": round(float(brier_score_loss(y_true, probabilities)), 4),
        "confusion_matrix": {
            "tn": int(matrix[0, 0]),
            "fp": int(matrix[0, 1]),
            "fn": int(matrix[1, 0]),
            "tp": int(matrix[1, 1]),
        },
        "threshold": round(float(threshold), 4),
        "support": int(len(y_true)),
        "positive_rate": round(float(np.mean(y_true)), 4),
    }


def choose_threshold(y_true: pd.Series, probabilities: np.ndarray, task: str) -> tuple[float, dict[str, float]]:
    """Minimize documented validation cost; test labels never tune threshold."""

    # Interventions are passive in-product cards, never unsolicited messages:
    # overlooking need is therefore costlier than showing a dismissible card.
    false_positive_cost, false_negative_cost = (1.0, 3.0) if task == "churn_risk" else (1.0, 2.5)
    best = (float("inf"), 0.5)
    for threshold in np.linspace(0.10, 0.90, 81):
        predicted = probabilities >= threshold
        fp = int(((predicted == 1) & (np.asarray(y_true) == 0)).sum())
        fn = int(((predicted == 0) & (np.asarray(y_true) == 1)).sum())
        cost = (false_positive_cost * fp + false_negative_cost * fn) / len(y_true)
        if cost < best[0]:
            best = (cost, float(threshold))
    return best[1], {
        "false_positive_cost": false_positive_cost,
        "false_negative_cost": false_negative_cost,
        "validation_cost_per_user": round(best[0], 4),
    }


def candidates() -> dict[str, object]:
    return {
        "logistic_regression": Pipeline(
            [
                ("scale", StandardScaler()),
                # Cost-sensitive validation thresholding handles imbalance
                # while preserving probabilities that are useful for Brier
                # evaluation and operator-facing distributions.
                ("model", LogisticRegression(max_iter=1000, random_state=SEED)),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=180,
            max_depth=8,
            min_samples_leaf=10,
            class_weight="balanced",
            random_state=SEED,
            # Single-process operation stays reliable on constrained Windows
            # hackathon runners and remains fast for this compact dataset.
            n_jobs=1,
        ),
    }


def export_logistic(model: Pipeline, task: str, threshold: float, output: Path) -> None:
    scaler: StandardScaler = model.named_steps["scale"]
    estimator: LogisticRegression = model.named_steps["model"]
    payload = {
        "artifact_format": "orbit-logistic-json-v1",
        "task": task,
        "model_version": "synthetic-2026.1",
        "trained_on": "synthetic_orbit_users.csv",
        "features": FEATURES,
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coefficients": estimator.coef_[0].tolist(),
        "intercept": float(estimator.intercept_[0]),
        "threshold": threshold,
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = output / f"{task}.json"
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")


def train_task(
    task: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    output: Path,
) -> dict[str, object]:
    target = TARGETS[task]
    fitted = {}
    comparison = {}
    thresholds = {}
    costs = {}
    for name, model in candidates().items():
        model.fit(train[FEATURES], train[target])
        probabilities = model.predict_proba(validation[FEATURES])[:, 1]
        threshold, cost = choose_threshold(validation[target], probabilities, task)
        metrics = metric_bundle(validation[target], probabilities, threshold)
        # Primary validation evidence is PR-AUC; operational F1 is the tie-break.
        comparison[name] = metrics
        thresholds[name] = threshold
        costs[name] = cost
        fitted[name] = model

    logistic_score = comparison["logistic_regression"]["pr_auc"]
    forest_score = comparison["random_forest"]["pr_auc"]
    # Prefer the auditable deployable model only within a predeclared 0.02
    # validation PR-AUC equivalence margin; otherwise report the forest winner.
    selected = "logistic_regression" if logistic_score >= forest_score - 0.02 else "random_forest"
    if selected != "logistic_regression":
        raise RuntimeError(
            f"{task}: random forest materially outperformed the safe JSON model; "
            "revisit deployment format instead of silently exporting another model"
        )
    model = fitted[selected]
    test_probabilities = model.predict_proba(test[FEATURES])[:, 1]
    test_metrics = metric_bundle(test[target], test_probabilities, thresholds[selected])
    importance = permutation_importance(
        model,
        test[FEATURES],
        test[target],
        scoring="average_precision",
        n_repeats=12,
        random_state=SEED,
        n_jobs=1,
    )
    ranking = sorted(
        [
            {
                "feature": feature,
                "importance_mean": round(float(mean), 5),
                "importance_std": round(float(std), 5),
            }
            for feature, mean, std in zip(FEATURES, importance.importances_mean, importance.importances_std)
        ],
        key=lambda item: item["importance_mean"],
        reverse=True,
    )
    export_logistic(model, task, thresholds[selected], output)
    return {
        "task": task,
        "target": target,
        "selected_model": selected,
        "selection_rule": "Highest validation PR-AUC; prefer logistic within 0.02 equivalence margin.",
        "validation_comparison": comparison,
        "threshold_costs": costs,
        "test_metrics": test_metrics,
        "permutation_importance_test": ranking,
    }


def train_all(data_path: Path = DEFAULT_DATA, output: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    validate_feature_contract()
    frame = pd.read_csv(data_path)
    validate_demo_data(frame)
    train, validation, test = chronological_split(frame)
    for column in FEATURES:
        if not pd.api.types.is_numeric_dtype(frame[column]) or frame[column].isna().any():
            raise ValueError(f"Feature {column} must be complete and numeric")
    output.mkdir(parents=True, exist_ok=True)
    results = {
        "provenance": "Models and metrics use reproducible synthetic demonstration data only.",
        "seed": SEED,
        "features": FEATURES,
        "split": {
            "method": "chronological 60/20/20 by as_of_date, then user_id",
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "train_end": train["as_of_date"].max().strftime("%Y-%m-%d"),
            "validation_start": validation["as_of_date"].min().strftime("%Y-%m-%d"),
            "validation_end": validation["as_of_date"].max().strftime("%Y-%m-%d"),
            "test_start": test["as_of_date"].min().strftime("%Y-%m-%d"),
        },
        "tasks": {},
    }
    for task in TARGETS:
        results["tasks"][task] = train_task(task, train, validation, test, output)
    (output / "evaluation.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    results = train_all(args.data, args.output)
    for task, result in results["tasks"].items():
        metrics = result["test_metrics"]
        print(
            f"{task}: {result['selected_model']}; "
            f"PR-AUC={metrics['pr_auc']:.4f}, ROC-AUC={metrics['roc_auc']:.4f}, "
            f"F1={metrics['f1']:.4f}"
        )


if __name__ == "__main__":
    main()
