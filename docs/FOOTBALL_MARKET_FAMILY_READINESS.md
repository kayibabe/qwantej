# Football market family readiness in Qwantej

This register maps the 25 families in the supplied catalogue to Qwantej's
current data and decision surface. A family can contain individual contracts
with different maturity. `Partial` means only the named score-derived subset is
implemented; it never means the family is approved for picks. Every family
remains research-only until it has point-in-time evidence, market-specific
validation, and an explicit promotion.

| # | Family | Current state | What Qwantej has today | Gate before extending or using |
| --- | --- | --- | --- | --- |
| 1 | Match result markets | Partial | Regulation-time 1X2, double chance, and DNB score adapters; existing qualification gates remain | Validate calibrated probabilities and bookmaker-specific abandoned, awarded, extra-time, and void rules per contract |
| 2 | Total match goals | Partial | Half-goal total lines have settlement contracts; selected lines are scored by the existing goals path | Preserve provisional qualification gates; validate chronological calibration and odds coverage for each line; define quarter-line partial payouts before adding them |
| 3 | Team total goals | Research-only | Joint home/away scores make the outcomes mathematically derivable, but no team-total market-specific qualification policy is registered | Freeze adapters and settlement contracts; validate each side and line separately with timestamped prices and outcomes |
| 4 | Both teams to score | Partial | Full-match BTTS yes/no is scored and settled | Keep the full-match scope explicit; validate the scorer and add separate period contracts before expanding |
| 5 | Correct score markets | Research-only | Final scores are stored for completed matches; correct-score selection contracts and qualified probabilities are absent | Register bounded score outcomes and tail handling, validate the joint distribution, and establish exact provider settlement wording |
| 6 | Goal timing markets | Data-blocked | No verified event-time goal history or event-time odds snapshots in the inspected decision path | Capture timestamped goals and period boundaries with source IDs; prove historical and prospective coverage before modelling |
| 7 | First-half goal markets | Data-blocked | Half-time scores may be ingested, but first-half scoring and settlement contracts are not registered | Measure half-time score completeness and correction behavior; add period-specific calibration and settlement tests |
| 8 | Second-half goal markets | Data-blocked | Final and half-time scores can support retrospective score differences where both are present | Define whether stoppage time and extra time count; validate second-half labels and add independent probability/settlement coverage |
| 9 | Half comparison markets | Data-blocked | Some outcomes can be derived from complete half-time and final scores | Require complete period scores, explicit tie/push rules, market adapters, and chronological validation |
| 10 | Asian handicap markets | Research-only | Final scores support a subset of whole-goal comparisons; line and quarter-line settlement is not implemented | Add signed line parsing and full win/half-win/push/half-loss rules; test return accounting before qualification |
| 11 | European handicap markets | Research-only | No three-way handicap contract is registered | Specify handicap sign, adjusted score, three-way selection, and provider wording; add outcome and settlement tests |
| 12 | Winning margin markets | Research-only | Full-time scores permit retrospective margin labels | Register exact/range outcomes and validate probabilities by margin; preserve the joint score tail policy |
| 13 | Corner markets | Data-blocked | No verified corner event capture and settlement source in the current path | Confirm provider/competition coverage, point-in-time captures, official-stat correction handling, and line settlement |
| 14 | Yellow and red card markets | Data-blocked | No verified card event history or card settlement contract | Define second-yellow/red-card counting and correction rules per bookmaker; capture timestamped source events |
| 15 | Shots and shots-on-target markets | Data-blocked | No verified match/player shot labels in the scored market path | Establish provider definitions, player identity, coverage, and correction provenance before modelling |
| 16 | Player goalscoring markets | Data-blocked | No player-linked goal-event or lineup/minutes contract | Resolve player identity and participation/void rules; capture event labels and prices before validation |
| 17 | Player performance markets | Data-blocked | Player identity, minutes, and event statistics are not established as decision inputs | Prove player-level data availability, definitions, lineup status, settlement source, and holdout coverage |
| 18 | Fouls and disciplinary statistics | Data-blocked | No verified foul-event or player disciplinary source contract | Define statistic provider and correction policy; measure competition coverage and timestamped availability |
| 19 | Offside markets | Data-blocked | No verified offside event capture or settlement contract | Establish event definitions, source coverage, and settlement/correction rules before modelling |
| 20 | Possession, passing, and other team statistics | Data-blocked | No verified point-in-time team-stat feature and outcome pipeline for these markets | Separate forecast-time inputs from final statistics; define each statistic and validate source coverage and calibration |
| 21 | Combined and bet-builder markets | Dependency-blocked | Existing marginal score probabilities do not model all dependencies; no bet-builder contract is registered | Use a validated joint event model or dependence layer and bookmaker-specific combinatorial price/settlement rules |
| 22 | Special match event markets | Data-blocked | No general event taxonomy, event-time feed, or per-event settlement registry | Register each event type and timing rule separately; verify source labels and rare-event uncertainty |
| 23 | Live/in-play markets | Partial infrastructure only | Fixture live status and phase are ingested; no qualified state-conditioned forecast/price snapshot path is established | Capture synchronized match state and live odds, then validate state-conditioned forecasts prospectively |
| 24 | Extra-time and penalty shootout markets | Review-only result scope | AET/PEN fixtures retain the regulation-time score for 90-minute markets; separate extra-time and shootout outcomes are not registered | Store period and shootout scores independently; add distinct contracts and verify competition/provider settlement rules |
| 25 | Tournament, league, and season outright markets | Data/model-blocked | No season simulation, standings probability, or outright settlement contract is established | Build point-in-time competition state and season simulation, then validate outright prices and settlement definitions |

## Shared evidence requirements

Before a family moves beyond research, retain canonical market and selection
IDs, contract and mapping versions, event scope, provider and raw labels,
source snapshot IDs, capture/as-of times, required input coverage, model and
calibration versions, price timestamps, and settlement provenance. Missing
fields remain missing. A provider's market listing is not proof of data
coverage, model support, qualification, or a valid settlement rule.

The current executable contracts are listed in
[`FOOTBALL_MARKET_FRAMEWORK.md`](FOOTBALL_MARKET_FRAMEWORK.md) and exposed by
`GET /api/v1/markets/catalog`. That individual-market catalogue remains the
source for implemented score-derived contracts; this family register records
the broader 25-family roadmap without presenting the unimplemented families as
available selections.
