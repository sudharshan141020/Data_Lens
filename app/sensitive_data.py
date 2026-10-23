"""
Sensitive-data detection: which columns look like personal data, so the app
can warn BEFORE a share link / HTML / PDF export puts them somewhere public.

Why this exists: a share link carries the full `v2` result, including the
row-level `filterable_data` and any free-text top words. If a file has an
email column or a Customer ID column, that data leaves the user's machine
the moment they click "Copy share link". Nothing used to look for that.

Design rules (same as the rest of the app -- rule-based, no LLM, no new deps):

* Two independent signals per column, and the confidence says which fired:
    - the HEADER looks like a personal-data field ("email", "phone", "ssn"...)
    - the VALUES match a pattern (email regex, Luhn-valid card number...)
  Header + values agreeing = "high". Values alone with a strong pattern
  (email, SSN, Luhn card) = "high". Header alone = "medium" or "low",
  because "Phone Model" or "Address Type" are not personal data.
* Value patterns are only run on text columns. A float column of Sales
  figures must never be flagged as phone numbers just because it has 10
  digits in it -- numeric columns are judged on their header only.
* The report NEVER contains a raw value, not even a masked sample. It is
  stored inside `v2`, which is exactly what gets shared and exported.
* Heuristics, not a compliance tool. A clean report means "nothing obvious
  found", not "this data is safe to publish" -- the UI says so.
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

SAMPLE_SIZE = 2000  # values inspected per column; detection is about rates, not totals

# ---- value patterns (applied to text columns only) -------------------------
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$")
_PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")  # Indian PAN
_AADHAAR_RE = re.compile(r"^\d{4}[ -]?\d{4}[ -]?\d{4}$")  # Indian Aadhaar (12 digits)
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_PHONE_RE = re.compile(r"^\+?\(?\d{1,4}\)?[\s.\-]?\(?\d{2,5}\)?[\s.\-]?\d{3,5}[\s.\-]?\d{0,5}$")
_DATE_LIKE_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")
_PERSON_NAME_RE = re.compile(r"^[A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-\.]+){1,2}$")

# ---- header hints ------------------------------------------------------------
# Each entry: kind -> (label, tokens that must appear as whole words in the header)
_HEADER_RULES = [
    ("email", "email address", ("email", "e-mail", "emailaddress", "mail address")),
    ("phone", "phone number", ("phone", "mobile", "telephone", "cellphone", "contact number", "whatsapp")),
    ("gov_id", "government ID", ("ssn", "social security", "aadhaar", "aadhar", "passport", "tax id", "pan number", "driver license", "drivers license", "licence number", "license number")),
    ("card", "payment card / bank account", ("credit card", "card number", "cardnumber", "debit card", "iban", "account number", "bank account", "cvv", "routing number")),
    ("dob", "date of birth", ("dob", "birth date", "birthdate", "date of birth", "birthday")),
    ("address", "street address", ("street", "address", "street address", "home address", "postcode", "postal code", "zip code", "zipcode")),
    ("ip", "IP address", ("ip address", "ipaddress")),
    ("person_name", "person name", ("first name", "last name", "full name", "surname", "given name", "firstname", "lastname", "fullname", "forename", "customer name", "patient name", "employee name", "student name", "contact name", "client name", "member name", "user name", "username")),
]

# Identifier columns that point at a PERSON (vs. a row/order/product id, which
# is not personal data on its own).
_PERSON_ID_WORDS = {
    "customer", "patient", "user", "employee", "member", "student", "person",
    "client", "passenger", "subscriber", "visitor", "account", "staff", "worker",
    "applicant", "donor", "resident", "policyholder", "cardholder", "driver",
}
_ID_WORDS = {"id", "ids", "no", "number", "code", "key", "uid", "guid", "uuid"}

_LABELS = {k: lbl for k, lbl, _ in _HEADER_RULES}
_LABELS["person_id"] = "person identifier"
_LABELS["email"] = "email address"
_LABELS["ip"] = "IP address"

# Kinds whose VALUE pattern alone is strong enough for "high".
_STRONG_VALUE_KINDS = {"email", "gov_id", "card"}
_RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_CONF_ORDER = {"low": 1, "medium": 2, "high": 3}


def _article(label: str) -> str:
    return "an" if label[:1].lower() in "aeiou" else "a"


def _words(header: str) -> list[str]:
    """Header -> lower-case word list. Splits snake_case, kebab-case, spaces
    and camelCase ("CustomerID" -> customer id)."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(header))
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def _header_has_phrase(words: list[str], phrase: str) -> bool:
    target = phrase.lower().replace("-", " ").split()
    if len(target) == 1:
        # also allow the glued form ("emailaddress" in the word list)
        return target[0] in words
    n = len(target)
    return any(words[i:i + n] == target for i in range(len(words) - n + 1))


def _header_kind(header: str) -> Optional[str]:
    words = _words(header)
    if not words:
        return None
    # "Phone Model", "Address Type", "Email Count": the hint word describes
    # something ABOUT the field rather than being the field.
    if words[-1] in {"model", "type", "count", "status", "flag", "domain", "provider", "brand", "plan", "usage", "year"}:
        return None
    for kind, _label, phrases in _HEADER_RULES:
        if any(_header_has_phrase(words, p) for p in phrases):
            return kind
    # <person word> + <id word>, e.g. "Customer ID", "patient_no", "EmployeeCode"
    if words[-1] in _ID_WORDS and any(w in _PERSON_ID_WORDS for w in words[:-1]):
        return "person_id"
    if "id" in words and any(w in _PERSON_ID_WORDS for w in words):
        return "person_id"
    return None


def _header_only_confidence(kind: str) -> str:
    """A header hint with no value evidence: medium for fields that are almost
    always personal, low for words that often are not ("address", "zip", "ip")."""
    return "medium" if kind in {"email", "phone", "gov_id", "card", "person_id", "dob", "person_name"} else "low"


def classify_header(name: str) -> Optional[dict]:
    """What a column NAME alone suggests, for callers that have names but no
    values (the share guard sees a result's column list, not the file)."""
    kind = _header_kind(name)
    if kind is None:
        return None
    return {"kind": kind, "label": _LABELS[kind], "confidence": _header_only_confidence(kind)}


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _is_card(s: str) -> bool:
    digits = re.sub(r"[ -]", "", s)
    return digits.isdigit() and 13 <= len(digits) <= 19 and _luhn_ok(digits)


def _is_phone(s: str) -> bool:
    if _DATE_LIKE_RE.match(s) or not _PHONE_RE.match(s):
        return False
    n = len(re.sub(r"\D", "", s))
    return 7 <= n <= 15


_VALUE_TESTS = {
    "email": lambda s: bool(_EMAIL_RE.match(s)),
    "gov_id": lambda s: bool(_SSN_RE.match(s) or _PAN_RE.match(s) or _AADHAAR_RE.match(s)),
    "card": _is_card,
    "ip": lambda s: bool(_IPV4_RE.match(s)),
    "phone": _is_phone,
}


def _text_sample(series: pd.Series) -> Optional[pd.Series]:
    """Non-null string values (capped), or None for non-text columns."""
    if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return None
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return None
    return s.head(SAMPLE_SIZE)


def _rate(sample: pd.Series, test) -> float:
    return float(sample.map(test).mean())


def _classify_column(name: str, series: pd.Series) -> Optional[dict]:
    header_kind = _header_kind(name)
    sample = _text_sample(series)
    nonnull = int(series.notna().sum())
    unique_pct = round(float(series.nunique(dropna=True)) / nonnull * 100, 1) if nonnull else 0.0

    # 1) value patterns (text columns only)
    value_kind, value_rate = None, 0.0
    if sample is not None:
        for kind, test in _VALUE_TESTS.items():
            r = _rate(sample, test)
            if r >= 0.5 and r > value_rate:
                value_kind, value_rate = kind, r
        # Aadhaar-style 12-digit and phone patterns overlap on digit-only
        # columns; the stricter (gov_id) one is tested first by dict order
        # only when rates tie, so resolve explicitly: prefer the header.
        if value_kind in {"phone", "gov_id"} and header_kind in {"phone", "gov_id"}:
            value_kind = header_kind

    # 2) person-name by value shape (only trusted with a name-ish header or
    #    high cardinality, so "Product Name" / "City" never trip it)
    if value_kind is None and sample is not None and header_kind in {None, "person_name"}:
        words = _words(name)
        nameish = "name" in words and not any(w in words for w in (
            "product", "item", "company", "brand", "city", "country", "state", "category",
            "region", "store", "file", "campaign", "project", "team", "department", "school", "hospital",
        ))
        if nameish or header_kind == "person_name":
            r = _rate(sample, lambda s: bool(_PERSON_NAME_RE.match(s)))
            if r >= 0.6 and unique_pct >= 40:
                value_kind, value_rate = "person_name", r

    if value_kind is None and header_kind is None:
        return None

    # 3) combine the two signals
    if value_kind and header_kind and value_kind == header_kind:
        kind, conf = value_kind, "high"
        reason = f"column name and {value_rate * 100:.0f}% of values both look like {_article(_LABELS[kind])} {_LABELS[kind]}"
    elif value_kind:
        kind = value_kind
        conf = "high" if kind in _STRONG_VALUE_KINDS and value_rate >= 0.8 else "medium"
        reason = f"{value_rate * 100:.0f}% of values match the pattern of {_article(_LABELS[kind])} {_LABELS[kind]}"
    else:
        kind = header_kind
        conf = _header_only_confidence(kind)
        if sample is None and kind in {"email", "phone", "card"} and not pd.api.types.is_numeric_dtype(series):
            return None  # an empty/odd column that only has a header hint -> nothing to share
        reason = f"column name looks like {_article(_LABELS[kind])} {_LABELS[kind]}"
        if kind == "person_id":
            reason += f" ({unique_pct:.0f}% distinct values)"

    return {
        "column": str(name),
        "kind": kind,
        "label": _LABELS[kind],
        "confidence": conf,
        "match_pct": round(value_rate * 100, 1) if value_kind else None,
        "unique_pct": unique_pct,
        "numeric": bool(pd.api.types.is_numeric_dtype(series)),
        "reason": reason,
    }


def detect_sensitive_data(df: pd.DataFrame) -> dict:
    """Scan every column. Returns a report that is safe to embed in a shared
    result: column names, kinds, rates -- never a raw value."""
    findings = []
    for name in df.columns:
        try:
            f = _classify_column(name, df[name])
        except Exception:  # one odd column must never break the analysis
            f = None
        if f:
            findings.append(f)

    findings.sort(key=lambda f: (-_CONF_ORDER[f["confidence"]], f["column"]))
    risk = "none"
    for f in findings:
        risk = max(risk, f["confidence"], key=_RISK_ORDER.get)

    if findings:
        names = ", ".join(f["column"] for f in findings[:4]) + ("..." if len(findings) > 4 else "")
        summary = (
            f"{len(findings)} column{'s' if len(findings) != 1 else ''} may contain personal data ({names}). "
            "A share link, HTML or PDF export can carry these values."
        )
    else:
        summary = "No obvious personal-data columns found. This is a heuristic check, not a guarantee."

    return {
        "scanned_columns": int(len(df.columns)),
        "rows_scanned": int(min(len(df), SAMPLE_SIZE)),
        "has_sensitive": bool(findings),
        "risk": risk,
        "columns": findings,
        "summary": summary,
    }
