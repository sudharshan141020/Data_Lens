"""
Text Field Analysis.

semantic_roles.py already classifies free-text columns (descriptions,
comments, reviews -- either by name or as the fallback for any
moderate-to-high-cardinality string column nothing else claimed), but
nothing in the pipeline actually reads them. This closes that gap with
plain keyword-frequency analysis: lowercase, tokenize, strip a small
stopword list, count -- no external NLP library, no sentiment model, no
LLM call, consistent with the rest of the app's from-scratch, rule-based
approach. It answers "what do people actually talk about in this
column", not "what do they feel about it" -- sentiment would require a
model this app deliberately doesn't use.
"""
import re
from collections import Counter

import pandas as pd

MIN_ENTRIES = 10
MIN_AVG_WORDS = 2.0   # skip columns that are really short codes, not real text
MAX_COLUMNS = 3
TOP_N_WORDS = 15

STOPWORDS = {
    "the", "and", "a", "an", "is", "was", "were", "are", "to", "of", "in", "for",
    "on", "with", "this", "that", "it", "as", "at", "by", "from", "be", "or",
    "but", "not", "have", "has", "had", "i", "you", "he", "she", "we", "they",
    "his", "her", "its", "our", "their", "them", "my", "your", "so", "if",
    "then", "than", "there", "here", "what", "which", "who", "when", "where",
    "how", "all", "some", "no", "yes", "do", "does", "did", "can", "could",
    "will", "would", "should", "just", "also", "very", "too", "up", "out",
    "about", "into", "over", "after", "before", "again", "one", "two",
}

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def _find_text_columns(profile) -> list:
    return [c for c, role in profile.semantic_roles.items() if role == "TEXT"]


def _analyze_column(df: pd.DataFrame, col: str) -> dict:
    values = df[col].dropna().astype(str)
    values = values[values.str.strip() != ""]
    if len(values) < MIN_ENTRIES:
        return {"column": col, "checked": False, "note": f"Only {len(values)} non-empty entries -- not enough to summarize."}

    avg_words = round(values.str.split().apply(len).mean(), 1)
    if avg_words < MIN_AVG_WORDS:
        return {"column": col, "checked": False, "note": "Entries are too short to be meaningful free text (looks more like codes or short labels)."}

    tokenized = values.str.lower().apply(lambda s: [w for w in _WORD_RE.findall(s) if w not in STOPWORDS])

    counter = Counter()
    doc_counter = Counter()  # how many distinct entries mention each word, for a "% of entries" stat
    for tokens in tokenized:
        counter.update(tokens)
        doc_counter.update(set(tokens))

    top_words = [
        {"word": w, "count": c, "pct_of_entries": round(100 * doc_counter[w] / len(values), 1)}
        for w, c in counter.most_common(TOP_N_WORDS)
    ]

    return {
        "column": col,
        "checked": True,
        "entry_count": int(len(values)),
        "avg_word_count": float(avg_words),
        "top_words": top_words,
    }


def analyze_text_fields(df: pd.DataFrame, profile) -> dict:
    columns = _find_text_columns(profile)[:MAX_COLUMNS]
    if not columns:
        return {"available": False, "note": "No free-text columns (descriptions, comments, reviews, etc.) found.", "results": []}

    results = [_analyze_column(df, c) for c in columns]
    if not any(r["checked"] for r in results):
        return {"available": False, "note": results[0].get("note"), "results": results}

    return {"available": True, "note": None, "results": results}
