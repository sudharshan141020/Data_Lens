import { SAMPLE_DATASETS } from '../api';

export default function SampleGallery({ onTrySample, loadingId }) {
  return (
    <div className="sample-gallery">
      <p className="sample-gallery-label">Or try a sample dataset — no upload needed</p>
      <div className="sample-gallery-grid">
        {SAMPLE_DATASETS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="sample-card"
            onClick={() => onTrySample(s)}
            disabled={loadingId !== null}
          >
            <span className="sample-card-label">{s.label}</span>
            <span className="sample-card-desc">
              {loadingId === s.id ? 'Loading…' : s.description}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
