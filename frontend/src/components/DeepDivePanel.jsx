import { useState } from 'react';
import DataQualityCenter from './DataQualityCenter';
import CorrelationCenter from './CorrelationCenter';
import PartialCorrelationsPanel from './PartialCorrelationsPanel';
import SegmentsPanel from './SegmentsPanel';
import SeasonalityPanel from './SeasonalityPanel';
import PeriodComparisonPanel from './PeriodComparisonPanel';
import DriversPanel from './DriversPanel';
import CohortsPanel from './CohortsPanel';
import AnomaliesPanel from './AnomaliesPanel';
import SimpsonsParadoxPanel from './SimpsonsParadoxPanel';
import BenfordPanel from './BenfordPanel';
import ConfidenceIntervalsPanel from './ConfidenceIntervalsPanel';
import RobustnessPanel from './RobustnessPanel';
import TextAnalysisPanel from './TextAnalysisPanel';

// Groups the panels that piled up one-per-feature over the course of
// development into a browsable set of tabs, the same way AnalysisExplorerV2
// already groups charts by section -- reuses its exact tab classes
// (explorer-tabs/explorer-tab) so this reads as the same UI pattern, not
// a second one. Every panel already renders its own "not available" state
// internally, so a tab is always shown even if everything in it happens
// to be unavailable for this dataset -- simpler and safer than each tab
// needing to know every panel's availability shape to decide whether to
// show itself.
const GROUPS = [
  { id: 'quality', label: 'Quality & Relationships' },
  { id: 'patterns', label: 'Patterns' },
  { id: 'integrity', label: 'Anomalies & Integrity' },
  { id: 'precision', label: 'Precision & Text' },
];

const FILTERED_PANELS = 'Seasonality, Period Comparison, Why Did It Change? and Robustness';

// Tells the person which numbers follow the filter bar and which do not. Without it the same page would mix
// reports about the filtered rows with reports about everything, and nothing would say which was which.
function FilteredNote({ filtered, totalRows }) {
  let text;
  if (filtered.status === 'loading') text = 'Updating for your filters…';
  else if (filtered.status === 'ready') {
    text = `Filters are on. ${FILTERED_PANELS} describe the ${filtered.rowsUsed.toLocaleString('en-US')} of ${totalRows.toLocaleString('en-US')} rows you are looking at. The other panels here still describe the full dataset.`;
  } else if (filtered.status === 'error') text = `${filtered.note} Those four panels show the full dataset instead.`;
  else if (filtered.status === 'blocked') text = `${filtered.note} Those four panels describe the full dataset.`;
  else return null;
  return (
    <p className="dim-sub" role="status" aria-live="polite" style={{ margin: '0 0 12px', padding: '8px 12px', borderRadius: 8, background: 'var(--surface-raised)', border: '1px solid var(--border)' }}>
      {text}
    </p>
  );
}

function UpdatingPlaceholder({ name }) {
  return (
    <div className="panel" aria-busy="true">
      <div className="panel-head"><h3>{name}</h3></div>
      <p className="dim-sub" style={{ padding: '4px 0 16px' }}>Updating for your filters…</p>
    </div>
  );
}

export default function DeepDivePanel({ v2, tickNum, filtered = null, totalRows = 0 }) {
  const [active, setActive] = useState(GROUPS[0].id);
  const following = filtered && filtered.status === 'ready' && filtered.reports;
  const updating = filtered && filtered.status === 'loading';
  const report = (key) => (following ? filtered.reports[key] : v2[key]);
  const note = filtered && filtered.status !== 'idle' ? <FilteredNote filtered={filtered} totalRows={totalRows} /> : null;

  return (
    <div className="panel deep-dive-panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <h3>Deep Dive</h3>
      </div>

      <div className="explorer-tabs">
        {GROUPS.map((g) => (
          <button
            key={g.id}
            className={`explorer-tab ${g.id === active ? 'active' : ''}`}
            onClick={() => setActive(g.id)}
          >
            {g.label}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 16 }}>
        {active === 'quality' && (
          <>
            <DataQualityCenter dataQuality={v2.data_quality} tickNum={null} />
            <CorrelationCenter correlationCenter={v2.correlation_center} tickNum={null} />
            <PartialCorrelationsPanel partialCorrelations={v2.partial_correlations} tickNum={null} />
          </>
        )}
        {active === 'patterns' && (
          <>
            {note}
            <SegmentsPanel segments={v2.segments} tickNum={null} />
            {updating ? <UpdatingPlaceholder name="Seasonality" /> : <SeasonalityPanel seasonality={report('seasonality')} tickNum={null} />}
            {updating ? <UpdatingPlaceholder name="Period Comparison" /> : <PeriodComparisonPanel periodComparison={report('period_comparison')} tickNum={null} />}
            {updating ? <UpdatingPlaceholder name="Why Did It Change?" /> : <DriversPanel drivers={report('drivers')} tickNum={null} />}
            <CohortsPanel cohorts={v2.cohorts} tickNum={null} />
          </>
        )}
        {active === 'integrity' && (
          <>
            <AnomaliesPanel anomalies={v2.anomalies} tickNum={null} />
            <SimpsonsParadoxPanel simpsonsParadox={v2.simpsons_paradox} tickNum={null} />
            <BenfordPanel benford={v2.benford} tickNum={null} />
          </>
        )}
        {active === 'precision' && (
          <>
            {note}
            <ConfidenceIntervalsPanel confidenceIntervals={v2.confidence_intervals} tickNum={null} />
            {updating ? <UpdatingPlaceholder name="Does This Hold Without the Outliers?" /> : <RobustnessPanel robustness={report('robustness')} tickNum={null} />}
            <TextAnalysisPanel textAnalysis={v2.text_analysis} tickNum={null} />
          </>
        )}
      </div>
    </div>
  );
}
