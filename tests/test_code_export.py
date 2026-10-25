"""app.code_export -- the "show the code" script.

The generated script is only worth shipping if it gives the SAME numbers as
the dashboard, so these tests run it: load the real file, exec the script, and
compare every analysis in RESULTS against what the app computed (including the
float32 precision the app's loader uses). If the generator and executor_v2.py
ever drift apart, that is what fails."""
import ast
import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.code_export import generate_script, SUPPORTED_TYPES

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = [
    ROOT / "app/static/demo-sales-data.csv",
    ROOT / "app/static/sample-healthcare-data.csv",
    ROOT / "app/static/sample-manufacturing-data.csv",
    ROOT / "frontend/src/test/fixtures/analysis.csv",
]


def _analyze(path: Path):
    from app.main import _full_analyze_from_df, _load_dataframe
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _full_analyze_from_df(_load_dataframe(path.name, path.read_bytes()))["v2"]


def _run(script: str, path: Path, tmp_path, monkeypatch, name=None):
    (tmp_path / (name or path.name)).write_bytes(path.read_bytes())
    monkeypatch.chdir(tmp_path)
    ns = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(compile(script, "<generated>", "exec"), ns)
    return ns


def _close(a, b, tol=1e-6):
    if a is None or b is None:
        return a is None and b is None or (a is None and pd.isna(b)) or (b is None and pd.isna(a))
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


def _compare(a: dict, res):
    """Assert one analysis from the app equals the script's result."""
    t, data = a["type"], a["data"]
    if t == "trend":
        data = [d for d in data if not d.get("is_forecast")]   # the app appends forecast months; the script is history only
        assert [d["label"] for d in data] == [str(i) for i in res.index]
        assert all(_close(d["value"], v) for d, v in zip(data, res.values))
    elif t in ("distribution_count", "distribution_sum"):
        assert [d["label"] for d in data] == [str(i) for i in res.index]
        assert all(_close(d["value"], v) for d, v in zip(data, res.values))
    elif t == "histogram":
        assert [d["value"] for d in data] == [int(c) for c in res["count"]]
    elif t == "pivot":
        for cell in data:
            got = res.loc[[i for i in res.index if str(i) == cell["y"]][0], [c for c in res.columns if str(c) == cell["x"]][0]]
            assert _close(cell["value"], None if pd.isna(got) else got)
    elif t == "correlation":
        assert round(float(res), 3) == a["r"]
    elif t == "correlation_matrix":
        for cell in data:
            assert _close(cell["value"], res.loc[cell["x"], cell["y"]], 1e-6)
    elif t == "outlier":
        for k in ("min", "q1", "median", "q3", "max", "lower_fence", "upper_fence"):
            assert _close(data[k], res[k]), k
        assert data["outlier_count"] == res["outlier_count"]
    else:  # pragma: no cover
        raise AssertionError(f"unhandled type {t}")


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_every_reproduced_analysis_matches_what_the_app_computed(path, tmp_path, monkeypatch):
    v2 = _analyze(path)
    ns = _run(generate_script(path.name, v2), path, tmp_path, monkeypatch)
    results = ns["RESULTS"]

    expected = [a for a in v2["all_analyses"] if a["type"] in SUPPORTED_TYPES and a["id"] in results]
    assert len(expected) >= 3, "the check would be vacuous"
    for a in expected:
        _compare(a, results[a["id"]])


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_headline_numbers_match_the_app_s_confidence_interval_point_estimates(path, tmp_path, monkeypatch):
    v2 = _analyze(path)
    ns = _run(generate_script(path.name, v2), path, tmp_path, monkeypatch)
    intervals = v2["confidence_intervals"]["intervals"]
    assert intervals
    for i in intervals:
        # the app rounds its point estimates to 2 decimals
        assert round(float(ns["headline"][i["measure"]]), 2) == pytest.approx(i["point_estimate"], abs=0.011, rel=1e-6), i["measure"]


def test_analyses_built_from_derived_columns_are_left_out_and_the_header_says_so():
    v2 = _analyze(SAMPLES[0])
    script = generate_script("demo-sales-data.csv", v2)
    ids = {a["id"] for a in v2["all_analyses"]}
    assert "cohort_retention" in ids and "cohort_retention" not in script
    assert "not in this script" in script
    assert "forecasts" in script


def test_key_analyses_come_first_and_are_labelled():
    v2 = _analyze(SAMPLES[0])
    script = generate_script("demo-sales-data.csv", v2)
    assert script.index("# %% 5. Key analyses") < script.index("# %% 6. More analyses")
    first_key = v2["top_analyses"][0]["title"]
    assert script.index(first_key) < script.index("# %% 6. More analyses")


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------
def test_active_filters_change_exactly_the_charts_the_dashboard_filters(tmp_path, monkeypatch):
    path = SAMPLES[3]
    v2 = _analyze(path)
    rows = v2["filterable_data"]["rows"]
    filters = {"dateColumn": "Order Date", "dateFrom": "2024-02-01", "dateTo": "2024-05-31",
               "dimensionFilters": {"Region": ["West", "East"]}}
    ns = _run(generate_script(path.name, v2, filters), path, tmp_path, monkeypatch)

    # independent re-implementation of filterUtils.applyFilters on the rows the browser holds
    def keep(r):
        d = r.get("Order Date")
        if not d or d < filters["dateFrom"] or d > filters["dateTo"]:
            return False
        return r["Region"] in filters["dimensionFilters"]["Region"]
    kept = [r for r in rows if keep(r)]
    assert 0 < len(kept) < len(rows)
    assert len(ns["df_filtered"]) == len(kept)

    by_region = {}
    for r in kept:
        by_region.setdefault(r["Region"], []).append(r["Sales"])
    res = ns["RESULTS"]["sum_region"]
    assert {k: round(float(v), 2) for k, v in res.items()} == {k: round(sum(v), 2) for k, v in by_region.items()}

    # charts the dashboard does NOT filter keep using the full data, as the app does
    assert len(ns["df"]) == len(rows)
    full_hist = next(a for a in v2["all_analyses"] if a["id"] == "hist_sales")
    assert [d["value"] for d in full_hist["data"]] == [int(c) for c in ns["RESULTS"]["hist_sales"]["count"]]
    assert "(filtered)" in generate_script(path.name, v2, filters)


def test_with_no_filters_the_script_says_so_and_uses_the_full_data(tmp_path, monkeypatch):
    path = SAMPLES[3]
    v2 = _analyze(path)
    script = generate_script(path.name, v2, {"dimensionFilters": {"Region": []}})
    assert "No filters were active" in script
    ns = _run(script, path, tmp_path, monkeypatch)
    assert len(ns["df_filtered"]) == len(ns["df"])


# ---------------------------------------------------------------------------
# loading and cleaning
# ---------------------------------------------------------------------------
def test_mostly_numeric_columns_with_stray_placeholders_are_coerced_like_the_app(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    csv = src / "messy.csv"
    csv.write_text("Region,Sales\n" + "\n".join(f"{'East' if i % 2 else 'West'},{i * 10}" for i in range(1, 40)) + "\nEast,N/A\nWest,-\n")
    v2 = _analyze(csv)
    run = tmp_path / "run"
    run.mkdir()
    ns = _run(generate_script("messy.csv", v2), csv, run, monkeypatch)
    assert pd.api.types.is_numeric_dtype(ns["df"]["Sales"]) and ns["df"]["Sales"].isna().sum() == 2


def test_precision_flag_switches_between_the_apps_float32_and_full_float64(tmp_path, monkeypatch):
    csv = tmp_path / "prec.csv"
    csv.write_text("Region,Sales\n" + "\n".join(f"{'A' if i % 2 else 'B'},{i / 7:.6f}" for i in range(1, 60)))
    v2 = _analyze(csv)
    script = generate_script("prec.csv", v2)
    assert _run(script, csv, tmp_path, monkeypatch)["df"]["Sales"].dtype == np.float32
    full = script.replace("MATCH_APP_PRECISION = True ", "MATCH_APP_PRECISION = False")
    assert _run(full, csv, tmp_path, monkeypatch)["df"]["Sales"].dtype == np.float64


def test_duplicate_removal_is_off_by_default_because_the_app_analyses_every_row(tmp_path, monkeypatch):
    csv = tmp_path / "dups.csv"
    csv.write_text("Region,Sales\n" + "\n".join(f"{'A' if i % 2 else 'B'},{i % 10}" for i in range(60)))
    v2 = _analyze(csv)
    script = generate_script("dups.csv", v2)
    assert len(_run(script, csv, tmp_path, monkeypatch)["df"]) == 60
    on = script.replace("REMOVE_EXACT_DUPLICATES = False ", "REMOVE_EXACT_DUPLICATES = True ")
    assert len(_run(on, csv, tmp_path, monkeypatch)["df"]) < 60


def test_date_columns_the_app_parsed_are_parsed_in_the_script_too():
    v2 = _analyze(SAMPLES[0])
    assert v2["profile"]["date_columns"]
    script = generate_script("demo-sales-data.csv", v2)
    for c in v2["profile"]["date_columns"]:
        assert f"pd.to_datetime(df[{c!r}]" in script


# ---------------------------------------------------------------------------
# safety: user data must never become code
# ---------------------------------------------------------------------------
EVIL_COL = "a'); import os; os.system('echo pwned') #"
EVIL_TITLE = "Totals\nimport os; os.system('echo pwned')"


def _evil_v2():
    return {
        "profile": {"columns": [EVIL_COL, "Region", "Date"], "date_columns": ["Date"]},
        "filterable_data": {"available": True, "date_column": "Date", "dimension_columns": ["Region"], "measure_columns": [EVIL_COL], "rows": []},
        "top_analyses": [],
        "all_analyses": [
            {"id": "x'); import os #", "type": "distribution_sum", "title": EVIL_TITLE, "column": "Region", "metric_column": EVIL_COL, "aggregation": "sum", "data": [1]},
            {"id": "t", "type": "trend", "title": "T", "metric_column": EVIL_COL, "date_column": "Date", "aggregation": "avg", "data": [1]},
        ],
        "confidence_intervals": {"intervals": [{"measure": EVIL_COL, "aggregation": "sum"}]},
    }


def test_hostile_column_names_titles_ids_and_filter_values_cannot_become_code():
    filters = {"dateFrom": "2024-01-01'); import os #", "dimensionFilters": {EVIL_COL: ["x'); os.system('y') #", "ok"]}}
    script = generate_script("evil'); import os #.csv", _evil_v2(), filters)
    tree = ast.parse(script)          # must still be valid Python

    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported == {"json", "sys", "pathlib", "numpy", "pandas"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "os" not in names
    assert not any(isinstance(n, ast.Attribute) and n.attr == "system" for n in ast.walk(tree))


def test_a_title_with_a_newline_stays_a_single_comment_line():
    script = generate_script("f.csv", _evil_v2())
    for line in script.splitlines():
        assert not line.strip().startswith("import os")


def test_result_variable_names_are_valid_and_unique_even_for_colliding_ids():
    v2 = _evil_v2()
    v2["all_analyses"].append({**v2["all_analyses"][0], "id": "x') import os ##"})   # different id, same identifier once cleaned
    script = generate_script("f.csv", v2)
    tree = ast.parse(script)
    results = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "RESULTS")
    values = [v.id for v in results.value.values]
    assert len(values) == len(set(values)) == 3
    assert all(re.fullmatch(r"[A-Za-z_]\w*", name) for name in values)


def test_unknown_types_and_unknown_columns_are_skipped_not_guessed():
    v2 = _evil_v2()
    v2["all_analyses"] += [
        {"id": "seg", "type": "segment", "title": "Fancy Segments", "data": [1]},
        {"id": "ghost", "type": "histogram", "title": "Ghost", "metric_column": "Not In File", "data": [1]},
    ]
    script = generate_script("f.csv", v2)
    assert "Fancy Segments" not in script and "Ghost" not in script and "Not In File" not in script


def test_a_result_with_no_analyses_still_gives_a_runnable_script():
    script = generate_script("f.csv", {"profile": {"columns": ["A"]}, "top_analyses": [], "all_analyses": []})
    ast.parse(script)
    assert "RESULTS = {" in script


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------
def test_endpoint_returns_a_downloadable_python_file(client, sales_df):
    v2 = client.post("/api/analyze", files={"file": ("my data.csv", sales_df.to_csv(index=False).encode(), "text/csv")}).json()["v2"]
    v2.pop("filterable_data")  # as the frontend sends it
    resp = client.post("/api/export/code", json={"file_name": "my data.csv", "v2": v2, "filters": None})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/x-python")
    assert 'filename="mydata_datalens.py"' in resp.headers["content-disposition"]
    ast.parse(resp.text)
    assert "DATA_FILE = 'my data.csv'" in resp.text


def test_endpoint_rejects_an_empty_payload_cleanly(client):
    assert client.post("/api/export/code", json={"file_name": "x.csv", "v2": {}}).status_code == 400
    assert client.post("/api/export/code", json={"file_name": "x.csv"}).status_code == 422


def test_the_script_survives_a_console_that_cannot_show_the_characters_in_the_data(tmp_path):
    """On Windows, output sent to a pipe or file uses the legacy code page (cp1252), which cannot encode
    most non-Latin scripts. A column called 売上 must not stop the script with UnicodeEncodeError."""
    import subprocess, sys
    csv = tmp_path / "売上.csv"
    # a category column NAMED and VALUED in Japanese, so the script prints non-Latin text (its title and its values)
    csv.write_text("地域,Sales\n" + "\n".join(f"{'東京' if i % 2 else '大阪'},{i * 10}" for i in range(1, 60)), encoding="utf-8")
    v2 = _analyze(csv)
    script = tmp_path / "s.py"
    script.write_text(generate_script(csv.name, v2), encoding="utf-8")
    env = {**__import__("os").environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    out = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, env=env)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")[-600:]
    assert b"rows x" in out.stdout
    assert b"?" in out.stdout and "東京".encode("utf-8") not in out.stdout   # shown as ? on a console that cannot display it
