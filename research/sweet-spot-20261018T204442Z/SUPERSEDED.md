This initial audit output is superseded by ../sweet-spot-20261018-verified/REPORT.md.
The initial timestamp check wrongly required decision <= database created_at.
PostgreSQL's created_at default uses transaction start, so legitimate decisions
can occur after created_at while still preceding kickoff. The corrected audit
requires quote <= decision < kickoff and created_at < kickoff independently.
The raw.json snapshot remains the source for the corrected audit.
