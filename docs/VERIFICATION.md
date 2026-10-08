# Verification record

## Studio 0.2.0 — 2026-10-08

48 unittest methods passed on macOS with Python 3.12, pandas 3.0.6 and openpyxl 3.1.5: the original 35 reconciliation checks plus 13 Studio checks. The count is not a coverage percentage.

Studio checks cover persistence across new store instances, duplicate snapshot reuse, changed-source/rule isolation, atomic rejection of invalid/stale decisions, simultaneous revision conflicts, close acknowledgement and freeze/reopen/withdraw, exact-source ZIP hashes and complete history, pagination row conservation, source immutability, explicit sample creation and real HTTP import/review/export. HTTP checks verify loopback binding, Host/Origin/session enforcement, CSP, no CORS and malformed-request rejection.

Browser checks used the packaged synthetic sample. The interface created a 26-row batch, saved the documented pair (6 pairs / 14 attention / 1 human decision), retained it after refresh, rejected closing without acknowledgement, froze the acknowledged batch, reopened it and withdrew the pair (5 / 16 / 0). Reloading the same sample reused the reviewed batch. Narrow-layout inspection showed no document overflow at the browser's reported 433 CSS-pixel width; this is not a device/browser compatibility matrix.

The automation file chooser returned no selected files, and its download event timed out. Therefore end-to-end browser file selection and completed browser ZIP downloads are **not claimed as verified**. HTTP import/export and archive byte/checksum validation passed independently; the UI rejected absent files instead of writing an empty batch. The product remains a preview pending ordinary-browser file-picker/download validation.

The wheel was installed into a separate target directory. From outside the source checkout, its package path was checked, its CLI generated the demo, its packaged Studio HTML/JS/CSS were served, and its HTTP sample/export verified all seven manifest checksums. Runtime dependencies came from the dedicated Python virtual environment; this was not a separate clean installation of every dependency. Publication evidence is recorded in the release notes. All screenshots and fixtures are synthetic. No customer data or transactions were used.

## Original 0.1.0 record

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
