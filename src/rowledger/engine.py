import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal

from .readers import Source, read_source
from .rules import Rules

SCHEMA_VERSION = 1
ENGINE_VERSION = "0.1.0"


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _rows(source: Source, side: str, rules: Rules):
    columns = getattr(rules, side)
    rows = []
    for record_no, raw in enumerate(source.frame.to_dict("records"), 1):
        errors = list(source.cell_errors.get(record_no, []))
        key = raw[columns.key].strip() if rules.trim_keys else raw[columns.key]
        currency = raw[columns.currency].strip()
        amount = raw[columns.amount].strip()
        minor = None
        if not key:
            errors.append("Missing identifier.")
        if currency not in rules.minor_units:
            errors.append("Currency is missing or not configured.")
        if not re.fullmatch(r"\d{1,18}(?:\.\d{1,6})?", amount, flags=re.ASCII):
            errors.append("Amount must be a nonnegative plain decimal with at most 18 integer digits.")
        elif currency in rules.minor_units:
            scale = rules.minor_units[currency]
            scaled = Decimal(amount) * (10 ** scale)
            if scaled != scaled.to_integral_value():
                errors.append(f"Amount has more than {scale} meaningful decimal places.")
            else:
                minor = str(int(scaled))
        rows.append({"row_id": f"{side}:{record_no}", "side": side, "record": record_no,
                     "source": source.name, "sheet": source.sheet,
                     "location": f"row {record_no + 1}" if source.sheet else f"record {record_no}",
                     "raw": raw, "key": key, "currency": currency, "amount": amount,
                     "amount_minor": minor, "errors": errors, "status": "invalid" if errors else "unmatched",
                     "explanation": "; ".join(errors), "partner_id": None, "review": None})
    return rows


def _set_status(rows, status, explanation):
    for row in rows:
        if row["errors"]:
            continue
        row["status"] = status
        row["explanation"] = explanation


def summarize(rows):
    totals = {}
    for side in ("orders", "payments"):
        side_rows = [row for row in rows if row["side"] == side]
        sums = defaultdict(int)
        for row in side_rows:
            if not row["errors"] and row["amount_minor"] is not None:
                sums[row["currency"]] += int(row["amount_minor"])
        totals[side] = {"records": len(side_rows), "statuses": dict(Counter(row["status"] for row in side_rows)),
                        "valid_amount_minor": {key: str(value) for key, value in sorted(sums.items())}}
    return {"rows": len(rows), "matched_pairs": sum(row["side"] == "orders" and row["status"] in
            ("matched", "manual_matched") for row in rows),
            "needs_attention": sum(row["status"] not in ("matched", "manual_matched") for row in rows),
            "sources": totals}


def reconcile(orders_path, payments_path, rules: Rules | None = None):
    rules = rules or Rules()
    sources = {side: read_source(path, getattr(rules, side))
               for side, path in (("orders", orders_path), ("payments", payments_path))}
    rows = [row for side, source in sources.items() for row in _rows(source, side, rules)]
    groups = defaultdict(list)
    for row in rows:
        if row["key"]:
            groups[row["key"]].append(row)
    for key, group in groups.items():
        orders = [row for row in group if row["side"] == "orders"]
        payments = [row for row in group if row["side"] == "payments"]
        if len(orders) > 1 or len(payments) > 1:
            _set_status(group, "duplicate_key", f"This key has {len(orders)} order and {len(payments)} payment records; no pairing was guessed.")
        elif any(row["errors"] for row in group):
            _set_status(group, "blocked_invalid", "A record with the same key is invalid; automatic matching is blocked.")
        elif not orders or not payments:
            _set_status(group, "unmatched", "No record with this exact key exists on the other side.")
        elif orders[0]["currency"] != payments[0]["currency"]:
            _set_status(group, "currency_mismatch", "Exact key found, but currencies differ; no currency conversion was attempted.")
        elif orders[0]["amount_minor"] != payments[0]["amount_minor"]:
            _set_status(group, "amount_mismatch", "Exact key and currency found, but amounts differ; no tolerance was applied.")
        else:
            _set_status(group, "matched", "One record per side; exact key, currency and minor-unit amount agree.")
            orders[0]["partner_id"] = payments[0]["row_id"]
            payments[0]["partner_id"] = orders[0]["row_id"]
    metadata = {side: source.metadata() for side, source in sources.items()}
    identity = {"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
                "rules": rules.to_dict(), "sources": metadata}
    run_id = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    return {**identity, "run_id": run_id, "rows": rows, "summary": summarize(rows),
            "profiles": {side: source.profile() for side, source in sources.items()}, "decisions": []}


def apply_review(result, document):
    if not isinstance(document, dict) or set(document) != {"schema_version", "run_id", "decisions"}:
        raise ValueError("Review must contain exactly schema_version, run_id and decisions.")
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported review schema.")
    if document["run_id"] != result["run_id"]:
        raise ValueError("Stale review: input files, file names, sheets or rules have changed.")
    decisions = document["decisions"]
    if not isinstance(decisions, list) or len(decisions) > len(result["rows"]):
        raise ValueError("Review decisions must be a bounded list.")
    updated = deepcopy(result)
    by_id = {row["row_id"]: row for row in updated["rows"]}
    claimed = set()
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != {"order_row_id", "payment_row_id", "reviewer", "reason"}:
            raise ValueError("Each decision needs order_row_id, payment_row_id, reviewer and reason.")
        for field, limit in (("reviewer", 100), ("reason", 1_000)):
            text = decision[field]
            if (not isinstance(text, str) or not 1 <= len(text.strip()) <= limit
                    or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", text)):
                raise ValueError(f"{field} must be nonempty text, at most {limit} characters.")
        ids = [decision["order_row_id"], decision["payment_row_id"]]
        if any(not isinstance(row_id, str) or row_id not in by_id for row_id in ids):
            raise ValueError("Decision references an unknown source record.")
        pair = [by_id[row_id] for row_id in ids]
        if pair[0]["side"] != "orders" or pair[1]["side"] != "payments":
            raise ValueError("Decision must pair an order with a payment.")
        if any(row_id in claimed for row_id in ids):
            raise ValueError("A source record cannot be used by two review decisions.")
        if any(row["errors"] or row["status"] in ("matched", "manual_matched") for row in pair):
            raise ValueError("Invalid or already matched records cannot be manually paired.")
        if pair[0]["currency"] != pair[1]["currency"] or pair[0]["amount_minor"] != pair[1]["amount_minor"]:
            raise ValueError("Manual pairs must have equal currency and exact amount.")
        claimed.update(ids)
        for row, partner in ((pair[0], pair[1]), (pair[1], pair[0])):
            row.update(status="manual_matched", partner_id=partner["row_id"], review=dict(decision),
                       explanation="Human-selected pair with exact amount and currency; original keys are preserved.")
    updated["decisions"].extend(deepcopy(decisions))
    updated["summary"] = summarize(updated["rows"])
    return updated
