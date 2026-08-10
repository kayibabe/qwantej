"""
migrations.py — Lightweight additive migrations for SQLite.

SQLite doesn't support ALTER TABLE ... ADD COLUMN IF NOT EXISTS before 3.37,
so we detect "duplicate column" errors and treat them as benign. Anything
else (locked DB, disk I/O, missing table) is logged as a warning so it can
be diagnosed instead of silently producing a half-migrated schema.
"""
from __future__ import annotations

import logging
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

# Each entry: (table, column, column_def)
COLUMN_MIGRATIONS = [
    ("tracked_bets",        "closing_odds",          "REAL"),
    ("tracked_bets",        "clv_pct",               "REAL"),
    ("signals",             "poisson_mixed_signals", "TEXT"),
    ("tracked_bets",        "user_id",               "INTEGER REFERENCES users(id)"),
    ("signals",             "odds_drift_pct",        "REAL"),
    ("tracked_bets",        "data_completeness",     "TEXT"),
    ("tracked_bets",        "dual_agreement",        "TEXT"),
    ("learning_proposals",  "updated_at",            "DATETIME"),
    # ── BOS 2.0 ───────────────────────────────────────────────────────────────
    ("signals", "bos_si",           "REAL"),
    ("signals", "bos_passed",       "INTEGER"),   # SQLite boolean → INTEGER
    # ── ZINB goal model ───────────────────────────────────────────────────────
    ("signals", "zinb_lambda_h",    "REAL"),
    ("signals", "zinb_lambda_a",    "REAL"),
    # ── Glicko-2 rating differential + rating age ─────────────────────────────
    ("signals", "glicko_r_diff",           "REAL"),
    ("signals", "glicko_rating_age_days",  "INTEGER"),
    # ── BREA (BTTS risk enrichment) ───────────────────────────────────────────
    ("signals", "brea_ri1",         "REAL"),
    ("signals", "brea_fss",         "REAL"),
    # ── FHGI (enhanced FH Over 0.5) ───────────────────────────────────────────
    ("signals", "fhgi_gpi",         "REAL"),
    ("signals", "fhgi_fhgmi",       "REAL"),
    ("signals", "fhgi_p_model",     "REAL"),
    # ── WTCPM (corner signals) ─────────────────────────────────────────────────
    ("signals", "wtcpm_di",         "REAL"),
    ("signals", "wtcpm_ccs",        "REAL"),
    ("signals", "wtcpm_p_corners",  "REAL"),
    # ── Halftime scores (needed by FHGI calibrator) ───────────────────────────
    ("fixtures", "home_score_ht",   "INTEGER"),
    ("fixtures", "away_score_ht",   "INTEGER"),
    # ── Actual corner counts (needed by WTCPM H2H corner service) ──────────────
    ("fixtures", "home_corners",    "INTEGER"),
    ("fixtures", "away_corners",    "INTEGER"),
    # ── Admin flag — explicit boolean; no longer inferred from tier ────────────
    ("users",    "is_admin",        "INTEGER NOT NULL DEFAULT 0"),
    # ── Backtest agreement column ─────────────────────────────────────────────
    ("backtest_results", "dual_agreement", "TEXT"),
    # ── Candidate signals (stored for backtesting, not served) ───────────────
    # Over 1.5 / Over 2.5 Bayesian-only High signals collected to validate
    # performance before enabling as a live tier. Default 0 = served normally.
    ("signals", "is_candidate", "INTEGER NOT NULL DEFAULT 0"),
    # ── User activity tracking ────────────────────────────────────────────────
    ("users", "last_active_at", "DATETIME"),
    # ── ACCA ticket grouping — one stable ID per advisory ticket per date ─────
    # Allows analytics to group legs by ticket rather than by event_date alone,
    # fixing incorrect hit-rate counts when multiple tickets exist on one date.
    ("tracked_bets", "acca_ticket_id", "TEXT"),
    # ── Hybrid B Strategy Engine — signal model fields ────────────────────────
    ("signals", "home_xg",              "REAL"),
    ("signals", "away_xg",              "REAL"),
    ("signals", "home_xga",             "REAL"),
    ("signals", "recency_xg_away",      "REAL"),
    ("signals", "bos_stability",        "TEXT"),
    ("signals", "selected_market",      "TEXT"),
    ("signals", "ep_x2",                "REAL"),
    ("signals", "ep_away_o05",          "REAL"),
    ("signals", "recommended_stake",    "REAL"),
    ("signals", "stake_tier",           "TEXT"),
    ("signals", "home_o05_odds_logged", "REAL"),
    ("signals", "home_team_scored",     "INTEGER"),
    # ── Hybrid B — tracked_bet passive tracking fields ─────────────────────────
    ("tracked_bets", "home_team_scored",     "INTEGER"),
    ("tracked_bets", "home_o05_odds_logged", "REAL"),
    # ── Hybrid B — weather override (Phase 6 Rule 5) needs venue location ──────
    ("fixtures", "venue_city", "TEXT"),
    # ── XGBoost meta-learner probability (Phase 1 model addition) ─────────────
    ("forecast_snapshots", "xgb_prob", "REAL"),
    # ── Data Value Score components ───────────────────────────────────────────
    ("data_source_experiments", "accuracy_score",    "REAL"),
    ("data_source_experiments", "calibration_score", "REAL"),
    ("data_source_experiments", "roi_score",         "REAL"),
    ("data_source_experiments", "coverage_score",    "REAL"),
    ("data_source_experiments", "timeliness_score",  "REAL"),
    ("data_source_experiments", "cost_score",        "REAL"),
    ("data_source_experiments", "data_value_score",  "REAL"),
    ("data_source_experiments", "updated_at",        "DATETIME"),
]

TABLE_MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS calibration_snapshots (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date   DATE    NOT NULL,
        window_days     INTEGER NOT NULL DEFAULT 90,
        n_bets          INTEGER NOT NULL,
        win_rate        REAL,
        brier_score     REAL,
        brier_skill     REAL,
        ece             REAL,
        flagged_markets TEXT,
        market_summary  TEXT,
        created_at      DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS system_settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS telegram_push_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        push_date    DATE    NOT NULL,
        channel_type TEXT    NOT NULL,
        push_type    TEXT    NOT NULL,
        sent_at      DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
        UNIQUE(push_date, channel_type, push_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS loss_analyses (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        tracked_bet_id  INTEGER NOT NULL REFERENCES tracked_bets(id),
        event_date      DATE,
        match_name      VARCHAR(255),
        league          VARCHAR(120),
        league_tier     INTEGER,
        market_type     VARCHAR(120),
        odds            REAL,
        dual_confidence VARCHAR(10),
        source_rule_key VARCHAR(40),
        home_score      INTEGER,
        away_score      INTEGER,
        agent_id        VARCHAR(40) NOT NULL DEFAULT 'loss_analyst',
        failure_categories VARCHAR(500),
        narrative       TEXT,
        recommendation  TEXT,
        avoidability_score REAL,
        created_at      DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_proposals (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        change_type     VARCHAR(60)  NOT NULL,
        target          VARCHAR(120) NOT NULL,
        proposed_value  REAL,
        rationale       TEXT,
        confidence      VARCHAR(10),
        backtest_note   TEXT,
        is_active       INTEGER NOT NULL DEFAULT 1,
        created_at      DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_forecasts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        source              VARCHAR(40)  NOT NULL,
        home_team           VARCHAR(120) NOT NULL,
        away_team           VARCHAR(120) NOT NULL,
        league              VARCHAR(120),
        country             VARCHAR(80),
        match_date          DATE         NOT NULL,
        fixture_id          INTEGER,
        scraped_at          DATETIME     DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
        home_win_prob       REAL,
        draw_prob           REAL,
        away_win_prob       REAL,
        over_15_prob        REAL,
        over_25_prob        REAL,
        under_25_prob       REAL,
        over_35_prob        REAL,
        under_35_prob       REAL,
        btts_yes_prob       REAL,
        btts_no_prob        REAL,
        pred_home_goals     REAL,
        pred_away_goals     REAL,
        confidence_label    VARCHAR(40),
        actual_home_goals   INTEGER,
        actual_away_goals   INTEGER,
        settled             INTEGER      NOT NULL DEFAULT 0,
        settled_at          DATETIME,
        brier_1x2_home      REAL,
        brier_1x2_draw      REAL,
        brier_1x2_away      REAL,
        brier_o15           REAL,
        brier_o25           REAL,
        brier_u25           REAL,
        brier_btts          REAL,
        UNIQUE(source, home_team, away_team, match_date)
    )
    """,
]


def _is_already_exists_error(exc: BaseException) -> bool:
    """
    Detects 'already exists' errors from both SQLite and PostgreSQL.
    SQLite: 'duplicate column name: foo'
    PostgreSQL: 'column "foo" of relation "bar" already exists'
    """
    msg = str(exc).lower()
    return "duplicate column" in msg or "already exists" in msg


INDEX_MIGRATIONS: list[tuple[str, str]] = [
    (
        "uq_bet_user",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bet_user "
        "ON tracked_bets (user_id, fixture_id, bookmaker, market_type, selection_name) "
        "WHERE user_id IS NOT NULL",
    ),
    (
        "ix_fixture_status",
        "CREATE INDEX IF NOT EXISTS ix_fixture_status ON fixtures(status)",
    ),
    (
        "ix_fixture_kickoff",
        "CREATE INDEX IF NOT EXISTS ix_fixture_kickoff ON fixtures(kickoff_at)",
    ),
    (
        "ix_signal_fixture_market",
        "CREATE INDEX IF NOT EXISTS ix_signal_fixture_market ON signals(fixture_id, market)",
    ),
    (
        "ix_signal_fixture_computed",
        "CREATE INDEX IF NOT EXISTS ix_signal_fixture_computed ON signals(fixture_id, computed_at)",
    ),
    (
        "ix_ms_fixture_pulledat",
        "CREATE INDEX IF NOT EXISTS ix_ms_fixture_pulledat ON market_snapshots(fixture_id, pulled_at)",
    ),
    (
        "ix_lp_change_type_target",
        "CREATE INDEX IF NOT EXISTS ix_lp_change_type_target "
        "ON learning_proposals(change_type, target)",
    ),
    (
        "ix_tb_user_created",
        "CREATE INDEX IF NOT EXISTS ix_tb_user_created "
        "ON tracked_bets(user_id, created_at DESC)",
    ),
    (
        "ix_tb_source_created",
        "CREATE INDEX IF NOT EXISTS ix_tb_source_created "
        "ON tracked_bets(source_rule_key, created_at DESC)",
    ),
    (
        "ix_tb_event_date",
        "CREATE INDEX IF NOT EXISTS ix_tb_event_date "
        "ON tracked_bets(event_date)",
    ),
    # One acca_advisory row per authenticated user per day — DB-level guard
    # (the app-level SELECT-before-INSERT handles the common path; this catches races)
    (
        "uq_acca_per_user_day",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_acca_per_user_day "
        "ON tracked_bets(user_id, event_date) "
        "WHERE source_rule_key = 'acca_advisory' AND user_id IS NOT NULL",
    ),
    # One system signal bet per fixture+market — DB-level guard against duplicate
    # auto-tracking when concurrent startup syncs both read the same empty dedup set
    # before either commits (race condition on consecutive deploys).
    # Excludes accumulators (fixture_id IS NULL) and user-tracked bets (user_id IS NOT NULL).
    (
        "uq_system_signal_bet",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_system_signal_bet "
        "ON tracked_bets (fixture_id, market_type) "
        "WHERE user_id IS NULL AND fixture_id IS NOT NULL AND market_type != 'Accumulator'",
    ),
]

# One-shot data fixes — each is an idempotent UPDATE with tight WHERE guards.
# Runs on every startup (cheap no-op once the condition is no longer true).
DATA_MIGRATIONS: list[str] = [
    # 2026-07-03: Convert 4 manually-tracked bets to system picks so they appear
    # in the system auto-tracking stats instead of the user's personal tracker.
    # Guard: only touches rows still owned by a user (user_id IS NOT NULL) that
    # aren't already classified as system picks.
    """
    UPDATE tracked_bets
    SET user_id            = NULL,
        source_rule_key    = 'system_dual',
        source_rule_label  = 'Dual Signal (High+Both)'
    WHERE event_date = '2026-07-03'
      AND user_id IS NOT NULL
      AND (source_rule_key IS NULL OR source_rule_key NOT LIKE 'system%')
      AND (
            match_name LIKE '%Treaty United%'
         OR match_name LIKE '%Drogheda United%'
         OR match_name LIKE '%Cobh Ramblers%'
         OR match_name LIKE '%Al Hikma%'
      )
    """,
    # 2026-07-02: Delfin SC vs Emelec was postponed — convert to system pick
    # and void it so it doesn't sit as a stale Pending row.
    """
    UPDATE tracked_bets
    SET user_id            = NULL,
        source_rule_key    = 'system_dual',
        source_rule_label  = 'Dual Signal (High+Both)',
        result_status      = 'Void'
    WHERE event_date = '2026-07-02'
      AND match_name LIKE '%Delfin%'
      AND result_status = 'Pending'
    """,
]


async def _run_one(engine: AsyncEngine, sql: str, label: str) -> bool:
    """
    Execute a single DDL/DML statement in its own transaction.

    Returns True on success, False if the statement was already applied
    (already-exists / duplicate-column), logs a warning on any other error.

    Running each migration in a separate connection is critical for PostgreSQL:
    a single failed statement puts the whole transaction in an aborted state,
    causing every subsequent statement to fail with "current transaction is
    aborted". Isolation per statement avoids that cascade.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
        return True
    except (OperationalError, Exception) as e:  # noqa: BLE001
        if _is_already_exists_error(e):
            return False
        log.warning("Migration FAILED — label=%r sql=%r err=%s", label, sql, e)
        return False


async def run_migrations(engine: AsyncEngine) -> None:
    """
    Apply all pending column additions and table creations. Safe to call on
    every startup — each statement runs in its own transaction so a failure
    (e.g. 'column already exists' on PostgreSQL) does not abort later steps.
    """
    for table, column, col_def in COLUMN_MIGRATIONS:
        sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
        applied = await _run_one(engine, sql, f"{table}.{column}")
        if applied:
            log.info("Migration applied: %s.%s %s", table, column, col_def)
        else:
            log.debug("Migration already applied (or skipped): %s.%s", table, column)

    for sql in TABLE_MIGRATIONS:
        applied = await _run_one(engine, sql.strip(), "CREATE TABLE")
        if applied:
            log.info("Table migration applied (CREATE TABLE IF NOT EXISTS)")

    # ── Pre-index dedup pass ──────────────────────────────────────────────────
    # Remove duplicate system signal bets (same fixture+market tracked multiple
    # times due to a bookmaker-field race on concurrent startup syncs).
    # Must run before uq_system_signal_bet index creation to avoid IntegrityError.
    dedup_sql = """
        DELETE FROM tracked_bets
        WHERE user_id IS NULL
          AND fixture_id IS NOT NULL
          AND market_type != 'Accumulator'
          AND id NOT IN (
            SELECT MIN(id)
            FROM tracked_bets
            WHERE user_id IS NULL
              AND fixture_id IS NOT NULL
              AND market_type != 'Accumulator'
            GROUP BY fixture_id, market_type
          )
    """
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(dedup_sql))
            if result.rowcount:
                log.info("Dedup migration: removed %d duplicate system signal bet(s)", result.rowcount)
    except Exception as e:  # noqa: BLE001
        log.warning("Dedup migration FAILED: %s", e)

    for index_name, sql in INDEX_MIGRATIONS:
        applied = await _run_one(engine, sql, index_name)
        if applied:
            log.info("Index migration applied: %s", index_name)

    # ── Data migrations ───────────────────────────────────────────────────
    # Seed is_admin=1 for any existing elite users who predate the column.
    await _run_one(
        engine,
        "UPDATE users SET is_admin=1 WHERE tier='elite' AND is_admin=0",
        "seed is_admin",
    )

    for dm_sql in DATA_MIGRATIONS:
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(dm_sql))
                if result.rowcount:
                    log.info("Data migration applied: %d row(s) updated", result.rowcount)
        except Exception as e:  # noqa: BLE001
            log.warning("Data migration FAILED: %s", e)
