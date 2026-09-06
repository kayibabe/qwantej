"""Prediction Engine (framework §8 engine 3, §14-16): statistical model
families producing coherent market probabilities.

Phase 3 baselines:
- `scoreline` / `probabilities`: the shared coherent scoreline distribution
  and the validated probability result types all models emit.
- `poisson`: independent Poisson (anchor) and the Dixon-Coles low-score
  correction.
- `elo`: team-strength ratings -> 1X2 and the rating update.
- `market`: bookmaker odds de-vigged into a fair-probability benchmark.

Later phases add `zinb`, `bayesian` and the `ensemble` that blends them.
"""
