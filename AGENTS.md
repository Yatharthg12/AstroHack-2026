# AGENTS.md

Instructions for contributors and coding agents working in this repository.

## Mission and non-negotiables

Build AstroLive Orbit as a working AstroHack 2026 prototype: daily Pulse → user-approved consultation Bridge → demo human guidance → follow-up/Journey → dual-consent Circle referral → measurable Growth Cockpit.

- Keep the stack Python 3.11+, Flask/Jinja, standard `sqlite3`, HTML, handcrafted CSS, vanilla JavaScript, pandas, NumPy, and scikit-learn.
- Do not introduce React, TypeScript, Node build tooling, Tailwind, Bootstrap, Streamlit, paid APIs, private credentials, or runtime AI services.
- Preserve the role of human astrologers. ML predicts product behavior only; it must not generate destiny, compatibility, or high-stakes advice.
- All behavioral data and model metrics currently committed are synthetic. Never describe them as AstroLive users, KPIs, or measured impact.
- All sample astrologers, prices, bookings, and simulator outputs are demos. Never imply an actual booking, charge, forecast, or deployment.
- Do not invent citations, interviews, metrics, test results, screenshots, URLs, or report QA.

## Setup

Windows:

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```

POSIX:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run locally:

```bash
python run.py
```

Production-style servers:

```bash
# Linux/Render
gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 2 run:app

# Windows
waitress-serve --listen=127.0.0.1:8000 --call app:create_app
```

Health endpoint: `GET /api/health`.

## Repository boundaries

- `app/routes/`: HTTP parsing, response shape, and template context only.
- `app/services/`: business rules, consent enforcement, and database transactions.
- `app/analytics/`: pure calculations and JSON-safe dashboard assembly.
- `app/ml/`: canonical feature contract and non-executable JSON inference.
- `app/db.py`: schema and low-level SQLite helpers.
- `scripts/`: reproducible offline generation, training, evaluation, smoke, and report tasks.
- `data/demo/`: public synthetic data only.
- `artifacts/models/`: compact JSON models, matching `.sha256` sidecars, and evaluation metadata.
- `instance/`: local runtime database; never commit.
- `submission/`: final exact-name PDF only, plus no temporary page renders.

Keep user-input validation server-side even when mirrored in HTML/JavaScript. Keep SQL parameterized. Do not move domain rules into templates.

## Environment configuration

Supported variables:

- `ORBIT_SECRET_KEY`: required for stable/production sessions; fallback is intentionally ephemeral and warns.
- `ORBIT_DATABASE`: SQLite path; defaults to `instance/orbit.db`.
- `ORBIT_MODEL_DIR`: defaults to `artifacts/models`.
- `ORBIT_DEMO_DATA`: defaults to `data/demo/synthetic_orbit_users.csv`.
- `ORBIT_SECURE_COOKIES`: set `1` behind HTTPS.
- `HOST`, `PORT`, `FLASK_DEBUG`: development entrypoint settings.

Never commit `.env`. Update `.env.example` if a new non-secret variable is introduced.

## Data and model changes

Regenerate in order:

```bash
python scripts/generate_demo_data.py
python scripts/train_models.py
```

Rules:

- preserve seed 2026 unless a documented experiment requires another seed;
- keep `data_provenance=synthetic_demo` and avoid personal/free-text fields;
- do not put target or future-window fields into `FEATURES`;
- fit preprocessing on training data only;
- select models and thresholds using validation evidence only;
- keep holdout metrics unmodified in `evaluation.json`;
- prefer portable JSON coefficients; never add pickle/joblib loading to the web process;
- regenerate `.sha256` with its matching artifact;
- update data audit/model card/README only from actual artifacts.

The models’ modest synthetic discrimination/precision and the churn threshold’s false-positive trade-off are limitations to disclose, not results to “fix” by hiding metrics or tuning on test labels.

## Consent and privacy invariants

Tests must preserve these boundaries:

- onboarding cannot persist without save consent;
- Circle invitations cannot be created without separate Circle consent;
- prior check-ins appear in the Console only when the brief explicitly includes them;
- referral URLs contain only a random token, never private/user attributes;
- mutual insight appears only after inviter and invitee consent;
- invalid/expired tokens disclose no private context;
- reset deletes the current local user and cascaded state;
- missing/tampered models produce no automated action.

Never log or publish entered concerns, birth details, session cookies, CSRF tokens, or referral tokens.

## Required verification

Run from repository root after implementation changes:

```bash
python -m pytest -q
python -m compileall -q app scripts run.py
python -m ruff check app scripts tests run.py
```

Then:

1. start Gunicorn on Linux/CI or Waitress on Windows;
2. smoke every main page and JSON API, including validation failures;
3. exercise the complete browser journey at desktop and 360 px mobile widths;
4. inspect browser console, keyboard focus, reduced motion, overflow, and chart legibility;
5. run a secret scan and repository-cleanliness check;
6. record exact results in `docs/SUBMISSION_CHECKLIST.md`—never pre-check them.

Do not weaken or remove meaningful tests to get a green result. Diagnose the underlying defect.

## Report verification

The required output is exactly:

```text
submission/AstroLive_OrbitWorks_YatharthGarg.pdf
```

After generation:

1. confirm the file exists and is at least eight substantive pages;
2. extract text and verify every required section, citations, and AI disclosure;
3. render every page to images using PyMuPDF;
4. visually inspect every page for clipping, blank/filler space, bad breaks, broken images, unreadable charts, and missing page numbers;
5. keep only final report assets/screenshots; remove temporary renders;
6. update README/checklist with observed page count and commands/results.

The report must distinguish observed public facts, company-reported claims, synthetic data/model findings, inferences, and simulations.

## Deployment

Render/Linux command:

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60 run:app
```

The free `render.yaml` stores SQLite at `/tmp/orbit.db`; state is ephemeral. Never describe it as persistent. If attaching a disk, mount `/var/data` and set `ORBIT_DATABASE=/var/data/orbit.db`. For more than one writing instance, migrate away from SQLite and the process-local rate limiter.

Do not claim a public URL until it has been deployed and the full journey and `/api/health` were verified on that exact URL.

## Documentation update rule

When implementation or verification changes, update only claims supported by repository evidence. In particular, keep these synchronized:

- README route/features/metrics and run commands;
- `docs/ARCHITECTURE.md` boundaries and data flow;
- `docs/DATA_AUDIT.md` file shape/provenance;
- `docs/MODEL_CARD.md` artifact metrics and limitations;
- `docs/EXPERIMENTATION.md` simulator defaults/method;
- `docs/PRIVACY_AND_ETHICS.md` consent/data behavior;
- `docs/SUBMISSION_CHECKLIST.md` actual pass/fail/pending evidence;
- final report and references.
