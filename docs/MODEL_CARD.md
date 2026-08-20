# Model Card: Orbit Behavioural Demonstration Models

Version `synthetic-2026.1` · evaluated 20 August 2026

## Summary

Two binary classifiers demonstrate how AstroLive Orbit could estimate **product behaviour**, not astrological truth:

1. `churn_risk`: probability of simulated disengagement in the 30 days after a snapshot.
2. `consultation_intent`: probability of a simulated consultation in the next 14 days.

Both selected models are logistic regressions. They are intended only to populate a transparent, non-transactional prototype and to illustrate a reviewable ML lifecycle. They were trained entirely on `data/demo/synthetic_orbit_users.csv`; results do not describe real AstroLive users, accuracy, lift, revenue, retention, or impact.

## Data and features

The source has 2,400 fictional users generated with seed 2026. The strict chronological split is:

| Split | Rows | Date range | Use |
|---|---:|---|---|
| Train | 1,411 | through 2026-05-07 | Fit scaler and candidates |
| Validation | 507 | 2026-05-08 to 2026-06-18 | Compare models and select threshold |
| Test | 482 | from 2026-06-19 | One final report and permutation importance |

The 14 pre-cutoff features cover account age; session recency/frequency; Pulse activity; weekly activity; session intensity; content diversity; prior consultation recency/frequency; Bridge starts; referral activity; and prior helpfulness fraction. Exact definitions and the leakage deny-list are in `app/ml/features.py` and [DATA_AUDIT.md](DATA_AUDIT.md).

There are no birth details, concerns/free text, demographic attributes, or astrological signs in the model. Standardization is fitted inside the logistic pipeline on training rows only. The random forest comparator uses balanced class weights. The selected logistic model handles operational imbalance with a validation-only cost-sensitive threshold.

## Candidate selection

An interpretable logistic regression was compared with a nonlinear random forest (180 trees, maximum depth 8, minimum leaf size 10). The declared rule selects the highest validation PR-AUC and prefers logistic regression only when it is within 0.02 PR-AUC of the forest. This is an explicit equivalence margin for auditability and safe JSON deployment, not an after-the-fact choice.

| Task/model | Validation PR-AUC | ROC-AUC | F1 | Brier |
|---|---:|---:|---:|---:|
| Churn logistic **selected** | 0.6810 | 0.7089 | 0.6165 | 0.2067 |
| Churn random forest | 0.6889 | 0.7065 | 0.6196 | 0.2087 |
| Intent logistic **selected** | 0.3929 | 0.6761 | 0.4192 | 0.1704 |
| Intent random forest | 0.3518 | 0.6359 | 0.4060 | 0.2096 |

The selection decision uses validation evidence only. Accuracy is not used to select a model because it can hide minority-class failures.

## Held-out test performance

| Task | Threshold | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | Brier | TN / FP / FN / TP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Churn risk | 0.18 | 0.4461 | 0.4242 | 0.9949 | 0.5948 | 0.6939 | 0.6077 | 0.2130 | 19 / 266 / 1 / 196 |
| Consultation intent | 0.27 | 0.7220 | 0.3056 | 0.3587 | 0.3300 | 0.7196 | 0.3459 | 0.1437 | 315 / 75 / 59 / 33 |

The churn threshold intentionally produces many false positives. The assumed intervention is a dismissible, in-product support card; missing a disengaging user is assigned 3× the cost of displaying that card. Intent uses a 2.5× false-negative cost because the action is an optional Bridge prompt, never unsolicited outreach. These subjective cost ratios are editable product assumptions, not empirical AstroLive costs. Thresholds minimize weighted error on validation data and are frozen before test evaluation.

PR-AUC should be read against the test prevalence (40.87% churn; 19.09% intent). Calibration is only summarized by Brier score; no production calibration claim is made. The low discrimination and precision are reasons to keep humans and user choice in control.

## Interpretability

Permutation importance uses test-set average precision with 12 fixed-seed repeats. The largest mean changes were:

| Task | Top features (mean PR-AUC decrease) |
|---|---|
| Churn | days since last session 0.16158; prior consultations 0.01493; days since last consultation 0.00723 |
| Intent | days since last consultation 0.02525; content diversity 0.01141; sessions in 7 days 0.00918 |

Near-zero or negative permutation values are retained in `artifacts/models/evaluation.json`; they should not be narrated as meaningful drivers. Importance is predictive association inside a synthetic generator, not a causal explanation.

## Artifact and inference safety

The deployed artifacts are small JSON files containing only an ordered feature list, scaling constants, logistic coefficients, intercept, threshold, and provenance. A sibling SHA-256 file is verified before parsing. The loader accepts only fixed task names and filenames below the configured artifact directory; it does not use pickle, `eval`, dynamic imports, or executable deserialization.

If a file is absent, malformed, mismatched to the feature contract, or fails integrity verification, `predict_user()` returns `model_available=false`, probability 0, label false, and a reason. It does not silently substitute a heuristic. `app.analytics.model_catalog()` and `snapshot()` expose the same status to the Growth Cockpit.

## Fairness, human oversight, and prohibited uses

Fairness across age, gender, caste, religion, income, language, disability, geography, and other groups is unknown because those fields do not exist. Engagement features may still encode unequal access. Before production: evaluate subgroup error and calibration with lawful, consented audit data; test notification burden; monitor drift; add appeals/feedback; and run a prospective experiment with guardrails.

Never use these models to:

- claim astrology is scientifically validated or predict fate, health, safety, legal, credit, employment, education, or investment outcomes;
- diagnose emotion or vulnerability, target anxiety, manipulate urgency, or make an automatic booking;
- set prices, eligibility, ranking, or astrologer compensation;
- expose private concerns to an astrologer or Circle contact without specific consent;
- replace professional or astrologer judgement; or
- report this synthetic performance as AstroLive production performance.

Appropriate prototype uses are aggregate dashboard distributions and a dismissible, explained suggestion to continue a user-initiated journey. Operators should see the model version, threshold, provenance, limitations, and error trade-off.

## Reproduction

```bash
python scripts/generate_demo_data.py
python scripts/train_models.py
python -m pytest tests/test_data_ml.py tests/test_analytics.py -q
```

Machine-readable comparisons, confusion matrices, thresholds, split boundaries, and full importance rankings are in `artifacts/models/evaluation.json`. Any regenerated metric must replace—not be blended with—the figures above.
