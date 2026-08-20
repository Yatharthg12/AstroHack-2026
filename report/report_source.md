# Page 1 — Cover Page and Team Information

## Cover Page and Team Information

AstroLive Orbit

From one-time consultation to continuous guidance.

AstroHack 2026: Build the Next Universe

Team OrbitWorks | Team leader: Yatharth Garg

Submission report | 20 August 2026

Orbit is a working product proposal that connects a voluntary daily reflection ritual, a user-approved consultation brief, human guidance, follow-up, and a consent-gated mutual referral loop. Prototype inputs are stored in its server-side SQLite database; a free Render deployment is ephemeral. The prototype uses no paid service and never claims to calculate a Kundli or prove astrology. Behaviour models estimate only synthetic product outcomes.

Evidence labels used throughout: OBSERVED means visible on an opened public surface; PUBLISHER CLAIM means first-party marketing or company-reported information; INFERENCE means a product interpretation; SYNTHETIC means generated demonstration data; SIMULATION means an assumption-driven scenario, not measured impact; REPOSITORY-VERIFIED means directly reproduced from this codebase.

<!-- PAGE -->
# Page 2 — Executive Summary and Challenge

## Executive Summary

AstroLive Orbit turns a set of destinations into a continuous, consent-aware guidance loop. Pulse gives users a small daily reason to return. Bridge converts a user-initiated need into an editable brief for a human astrologer. Follow-up carries approved actions into the Journey timeline. Circle creates mutual value only after both people consent. The Growth Cockpit measures this loop without presenting synthetic outputs as company KPIs.

The proposal is differentiated from a generic horoscope, chatbot, astrologer marketplace, recommender, or upsell surface. Its unit of value is a completed guidance loop: a person reflects, chooses whether deeper help is useful, arrives prepared for a human conversation, continues with approved next steps, and may invite someone through a privacy-safe mechanism.

REPOSITORY-VERIFIED: the Flask prototype has server-rendered product and operator routes, server-side SQLite demo state, deterministic reflection templates, secure random referral tokens, seeded simulation, reproducible synthetic analytics, and integrity-checked JSON model artifacts. It requires no external API at runtime.

## Challenge Interpretation and Problem Statement

OBSERVED: the organizer asks teams to address structural virality, habit formation, new revenue, or a differentiated USP, and requires a working public prototype plus an eight-page-or-longer cited report [R1]. Orbit addresses the first, second, and fourth areas as one system.

INFERENCE: AstroLive can be useful at moments of intent, but separate service destinations do not by themselves create continuity. The design question is therefore not “what additional astrology feature can be added?” It is “how can a user move voluntarily from daily value to prepared human guidance, then continue safely and create mutual value for another person?”

The north-star metric is Weekly Guided Users. In this synthetic snapshot it is defined conservatively as users with at least one Pulse check-in in seven days, because the data has no exact seven-day consultation event. Production WGU should also deduplicate consented consultation and follow-up events inside the same weekly window.

<!-- PAGE -->
# Page 3 — Public Experience Teardown

## Evidence-Based Teardown of AstroLive's Public Experience

OBSERVED: AstroLive's opened website exposes Horoscope, Connect, Reports, Book a pooja, Shop, and Blogs, plus astrologer discovery, live sessions, Panchang, Kundli utilities, compatibility tools, and video calls [R2]. This demonstrates breadth; it does not reveal authenticated retention paths or internal information architecture.

OBSERVED: the Google Play listing describes real-time consultations, private audio/video calls and chat, three free calls for new users, and no advance scheduling. At the access date it displayed 500K+ downloads and in-app purchases [R3]. These are point-in-time listing observations, not audited usage or conversion.

OBSERVED: AstroLive's public privacy policy describes collection that may include identity/contact fields, preferences, location, device and usage data, and camera, microphone, or media-library access. It also describes withdrawal, deletion, opt-out, correction, and access routes [R5]. This report does not infer that every optional permission is exercised for every user.

PUBLISHER CLAIM: a repost visible on AstroLive's LinkedIn page attributed paid-user CAC of INR 150–200, earlier LTV of INR 600–800, and later LTV of INR 1,200–1,500 to an LLM-powered upsell engine [R4]. These company-reported, relative-date claims are not used as model targets, simulator defaults, or independently verified economics.

INFERENCE: the public surfaces show many useful destinations but do not evidence a closed, user-visible loop across a daily ritual, consented pre-consultation context, post-consultation continuity, and mutual referral value. “Not observed” is not “does not exist”; no authenticated product audit or reverse engineering was performed.

The opportunity is connective tissue. Pulse should earn return visits with a transparent reflection and harmless micro-action. Bridge should reduce repetitive discovery without exposing unapproved context. Follow-up should preserve user-owned next steps. Circle should make sharing structurally valuable without leaking birth details or concerns. The Cockpit should make each transition inspectable and attach guardrails to growth.

<!-- PAGE -->
# Page 4 — Competitors and Opportunity

## Competitive Landscape and Opportunity Gap

OBSERVED/PUBLISHER CLAIM: AstroTalk's official page describes discovery by expertise, reviews, ratings and language; chat and call; saved consultations; horoscopes; Kundli tools; and commerce. It also publishes first-party claims about astrologer count, languages, availability, and response time [R6]. Its Play listing showed 100M+ downloads and described free first contact, live sessions, instant consultation, and remedies commerce [R7].

OBSERVED/PUBLISHER CLAIM: AstroSage's official page emphasizes Kundli, matching, Panchang, printable reports, nine languages, learning material, consultations, and commerce, while making a first-party download claim [R8]. Its Play listing showed 50M+ downloads and described AI and human astrology experiences, stored horoscopes, and cloud synchronization [R9].

OBSERVED/PUBLISHER CLAIM: Astroyogi's FAQ describes OTP onboarding, wallet recharge, queues, call/chat, consultation categories, and multiple specialities [R10]. Its Play listing showed 10M+ downloads and described Kundli, horoscopes, human and AI consultation, live content, remedies, a family module, and matchmaking [R11].

No competitor count or superlative above is treated as audited. Ratings were intentionally excluded where the verified record varied by locale or render.

INFERENCE: capability breadth, instant access, introductory offers, content, utilities, AI, and commerce are crowded territory. Orbit's opportunity gap is not “more content” or “another AI astrologer.” It is a complete service loop with four defensible seams: transparent daily habit, user-approved preparation for a human, user-owned continuity after that consultation, and dual-consent mutual referral value.

The competitive test is therefore structural. Can the product help before a consultation without manufacturing urgency? Can the astrologer begin with context the user approved? Can follow-up retain utility without forcing a purchase? Can an invite create value for both people without exposing sensitive attributes? Orbit's working prototype makes those seams clickable and measurable.

<!-- PAGE -->
# Page 5 — Users and Product Journey

## Target Users, Jobs-to-be-Done and Current Journey

The primary archetypes are product hypotheses, not interviewed personas. A “ritual builder” wants a brief, low-pressure daily reflection. A “guidance seeker” has a concern and wants to prepare before choosing human help. A “continuity seeker” wants approved actions and context to survive beyond one call. A “trusted pair” wants a shared reflection without disclosing private birth data or concerns. An operator needs to understand where useful guidance starts, stalls, converts, and creates consented acquisition.

Current-journey inference: a user can discover content or utilities, choose a consultation destination, and transact, but the opened public evidence does not reveal a single visible path tying daily use, approved context, consultation, follow-up, and mutual referral together [R2, R3]. This is a design hypothesis to validate, not a statement about internal AstroLive flows.

## AstroLive Orbit Product Solution and Complete User Journey

The working sequence is: landing → minimal onboarding → Pulse → saved check-in → Bridge brief → sample booking → astrologer console → user-approved follow-up → Journey → Circle invite → invitee consent and communication preference → mutual insight → Growth Cockpit.

Onboarding asks only for a display name, birth date, optional time/city, focus, communication preference, save consent, and separate Circle consent. The prototype derives only a deterministic sun sign from date ranges; it does not claim a full chart calculation.

Pulse shows why a deterministic reflection appeared and pairs it with a non-harmful action. Bridge makes topic, context, desired outcome, questions, mode, language, and urgency editable. If selected, the exact reviewed Pulse entries are frozen into that draft; a refresh creates a newly reviewed snapshot. All astrologers, bookings, prices, and confirmations are explicitly samples. Journey records check-ins, actions, and booking-scoped helpfulness and can delete the session-owned server records. Every transition exposes a meaningful empty, validation, success, or error state.

<!-- PAGE -->
# Page 6 — Virality and Habit

## Structural Virality Mechanism

Circle is a product loop, not a social-share button. The inviter grants separate Circle consent. The server creates a cryptographically random token with a seven-day expiry, revoking any older active link for that inviter. The share URL contains only that token—never birth details, focus, private concern, check-in text, or database identity. An invitee can open a safe invitation, consent independently, and choose a non-sensitive conversation preference that is not retained. A fixed communication suggestion unlocks only after both sides consent.

The implementation tracks creation, opening, and consented completion. K-factor is calculated transparently as invites per eligible user multiplied by invite completion rate. SYNTHETIC: across 2,400 fictional snapshots, invites per user are 0.3208, completion per created invite is 0.2987, and K-factor is 0.0958. These values verify the calculation; they are not an AstroLive acquisition benchmark.

The structural value is reciprocity: the invited person receives a standalone consent choice, and both receive the same non-sensitive communication suggestion after consent. Production guardrails should include blocks, abuse review, rate limits shared across workers, expiry, revocation, complaint monitoring, and no recursive incentives that reward pressure.

## Habit and Retention Mechanism

Pulse uses a small daily completion unit: state, concern, reflection, explanation, and one concrete action. A visible streak and seven-day completion state make progress legible. Relevance feedback creates a correction path. The user—not a model—chooses whether to continue to Bridge.

Follow-up closes the loop after a demo consultation with an approved summary, at most three actions, a local check-in date, and helpfulness feedback. Journey lets the user mark an action complete and see check-ins, briefs, bookings, and follow-up in one timeline.

SYNTHETIC: Weekly Guided Users equal 635 of 2,400 snapshots under the exact Pulse-in-seven-days definition; D1/D7/D30 retention labels are 46.21%, 20.13%, and 8.87%. They are generated outcomes for dashboard and pipeline verification, not expected product lift. A real phased experiment must measure absolute retention, opt-out, low-relevance feedback, pressure complaints, and safety flags.

<!-- PAGE -->
# Page 7 — Human Workflow and Architecture

## Consultation and Operational Workflow

Bridge begins only when a user asks for deeper guidance. The brief is structured but editable: topic, context, desired outcome, questions, language/mode, and non-manipulative urgency. Prior Pulse context is included only with specific approval. Suggested speciality is explained as a transparent topic mapping, not a prediction of quality. The user approves before a sample booking is persisted.

The Astrologer Console receives the approved brief, consented context, user goal, and suggested opening questions. It does not expose unapproved check-ins or Circle information. This preserves the role of the human astrologer while reducing repetitive discovery. A production pilot should measure brief edit rate, abandonment, time to meaningful discussion, astrologer-rated readiness, helpfulness, and context-sharing complaints.

## Technical Architecture and Data Flow

REPOSITORY-VERIFIED: one Flask application factory serves Jinja pages and JSON APIs. Domain services validate journey, consultation, referral, growth, and simulation operations. Python sqlite3 stores prototype server state through parameterized queries and idempotent schema initialization. Handcrafted CSS and vanilla JavaScript implement the client. No paid API, external AI model, real payment, or external booking system is required.

The analytics path is deliberately offline: a fixed-seed generator writes a public synthetic CSV; training applies a strict chronological split; validation compares standardized logistic regression with a balanced random forest; selected logistic parameters are exported as JSON with SHA-256; NumPy performs runtime scoring. No pickle or executable model object is loaded.

Failure is explicit. A missing or mismatched artifact returns model_available=false and assigns no automated action. A missing dataset suppresses KPIs. A zero revenue assumption suppresses revenue output. Invalid or expired referral tokens expose no private state. Render's free filesystem is ephemeral; production persistence needs a disk or managed database.

<!-- PAGE -->
# Page 8 — Data and Features

## Dataset Audit and Feature Engineering

No organizer dataset was present when the repository was initialized. The project therefore generates `synthetic_orbit_users.csv`: 2,400 fictional user snapshots, 33 columns, seed 2026, no missing cells, no duplicate rows, and no duplicate user IDs. Snapshot dates span 2026-01-01 to 2026-07-31; fictional signup dates span 2024-08-02 to 2026-06-27.

The data contains no names, phone numbers, emails, birth details, free text, precise locations, real account identifiers, or AstroLive records. The constant provenance field is `synthetic_demo`. Targets are simulated after the snapshot cutoff: 1,038 future 30-day churn positives (43.25%) and 489 future 14-day consultation positives (20.38%).

Fourteen pre-cutoff numeric features cover account age; session recency and 7/30-day frequency; Pulse 7/30-day frequency; weekly active days; average session minutes; content diversity; consultation 90-day frequency and recency; briefs started; referrals created; and prior helpfulness rate. Focus, dates, identifiers, funnel outcomes, retention outcomes, future outcomes, and provenance do not enter training.

Leakage prevention is executable. A named deny-list rejects future targets, future sessions/revenue, historical booking outcome, and D30 retention. Dataset validation checks completeness, finite and non-negative features, binary targets, date order, short/long-window consistency, nested activation and retention, referral completion ≤ opens ≤ creates, active days ≤ weekly sessions, mutually consistent 7/30-day recency windows, and zero windowed activity when 30-day sessions are zero.

The split uses non-overlapping date boundaries: 1,411 training rows through 2026-05-07; 507 validation rows from 2026-05-08 to 2026-06-18; and 482 test rows from 2026-06-19. Scaling is fitted inside the training pipeline. Validation selects model and threshold. Test labels are used once for final metrics and permutation importance.

Limitations are material: one snapshot per fictional person cannot demonstrate causality, network effects, repeated exposure, censoring, drift, long seasonality, or fairness. Generated signal recovery is not external validity.

<!-- PAGE -->
# Page 9 — ML Evaluation

## ML Methodology, Evaluation and Limitations

The two tasks predict product behaviour only: simulated 30-day churn and simulated 14-day consultation. Logistic regression is the interpretable baseline; a 180-tree random forest with depth 8, minimum leaf size 10, and balanced class weights is the nonlinear comparator. Selection maximizes validation PR-AUC, with a declared 0.02 equivalence margin favoring logistic auditability. Logistic wins both tasks under that rule.

REPOSITORY-VERIFIED held-out churn metrics at threshold 0.18 are accuracy 0.4461, precision 0.4242, recall 0.9949, F1 0.5948, ROC-AUC 0.6939, PR-AUC 0.6077, and Brier 0.2130. The confusion matrix is TN 19, FP 266, FN 1, TP 196. The threshold weights a missed at-risk user three times a passive false-positive card.

Held-out intent metrics at threshold 0.27 are accuracy 0.7220, precision 0.3056, recall 0.3587, F1 0.3300, ROC-AUC 0.7196, PR-AUC 0.3459, and Brier 0.1437. The confusion matrix is TN 315, FP 75, FN 59, TP 33. Its false-negative cost is 2.5 times a passive false-positive Bridge prompt. These cost ratios are product assumptions, not measured harm.

Permutation importance on test PR-AUC identifies churn recency (0.16158 mean decrease) as the dominant synthetic signal; prior consultation (0.01493), consultation recency (0.00723), content diversity (0.00584), and weekly activity (0.00580) are much smaller. Intent's leading synthetic signals are consultation recency (0.02525), content diversity (0.01141), 7-day sessions (0.00918), Pulse check-ins (0.00339), and briefs started (0.00329). Association is not causation.

No subgroup fairness claim is possible because protected and demographic attributes do not exist. Production use requires governed consented outcomes, calibration, subgroup error review, drift monitoring, intervention evaluation, override, and an audit trail. Prohibited uses include pricing, eligibility, astrologer ranking, vulnerability targeting, high-stakes advice, fate claims, or automatic contact.

<!-- PAGE -->
# Page 10 — Simulation, Metrics, and Economics

## Experiment Simulator and Impact Scenarios

SIMULATION: the seeded Monte Carlo tool runs 10,000 trials around editable assumptions. Defaults are 10,000 eligible users, 22% Pulse adoption, 24% baseline retention, 10% relative retention uplift, 8% share rate, 1.4 invites per sharer, 18% invite conversion, 5.5% baseline consultation conversion, 7.2% scenario conversion, 8% repeat uplift, and zero revenue. None is an AstroLive baseline.

At seed 2026, incremental retained users have p05 -50, median 53, expected 53.42, and p95 155. Incremental consultations have p05 32.13, median 231.84, expected 232.50, and p95 434.14. Incremental organic users have p05 28.35, median 43.44, expected 44.28, and p95 63.27. These ranges reflect encoded assumption uncertainty, not confidence intervals for actual business impact. Consultation conversion has the largest local absolute sensitivity correlation, 0.677.

## Success Metrics, North-Star Metric and Guardrails

Weekly Guided Users currently counts unique synthetic users with a meaningful Pulse in seven days; production should extend it to deduplicated consultation and follow-up events. Supporting measures are activation, D1/D7/D30 and cohort retention, Pulse completion and relevance, brief-to-booking conversion, repeat consultation, Circle creation/open/completion, K-factor, action completion, and helpfulness. Guardrails are deletion success, opt-out, unwanted context sharing, invitation complaints, pressure reports, safety flags, latency, and astrologer capacity.

## Revenue Opportunities and Unit-Economic Logic

Orbit may support consultation conversion, repeat consultation through useful continuity, and organic acquisition through Circle. That is a mechanism hypothesis, not a forecast. Revenue is omitted from the default simulation because the repository has no defensible transaction input. The company-reported CAC/LTV figures are contextual only [R4]. A real model must deduct refunds, astrologer payouts, incentives, taxes, support, fraud, and incremental delivery cost, and report contribution margin with confidence intervals.

<!-- PAGE -->
# Page 11 — Delivery, Scale, Privacy, and Trust

## Feasibility, Scalability and Staged Rollout

The prototype is feasible as a single Python service: Flask/Jinja, vanilla JavaScript, handcrafted CSS, sqlite3, pandas, NumPy, scikit-learn, and compact JSON artifacts. Local setup needs no credential. Gunicorn, Docker, Render configuration, a health endpoint, and an ephemeral-storage warning are included.

Stage 1 is an instrumentation and consent pilot with synthetic scoring disabled. Stage 2 tests Pulse eligibility with an A/A check and then randomized rollout. Stage 3 tests Bridge with a small astrologer cohort and explicit context approval. Stage 4 tests follow-up timing. Stage 5 tests Circle mutual value with invitation-spillover controls. Only governed evidence should update simulator assumptions or train production models.

Scaling requires replacing SQLite with managed Postgres, process-local rate limits with a shared store, and ad hoc schema initialization with migrations. Add queues, observability, backups, capacity controls, audit logs, deletion SLAs, model registry, drift monitoring, and staged rollback. The closed-loop services remain separable even if deployed as one service during validation.

## Privacy, Trust, Consent, Safety and Responsible Astrology

Orbit minimizes data and separates consent. Saving the demo journey and Circle sharing are independent. Exact reviewed check-ins enter a frozen brief only with approval. Referral URLs contain random tokens only. Mutual insight requires consent on both sides. Reset deletes the session-owned demo user's dependent server records and experiment runs. The public synthetic CSV excludes personal and birth information.

Guidance is reflective and non-fatalistic. Templates do not give medical, legal, investment, safety, or guaranteed-outcome instructions. The prototype calculates only deterministic sun sign ranges, never a Kundli or planetary position. ML predicts product behaviour, not emotion, destiny, compatibility, or astrological validity, and it never replaces a human astrologer.

Public privacy evidence makes consent quality particularly important: AstroLive's policy describes potentially broad identity, preference, location, device, usage, and media-permission categories plus user-rights routes [R5]; the Play listing's developer-provided data-safety panel also makes collection and sharing statements [R3]. Orbit's design does not claim to audit or replace those production controls.

Residual risks include engagement proxies encoding access differences, invitation abuse, social pressure, context misunderstanding, astrologer capacity, and simplistic in-memory rate limiting. Guardrails must be tested with real users before launch.

<!-- PAGE -->
# Page 12 — Prototype, Conclusion, References, and Disclosure

## Prototype Screenshots and Demonstration Instructions

The image below is admitted only from a successful `browser_smoke_results.json` manifest. The verified run completed the full journey at desktop and an exact 360px emulated viewport, used an independent invitee browser, exercised JSON/CSV/PNG downloads, checked overflow, keyboard focus and reduced motion, and reported no browser-console errors. Thirteen curated captures are retained in `docs/screenshots/`.

Three-minute path: landing (0:00); onboard with separate save/Circle consent (0:20); complete Pulse and inspect “why shown” (0:40); create, review and approve Bridge (1:00); sample booking and consent-filtered console (1:20); follow-up (1:40); independent Circle invitee consent and mutual suggestion (1:55); Journey (2:25); Growth and seeded scenario (2:40); evidence limits (2:55).

## Conclusion

Orbit's differentiation is the loop, not another isolated feature: daily value → voluntary readiness → prepared human consultation → approved continuity → dual-consent mutual value → measurable learning. The repository proves prototype feasibility and analytical discipline. It does not prove demand, lift, fairness, unit economics, or production readiness. Those are the next experiments.

## References

[R1] Unstop, “AstroHack 2026: Build the Next Universe,” AMP and canonical challenge pages, accessed 2026-08-20. https://unstop.com/competitions/astrohack-2026-build-the-next-universe-astrolive-1719172

[R2] AstroLive, public home page, accessed 2026-08-20. https://astrolive.app/

[R3] Google Play, “AstroLive - Talk to Astrologer,” updated 2026-08-10, accessed 2026-08-20. https://play.google.com/store/apps/details?id=app.astrolive

[R4] AstroLive LinkedIn company page and visible repost, accessed 2026-08-20. https://www.linkedin.com/company/astroliveapp

[R5] AstroLive Privacy Policy, accessed 2026-08-20. https://astrolive.app/privacy-policy

[R6] AstroTalk, “Chat with Astrologer Online | First Chat Free,” accessed 2026-08-20. https://astrotalk.com/chat-with-astrologer

[R7] Google Play, “Astrotalk - Talk to Astrologer,” accessed 2026-08-20. https://play.google.com/store/apps/details?id=com.astrotalk

[R8] AstroSage, “AstroSage Kundli,” accessed 2026-08-20. https://www.astrosage.com/mobileapps/astrosage-kundli-best-astrology-app-by-astrosage.asp

[R9] Google Play, “AstroSage Kundli: AI Astrology,” accessed 2026-08-20. https://play.google.com/store/apps/details?id=com.ojassoft.astrosage

[R10] Astroyogi, “Frequently Asked Questions,” accessed 2026-08-20. https://www.astroyogi.com/faqs

[R11] Google Play, “Astroyogi - Astrology & Kundli,” accessed 2026-08-20. https://play.google.com/store/apps/details?hl=en-US&id=com.netway.phone.advice

## AI Tools Disclosure

OpenAI ChatGPT supported ideation, research synthesis and prompt preparation. OpenAI Codex supported implementation, testing, debugging, documentation and report production. AI output was not accepted as evidence by default. Validation included opened public sources, deterministic data/model/simulator pipelines, automated tests, compilation, HTTP and browser journeys, PDF extraction/rendering checks, and manual inspection of every rendered page. AI assistance is disclosed rather than concealed.
