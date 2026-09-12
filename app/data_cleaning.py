"""
Cleaned CSV Export.

Deliberately conservative about what "cleaned" means: removes exact
duplicate rows (unambiguously dirty data -- there's no legitimate reason
two fully-identical rows both belong in the dataset), and FLAGS rows the
anomaly detector identified rather than deleting them. Auto-deleting
statistical outliers would be a real, opinionated data-loss decision this
app has no business making silently -- a genuinely large sale isn't
"dirty data" just because it's unusual, and removing it changes the
dataset's story without the person asking for that. Flagging keeps that
call in the person's hands, in a normal spreadsheet tool they already
have, rather than Claude or this app deciding for them.
"""
import pandas as pd

from app.anomaly_detection import detect_anomalies


def build_cleaned_csv(df: pd.DataFrame, profile) -> tuple:
    """Returns (cleaned_df, summary_dict)."""
    original_row_count = len(df)

    is_duplicate = df.duplicated()
    cleaned = df[~is_duplicate].reset_index(drop=True)
    duplicates_removed = int(is_duplicate.sum())

    anomaly_report = detect_anomalies(cleaned, profile)
    cleaned["flagged_as_unusual"] = False
    anomalies_flagged = 0
    if anomaly_report.get("available"):
        flagged_rows = set(anomaly_report["all_anomaly_row_indices"])  # uncapped -- every flagged row, not just the top N with a full explanation
        cleaned.loc[cleaned.index.isin(flagged_rows), "flagged_as_unusual"] = True
        anomalies_flagged = int(cleaned["flagged_as_unusual"].sum())

    summary = {
        "original_row_count": original_row_count,
        "cleaned_row_count": int(len(cleaned)),
        "duplicates_removed": duplicates_removed,
        "anomalies_flagged": anomalies_flagged,
        "anomaly_detection_available": bool(anomaly_report.get("available")),
    }
    return cleaned, summary
