"""
The PDF export has to survive the text in the data.

reportlab parses Paragraph content as a mini-HTML, so a value as ordinary as
"R&D" or "Sales < 5" raised a parse error ("paraparser: syntax error") and the
endpoint turned that into a 500 -- one ampersand anywhere in a finding made the
whole report undownloadable. Every field below carries markup characters, and
the document still has to render.
"""
import pytest

from app.pdf_report import build_pdf_report

# reportlab is lenient about a bare "&" or "< 5", but it wraps the text in its own
# <para> tag, so any tag the data leaves unclosed -- or a stray closing tag, or an
# <font>/<br> with no end -- is a hard parse error. These are the shapes that used
# to turn a copy-pasted field into a 500; the bare "&" case is included because it
# must also survive.
HOSTILE = "R&D <b>not bold</b> 5 < 3 & > 2"
MARKUP_THAT_BREAKS_AN_UNESCAPED_PARAGRAPH = ["R&D <b>unclosed", "</b>", "<para>", "<br>oops"]


def _payload(text=HOSTILE):
    return {
        "profile": {
            "domain": text,
            "domain_confidence": 0.9,
            "primary_entity": text,
            "row_count": 10,
            "column_count": 2,
            "data_completeness_pct": 99.5,
        },
        "story": [{"label": text, "text": text, "tone": "neutral"}],
        "findings": [{"text": text, "category": text}],
        "weak_points": [{
            "problem": text, "impact": text, "suggested_action": text,
            "priority": text,
        }],
        "data_quality": {
            "duplicate_row_count": 0,
            "duplicate_row_pct": 0.0,
            "overall_quality_score": 90,
            "usable_quality_score": 88,
            "usable_column_count": 2,
            "total_column_count": 2,
            "constant_columns": [text],
            "missing_by_column": [{"column": text, "missing_pct": 1.0}],
        },
        "correlation_center": {
            "pairs": [{
                "col1": text, "col2": "Plain", "r": 0.5, "n": 10,
                "p_value": 0.01, "significant": True, "strength": "moderate",
                "caveat": text,
            }],
            "multicollinearity": {
                "results": [{"column": text, "vif": 2.0, "severity": "low", "note": text}],
                "note": None,
            },
        },
    }


def test_markup_characters_in_the_data_do_not_break_the_report():
    pdf = build_pdf_report("R&D <sales>.csv", _payload())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1_000


@pytest.mark.parametrize("text", MARKUP_THAT_BREAKS_AN_UNESCAPED_PARAGRAPH)
def test_markup_that_would_not_parse_is_rendered_as_text(text):
    pdf = build_pdf_report("data.csv", _payload(text))
    assert pdf.startswith(b"%PDF")


def test_a_plain_report_still_renders():
    pdf = build_pdf_report("sales.csv", {"profile": {"domain": "sales", "row_count": 3}})
    assert pdf.startswith(b"%PDF")
