import { useEffect, useRef, useState } from 'react';
import { defaultMaskSelection } from '../sensitiveUtils';

const ACTION_COPY = {
  share: { what: 'a share link', verb: 'Create share link', risk: 'Anyone with the link can read the full result, including the row-level data behind the filters.' },
  pdf: { what: 'a PDF report', verb: 'Export PDF', risk: 'The report is a file you can forward, so what is in it travels with it.' },
  html: { what: 'an HTML report', verb: 'Export HTML', risk: 'The report is a standalone file you can forward, so what is in it travels with it.' },
};

// Modal that stops a share/export when the scan found personal-data columns.
// The user picks one of three outcomes; nothing leaves the app until they do.
export default function SensitiveExportDialog({ action, report, variant = 'upload', onConfirm, onCancel }) {
  const copy = ACTION_COPY[action] || ACTION_COPY.share;
  const columns = (report?.columns || []).filter((c) => !c.masked);
  const [selected, setSelected] = useState(() => new Set(defaultMaskSelection(report)));
  const firstBtn = useRef(null);
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel; // the parent passes a fresh function every render; don't re-run the effect (and re-steal focus) for it

  useEffect(() => {
    firstBtn.current?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') cancelRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const toggle = (name) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sensitive-dialog-title"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', boxShadow: 'var(--shadow-raised)', maxWidth: 560, width: '100%', maxHeight: '90vh', overflowY: 'auto', padding: 20, }}
      >
        <h2 id="sensitive-dialog-title" style={{ margin: '0 0 12px', fontSize: 20 }}>Personal data may be included</h2>
        <p style={{ fontSize: 14, lineHeight: 1.5, margin: '0 0 8px' }}>
          {variant === 'server'
            ? <>The server checked what is about to be shared and found personal data that the first check did not. {copy.risk} It found:</>
            : <>You're about to create {copy.what}. {copy.risk} These columns look like personal information:</>}
        </p>
        <ul style={{ listStyle: 'none', padding: 0, margin: '12px 0' }}>
          {columns.map((c) => (
            <li key={c.column} style={{ marginBottom: 8 }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: c.maskable === false ? 'default' : 'pointer' }}>
                {c.maskable === false
                  ? <span aria-hidden="true" style={{ width: 13, flex: 'none' }} />
                  : <input type="checkbox" checked={selected.has(c.column)} onChange={() => toggle(c.column)} aria-label={`Mask ${c.column}`} />}
                <span>
                  <span className="mono">{c.column}</span>
                  <span className="dim-sub"> — {c.reason} ({c.confidence} confidence)</span>
                  {c.maskable === false && <span className="dim-sub"> It can't be masked automatically: continue to share it as is, or cancel and remove it.</span>}
                </span>
              </label>
            </li>
          ))}
        </ul>
        <p className="dim-sub" style={{ lineHeight: 1.5 }}>
          Masking swaps the real values for stable placeholders like "Customer ID 7" everywhere in the copy that
          leaves the app, so charts and filters still work. Your own session is not changed. This check is
          pattern-based: it can miss things, so look through the result yourself before sharing publicly.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end', marginTop: 16 }}>
          <button type="button" onClick={onCancel} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>Cancel</button>
          <button type="button" onClick={() => onConfirm({ columns: [] })} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>Continue without masking</button>
          <button type="button" ref={firstBtn} disabled={selected.size === 0} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'inherit', cursor: 'pointer', background: 'var(--teal)', color: 'var(--on-accent)', border: 'none', opacity: selected.size === 0 ? 0.5 : 1 }} onClick={() => onConfirm({ columns: [...selected] })}>
            Mask {selected.size} selected &amp; continue
          </button>
        </div>
      </div>
    </div>
  );
}
