"""
Server-side personal-data guard for share links.

The frontend already stops and asks before it creates a share link. That is a
UI step: anyone who calls POST /api/share directly (a script, an integration, a
bug in some future client) skips it, and a share link is the one place this app
makes data PUBLIC -- anyone holding the link can read the full result, including
the row-level data behind the filters. This puts the check where it cannot be
skipped.

The design problem is that the caller cannot be trusted to say what is
sensitive: a report supplied in the payload can simply be left out. So the
server re-derives what it can from the payload it actually receives:

1. VALUES. The row-level data is scanned with the same detector used at upload
   time. A raw email address in a row is found whatever the caller claims.
2. COLUMN NAMES. Names that suggest personal data (a person identifier, a date
   of birth, a person's name) are flagged -- unless the payload declares that
   column masked. This is the one place the caller's word is accepted, because
   an identifier column is often absent from the rows and its values appear only
   as numbers elsewhere (the at-risk customer list, scatter points), where no
   pattern can be checked.
3. TEXT. Every other string in the result is searched for email addresses,
   US-style SSNs and card numbers: high-precision patterns that cannot be
   masked by column, only acknowledged or removed.

A declared mask never suppresses a VALUE finding: if the rows still contain
email addresses, saying "masked" does not make them go away.

If anything medium or high confidence remains, the share is refused with 409
and a list of column names and kinds. The list never contains a value, because
an error message that echoed an email address would itself be a leak. The
caller can proceed by sending acknowledge_personal_data=true, which is the
explicit, deliberate decision the UI's "Continue without masking" button
records.

What this is not: protection against someone determined to publish data they
already hold -- they could post it anywhere. It makes the API safe by default
against accidents: UI bugs, careless scripts, a future client that forgets the
dialog. Detection is heuristic, so a clean scan is "nothing obvious found", not
"safe to publish".

Scope: only share links. PDF and HTML exports are returned to the same person
who already has the data, so there is nothing public to protect there.
"""
from __future__ import annotations

import re
from typing import Iterator, Optional

import pandas as pd

from app.sensitive_data import classify_header, detect_sensitive_data, _luhn_ok

BLOCKING = {"high", "medium"}
MAX_LEAVES = 200_000          # a defensive cap on how many strings are inspected

# Email detection is deliberately NOT one regex over the whole string. The obvious
# pattern, [A-Za-z0-9._%+-]+@..., is quadratic on a long run of letters with no "@"
# (every start position scans to the end before failing), which would let one hostile
# request freeze the server -- a bad property for a security check. Instead each "@"
# is found in linear time and only a bounded window around it is examined, which keeps
# the whole scan linear in the size of the payload.
_LOCAL_AT_END = re.compile(r"[A-Za-z0-9._%+\-]+$")
_DOMAIN_AT_START = re.compile(r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_LOCAL_WINDOW, _DOMAIN_WINDOW = 64, 255     # RFC limits for a local part and a domain
_MAX_AT_SIGNS = 10_000                      # per string; stop checking a string that is mostly "@"
_SSN_IN_TEXT = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")   # fixed length: linear
_CARD_WHOLE = re.compile(r"^(?:\d[ -]?){13,19}$")                   # bounded repetition: linear
_MAX_CARD_LEN = 40

# parts of the result that are scanned as COLUMNS, or that only carry names
_SKIP_LEAF_KEYS = {"filterable_data", "sensitive_data"}


def _dict(v) -> dict:
    """The payload is built by the caller, so any field can be the wrong type."""
    return v if isinstance(v, dict) else {}


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _leaves(node, path: str = "") -> Iterator[tuple]:
    """(path, string) for every string in the result, skipping the parts that are
    scanned as columns."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _leaves(item, f"{path}[{i}]")
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in _SKIP_LEAF_KEYS and path == "":
                continue
            yield from _leaves(v, f"{path}.{k}" if path else str(k))


def contains_email(text: str) -> bool:
    start, checked = 0, 0
    while checked < _MAX_AT_SIGNS:
        i = text.find("@", start)
        if i < 0:
            return False
        checked += 1
        start = i + 1
        if _LOCAL_AT_END.search(text[max(0, i - _LOCAL_WINDOW):i]) and _DOMAIN_AT_START.match(text[i + 1:i + 1 + _DOMAIN_WINDOW]):
            return True
    return False


def _declared_masked(v2: dict) -> set:
    cols = _list(_dict(v2.get("sensitive_data")).get("columns"))
    return {c.get("column") for c in cols if isinstance(c, dict) and c.get("masked") is True}


def _row_findings(v2: dict) -> list:
    rows = [r for r in _list(_dict(v2.get("filterable_data")).get("rows")) if isinstance(r, dict)]
    if not rows:
        return []
    try:
        report = detect_sensitive_data(pd.DataFrame(rows))
    except Exception:  # a malformed payload must never turn into a 500
        return []
    out = []
    for c in report["columns"]:
        out.append({
            "column": c["column"], "kind": c["kind"], "label": c["label"], "confidence": c["confidence"],
            # match_pct is set only when VALUES matched a pattern; header-only findings have none
            "source": "values" if c.get("match_pct") is not None else "header",
            "maskable": True,
        })
    return out


def _header_findings(v2: dict) -> list:
    names = list(_list(_dict(v2.get("profile")).get("columns")))
    at_risk = _dict(_dict(v2.get("cohorts")).get("at_risk"))
    if at_risk.get("entity_column"):
        names.append(at_risk["entity_column"])
    seen, out = set(), []
    for name in names:
        if not isinstance(name, str) or name in seen:
            continue
        seen.add(name)
        h = classify_header(name)
        if h:
            out.append({"column": name, **h, "source": "header", "maskable": True})
    return out


def _text_findings(v2: dict) -> list:
    hits = {}
    for n, (_path, text) in enumerate(_leaves(v2)):
        if n >= MAX_LEAVES:
            break
        if "email" not in hits and contains_email(text):
            hits["email"] = "email address"
        if "gov_id" not in hits and _SSN_IN_TEXT.search(text):
            hits["gov_id"] = "government ID"
        stripped = text.strip()
        if "card" not in hits and len(stripped) <= _MAX_CARD_LEN and _CARD_WHOLE.match(stripped):
            if _luhn_ok(re.sub(r"[ -]", "", stripped)):
                hits["card"] = "payment card number"
    return [{"column": None, "kind": k, "label": label, "confidence": "high", "source": "text", "maskable": False}
            for k, label in hits.items()]


def scan_share_payload(v2: dict) -> list:
    """Findings that would make this payload unsafe to publish, strongest first.
    Column names and kinds only -- never a value."""
    if not isinstance(v2, dict):
        return []
    masked = _declared_masked(v2)

    merged = {}
    for f in _row_findings(v2) + _header_findings(v2):
        if f["source"] == "header" and f["column"] in masked:
            continue                      # a declared mask suppresses a NAME-based finding only
        prev = merged.get(f["column"])
        # prefer the evidence-backed finding over a name-only one for the same column
        if prev is None or (f["source"] == "values" and prev["source"] != "values"):
            merged[f["column"]] = f
    findings = list(merged.values()) + _text_findings(v2)

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order[f["confidence"]], f["column"] or ""))
    return findings


def blocking_findings(findings: list) -> list:
    return [f for f in findings if f["confidence"] in BLOCKING]


def refusal_message(findings: list) -> str:
    names = [f["column"] if f["column"] else f"{f['label']}s in the result text" for f in findings[:4]]
    more = f" and {len(findings) - 4} more" if len(findings) > 4 else ""
    return ("This result appears to contain personal data (" + ", ".join(names) + more + "), and a share link makes it "
            "readable by anyone who has the link. Mask those columns, or confirm you want to share it as is "
            "(acknowledge_personal_data).")
