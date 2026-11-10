# Calibration walk-forward audit

**Question: is the Q>=75 overconfidence a calibration bug or a model-ordering failure?**

Method: expanding-window walk-forward. Each matchday is scored out of sample
after fitting Platt and isotonic mappings on every earlier matchday. No
prediction is fitted on its own day, and no closing-line or outcome field is
used as an input. Per-market isotonic mappings are used when a market has at
least 250 prior picks, otherwise the global mapping.

## Headline

- Out-of-sample picks: **25,095** over **44** matchdays.
- All picks: observed **47.9%**, raw model **48.0%**, calibrated **48.2%**, bookmaker **51.7%**.
- Brier: raw **0.218**, isotonic **0.208**, implied **0.199**.
- Isotonic reduces Brier by **4.7%** versus raw, but it still scores **-4.8% worse** than the bookmaker's implied probability (positive skill score = better than market).
- Q >= 75: observed **57.4%**, raw model **77.0%**, calibrated **65.7%**, implied **60.0%**.
- Q >= 75 Brier: raw **0.257**, isotonic **0.230**, implied **0.212**.
- Market-relative test (outcome ~ logit(implied) + logit(model), days clustered): model coefficient **0.003** with 95% CI **[-0.107, 0.110]**, p(coef<=0) = **0.472**.

## Does the model beat the market?

A model can be badly calibrated and still add information. The test below asks whether the model's probability explains outcomes once the closing/entry price is known. It is the difference between "recalibrate" and "overhaul".

| Scope | N | Market coef | Model coef | Model 95% CI | p(coef<=0) | Verdict |
|---|---|---|---|---|---|---|
| all picks | 25095 | 0.966 | 0.003 | [-0.107, 0.110] | 0.472 | no demonstrated information beyond price |
| Q >= 75 | 3021 | 1.024 | -0.104 | [-0.459, 0.232] | 0.724 | no demonstrated information beyond price |

## What the numbers mean

- If calibrated Brier is close to implied Brier, a monotone mapping is enough and the model can stay.
- If calibrated Brier is still clearly worse than implied, the model's ordering is wrong, not just its level, and that is the case for a model change.
- If calibrated edge bands still show worse ROI at higher edge, the edge signal remains anti-predictive even after calibration.

## Reliability, all picks

| Scope | N | Observed % | Raw % | Calibrated % | Implied % | Brier raw | Brier iso | Brier implied | ECE raw | ECE iso |
|---|---|---|---|---|---|---|---|---|---|---|
| all picks | 25095 | 47.946 | 47.996 | 48.157 | 51.674 | 0.218 | 0.208 | 0.199 | 0.060 | 0.011 |
| Q >= 75 | 3021 | 57.431 | 76.980 | 65.664 | 59.977 | 0.257 | 0.230 | 0.212 | 0.195 | 0.082 |


## Edge bands, out of sample (all picks)

| Edge | Band | N | Hit % | ROI % |
|---|---|---|---|---|
| raw edge | <=0 | 15464 | 48.965 | -5.359 |
| raw edge | 0-5pp | 3450 | 48.435 | -7.980 |
| raw edge | 5-10pp | 2337 | 49.208 | -4.930 |
| raw edge | 10-20pp | 2535 | 43.984 | -9.215 |
| raw edge | 20pp+ | 1309 | 40.031 | -1.723 |
| calibrated edge | <=0 | 16841 | 52.152 | -4.709 |
| calibrated edge | 0-5pp | 4135 | 43.168 | -6.966 |
| calibrated edge | 5-10pp | 2149 | 40.437 | -6.165 |
| calibrated edge | 10-20pp | 1495 | 32.107 | -10.868 |
| calibrated edge | 20pp+ | 475 | 24.211 | -20.918 |


## Edge bands at Q >= 75

| Edge | Band | N | Hit % | ROI % |
|---|---|---|---|---|
| raw edge | <=0 | 19 | 100.000 | 6.737 |
| raw edge | 0-5pp | 175 | 85.714 | -2.097 |
| raw edge | 5-10pp | 495 | 78.586 | 2.451 |
| raw edge | 10-20pp | 1323 | 55.782 | -3.962 |
| raw edge | 20pp+ | 1009 | 43.508 | 1.137 |
| calibrated edge | <=0 | 927 | 67.098 | 0.002 |
| calibrated edge | 0-5pp | 698 | 63.324 | -0.404 |
| calibrated edge | 5-10pp | 599 | 57.763 | 0.260 |
| calibrated edge | 10-20pp | 517 | 46.035 | -2.561 |
| calibrated edge | 20pp+ | 280 | 31.071 | -5.975 |


## Per-market calibration (all picks)

| Market | N | Observed % | Raw % | Calibrated % | Implied % | Brier raw | Brier iso | Brier implied | ROI % |
|---|---|---|---|---|---|---|---|---|---|
| away_win | 1690 | 30.651 | 36.069 | 33.143 | 34.052 | 0.210 | 0.206 | 0.188 | -9.087 |
| draw | 1690 | 22.249 | 24.703 | 24.179 | 26.817 | 0.175 | 0.179 | 0.173 | -12.231 |
| home_win | 1690 | 47.101 | 39.227 | 45.433 | 46.790 | 0.246 | 0.240 | 0.219 | 2.896 |
| btts_no | 1689 | 43.635 | 49.543 | 43.738 | 47.379 | 0.265 | 0.248 | 0.245 | -4.229 |
| btts_yes | 1689 | 56.365 | 50.457 | 56.320 | 60.535 | 0.265 | 0.248 | 0.245 | -4.400 |
| double_chance_1x | 1689 | 69.390 | 62.601 | 66.437 | 73.104 | 0.217 | 0.208 | 0.188 | -2.444 |
| double_chance_x2 | 1689 | 52.872 | 62.037 | 54.650 | 60.449 | 0.254 | 0.240 | 0.224 | -11.668 |
| over_1.5 | 1689 | 79.218 | 74.389 | 77.455 | 82.821 | 0.186 | 0.170 | 0.164 | -1.692 |
| over_2.5 | 1689 | 55.003 | 52.877 | 55.136 | 59.291 | 0.266 | 0.248 | 0.243 | -4.099 |
| over_3.5 | 1689 | 33.452 | 34.165 | 35.141 | 37.780 | 0.234 | 0.222 | 0.217 | -7.647 |
| over_4.5 | 1689 | 18.828 | 20.357 | 19.666 | 21.353 | 0.162 | 0.157 | 0.148 | -6.725 |
| under_2.5 | 1689 | 44.997 | 47.123 | 44.898 | 47.453 | 0.266 | 0.248 | 0.242 | -1.084 |
| under_3.5 | 1689 | 66.548 | 65.835 | 64.748 | 69.479 | 0.234 | 0.222 | 0.216 | -1.397 |
| under_4.5 | 1689 | 81.172 | 79.643 | 80.156 | 86.263 | 0.162 | 0.157 | 0.150 | -3.292 |
| under_0.5 | 723 | 5.256 | 8.512 | 9.566 | 8.812 | 0.055 | 0.059 | 0.050 | -35.781 |
| under_1.5 | 723 | 20.055 | 24.269 | 23.951 | 24.228 | 0.177 | 0.178 | 0.159 | -11.501 |


## Per-market calibration at Q >= 75

| Market | N | Observed % | Raw % | Calibrated % | Implied % | Brier raw | Brier iso | Brier implied | ROI % |
|---|---|---|---|---|---|---|---|---|---|
| double_chance_x2 | 483 | 51.553 | 76.535 | 64.082 | 58.078 | 0.302 | 0.257 | 0.234 | -8.658 |
| under_3.5 | 419 | 70.644 | 84.905 | 75.057 | 71.086 | 0.221 | 0.205 | 0.198 | 2.105 |
| under_2.5 | 330 | 51.515 | 72.624 | 55.277 | 50.941 | 0.292 | 0.256 | 0.237 | 3.379 |
| under_4.5 | 315 | 83.175 | 93.011 | 87.829 | 85.879 | 0.145 | 0.142 | 0.133 | -0.733 |
| btts_no | 298 | 49.664 | 71.797 | 51.381 | 50.081 | 0.305 | 0.255 | 0.251 | 3.513 |
| over_2.5 | 224 | 58.482 | 78.719 | 65.688 | 62.606 | 0.286 | 0.248 | 0.245 | -2.487 |
| away_win | 216 | 31.019 | 57.070 | 47.652 | 32.827 | 0.279 | 0.244 | 0.206 | 7.648 |
| over_1.5 | 179 | 83.799 | 91.007 | 85.327 | 84.047 | 0.146 | 0.142 | 0.140 | 2.939 |
| double_chance_1x | 146 | 58.219 | 81.382 | 79.942 | 66.524 | 0.274 | 0.277 | 0.221 | -12.007 |
| over_3.5 | 135 | 39.259 | 68.089 | 51.436 | 45.155 | 0.323 | 0.261 | 0.237 | -9.252 |
| btts_yes | 115 | 62.609 | 76.825 | 66.598 | 62.740 | 0.258 | 0.247 | 0.233 | 2.670 |
| home_win | 87 | 35.632 | 58.587 | 59.935 | 37.069 | 0.265 | 0.279 | 0.217 | -1.701 |
| over_4.5 | 33 | 27.273 | 57.084 | 38.278 | 31.118 | 0.272 | 0.248 | 0.185 | -15.152 |
| under_1.5 | 33 | 30.303 | 56.441 | 41.642 | 28.965 | 0.277 | 0.270 | 0.197 | 3.333 |


## Caveats

- The mapping is refitted every matchday, but the model itself is a single deployed version; regime changes are not modelled.
- Per-market isotonic is only fitted when the market has enough prior picks, so small markets fall back to the global mapping.
- Walk-forward scoring starts only after 300 prior picks exist, so early matchdays are not scored.
- This audit says how much a mapping can fix. It does not by itself authorise changing live decisions; that still needs a frozen prospective review.
