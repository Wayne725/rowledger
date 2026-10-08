# Changelog

## 0.2.0 — 2026-10-08

Studio preview adds a persistent local browser workspace for recurring one-to-one reconciliation.

- Import CSV/XLSX files with explicit column, worksheet and currency-scale settings; retain exact original bytes.
- Save batches, decisions and change reasons in SQLite; resume after server/browser restarts.
- Reuse an existing source/rule snapshot instead of silently duplicating it or resetting review.
- Inspect and filter source records, with 50-row pages and an explicit synthetic sample.
- Save and withdraw valid manual pairs atomically; reject stale revisions and conflicting simultaneous writes.
- Freeze/reopen a batch with a reason. Closing unresolved work requires acknowledgement and never marks it settled.
- Export a revision-bound ZIP with source files, HTML/Excel/JSON results, complete history and SHA-256 checksums.
- Restrict the server to loopback with Host/Origin checks, a transient session token and CSP.
- Add Studio documentation and persistence/HTTP regression checks. Existing CLI/report behavior remains supported.

This is a single-user local preview. Authentication, cloud deployment, partial payments, allocations and team review are not implemented. The package version advances to 0.2.0; the unchanged reconciliation algorithm retains engine version 0.1.0 and review schema 1.

## 0.1.0 — 2026-10-05

Initial published reconciliation tool: exact one-to-one matching, source provenance, snapshot-bound human review, local HTML/Excel/JSON exports and synthetic fixtures.
