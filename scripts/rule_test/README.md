# Selection-rule test

Tests a forecast selection rule against archived, settled forecasts and
compares it with three looser groups:

| Group | Filter |
|---|---|
| A | all eligible priced forecasts |
| B | P ≥ 70% |
| C | P ≥ 70% and EV > 0 |
| D | P ≥ 70% and EV > 0 and QSS ≥ 82 (the rule) |

The report also shows C∖D (the forecasts the QSS gate removes), and breaks
each group down by market, league, model version and kickoff month.
Thresholds are flags (`--p-min`, `--ev-min`, `--qss-min`), so other rules can
be tested the same way.

## What it guards against

- **Timing:** it excludes a forecast whose quote is after `decision_as_of`,
  whose decision or prediction time is after kickoff, or which was archived
  after kickoff.
- **Missing fields:** it reports how often each field is missing.
  Probability, odds and EV are required. A missing QSS fails the QSS gate
  and is counted separately.
- **Repeated picks:** only the first qualifying forecast per (fixture,
  market, selection, line) counts. The ROI confidence intervals resample
  whole matches, so correlated picks on one match are not treated as
  independent evidence.
- **Settlement:** it uses the effective settlement only (not superseded, not
  reopened). It drops rows whose recorded result disagrees with the final
  score, or that were settled before the fixture finished.
- **Live vs research:** research/shadow rows are excluded by default.
  `--include-research` adds them for a clearly labelled secondary view.

## Running it

`extract.py` opens a **read-only** connection. `analyze.py` needs only the
standard library. Keep extracts and reports outside the repository (or in the
git-ignored `scripts/rule_test/out/`), because they contain archive data.

### Against the local dev database

```powershell
New-Item -ItemType Directory -Force scripts\rule_test\out | Out-Null
.venv\Scripts\python.exe scripts\rule_test\extract.py --out scripts\rule_test\out\dev.csv
.venv\Scripts\python.exe scripts\rule_test\analyze.py scripts\rule_test\out\dev.csv --label "dev" --out scripts\rule_test\out\dev_report.md
```

### Against production (read-only, via Railway SSH)

The production database is only reachable from inside Railway. This pipes
`extract.py` into the `qwantej-api` container's Python and cuts the CSV out
of the session output. The command only reads data, but it is still
production access, so run it deliberately:

```powershell
New-Item -ItemType Directory -Force scripts\rule_test\out | Out-Null
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("scripts\rule_test\extract.py")); $raw = @(railway ssh --service qwantej-api -- sh -c "echo $b64 | base64 -d | python"); "railway exit: $LASTEXITCODE, lines: $($raw.Count)"; $i = [array]::IndexOf($raw,'===CSV-BEGIN==='); $j = [array]::IndexOf($raw,'===CSV-END==='); if ($i -lt 0 -or $j -le $i) { "Extract markers not found:"; $raw | Select-Object -First 15 } else { $raw[($i+1)..($j-1)] | Out-File -Encoding utf8 scripts\rule_test\out\prod.csv; "Wrote $($j-$i-1) lines" }
.venv\Scripts\python.exe scripts\rule_test\analyze.py scripts\rule_test\out\prod.csv --label "production" --out scripts\rule_test\out\prod_report.md
```

Add `--include-research` for the secondary view that includes shadow rows.

## Reading the report

- **Evidence label:** under 30 picks is *insufficient*, 30–99 is *thin*,
  100 or more is *usable*. Do not act on a cell below *usable*.
- **Cal gap:** hit rate minus mean predicted probability. A negative value
  means the model is overconfident.
- **Claimed EV vs flat ROI:** a large positive claimed EV with a flat or
  negative ROI points to price or calibration problems, not an edge.

Tests: `pytest tests/test_rule_test.py`.
