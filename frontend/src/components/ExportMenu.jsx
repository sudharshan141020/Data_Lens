import { useEffect, useRef, useState } from 'react';

export default function ExportMenu({ onExportExcel, onExportPdf, onCopyFindings, onDownloadCleanedCsv, pdfLoading }) {
  const [open, setOpen] = useState(false);
  const [copyState, setCopyState] = useState('idle'); // idle | copied | error
  const [cleanState, setCleanState] = useState('idle'); // idle | downloading | done | error
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const handleEscape = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const handleCopyFindings = async () => {
    try {
      const ok = await onCopyFindings();
      setCopyState(ok ? 'copied' : 'error');
    } catch {
      setCopyState('error');
    }
    setTimeout(() => setCopyState('idle'), 1800);
    setOpen(false);
  };

  const copyLabel = copyState === 'copied' ? 'Copied!' : copyState === 'error' ? "Couldn't copy" : 'Copy findings as text';

  const handleDownloadCleaned = async () => {
    setCleanState('downloading');
    try {
      await onDownloadCleanedCsv();
      setCleanState('done');
    } catch {
      setCleanState('error');
    }
    setTimeout(() => setCleanState('idle'), 1800);
    setOpen(false);
  };

  const cleanLabel = cleanState === 'downloading' ? 'Preparing…' : cleanState === 'done' ? 'Downloaded!' : cleanState === 'error' ? "Couldn't download" : 'Download cleaned CSV';

  return (
    <div className="export-menu-wrap" ref={wrapRef}>
      <button
        type="button"
        className="export-btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        ↓ Export {open ? '▴' : '▾'}
      </button>
      {open && (
        <div className="export-menu" role="menu">
          <button
            type="button"
            className="export-menu-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onExportExcel();
            }}
          >
            <span>Excel workbook</span>
            <span className="export-menu-ext">.xlsx</span>
          </button>
          <button
            type="button"
            className="export-menu-item"
            role="menuitem"
            disabled={pdfLoading}
            onClick={() => {
              setOpen(false);
              onExportPdf();
            }}
          >
            <span>{pdfLoading ? 'Generating…' : 'PDF report'}</span>
            <span className="export-menu-ext">.pdf</span>
          </button>
          {onCopyFindings && (
            <button
              type="button"
              className="export-menu-item"
              role="menuitem"
              onClick={handleCopyFindings}
            >
              <span>{copyLabel}</span>
              <span className="export-menu-ext">Slack/email</span>
            </button>
          )}
          {onDownloadCleanedCsv && (
            <button
              type="button"
              className="export-menu-item"
              role="menuitem"
              disabled={cleanState === 'downloading'}
              onClick={handleDownloadCleaned}
            >
              <span>{cleanLabel}</span>
              <span className="export-menu-ext">.csv</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
