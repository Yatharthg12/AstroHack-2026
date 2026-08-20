# Experimentation and Impact Simulation

Orbit’s simulator is a **scenario-planning tool**, not an impact claim, forecast, or substitute for an experiment. The repository had no real AstroLive intervention data. Every default is an editable conservative product assumption chosen to make the mechanism inspectable; it is not a measured AstroLive baseline.

## Questions the prototype can test

| Hypothesis | Primary measure | Guardrails | Required real test |
|---|---|---|---|
| A small Pulse ritual increases recurring guided activity | Weekly Guided Users; D7/D30 retention | opt-out, low relevance, safety flags | randomized Pulse eligibility or phased rollout |
| A user-approved brief improves consultation readiness | brief-to-booking conversion; time to meaningful discussion | brief edits, abandonment, unwanted context sharing | controlled Bridge flow with astrologer feedback |
| Follow-up creates value beyond a single session | action completion; helpfulness; repeat consultation | pressure complaints, notification opt-out | post-consultation randomized follow-up timing/content |
| Mutual Circle value creates consented acquisition | invite completion; K-factor; activated invitees | unwanted invites, consent withdrawal, blocks | holdout or randomized invitation prompt |

No hypothesis is “validated” by the synthetic dataset or simulator.

## North star and supporting metrics

**Weekly Guided Users (WGU):** unique consenting users who complete at least one meaningful guidance step during a seven-day window. The synthetic dashboard uses the exact signal it has—at least one Pulse check-in in seven days—and does not treat a 90-day consultation aggregate as weekly. Production should extend the event contract to deduplicated consultation and follow-up steps.

Supporting measures:

- activation funnel: signup → onboarding → first Pulse → Bridge brief → consultation;
- D1, D7, and D30 retention and signup-month cohorts;
- Pulse completion and helpfulness;
- consultation conversion and repeat-consultation rate;
- invite creation, open, and consented completion;
- viral coefficient `K = invites per eligible user × invite completion rate`;
- trust guardrails, including deletion success, sharing complaints, and opt-out.

## Simulator defaults

The implementation validates all inputs and runs at least 10,000 trials.

| Input | Default | Allowed range | Provenance |
|---|---:|---:|---|
| Eligible users | 10,000 | 100–10,000,000 | Editable round scenario size; not AstroLive traffic |
| Pulse adoption | 22% | 0–100% | Assumption |
| Baseline retention | 24% | 0–100% | Assumption |
| Relative retention uplift | 10% | -50–100% | Assumption |
| Share rate | 8% | 0–100% | Assumption |
| Invites per sharer | 1.4 | 0–20 | Assumption |
| Invite conversion | 18% | 0–100% | Assumption |
| Baseline consultation conversion | 5.5% | 0–100% | Assumption |
| Scenario consultation conversion | 7.2% | 0–100% | Assumption |
| Repeat-consultation uplift | 8% | -50–100% | Assumption |
| Average consultation revenue | ₹0 | ₹0–₹1,000,000 | Zero by default because no defensible repository revenue input exists |
| Trials | 10,000 | 10,000–100,000 | Minimum required simulation precision; bounded for prototype resource safety |
| Random seed | 2026 | 0–2³²−1 | Reproducibility control |

The company-reported CAC/LTV values in the research references are not simulator defaults and are not treated as measured unit economics.

## Simulation mechanics

For each trial, bounded uncertainty is sampled around editable adoption, retention, share, conversion, and repeat assumptions. Counts use binomial sampling where a user-level event is represented.

```text
scenario retention rate
  = baseline retention × (1 + Pulse adoption × retention uplift)

incremental organic users
  = eligible users × Pulse adoption × share rate
    × invites per sharer × invite conversion

baseline consultations
  ~ Binomial(eligible users, baseline consultation conversion)

scenario consultations
  ~ Binomial(eligible users + organic users, scenario consultation conversion)
    × (1 + repeat-consultation uplift)
```

Rates are clipped to `[0, 1]`. Retention and consultation counts include binomial variability. The simulator reports baseline and scenario distributions plus incremental retained users, consultations, and organic users. Incremental revenue is emitted only when average consultation revenue is positive.

Each output reports:

- expected value (arithmetic mean);
- median;
- 5th percentile;
- 95th percentile;
- input echo and seed;
- sensitivity ranking.

Sensitivity is the absolute Pearson correlation between each sampled driver and a composite scenario outcome (`incremental retained + organic + incremental consultations`). This is a local diagnostic, not a causal importance score.

## Reproducibility and export

The same validated inputs and seed produce the same result. Successful API simulations are stored in `experiment_runs` with their input and result JSON. Stored runs can be downloaded as JSON or a flattened CSV through `/api/experiments/<run_id>.json` and `/api/experiments/<run_id>.csv`.

Local programmatic check:

```bash
python -c "from app import create_app; from app.services.experiments import simulate; app=create_app({'TESTING': True}); ctx=app.app_context(); ctx.push(); print(simulate({'trials': 10000, 'seed': 2026}, persist=False)['label']); ctx.pop()"
```

This command prints the scenario label; automated tests should compare complete deterministic result payloads and validate bounds.

## From simulation to a real experiment

1. Define event names, eligibility, exposure, consent, and metric windows before launch.
2. Run an A/A instrumentation check.
3. Randomize at user level; prevent invitation spillover from contaminating the control analysis.
4. Pre-register the primary metric, minimum detectable effect, duration, and stopping rule.
5. Evaluate intent-to-treat first. Report confidence intervals and absolute effects, not only percent uplift.
6. Review guardrails and subgroup calibration before rollout.
7. Update simulator assumptions from measured intervals, retaining provenance and date.

Suggested experiment sequence:

- Phase 1: Pulse vs current experience, measuring WGU and D7 retention.
- Phase 2: Bridge brief vs standard consultation entry, measuring booking and astrologer-rated readiness.
- Phase 3: follow-up vs no structured follow-up, measuring action completion and user helpfulness.
- Phase 4: Circle mutual insight vs a neutral referral prompt, measuring consented completion and downstream activation.

## Interpretation limits

- Correlated assumptions and real-world feedback loops are simplified.
- The model does not simulate capacity constraints, astrologer availability, fraud, channel cannibalization, or seasonality.
- Organic invitees are treated as additive and do not recursively generate further invite generations.
- Revenue excludes refunds, taxes, astrologer payouts, incentives, acquisition cost, and support cost.
- Percentile ranges express uncertainty encoded by the simulator, not confidence intervals for actual AstroLive impact.
- A favorable scenario cannot justify dark patterns, sensitive inference, or broad sharing.

Judge-facing language should say “the scenario estimates” or “under these editable assumptions,” never “Orbit increased” or “Orbit will deliver.”
