import { useEffect, useRef, useState } from 'react';
import { getDistinctValues, getDateRange } from '../filterUtils';

function DimensionFilter({ column, rows, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const values = getDistinctValues(rows, column);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const activeCount = selected ? selected.size : 0;

  const toggleValue = (v) => {
    const next = new Set(selected || []);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange(next);
  };

  if (values.length < 2 || values.length > 40) return null; // not meaningfully filterable

  return (
    <div className="filter-dim-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`filter-dim-btn ${activeCount > 0 ? 'is-active' : ''}`}
        onClick={() => setOpen((o) => !o)}
      >
        {column}{activeCount > 0 ? ` (${activeCount})` : ''} <span className="filter-dim-caret">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="filter-dim-menu">
          {activeCount > 0 && (
            <button type="button" className="filter-dim-clear" onClick={() => onChange(new Set())}>
              Clear
            </button>
          )}
          {values.map((v) => (
            <label key={v} className="filter-dim-option">
              <input
                type="checkbox"
                checked={!selected || selected.size === 0 ? false : selected.has(v)}
                onChange={() => toggleValue(v)}
              />
              <span>{String(v)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export default function FilterBar({ filterableData, filters, onChange, filteredCount, totalCount }) {
  if (!filterableData?.available) return null;

  const { date_column: dateColumn, dimension_columns: dimensionColumns, rows } = filterableData;
  if (!dateColumn && (!dimensionColumns || dimensionColumns.length === 0)) return null;
  const dateRange = dateColumn ? getDateRange(rows, dateColumn) : null;
  const hasActiveFilters = filters && (
    filters.dateFrom || filters.dateTo ||
    Object.values(filters.dimensionFilters || {}).some((s) => s && s.size > 0)
  );

  const setDimensionFilter = (col, set) => {
    onChange({
      ...filters,
      dimensionFilters: { ...(filters?.dimensionFilters || {}), [col]: set },
    });
  };

  return (
    <div className="filter-bar">
      <div className="filter-bar-controls">
        {dateColumn && dateRange?.min && (
          <div className="filter-date-group">
            <input
              type="date"
              className="filter-date-input"
              min={dateRange.min}
              max={dateRange.max}
              value={filters?.dateFrom || ''}
              onChange={(e) => onChange({ ...filters, dateFrom: e.target.value, dateColumn })}
            />
            <span className="filter-date-sep">→</span>
            <input
              type="date"
              className="filter-date-input"
              min={dateRange.min}
              max={dateRange.max}
              value={filters?.dateTo || ''}
              onChange={(e) => onChange({ ...filters, dateTo: e.target.value, dateColumn })}
            />
          </div>
        )}

        {dimensionColumns.map((col) => (
          <DimensionFilter
            key={col}
            column={col}
            rows={rows}
            selected={filters?.dimensionFilters?.[col]}
            onChange={(set) => setDimensionFilter(col, set)}
          />
        ))}

        {hasActiveFilters && (
          <button type="button" className="filter-reset-btn" onClick={() => onChange(null)}>
            Reset filters
          </button>
        )}
      </div>

      <p className="filter-count">
        {hasActiveFilters ? (
          <>Showing <span className="mono">{filteredCount}</span> of <span className="mono">{totalCount}</span> rows</>
        ) : (
          <>All <span className="mono">{totalCount}</span> rows</>
        )}
      </p>
    </div>
  );
}
