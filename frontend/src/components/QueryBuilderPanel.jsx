import { useMemo, useState, useEffect } from 'react';
import AnalysisChartV2 from './AnalysisChartV2';
import { runCustomQuery, chooseQueryChartType } from '../filterUtils';

const AGG_LABELS = { sum: 'Total', avg: 'Average', count: 'Count of records' };

export default function QueryBuilderPanel({ filterableData, rows, tickNum }) {
  const dimensionColumns = filterableData?.dimension_columns || [];
  const measureColumns = filterableData?.measure_columns || [];

  const [measure, setMeasure] = useState('');
  const [aggregation, setAggregation] = useState('sum');
  const [dim1, setDim1] = useState('');
  const [dim2, setDim2] = useState('');

  // Pick sensible defaults as soon as real columns show up, so the panel
  // shows a real result immediately instead of an empty "pick something" state.
  useEffect(() => {
    if (!dim1 && dimensionColumns.length) setDim1(dimensionColumns[0]);
    if (!measure && measureColumns.length) setMeasure(measureColumns[0]);
  }, [dimensionColumns, measureColumns]); // eslint-disable-line react-hooks/exhaustive-deps

  const data = useMemo(() => {
    if (!dim1) return null;
    return runCustomQuery(rows, { measure, aggregation, dim1, dim2: dim2 || null });
  }, [rows, measure, aggregation, dim1, dim2]);

  if (!filterableData?.available || dimensionColumns.length === 0) return null;

  const cardinality = data ? new Set(data.map((d) => d.x ?? d.label)).size : 0;
  const chartType = dim1 && (data?.length ? chooseQueryChartType(!!dim2, cardinality, aggregation) : null);

  const analysis = data?.length ? {
    type: dim2 ? 'pivot' : (aggregation === 'count' ? 'distribution_count' : 'distribution_sum'),
    chart_type: chartType,
    column: dim1,
    column2: dim2 || undefined,
    metric_column: aggregation === 'count' ? undefined : measure,
    aggregation,
    data,
  } : null;

  const captionMetric = aggregation === 'count' ? 'records' : measure;
  const caption = dim2
    ? `${AGG_LABELS[aggregation]} of ${captionMetric}, by ${dim1} \u00d7 ${dim2}`
    : `${AGG_LABELS[aggregation]} of ${captionMetric}, by ${dim1}`;

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>Ask Your Own Question</h3>
          <p className="dim-sub">Pick a measure and a dimension to build a custom view — updates instantly, no page reload</p>
        </div>
      </div>

      <div className="query-builder-controls">
        <div className="query-builder-field">
          <label>Aggregation</label>
          <select className="query-builder-select" value={aggregation} onChange={(e) => setAggregation(e.target.value)}>
            <option value="sum">Total</option>
            <option value="avg">Average</option>
            <option value="count">Count of records</option>
          </select>
        </div>

        {aggregation !== 'count' && (
          <div className="query-builder-field">
            <label>Of</label>
            <select className="query-builder-select" value={measure} onChange={(e) => setMeasure(e.target.value)}>
              {measureColumns.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        )}

        <div className="query-builder-field">
          <label>Broken down by</label>
          <select className="query-builder-select" value={dim1} onChange={(e) => setDim1(e.target.value)}>
            {dimensionColumns.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        {dimensionColumns.length > 1 && (
          <div className="query-builder-field">
            <label>And by (optional)</label>
            <select className="query-builder-select" value={dim2} onChange={(e) => setDim2(e.target.value)}>
              <option value="">— none —</option>
              {dimensionColumns.filter((d) => d !== dim1).map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
        )}
      </div>

      {analysis ? (
        <div style={{ marginTop: 16 }}>
          <p className="dim-sub" style={{ marginBottom: 8 }}>{caption}</p>
          <AnalysisChartV2 analysis={analysis} />
        </div>
      ) : (
        <p className="dim-sub" style={{ padding: '12px 0' }}>
          {dim1 ? 'No rows match this combination.' : 'Pick a dimension above to see a result.'}
        </p>
      )}
    </div>
  );
}
