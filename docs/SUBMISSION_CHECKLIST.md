# Submission Checklist

Snapshot date: **2026-08-20**. This file distinguishes evidence already present from work that still requires execution. A checkbox is marked only when the repository currently contains objective evidence; test and visual-QA items remain pending until their results are recorded.

Legend: `[x]` present/verified from repository evidence, `[ ]` pending verification or artifact.

## Submission identity and compliance

- [x] Product name: AstroLive Orbit
- [x] Team name: OrbitWorks
- [x] Team leader: Yatharth Garg
- [x] Required PDF filename documented: `AstroLive_OrbitWorks_YatharthGarg.pdf`
- [x] Challenge requires a working public prototype and report of at least eight pages.
- [x] Public research sources and AI usage are documented.
- [ ] Final repository URL is public and opens without authentication.
- [ ] Final deployed prototype URL is public and verified.
- [x] Exact PDF exists at `submission/AstroLive_OrbitWorks_YatharthGarg.pdf`.
- [x] PDF verifier reports 12 pages, exceeding the eight-page minimum.
- [ ] Final submission is uploaded by the team leader before the portal deadline.

## Product scope

- [x] Flask application factory and SQLite schema exist.
- [x] Onboarding rules include minimum fields, deterministic sun sign, save consent, and optional Circle consent.
- [x] Pulse service includes deterministic reflection, micro-action, explanation, persistence, feedback, streak, and weekly state.
- [x] Bridge service validates an approved consultation brief and optional check-in context.
- [x] Demo booking uses named sample astrologers and explicitly records that no real booking/charge occurred.
- [x] Astrologer Console service filters check-ins by consent.
- [x] Follow-up stores a user-approved summary, one to three actions, date, and optional helpfulness.
- [x] Journey timeline and current-user cascade reset exist.
- [x] Circle uses random tokens, seven-day expiry, current-consent checks, atomic create/revoke and single-winner completion, transient guest input, withdrawal invalidation, and redacted consumed/replay responses.
- [x] Growth analytics, synthetic provenance, rule-based segments, model evidence, filters, and anonymized drill-down exist in backend code.
- [x] Simulator enforces at least 10,000 trials, seeded results, uncertainty summaries, sensitivity, persistence, and JSON/CSV downloads.
- [ ] Every page/template and visible control is exercised successfully in a browser.
- [ ] Full landing → Circle → Growth journey passes at desktop and 360 px mobile widths.

## Data and ML

- [x] No organizer dataset was found at pipeline creation; fallback is documented.
- [x] `data/demo/synthetic_orbit_users.csv` is explicitly synthetic and reproducible with seed 2026.
- [x] Current CSV inventory: 2,400 rows, 33 columns, 2026-01-01 through 2026-07-31.
- [x] Synthetic file has fictional IDs and no names, contacts, birth details, locations, or free text.
- [x] Feature contract names 14 behavioral predictors and denies future/outcome fields.
- [x] Training uses a chronological 60/20/20 split.
- [x] Logistic regression is compared with a balanced random forest using validation evidence.
- [x] Thresholds are selected on validation costs and test metrics are retained separately.
- [x] Evaluation includes accuracy, precision, recall, F1, ROC-AUC, PR-AUC, Brier, confusion matrix, and permutation importance.
- [x] Compact JSON artifacts have SHA-256 sidecars; inference does not load pickle.
- [x] Missing/tampered artifact fallback assigns no automated action.
- [x] Data audit matches the committed CSV shape, dates, target balance, split, and limitations.
- [x] Model card matches `artifacts/models/evaluation.json` metrics, thresholds, and limitations.
- [ ] Data generation and training are rerun in a clean environment and byte/result reproducibility is recorded.

## Security and privacy

- [x] Environment secret and visible development fallback warning.
- [x] Parameterized SQL, foreign keys, constraints, request-size limit, server validation, CSRF, and safe error shapes.
- [x] CSP, frame, MIME, referrer, permissions, HSTS, and cookie controls.
- [x] Referral URLs omit private context; tokens are high-entropy and time-limited.
- [x] Separate save, Circle, consultation-context, and invitee consent boundaries.
- [x] Current-session reset deletes owner-scoped experiment runs, the server-side demo user, and cascaded state before clearing the session.
- [x] Responsible-astrology and ML prohibited-use boundaries documented.
- [x] Automated private-data non-disclosure, expiry/throttling, CSRF, reset-confirmation, cache-control, integrity-health, schema-migration, and owner-nonce export-isolation tests pass.
- [ ] Secret scan reports no committed credentials or private records.
- [ ] Dependency vulnerability review completed or residual findings documented.

## Verification evidence still to record

- [x] `.venv\\Scripts\\python.exe -m pytest -q` — **68 passed in 22.47s** on 2026-08-20
- [x] `python -m compileall -q app scripts run.py` — passed on 2026-08-20
- [x] `.venv\\Scripts\\python.exe -m ruff check app scripts tests run.py` — **all checks passed** on 2026-08-20
- [ ] Clean virtual-environment install from `requirements.txt` — result: **pending**
- [ ] Gunicorn Linux/Render smoke — result: **pending**
- [x] Waitress Windows factory smoke on `127.0.0.1:8099` — `/api/health` healthy/database ok and `/` HTTP 200 on 2026-08-20
- [ ] HTTP smoke for every page and API — result: **pending**
- [ ] Browser console has no runtime errors — result: **pending**
- [ ] Keyboard navigation, focus visibility, reduced motion, and contrast inspected — result: **pending**
- [ ] Desktop screenshots inspected — result: **pending**
- [ ] 360 px mobile screenshots inspected — result: **pending**
- [x] `.venv\\Scripts\\python.exe scripts/secret_scan.py` — **86 text files scanned; no findings** on 2026-08-20
- [ ] Repository cleanliness/size check — result: **pending**
- [x] `python scripts/evaluate_submission.py` — minimum objective score **8/10**, all seven categories at or above target on 2026-08-20; these are repository-evidence rubric scores, not organizer judging results

## Report QA still to record

- [x] Editable source exists at `report/report_source.md`.
- [x] Python generator exists at `scripts/generate_report.py`; build manifest records the output.
- [x] Final PDF exact path/name exists.
- [x] Verifier reports 12 pages and no potential blank pages.
- [x] Verifier found all 22 required sections after extraction.
- [x] Report source includes an explicit references section and cited external claims.
- [x] Report source defines and uses observed, publisher-claim, synthetic, inferred, simulated, and repository-verified labels.
- [x] AI disclosure truthfully names ChatGPT and Codex roles.
- [ ] Every page is rendered to an image and visually inspected.
- [ ] No blank/filler pages, clipping, overflow, orphan headings, tiny charts, or broken images.
- [ ] Page numbers, headers/footers, captions, and readable typography verified.

## Deployment readiness

- [x] `requirements.txt` contains pinned runtime dependencies.
- [x] `Dockerfile` runs as a non-root user with Gunicorn; only `/app/instance` is transferred to the runtime user, leaving application code root-owned/read-only.
- [x] `Procfile` contains a Gunicorn command.
- [x] `render.yaml` defines Python, secret generation, secure cookies, start command, and `/api/health`.
- [x] `.env.example` contains no real secret.
- [x] README documents Render and Docker deployment.
- [x] Ephemeral SQLite warning and persistent-disk migration path documented.
- [ ] `render.yaml` validated by Render Blueprint schema/CLI.
- [ ] Container image builds and `/api/health` passes.
- [ ] Public deploy completed and full flow verified.

## Public repository manifest

The final public repository should contain these categories. Items marked pending must be confirmed after concurrent build/report work finishes.

```text
.
├── app/
│   ├── __init__.py, config.py, db.py
│   ├── analytics/               # funnel, cohort, growth, distribution calculations
│   ├── ml/                      # feature contract and safe JSON inference
│   ├── routes/                  # web and JSON blueprints
│   ├── services/                # journey, consultation, referrals, growth, simulator
│   ├── static/                  # handcrafted CSS/vanilla JS/assets
│   └── templates/               # Jinja product/operator/error pages
├── artifacts/models/            # JSON models, SHA-256 digests, evaluation.json
├── data/demo/                    # public synthetic CSV only
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_AUDIT.md
│   ├── DEMO_SCRIPT.md
│   ├── EXPERIMENTATION.md
│   ├── MODEL_CARD.md
│   ├── PRIVACY_AND_ETHICS.md
│   ├── PRODUCT_TEARDOWN.md
│   ├── REFERENCES.md
│   └── SUBMISSION_CHECKLIST.md
├── report/                       # editable source, generation script, assets, and QA manifest
├── scripts/                      # data, training, report, smoke/evaluator scripts
├── submission/
│   └── AstroLive_OrbitWorks_YatharthGarg.pdf  # generated exact-name report
├── tests/                        # service, flow, security, analytics, and ML tests
├── .env.example
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── Dockerfile
├── LICENSE
├── Procfile
├── README.md
├── render.yaml
├── requirements-dev.txt
├── requirements.txt
└── run.py
```

## Exclusion/cleanliness rules

Do not publish:

- `.env`, API keys, passwords, tokens, private certificates, or secret scan output containing values;
- `instance/orbit.db`, local sessions, user-entered demo text, or any private/raw dataset;
- virtual environments, caches, coverage, browser traces, temporary PDF renders, or redundant QA images;
- invented deployment URLs, user interviews, production metrics, or experiment results.

Do retain the explicitly synthetic CSV, compact safe model artifacts, final selected screenshots, final PDF, reproducibility scripts, source documents, and objective verification evidence.
