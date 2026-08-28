import { useEffect, useRef, useState } from 'react';
import { searchIndex } from '../searchUtils';

const CATEGORY_COLOR = {
  Finding: 'var(--teal)',
  'Weak Point': 'var(--red)',
  Story: 'var(--amber)',
  Chart: 'var(--text-muted)',
  Correlation: 'var(--teal)',
};

function highlightMatch(text, query) {
  const lower = text.toLowerCase();
  const pos = lower.indexOf(query.toLowerCase());
  if (pos === -1) return text;
  return (
    <>
      {text.slice(0, pos)}
      <mark className="search-result-mark">{text.slice(pos, pos + query.length)}</mark>
      {text.slice(pos + query.length)}
    </>
  );
}

function jumpToPlainAnchor(anchorId) {
  const el = document.getElementById(anchorId);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('search-highlight');
  setTimeout(() => el.classList.remove('search-highlight'), 1400);
}

export default function SearchBar({ index, onJumpToAnalysis }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const inputRef = useRef(null);

  const results = searchIndex(index, query);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  if (!index?.length) return null;

  const handleSelect = (result) => {
    setOpen(false);
    if (result.analysisId) {
      onJumpToAnalysis(result.analysisId);
    } else {
      jumpToPlainAnchor(result.anchorId);
    }
  };

  return (
    <div className="search-bar-wrap" ref={wrapRef}>
      <div className="search-bar-input-wrap">
        <span className="search-bar-icon">⌕</span>
        <input
          ref={inputRef}
          type="text"
          className="search-bar-input"
          placeholder="Search findings, charts, weak points…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
        />
        {query && (
          <button type="button" className="search-bar-clear" onClick={() => { setQuery(''); inputRef.current?.focus(); }}>
            ×
          </button>
        )}
      </div>

      {open && query.trim() && (
        <div className="search-results">
          {results.length === 0 ? (
            <p className="search-results-empty">No matches for "{query}"</p>
          ) : (
            results.map((r, i) => (
              <button
                type="button"
                key={i}
                className="search-result-row"
                onClick={() => handleSelect(r)}
              >
                <span className="search-result-category" style={{ color: CATEGORY_COLOR[r.category] || 'var(--text-muted)' }}>
                  {r.category}
                </span>
                <span className="search-result-text">{highlightMatch(r.text, query)}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
