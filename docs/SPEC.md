# RowLedger 0.1.0 acceptance contract

Date: 2026-10-05

## Problem and boundary

Compare one order table and one payment table locally. Preserve all accepted source records, explain every result, and permit human pair selection only with exact financial agreement. The deliverable is an installable Python package and an offline interactive report. It does not modify originals or post transactions.

## Requirements

1. Accept UTF-8 CSV and XLSX with explicit key/amount/currency mappings; reject duplicate headers and malformed rows.
2. Preserve string identifiers, including leading zeros and literal NA; never infer zeros from numeric XLSX identifiers.
3. Use exact nonnegative decimal money and configured currency scales. Invalid values are retained as invalid rows.
4. Automatic matching requires exactly one record per side with an exact key, equal currency and equal amount. Duplicate groups and invalid counterparts block automatic matching.
5. Each accepted source record appears once. Source filenames, hashes, CSV record numbers or XLSX sheet/row numbers and original fields remain inspectable.
6. A human review may pair two unresolved valid records only if amount/currency agree. Reviewer/reason are mandatory; source records cannot be reused. Original keys remain unchanged.
7. Reject review decisions when the input byte hashes, filenames, sheets, rules or engine version differ. Reviews are not authenticated signatures.
8. Export self-contained HTML, JSON, literal-text XLSX, a review template and checksums. Never overwrite an existing output directory.
9. HTML must not interpret input data as markup/scripts or contact external services. Use textContent for input-derived display values. XLSX exports must not activate input formulas.
10. Provide a synthetic demo with independent expectations: 26 input records, 5 matched pairs, 16 attention records; the documented manual pair yields 6 pairs and 14 attention records.
11. Package assets and examples so the installed wheel can run outside the source checkout. Include English and Traditional Chinese instructions and automated tests.

## Limits and deliberate omissions

One-to-one reconciliation only. No fuzzy matching, refunds, partial/split settlement, FX, tax judgement, hosted service, AI extraction or automated bookkeeping. File and row limits are documented in README. Matching-column formulas and numeric identifiers in XLSX are reported as invalid; CSV text formulas are preserved and exported as literal strings. Source workbooks are not reconstructed; exported original tables preserve cell values as text, not input styles or formulas as executable expressions.

## Development standards

Python, snake_case, pandas for table/profile handling, Decimal/integer minor units for money, small modules at input/rule/engine/export boundaries. Avoid speculative integrations and broad exception swallowing. Tests assert externally meaningful behavior and adversarial data boundaries.

## Studio 0.2.0 extension — 2026-10-08

The unchanged matching contract above also applies to Studio. The package adds a local, single-user persistence layer; the reconciliation engine retains version 0.1.0 and review schema 1.

1. Import two files with explicit rules through a loopback browser interface. Preserve exact input bytes and immutable base results. Rejected imports do not create a partial batch.
2. Persist batches in SQLite. Identical input bytes, filenames, rules and engine identity reuse the existing batch without clearing its decisions or title.
3. Reconstruct the current result from the immutable base and the current full decision document. Save the change and its event in one database transaction; invalid changes leave both untouched.
4. Require an exact batch revision for decision/state updates and export. Concurrent updates from the same revision permit one commit; stale revisions receive HTTP 409.
5. Withdrawing a manual pair restores the underlying unresolved statuses. Changes require an actor and reason; historical before/after decisions are included in export.
6. Closing freezes changes without resolving records. Unresolved work requires explicit acknowledgement. Reopening requires a reason; both events retain the corresponding unresolved row IDs.
7. Search/filter by source and result, with 50 records per page. UI history shows the most recent 100 events; export includes all events.
8. Export a consistent revision containing original source bytes, result files, state and all history. Hash all ZIP members other than the manifest. ZIPs are records, not workspace restore archives.
9. Bind only to 127.0.0.1; validate exact Host, same-origin browser requests and a transient API token. Serve only fixed UI assets; do not expose a filesystem tree, enable CORS or import third-party frontend assets.
10. Package the Studio UI and provide an explicit synthetic sample without requiring private data. Saved decisions survive browser and server restarts; unsubmitted UI text need not persist.

The database is unencrypted. Actors are self-reported and the local history is mutable by anyone with filesystem access. This is not multiuser authentication, a tamper-proof audit trail, an accounting ledger, a production internet server or a hostile-file sandbox. Restore requires a copy of the complete workspace taken while the server is stopped. Allocation/partial settlement and team workflows remain future work.
