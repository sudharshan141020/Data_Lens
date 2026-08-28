const TONE_COLOR = {
  neutral: 'var(--teal)',
  warning: 'var(--red)',
  action: 'var(--amber)',
};

export default function StoryMode({ story, tickNum }) {
  if (!story?.length) return null;

  return (
    <div className="panel story-panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>The Story</h3>
          <p className="dim-sub">What this dataset is telling you, in order</p>
        </div>
      </div>

      <div className="story-beats">
        {story.map((beat, i) => (
          <div className="story-beat" key={i} id={`search-story-${i}`}>
            <div className="story-beat-marker">
              <span className="story-beat-dot" style={{ background: TONE_COLOR[beat.tone] || 'var(--text-faint)' }} />
              {i < story.length - 1 && <span className="story-beat-line" />}
            </div>
            <div className="story-beat-body">
              <span className="story-beat-label" style={{ color: TONE_COLOR[beat.tone] || 'var(--text-muted)' }}>
                {beat.label}
              </span>
              <p className="story-beat-text">{beat.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
