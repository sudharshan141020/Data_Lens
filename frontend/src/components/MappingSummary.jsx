import { useState } from 'react';

const ROLE_LABELS = {
  date: 'Date', revenue: 'Revenue', profit: 'Profit', cost: 'Cost',
  quantity: 'Quantity', discount: 'Discount', customer: 'Customer',
  category: 'Category', region: 'Region',
};

export default function MappingSummary({ result }) {
  const [open, setOpen] = useState(false);
  const { detected_columns, detection_confidence, unmapped_columns } = result;
  const roles = Object.keys(ROLE_LABELS).filter((r) => detected_columns[r]);
  // 'guessed' (no real name/dtype signal at all -- picked as a last
  // resort, e.g. "largest numeric column" standing in for revenue on a
  // dataset that may not have a revenue concept) is even lower-confidence
  // than 'inferred' and should count toward the same "worth a check" flag.
  const isLowConfidence = (role) => detection_confidence[role] === 'inferred' || detection_confidence[role] === 'guessed';
  const inferredCount = roles.filter(isLowConfidence).length;

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
          <div className="mapping-grid">
            {roles.map((role) => (
              <div key={role} className="mapping-row">
                <span className="mapping-role">{ROLE_LABELS[role]}</span>
                <span className="mapping-arrow">→</span>
                <span className="mapping-col mono">{detected_columns[role]}</span>
                <span className={`mapping-badge ${detection_confidence[role] === 'name' ? 'name' : detection_confidence[role] === 'combined' ? 'combined' : 'inferred'}`}>
                  {detection_confidence[role] === 'name' ? 'matched'
                    : detection_confidence[role] === 'combined' ? 'merged'
                    : detection_confidence[role] === 'guessed' ? 'best guess'
                    : 'inferred'}
                </span>
              </div>
            ))}
          </div>
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
