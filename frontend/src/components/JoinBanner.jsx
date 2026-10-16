// One-line, plain-language account of what a "Join two files" actually
// did: which column matched which, how many rows found a partner, and
// which same-named columns were kept apart. Shown above a joined
// analysis so a silent merge never has to be taken on faith.
export default function JoinBanner({ info }) {
  if (!info) return null;
  const j = info;
  return (
    <p className="dim-sub" style={{ marginBottom: 12 }}>
      Joined {j.fact_file} to {j.dimension_file} on
      {' '}<span className="mono">{j.key_in_fact_file}</span>
      {j.key_in_fact_file !== j.key_in_dimension_file && <> / <span className="mono">{j.key_in_dimension_file}</span></>}
      {' — '}{j.matched_rows} of {j.total_rows} rows matched ({j.match_rate_pct}%)
      {j.unmatched_rows > 0 && `, ${j.unmatched_rows} kept with blank fields from the unmatched side`}
      {j.shared_column_names?.length > 0 && (
        <> · shared column name{j.shared_column_names.length > 1 ? 's' : ''} {j.shared_column_names.map((c) => `"${c}"`).join(', ')} kept as separate columns per file</>
      )}
    </p>
  );
}
