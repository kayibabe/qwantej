"""
xgboost_model.py — Gradient boosted meta-learner on top of ZINB + Bayesian + Elo.

Architecture
============
XGBoost acts as a stacking meta-learner: it is trained on historical match data
using bookmaker-implied probabilities + basic stats as features, then predicts
per-market outcome probabilities at inference time from our own model outputs.

Training data
-------------
Source: `historical_fixtures` table (populated by historical_data_etl.py).
Target variables: `over_1_5`, `over_2_5`, `under_2_5`, `under_3_5`, `btts`,
                  1X2-derived market booleans.

Feature vector (8 dimensions, per market)
------------------------------------------
  0: primary_prob    — P(event) from main model (ZINB for goals, Elo for 1X2)
  1: secondary_prob  — P(event) from secondary model (Bayesian implied)
  2: market_implied  — bookmaker fair probability (1/odds normalised)
  3: lambda_total    — ZINB expected total goals
  4: elo_diff        — Elo rating difference (home − away), scaled 0-1
  5: lambda_home     — ZINB expected home goals
  6: lambda_away     — ZINB expected away goals
  7: odds_raw        — raw market decimal odds (0 if unavailable)

Training feature mapping uses historical bookmaker odds as surrogates for
model outputs (bookmaker-implied ≈ Bayesian probability).

Model persistence
-----------------
Models are serialised with joblib to:
  {MODEL_DIR}/{market_slug}.pkl

If the file does not exist, the market is silently skipped (XGBoost weight = 0).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Model files live next to the DB by default; override via XGB_MODEL_DIR env var.
_MODEL_DIR = Path(os.getenv("XGB_MODEL_DIR", "xgb_models"))

# XGBoost hyperparameters — conservative defaults for Phase 1 (limited data).
_XGB_PARAMS: dict = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 10,   # avoid overfitting on thin markets
    "eval_metric": "logloss",
    "use_label_encoder": False,
    "random_state": 42,
    "n_jobs": -1,
}

_MIN_TRAINING_ROWS = 500   # skip market if fewer historical rows


def _market_slug(market: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", market.lower()).strip("_")


# Per-market training configuration: {market: (feature_cols, target_col)}
# Feature columns reference columns in historical_fixtures that act as
# training surrogates for our model outputs.
_MARKET_TRAIN_CFG: dict[str, dict] = {
    "Over 1.5": {
        "target":   "over_1_5",
        "f_primary":   ["odds_over_1_5", "odds_under_1_5"],
        "f_secondary": ["odds_over_2_5", "odds_home_win", "odds_draw", "odds_away_win"],
    },
    "Over 2.5": {
        "target":   "over_2_5",
        "f_primary":   ["odds_over_2_5", "odds_under_2_5"],
        "f_secondary": ["odds_home_win", "odds_draw", "odds_away_win", "odds_over_1_5"],
    },
    "Under 2.5": {
        "target":   "under_2_5",
        "f_primary":   ["odds_under_2_5", "odds_over_2_5"],
        "f_secondary": ["odds_home_win", "odds_draw", "odds_away_win"],
    },
    "Under 3.5": {
        "target":   "under_3_5",
        "f_primary":   ["odds_under_3_5", "odds_over_3_5"],
        "f_secondary": ["odds_under_2_5", "odds_over_2_5", "odds_home_win"],
    },
    "BTTS Yes": {
        "target":   "btts",
        "f_primary":   ["odds_btts_yes", "odds_btts_no"],
        "f_secondary": ["odds_home_win", "odds_away_win", "odds_over_2_5"],
    },
    "1X (Home or Draw)": {
        "target":   None,   # computed as (result != 'A')
        "f_primary":   ["odds_home_win", "odds_draw"],
        "f_secondary": ["odds_away_win", "odds_over_2_5"],
    },
    "X2 (Draw or Away)": {
        "target":   None,   # computed as (result != 'H')
        "f_primary":   ["odds_draw", "odds_away_win"],
        "f_secondary": ["odds_home_win", "odds_over_2_5"],
    },
    "Home Over 0.5": {
        "target":   None,   # computed as (home_goals >= 1)
        "f_primary":   ["odds_home_win"],
        "f_secondary": ["odds_draw", "odds_away_win", "odds_over_1_5"],
    },
    "Away Over 0.5": {
        "target":   None,   # computed as (away_goals >= 1)
        "f_primary":   ["odds_away_win"],
        "f_secondary": ["odds_home_win", "odds_draw", "odds_over_1_5"],
    },
}


def _safe_implied(odds: object) -> float:
    """Convert decimal odds → implied probability. Returns 0.0 on bad input."""
    try:
        o = float(odds)
        return round(1.0 / o, 6) if o > 1.0 else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


class XGBoostMarketModel:
    """Thin wrapper around one XGBClassifier for one market."""

    def __init__(self, market: str) -> None:
        self.market = market
        self._clf = None

    @property
    def is_fitted(self) -> bool:
        return self._clf is not None

    def predict_proba(self, features: list[float]) -> float:
        """Return P(event) for a feature vector. Returns None if not fitted."""
        if self._clf is None:
            return None
        import numpy as np
        X = np.array(features, dtype=float).reshape(1, -1)
        return float(self._clf.predict_proba(X)[0, 1])

    def save(self, model_dir: Path) -> None:
        if self._clf is None:
            return
        try:
            import joblib
            model_dir.mkdir(parents=True, exist_ok=True)
            path = model_dir / f"{_market_slug(self.market)}.pkl"
            joblib.dump(self._clf, path)
            logger.info("XGBoost: saved %s → %s", self.market, path)
        except Exception as e:
            logger.error("XGBoost: save failed for %s — %s", self.market, e)

    def load(self, model_dir: Path) -> bool:
        path = model_dir / f"{_market_slug(self.market)}.pkl"
        if not path.exists():
            return False
        try:
            import joblib
            self._clf = joblib.load(path)
            return True
        except Exception as e:
            logger.warning("XGBoost: load failed for %s — %s", self.market, e)
            return False


class XGBoostEnsemble:
    """
    Collection of per-market XGBoost classifiers.

    Usage:
        ens = XGBoostEnsemble()
        ens.load_all()              # loads pre-trained models from disk
        ens.predict_all(...)        # returns {market: prob}

    Training:
        ens.train_all(historical_rows)
        ens.save_all()
    """

    def __init__(self, model_dir: Path = _MODEL_DIR) -> None:
        self.model_dir = model_dir
        self._models: dict[str, XGBoostMarketModel] = {
            market: XGBoostMarketModel(market)
            for market in _MARKET_TRAIN_CFG
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_all(self) -> None:
        for m in self._models.values():
            m.save(self.model_dir)

    def load_all(self) -> int:
        """Load all available models from disk. Returns count loaded."""
        loaded = sum(1 for m in self._models.values() if m.load(self.model_dir))
        logger.info("XGBoost: loaded %d/%d market models", loaded, len(self._models))
        return loaded

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_all(
        self,
        zinb_probs: dict[str, float],
        bayesian_probs: dict[str, float],
        elo_1x2: tuple[float, float, float] | None,
        market_odds: dict[str, float],
        lambda_home: Optional[float] = None,
        lambda_away: Optional[float] = None,
        elo_home: Optional[float] = None,
        elo_away: Optional[float] = None,
    ) -> dict[str, float]:
        """
        Build feature vectors from model outputs and predict P(event) per market.
        Returns {} if no models are loaded.
        """
        if not any(m.is_fitted for m in self._models.values()):
            return {}

        lh = lambda_home or 0.0
        la = lambda_away or 0.0
        lambda_total = lh + la

        # Elo rating difference scaled to [0,1]: diff of 600 points → near 1
        elo_diff = 0.0
        if elo_home and elo_away:
            elo_diff = max(-1.0, min(1.0, (elo_home - elo_away) / 600.0))

        # Elo 1X2 implied probs
        elo_home_win = elo_1x2[0] if elo_1x2 else 0.0
        elo_draw = elo_1x2[1] if elo_1x2 else 0.0
        elo_away_win = elo_1x2[2] if elo_1x2 else 0.0

        results: dict[str, float] = {}

        for market, model in self._models.items():
            if not model.is_fitted:
                continue

            z = zinb_probs.get(market, 0.0) or 0.0
            b = bayesian_probs.get(market, 0.0) or 0.0
            m_odds = market_odds.get(market)
            m_implied = _safe_implied(m_odds) if m_odds else 0.0
            raw_odds = m_odds or 0.0

            # Market-specific primary / secondary probabilities
            if "1X" in market or "X2" in market or "Home Over" in market or "Away Over" in market:
                # Use Elo for 1X2-derived markets
                if "1X" in market:
                    e_prob = elo_home_win + elo_draw
                elif "X2" in market:
                    e_prob = elo_draw + elo_away_win
                elif "Home Over" in market:
                    e_prob = elo_home_win
                else:
                    e_prob = elo_away_win
            else:
                e_prob = 0.0

            features = [
                z,                # primary model prob
                b,                # bayesian / implied prob
                e_prob,           # elo-derived prob
                m_implied,        # bookmaker fair probability
                lambda_total,     # expected total goals
                elo_diff,         # elo rating gap
                lh,               # expected home goals
                la,               # expected away goals
                raw_odds,         # raw decimal odds
            ]

            prob = model.predict_proba(features)
            if prob is not None and 0.0 < prob < 1.0:
                results[market] = round(prob, 6)

        return results

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train_all(self, historical_rows: list[dict]) -> dict[str, int]:
        """
        Train per-market classifiers from historical fixture rows.

        Each row must be a dict with keys matching HistoricalFixture columns.
        Returns {market: n_training_rows}.
        """
        try:
            import xgboost as xgb
            import numpy as np
        except ImportError:
            logger.error(
                "XGBoost is not installed — run: pip install xgboost lightgbm"
            )
            return {}

        results = {}
        for market, cfg in _MARKET_TRAIN_CFG.items():
            X_rows = []
            y_rows = []

            for row in historical_rows:
                # Compute target
                target_col = cfg.get("target")
                if target_col:
                    target = row.get(target_col)
                else:
                    # Derived target
                    hg = row.get("home_goals")
                    ag = row.get("away_goals")
                    result = row.get("result", "")
                    if "1X" in market:
                        target = result in ("H", "D")
                    elif "X2" in market:
                        target = result in ("D", "A")
                    elif "Home Over" in market:
                        target = hg is not None and hg >= 1
                    elif "Away Over" in market:
                        target = ag is not None and ag >= 1
                    else:
                        target = None

                if target is None:
                    continue

                # Build feature vector from bookmaker odds (training surrogates)
                f_primary = cfg.get("f_primary", [])
                f_secondary = cfg.get("f_secondary", [])

                # Primary features: 2 odds columns → 2 implied probs
                p_feats = [_safe_implied(row.get(c)) for c in f_primary]
                s_feats = [_safe_implied(row.get(c)) for c in f_secondary]

                # Pad/truncate to fixed width for consistency
                p_feats = (p_feats + [0.0] * 4)[:4]
                s_feats = (s_feats + [0.0] * 4)[:4]

                # Add lambda total from odds sum (crude proxy)
                hg = row.get("home_goals") or 0
                ag = row.get("away_goals") or 0

                feats = p_feats + s_feats + [float(hg + ag)]
                X_rows.append(feats)
                y_rows.append(int(bool(target)))

            if len(X_rows) < _MIN_TRAINING_ROWS:
                logger.info(
                    "XGBoost: skipping %s — only %d training rows (min %d)",
                    market, len(X_rows), _MIN_TRAINING_ROWS,
                )
                continue

            X = np.array(X_rows, dtype=float)
            y = np.array(y_rows, dtype=int)

            # Remove rows where all features are 0 (missing odds)
            valid = np.any(X != 0, axis=1)
            X, y = X[valid], y[valid]

            if len(X) < _MIN_TRAINING_ROWS:
                logger.info("XGBoost: skipping %s after zeroed-row removal", market)
                continue

            logger.info("XGBoost: training %s on %d rows (%.1f%% positives)",
                        market, len(X), 100.0 * y.sum() / len(y))

            clf = xgb.XGBClassifier(**_XGB_PARAMS)
            clf.fit(X, y, verbose=False)
            self._models[market]._clf = clf
            results[market] = len(X)
            logger.info("XGBoost: fitted %s", market)

        return results


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-loaded)
# ---------------------------------------------------------------------------

_ensemble: XGBoostEnsemble | None = None


def get_xgb_ensemble() -> XGBoostEnsemble:
    """Return the module-level singleton, loading models from disk if needed."""
    global _ensemble
    if _ensemble is None:
        _ensemble = XGBoostEnsemble()
        _ensemble.load_all()
    return _ensemble


async def train_and_save(db, model_dir: Path = _MODEL_DIR) -> dict[str, int]:
    """
    Train XGBoost models from historical_fixtures and persist to disk.

    Called by the admin endpoint POST /api/admin/etl/xgb-train.
    Returns {market: n_training_rows}.
    """
    from sqlalchemy import select
    from app.models.historical_fixture import HistoricalFixture

    result = await db.execute(
        select(
            HistoricalFixture.home_goals,
            HistoricalFixture.away_goals,
            HistoricalFixture.result,
            HistoricalFixture.btts,
            HistoricalFixture.over_1_5,
            HistoricalFixture.over_2_5,
            HistoricalFixture.over_3_5,
            HistoricalFixture.under_2_5,
            HistoricalFixture.under_3_5,
            HistoricalFixture.odds_home_win,
            HistoricalFixture.odds_draw,
            HistoricalFixture.odds_away_win,
            HistoricalFixture.odds_over_1_5,
            HistoricalFixture.odds_under_1_5,
            HistoricalFixture.odds_over_2_5,
            HistoricalFixture.odds_under_2_5,
            HistoricalFixture.odds_over_3_5,
            HistoricalFixture.odds_under_3_5,
            HistoricalFixture.odds_btts_yes,
            HistoricalFixture.odds_btts_no,
        ).where(
            HistoricalFixture.home_goals.is_not(None),
            HistoricalFixture.away_goals.is_not(None),
        )
    )
    rows = [dict(r._mapping) for r in result.all()]
    logger.info("XGBoost: loaded %d training rows from historical_fixtures", len(rows))

    ens = XGBoostEnsemble(model_dir)
    market_counts = ens.train_all(rows)
    ens.save_all()

    # Reload the singleton
    global _ensemble
    _ensemble = ens

    return market_counts
