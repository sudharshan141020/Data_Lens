import { useCallback, useRef, useState } from 'react';

const ACCEPTED_EXTENSIONS = ['.csv', '.tsv', '.xlsx', '.xls'];

function CloudIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 27a7 7 0 0 1-1-13.94A9 9 0 0 1 28 15.1 6.5 6.5 0 0 1 27 27H12Z"
        stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"
      />
      <path d="M20 19v10m0-10 3.5 3.5M20 19l-3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Pasted data (especially copied straight out of Excel/Sheets) usually
// comes tab-separated, not comma-separated -- sniff the first non-empty
// line so the synthesized file gets the right extension. The backend
// (app/main.py's _load_dataframe) picks its parser purely from the file
// extension: ".tsv" -> tab, anything else -> comma. Naming the file
// correctly here is the only thing that needs to be right for the
// existing upload pipeline to handle it with zero backend changes.
function sniffDelimiter(text) {
  const firstLine = text.split('\n').find((l) => l.trim().length > 0) || '';
  const tabs = (firstLine.match(/\t/g) || []).length;
  const commas = (firstLine.match(/,/g) || []).length;
  return tabs > commas ? '\t' : ',';
}

function buildFileFromPastedText(text) {
  const trimmed = text.trim();
  const lines = trimmed.split('\n').filter((l) => l.trim().length > 0);
  if (lines.length < 2) {
    return { file: null, error: 'Paste at least a header row and one data row.' };
  }
  const delimiter = sniffDelimiter(trimmed);
  const ext = delimiter === '\t' ? 'tsv' : 'csv';
  const blob = new Blob([trimmed], { type: 'text/csv' });
  return { file: new File([blob], `pasted-data.${ext}`, { type: 'text/csv' }), error: null };
}

function PasteImportPanel({ onFilesSelected, compact, onClose }) {
  const [text, setText] = useState('');

  const handleSubmit = () => {
    const { file, error } = buildFileFromPastedText(text);
    if (!file) {
      onFilesSelected([], error);
      return;
    }
    onFilesSelected([file], null);
    setText('');
    onClose();
  };

  return (
    <div className="upload-zone" style={{ display: 'block', cursor: 'default', padding: compact ? 16 : 28 }}>
      <p className="upload-sub" style={{ marginBottom: 8 }}>
        Paste rows copied from Excel, Google Sheets, or a CSV — first row should be headers.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'Name\tRevenue\tRegion\nAcme Co\t12000\tWest'}
        rows={compact ? 5 : 8}
        style={{
          width: '100%',
          resize: 'vertical',
          background: 'var(--surface-raised)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: '8px 10px',
          fontFamily: 'var(--font-mono)',
          fontSize: 12.5,
          boxSizing: 'border-box',
        }}
      />
      <div style={{ display: 'flex', gap: 10, marginTop: 10, alignItems: 'center' }}>
        <span className="upload-browse-btn" style={{ cursor: 'pointer' }} onClick={handleSubmit}>
          Analyze Pasted Data
        </span>
        <span className="upload-sub" style={{ cursor: 'pointer', textDecoration: 'underline' }} onClick={onClose}>
          Cancel
        </span>
      </div>
    </div>
  );
}

export default function UploadZone({ onFilesSelected, error, compact = false }) {
  const [isDragging, setIsDragging] = useState(false);
  const [pasteMode, setPasteMode] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = useCallback((fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    const valid = [];
    const rejected = [];
    for (const f of files) {
      const name = f.name.toLowerCase();
      if (ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
        valid.push(f);
      } else {
        rejected.push(f.name);
      }
    }

    const errorMsg = rejected.length
      ? `Skipped ${rejected.length} file(s) with unsupported type: ${rejected.join(', ')}`
      : null;

    if (valid.length) onFilesSelected(valid, errorMsg);
    else onFilesSelected([], errorMsg || 'Accepted formats: .csv, .tsv, .xlsx, .xls');
  }, [onFilesSelected]);

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  if (pasteMode) {
    return (
      <div className={compact ? 'upload-wrap-compact' : 'upload-wrap'}>
        <PasteImportPanel onFilesSelected={onFilesSelected} compact={compact} onClose={() => setPasteMode(false)} />
        {error && <p className="upload-error">{error}</p>}
      </div>
    );
  }

  return (
    <div className={compact ? 'upload-wrap-compact' : 'upload-wrap'}>
      <div
        className={`upload-zone ${isDragging ? 'dragging' : ''} ${compact ? 'compact' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.xls"
          multiple
          hidden
          onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
        />
        {compact ? (
          <span className="upload-compact-label">+ New analysis</span>
        ) : (
          <>
            <div className="upload-icon"><CloudIcon /></div>
            <p className="upload-title">Drop your data files here</p>
            <p className="upload-or">or</p>
            <span className="upload-browse-btn">Browse Files</span>
            <p className="upload-formats mono">CSV &nbsp;•&nbsp; XLSX &nbsp;•&nbsp; XLS</p>
          </>
        )}
      </div>
      <p className="upload-sub" style={{ marginTop: 10, cursor: 'pointer', textDecoration: 'underline' }}
         onClick={(e) => { e.stopPropagation(); setPasteMode(true); }}>
        or paste data instead
      </p>
      {error && <p className="upload-error">{error}</p>}
    </div>
  );
}

