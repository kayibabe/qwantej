"""Read-only extract of the forecast archive for selection-rule tests.

One row per archived prediction, joined to its *effective* settlement (not
superseded by a correction and not withdrawn by a ticket reopen), its fixture,
league and model version. The connection is opened READ ONLY, so the script
cannot write even by accident.

Two ways to run it (see README.md):

* Locally against the dev database: ``--out path.csv``.
* Inside the ``qwantej-api`` container (production): no ``--out``; the CSV is
  printed to stdout between ``===CSV-BEGIN===`` / ``===CSV-END===`` markers so
  the caller can cut it out of the SSH session output.

Only ``psycopg`` and the standard library are used, so the file can be piped
into the container's Python without the rest of the repository.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

import psycopg

BEGIN, END = "===CSV-BEGIN===", "===CSV-END==="

SQL = """
WITH superseded AS (
    SELECT supersedes_id AS id FROM settlements WHERE supersedes_id IS NOT NULL
), reopened AS (
    SELECT entity_id AS id FROM audit_events
    WHERE entity_type = 'settlement' AND action = 'ticket_reopened' AND entity_id IS NOT NULL
), eff AS (
    SELECT s.*, count(*) OVER (PARTITION BY s.subject_id) AS n_effective,
           row_number() OVER (PARTITION BY s.subject_id ORDER BY s.settled_at DESC) AS rn
    FROM settlements s
    WHERE s.subject_type = 'prediction'
      AND s.id NOT IN (SELECT id FROM superseded)
      AND s.id NOT IN (SELECT id FROM reopened)
), hist AS (
    SELECT subject_id, count(*) AS n_settlement_rows
    FROM settlements WHERE subject_type = 'prediction' GROUP BY subject_id
)
SELECT p.id, p.fixture_id, p.market, p.selection, p.line,
       p.prediction_timestamp, p.decision_as_of, p.quote_timestamp, p.created_at,
       p.ensemble_probability, p.calibrated_probability, p.conservative_probability,
       p.fair_market_probability, p.executable_odds, p.bookmaker, p.edge_pp,
       p.expected_value, p.dqs, p.qss, p.lrs, p.mrs,
       p.research_mode, p.gate_passed, p.model_version_id, p.feature_version,
       p.calibration_version, p.risk_policy_version, p.code_commit,
       mr.name AS model_name, mr.version AS model_version, mr.family AS model_family,
       f.kickoff_utc, f.status AS fixture_status, f.home_goals, f.away_goals,
       c.name AS league, c.country AS league_country, c.validated AS league_validated,
       e.outcome, e.settled_at, e.profit_loss, e.stake, e.taken_odds, e.closing_odds,
       e.clv, e.n_effective, coalesce(h.n_settlement_rows, 0) AS n_settlement_rows
FROM predictions p
JOIN fixtures f ON f.id = p.fixture_id
JOIN competitions c ON c.id = f.competition_id
LEFT JOIN model_registry mr ON mr.id = p.model_version_id
LEFT JOIN eff e ON e.subject_id = p.id AND e.rn = 1
LEFT JOIN hist h ON h.subject_id = p.id
ORDER BY p.prediction_timestamp
"""


def _conninfo() -> str:
    # SQLAlchemy URLs carry a driver suffix that libpq does not understand.
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def extract(out) -> int:
    with psycopg.connect(_conninfo()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(SQL)
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow([d.name for d in cur.description])
            n = 0
            for row in cur:
                writer.writerow(row)
                n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="write CSV here instead of marked stdout")
    args = parser.parse_args(argv)
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            n = extract(fh)
        print(f"wrote {n} predictions to {args.out}", file=sys.stderr)
    else:
        print(BEGIN)
        extract(sys.stdout)
        print(END)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
