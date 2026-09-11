import UploadZone from './UploadZone';

function StatusDot({ status }) {
  if (status === 'loading') return <span className="status-dot loading" title="Analyzing…" />;
  if (status === 'error') return <span className="status-dot error" title="Failed" />;
  return <span className="status-dot ready" title="Ready" />;
}

export default function Sidebar({
  sessions, activeId, onSelect, onRemove, onFilesSelected, uploadError,
  onTogglePin, combineMode, onToggleCombineMode, selectedForCombine,
  onToggleSelect, onCombine, compareMode, onToggleCompareMode,
  selectedForCompare, onToggleSelectForCompare, onCompare,
}) {
  const readySessions = sessions.filter((s) => s.status === 'ready' && s.sourceFile);
  const canCombine = readySessions.length >= 2;
  const canCompare = readySessions.length >= 2;
  const anySelectMode = combineMode || compareMode;

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" />
        <span className="brand-name">DATALENS</span>
      </div>

      <UploadZone onFilesSelected={onFilesSelected} error={uploadError} compact />

      <div className="sidebar-actions">
        {canCombine && !compareMode && (
          <button
            className={`combine-toggle ${combineMode ? 'active' : ''}`}
            onClick={onToggleCombineMode}
          >
            {combineMode ? 'Cancel combine' : 'Combine files…'}
          </button>
        )}
        {combineMode && (
          <button
            className="combine-run"
            disabled={selectedForCombine.length < 2}
            onClick={onCombine}
          >
            Combine selected ({selectedForCombine.length})
          </button>
        )}
        {canCompare && !combineMode && (
          <button
            className={`combine-toggle ${compareMode ? 'active' : ''}`}
            onClick={onToggleCompareMode}
          >
            {compareMode ? 'Cancel compare' : 'Compare two files…'}
          </button>
        )}
        {compareMode && (
          <button
            className="combine-run"
            disabled={selectedForCompare.length !== 2}
            onClick={onCompare}
          >
            Compare selected ({selectedForCompare.length}/2)
          </button>
        )}
      </div>

      <div className="session-list">
        {sessions.length === 0 && (
          <p className="dim-sub session-empty">No files analyzed yet.</p>
        )}
        {sessions.map((s) => {
          const canSelectForCombine = combineMode && s.status === 'ready' && s.sourceFile;
          const canSelectForCompare = compareMode && s.status === 'ready' && s.sourceFile
            && (selectedForCompare.includes(s.id) || selectedForCompare.length < 2);
          return (
            <div
              key={s.id}
              className={`session-item ${s.id === activeId ? 'active' : ''} ${anySelectMode ? 'combine-mode' : ''}`}
              onClick={() => {
                if (combineMode) return canSelectForCombine && onToggleSelect(s.id);
                if (compareMode) return canSelectForCompare && onToggleSelectForCompare(s.id);
                return onSelect(s.id);
              }}
            >
              {combineMode && (
                <input
                  type="checkbox"
                  className="session-checkbox"
                  checked={selectedForCombine.includes(s.id)}
                  disabled={!canSelectForCombine}
                  onChange={() => onToggleSelect(s.id)}
                  onClick={(e) => e.stopPropagation()}
                />
              )}
              {compareMode && (
                <input
                  type="checkbox"
                  className="session-checkbox"
                  checked={selectedForCompare.includes(s.id)}
                  disabled={!canSelectForCompare}
                  onChange={() => onToggleSelectForCompare(s.id)}
                  onClick={(e) => e.stopPropagation()}
                />
              )}
              {!anySelectMode && <StatusDot status={s.status} />}

              <div className="session-item-body">
                <span className="session-name mono">{s.fileName}</span>
                {s.status === 'ready' && s.result?.kpis?.total_revenue !== undefined
                  && s.result?.detection_confidence?.revenue !== 'guessed' && (
                  <span className="session-sub mono">
                    ${(s.result.kpis.total_revenue / 1000).toFixed(1)}K revenue
                  </span>
                )}
                {s.status === 'loading' && <span className="session-sub">Analyzing…</span>}
                {s.status === 'error' && <span className="session-sub session-sub-error">Failed</span>}
              </div>

              {!anySelectMode && (
                <>
                  <button
                    className={`session-pin ${s.pinned ? 'pinned' : ''}`}
                    onClick={(e) => { e.stopPropagation(); onTogglePin(s.id); }}
                    aria-label={s.pinned ? `Unpin ${s.fileName}` : `Pin ${s.fileName}`}
                    title={s.pinned ? 'Unpin' : 'Pin'}
                  >
                    ▲
                  </button>
                  <button
                    className="session-remove"
                    onClick={(e) => { e.stopPropagation(); onRemove(s.id); }}
                    aria-label={`Remove ${s.fileName}`}
                    title="Remove"
                  >
                    ×
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>

      <p className="dim-sub sidebar-footer">Each file is analyzed separately — nothing is combined unless you choose to.</p>
    </aside>
  );
}
