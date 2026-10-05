# Verification record

Date: 2026-10-05 · Version: 0.1.0

## Automated behavior checks

35 unittest test methods passed locally on macOS, Python 3.12.14, pandas 2.2.3 and openpyxl 3.1.5. The suite includes subcases for invalid money, review constraints and configuration errors. Run `python -m unittest discover -s tests -v` to reproduce; test count is not a coverage percentage.

Independent demo expectations: 13 order records plus 13 payment records, 5 automatic pairs, 16 attention records. Matching the documented typo manually yields 6 pairs and 14 attention records. Input identifiers, source record counts and original file bytes are checked.

Other boundaries: exact large-number amounts; duplicate keys and invalid counterparts; stale input/rule/filename review rejection; no reused or invalid manual pair; atomic review validation; duplicate headers; malformed CSV; multiline record numbering; XLSX numeric identifiers/formulas/multiple sheets/expansion limits; literal formula-looking text in Excel exports; HTML payload escaping; empty tables; output checksums; preservation of existing output directories.

## Package and browser checks

- Built a wheel, installed it into a separate target directory and ran its console command from outside the source checkout using the installed package. Packaged examples and report assets were present. Runtime dependencies came from the existing Python runtime; this was not an isolated installation of every dependency from scratch.
- Opened the generated report in the Codex in-app browser. Selected source records, completed the documented manual pair and observed 6 matched pairs, 14 attention records and one human decision.
- Copied the actual browser-generated Review JSON from the visible fallback and applied it through the CLI to the original synthetic inputs. The final report reproduced those counts.
- The browser download event did not return through the automation interface, so file download completion is not claimed as verified. The report exposes the same JSON as a copy-and-save fallback.
- Recorded the default desktop screenshot. Console inspection returned no warnings or errors at that check. Mobile, Safari and Windows Excel are not covered by these local checks.

## Published repository checks

- The public repository's complete 24-file tree matched the locally tested tree byte for byte (Git tree `157c1ca1542a4897a387edfdb6759dc0255e125d`). Only synthetic examples and generated synthetic screenshots were published.
- [GitHub Actions run 1](https://github.com/Wayne725/rowledger/actions/runs/37265289758), commit `d2c6be1a03290f51d726941ec211cc2c51bd2531`, passed on Ubuntu for Python 3.11, 3.12 and 3.13. Each job installed the package from the published source, ran the 35-test suite and generated the demo successfully.

## Limits

Only synthetic fixtures were used. No customer data, financial posting, actual payments or accounting certification was involved. Fingerprints bind reviews to input snapshots; they are not signatures or verified reviewer identities. CSV record references are not physical line numbers. Excel exports preserve input values as text, not workbook styling. See README for the supported one-to-one matching scope.
