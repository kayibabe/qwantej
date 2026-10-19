# Verification and interpretation

- Five focused unit tests passed: transaction-start timing, rejecting future information, retaining missing first-capture prices, excluding incomplete days/postponements, and settlement/profit accounting.
- All 46,400 source rows reconcile: 32,144 later repeats + 4,218 missing/invalid odds + 1,134 current/future-day observations + 84 without final results + 8,820 eligible observations.
- Eligible observations represent 630 distinct fixtures. Each of 14 market comparisons contains 300 later-period fixtures. Calibration bins reconcile to all 4,200 later-period market observations.
- Independent recomputation from final scores and odds confirms candidate later-period profit of 10.73 units over 33 picks (32.52% ROI).
- The prior first-capture study had 9,646 observations. The 826-observation difference is exactly 742 selections from the incomplete 18 October day and 84 postponed/cancelled observations previously counted as refunds. This is why the headline differs from that report; it is not a new independent validation sample.
- Only 2,548 of 8,820 eligible observations have both nonempty stored features and explicit decision timestamps. This basic presence check does not establish complete or uncontaminated historical inputs. For the candidate, that subset has zero earlier observations and 21 later observations, with 18.90% simulated ROI.
- Lowering Q from 65 to 60 changes candidate later-period ROI from +32.52% to -2.27%. The Q>=70 subset is smaller and was examined historically; its higher return does not justify changing the frozen rule.
- The descriptive bootstrap interval is positive, but uses only seven later matchdays and does not correct historical selection bias. It must not be interpreted as statistical confirmation of profitability.
- Calibration remains uncertain: away-win predictions in the 60-70% bin averaged 63.75% but won 50% of 26 later fixtures. The 40-50% bin averaged 44.69% and won 29.17% of 48. These are small retrospective diagnostics, not new filters.
- Repository whitespace validation passed. Application policy, database records and live services were not modified. The future protocol is saved; automated prospective collection has not been installed or scheduled.
