"""
Self-contained Static HTML Report.

A single .html file with everything inlined -- CSS, no external
scripts, no CDN, no charting library -- that opens correctly straight
from disk or an email attachment with zero network access. Same
stateless design as pdf_report.py (takes the `v2` payload the frontend
already has, nothing stored server-side) and reuses its color palette
for visual consistency across exports, but covers more ground: this
session's newer sections (segments, seasonality, retention, anomalies,
period comparison, Simpson's paradox, Benford's Law, confidence
intervals, text fields) are included here, not just in the PDF, since
this is the "everything, to keep or forward" export rather than the
PDF's more print-oriented summary.

No JS framework, no Recharts -- bar comparisons are rendered as plain
HTML/CSS width-percentage bars, which need nothing but a browser to
display correctly, matching the "opens anywhere, forever" goal a
self-contained file is supposed to deliver.
"""
import html
from datetime import datetime, timezone

INK = "#0A0A0B"
MUTED = "#6B6B70"
BORDER = "#DADADD"
RED = "#C1272D"
TEAL = "#1E7F73"
SURFACE = "#F5F5F6"

CSS = f"""
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        color: {INK}; max-width: 860px; margin: 0 auto; padding: 40px 24px 80px; line-height: 1.55; }}
h1 {{ font-size: 26px; margin: 0 0 4px; }}
h2 {{ font-size: 16px; margin: 36px 0 12px; padding-top: 20px; border-top: 1px solid {BORDER}; }}
.subtitle {{ color: {MUTED}; font-size: 13px; margin-bottom: 28px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid {BORDER}; vertical-align: top; }}
th {{ background: {SURFACE}; font-weight: 600; }}
.muted {{ color: {MUTED}; font-size: 12.5px; }}
.caveat {{ color: {RED}; font-size: 12px; font-style: italic; }}
.card {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 12px 14px; margin-bottom: 10px; }}
.card .top {{ display: flex; justify-content: space-between; font-size: 12px; color: {MUTED}; margin-bottom: 6px; }}
.bar-row {{ display: grid; grid-template-columns: 140px 1fr 60px; align-items: center; gap: 8px; font-size: 12.5px; margin-bottom: 6px; }}
.bar-track {{ height: 7px; background: {SURFACE}; border-radius: 3px; overflow: hidden; }}
.bar-fill {{ height: 100%; background: {TEAL}; }}
footer {{ margin-top: 48px; color: {MUTED}; font-size: 11.5px; border-top: 1px solid {BORDER}; padding-top: 12px; }}
"""


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _section(title: str, body: str) -> str:
    return f"<h2>{_esc(title)}</h2>\n{body}"


def _table(headers: list, rows: list) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bar_list(rows: list, max_value: float = None) -> str:
    """rows: [(label, value, display_value_str), ...]"""
    if not rows:
        return ""
    m = max_value or max((r[1] for r in rows), default=1) or 1
    out = []
    for label, value, display in rows:
        pct = max(0, min(100, 100 * value / m)) if m else 0
        out.append(
            f'<div class="bar-row"><span>{_esc(label)}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<span class="muted">{_esc(display)}</span></div>'
        )
    return "".join(out)


def build_html_report(file_name: str, v2: dict) -> str:
    profile = v2.get("profile") or {}
    sections = []

    # --- Overview ---
    overview_rows = []
    for label, key in [
        ("Detected domain", "domain"), ("Domain confidence", "domain_confidence"),
        ("Primary entity", "primary_entity"), ("Row count", "row_count"),
        ("Column count", "column_count"), ("Data completeness", "data_completeness_pct"),
    ]:
        val = profile.get(key)
        if val is not None:
            overview_rows.append([label, val])
    dq = v2.get("data_quality") or {}
    if dq.get("overall_quality_score") is not None:
        overview_rows.append(["Data quality score", f"{dq['overall_quality_score']}/100"])
    overview_html = _table(["Field", "Value"], overview_rows) if overview_rows else "<p class='muted'>No profile data.</p>"

    # --- Story ---
    beats = v2.get("story") or []
    if beats:
        beats_html = "".join(f"<p><b>{_esc(b.get('label',''))}:</b> {_esc(b.get('text',''))}</p>" for b in beats)
        sections.append(_section("The Story", beats_html))

    # --- Findings ---
    findings = v2.get("findings") or []
    if findings:
        rows = [[f.get("text", ""), f.get("category", "")] for f in findings]
        sections.append(_section("Findings", _table(["Finding", "Category"], rows)))

    # --- Segments ---
    segments = v2.get("segments") or {}
    if segments.get("available"):
        rows = [(c["label"], c["pct"], f"{c['pct']}% ({c['size']} rows)") for c in segments.get("clusters", [])]
        sections.append(_section("Segments", _bar_list(rows, max_value=100)))

    # --- Seasonality ---
    seasonality = v2.get("seasonality") or {}
    if seasonality.get("available"):
        sections.append(_section("Seasonality", f"<p>{_esc(seasonality.get('summary',''))}</p>"))

    # --- Period comparison ---
    pc = v2.get("period_comparison") or {}
    if pc.get("available"):
        sections.append(_section("Period Comparison", f"<p>{_esc(pc.get('summary',''))}</p>"))

    # --- Retention / cohorts ---
    cohorts = v2.get("cohorts") or {}
    if cohorts.get("available"):
        body = f"<p>{_esc(cohorts.get('summary',''))}</p>"
        rows = [(c["cohort"], c["size"], f"{c['size']}") for c in cohorts.get("cohort_sizes", [])]
        if rows:
            body += _bar_list(rows)
        sections.append(_section("Retention", body))

    # --- Anomalies ---
    anomalies = v2.get("anomalies") or {}
    if anomalies.get("available") and anomalies.get("anomaly_count"):
        body = f"<p>{anomalies['anomaly_count']} of {anomalies['row_count_used']} rows ({anomalies['anomaly_pct']}%) flagged as unusual.</p>"
        rows = [[a["row_index"], a["distance"], a["why"]] for a in anomalies.get("anomalies", [])[:15]]
        if rows:
            body += _table(["Row", "Distance", "Why"], rows)
        sections.append(_section("Anomalies", body))

    # --- Simpson's paradox ---
    simpsons = v2.get("simpsons_paradox") or {}
    if simpsons.get("flags"):
        body = "".join(f"<p class='caveat'>{_esc(f['summary'])}</p>" for f in simpsons["flags"])
        sections.append(_section("Simpson's Paradox Check", body))

    # --- Benford ---
    benford = v2.get("benford") or {}
    checked = [r for r in benford.get("results", []) if r.get("checked")]
    if checked:
        rows = [[r["column"], r["n"], r["p_value"], "Yes" if r["deviates"] else "No"] for r in checked]
        sections.append(_section("Benford's Law Check", _table(["Column", "n", "p-value", "Deviates"], rows)))

    # --- Confidence intervals ---
    ci = v2.get("confidence_intervals") or {}
    if ci.get("available"):
        rows = [[i["measure"], i["point_estimate"], f"{i['ci_low']} \u2013 {i['ci_high']}", f"\u00b1{i['relative_margin_pct']}%"] for i in ci.get("intervals", [])]
        sections.append(_section("Confidence Intervals", _table(["Measure", "Estimate", "95% Range", "Margin"], rows)))

    # --- Text fields ---
    text_analysis = v2.get("text_analysis") or {}
    checked_text = [r for r in text_analysis.get("results", []) if r.get("checked")]
    if checked_text:
        body = ""
        for r in checked_text:
            body += f"<p class='muted'>{_esc(r['column'])} \u2014 {r['entry_count']} entries</p>"
            rows = [(w["word"], w["count"], f"{w['pct_of_entries']}%") for w in r["top_words"][:10]]
            body += _bar_list(rows)
        sections.append(_section("Text Fields", body))

    # --- Weak points ---
    weak_points = v2.get("weak_points") or []
    if weak_points:
        body = ""
        for w in weak_points:
            body += (
                f"<div class='card'><div class='top'><b style='color:{INK}'>{_esc(w.get('problem',''))}</b>"
                f"<span>{_esc(w.get('priority',''))}</span></div>"
            )
            if w.get("impact"):
                body += f"<p class='muted'>Impact: {_esc(w['impact'])}</p>"
            if w.get("suggested_action"):
                body += f"<p class='muted'>Suggested action: {_esc(w['suggested_action'])}</p>"
            body += "</div>"
        sections.append(_section("Weak Points & Recommendations", body))

    # --- Correlations ---
    cc = v2.get("correlation_center") or {}
    pairs = cc.get("pairs") or []
    if pairs:
        rows = [[f"{p.get('col1','')} \u00d7 {p.get('col2','')}", p.get("r", ""), p.get("n", ""), "Yes" if p.get("significant") else "No", p.get("strength", "")] for p in pairs]
        sections.append(_section("Correlations", _table(["Columns", "r", "n", "Significant", "Strength"], rows)))

    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y")
    body_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>DataLens Report \u2014 {_esc(file_name)}</title>
<style>{CSS}</style>
</head>
<body>
<h1>DataLens Report</h1>
<p class="subtitle">{_esc(file_name)} &nbsp;\u00b7&nbsp; generated {generated_at}</p>
{_section("Overview", overview_html)}
{body_html}
<footer>Generated by DataLens \u00b7 rule-based, no AI calls \u00b7 self-contained file, nothing sent or stored</footer>
</body>
</html>"""
