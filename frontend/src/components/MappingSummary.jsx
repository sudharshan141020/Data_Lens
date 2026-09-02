import { useState } from 'react';

const ROLE_LABELS = {
  date: 'Date', revenue: 'Revenue', profit: 'Profit', cost: 'Cost',
  quantity: 'Quantity', discount: 'Discount', customer: 'Customer',
  category: 'Category', region: 'Region',
};

function badgeLabel(confidence) {
  if (confidence === 'name') return 'matched';
  if (confidence === 'combined') return 'merged';
  if (confidence === 'guessed') return 'best guess';
  if (confidence === 'manual') return 'set by you';
  return 'inferred';
}

function badgeClass(confidence) {
  if (confidence === 'name' || confidence === 'combined' || confidence === 'manual') return confidence === 'manual' ? 'manual' : confidence;
  return 'inferred'; // covers 'inferred' and 'guessed'
}

function MappingRow({ role, column, confidence, allColumns, onRemap, disabled }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <div className="mapping-row mapping-row-editing">
        <span className="mapping-role">{ROLE_LABELS[role]}</span>
        <span className="mapping-arrow">→</span>
        <select
          className="mapping-select"
          autoFocus
          defaultValue={column}
          disabled={disabled}
          onChange={(e) => {
            const newColumn = e.target.value;
            setEditing(false);
            if (newColumn !== column) onRemap(role, newColumn);
          }}
          onBlur={() => setEditing(false)}
        >
          {allColumns.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className="mapping-row">
      <span className="mapping-role">{ROLE_LABELS[role]}</span>
      <span className="mapping-arrow">→</span>
      <span className="mapping-col mono">{column}</span>
      <span className={`mapping-badge ${badgeClass(confidence)}`}>{badgeLabel(confidence)}</span>
      <button
        type="button"
        className="mapping-edit-btn"
        onClick={() => setEditing(true)}
        disabled={disabled}
        title={`Use a different column for ${ROLE_LABELS[role]}`}
      >
        change
      </button>
    </div>
  );
}

export default function MappingSummary({ result, onRemap, remapping, remapError }) {
  const [open, setOpen] = useState(false);
  const { detected_columns, detection_confidence, unmapped_columns } = result;
  const roles = Object.keys(ROLE_LABELS).filter((r) => detected_columns[r]);
  // 'guessed' (no real name/dtype signal at all -- picked as a last
  // resort, e.g. "largest numeric column" standing in for revenue on a
  // dataset that may not have a revenue concept) is even lower-confidence
  // than 'inferred' and should count toward the same "worth a check" flag.
  const isLowConfidence = (role) => detection_confidence[role] === 'inferred' || detection_confidence[role] === 'guessed';
  const inferredCount = roles.filter(isLowConfidence).length;

  const allColumns = Array.from(new Set([...Object.values(detected_columns), ...(unmapped_columns || [])])).sort();
  const canRemap = typeof onRemap === 'function' && allColumns.length > 0;

  return (
    <div className="mapping-summary">
      <button className="mapping-toggle" onClick={() => setOpen((o) => !o)}>
        <span className="tick">02</span>
        <span className="mapping-toggle-label">Column mapping</span>
        {inferredCount > 0 && (
          <span className="mapping-flag">{inferredCount} inferred — worth a check</span>
        )}
        <span className="mapping-chevron">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="mapping-body">
          {canRemap && (
            <p className="mapping-hint">
              Got something wrong? Click <span className="mono">change</span> next to any row to pick a
              different column — the whole analysis updates to match.
            </p>
          )}
          <div className="mapping-grid">
            {roles.map((role) => (
              canRemap ? (
                <MappingRow
                  key={role}
                  role={role}
                  column={detected_columns[role]}
                  confidence={detection_confidence[role]}
                  allColumns={allColumns}
                  onRemap={onRemap}
                  disabled={remapping}
                />
              ) : (
                <div key={role} className="mapping-row">
                  <span className="mapping-role">{ROLE_LABELS[role]}</span>
                  <span className="mapping-arrow">→</span>
                  <span className="mapping-col mono">{detected_columns[role]}</span>
                  <span className={`mapping-badge ${badgeClass(detection_confidence[role])}`}>
                    {badgeLabel(detection_confidence[role])}
                  </span>
                </div>
              )
            ))}
          </div>
          {remapping && <p className="mapping-remapping-note">Re-analyzing with the new mapping…</p>}
          {remapError && <p className="mapping-remap-error">{remapError}</p>}
          {unmapped_columns?.length > 0 && (
            <div className="mapping-unused">
              <span className="dim-sub">Not used in analysis: </span>
              <span className="mono unused-list">{unmapped_columns.join(', ')}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
