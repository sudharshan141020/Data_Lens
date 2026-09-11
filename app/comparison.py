"""
File-to-File Comparison.

Different from the existing /api/analyze-combined, which merges two
files' ROWS into one dataset (e.g. two regions' exports of the same
period). This compares two SEPARATE analyses -- e.g. this month's export
vs. last month's, or two different regions' full exports -- and reports
what changed between them: KPI deltas, which correlations appeared,
disappeared, or flipped sign, and how data quality compares.

Deliberately a pure post-processing step: it takes two already-computed
_run_v2_pipeline() results and diffs them, rather than introducing any
new analysis logic of its own. Everything it reports was already
computed, independently, by the exact same pipeline every single-file
upload goes through -- this module's only job is matching keys between
the two results and computing deltas.
"""
CURRENCY_HINTS = ["sale", "revenue", "price", "cost", "amount", "fare", "profit", "value", "income", "pay", "earning", "billing", "salary"]


def _pct_change(a, b):
    if a in (None, 0) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return None
    return round(100 * (b - a) / a, 1)


def _compare_kpis(kpis_a: dict, kpis_b: dict) -> list:
    shared = sorted(set(kpis_a) & set(kpis_b))
    rows = []
    for key in shared:
        val_a, val_b = kpis_a[key], kpis_b[key]
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            rows.append({
                "metric": key,
                "value_a": val_a,
                "value_b": val_b,
                "delta": round(val_b - val_a, 2),
                "pct_change": _pct_change(val_a, val_b),
            })
    return rows


def _compare_correlations(pairs_a: list, pairs_b: list) -> dict:
    """pairs_a/pairs_b are the serialized correlation_center pair dicts
    (col1, col2, r, significant, ...). Matched as an unordered (col1, col2)
    pair, since correlation is symmetric but column order in the two
    datasets might not match."""
    def key(p):
        return tuple(sorted([p["col1"], p["col2"]]))

    map_a = {key(p): p for p in pairs_a if p}
    map_b = {key(p): p for p in pairs_b if p}

    changed = []
    for k in sorted(set(map_a) & set(map_b)):
        pa, pb = map_a[k], map_b[k]
        sign_flipped = (pa["r"] > 0) != (pb["r"] > 0) and abs(pa["r"]) > 0.1 and abs(pb["r"]) > 0.1
        changed.append({
            "col1": k[0], "col2": k[1],
            "r_a": pa["r"], "r_b": pb["r"],
            "delta": round(pb["r"] - pa["r"], 3),
            "sign_flipped": sign_flipped,
        })

    only_a = [{"col1": k[0], "col2": k[1], "r": map_a[k]["r"]} for k in sorted(set(map_a) - set(map_b))]
    only_b = [{"col1": k[0], "col2": k[1], "r": map_b[k]["r"]} for k in sorted(set(map_b) - set(map_a))]

    return {"changed": changed, "only_in_a": only_a, "only_in_b": only_b}


def compare_results(result_a: dict, result_b: dict, name_a: str, name_b: str) -> dict:
    profile_a, profile_b = result_a["v2"]["profile"], result_b["v2"]["profile"]
    domain_mismatch = profile_a["domain"] != profile_b["domain"]

    kpi_deltas = _compare_kpis(result_a.get("kpis") or {}, result_b.get("kpis") or {})
    kpi_deltas.sort(key=lambda r: -abs(r["pct_change"]) if r["pct_change"] is not None else 0)

    corr_a = result_a["v2"]["correlation_center"]["pairs"]
    corr_b = result_b["v2"]["correlation_center"]["pairs"]
    correlation_diff = _compare_correlations(corr_a, corr_b)

    return {
        "name_a": name_a,
        "name_b": name_b,
        "domain_a": profile_a["domain"],
        "domain_b": profile_b["domain"],
        "domain_mismatch": domain_mismatch,
        "row_count_a": profile_a["row_count"],
        "row_count_b": profile_b["row_count"],
        "data_quality_a": result_a["v2"]["data_quality"]["overall_quality_score"],
        "data_quality_b": result_b["v2"]["data_quality"]["overall_quality_score"],
        "kpi_deltas": kpi_deltas,
        "correlation_diff": correlation_diff,
    }
