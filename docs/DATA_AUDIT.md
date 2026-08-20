# Data Audit

Last verified: 20 August 2026

## Finding and provenance

No organizer-supplied CSV, TSV, XLSX, JSON, JSONL, Parquet, or database was present when the repository was initialized. The project therefore does **not** claim access to AstroLive customer data. `data/demo/synthetic_orbit_users.csv` is a generated demonstration dataset: 2,400 fictional user-level behavioural snapshots produced with NumPy seed `2026` by `python scripts/generate_demo_data.py`. Re-running that command reproduces the file byte-for-byte under the pinned dependency set.

The table contains no names, email addresses, phone numbers, birth details, free text, precise locations, device identifiers, or real account identifiers. IDs use the obvious `SYN-00001` pattern. It must never be described as observed users, measured product performance, a randomized experiment, or evidence that Orbit improves retention.

## Inventory and structural checks

| File | Format | Rows × columns | Missing cells | Duplicate rows | Duplicate user IDs |
|---|---:|---:|---:|---:|---:|
| `data/demo/synthetic_orbit_users.csv` | UTF-8 CSV | 2,400 × 33 | 0 | 0 | 0 |

Temporal coverage is 2026-01-01 through 2026-07-31 for prediction snapshots. Fictional signup dates span 2024-08-02 through 2026-06-27. Each user has one snapshot, so the table does not support within-person causal or longitudinal inference. All users are at least 30 days old at their prediction cutoff, making D30 demonstration labels structurally eligible; the retention fields are simulated outcomes, not observation from a production event ledger.

## Data dictionary

| Columns | Stored type | Meaning and range/validation |
|---|---|---|
| `user_id` | string | Synthetic stable identifier; unique and non-PII. |
| `data_provenance` | string | Constant `synthetic_demo`, enabling prominent UI labelling. |
| `as_of_date`, `signup_date` | ISO date string | Feature cutoff and fictional signup date; signup precedes cutoff. |
| `focus_area` | category string | Career, relationship, finance, education, family, or personal growth; generated, not sensitive user testimony. |
| `account_age_days` | integer | Days from signup to snapshot, 30–539. |
| `days_since_last_session` | integer | Product-session recency, clipped to 0–75; `<7` exactly when `sessions_7d>0`, and `<30` exactly when `sessions_30d>0`. |
| `sessions_7d`, `sessions_30d` | integer | Session frequency at cutoff; 7-day count never exceeds 30-day count. Zero 30-day sessions force content diversity, Pulse, and brief counts to zero. |
| `pulse_checkins_7d`, `pulse_checkins_30d` | integer | Completed Pulse counts; each is capped by sessions in the same window. |
| `weekly_active_days` | integer | Active days in the preceding week, bounded by both 7 and `sessions_7d`. |
| `avg_session_minutes` | float | Mean session duration, clipped to 1–25 minutes. |
| `content_diversity_30d` | integer | Count of content categories, 0–7. |
| `consultations_90d` | integer | Prior fictional consultations, 0–5. |
| `days_since_last_consultation` | integer | 1–90 when one exists; sentinel 180 means none in the window. |
| `briefs_started_30d` | integer | Prior Bridge brief starts, 0–5. |
| `referrals_created_90d` | integer | Prior Circle invites, 0–3. |
| `feedback_helpful_rate` | float | Smoothed fictional helpfulness fraction, 0–1. |
| `signup_completed` … `consultation_booked` | binary integer | Nested synthetic activation funnel: signup → onboarding → Pulse → brief → booking. Pulse/brief flags exactly match positive 30-day Pulse/brief counts. |
| `repeat_consultation_90d` | binary integer | At least two prior consultations in 90 days. |
| `invites_created`, `invites_opened`, `invites_completed` | integer | Aggregated referral flow; completed ≤ opened ≤ created. |
| `retained_d1`, `retained_d7`, `retained_d30` | binary integer | Nested simulated retention outcomes; D30 ≤ D7 ≤ D1. |
| `future_30d_churn` | binary target | Simulated absence/disengagement outcome after cutoff. |
| `future_14d_consultation` | binary target | Simulated consultation outcome after cutoff. |

Numeric values are finite, non-negative where applicable, and within the stated bounds. The generator enforces funnel and retention ordering. Validation tests cover determinism, missingness, ID uniqueness, target encoding, and strict temporal splits.

## Target availability and balance

| Target | Positive | Negative | Positive share |
|---|---:|---:|---:|
| Future 30-day churn | 1,038 | 1,362 | 43.25% |
| Future 14-day consultation | 489 | 1,911 | 20.38% |

These labels are deliberately simulated after the cutoff so the repository can demonstrate a correct training workflow. They are not fabricated *claims*: every artifact and surface identifies them as synthetic. Class imbalance is handled by cost-sensitive validation thresholds for logistic regression and balanced class weights for the random-forest comparator.

## Transformations and leakage controls

`app/ml/features.py` defines exactly 14 pre-cutoff aggregate features. Direct outcomes, future sessions/revenue, the historical funnel booking flag, and D30 retention are explicitly forbidden. Features are computed before target windows and preprocessing is fitted only on training data through a scikit-learn pipeline. Rows are ordered by `as_of_date` and split on strict, non-overlapping date boundaries: 1,411 training rows through 2026-05-07; 507 validation rows from 2026-05-08 through 2026-06-18; and 482 untouched test rows from 2026-06-19 onward. No user appears twice.

Scaling means and standard deviations are learned from training rows only. Validation chooses the model and threshold. The test split is used once for final evaluation and permutation importance. The `focus_area`, funnel, referral outcomes, retention outcomes, provenance, dates, and identifiers are excluded from model inputs.

## Privacy, bias, and responsible use

The dataset contains no demographic groups, so subgroup fairness cannot be evaluated. That absence prevents discriminatory demographic targeting but does not prove fairness. Product engagement can proxy for access, language, disability, disposable time, or connectivity. A production study needs consent, retention rules, deletion handling, subgroup performance/error review, calibration monitoring, drift alerts, and a controlled rollout against a simple rules baseline.

Predictions may prioritize an optional in-product explanation or support card only. They must not set prices, restrict service, infer personality, make fate/health/legal/financial claims, contact a user without consent, replace an astrologer, or be treated as proof of astrology. The dashboard’s synthetic retention, funnel, and K-factor values validate calculations—not business impact.

## Limitations

- The generator encodes its authors’ assumptions; successful recovery of those patterns is not evidence of external validity.
- One row per fictional user cannot represent repeated exposure, seasonality beyond seven months, network dependence, censoring, or concept drift.
- Retention and funnel values come from a snapshot abstraction rather than raw events.
- There is no revenue target; the dashboard must not present observed ARPU/LTV or incremental revenue from this table.
- Model metrics are uncertain on 482 test rows and require confidence intervals and prospective validation before any production decision.
