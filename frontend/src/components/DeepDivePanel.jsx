import { useState } from 'react';
import DataQualityCenter from './DataQualityCenter';
import CorrelationCenter from './CorrelationCenter';
import PartialCorrelationsPanel from './PartialCorrelationsPanel';
import SegmentsPanel from './SegmentsPanel';
import SeasonalityPanel from './SeasonalityPanel';
import PeriodComparisonPanel from './PeriodComparisonPanel';
import CohortsPanel from './CohortsPanel';
import AnomaliesPanel from './AnomaliesPanel';
import SimpsonsParadoxPanel from './SimpsonsParadoxPanel';
import BenfordPanel from './BenfordPanel';
import ConfidenceIntervalsPanel from './ConfidenceIntervalsPanel';
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

export default function DeepDivePanel({ v2, tickNum }) {
  const [active, setActive] = useState(GROUPS[0].id);

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
            <SegmentsPanel segments={v2.segments} tickNum={null} />
            <SeasonalityPanel seasonality={v2.seasonality} tickNum={null} />
            <PeriodComparisonPanel periodComparison={v2.period_comparison} tickNum={null} />
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
            <ConfidenceIntervalsPanel confidenceIntervals={v2.confidence_intervals} tickNum={null} />
            <TextAnalysisPanel textAnalysis={v2.text_analysis} tickNum={null} />
          </>
        )}
      </div>
    </div>
  );
}
