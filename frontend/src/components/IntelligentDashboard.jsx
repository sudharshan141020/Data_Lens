import AnalysisChartV2 from './AnalysisChartV2';
import { FILTER_REACTIVE_TYPES } from '../filterUtils';

export default function IntelligentDashboard({ topAnalyses, tickNum, filtersActive }) {
  if (!topAnalyses?.length) return null;

  return (
    <div className="intelligent-dashboard">
      <div className="panel-head" style={{ marginBottom: 4 }}>
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Key Analyses</h3>
          <p className="dim-sub">The most important views into this dataset, chosen automatically</p>
        </div>
      </div>
      <div className="dashboard-3col">
        {topAnalyses.map((a) => (
          <div key={a.id} className="panel top-analysis-panel">
            <h4 className="top-analysis-title">{a.title}</h4>
            <AnalysisChartV2 analysis={a} />
            {a.reasoning && <p className="chart-reasoning">{a.reasoning}</p>}
            {a.forecast_note && <p className="forecast-note">↝ {a.forecast_note}</p>}
            {filtersActive && !FILTER_REACTIVE_TYPES.has(a.type) && (
              <p className="filter-inactive-note">Showing the full dataset — this view doesn't update with filters yet.</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
