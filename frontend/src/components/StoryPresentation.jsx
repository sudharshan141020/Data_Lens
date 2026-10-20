import { useEffect, useRef, useState } from 'react';

const TONE_COLOR = {
  neutral: 'var(--teal)',
  warning: 'var(--red)',
  action: 'var(--amber)',
};

const btn = {
  padding: '10px 18px',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'transparent',
  color: 'inherit',
  cursor: 'pointer',
  fontSize: 15,
};

// Full-screen walkthrough of "The Story", one beat at a time, for presenting
// a result to other people. Keyboard: Right / Space / Enter advance, Left
// goes back, Escape closes. Clicking the slide advances (except on the last
// beat, where Done closes), and the dots jump straight to a beat.
export default function StoryPresentation({ story, onClose }) {
  const [index, setIndex] = useState(0);
  const count = story?.length || 0;
  const last = count - 1;

  // The parent passes a fresh onClose every render; hold it in a ref so the
  // keyboard listener is attached once and is removed when this unmounts.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const dialogRef = useRef(null);

  const next = () => setIndex((i) => Math.min(i + 1, last));
  const back = () => setIndex((i) => Math.max(i - 1, 0));

  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') { closeRef.current?.(); return; }
      if (e.key === 'ArrowRight') { e.preventDefault(); next(); return; }
      if (e.key === 'ArrowLeft') { e.preventDefault(); back(); return; }
      if (e.key === ' ' || e.key === 'Enter') {
        // On a focused button the browser's own click already does the job;
        // advancing here too would skip a beat.
        if (e.target?.tagName === 'BUTTON') return;
        e.preventDefault();
        next();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [last]);

  if (!count) return null;
  const beat = story[index];
  const color = TONE_COLOR[beat.tone] || 'var(--text-muted)';
  const isLast = index === last;

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Story presentation"
      tabIndex={-1}
      style={{
        position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', flexDirection: 'column',
        background: 'var(--ink)', color: 'var(--text)', outline: 'none',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px' }}>
        <span className="mono" style={{ color: 'var(--text-muted)' }}>{index + 1} / {count}</span>
        <button type="button" aria-label="Close presentation" onClick={() => closeRef.current?.()} style={{ ...btn, padding: '6px 12px' }}>
          ✕
        </button>
      </div>

      <div
        onClick={() => { if (!isLast) next(); }}
        style={{
          flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center',
          maxWidth: 900, width: '100%', margin: '0 auto', padding: '0 32px',
          cursor: isLast ? 'default' : 'pointer',
        }}
      >
        <span style={{ color, fontSize: 16, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 16 }}>
          {beat.label}
        </span>
        <p style={{ fontSize: 'clamp(24px, 4vw, 40px)', lineHeight: 1.35, margin: 0 }}>{beat.text}</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '8px 0' }}>
        {story.map((b, i) => (
          <button
            key={i}
            type="button"
            aria-label={`Go to slide ${i + 1}`}
            aria-current={i === index ? 'step' : undefined}
            onClick={() => setIndex(i)}
            style={{
              width: 12, height: 12, borderRadius: '50%', padding: 0, cursor: 'pointer',
              border: 'none', background: i === index ? color : 'var(--border)',
            }}
          />
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: 12, padding: '16px 24px 32px' }}>
        <button type="button" onClick={back} disabled={index === 0} style={{ ...btn, opacity: index === 0 ? 0.4 : 1 }}>
          ← Back
        </button>
        {isLast ? (
          <button type="button" onClick={() => closeRef.current?.()} style={{ ...btn, background: 'var(--teal)', color: 'var(--on-accent)', border: 'none' }}>
            Done
          </button>
        ) : (
          <button type="button" onClick={next} style={{ ...btn, background: 'var(--teal)', color: 'var(--on-accent)', border: 'none' }}>
            Next →
          </button>
        )}
      </div>
    </div>
  );
}
