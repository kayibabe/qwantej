# Qwantej — Accumulator Intelligence Framework

**Version 2.0** — Continuously Calibrated, Value-Driven and Risk-Controlled
Football Accumulator Engine.

*Intelligence Beyond Numbers.*

> **Framework status:** Engineering-governed conceptual specification, prepared
> from the existing Qwantej framework and the supplied development/architecture
> recommendations. Dated 6 September 2026.

> **Provenance:** This file is the in-repo canonical copy of
> `Qwantej_Accumulator_Intelligence_Framework_v2.0.docx`, converted to Markdown
> so that it is diffable, reviewable and readable by both coding agents. The
> `.docx` remains the human-authored source; regenerate this file rather than
> editing it by hand if the source document changes.

# Document Control and Version 2.0 Change Summary

| Item | Version 2.0 position |
| --- | --- |
| Purpose | Convert Qwantej from a daily accumulator generator into an auditable probabilistic decision and learning system. |
| Primary objective | Seek and validate positive long-run expected value; never assume or guarantee it. |
| Authoritative probability | Calibrated probability, then uncertainty-adjusted conservative probability for betting decisions. |
| Core engineering principle | Every live prediction is immutable, timestamped, reproducible and linked to its exact data/model/calibration versions. |
| Accumulator products | Core 3.00–5.00; Growth 5.00–10.00; Alpha 10.00–20.00 operating band. No ticket is mandatory. |
| Development baseline | VS Code + GitHub + Claude Code + OpenAI Codex; Python/FastAPI; PostgreSQL; Docker; Fly.io; CI/CD. |
| Critical new controls | Point-in-time backtesting, data leakage prevention, Bayesian shrinkage, dependence/covariance controls, explicit Value Gate, model registry and champion–challenger promotion. |

> Version 2.0 keeps the original framework’s philosophy but hardens it into a system that can be coded, tested, audited, and challenged. It is not a promise of profit; it is a disciplined mechanism for discovering whether a repeatable edge exists.

# Contents

| Section | Coverage |
| --- | --- |
| Part I | Purpose, Constitution and Operating Philosophy |
| Part II | System and Development Architecture |
| Part III | Data Intelligence and Point-in-Time Institutional Memory |
| Part IV | Prediction, Ensemble and Calibration Engine |
| Part V | Bookmaker Intelligence, Value and Execution |
| Part VI | Selection Qualification and Reliability Learning |
| Part VII | Accumulator Optimisation and Dependence Control |
| Part VIII | Bankroll, Risk and Drawdown Control |
| Part IX | Settlement, Performance, Learning and Model Governance |
| Part X | Daily Processing Workflow and Product Experience |
| Part XI | Implementation Roadmap and Coding Specification |
| Appendices | Initial thresholds, data schema, governance rules and formulas |

# PART I — PURPOSE, CONSTITUTION AND OPERATING PHILOSOPHY

## 1. Qwantej’s identity
Qwantej is not a football tips generator. It is a continuously calibrated probabilistic decision system whose job is to estimate football-market probabilities, determine whether the available price offers sufficient value after uncertainty and market friction, construct risk-controlled accumulator portfolios only from qualified selections, and learn from every settled decision.

> Qwantej should prefer NO BET over a fabricated bet. The rejection engine is as important as the prediction engine.

## 2. Refined core objective
Build a continuously calibrated accumulator engine that estimates probabilities which can outperform appropriately de-vigged market probabilities by enough to create positive expected value after accounting for model uncertainty, dependence, price movement, execution constraints and bankroll risk; while continuously learning the leagues, markets, conditions and timing windows where Qwantej has demonstrable predictive advantage.
No component of this objective should be interpreted as a guarantee of positive long-term expected value. Qwantej must continually test whether the edge exists, how stable it is, and when it has disappeared.

## 3. The Qwantej System Constitution
Probability before tips: every selection must originate from an explicit probability estimate, not an unsupported categorical prediction.
Calibration before confidence: model probability must be calibrated and uncertainty-adjusted before it can drive a bet.
Price before selection: a strong football prediction is not automatically a good wager; price determines value.
Point-in-time integrity: no prediction or backtest may use information that was unavailable at its decision timestamp.
Immutable decision record: a published prediction must remain reproducible even after models, features or calibrators change.
No forced tickets: Core, Growth or Alpha may return NO QUALIFIED ACCA.
No quality dilution: higher accumulator odds must primarily come from additional qualified legs, not weaker legs.
No Martingale or loss chasing: risk controls may reduce exposure after losses but never escalate stakes to recover them.
Challenge the model: extreme model-versus-market disagreements trigger scrutiny, not blind confidence.
Model changes require evidence: retraining may be frequent, but live model promotion requires controlled validation.
Auditability: every price, data snapshot, feature set, probability, selection decision, ticket and settlement must be traceable.
Capital preservation: maximising risk-adjusted long-run growth takes precedence over maximising daily ticket count or displayed odds.

## 4. Closed decision and learning loop
Football data
↓  Fixture intelligence
↓  Feature generation
↓  Probability models
↓  Ensemble
↓  Calibration
↓  Market fair-price estimation
↓  Value Gate
↓  Selection qualification
↓  Accumulator optimisation
↓  Risk control
↓  Publication/lock
↓  Settlement
↓  Performance measurement
↓  Learning/recalibration
↓  Back into models and reliability scores

> Predict → Price → Calibrate → Filter → Combine → Risk-Control → Lock → Settle → Measure → Learn.

# PART II — SYSTEM AND DEVELOPMENT ARCHITECTURE

## 5. Recommended engineering environment
Qwantej should be built using agentic software engineering rather than relying on a browser-only vibe-coding environment as the authoritative codebase. Rapid UI prototyping tools may be used for experiments, but the modelling, calibration, backtesting, risk and audit layers should remain in a version-controlled engineering environment.

| Component | Recommended baseline | Role |
| --- | --- | --- |
| Core IDE | VS Code | Primary workspace and repository context |
| Primary coding agent | Claude Code | Architecture, large implementations and refactors |
| Independent reviewer | OpenAI Codex | Quant/code review, testing, adversarial validation and alternate implementations |
| Source control | GitHub | Single source of truth, branches, pull requests and audit trail |
| Backend | Python + FastAPI | Prediction, calibration, value, risk and accumulator APIs |
| Database | PostgreSQL | Institutional memory and point-in-time historical record |
| Cache / queue | Redis | Caching, locks, jobs and transient state |
| Frontend | Next.js / React | Dashboard and product experience |
| Statistics / ML | NumPy, pandas, SciPy, statsmodels, scikit-learn; PyMC where justified | Statistical and machine-learning layer |
| Experiment tracking | MLflow or equivalent | Model registry, runs, metrics, artefacts and promotion evidence |
| Job orchestration | Prefect initially | Ingestion, scoring, settlement, monitoring and recalibration jobs |
| Containers | Docker | Reproducible runtime environments |
| Deployment | Fly.io initially | API, workers, scheduler and web services |
| CI/CD | GitHub Actions | Tests, quality gates and deployment automation |

## 6. Dual-agent engineering model
Claude Code and Codex should not merely duplicate each other. They should be assigned deliberately different responsibilities over the same repository.

| Agent role | Primary duties | Required behaviour |
| --- | --- | --- |
| Principal Software Engineer — Claude Code | Architecture, schemas, ingestion, services, optimiser, UI integration, refactors | Implement against approved specifications; maintain tests; document architectural decisions. |
| Quantitative Engineering Reviewer — Codex | Probability logic, vig removal, EV, leakage, dependence, numerical stability, tests, race conditions | Review findings first; challenge assumptions; propose tests and only then implement approved fixes. |
| Human governance | Product objectives, risk policy, threshold approval, model promotion decisions | Approve material changes and resolve disagreements between agents. |

## 7. Repository constitution

| Path | Purpose |
| --- | --- |
| /docs/QWANTEJ_FRAMEWORK.md | Canonical functional and quantitative framework |
| /docs/ARCHITECTURE.md | Services, components, dependencies and diagrams |
| /docs/MODEL_GOVERNANCE.md | Model registry, versioning, validation and promotion |
| /docs/DATA_DICTIONARY.md | Canonical entities, fields, units, timestamps and provider mappings |
| /docs/ACCUMULATOR_POLICY.md | Ticket bands, constraints, dependence and rejection rules |
| /docs/RISK_POLICY.md | Bankroll, Kelly, exposure and drawdown controls |
| /docs/BACKTEST_POLICY.md | Point-in-time evaluation and leakage prevention |
| /CLAUDE.md | Permanent implementation guidance for Claude Code |
| /AGENTS.md | Shared agent roles, test expectations and review protocol |
| /README.md | Developer onboarding, local run and deployment guide |

main — production-ready code only.
develop — integration branch when used.
feature/* — application features.
model/* — model changes isolated from unrelated application work.
experiment/* — non-production research and challenger experiments.

## 8. Logical engine architecture

| # | Engine | Primary purpose |
| --- | --- | --- |
| 1 | Fixture & Data Intelligence | Gather, normalise, validate and score data quality. |
| 2 | Feature Engineering | Produce point-in-time model features with versioned transformations. |
| 3 | Prediction Engine | Generate market probabilities from statistical and ML models. |
| 4 | Ensemble & Calibration Engine | Combine models, calibrate probabilities and quantify uncertainty. |
| 5 | Bookmaker & Market Intelligence | De-vig prices, build consensus fair probabilities and track line movement. |
| 6 | Value Detection Engine | Compute probability edge, EV and pass candidates through the Value Gate. |
| 7 | Selection Qualification Engine | Compute QSS and enforce data, stability, calibration and quality rules. |
| 8 | League & Market Reliability Engine | Learn where Qwantej is reliable using Bayesian shrinkage and recency. |
| 9 | Accumulator Optimiser | Construct Core, Growth and Alpha portfolios under dependence constraints. |
| 10 | Risk & Bankroll Engine | Stake sizing, exposure caps, drawdown states and circuit breakers. |
| 11 | Settlement & Performance Engine | Settle results; calculate P/L, ROI, CLV, calibration and risk metrics. |
| 12 | Continuous Learning & Model Governance | Drift detection, retraining, challenger evaluation and controlled promotion. |

> Surrounding all twelve engines: QWANTEJ GOVERNANCE & AUDIT LAYER — every material decision must be reproducible and attributable to exact data, code, model, calibration and price versions.

# PART III — DATA INTELLIGENCE AND POINT-IN-TIME INSTITUTIONAL MEMORY

## 9. Fixture and Data Intelligence
Before Qwantej predicts a fixture, it must decide whether it has enough trustworthy and temporally valid information to support a prediction. Data availability is itself a model input and a filtering mechanism.

| Data family | Examples | Initial priority |
| --- | --- | --- |
| Results | Goals scored/conceded; scorelines; venue | High |
| Expected goals | xGF, xGA, xG chain or provider-equivalent where available | High |
| Form | Last 5/10/20 with strength and recency adjustment | High |
| Home/Away | Venue-specific attack/defence splits | High |
| Shots | Shots, shots on target, shot quality where available | Medium |
| Strength | Elo/team ratings, opponent-adjusted performance | High |
| Squad availability | Injuries, suspensions, expected/confirmed line-up | Medium → High as source quality improves |
| Schedule | Rest days, congestion, travel, competition priority | Medium |
| Market prices | Opening/current/closing odds across bookmakers | High |
| Environment | Weather and pitch context where demonstrably useful | Later / conditional |

## 10. Data Quality Score (DQS)
DQS remains a 0–100 measure but Version 2.0 formalises it as a composite of completeness, freshness, provider reliability, sample sufficiency, entity-match confidence and timestamp validity. DQS is not a model probability.

| DQS | Interpretation | Default action |
| --- | --- | --- |
| 90–100 | Excellent | Eligible for all products subject to other gates |
| 80–89 | Strong | Eligible |
| 70–79 | Acceptable | Eligible only if model/reliability/EV evidence is strong |
| 60–69 | Weak | Normally reject; research only |
| <60 | Reject | Do not generate live betting candidates |

## 11. Canonical data contracts
Qwantej should never let provider-specific identifiers leak throughout the modelling code. Every provider fixture/team/competition/market should be mapped into canonical internal entities with explicit confidence and provenance.
Canonical fixture_id, team_id, competition_id and season_id.
Provider mapping tables with source identifiers and mapping confidence.
Timestamps stored in UTC; display converted to user timezone only at presentation.
Odds quote must carry bookmaker, market, selection, decimal odds, captured_at and source.
Feature values must carry feature_version and as_of_timestamp.
Missing data must be explicit; never silently impute without recording the imputation policy.
Duplicate and conflicting fixtures require reconciliation rules and an audit event.

## 12. PostgreSQL as Qwantej institutional memory
The historical decision record is a central intellectual asset. Every live prediction and accumulator must be archived in sufficient detail to reproduce what Qwantej knew, what it believed, what price it saw, why it acted, and what happened afterward.

| Core table | Minimum responsibility |
| --- | --- |
| fixtures | Canonical fixture identity, competition, teams, kickoff, status |
| providers / source_mappings | Provider metadata and canonical mappings |
| odds_quotes | Every timestamped bookmaker quote used or observed |
| stats_snapshots | Point-in-time team/fixture statistics |
| feature_snapshots | Versioned model-ready features and as-of timestamp |
| model_registry | Model family/version, training window, code/artefact hashes, status |
| model_runs | Execution metadata, data snapshot, parameters, outputs |
| predictions | Raw/ensemble/calibrated/conservative probabilities by market/selection |
| calibration_models | Calibrator version, segment, training sample and diagnostics |
| reliability_snapshots | LRS/MRS and posterior uncertainty at a point in time |
| selection_candidates | QSS, value gate result and rejection/pass reasons |
| accumulators / accumulator_legs | Ticket product, odds, probability, EV, legs and optimiser version |
| settlements | Outcomes, P/L, voids and settlement timestamps |
| bankroll_ledger | Deposits, withdrawals, stakes, returns and bankroll state |
| experiments | Backtests, challenger runs and evaluation metrics |
| audit_events | Material system and human actions |

## 13. Point-in-time integrity and immutable predictions

> A prediction made at 18:00 on 6 September must remain exactly the prediction made at 18:00 on 6 September, even if the model changes later.

Every prediction stores prediction_timestamp and decision_as_of timestamp.
Only data with source timestamps less than or equal to the decision timestamp may enter its features.
Closing odds may be stored later for CLV evaluation, but must never leak into an earlier prediction feature set.
Historical corrections should create a new data revision; they must not silently rewrite the decision-time snapshot used by a published prediction.
Every prediction links to model_version, feature_version, calibration_version, reliability_snapshot and optimiser/risk-policy version.
For high-integrity reproduction, store input snapshot identifiers/hashes and code commit SHA where practical.

# PART IV — PREDICTION, ENSEMBLE AND CALIBRATION ENGINE

## 14. Modelling philosophy
Qwantej should predict probability distributions and market probabilities rather than tips. It should use multiple complementary models and should not assume that one universal model is optimal for every football market.

| Model family | Primary use | Governance note |
| --- | --- | --- |
| Poisson | Baseline goal distributions | Transparent anchor and diagnostic benchmark |
| Dixon–Coles | Low-score correction for football scorelines | Useful for 0–0, 1–0, 0–1, 1–1 dependence adjustment |
| Bivariate Poisson | Correlated home/away goal counts using a shared intensity component | Treat separately from Dixon–Coles; validate whether correlation materially improves out-of-sample performance |
| Negative Binomial | Over-dispersed scoring | Use where variance materially exceeds Poisson assumptions |
| ZINB | Excess zeros plus over-dispersion | Use only where diagnostics justify it |
| Elo / team strength | Relative team quality and result probabilities | Time-varying, competition-aware ratings |
| Bayesian models | Uncertainty and partial pooling | Especially valuable for sparse leagues/teams and hierarchical effects |
| xG-based models | Underlying chance quality rather than result-only form | Provider-specific measurement differences must be tracked |
| Market model | Bookmaker consensus as information signal and benchmark | Never treat raw implied probability as fair probability without vig handling |
| ML challengers | Gradient boosting/logistic/random forest and later alternatives | Supplement the statistical core only after leakage-safe validation |

## 15. Technical clarification: scoreline dependence
The supplied enhancement correctly identifies the need to move beyond naive independent home/away goal assumptions. Version 2.0 implements this as a modelling requirement but distinguishes two mechanisms: bivariate Poisson dependence through a shared goal-intensity component, and Dixon–Coles low-score correction through its own adjustment parameter. They should be tested as separate model candidates rather than conflated into one formula.
Produce a complete scoreline probability matrix up to a configurable truncation (for example 0–10 goals with tail handling).
Validate that probabilities sum to approximately 1 after tail treatment.
Derive 1X2, double chance, totals, BTTS and team-goal markets from the same internally coherent scoreline distribution when that model is used.
Run numerical sanity tests against known symmetric and low-scoring cases.
Keep a simple independent-Poisson benchmark so additional complexity must prove incremental value.

## 16. Market-specific modelling stacks

| Market family | Candidate stack | Key diagnostics |
| --- | --- | --- |
| Over 1.5 / Over 2.5 | Goal-distribution + xG + attack/defence strength | Calibration by probability band; scoring regime drift |
| Under 2.5 / Under 3.5 | Poisson/NB/ZINB/Dixon–Coles ensemble | Tail calibration; zero/low-score behaviour |
| 1X / X2 / 1X2 | Elo + result model + home advantage + market signal | Draw calibration; league home-advantage drift |
| BTTS | Team scoring probability + defence + xG + dependence model | Joint scoring calibration |
| Team over 0.5 / 1.5 | Team-specific scoring distribution | Attack/defence interaction; line-up sensitivity |
| Halves / cards / corners | Separate future models | Do not infer from full-match goal model without validation |

## 17. Ensemble design
The ensemble should store each component probability, the weighting method, the ensemble output and the disagreement among models. Fixed weights are acceptable for the baseline; learned weights must be trained only on past data and validated out of sample.
Model disagreement is a risk signal, not merely an averaging problem.
If one model produces a materially extreme probability, retain the reason and diagnostic rather than hiding it inside the average.
Ensemble weights may differ by market, league class and data-quality regime once sample sizes support segmentation.
A market-derived probability may be used as a feature or blend component only under a governance policy that prevents the model from simply reproducing the bookmaker.

## 18. Probability calibration
Calibration is a first-class engine. If Qwantej labels many events as 80%, roughly 80% should occur over an appropriate sample. Accuracy alone is insufficient.

| Metric | Purpose |
| --- | --- |
| Brier Score | Quadratic probability error and calibration/discrimination quality |
| Log Loss | Penalises confident wrong probabilities strongly |
| Expected Calibration Error / calibration error | Observed-versus-predicted deviation across bins |
| Calibration intercept / slope | Detect systematic bias and over/under-confidence |
| Reliability curve | Visual probability calibration |
| Brier Skill Score | Compare Qwantej to a market or baseline reference |

Calibration should eventually be segmented by market, league or league cluster, odds/probability band, home/away context, season regime and model family—but only when sample size permits. Sparse segments must fall back toward broader calibrators rather than fit unstable local curves.

## 19. Raw, calibrated and conservative probability

| Probability layer | Definition | Use |
| --- | --- | --- |
| P_raw | Direct model/ensemble probability | Diagnostics and research |
| P_cal | Probability after calibration | Primary probabilistic belief |
| P_cons | Conservative probability after uncertainty haircut | Live value, accumulator and risk decisions |

A practical baseline is to derive P_cons from a lower credible/confidence bound or from an uncertainty haircut that increases when model disagreement, data weakness, calibration uncertainty or distribution shift rises. The haircut methodology must itself be versioned and backtested.

# PART V — BOOKMAKER INTELLIGENCE, VALUE AND EXECUTION

## 20. Bookmaker market intelligence
Qwantej moves from football prediction into betting intelligence only after comparing its calibrated belief with the available market price. Raw implied probabilities include margin and should not be treated as fair probabilities.
Capture opening, current and closing odds where available.
Convert decimal odds to raw implied probability: p_raw_market = 1 / odds.
Remove bookmaker margin using a documented de-vig method appropriate to the market.
Build consensus fair probability from multiple bookmakers when possible.
Store best available executable odds separately from market-consensus probability.
Track quote age and reject stale prices beyond product-specific limits.
Record line movement and later compute Closing Line Value (CLV).

## 21. Qwantej Edge and Expected Value
Define probability edge in percentage points as: Edge = P_cons − P_market_fair. For decimal odds, selection EV = (P_cons × Odds_exec) − 1. Both values must be stored; neither should be considered valid if the market price is stale or the probability is uncalibrated.

> Large theoretical EV is a diagnostic event. It may indicate genuine value, bad data, market mismatch, a mapping error or model misspecification. Extreme edges require additional scrutiny.

## 22. The explicit Qwantej Value Gate

| Gate | Pass requirement |
| --- | --- |
| Calibration gate | Approved calibrator exists or approved broader fallback is used |
| Uncertainty gate | Conservative probability remains above minimum after haircut |
| Market gate | Valid, sufficiently fresh executable odds and de-vigged market benchmark exist |
| Edge gate | Minimum probability edge satisfied |
| EV gate | Conservative EV positive and above the configured minimum |
| Data gate | DQS above required threshold |
| Reliability gate | League/market posterior reliability above threshold or explicit research exception |
| Stability gate | Probability not excessively sensitive to recent data/model updates |
| Anomaly gate | No unresolved extreme disagreement, mapping or price anomaly |
| Risk gate | Selection compatible with current operating state and portfolio constraints |

Every failed gate should record a machine-readable reason code. This creates a powerful “Why selected / Why rejected” capability and prevents hidden discretionary overrides.

## 23. Price execution and ticket invalidation
The ticket stores target/observed odds and lock time.
If one leg’s odds move materially before lock, the optimiser must re-evaluate ticket EV and constraints.
A ticket may transition Draft → Qualified → Published → Odds Changed → Requalified/Withdrawn → Locked → Live → Settled.
If the executable price falls below minimum value, the leg is removed or the ticket is withdrawn; the UI must not preserve a stale “value” label.
Execution slippage assumptions should be included in backtests if actual taken prices differ systematically from observed screen prices.

# PART VI — SELECTION QUALIFICATION AND RELIABILITY LEARNING

## 24. Qwantej Selection Score (QSS)
QSS remains a 0–100 composite quality score. It is not probability. Version 2.0 retains a transparent initial weighting scheme but treats it as a policy to be learned and validated rather than a permanent truth.

| Component | Initial research weight |
| --- | --- |
| Calibrated / conservative probability quality | 25% |
| Model consensus and stability | 15% |
| Expected value / probability edge | 15% |
| Data Quality Score | 10% |
| League reliability | 10% |
| Market reliability | 10% |
| Probability stability | 5% |
| Odds / execution stability | 5% |
| Historical calibration quality | 5% |

| QSS | Grade | Meaning |
| --- | --- | --- |
| 92–100 | A+ Elite | Exceptional overall candidate quality |
| 87–91 | A+ | Very strong |
| 82–86 | A | Strong |
| 77–81 | B+ | Borderline for live accumulator use |
| 72–76 | B | Research / watchlist |
| <72 | Reject | Not accumulator eligible |

## 25. League Reliability Score (LRS) and Market Reliability Score (MRS)
Reliability must reflect more than hit rate. It should incorporate calibration, ROI/yield, CLV, variance, drawdown, recency, sample size and model stability. Version 2.0 makes Bayesian shrinkage mandatory for sparse segments.

## 26. Small-sample Bayesian shrinkage
A league-market segment with 6 wins in 7 selections must not be treated as an 86% reliable segment. Its performance should be pulled toward a broader prior until evidence accumulates.
A transparent initial shrinkage mechanism can use an effective sample weight: w = n_eff / (n_eff + k), with k initially set around 100 and tuned by backtesting. A segment estimate then becomes Posterior = w × SegmentEstimate + (1 − w) × GlobalOrParentEstimate. Recency weighting should determine n_eff so old evidence gradually loses influence.
Use hierarchical parents: league-market → league or market family → competition class → global baseline.
Use posterior uncertainty, not just posterior mean, in qualification decisions.
Do not treat N ≥ 100 as a magical point where shrinkage stops; instead allow weight to rise gradually and validate the strength parameter k.
Reliability status should move dynamically among Qualified, Watch, Restricted and Blacklisted.
Promotion or recovery from blacklist requires evidence, not elapsed time alone.

## 27. Qwantej League–Market Intelligence Matrix
The platform should continuously maintain a league × market matrix summarising posterior reliability grades, sample size, uncertainty, calibration, ROI, CLV and current status. The matrix is an internal decision asset and should directly influence candidate generation and model segmentation.

| Example league | O1.5 | O2.5 | U3.5 | 1X | X2 | BTTS |
| --- | --- | --- | --- | --- | --- | --- |
| EPL | A+ | A | A+ | A | A | B+ |
| Bundesliga | A+ | A+ | B+ | A | A | A |
| Serie A | A | B+ | A+ | A | A | B |
| Ligue 1 | A | A | A | A | B+ | B+ |

The table above remains illustrative. Live grades must come from the settlement and reliability engines, not from hard-coded assumptions.

# PART VII — ACCUMULATOR OPTIMISATION AND DEPENDENCE CONTROL

## 28. Candidate funnel
The optimiser must receive only selections that have already passed the relevant gates. A large daily fixture universe should narrow progressively through data, model, value, calibration and reliability filters before optimisation begins.
All markets analysed
↓
Statistically valid markets
↓
DQS pass
↓
Calibrated and uncertainty-adjusted
↓
Positive conservative value
↓
Reliability pass
↓
QSS pass
↓
Dependence-compatible candidate pool
↓
Optimised ticket or NO QUALIFIED ACCA

## 29. Product structure — Core, Growth and Alpha

| Product | Combined odds | Typical legs | Purpose | Default quality stance |
| --- | --- | --- | --- | --- |
| CORE | 3.00–5.00 | 3–4 | Flagship; highest-quality daily accumulator | Highest QSS/reliability and lower volatility |
| GROWTH | >5.00–10.00 | 4–6 | Balanced risk/reward | Strong screening; broader pool without quality dilution |
| ALPHA | >10.00–20.00 operating band | 5–7 | Higher-variance opportunity built from qualified legs | Higher odds mainly through more good legs, not weak markets |

The interface may display “10.0+” for Alpha, but the initial internal operating band should be capped around 20.00. Any 20+ entertainment product should be separated as a Jackpot/experimental product and excluded from the core investment-performance KPIs.

## 30. Core accumulator constraints
Maximum one selection from any fixture in a standard accumulator.
Never add a leg solely to reach a target price.
Never reduce QSS, DQS, EV or reliability thresholds because the daily ticket is otherwise unavailable.
No blacklisted league-market segment.
Maximum legs by product unless a backtested policy revision approves otherwise.
No more than two legs from one league in the initial policy, subject to validation.
No more than three legs from the same market family in the initial policy, subject to validation.
Enforce price freshness at lock time.
Each ticket must remain positive under its conservative probability estimate and stress haircut.
NO QUALIFIED ACCA is an expected operational result, not a failure.

## 31. The fallacy of simple accumulator independence
The original product-level probability P_ticket = ΠP_i is acceptable only as an independence baseline. One-selection-per-match removes direct same-fixture dependence but does not eliminate systemic dependence across matches. League style, weather systems, schedule effects, provider/model errors and common market factors can create shared risk.

## 32. Dependence and covariance control
Version 2.0 therefore separates two questions: (1) how to estimate joint outcome probability, and (2) how to prevent concentration even when joint probability is difficult to estimate robustly.

| Stage | Method | Use |
| --- | --- | --- |
| Baseline | Independent product of conservative leg probabilities | Transparent benchmark only |
| Immediate production control | Concentration constraints + dependence penalty matrix | Block or penalise same league/market/time/weather clusters |
| Empirical upgrade | Residual outcome correlation / covariance matrix by market and competition group | Quantify shared forecast error after conditioning on predicted probabilities |
| Advanced research | Scenario simulation / copula or hierarchical latent-factor model | Estimate portfolio/ticket joint risk when sample size supports it |

Until empirical covariance is stable, Qwantej should not invent precise correlation coefficients. It should use conservative proxy penalties and hard diversification limits, then replace them with learned dependence estimates as the historical archive grows.

## 33. Optimiser objective
The optimiser should not maximise combined odds. Its conceptual objective is to maximise risk-adjusted expected growth subject to product odds, quality, value, diversification, dependence, execution and drawdown constraints.

> Optimise approximately: Robust EV + Quality + Reliability + Diversification − Uncertainty − Dependence − Execution Risk − Drawdown Risk.

For implementation, this should become an explicit scoring function or constrained optimisation problem whose terms are normalised and backtested. A simple exhaustive/beam-search optimiser may be preferable to a sophisticated solver at first because it is easier to audit.

# PART VIII — BANKROLL, RISK AND DRAWDOWN CONTROL

## 34. Risk engine objective
A profitable predictive process can still destroy capital if staking is uncontrolled. The risk engine therefore operates independently from the selection engine and may veto an otherwise qualified ticket.

| Metric | Required tracking |
| --- | --- |
| Current bankroll | Settled capital base |
| Available bankroll | Bankroll less committed unsettled exposure |
| Daily exposure | Total stakes at risk today |
| Ticket exposure | Stake and maximum loss by product |
| Maximum drawdown | Peak-to-trough bankroll decline |
| Rolling volatility | P/L variability over defined windows |
| Kelly fraction | Theoretical stake fraction from edge and odds |
| Recommended stake | Fractional Kelly after caps and state adjustment |
| Risk of ruin proxy | Simulation/analytical estimate where feasible |

## 35. Fractional Kelly and exposure caps
Full Kelly is too aggressive when model probabilities are uncertain. The initial policy should use approximately 1/5 to 1/4 Kelly with hard exposure caps. These values are research defaults and must be tested under realistic historical drawdowns.

| Control | Initial policy |
| --- | --- |
| Single accumulator ticket | Normally ≤2% of bankroll |
| Total daily accumulator exposure | Normally ≤4–5% of bankroll |
| Core allocation | Highest relative allocation |
| Growth allocation | Medium allocation |
| Alpha allocation | Lowest allocation |
| Loss recovery | No Martingale, doubling or stake-chasing logic |

## 36. Drawdown-aware operating state

| State | Illustrative trigger | System response |
| --- | --- | --- |
| NORMAL | Healthy calibration/performance; drawdown modest | Normal thresholds and approved fractional-Kelly stake |
| CAUTION | Approx. 10% drawdown or statistically meaningful soft deterioration | Reduce stake; increase monitoring; possibly tighten marginal selections |
| DEFENSIVE | Approx. 15% drawdown or clear drift | Strongest selections only; raise qualification thresholds; restrict products |
| REVIEW | Approx. 20% drawdown, calibration failure or severe drift | Suspend live accumulator generation; investigate and revalidate |

Drawdown percentages are initial policy anchors, not immutable truths. The transition logic should also consider expected drawdown distributions, sample size, calibration drift and whether losses are statistically consistent with the model’s predicted variance.

## 37. Responsible-use controls
Bankroll limits and exposure caps should be visible and enforceable, not merely advisory.
The product should never present recovery staking, guaranteed returns or certainty language.
Performance reporting should show losing periods, drawdown and uncertainty alongside wins and ROI.
If external users are added, provide configurable deposit/stake limits, cooling-off or suspension options as appropriate to the product and jurisdiction.

# PART IX — SETTLEMENT, PERFORMANCE, LEARNING AND MODEL GOVERNANCE

## 38. Settlement engine
After each fixture/ticket, Qwantej must automatically determine outcome and store all information required for performance decomposition and future learning.

| Prediction/ticket data to preserve | Examples |
| --- | --- |
| Decision state | Probability layers, odds taken, fair market probability, edge, EV |
| Context | Market, league, teams, data quality, model versions, QSS/LRS/MRS |
| Execution | Published/locked odds, timestamps, later closing odds |
| Outcome | Win/loss/void/push, settlement rule and source |
| Financial | Stake, return, profit/loss, bankroll effect |
| Evaluation | Brier/log-loss contribution, CLV, calibration bin, rejection/pass diagnostics |

## 39. Performance framework

| Level | Question |
| --- | --- |
| Selection | Are individual probabilities accurate, calibrated and valuable? |
| Market | Which market families produce robust edge? |
| League / league-market | Where does Qwantej have or lack advantage? |
| Accumulator product | Do Core/Growth/Alpha produce risk-adjusted value after compounding? |
| Model / version | Which model/calibrator combinations improve out-of-sample performance? |
| Timing / execution | When should Qwantej price and lock tickets? |

## 40. KPI hierarchy

| Dimension | Primary KPIs |
| --- | --- |
| Predictive | Brier Score, Brier Skill Score, Log Loss, calibration slope/intercept, ECE |
| Betting | ROI, yield, profit factor where useful, break-even hit rate, realised EV |
| Market quality | CLV, edge distribution, price slippage, stale-price rejection rate |
| Risk | Maximum drawdown, volatility, losing streak distribution, risk-of-ruin proxy |
| Reliability | Posterior LRS/MRS, effective sample size, uncertainty, state changes |
| Operational | Data completeness, DQS distribution, fixture coverage, job failure rate, prediction latency |

Hit rate must always be interpreted alongside average odds and break-even probability. Qwantej must never optimise around “number of winning tickets” in isolation.

## 41. Backtesting policy — non-negotiable
Backtesting is a governance process, not merely a historical simulation. Version 2.0 requires point-in-time, walk-forward evaluation designed to prevent future information leakage and threshold overfitting.
Use time-ordered train/validation/test or rolling walk-forward windows; never random shuffle football time series for final evaluation.
Features must be reconstructed as they were knowable at the prediction timestamp.
Calibration must be trained only on observations available before each evaluation period.
League/market reliability scores used in a historical decision must be the scores available then, not today’s revised scores.
Use the odds actually observable at the simulated decision time; closing odds are evaluation data, not early-decision inputs.
Account for voids, postponed matches, missing prices and ticket invalidation rules.
Freeze threshold sets before evaluating a hold-out period to reduce data snooping.
Compare against de-vigged market probabilities and simple statistical baselines, not only raw win rate.
Report confidence intervals or bootstrap uncertainty for ROI, calibration and product performance where feasible.
Preserve every backtest configuration, code version and result in the experiment registry.

## 42. Continuous learning without daily self-destruction
Qwantej should learn every day but should not rewrite its live decision rules after every short losing sequence. Daily jobs can update descriptive statistics, posterior reliability and drift indicators; material model or policy changes require a separate promotion process.
1. Settle outcomes
2. Update prediction errors and calibration monitoring
3. Update LRS/MRS posterior statistics
4. Update CLV and execution diagnostics
5. Detect drift
6. Train or score challengers where scheduled
7. Run backtests/validation
8. Record model/policy candidate version
9. Promote only after governance criteria are satisfied

## 43. Champion–challenger framework

| Stage | Requirement |
| --- | --- |
| Champion | Current approved production model/policy |
| Challenger | Runs in shadow mode; cannot control live tickets |
| Minimum evidence | Sufficient predictions across relevant markets; 500+ may be a practical target for broad comparison, but segmented tests require context-specific power |
| Comparison | Calibration, Brier/log loss, ROI/yield, CLV, drawdown, stability and operational reliability |
| Promotion | Challenger demonstrates robust improvement on pre-specified criteria and does not materially degrade risk |
| Rollback | Previous champion artefacts and configuration remain deployable |

## 44. Drift detection
Feature drift — input distributions change.
Prediction drift — probability distributions change unexpectedly.
Calibration drift — observed frequencies no longer match predicted probabilities.
Market drift — bookmaker efficiency/pricing relationships change.
League regime drift — scoring, home advantage, styles or competition structure change.
Execution drift — prices move faster or Qwantej captures less favourable odds.
Drift should first reduce reliability or widen uncertainty. It should not automatically trigger a new production model without validation.

# PART X — DAILY PROCESSING WORKFLOW AND PRODUCT EXPERIENCE

## 45. Timing intelligence

| Window | Typical action |
| --- | --- |
| T−24h | Initial fixture/data ingestion and baseline probability |
| T−12h | Odds refresh, market consensus and early value monitoring |
| T−6h | Stats/team-news refresh and probability stability check |
| T−2h | Injury/line-up refresh where available; candidate requalification |
| T−1h | Final optimiser run; price freshness and risk-state check |
| Lock | Freeze ticket inputs, prices, versions and rationale |
| Post-match | Settlement, CLV, performance and learning archive |

Qwantej should learn whether particular products, leagues or markets perform better when priced at specific time-to-kickoff windows. Timing itself becomes a reliability dimension.

## 46. Daily processing workflow
1. Ingest fixtures and provider mappings.
2. Capture current bookmaker odds and market metadata.
3. Update point-in-time team/competition statistics.
4. Compute DQS; reject insufficient fixtures.
5. Generate versioned features.
6. Run model stack and ensemble.
7. Apply calibration and uncertainty adjustment.
8. De-vig market prices and compute consensus fair probabilities.
9. Run Value Gate and selection qualification.
10. Update or retrieve point-in-time LRS/MRS.
11. Build dependence matrix/concentration groups.
12. Optimise Core, Growth and Alpha independently.
13. Apply bankroll/risk state and stake sizing.
14. Publish qualifying tickets or explicit NO QUALIFIED ACCA.
15. Re-evaluate on odds/data changes until lock.
16. Settle and archive results.
17. Run performance, drift and challenger monitoring.

## 47. Ticket lifecycle

| State | Meaning |
| --- | --- |
| Draft | Candidate ticket under optimisation |
| Qualified | Passes value, quality, dependence and risk constraints |
| Published | Visible to users; not yet necessarily locked |
| Odds Changed | One or more price assumptions changed materially |
| Requalified | Still valid after re-run |
| Withdrawn | No longer meets value/risk rules |
| Locked | Decision inputs and odds frozen for evaluation |
| Live | At least one leg has started |
| Won / Lost / Partial / Void | Outcome state according to rules |
| Settled | Financial result finalised |
| Learning Archive | Immutable record available for evaluation and retraining |

## 48. Dashboard architecture

| Area | Key information |
| --- | --- |
| Executive Dashboard | Bankroll, exposure, model state, ROI, drawdown, data health, today’s product availability |
| Today’s Accumulators | Core, Growth, Alpha with probability, market probability, EV, QSS, DQS, reliability, risk and rationale |
| Signals | A+/A selections, value opportunities, rejected candidates with reasons |
| Fixtures | All analysed matches, timestamps and data-quality status |
| Market Intelligence | Odds, de-vig, line movement, CLV and market profitability |
| League Intelligence | LRS, MRS, league-market matrix and dynamic status |
| Performance | ROI, yield, hit rate vs break-even, CLV, calibration, drawdown |
| Models | Champion/challenger, drift, calibration and model-version metrics |
| Archive | Immutable historical predictions, tickets, prices and settlements |
| Audit | Policy/model changes, overrides, job failures and governance events |

## 49. Recommended accumulator card

| Field | Example display |
| --- | --- |
| Product | CORE ACCA |
| Combined odds | 4.26 |
| Legs | 4 |
| Ticket quality | A+ |
| Conservative ticket probability | 31.8% |
| Market fair probability | 23.5% |
| Qwantej probability edge | +8.3 percentage points |
| Conservative EV | +35.5% |
| Average QSS | 91 |
| Data quality | Excellent |
| Reliability | High |
| Dependence risk | Low–Moderate |
| Operating state | NORMAL |
| Action | Why selected / What would invalidate this ticket |

# PART XI — IMPLEMENTATION ROADMAP AND CODING SPECIFICATION

## 50. Build order — intelligence before dashboard

| Phase | Focus | Primary deliverable |
| --- | --- | --- |
| Phase 0 | System constitution and repository governance | QWANTEJ_FRAMEWORK.md, ARCHITECTURE.md, DATA_DICTIONARY.md, policies, CI skeleton |
| Phase 1 | Data architecture and ingestion | Canonical entities, fixtures, results, odds snapshots, point-in-time storage, DQS |
| Phase 2 | Historical decision archive | Prediction schema, model/version registry, audit trail, reproducibility checks |
| Phase 3 | Baseline probability engine | Poisson, Dixon–Coles / candidate dependence model, Elo and market baselines |
| Phase 4 | Calibration and uncertainty | Calibrators, calibration monitoring, P_cons policy |
| Phase 5 | Value and backtesting | De-vig, EV, Value Gate, walk-forward backtester, leakage tests |
| Phase 6 | Reliability engine | Bayesian LRS/MRS, dynamic status, league-market matrix |
| Phase 7 | Risk engine | Bankroll ledger, fractional Kelly, exposure and drawdown states |
| Phase 8 | Accumulator optimiser | Core/Growth/Alpha constraints, dependence/concentration controls, NO ACCA output |
| Phase 9 | Settlement and learning | Automated settlement, CLV, performance, drift and champion/challenger |
| Phase 10 | API and dashboard | FastAPI services, Next.js UI and archive/explanation screens |
| Phase 11 | Notifications and operational hardening | Telegram/WhatsApp as appropriate, observability, retries, backups, security |

## 51. Definition of Done for a quantitative feature
Functional specification exists and states the exact decision rule.
Inputs/outputs and timestamps are defined in the data dictionary.
Unit tests cover normal, boundary and failure cases.
Leakage test demonstrates that future data cannot enter the computation.
Numerical sanity tests compare against a known baseline.
Backtest is walk-forward and configuration is preserved.
Metrics include calibration and risk, not only hit rate.
Logging/audit records identify model, code and policy versions.
Codex/independent review resolves probability, data and risk findings.
Documentation is updated before production promotion.

## 52. Immediate coding epics

| Epic | Key stories |
| --- | --- |
| E1 Canonical football data | fixtures/teams/competitions/provider mappings; result settlement identities |
| E2 Odds intelligence | quote capture; vig removal; consensus; closing-line archive |
| E3 Feature store | point-in-time feature snapshots and feature versions |
| E4 Model registry | model metadata, artefacts, champion/challenger states |
| E5 Probability service | model outputs, ensemble, coherent market matrix |
| E6 Calibration service | segment fallback hierarchy, diagnostics, uncertainty |
| E7 Value service | edge, EV, anomalies, Value Gate and reason codes |
| E8 Reliability service | Bayesian shrinkage, LRS/MRS and dynamic states |
| E9 Accumulator service | candidate pool, constraints, dependence and optimisation |
| E10 Risk service | bankroll, Kelly, exposure, drawdown and circuit breakers |
| E11 Settlement/performance | P/L, CLV, calibration, rolling KPIs and archive |
| E12 Dashboard/API | product cards, explainability, archive, model health and audit |

# APPENDIX A — INITIAL POLICY THRESHOLDS (RESEARCH DEFAULTS)
These are starting configuration values, not claims of optimality. Every threshold must be backtested and may change through governed policy versions.

| Policy | Core | Growth | Alpha |
| --- | --- | --- | --- |
| Combined odds | 3.00–5.00 | >5.00–10.00 | >10.00–20.00 |
| Typical legs | 3–4 | 4–6 | 5–7 |
| Preferred QSS | ≥87 | ≥85 | ≥82 |
| Hard QSS floor | ≥82 unless research-only | ≥82 | ≥82 |
| DQS | Prefer ≥80; hard floor 70 | Prefer ≥80; hard floor 70 | Prefer ≥80; hard floor 70 |
| League/market state | Qualified | Qualified; limited Watch only if policy explicitly allows | Qualified only initially |
| Same fixture | Max 1 leg | Max 1 leg | Max 1 leg |
| Same league | Max 2 initial | Max 2 initial | Max 2 initial |
| Same market family | Max 3 initial | Max 3 initial | Max 3 initial |
| Stake priority | Highest | Medium | Lowest |
| No-bet behaviour | Allowed / expected | Allowed / expected | Allowed / expected |

# APPENDIX B — KEY FORMULAS AND DEFINITIONS

| Concept | Definition / baseline formula |
| --- | --- |
| Raw implied probability | p_raw_market = 1 / decimal_odds |
| Fair market probability | p_market_fair = de-vigged bookmaker/consensus probability |
| Probability edge | Edge_pp = P_cons − p_market_fair |
| Selection expected value | EV = P_cons × decimal_odds − 1 |
| Independent ticket baseline | P_ticket_ind = Π P_cons,i |
| Ticket expected value baseline | EV_ticket = P_ticket × combined_odds − 1 |
| Shrinkage weight | w = n_eff / (n_eff + k) |
| Shrunk reliability estimate | R_post = w R_segment + (1−w) R_parent/global |
| Fractional Kelly | Stake fraction = Kelly_fraction × configured multiplier, then hard caps apply |
| CLV | Compare price taken with closing market using a consistent odds/probability convention |

# APPENDIX C — MINIMUM PREDICTION RECORD
prediction_id, fixture_id, prediction_timestamp, decision_as_of
competition_id, season_id, home_team_id, away_team_id
market, selection, line where applicable
poisson_probability, dixon_coles_probability, zinb_probability, elo_probability, market_model_probability (where used)
ensemble_probability, calibrated_probability, conservative_probability
bookmaker, executable_odds, quote_timestamp, fair_market_probability
edge_pp, expected_value, uncertainty_measure
DQS, QSS, LRS, MRS, dynamic reliability states
model_version, feature_version, calibration_version, risk_policy_version, optimiser_version, code_commit
accumulator_id / product where applicable
result, settlement_status, stake, return, profit_loss
closing_odds, CLV, Brier contribution, log-loss contribution
created_at, audit/reason codes

# APPENDIX D — REJECTION REASON TAXONOMY

| Code | Meaning |
| --- | --- |
| DATA_LOW_DQS | Data Quality Score below policy |
| DATA_STALE | Required data snapshot too old |
| MODEL_UNSTABLE | Excessive model disagreement or sensitivity |
| CALIBRATION_UNAVAILABLE | No approved calibrator/fallback |
| UNCERTAINTY_TOO_HIGH | Conservative probability falls below threshold |
| MARKET_STALE | Odds too old to support value claim |
| EDGE_TOO_LOW | Probability edge below minimum |
| EV_NON_POSITIVE | Conservative EV not positive / below minimum |
| RELIABILITY_LOW | LRS/MRS or state below product policy |
| QSS_LOW | Selection quality below threshold |
| CORRELATION_CONCENTRATION | Dependence or diversification constraint violated |
| PRODUCT_ODDS_OUT_OF_RANGE | Ticket cannot satisfy odds band without quality dilution |
| RISK_STATE_BLOCK | Current drawdown/operating state blocks product |
| EXPOSURE_CAP | Bankroll exposure limit reached |
| ANOMALY_REVIEW | Extreme edge, mapping or model-market anomaly unresolved |

# APPENDIX E — QWANTEJ’S ULTIMATE DECISION TREE
Fixture valid and mapped?
PASS ↓     FAIL → REJECT
Enough point-in-time data?
PASS ↓     FAIL → REJECT
DQS sufficient?
PASS ↓     FAIL → REJECT
Model outputs numerically valid?
PASS ↓     FAIL → REJECT
Probability stable?
PASS ↓     FAIL → REJECT
Calibration valid?
PASS ↓     FAIL → REJECT
Conservative probability calculated?
PASS ↓     FAIL → REJECT
Executable market price fresh?
PASS ↓     FAIL → REJECT
Fair market probability de-vigged?
PASS ↓     FAIL → REJECT
Positive conservative edge and EV?
PASS ↓     FAIL → REJECT
League/market reliability sufficient?
PASS ↓     FAIL → REJECT
QSS sufficient?
PASS ↓     FAIL → REJECT
No anomaly unresolved?
PASS ↓     FAIL → REJECT
Compatible with dependence/diversification rules?
PASS ↓     FAIL → REJECT
Improves a product accumulator without quality dilution?
PASS ↓     FAIL → REJECT
Risk engine permits exposure?
PASS ↓     FAIL → REJECT

> ACCEPT → construct/retain ticket. Any material price or data change before lock → re-run the relevant gates.

# APPENDIX F — FRAMEWORK IN ONE LINE

> Qwantej should construct an accumulator only when every leg is statistically credible, point-in-time valid, calibrated, uncertainty-adjusted, sufficiently priced, historically reliable, dependence-compatible and risk-compatible—and when the resulting ticket remains superior to the market under a conservative estimate.

## Closing position
Version 2.0 turns Qwantej into a measurable research-and-decision platform rather than a tips interface. Its most important assets are the immutable historical decision record, the calibration and reliability evidence, and the governance process that determines when the system should act—and when it should refuse to act.
The next engineering deliverable should be a Technical Specification v1.0 that converts each engine into database schemas, APIs, exact algorithms, configuration values, test cases, background jobs and acceptance criteria. That specification should become the authoritative contract used by both the primary coding agent and the independent reviewer.
